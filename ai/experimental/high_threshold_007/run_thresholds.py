#!/usr/bin/env python3
"""Validation-only threshold sensitivity. No fit, calibration, test scoring or promotion."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from numbers import Real
from pathlib import Path
import platform
import sys
import time

import numpy as np
import pandas as pd
from sklearn.metrics import (accuracy_score, average_precision_score, balanced_accuracy_score,
                             classification_report, confusion_matrix, f1_score, precision_recall_curve)

HERE = Path(__file__).resolve().parent
AI = HERE.parents[1]
LABELS = ["low", "moderate", "high"]
EXPECTED_PLAN_SHA256 = "5399aa38486c4e6e62be78613486182a97a5791fcd9eaafa346209a7cc26a6cb"
if str(AI) not in sys.path:
    sys.path.insert(0, str(AI))


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def jsonable(value):
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [jsonable(v) for v in value]
    if isinstance(value, np.generic):
        return jsonable(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8") as handle:
        json.dump(jsonable(value), handle, indent=2, allow_nan=False)
        handle.write("\n")


def validate_probabilities(probabilities, classes):
    labels = list(classes)
    if len(labels) != 3 or set(labels) != set(LABELS):
        raise ValueError("Exactly one probability column for each of low, moderate and high is required.")
    values = np.asarray(probabilities)
    if values.ndim != 2 or values.shape[1] != 3 or values.shape[0] == 0:
        raise ValueError("Probabilities must have shape (nonempty rows, 3).")
    if not np.issubdtype(values.dtype, np.number) or np.issubdtype(values.dtype, np.bool_):
        raise ValueError("Probabilities must be numeric.")
    values = values.astype(float)
    if not np.isfinite(values).all() or (values < 0).any() or (values > 1).any():
        raise ValueError("Probabilities must be finite and within [0,1].")
    if not np.allclose(values.sum(axis=1), 1., atol=1e-9, rtol=0):
        raise ValueError("Each probability row must sum to one.")
    return values, labels


def baseline_predictions(probabilities, classes):
    """Original multiclass argmax, preserving estimator class order for ties."""
    values, labels = validate_probabilities(probabilities, classes)
    return np.asarray(labels)[values.argmax(axis=1)]


def predict_threshold(probabilities, classes, threshold):
    """High iff P_high >= t; otherwise compare Low/Moderate, ties to Low."""
    if isinstance(threshold, (bool, np.bool_)) or not isinstance(threshold, Real) or not np.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError("Threshold must be a finite number within [0,1].")
    values, labels = validate_probabilities(probabilities, classes)
    high, low, moderate = [labels.index(label) for label in ["high", "low", "moderate"]]
    fallback = np.where(values[:, low] >= values[:, moderate], "low", "moderate")
    return np.where(values[:, high] >= threshold, "high", fallback)


def classification_summary(y, pred, baseline=None):
    truth, predicted = np.asarray(y), np.asarray(pred)
    if truth.ndim != 1 or predicted.shape != truth.shape or not len(truth):
        raise ValueError("Truth and predictions must be nonempty, aligned 1D arrays.")
    if not set(truth).issubset(LABELS) or not set(predicted).issubset(LABELS):
        raise ValueError("Unexpected target or prediction class.")
    real_high, predicted_high = truth == "high", predicted == "high"
    tp = int((real_high & predicted_high).sum())
    fn = int((real_high & ~predicted_high).sum())
    fp = int((~real_high & predicted_high).sum())
    tn = int((~real_high & ~predicted_high).sum())
    report = classification_report(truth, predicted, labels=LABELS, output_dict=True, zero_division=0)
    summary = {
        "rows": len(truth), "high_support": tp+fn, "non_high_support": fp+tn,
        "high_tp": tp, "high_fn": fn, "high_fp": fp, "high_tn": tn,
        "high_recall": tp/(tp+fn) if tp+fn else None,
        "high_precision": tp/(tp+fp) if tp+fp else None,
        "high_f1": 2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0.,
        "macro_f1": float(f1_score(truth, predicted, labels=LABELS, average="macro", zero_division=0)),
        "accuracy": float(accuracy_score(truth, predicted)),
        "balanced_accuracy": float(balanced_accuracy_score(truth, predicted)),
        "high_false_positive_rate": fp/(fp+tn) if fp+tn else None,
        "high_false_alarms_per_100_assessments": 100*fp/len(truth),
        "high_prediction_count": tp+fp,
        "high_predictions_per_100_assessments": 100*(tp+fp)/len(truth),
        "classification_report": report,
        "confusion_matrix_labels": LABELS,
        "confusion_matrix": confusion_matrix(truth, predicted, labels=LABELS).tolist(),
    }
    if baseline is not None:
        reference = np.asarray(baseline)
        if reference.shape != truth.shape or not set(reference).issubset(LABELS):
            raise ValueError("Baseline must align with truth and use the expected classes.")
        was_high = reference == "high"
        promoted = ~was_high & predicted_high
        demoted = was_high & ~predicted_high
        summary.update({
            "high_promotions": int(promoted.sum()), "high_demotions": int(demoted.sum()),
            "additional_high_cases_detected": int((promoted & real_high).sum()),
            "additional_false_high_flags": int((promoted & ~real_high).sum()),
            "previous_high_cases_lost": int((demoted & real_high).sum()),
            "previous_false_high_flags_removed": int((demoted & ~real_high).sum()),
        })
    return summary


def flat_metrics(metrics):
    result = {key: value for key, value in metrics.items() if not isinstance(value, (list, dict))}
    for label in LABELS:
        for field in ["precision", "recall", "f1-score", "support"]:
            result[f"class_{label}_{field}"] = metrics["classification_report"][label][field]
    for i, actual in enumerate(LABELS):
        for j, predicted in enumerate(LABELS):
            result[f"cm_{actual}_as_{predicted}"] = metrics["confusion_matrix"][i][j]
    return result


def verify_plan():
    actual = sha256(HERE/"PLAN.json")
    if actual != EXPECTED_PLAN_SHA256 or (HERE/"PLAN.sha256").read_text().strip() != actual:
        raise RuntimeError("The preregistered threshold plan changed.")
    plan = read_json(HERE/"PLAN.json")
    for name, expected in plan["protected_scientific_inputs_sha256"].items():
        if sha256(AI/name) != expected:
            raise RuntimeError("Protected input hash mismatch: " + name)
    return plan


def freeze():
    plan = verify_plan()
    write_json(HERE/"RUN_FROZEN.json", {
        "frozen_at_utc": utc_now(), "plan_sha256": sha256(HERE/"PLAN.json"),
        "script_sha256": sha256(__file__), "unit_tests_sha256": sha256(HERE/"test_thresholds.py"),
        "observations_or_probability_outcomes_inspected_by_runner": False,
        "protected_inputs_sha256": plan["protected_scientific_inputs_sha256"],
        "scope": "Frozen before first threshold analysis; no fitted artifact or deployment is produced."
    })


def primary_data(plan):
    import joblib
    spec = plan["primary"]
    manifest = read_json(AI/"artifacts/frozen_manifest.json")
    assert sha256(AI/spec["model"]) == manifest["artifact_sha256"][spec["model"]]
    assert sha256(AI/spec["validation"]) == manifest["data_sha256"][spec["validation"]]
    assert sha256(AI/spec["predictors"]) == manifest["task_config_sha256"]
    bundle = joblib.load(AI/spec["model"])  # Trusted artifact, verified before deserialization.
    config = read_json(AI/spec["predictors"])
    task = config["tasks"][spec["task"]]
    assert task == bundle["task_config"]["tasks"][spec["task"]]
    features = task["predictors"]
    assert len(features) == 26 and not any(c.startswith("target_") or c in {"participant_id", "record_id", "split"} for c in features)
    frame = pd.read_csv(AI/spec["validation"], float_precision="round_trip")
    assert frame.split.eq("validation").all()
    assert frame.record_id.is_unique and not frame.duplicated(["participant_id", "mission_day"]).any()
    assert frame.is_synthetic.eq(1).all() and np.isfinite(frame[features].to_numpy()).all()
    split = pd.read_csv(AI/"data/participant_splits.csv")
    assert set(frame.participant_id) == set(split.loc[split.split.eq("validation"), "participant_id"])
    model = bundle["models"][spec["task"]]
    classes = [str(c) for c in model.classes_]
    probabilities = model.predict_proba(frame[features])
    baseline = baseline_predictions(probabilities, classes)
    assert np.array_equal(baseline, model.predict(frame[features]))
    reference = read_json(AI/spec["reference_metrics"])["tasks"][spec["task"]]["selection"]["validation_metrics"]
    keys = ["record_id", "participant_id", "mission_day", "observation_timestamp_utc", "target_timestamp_utc"]
    observations = frame[keys].copy()
    observations["true_label"] = frame[spec["target"]]
    return observations, probabilities, classes, baseline, reference, {
        "model_file": spec["model"], "model_sha256": sha256(AI/spec["model"]),
        "data_file": spec["validation"], "data_sha256": sha256(AI/spec["validation"]),
        "feature_count": len(features), "classes_in_estimator_order": classes,
        "inference_only": True, "estimator_fits": 0,
    }


def secondary_data(plan):
    spec = plan["secondary"]
    prefix = spec["prefix"]
    classes = ["high", "low", "moderate"]
    keys = ["record_id", "participant_id", "mission_day", "observation_timestamp_utc", "target_timestamp_utc", "true_label"]
    probability_names = [f"{prefix}__model_probability_{label}" for label in classes]
    frame = pd.read_csv(AI/spec["validation_predictions"], usecols=keys+probability_names+[prefix+"__prediction"], float_precision="round_trip")
    probabilities = frame[probability_names].to_numpy()
    baseline = baseline_predictions(probabilities, classes)
    assert np.array_equal(baseline, frame[prefix+"__prediction"].to_numpy())
    reference = read_json(AI/spec["reference_metrics"])["metrics"][prefix]
    return frame[keys].copy(), probabilities, classes, baseline, reference, {
        "model": prefix, "data_file": spec["validation_predictions"],
        "data_sha256": sha256(AI/spec["validation_predictions"]),
        "classes_in_stored_estimator_order": classes,
        "scope": "Uses frozen rounded-to-12-decimal validation scores, not original serving-model observations.",
        "new_model_inferences": 0, "estimator_fits": 0,
    }


def assert_reference(metrics, expected):
    assert metrics["confusion_matrix"] == expected["confusion_matrix"]
    assert metrics["confusion_matrix_labels"] == expected["confusion_matrix_labels"]
    for key in ["macro_f1", "accuracy", "balanced_accuracy"]:
        assert abs(metrics[key] - expected[key]) < 1e-12, key
    for label in LABELS:
        for key in ["precision", "recall", "f1-score", "support"]:
            assert abs(metrics["classification_report"][label][key] - expected["classification_report"][label][key]) < 1e-12


def choose_shortlist(plan, rows, baseline):
    chosen = []
    def pick(eligible, key):
        return max(eligible, key=key) if eligible else None
    for rule in plan["shortlist_rules"]:
        name = rule["name"]
        if name == "baseline_argmax":
            choice = {"threshold": None, "metrics": baseline}
        elif name == "best_high_f1_grid":
            choice = pick(rows, lambda r: (r["metrics"]["high_f1"], r["metrics"]["macro_f1"], r["threshold"]))
        elif name == "best_macro_f1_grid":
            choice = pick(rows, lambda r: (r["metrics"]["macro_f1"], r["metrics"]["high_recall"], r["threshold"]))
        elif name.startswith("recall_"):
            target = int(name.split("_")[1])/100
            eligible = [r for r in rows if r["metrics"]["high_recall"] >= target and r["metrics"]["high_precision"] is not None]
            choice = pick(eligible, lambda r: (r["metrics"]["high_precision"], r["metrics"]["macro_f1"], r["threshold"]))
        elif name == "illustrative_budget_grid":
            eligible = [r for r in rows if r["metrics"]["high_precision"] is not None
                        and r["metrics"]["high_precision"] >= baseline["high_precision"]
                        and r["metrics"]["macro_f1"] >= baseline["macro_f1"]-.02]
            choice = pick(eligible, lambda r: (r["metrics"]["high_recall"], r["metrics"]["macro_f1"], r["threshold"]))
        else:
            raise RuntimeError("Unknown preregistered shortlist rule: " + name)
        chosen.append({"candidate_name": name, "selection_criterion": rule["criterion"], "available": choice is not None,
                       **(choice or {"threshold": None, "metrics": None})})
    return chosen


def analyze(plan, which, data):
    spec = plan[which]
    observations, probabilities, classes, baseline, reference, provenance = data
    assert len(observations) == spec["expected_rows"] and observations.participant_id.nunique() == spec["expected_people"]
    assert observations.record_id.is_unique and not observations.duplicated(["participant_id", "mission_day"]).any()
    truth = observations.true_label.to_numpy()
    assert int((truth == "high").sum()) == spec["expected_high_count"]
    baseline_metrics = classification_summary(truth, baseline, baseline)
    assert_reference(baseline_metrics, reference)
    output = HERE/"results"/which
    output.mkdir()
    for label in LABELS:
        observations["probability_"+label] = probabilities[:, classes.index(label)]
    observations["baseline_prediction"] = baseline
    observations.to_csv(output/"frozenvalidationprobabilities.csv", index=False, float_format="%.17g")
    rows = []
    for threshold in plan["threshold_grid"]:
        prediction = predict_threshold(probabilities, classes, threshold)
        metrics = classification_summary(truth, prediction, baseline)
        rows.append({"threshold": threshold, "metrics": metrics})
    assert all(a["metrics"]["high_tp"] >= b["metrics"]["high_tp"] and a["metrics"]["high_fp"] >= b["metrics"]["high_fp"]
               for a, b in zip(rows, rows[1:]))
    pd.DataFrame([{"threshold": r["threshold"], **flat_metrics(r["metrics"])} for r in rows]).to_csv(output/"allthresholdmetrics.csv", index=False, float_format="%.17g")
    shortlisted = choose_shortlist(plan, rows, baseline_metrics)
    flat_shortlist = []
    cm_rows = []
    for choice in shortlisted:
        flat_shortlist.append({k: v for k, v in choice.items() if k != "metrics"} | (flat_metrics(choice["metrics"]) if choice["available"] else {}))
        if choice["available"]:
            for i, actual in enumerate(LABELS):
                for j, predicted in enumerate(LABELS):
                    cm_rows.append({"candidate_name": choice["candidate_name"], "threshold": choice["threshold"],
                                    "actual_label": actual, "predicted_label": predicted, "count": choice["metrics"]["confusion_matrix"][i][j]})
    pd.DataFrame(flat_shortlist).to_csv(output/"shortlist.csv", index=False, float_format="%.17g")
    pd.DataFrame(cm_rows).to_csv(output/"confusionmatrices.csv", index=False)
    high_truth = truth == "high"
    high_probability = probabilities[:, classes.index("high")]
    precision, recall, thresholds = precision_recall_curve(high_truth, high_probability, drop_intermediate=False)
    assert len(precision) == len(recall) == len(thresholds)+1
    pd.DataFrame({"threshold": list(thresholds)+[None], "precision": precision, "recall": recall,
                  "endpoint_without_threshold": [False]*len(thresholds)+[True]}).to_csv(output/"PRcurve.csv", index=False, float_format="%.17g")
    summary = {"experiment": plan["experiment"], "cohort": which, "name": spec["name"], "evaluated_at_utc": utc_now(),
               "rows": len(observations), "participants": observations.participant_id.nunique(),
               "participant_ids": sorted(observations.participant_id.unique()), "class_counts": {label: int((truth == label).sum()) for label in LABELS},
               "baseline": baseline_metrics, "shortlist": shortlisted,
               "high_average_precision": float(average_precision_score(high_truth, high_probability)),
               "high_prevalence": float(high_truth.mean()),
               "threshold_grid_count": len(rows), "pr_actual_threshold_count": len(thresholds),
               "pr_endpoint_note": "Last point has null threshold and precision1/recall0 solely for plotting; this is not measured precision when no High predictions occur.",
               "provenance": provenance, "baseline_matches_archived_reference": True,
               "thresholds_selected_and_evaluated_on_same_reused_validation": True,
               "interpretation": "Descriptive exploratory trade-offs, not independent validation or clinically acceptable operating points.",
               "plan_sha256": sha256(HERE/"PLAN.json"), "script_sha256": sha256(__file__),
               "fits": 0, "test_records_loaded": False, "threshold_promoted": False,
               "limitations": plan["selection_limitations"]}
    write_json(output/"summary.json", summary)
    return summary


def run():
    started = time.perf_counter()
    plan = verify_plan()
    frozen = read_json(HERE/"RUN_FROZEN.json")
    assert frozen["script_sha256"] == sha256(__file__)
    assert frozen["unit_tests_sha256"] == sha256(HERE/"test_thresholds.py")
    assert frozen["plan_sha256"] == sha256(HERE/"PLAN.json")
    (HERE/"results").mkdir(exist_ok=False)
    primary = analyze(plan, "primary", primary_data(plan))
    secondary = analyze(plan, "secondary", secondary_data(plan))
    assert set(primary["participant_ids"]).isdisjoint(secondary["participant_ids"])
    verify_plan()
    import sklearn
    write_json(HERE/"results/EXECUTION_VERIFICATION.json", {
        "status": "completed", "completed_at_utc": utc_now(), "elapsed_seconds": time.perf_counter()-started,
        "plan_sha256": sha256(HERE/"PLAN.json"), "script_sha256": sha256(__file__),
        "fits": 0, "calibration_fits": 0, "test_records_loaded": False, "test_predictions_loaded": False,
        "all_protected_scientific_inputs_unchanged": True, "baseline_metrics_match_archives": True,
        "serving_model_or_api_changed": False, "threshold_promoted": False,
        "source_cohorts_kept_separate": True,
        "environment": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__, "scikit_learn": sklearn.__version__},
        "output_files_sha256": {str(p.relative_to(HERE)): sha256(p) for p in sorted((HERE/"results").rglob("*")) if p.is_file()}
    })
    print(json.dumps({"status": "completed", "outputs": ["results/primary/summary.json", "results/secondary/summary.json"],
                      "fits": 0, "test_scoring": False, "deployment": False}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["freeze", "run"])
    argument = parser.parse_args()
    freeze() if argument.stage == "freeze" else run()
