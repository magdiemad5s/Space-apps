"""Independent review of saved filter_validation_005 artifacts.

Reads only the training partition, experiment predictions, historical predictions,
metadata, source and trusted local model artifacts. No model is fitted and no
original validation/test observation file is opened.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import classification_report, confusion_matrix, f1_score

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
EXP = ROOT / "experiments/filter_validation_005"
CONTROL = "control_rf_full_training"
FILTERED = "filtered_rf_fit_tail_exclusion"
PERSISTENCE = "current_fatigue_persistence"
LABELS = ["low", "moderate", "high"]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    plan = json.loads((EXP / "plan.json").read_text())
    summary = json.loads((EXP / "summary.json").read_text())
    mask_freeze = json.loads((EXP / "training_mask_frozen.json").read_text())
    fit_completed = json.loads((EXP / "fit_completed_before_validation.json").read_text())
    frozen = json.loads((ROOT / "artifacts/frozen_manifest.json").read_text())
    paths = {
        "train_sha256": ROOT / "data/train.csv",
        "official_bundle_sha256_before": ROOT / "artifacts/bundle.joblib",
        "task_config_sha256": ROOT / "data/task_config.json",
        "script_sha256": ROOT / "astra_shield_ml/filter_validation_experiment.py",
        "reused_noise_rule_script_sha256": ROOT / "astra_shield_ml/noise_cleaning_experiment.py",
    }
    hash_checks = {key: sha(path) == plan[key] for key, path in paths.items()}
    hash_checks["thresholds_match_mask_freeze"] = sha(EXP / "fixed_training_thresholds.csv") == mask_freeze["thresholds_sha256"]
    hash_checks["flagged_ids_match_mask_freeze"] = sha(EXP / "flagged_training_record_ids.csv") == mask_freeze["flagged_record_ids_sha256"]
    hash_checks["candidate_matches_before_validation_checkpoint"] = sha(EXP / "filtered_candidate.joblib") == fit_completed["candidate_sha256"]
    hash_checks["expected_validation_hash_matches_original_manifest"] = plan["expected_validation_sha256_from_existing_frozen_manifest"] == frozen["data_sha256"]["data/validation.csv"]
    assert all(hash_checks.values()), hash_checks
    train = pd.read_csv(ROOT / "data/train.csv")
    assert len(train) == 5040 and train.participant_id.nunique() == 84
    assert train.split.eq("train").all() and train.record_id.is_unique
    columns = plan["fixed_rule"]["features"]
    assert len(columns) == 4 and not any(c.startswith("target_") for c in columns)
    values = train[columns]
    median = values.median()
    mad = (values - median).abs().median()
    active = mad.gt(0)
    flags = ((values.loc[:, active] - median[active]).abs() / (1.4826 * mad[active])).gt(4.5).any(axis=1)
    flagged = pd.read_csv(EXP / "flagged_training_record_ids.csv")
    assert int(flags.sum()) == mask_freeze["calculated_flags"] == 254
    assert int((~flags).sum()) == summary["retained_candidate_fit_rows"] == 4786
    assert flagged.record_id.is_unique and set(flagged.record_id) == set(train.loc[flags, "record_id"])
    thresholds = pd.read_csv(EXP / "fixed_training_thresholds.csv")
    for row in thresholds.itertuples():
        assert abs(row.median - median[row.feature]) < 1e-12
        assert abs(row.mad - mad[row.feature]) < 1e-12
        assert abs(row.lower_threshold - (median[row.feature] - 4.5 * 1.4826 * mad[row.feature])) < 1e-12
        assert abs(row.upper_threshold - (median[row.feature] + 4.5 * 1.4826 * mad[row.feature])) < 1e-12
    target = plan["target"]
    full_counts = {str(k): int(v) for k, v in train[target].value_counts().items()}
    retained_counts = {str(k): int(v) for k, v in train.loc[~flags, target].value_counts().items()}
    assert full_counts == fit_completed["training_class_counts"]
    assert retained_counts == fit_completed["retained_training_class_counts"]
    fitted = joblib.load(EXP / "filtered_candidate.joblib")
    assert fitted["features"] == plan["rf_feature_allowlist"]
    assert fitted["training_rows"] == 4786 and fitted["plan_sha256"] == sha(EXP / "plan.json")
    model = fitted["estimator"].named_steps["model"]
    for name, value in plan["rf_parameters"].items():
        assert model.get_params()[name] == value
    assert model.n_features_in_ == 26
    expected_medians = train.loc[~flags, fitted["features"]].median().to_numpy()
    assert np.allclose(fitted["estimator"].named_steps["imputer"].statistics_, expected_medians, atol=1e-12, rtol=0)
    predictions = pd.read_csv(EXP / "validation_predictions.csv")
    assert len(predictions) == 1080 and predictions.record_id.is_unique
    assert predictions.participant_id.nunique() == 18
    assert predictions.groupby("participant_id").size().eq(60).all()
    assert set(predictions.participant_id).isdisjoint(train.participant_id)
    historical = pd.read_csv(ROOT / "experiments/eda_first_001/validation_predictions.csv")
    joined = predictions.merge(historical[["record_id", "target_next_day_fatigue_class", "full_26__random_forest_balanced"]],
                               on="record_id", validate="one_to_one")
    assert len(joined) == 1080
    assert joined.true_label.eq(joined.target_next_day_fatigue_class).all()
    assert joined[CONTROL + "__prediction"].eq(joined.full_26__random_forest_balanced).all()
    recomputed = {}
    for candidate in plan["candidates"]:
        pred = predictions[candidate + "__prediction"]
        report = classification_report(predictions.true_label, pred, labels=LABELS, output_dict=True, zero_division=0)
        score = float(f1_score(predictions.true_label, pred, labels=LABELS, average="macro", zero_division=0))
        cm = confusion_matrix(predictions.true_label, pred, labels=LABELS).tolist()
        expected = summary["metrics"][candidate]
        assert abs(score - expected["macro_f1"]) < 1e-12
        for metric in ("precision", "recall"):
            assert abs(report["high"][metric] - expected["high_" + metric]) < 1e-12
        assert cm == expected["confusion_matrix"]
        for label in LABELS:
            for metric in ("precision", "recall", "f1-score", "support"):
                assert abs(report[label][metric] - expected["classification_report"][label][metric]) < 1e-12
        probability_cols = [candidate + "__model_probability_" + label for label in LABELS]
        p = predictions[probability_cols].to_numpy()
        assert np.isfinite(p).all() and (p >= 0).all() and (p <= 1).all()
        assert np.allclose(p.sum(axis=1), 1, atol=2e-12, rtol=0)
        recomputed[candidate] = {"macro_f1": score, "high_precision": report["high"]["precision"],
                                 "high_recall": report["high"]["recall"], "confusion_matrix": cm}
    subgroup = pd.read_csv(EXP / "validation_event_subgroup_metrics.csv")
    for row in subgroup.itertuples():
        part = predictions[predictions.current_simulator_event.eq(row.current_simulator_event)]
        assert len(part) == row.validation_rows
        report = classification_report(part.true_label, part[row.candidate + "__prediction"], labels=LABELS, output_dict=True, zero_division=0)
        assert abs(report["macro avg"]["f1-score"] - row.macro_f1) < 1e-12
        assert abs(report["high"]["precision"] - row.high_precision) < 1e-12
        assert abs(report["high"]["recall"] - row.high_recall) < 1e-12
    # Independent paired bootstrap from per-person confusion matrices.
    ids = sorted(predictions.participant_id.unique())
    label_map = {label: index for index, label in enumerate(LABELS)}
    matrices = {}
    for candidate in (CONTROL, FILTERED):
        per_person = []
        for pid in ids:
            part = predictions[predictions.participant_id.eq(pid)]
            pairs = 3 * part.true_label.map(label_map).to_numpy() + part[candidate + "__prediction"].map(label_map).to_numpy()
            per_person.append(np.bincount(pairs, minlength=9).reshape(3, 3))
        matrices[candidate] = np.asarray(per_person)
    uncertainty = summary["paired_participant_bootstrap"]
    sampled = np.random.default_rng(plan["seed"]).choice(len(ids), size=(1000, len(ids)), replace=True)
    scores = {}
    recalls = {}
    for candidate in (CONTROL, FILTERED):
        cms = matrices[candidate][sampled].sum(axis=1)
        numerator = 2 * np.diagonal(cms, axis1=1, axis2=2)
        denominator = cms.sum(axis=1) + cms.sum(axis=2)
        scores[candidate] = np.divide(numerator, denominator, out=np.zeros_like(numerator, dtype=float), where=denominator != 0).mean(axis=1)
        high_total = cms[:, 2, :].sum(axis=1)
        recalls[candidate] = np.divide(cms[:, 2, 2], high_total, out=np.zeros_like(high_total, dtype=float), where=high_total != 0)
    f1_interval = np.quantile(scores[FILTERED] - scores[CONTROL], [.025, .975])
    recall_interval = np.quantile(recalls[FILTERED] - recalls[CONTROL], [.025, .975])
    assert np.allclose(f1_interval, uncertainty["macro_f1_difference_percentile_95ci"], atol=1e-12, rtol=0)
    assert np.allclose(recall_interval, uncertainty["high_recall_difference_percentile_95ci"], atol=1e-12, rtol=0)
    result = {"verified_at_utc": datetime.now(timezone.utc).isoformat(),
              "source_scope": "TRAIN, saved predictions, source and trusted artifacts only; no original validation/test observation reads and no fitting",
              "hash_checks": hash_checks, "training_rows": 5040, "independently_flagged_rows": 254,
              "retained_fitting_rows": 4786, "retained_class_counts": retained_counts,
              "validation_predictions_checked": 1080, "validation_participants": 18,
              "historical_control_predictions_match_by_record_id": True,
              "candidate_parameters_and_imputer_verified": True,
              "recomputed_metrics": recomputed,
              "event_subgroup_rows_verified": len(subgroup),
              "independent_bootstrap_macro_f1_difference_interval": f1_interval.tolist(),
              "independent_bootstrap_high_recall_difference_interval": recall_interval.tolist(),
              "implementation_review": {"detector_fit_on_train_only": True,
                  "all_fits_precede_validation_load": True, "original_target_and_history_values_preserved": True,
                  "validation_not_filtered": True, "test_not_opened_in_reviewed_script": True},
              "all_checks_passed": True}
    (OUT / "VERIFICATION.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
