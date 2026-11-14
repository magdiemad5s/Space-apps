"""Independently check saved noise_004 predictions, masks and frozen hashes.

Uses TRAIN plus saved experiment artifacts only. Does not fit any model.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json

import numpy as np
import pandas as pd
from sklearn.metrics import f1_score, precision_score, recall_score

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
EXP = ROOT / "experiments/noise_004"
NAMES = {"unchanged_rf_control": "control", "rf_fit_tail_exclusion": "exclude",
         "rf_fit_tail_weight_0.25": "downweight", "current_fatigue_persistence": "persistence"}
LABELS = ["low", "moderate", "high"]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_metrics(truth, prediction, row):
    scores = {
        "macro_f1": f1_score(truth, prediction, labels=LABELS, average="macro", zero_division=0),
        "high_precision": precision_score(np.asarray(truth) == "high", np.asarray(prediction) == "high", zero_division=0),
        "high_recall": recall_score(np.asarray(truth) == "high", np.asarray(prediction) == "high", zero_division=0),
    }
    for name, value in scores.items():
        assert abs(value - getattr(row, name)) < 1e-12, (name, value, row)
    return scores


def main():
    plan = json.loads((EXP / "plan.json").read_text())
    summary = json.loads((EXP / "summary.json").read_text())
    paths = {"source_train_sha256": ROOT / "data/train.csv",
             "official_bundle_sha256_before": ROOT / "artifacts/bundle.joblib",
             "task_config_sha256": ROOT / "data/task_config.json",
             "source_folds_sha256": ROOT / "experiments/improvement_002/participant_folds.csv",
             "script_sha256": ROOT / "astra_shield_ml/noise_cleaning_experiment.py"}
    hash_checks = {key: sha(path) == plan[key] for key, path in paths.items()}
    assert all(hash_checks.values()), hash_checks
    train = pd.read_csv(ROOT / "data/train.csv")
    folds = pd.read_csv(EXP / "participant_folds.csv").set_index("participant_id").held_out_fold
    preds = pd.read_csv(EXP / "groupcv_predictions.csv")
    metrics = pd.read_csv(EXP / "groupcv_fold_metrics.csv")
    temporal = pd.read_csv(EXP / "temporal_predictions.csv")
    temporal_metrics = pd.read_csv(EXP / "temporal_metrics.csv")
    assert len(preds) == 5040 and preds.record_id.is_unique
    assert set(preds.record_id) == set(train.record_id)
    assert preds.groupby("participant_id").held_out_fold.nunique().eq(1).all()
    indexed = train.set_index("record_id")
    assert np.array_equal(preds.true_label, indexed.loc[preds.record_id, plan["target"]])
    assert np.array_equal(preds.held_out_fold, preds.participant_id.map(folds))
    rows = []
    for row in metrics.itertuples():
        part = preds[preds.held_out_fold.eq(row.fold)]
        assert len(part) == row.held_out_rows == 1680
        scores = check_metrics(part.true_label, part[row.candidate], row)
        rows.append({"evaluation": "group_cv", "variant": NAMES[row.candidate], "fold": row.fold, **scores})
    for row in temporal_metrics.itertuples():
        part = temporal[temporal.candidate.eq(row.candidate) & temporal.temporal_fold.eq(row.temporal_fold)]
        expected = train[train.mission_day.between(row.evaluation_day_start, row.evaluation_day_end)]
        assert part.record_id.is_unique and len(part) == row.held_out_rows == 1176
        assert set(part.record_id) == set(expected.record_id)
        assert np.array_equal(part.true_label, indexed.loc[part.record_id, plan["target"]])
        scores = check_metrics(part.true_label, part.prediction, row)
        rows.append({"evaluation": "temporal", "variant": NAMES[row.candidate], "fold": row.temporal_fold, **scores})
    subgroup = pd.read_csv(EXP / "oof_event_subgroup_metrics.csv")
    for row in subgroup.itertuples():
        part = preds[preds.current_simulator_event.eq(row.current_simulator_event)]
        assert len(part) == row.held_out_rows
        check_metrics(part.true_label, part[row.candidate], row)
    flags = pd.read_csv(EXP / "fit_tail_flags.csv")
    thresholds = pd.read_csv(EXP / "detector_thresholds.csv")
    stage_results = []
    for stage in pd.read_csv(EXP / "fit_stage_summary.csv").itertuples():
        ix = int(stage.stage_id.rsplit("_", 1)[1])
        if stage.stage_id.startswith("group"):
            fitting = train[train.participant_id.map(folds).ne(ix)]
        else:
            spec = plan["temporal_evaluations"][ix]
            fitting = train[train.mission_day.between(*spec["fit_days"])]
            assert fitting.mission_day.max() + 1 <= spec["label_cutoff_day"] < spec["evaluation_days"][0]
        values = fitting[plan["detector"]["features"]]
        med = values.median()
        mad = (values - med).abs().median()
        nonzero = mad.gt(0)
        mask = ((values.loc[:, nonzero] - med[nonzero]).abs() / (1.4826 * mad[nonzero])).gt(4.5).any(axis=1)
        assert int(mask.sum()) == stage.flagged_rows
        assert set(fitting.loc[mask, "record_id"]) == set(flags[flags.stage_id.eq(stage.stage_id)].record_id)
        for th in thresholds[thresholds.stage_id.eq(stage.stage_id)].itertuples():
            assert abs(med[th.feature] - th.median) < 1e-12
            assert abs(mad[th.feature] - th.mad) < 1e-12
        stage_results.append({"stage": stage.stage_id, "flagged_rows": int(mask.sum()), "independent_mask_matches": True})
    # Compute participant-bootstrap intervals independently from summed 3x3
    # confusion matrices, rather than repeatedly calling the experiment's F1 code.
    ids = sorted(preds.participant_id.unique())
    maps = {label: index for index, label in enumerate(LABELS)}
    matrices = {}
    for candidate in NAMES:
        cms = []
        for pid in ids:
            part = preds[preds.participant_id.eq(pid)]
            pairs = part.true_label.map(maps).to_numpy() * 3 + part[candidate].map(maps).to_numpy()
            cms.append(np.bincount(pairs, minlength=9).reshape(3, 3))
        matrices[candidate] = np.asarray(cms)
    rng = np.random.default_rng(plan["seed"])
    samples = rng.choice(len(ids), size=(1000, len(ids)), replace=True)
    def f1_from_matrices(cms):
        sums = cms[samples].sum(axis=1)
        numer = 2 * np.diagonal(sums, axis1=1, axis2=2)
        denom = sums.sum(axis=1) + sums.sum(axis=2)
        return np.divide(numer, denom, out=np.zeros_like(numer, dtype=float), where=denom != 0).mean(axis=1)
    reference = f1_from_matrices(matrices["unchanged_rf_control"])
    bootstrap_checks = {}
    for name in ("rf_fit_tail_exclusion", "rf_fit_tail_weight_0.25"):
        interval = np.quantile(f1_from_matrices(matrices[name]) - reference, [.025, .975])
        expected = summary["paired_participant_bootstrap"][name]["percentile_95ci"]
        assert np.allclose(interval, expected, atol=1e-12, rtol=0), (interval, expected)
        bootstrap_checks[name] = interval.tolist()
    output = {"verified_at_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "TRAIN and saved predictions only; no model fits or validation/test reads.",
              "hash_checks": hash_checks, "group_cv_metric_rows_verified": len(metrics),
              "temporal_metric_rows_verified": len(temporal_metrics),
              "event_subgroup_metric_rows_verified": len(subgroup),
              "fitting_mask_checks": stage_results, "bootstrap_interval_checks": bootstrap_checks,
              "all_passed": True}
    pd.DataFrame(rows).to_csv(OUT / "verified_comparison.csv", index=False)
    (OUT / "INDEPENDENT_VERIFICATION.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
