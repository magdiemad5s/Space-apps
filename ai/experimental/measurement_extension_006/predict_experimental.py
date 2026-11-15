#!/usr/bin/env python3
"""Isolated inference for the frozen measurement-extension experiment.

This helper is not imported by the live API and never changes its bundle. It
loads only this experiment's trusted training/candidate_models.joblib, whose
frozen SHA-256 is checked before deserialization. Joblib/pickle can execute code:
never substitute an untrusted artifact or expose artifact upload to end users.

Examples, from this experiment directory in an environment with ai/requirements:
    python predict_experimental.py --demo
    python predict_experimental.py --check
    python predict_experimental.py --input feature_values.json

The default artifact and report paths are relative to this file. This script has
no training, model-selection, validation-partition, or test-partition code.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import json
import math
from numbers import Integral, Real
from pathlib import Path
import sys
from typing import Any

EXPERIMENT_ROOT = Path(__file__).resolve().parent
AI_ROOT = EXPERIMENT_ROOT.parents[1]
for candidate in (AI_ROOT, AI_ROOT / "src"):
    if candidate.is_dir() and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import joblib
import numpy as np
import pandas as pd
import shap
from sklearn.ensemble import RandomForestClassifier

ORDINAL_RANGES = {
    "kss_like_sleepiness_score": (1, 9),
    "samn_perelli_like_fatigue_score": (1, 7),
}
UNITS = {
    "sleep_duration_hours": "hours",
    "sleep_efficiency_pct": "percent",
    "sleep_onset_delay_minutes": "minutes",
    "awakenings_count": "count",
    "sleep_midpoint_deviation_minutes": "signed minutes",
    "resting_heart_rate_bpm": "beats/minute",
    "hrv_rmssd_ms": "milliseconds RMSSD",
    "reaction_time_median_ms": "milliseconds",
    "reaction_time_lapses_count": "count",
    "attention_accuracy_pct": "percent",
    "self_report_stress_score": "custom simulated 0..10 score",
    "self_report_fatigue_score": "custom simulated 0..10 score",
    "self_report_mood_score": "custom simulated 0..10 score",
    "workload_hours": "hours",
    "exercise_minutes": "minutes",
    "baseline_sleep_duration_hours": "hours",
    "baseline_resting_heart_rate_bpm": "beats/minute",
    "baseline_hrv_rmssd_ms": "milliseconds RMSSD",
    "baseline_reaction_time_median_ms": "milliseconds",
    "sleep_duration_delta_from_baseline_hours": "signed hours",
    "heart_rate_delta_from_baseline_bpm": "signed beats/minute",
    "hrv_delta_from_baseline_ms": "signed milliseconds RMSSD",
    "reaction_time_change_from_baseline_pct": "signed percent",
    "prior_3day_mean_sleep_hours": "hours",
    "prior_3day_mean_resting_heart_rate_bpm": "beats/minute",
    "prior_3day_mean_reaction_time_ms": "milliseconds",
    "kss_like_sleepiness_score": "synthetic KSS-like ordinal integer 1..9",
    "samn_perelli_like_fatigue_score": "synthetic Samn-Perelli-like ordinal integer 1..7",
    "main_sleep_waso_minutes": "minutes",
    "time_since_last_sleep_hours": "hours",
    "nap_sleep_minutes_last_24h": "minutes",
    "total_sleep_last_24h_hours": "hours",
    "prior_3day_sleep_shortfall_hours": "hours",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ExperimentalPredictor:
    """One cached frozen RF plus one genuine TreeSHAP explainer."""

    def __init__(self):
        artifact = EXPERIMENT_ROOT / "training" / "candidate_models.joblib"
        frozen_path = EXPERIMENT_ROOT / "training" / "SELECTION_FROZEN.json"
        if not artifact.is_file() or not frozen_path.is_file():
            raise RuntimeError("The experiment's trained and frozen artifacts are not ready.")
        frozen = json.loads(frozen_path.read_text())
        expected = frozen["training_artifact_sha256"]["candidate_models.joblib"]
        if sha256(artifact) != expected:
            raise RuntimeError("The experimental candidate artifact differs from its frozen SHA-256.")
        bundle = joblib.load(artifact)  # Trusted, hash-identified project artifact only.
        self.selected_model = bundle["selection"]["selected_rf_extension"]
        if self.selected_model != frozen["selected_rf_extension"]:
            raise RuntimeError("The selected experimental RF differs from the frozen selection.")
        self.model = bundle["models"][self.selected_model]
        self.features = list(bundle["candidate_specs"][self.selected_model]["features"])
        self.target = str(bundle["target"])
        if len(set(self.features)) != len(self.features):
            raise RuntimeError("The frozen feature allowlist contains duplicates.")
        if any(name.startswith("target_") or "latent" in name.lower()
               or name in {"participant_id", "record_id", "split", "mission_day"}
               or "timestamp" in name.lower() for name in self.features):
            raise RuntimeError("The frozen feature allowlist contains forbidden target or metadata fields.")
        if any(name not in UNITS for name in self.features):
            raise RuntimeError("A frozen feature is missing an explicit measurement unit.")
        native = self.model.named_steps.get("model")
        if not isinstance(native, RandomForestClassifier):
            raise RuntimeError("This helper accepts only the experiment's selected fitted Random Forest.")
        self.classes = [str(label) for label in self.model.classes_]
        if set(self.classes) != {"low", "moderate", "high"}:
            raise RuntimeError("Unexpected synthetic fatigue categories in frozen classifier.")
        self.explainer = shap.TreeExplainer(native)
        if self.explainer.model.tree_output != "probability":
            raise RuntimeError("Expected probability-space Random Forest TreeSHAP contributions.")
        self.artifact_sha256 = expected

    def prepare(self, features: dict[str, Any]) -> pd.DataFrame:
        if not isinstance(features, dict):
            raise ValueError("features must be a JSON object containing exactly the frozen input allowlist")
        if any(not isinstance(name, str) for name in features):
            raise ValueError("Every input field name must be a string")
        missing = set(self.features) - set(features)
        unknown = set(features) - set(self.features)
        if missing:
            raise ValueError("Missing feature values: " + ", ".join(sorted(missing)))
        if unknown:
            raise ValueError("Unknown/forbidden fields (no labels, identifiers or latents): " + ", ".join(sorted(unknown)))
        ordered = {}
        for name in self.features:
            value = features[name]
            if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
                raise ValueError(f"{name} must be numeric, not null, text or boolean")
            if not math.isfinite(float(value)):
                raise ValueError(f"{name} must be finite")
            if name in ORDINAL_RANGES:
                low, high = ORDINAL_RANGES[name]
                if not isinstance(value, Integral) or not low <= int(value) <= high:
                    raise ValueError(f"{name} must be an integer from {low} to {high}; no fractional or floating-point ordinal inputs")
                ordered[name] = int(value)
            else:
                ordered[name] = float(value)
        return pd.DataFrame([ordered], columns=self.features)

    def predict(self, features: dict[str, Any]) -> dict[str, Any]:
        frame = self.prepare(features)
        label = str(self.model.predict(frame)[0])
        probabilities = {name: float(value) for name, value in zip(self.classes, self.model.predict_proba(frame)[0])}
        transformed = self.model[:-1].transform(frame)
        explanation = self.explainer(transformed, check_additivity=True)
        values = np.asarray(explanation.values)
        bases = np.asarray(explanation.base_values)
        class_index = self.classes.index(label)
        if values.shape != (1, len(self.features), len(self.classes)):
            raise RuntimeError("Unexpected SHAP dimensions for the selected multiclass RF")
        contributions = values[0, :, class_index]
        base_value = float(bases[0, class_index])
        reconstructed = base_value + float(np.sum(contributions))
        if not np.isfinite(contributions).all() or not math.isclose(reconstructed, probabilities[label], abs_tol=1e-7):
            raise RuntimeError("TreeSHAP additivity did not match the selected-class prediction")
        annotated = []
        for name, value, contribution in zip(self.features, frame.iloc[0], contributions):
            contribution = float(contribution)
            annotated.append({
                "feature": name,
                "value": int(value) if name in ORDINAL_RANGES else float(value),
                "feature_unit": UNITS[name],
                "shap_value": contribution,
                "shap_unit": "change in predicted-class model probability",
                "direction": "supports_prediction" if contribution > 0 else ("opposes_prediction" if contribution < 0 else "neutral"),
            })
        # Prefer positive reasons for the chosen label, and use largest opposing
        # effects only if fewer than three features contribute positively.
        positives = sorted((row for row in annotated if row["shap_value"] > 0), key=lambda row: row["shap_value"], reverse=True)
        others = sorted((row for row in annotated if row["shap_value"] <= 0), key=lambda row: abs(row["shap_value"]), reverse=True)
        reasons = (positives + others)[:3]
        for row in reasons:
            row["reason"] = f"{row['feature']} {'supported' if row['shap_value'] > 0 else 'opposed'} the model's predicted {label} category relative to its SHAP reference."
        return {
            "label": label,
            "points": round(50 * probabilities["moderate"] + 100 * probabilities["high"], 2),
            "points_definition": "Prototype severity index: 0*P(low)+50*P(moderate)+100*P(high); not a medical probability or a validated score.",
            "reasons": reasons,
            "model_class_probabilities": probabilities,
            "probability_scope": "Uncalibrated model scores for a synthetic outcome; not medical risk probabilities.",
            "experimental": True,
            "clinical_validation": False,
            "data_origin": "fresh synthetic measurement-extension cohort",
            "forecast_horizon_days": 1,
            "forecast_horizon_hours": 24,
            "selected_model": self.selected_model,
            "target": self.target,
            "input_feature_count": len(self.features),
            "explanation_type": "TreeSHAP, selected-class probability space, tree-path-dependent reference",
            "shap": {"explained_class": label, "base_value": base_value,
                     "sum_feature_contributions": float(np.sum(contributions)),
                     "reconstructed_model_probability": reconstructed,
                     "all_feature_contributions": annotated},
            "artifact_sha256": self.artifact_sha256,
            "limitations": [
                "This helper is experimental and is not connected to the live backend or API.",
                "Both questionnaire-range fields are simulated KSS-like/Samn-Perelli-like measurements, not validated instrument administrations.",
                "TreeSHAP explains this fitted classifier; its reasons are not causes of fatigue or medical findings.",
                "No alert engine, clinical thresholds, intervention or mission decision is implemented here.",
            ],
        }


@lru_cache(maxsize=1)
def _predictor() -> ExperimentalPredictor:
    return ExperimentalPredictor()


def predict(features: dict[str, Any]) -> dict[str, Any]:
    """One prediction from exactly the frozen selected model's input fields."""
    return _predictor().predict(features)


def _training_example(predictor: ExperimentalPredictor) -> tuple[dict[str, Any], dict[str, Any]]:
    # Read TRAIN only and never select using its target or predicted class.
    train_path = EXPERIMENT_ROOT / "data" / "train.csv"
    frame = pd.read_csv(train_path, usecols=predictor.features + ["record_id"])
    complete = frame.dropna(subset=predictor.features)
    if complete.empty:
        raise RuntimeError("No complete training row is available for a strict-input inference demonstration")
    row = complete.iloc[0]
    features = {name: int(row[name]) if name in ORDINAL_RANGES else float(row[name]) for name in predictor.features}
    return features, {"partition": "train", "record_id": str(row["record_id"]),
                      "row_selection": "first complete training row, independent of target/prediction",
                      "source_file": "data/train.csv"}


def _write(path: Path, content: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(content, indent=2, allow_nan=False) + "\n")


def smoke_checks(output_dir: Path | None = None) -> dict[str, Any]:
    predictor = _predictor()
    features, source = _training_example(predictor)
    result = predictor.predict(features)
    frame = predictor.prepare(features)
    direct_label = str(predictor.model.predict(frame)[0])
    direct_probabilities = predictor.model.predict_proba(frame)[0]
    checks = []
    def check(name: str, passed: bool):
        if not passed:
            raise AssertionError(name)
        checks.append(name)
    check("feature-only frame has exact frozen order", list(frame.columns) == predictor.features)
    check("selected RF matches frozen selection", result["selected_model"] == predictor.selected_model)
    check("helper label equals direct model prediction", result["label"] == direct_label)
    check("helper probabilities equal direct prediction", bool(np.allclose([result["model_class_probabilities"][name] for name in predictor.classes], direct_probabilities, atol=1e-12)))
    check("model probabilities sum to one", math.isclose(sum(result["model_class_probabilities"].values()), 1, abs_tol=1e-10))
    check("severity points follow documented formula", result["points"] == round(50*result["model_class_probabilities"]["moderate"] + 100*result["model_class_probabilities"]["high"], 2))
    check("all selected features have actual SHAP values", len(result["shap"]["all_feature_contributions"]) == len(predictor.features))
    check("SHAP additivity equals predicted class probability", math.isclose(result["shap"]["reconstructed_model_probability"], result["model_class_probabilities"][result["label"]], abs_tol=1e-7))
    check("top three reasons have feature units", len(result["reasons"]) == 3 and all(row["feature_unit"] and row["shap_unit"] for row in result["reasons"]))
    check("one-day horizon is distinct from a clinical claim", result["forecast_horizon_days"] == 1 and result["experimental"] and not result["clinical_validation"])
    invalid = []
    first = predictor.features[0]
    missing = dict(features); missing.pop(first)
    invalid.append(("missing required feature", missing))
    for key in ("target_next_day_fatigue_class", "participant_id", "record_id", "split", "latent_fatigue"):
        invalid.append(("forbidden " + key, {**features, key: "high"}))
    for label, value in (("boolean", True), ("NaN", float("nan")), ("positive infinity", float("inf")), ("negative infinity", -float("inf")), ("numeric string", "7.5"), ("null", None)):
        invalid.append((label + " numerical input", {**features, first: value}))
    for name, (low, high) in ORDINAL_RANGES.items():
        if name not in features:
            continue
        for label, value in (("below range", low-1), ("above range", high+1), ("fractional", low+0.5), ("boolean", True), ("floating-point ordinal", float(low)), ("null", None)):
            invalid.append((name + " " + label, {**features, name: value}))
    for name, bad in invalid:
        try:
            predictor.prepare(bad)
        except ValueError:
            check("reject " + name, True)
        else:
            check("reject " + name, False)
    demo = {"demo_source": source, "features": features, "prediction": result}
    report = {"status": "passed", "checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "selected_model": predictor.selected_model, "feature_count": len(predictor.features),
              "artifact_sha256": predictor.artifact_sha256, "checks_passed": len(checks),
              "source_partition": "train", "validation_or_test_read": False,
              "training_or_reselection_performed": False, "live_backend_changed": False,
              "checks": checks}
    if output_dir is not None:
        _write(output_dir / "inference_demo.json", demo)
        _write(output_dir / "inference_checks.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--input", type=Path, help="JSON object containing exactly the selected-model feature allowlist")
    group.add_argument("--demo", action="store_true", help="Predict first complete TRAIN row; print without changing archived reports")
    group.add_argument("--check", action="store_true", help="Run strict-input and SHAP smoke checks using TRAIN only; print results")
    group.add_argument("--list-features", action="store_true", help="List exact frozen inputs with units")
    parser.add_argument("--output-dir", type=Path, help="Optional NEW directory for demo/check reports; existing directories are refused")
    args = parser.parse_args()
    if args.output_dir is not None:
        if not (args.demo or args.check):
            parser.error("--output-dir is available only with --demo or --check")
        args.output_dir.mkdir(parents=True, exist_ok=False)
    if args.check:
        output = smoke_checks(args.output_dir)
    elif args.list_features:
        predictor = _predictor()
        output = {"selected_model": predictor.selected_model, "inputs": [{"name": name, "unit": UNITS[name]} for name in predictor.features]}
    elif args.demo:
        predictor = _predictor()
        features, source = _training_example(predictor)
        output = {"demo_source": source, "features": features, "prediction": predictor.predict(features)}
        if args.output_dir is not None:
            _write(args.output_dir / "inference_demo.json", output)
    else:
        features = json.loads(args.input.read_text())
        output = predict(features)
    print(json.dumps(output, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
