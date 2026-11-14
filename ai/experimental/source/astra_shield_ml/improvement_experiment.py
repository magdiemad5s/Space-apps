"""One bounded development experiment; existing production/demo artifacts stay fixed.

Candidate selection uses participant-grouped CV within training only. Existing
validation is examined only after selection and is explicitly reused development
validation. This command never opens data/test.csv or an uploaded full dataset.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix, f1_score, recall_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .estimators import PersistenceClassifier

SEED = 20261114
LABELS = ["low", "moderate", "high"]
TASK = "next_day_fatigue_classification"
CONTROL = "current_rf_leaf8_depth14"
PERSISTENCE = "current_fatigue_persistence"
SPECS = [
    {"name": CONTROL, "kind": "rf", "leaf": 8, "depth": 14, "complexity_rank": 7},
    {"name": "rf_leaf16_depth10", "kind": "rf", "leaf": 16, "depth": 10, "complexity_rank": 6},
    {"name": "rf_leaf32_depth8", "kind": "rf", "leaf": 32, "depth": 8, "complexity_rank": 5},
    {"name": "rf_leaf48_depth6", "kind": "rf", "leaf": 48, "depth": 6, "complexity_rank": 4},
    {"name": "balanced_logistic_C0.1", "kind": "logistic", "C": .1, "complexity_rank": 2},
    {"name": "balanced_logistic_C1", "kind": "logistic", "C": 1., "complexity_rank": 3},
    {"name": PERSISTENCE, "kind": "persistence", "complexity_rank": 1},
    {"name": "majority_class", "kind": "majority", "complexity_rank": 0},
]


def now():
    return datetime.now(timezone.utc).isoformat()


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False)+"\n")


def make_model(spec):
    if spec["kind"] == "persistence":
        return PersistenceClassifier()
    if spec["kind"] == "majority":
        return DummyClassifier(strategy="most_frequent")
    if spec["kind"] == "rf":
        estimator = RandomForestClassifier(
            n_estimators=200, min_samples_leaf=spec["leaf"], max_depth=spec["depth"],
            class_weight="balanced", random_state=SEED, n_jobs=2)
        return Pipeline([("imputer", SimpleImputer(strategy="median")), ("model", estimator)])
    return Pipeline([("imputer", SimpleImputer(strategy="median")),
                     ("scaler", StandardScaler()),
                     ("model", LogisticRegression(C=spec["C"], class_weight="balanced",
                                                  max_iter=2000, random_state=SEED))])


def measure(y, prediction):
    report = classification_report(y, prediction, labels=LABELS, output_dict=True, zero_division=0)
    return {"macro_f1": float(f1_score(y, prediction, labels=LABELS, average="macro", zero_division=0)),
            "high_recall": float(report["high"]["recall"]),
            "high_precision": float(report["high"]["precision"]),
            "accuracy": float(np.mean(np.asarray(y) == np.asarray(prediction))),
            "classification_report": report,
            "confusion_matrix_labels": LABELS,
            "confusion_matrix": confusion_matrix(y, prediction, labels=LABELS).tolist()}


def paired_bootstrap(frame, predictions, selected, comparison, repetitions=1000):
    """Resample whole participants, preserving all correlated days together."""
    ids = np.asarray(sorted(frame.participant_id.unique()))
    positions = {pid: np.flatnonzero(frame.participant_id.to_numpy() == pid) for pid in ids}
    y = frame._true_label.to_numpy()
    a, b = predictions[selected], predictions[comparison]
    rng = np.random.default_rng(SEED)
    differences = []
    recall_differences = []
    for _ in range(repetitions):
        sampled = rng.choice(ids, size=len(ids), replace=True)
        ix = np.concatenate([positions[pid] for pid in sampled])
        differences.append(float(f1_score(y[ix], a[ix], labels=LABELS, average="macro", zero_division=0)
                                 - f1_score(y[ix], b[ix], labels=LABELS, average="macro", zero_division=0)))
        high = y[ix] == "high"
        recall_differences.append(float((a[ix][high] == "high").mean() - (b[ix][high] == "high").mean()) if high.any() else 0.)
    observed = measure(y, a)["macro_f1"] - measure(y, b)["macro_f1"]
    return {"method": "paired whole-participant bootstrap; repeated development validation",
            "repetitions": repetitions, "participants": len(ids), "seed": SEED,
            "comparison": comparison, "macro_f1_difference_selected_minus_comparison": observed,
            "macro_f1_difference_percentile_95ci": np.quantile(differences, [.025, .975]).tolist(),
            "high_recall_difference_percentile_95ci": np.quantile(recall_differences, [.025, .975]).tolist(),
            "fraction_bootstrap_differences_above_zero": float((np.asarray(differences) > 0).mean()),
            "interpretation": "Descriptive uncertainty on reused synthetic development validation; not a new independent or clinical test"}


def main(project_dir=None):
    root = Path(project_dir or Path(__file__).resolve().parents[1])
    output = root / "experiments/improvement_002"
    output.mkdir(parents=True, exist_ok=True)
    if (output / "plan.json").exists():
        raise RuntimeError("This prespecified experiment already exists. Do not overwrite or adapt it after seeing results.")
    start = time.perf_counter()
    training_path, config_path = root / "data/train.csv", root / "data/task_config.json"
    train = pd.read_csv(training_path)
    config = json.loads(config_path.read_text())
    features, target = config["tasks"][TASK]["predictors"], config["tasks"][TASK]["target"]
    assert train.split.eq("train").all() and train.is_synthetic.eq(1).all()
    assert train.record_id.is_unique and not train.isna().any().any()
    assert not any(c.startswith("target_") for c in features)
    ids = np.asarray(sorted(train.participant_id.unique()))
    shuffled = np.random.default_rng(SEED).permutation(ids)
    fold_map = {pid: int(i % 3) for i,pid in enumerate(shuffled)}
    folds = pd.DataFrame({"participant_id": sorted(fold_map),
                          "held_out_fold": [fold_map[pid] for pid in sorted(fold_map)]})
    assert folds.participant_id.is_unique
    folds.to_csv(output / "participant_folds.csv", index=False)
    plan = {
        "frozen_before_fit_at_utc": now(), "experiment": "improvement_002", "seed": SEED,
        "scope": "Synthetic train-only grouped CV selection, followed by a single comparison on reused development validation",
        "target": target, "predictors": features,
        "train_sha256": sha256(training_path), "task_config_sha256": sha256(config_path),
        "script_sha256": sha256(__file__), "participant_folds_sha256": sha256(output / "participant_folds.csv"),
        "candidates": SPECS, "n_folds": 3,
        "fold_policy": "Shuffle training participant IDs with seed; allocate round-robin to three held-out folds; all days of a participant stay together",
        "selection": "Highest mean grouped-CV macro F1 rounded to 6 decimals; tie chooses lower prespecified complexity_rank",
        "secondary_metric": "High-category recall, descriptive only and not a selection tiebreaker",
        "preprocessing": "Fit imputer and (for logistic regression) scaler separately on each fold's fitting participants only",
        "validation_policy": "Read existing validation.csv only AFTER writing CV winner selection; no validation-based retuning or reselection",
        "test_policy": "Never read test.csv; original frozen model, scripts and reports remain untouched",
        "candidate_promotion": "None; winner may be a baseline and remains development-only",
        "future_shap_compatibility": "A logistic winner would require a linear explainer; existing deployed TreeSHAP service remains unchanged",
        "ordinal_regression_not_selected": "Thresholding a conditional mean at 4/7 may suppress rare high outcomes; use balanced logistic as a regularized comparator instead",
        "bootstrap": "1000 paired participant resamples of reused validation, selected winner minus control and persistence",
    }
    write_json(output / "plan.json", plan)
    fold_predictions = train[["record_id", "participant_id"]].copy()
    fold_predictions["held_out_fold"] = train.participant_id.map(fold_map)
    fold_predictions["true_label"] = train[target]
    rows = []
    independence = []
    for spec in SPECS:
        oof = np.empty(len(train), dtype=object)
        for fold in range(3):
            fitting = train.participant_id.map(fold_map).ne(fold)
            holding = ~fitting
            fitting_ids, holding_ids = set(train.loc[fitting, "participant_id"]), set(train.loc[holding, "participant_id"])
            assert fitting_ids.isdisjoint(holding_ids)
            assert fitting_ids.union(holding_ids) == set(ids)
            assert len(holding_ids) == 28 and len(fitting_ids) == 56
            model = make_model(spec)
            before = time.perf_counter()
            model.fit(train.loc[fitting, features], train.loc[fitting, target])
            prediction = model.predict(train.loc[holding, features])
            elapsed = time.perf_counter()-before
            oof[holding.to_numpy()] = prediction
            metrics = measure(train.loc[holding, target], prediction)
            rows.append({"candidate": spec["name"], "fold": fold, "fit_predict_seconds": elapsed,
                         "macro_f1": metrics["macro_f1"], "high_recall": metrics["high_recall"],
                         "accuracy": metrics["accuracy"], "fit_participants": len(fitting_ids),
                         "held_out_participants": len(holding_ids), "held_out_rows": int(holding.sum())})
            if spec == SPECS[0]:
                independence.append({"fold": fold, "fitting_participants": sorted(fitting_ids),
                                     "holding_participants": sorted(holding_ids), "overlap_count": 0})
        assert all(value is not None for value in oof)
        fold_predictions[spec["name"]] = oof
        print(spec["name"], "OOF macroF1", round(measure(train[target], oof)["macro_f1"], 4), flush=True)
    cv = pd.DataFrame(rows)
    cv.to_csv(output / "cv_fold_metrics.csv", index=False)
    fold_predictions.to_csv(output / "fold_predictions.csv", index=False)
    aggregate = cv.groupby("candidate").agg(mean_cv_macro_f1=("macro_f1", "mean"),
        std_cv_macro_f1=("macro_f1", "std"), mean_cv_high_recall=("high_recall", "mean"),
        mean_cv_accuracy=("accuracy", "mean"), total_fit_predict_seconds=("fit_predict_seconds", "sum")).reset_index()
    ranks = {s["name"]: s["complexity_rank"] for s in SPECS}
    aggregate["complexity_rank"] = aggregate.candidate.map(ranks)
    aggregate["selection_f1_rounded_6dp"] = aggregate.mean_cv_macro_f1.round(6)
    aggregate = aggregate.sort_values(["selection_f1_rounded_6dp", "complexity_rank"], ascending=[False, True])
    aggregate.to_csv(output / "cv_comparison.csv", index=False)
    winner = aggregate.iloc[0].candidate
    selection = {"selected_at_utc": now(), "selected_candidate": winner,
                 "selected_using": "training-participant grouped CV only",
                 "validation_loaded_at_selection": False,
                 "selection_rule": plan["selection"],
                 "selected_candidate_is_baseline": winner in {PERSISTENCE, "majority_class"},
                 "fold_independence": independence,
                 "cv_comparison_sha256": sha256(output / "cv_comparison.csv")}
    write_json(output / "cv_selection.json", selection)

    wanted = list(dict.fromkeys([winner, CONTROL, PERSISTENCE]))
    fitted = {}
    for name in wanted:
        spec = next(s for s in SPECS if s["name"] == name)
        fitted[name] = make_model(spec).fit(train[features], train[target])
    joblib.dump({"scope": "development-only; not deployed", "selected_candidate": winner,
                 "models": fitted, "feature_columns": features, "target": target,
                 "selection": selection, "plan_sha256": sha256(output / "plan.json")},
                output / "development_bundle.joblib", compress=3)

    # The first read of development validation occurs strictly after selection.
    validation = pd.read_csv(root / "data/validation.csv")
    assert validation.split.eq("validation").all()
    assert set(train.participant_id).isdisjoint(validation.participant_id)
    prediction_table = validation[["record_id", "participant_id"]].copy()
    prediction_table["true_label"] = validation[target]
    measured, predictions = {}, {}
    for name, model in fitted.items():
        prediction = np.asarray(model.predict(validation[features]))
        predictions[name] = prediction
        prediction_table[name] = prediction
        measured[name] = measure(validation[target], prediction)
    prediction_table.to_csv(output / "validation_predictions.csv", index=False)
    bootstrap_frame = validation[["participant_id"]].copy()
    bootstrap_frame["_true_label"] = validation[target]
    uncertainty = {name: paired_bootstrap(bootstrap_frame, predictions, winner, name)
                   for name in [CONTROL, PERSISTENCE]}
    validation_rows = [{"candidate": name, "scope": "reused_synthetic_development_validation",
                        **{k: values[k] for k in ["macro_f1", "high_recall", "high_precision", "accuracy"]}}
                       for name, values in measured.items()]
    pd.DataFrame(validation_rows).to_csv(output / "validation_comparison.csv", index=False)
    summary = {"experiment": "improvement_002", "completed_at_utc": now(),
               "elapsed_seconds": time.perf_counter()-start, "selected_candidate": winner,
               "candidate_is_baseline": selection["selected_candidate_is_baseline"],
               "scope": "Synthetic development experiment; existing validation reused; no fresh test or scientific improvement claim",
               "cv_results": aggregate.to_dict("records"), "validation_metrics": measured,
               "paired_participant_bootstrap": uncertainty,
               "validation_sha256": sha256(root / "data/validation.csv"),
               "test_read": False, "deployed_model_changed": False, "clinical_validation": False,
               "promotion": "None; fitted artifact is development-only",
               "shap_compatibility": "If logistic wins, future promotion needs linear SHAP support; current TreeSHAP service unchanged"}
    write_json(output / "summary.json", summary)
    lines = ["ASTRA-SHIELD — BOUNDED DEVELOPMENT IMPROVEMENT EXPERIMENT 002", "",
        "All observations are from the original longitudinal SYNTHETIC dataset.",
        "Candidate definitions, group folds and the selection tie rule were frozen",
        "in plan.json before fitting. Eight fixed candidates were compared using",
        "three participant-disjoint CV folds inside the training partition only.",
        "Imputation/scaling were fitted independently within fitting folds.", "",
        f"CV-selected candidate: {winner}.",
        "Selection used mean CV macro F1 rounded to six decimals; exact rounded",
        "ties preferred lower prespecified complexity rank. High recall is also",
        "reported but was not a secondary tuning objective.", "",
        "The existing validation partition was opened only after cv_selection.json",
        "was written. It is REUSED DEVELOPMENT VALIDATION, not a fresh independent",
        "test. No retuning or reselection followed these validation results.", ""]
    for name, metric in measured.items():
        lines.append(f"{name}: reused-validation macro F1={metric['macro_f1']:.4f}; high recall={metric['high_recall']:.4f}.")
    for name, stats in uncertainty.items():
        lines.append(f"Selected minus {name}: macro F1 difference={stats['macro_f1_difference_selected_minus_comparison']:.4f}; paired participant bootstrap percentile 95% interval={stats['macro_f1_difference_percentile_95ci']}.")
    lines.extend(["", "The selected candidate is not automatically promoted. The existing saved",
        "model, serving worker, scripts, frozen reports, and test partition were",
        "left unchanged. A baseline can legitimately win this experiment.",
        "If a logistic candidate is promoted later, explanation support must use",
        "a suitable linear SHAP explainer rather than the current tree explainer.",
        "Any observed gain describes this simulator and reused development cohort,",
        "not improved medical validity or demonstrated astronaut safety.", "",
        "Reproduce in a new experiment directory only after defining another plan;",
        "this script refuses to overwrite an existing frozen experiment."])
    (output / "RESULTS.txt").write_text("\n".join(lines)+"\n")
    print(json.dumps({"selected_candidate": winner, "elapsed_seconds": summary["elapsed_seconds"],
                      "validation_macro_f1": {n:m["macro_f1"] for n,m in measured.items()},
                      "test_read": False, "deployed_model_changed": False}, indent=2))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path)
    args = parser.parse_args()
    main(args.project_dir)
