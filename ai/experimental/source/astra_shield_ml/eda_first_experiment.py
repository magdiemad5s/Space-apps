"""Run a prespecified EDA-first development experiment without opening test data.

This revision cannot create a fresh holdout from the already-used old test set.
Its candidate comparison is development evidence on existing validation people.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

import joblib
import numpy as np
import pandas as pd

from .features import FEATURE_COLUMNS
from .training import PRIMARY, baseline_models, candidate_models, classification_metrics

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / "experiments/eda_first_001"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def main():
    destination = EXPERIMENT
    destination.mkdir(parents=True, exist_ok=True)
    if (destination / "RESULTS.json").exists():
        raise RuntimeError("This development experiment is already complete; preserve its decisions and results.")
    decision_file = destination / "FEATURE_DECISIONS.json"
    graph_review = destination / "EDA_GRAPH_REVIEW.txt"
    if not decision_file.exists() or not graph_review.exists():
        raise RuntimeError("Review EDA graphs and write feature decisions before model training.")
    decisions = json.loads(decision_file.read_text())
    sets = decisions["feature_sets"]
    assert sets["full_26"] == FEATURE_COLUMNS
    assert decisions["selection_metric"] == "macro_f1"
    for name, features in sets.items():
        assert len(features) == len(set(features)) and set(features).issubset(FEATURE_COLUMNS)
        assert "self_report_fatigue_score" in features
        assert not any(column.startswith("target_") for column in features)
    train_path = ROOT / "data/train.csv"
    validation_path = ROOT / "data/validation.csv"
    train = pd.read_csv(train_path)
    validation = pd.read_csv(validation_path)
    assert train.split.eq("train").all() and validation.split.eq("validation").all()
    assert set(train.participant_id).isdisjoint(validation.participant_id)
    assert not train.isna().any().any() and not validation.isna().any().any()
    assert train.is_synthetic.eq(1).all() and validation.is_synthetic.eq(1).all()
    target = "target_next_day_fatigue_class"
    prototype_models = candidate_models(PRIMARY)
    plan = {
        "stage": "frozen_before_fit", "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "data_origin": "original_longitudinal_synthetic_dataset",
        "observation_files_permitted": ["data/train.csv", "data/validation.csv"],
        "test_policy": "No test file is opened, scored or selected on. The original test was already evaluated in the historical baseline experiment.",
        "feature_decisions_sha256": digest(decision_file),
        "graph_review_sha256": digest(graph_review),
        "eda_summary_sha256": digest(ROOT / "reports/eda/data_quality_summary.json"),
        "train_sha256": digest(train_path), "validation_sha256": digest(validation_path),
        "target": target, "selection_metric": "validation macro_f1",
        "tie_break": "If exactly tied, choose fewer model input columns, then lexical candidate name",
        "prespecified_feature_sets": sets,
        "prespecified_algorithms": {name: str(model) for name, model in prototype_models.items()},
        "sampling": "Existing participant partitions unchanged; class weights learned using training only; no row oversampling",
        "scope": "Development comparison, not a new independent test or a scientific claim of improved human forecasting",
    }
    plan_path = destination / "FROZEN_BEFORE_TRAINING.json"
    if plan_path.exists():
        raise RuntimeError("A frozen plan already exists; inspect any interrupted run rather than silently rewriting it.")
    write_json(plan_path, plan)
    start = time.perf_counter()
    rows, fitted = [], {}
    predictions = validation[["record_id", "participant_id", target]].copy()
    for name, estimator in baseline_models(PRIMARY).items():
        estimator.fit(train[FEATURE_COLUMNS], train[target])
        prediction = estimator.predict(validation[FEATURE_COLUMNS])
        metrics = classification_metrics(validation[target], prediction)
        rows.append({"candidate": name, "feature_set": "baseline", "predictor_count": 26,
                     "validation_metrics": metrics, "fit_seconds": None})
        predictions[name] = prediction
    for set_name, predictors in sets.items():
        for algorithm, estimator in candidate_models(PRIMARY).items():
            name = set_name + "__" + algorithm
            before = time.perf_counter()
            estimator.fit(train[predictors], train[target])
            elapsed = time.perf_counter() - before
            prediction = estimator.predict(validation[predictors])
            metrics = classification_metrics(validation[target], prediction)
            fitted[name] = estimator
            rows.append({"candidate": name, "algorithm": algorithm, "feature_set": set_name,
                         "predictor_count": len(predictors), "predictors": predictors,
                         "validation_metrics": metrics, "fit_seconds": elapsed})
            predictions[name] = prediction
            print(f"{name}: validation Macro-F1={metrics['macro_f1']:.4f}; fit={elapsed:.2f}s", flush=True)
    competitors = [row for row in rows if row["feature_set"] != "baseline"]
    winner = sorted(competitors, key=lambda row: (-row["validation_metrics"]["macro_f1"], row["predictor_count"], row["candidate"]))[0]
    bundle = {
        "experiment": "eda_first_001", "scope": "development_only_no_fresh_test_evaluation",
        "target": target, "selected_candidate": winner["candidate"],
        "selected_predictors": winner["predictors"], "models": fitted,
        "selection": winner, "frozen_plan_sha256": digest(plan_path),
        "data_origin": "synthetic", "clinical_validation": False,
    }
    joblib.dump(bundle, destination / "development_models.joblib", compress=3)
    result = {
        "experiment": "eda_first_001", "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "sequence": ["training-only EDA", "visual graph review", "feature decisions", "frozen recipe", "training-only fit", "validation comparison"],
        "frozen_plan_sha256": digest(plan_path), "fit_started_after_plan": True,
        "train_rows": len(train), "validation_rows": len(validation),
        "train_participants": train.participant_id.nunique(), "validation_participants": validation.participant_id.nunique(),
        "test_accessed": False, "test_score": None,
        "historical_test_policy": "Old test report retained as historical evidence; not a new test for this revision",
        "selected_candidate": winner["candidate"], "selected_predictors": winner["predictors"],
        "selected_validation_macro_f1": winner["validation_metrics"]["macro_f1"],
        "results": rows, "training_and_comparison_seconds": time.perf_counter()-start,
        "model_sha256": digest(destination / "development_models.joblib"),
        "current_api_bundle_modified": False,
        "clinical_validation": False,
    }
    assert digest(decision_file) == plan["feature_decisions_sha256"]
    assert digest(graph_review) == plan["graph_review_sha256"]
    write_json(destination / "RESULTS.json", result)
    pd.DataFrame([{"candidate": row["candidate"], "feature_set": row["feature_set"],
                   "predictor_count": row["predictor_count"],
                   "validation_macro_f1": row["validation_metrics"]["macro_f1"],
                   "validation_high_recall": row["validation_metrics"]["classification_report"]["high"]["recall"],
                   "fit_seconds": row["fit_seconds"]} for row in rows]).to_csv(destination / "model_comparison.csv", index=False)
    predictions.to_csv(destination / "validation_predictions.csv", index=False)
    print(json.dumps({"selected_candidate": winner["candidate"], "validation_macro_f1": winner["validation_metrics"]["macro_f1"],
                      "test_accessed": False, "current_api_bundle_modified": False}, indent=2))


if __name__ == "__main__":
    main()
