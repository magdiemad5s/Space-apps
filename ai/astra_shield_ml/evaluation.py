"""Evaluate frozen ASTRA-SHIELD prototypes on the held-out participant partition.

This module never fits a model, selects a model, changes a threshold, or writes
model artifacts. Run it once after training/validation choices have been frozen.
All outcomes in this delivery are synthetic; metrics describe the simulator.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    precision_score,
    r2_score,
    recall_score,
    roc_auc_score,
    root_mean_squared_error,
)


LABELS = ["low", "moderate", "high"]
ANOMALY_TASK = "physiology_anomaly_detection"
TEXT_TASK = "journal_stress_classification"
CLASSIFICATION_TASKS = {"next_day_fatigue_classification", TEXT_TASK}


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _local_path(root: Path, relative_path: str) -> Path:
    path = (root / relative_path).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"Manifest path is outside project: {relative_path}")
    return path


def _json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(v) for v in value]
    if isinstance(value, np.ndarray):
        return [_json_value(v) for v in value.tolist()]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def classification_metrics(y_true: Any, y_pred: Any) -> dict[str, Any]:
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "macro_f1": float(f1_score(y_true, y_pred, labels=LABELS, average="macro", zero_division=0)),
        "classification_report": classification_report(
            y_true, y_pred, labels=LABELS, output_dict=True, zero_division=0
        ),
        "confusion_matrix_labels": LABELS,
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=LABELS).tolist(),
    }


def regression_metrics(y_true: Any, y_pred: Any) -> dict[str, Any]:
    return {
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "rmse": float(root_mean_squared_error(y_true, y_pred)),
        "r2": float(r2_score(y_true, y_pred)),
    }


def anomaly_metrics(y_true: Any, y_pred: Any, score: Any = None) -> dict[str, Any]:
    result = {
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "confusion_matrix_labels": [0, 1],
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=[0, 1]).tolist(),
        "anomaly_definition": "simulator-injected higher heart rate/lower RMSSD; not disease",
    }
    if score is not None and len(np.unique(y_true)) == 2:
        result["roc_auc"] = float(roc_auc_score(y_true, score))
        result["average_precision"] = float(average_precision_score(y_true, score))
    return result


def predict_and_measure(
    task_name: str,
    estimator: Any,
    frame: pd.DataFrame,
    task: dict[str, Any],
) -> tuple[dict[str, Any], np.ndarray, np.ndarray | None, Any]:
    predictors = task["predictors"]
    target = task.get("target", task.get("evaluation_target"))
    if not target or target not in frame:
        raise ValueError(f"Missing target for task {task_name}")
    if any(c.startswith("target_") for c in predictors):
        raise ValueError(f"Target leakage in predictor allowlist for {task_name}")
    x = frame[predictors[0]].astype(str) if task_name == TEXT_TASK else frame[predictors]
    truth = frame[target].to_numpy()
    raw_prediction = np.asarray(estimator.predict(x))
    if len(raw_prediction) != len(frame):
        raise ValueError(f"Wrong prediction count for {task_name}")
    probabilities = None
    classes = None
    if task_name == ANOMALY_TASK:
        if not set(np.unique(raw_prediction)).issubset({-1, 1}):
            raise ValueError("Anomaly detector must use sklearn +1/-1 convention")
        prediction = (raw_prediction == -1).astype(int)
        score = -np.asarray(estimator.decision_function(x)) if hasattr(estimator, "decision_function") else None
        metrics = anomaly_metrics(truth, prediction, score)
    elif task_name in CLASSIFICATION_TASKS:
        prediction = raw_prediction.astype(str)
        if not set(np.unique(prediction)).issubset(set(LABELS)):
            raise ValueError(f"Unexpected class names for {task_name}")
        metrics = classification_metrics(truth, prediction)
        if hasattr(estimator, "predict_proba"):
            probabilities = np.asarray(estimator.predict_proba(x))
            classes = [str(c) for c in estimator.classes_]
    else:
        prediction = raw_prediction.astype(float)
        if not np.isfinite(prediction).all():
            raise ValueError(f"Non-finite predictions for {task_name}")
        metrics = regression_metrics(truth, prediction)
    return metrics, prediction, probabilities, classes


def evaluate(project_dir: str | Path | None = None) -> dict[str, Any]:
    root = Path(project_dir).resolve() if project_dir else Path(__file__).resolve().parents[1]
    reports = root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    destination = reports / "test_metrics.json"
    if destination.exists():
        raise RuntimeError(
            "Held-out evaluation already exists. Do not repeatedly tune against test results; "
            "use a new untouched evaluation cohort for subsequent model development."
        )
    manifest_path = root / "artifacts" / "frozen_manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError("Freeze training/validation choices before evaluating the test partition")
    frozen = json.loads(manifest_path.read_text())
    artifact_hashes = frozen.get("artifact_sha256", {})
    bundle_key = "artifacts/bundle.joblib"
    if bundle_key not in artifact_hashes:
        raise ValueError("Frozen manifest must identify artifacts/bundle.joblib SHA-256")
    for relative_path, expected in artifact_hashes.items():
        path = _local_path(root, relative_path)
        if not path.is_file() or sha256(path) != expected:
            raise ValueError(f"Frozen artifact integrity failed: {relative_path}")
    data_hashes = frozen.get("data_sha256", {})
    if "data/test.csv" not in data_hashes:
        raise ValueError("Test partition hash must be frozen before held-out evaluation")
    for relative_path, expected in data_hashes.items():
        path = _local_path(root, relative_path)
        if not path.is_file() or sha256(path) != expected:
            raise ValueError(f"Frozen data integrity failed: {relative_path}")

    # Exclusive reservation prevents concurrent test evaluations in this run.
    lock = reports / ".test_evaluation.lock"
    descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(descriptor)
    started = time.perf_counter()
    try:
        # Load only an artifact produced locally and verified against the frozen manifest.
        bundle = joblib.load(root / bundle_key)
        frame = pd.read_csv(root / "data" / "test.csv")
        if frame.empty or frame.isna().any().any():
            raise ValueError("Test partition must contain complete observations")
        if not frame["split"].eq("test").all() or frame["record_id"].duplicated().any():
            raise ValueError("Invalid held-out partition assignment/record identifiers")
        if not frame["is_synthetic"].eq(1).all():
            raise ValueError("This artifact was built for the synthetic demonstration dataset only")
        test_participants = set(frame["participant_id"])
        for partition in ("train", "validation"):
            ids = pd.read_csv(root / "data" / f"{partition}.csv", usecols=["participant_id"])
            if test_participants.intersection(ids["participant_id"]):
                raise ValueError(f"Participant leakage between test and {partition}")

        tasks = bundle["task_config"]["tasks"]
        output = frame[["record_id", "participant_id", "observation_timestamp_utc", "target_timestamp_utc"]].copy()
        summary: dict[str, Any] = {
            "evaluation_scope": "held-out synthetic participants; simulator fidelity only",
            "clinical_validation": False,
            "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
            "model_version": bundle.get("metadata", {}).get("model_version"),
            "test_rows": len(frame),
            "test_participants": len(test_participants),
            "test_sha256": sha256(root / "data" / "test.csv"),
            "bundle_sha256": artifact_hashes[bundle_key],
            "frozen_manifest_sha256": sha256(manifest_path),
            "selection_policy": "Models and thresholds frozen using training/validation only; no fitting in evaluation",
            "tasks": {},
        }
        for name, estimator in bundle["models"].items():
            if name not in tasks:
                raise ValueError(f"Missing task configuration for {name}")
            task = tasks[name]
            target = task.get("target", task.get("evaluation_target"))
            metrics, prediction, probabilities, classes = predict_and_measure(name, estimator, frame, task)
            baseline_results = {}
            for baseline_name, baseline in bundle.get("baselines", {}).get(name, {}).items():
                baseline_results[baseline_name] = predict_and_measure(name, baseline, frame, task)[0]
            info = bundle.get("model_information", {}).get(name, {})
            summary["tasks"][name] = {
                "selected_model": info.get("selected_model", type(estimator).__name__),
                "target": target,
                "selected_metrics": metrics,
                "baseline_metrics": baseline_results,
                "validation_selected_model": True,
            }
            output[f"{name}__y_true"] = frame[target].to_numpy()
            output[f"{name}__y_pred"] = prediction
            if probabilities is not None:
                for index, label in enumerate(classes):
                    output[f"{name}__model_probability_{label}"] = probabilities[:, index]
        summary["evaluation_seconds"] = time.perf_counter() - started
        output.to_csv(reports / "test_predictions.csv", index=False, float_format="%.8f")
        temporary = reports / "test_metrics.json.tmp"
        temporary.write_text(json.dumps(_json_value(summary), indent=2, allow_nan=False) + "\n")
        temporary.replace(destination)
        return summary
    finally:
        lock.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path)
    arguments = parser.parse_args()
    result = evaluate(arguments.project_dir)
    print(json.dumps({
        "evaluation_scope": result["evaluation_scope"],
        "test_rows": result["test_rows"],
        "test_participants": result["test_participants"],
        "tasks": {
            name: {key: value for key, value in task["selected_metrics"].items() if key not in {
                "classification_report", "confusion_matrix", "confusion_matrix_labels"
            }} for name, task in result["tasks"].items()
        },
    }, indent=2))


if __name__ == "__main__":
    main()
