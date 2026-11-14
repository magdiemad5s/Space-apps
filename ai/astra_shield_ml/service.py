"""Offline inference from trusted, locally trained ASTRA-SHIELD artifacts.

The saved bundle is a Python/joblib serialization. Load only artifacts produced
by this project or another trusted source; this service never accepts uploads.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import os
import tempfile

import joblib
import numpy as np
import pandas as pd

from .features import prepare_features


DEFAULT_MODEL_PATH = Path(__file__).resolve().parent.parent / "artifacts" / "bundle.joblib"
TASK_FATIGUE = "next_day_fatigue_classification"
TASK_SCORE = "next_day_fatigue_regression"
TASK_RT = "next_day_reaction_time_regression"
TASK_ANOMALY = "physiology_anomaly_detection"
TASK_JOURNAL = "journal_stress_classification"
REQUIRED_TASKS = (TASK_FATIGUE, TASK_SCORE, TASK_RT, TASK_ANOMALY, TASK_JOURNAL)

LIMITATIONS = [
    "All models were trained on explicitly synthetic demonstration data.",
    "Outputs are not validated astronaut-health, medical-diagnostic, or operational-readiness assessments.",
    "Class probabilities are uncalibrated model outputs, not clinical risk probabilities.",
    "Current physiology and journal outputs are not next-day forecasts.",
    "Personal baselines and recent-history summaries must come from earlier observations, never future records.",
    "Journal language was generated from templates; journal predictions do not establish performance on real language.",
]

# These groups perturb measured inputs together. All derived deltas are rebuilt
# through the same feature function before obtaining another model prediction.
REFERENCE_GROUPS = {
    "sleep": ["sleep_duration_hours", "sleep_efficiency_pct", "sleep_onset_delay_minutes", "awakenings_count", "sleep_midpoint_deviation_minutes"],
    "physiology": ["resting_heart_rate_bpm", "hrv_rmssd_ms"],
    "cognitive_performance": ["reaction_time_median_ms", "reaction_time_lapses_count", "attention_accuracy_pct"],
    "self_reports": ["self_report_stress_score", "self_report_fatigue_score", "self_report_mood_score"],
    "workload_and_exercise": ["workload_hours", "exercise_minutes"],
}


class ArtifactUnavailableError(RuntimeError):
    """A missing or incompatible trusted local model bundle."""


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, np.ndarray):
        return _jsonable(value.tolist())
    if isinstance(value, np.generic):
        return _jsonable(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return None
    if isinstance(value, Path):
        return str(value)
    return value


class ModelService:
    """Loads a frozen bundle once, and makes no network or training calls."""

    def __init__(self, bundle_path: str | Path | None = None):
        self.bundle_path = Path(bundle_path) if bundle_path else DEFAULT_MODEL_PATH
        if not self.bundle_path.is_file():
            raise ArtifactUnavailableError("Model artifact not found. Run the documented training command first.")
        try:
            bundle = joblib.load(self.bundle_path)
        except Exception as exc:
            raise ArtifactUnavailableError("Could not load the trusted local model artifact.") from exc
        if not isinstance(bundle, dict) or bundle.get("format_version") != 1:
            raise ArtifactUnavailableError("Unsupported model bundle format.")
        self.bundle = bundle
        self.models = bundle.get("models", {})
        self.task_config = bundle.get("task_config", {})
        self.metadata = bundle.get("metadata", {})
        self.reference_values = bundle.get("reference_values", {})
        self.training_feature_ranges = bundle.get("training_feature_ranges", {})
        self.model_information = bundle.get("model_information", {})
        if any(task not in self.models for task in REQUIRED_TASKS):
            raise ArtifactUnavailableError("The model bundle does not contain all five configured tasks.")
        if any(task not in self.task_config.get("tasks", {}) for task in REQUIRED_TASKS):
            raise ArtifactUnavailableError("The model bundle is missing task predictor definitions.")
        # SHAP is created once per loaded frozen artifact, not fitted per request.
        # Its optional plotting imports otherwise try a read-only home cache in
        # the managed cloud workspace. Respect any caller-supplied cache paths.
        os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "astra-shield-mpl"))
        os.environ.setdefault("XDG_CACHE_HOME", str(Path(tempfile.gettempdir()) / "astra-shield-cache"))
        try:
            import shap
        except ImportError as exc:
            raise ArtifactUnavailableError("The required SHAP dependency is missing. Install this project's requirements.") from exc
        primary = self.models[TASK_FATIGUE]
        if not hasattr(primary, "named_steps") or "model" not in primary.named_steps:
            raise ArtifactUnavailableError("The selected fatigue classifier is not a supported tree pipeline for TreeSHAP.")
        native = primary.named_steps["model"]
        # RandomForest also has estimator_: an UNFITTED tree template. Only
        # unwrap the project's fitted XGBoost label-encoding wrapper.
        if hasattr(native, "estimator_") and native.estimator_.__class__.__module__.startswith("xgboost"):
            native = native.estimator_
        try:
            self.shap_explainer = shap.TreeExplainer(native)
        except Exception as exc:
            raise ArtifactUnavailableError("Could not initialize TreeSHAP for the frozen fatigue classifier.") from exc
        self.shap_output_space = (
            "class_probability" if self.shap_explainer.model.tree_output == "probability"
            else "raw_class_margin"
        )

    def model_info(self) -> dict[str, Any]:
        return _jsonable({
            "model_version": self.metadata.get("model_version", "unknown"),
            "data_origin": self.metadata.get("data_origin", "synthetic"),
            "clinical_validation": False,
            "forecast_horizon_hours": 24,
            "explanation_method": "TreeSHAP for the selected fatigue classifier",
            "points_definition": "0 * P(low) + 50 * P(moderate) + 100 * P(high); prototype severity index, not a clinical risk probability",
            "metadata": self.metadata,
            "tasks": {
                task: {"predictors": self.task_config["tasks"][task]["predictors"],
                       "target": self.task_config["tasks"][task].get("target"),
                       "evaluation_target": self.task_config["tasks"][task].get("evaluation_target"),
                       "model_information": self.model_information.get(task, {})}
                for task in REQUIRED_TASKS
            },
            "limitations": LIMITATIONS,
        })

    def _task_frame(self, features: pd.DataFrame, task: str) -> pd.DataFrame:
        return features.loc[:, self.task_config["tasks"][task]["predictors"]]

    def _class_probabilities(self, features: pd.DataFrame) -> dict[str, float]:
        model = self.models[TASK_FATIGUE]
        frame = self._task_frame(features, TASK_FATIGUE)
        values = model.predict_proba(frame)[0]
        return {str(label): float(prob) for label, prob in zip(model.classes_, values)}

    def _sensitivities(self, payload: dict[str, Any], base_high: float) -> list[dict[str, Any]]:
        """Reference substitutions, not additive SHAP values or causal effects."""
        rows = []
        for group, columns in REFERENCE_GROUPS.items():
            if any(column not in self.reference_values for column in columns):
                continue
            altered = dict(payload)
            for column in columns:
                reference = float(self.reference_values[column])
                altered[column] = int(round(reference)) if column in {"awakenings_count", "reaction_time_lapses_count"} else reference
            # A group may have an incompatible synthetic reference for the current
            # observation's time budget; omit it rather than weaken validation.
            try:
                reference_features = prepare_features(altered)
            except ValueError:
                continue
            reference_high = self._class_probabilities(reference_features).get("high", 0.0)
            change = base_high - reference_high
            rows.append({
                "group": group,
                "high_class_probability_difference": round(change, 6),
                "direction_relative_to_training_reference": "higher" if change > 1e-6 else ("lower" if change < -1e-6 else "unchanged"),
            })
        return sorted(rows, key=lambda row: abs(row["high_class_probability_difference"]), reverse=True)

    def _input_quality(self, features: pd.DataFrame) -> dict[str, Any]:
        warnings = []
        for name, bounds in self.training_feature_ranges.items():
            if name not in features or not isinstance(bounds, dict):
                continue
            value = float(features.iloc[0][name])
            low, high = float(bounds["min"]), float(bounds["max"])
            if value < low or value > high:
                warnings.append({"feature": name, "observed": value,
                                 "training_min": low, "training_max": high})
        return {
            "status": "outside_training_ranges" if warnings else "within_checked_training_ranges",
            "out_of_training_range_features": warnings,
            "interpretation": "Ranges describe this small synthetic training distribution, not medical limits or proof of model reliability.",
        }

    def _shap_explanation(self, features: pd.DataFrame, predicted_class: str) -> dict[str, Any]:
        """TreeSHAP for the predicted class, preserving its actual output units."""
        model = self.models[TASK_FATIGUE]
        task_frame = self._task_frame(features, TASK_FATIGUE)
        transformed = model[:-1].transform(task_frame)
        explanation = self.shap_explainer(transformed, check_additivity=True)
        values = np.asarray(explanation.values)
        base = np.asarray(explanation.base_values)
        classes = [str(item) for item in model.classes_]
        class_index = classes.index(predicted_class)
        if values.ndim == 3:
            contributions = values[0, :, class_index]
            base_value = float(base[0, class_index] if base.ndim == 2 else base[class_index])
        elif values.ndim == 2 and len(classes) == 2:
            # Compatibility with older binary TreeSHAP output conventions.
            contributions = values[0] * (1 if class_index == 1 else -1)
            raw_base = float(base.reshape(-1)[0])
            base_value = raw_base if class_index == 1 else 1 - raw_base
        else:
            raise ArtifactUnavailableError("Unexpected TreeSHAP class-output shape for the frozen classifier.")
        if len(contributions) != len(task_frame.columns) or not np.isfinite(contributions).all():
            raise ArtifactUnavailableError("TreeSHAP did not return a finite contribution for every classifier feature.")
        feature_values = []
        for name, value, contribution in zip(task_frame.columns, task_frame.iloc[0], contributions):
            effect = float(contribution)
            feature_values.append({
                "feature": str(name), "value": float(value), "shap_value": effect,
                "direction": "supports_prediction" if effect > 0 else ("opposes_prediction" if effect < 0 else "neutral"),
            })
        supporting = sorted([item for item in feature_values if item["shap_value"] > 0], key=lambda item: item["shap_value"], reverse=True)
        remaining = sorted([item for item in feature_values if item["shap_value"] <= 0], key=lambda item: abs(item["shap_value"]), reverse=True)
        top = (supporting + remaining)[:3]
        for item in top:
            readable = item["feature"].replace("_", " ")
            direction = "increased" if item["shap_value"] > 0 else "decreased"
            item["reason"] = f"{readable} {direction} the model's score for the predicted '{predicted_class}' category relative to its SHAP reference."
        return {
            "method": "TreeSHAP", "explained_class": predicted_class,
            "model_output_space": self.shap_output_space,
            "base_value": base_value,
            "sum_feature_contributions": float(np.sum(contributions)),
            "reconstructed_model_output": base_value + float(np.sum(contributions)),
            "top_three_reasons": top,
            "all_feature_contributions": feature_values,
            "interpretation": "Attributions explain this classifier output, not causes of fatigue or medical findings. Correlated and derived features may share attribution.",
        }

    def predict(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Predict for one validated observation; raw payload never becomes labels."""
        features = prepare_features(payload)
        if len(features) != 1:
            raise ValueError("Exactly one observation is required.")
        row = features.iloc[0]
        probabilities = self._class_probabilities(features)
        fatigue_class = str(self.models[TASK_FATIGUE].predict(self._task_frame(features, TASK_FATIGUE))[0])
        shap_explanation = self._shap_explanation(features, fatigue_class)
        points = 50 * probabilities.get("moderate", 0.0) + 100 * probabilities.get("high", 0.0)
        fatigue_score = float(self.models[TASK_SCORE].predict(self._task_frame(features, TASK_SCORE))[0])
        reaction_time = float(self.models[TASK_RT].predict(self._task_frame(features, TASK_RT))[0])
        anomaly_frame = self._task_frame(features, TASK_ANOMALY)
        anomaly_model = self.models[TASK_ANOMALY]
        anomaly_decision = float(anomaly_model.decision_function(anomaly_frame)[0])
        anomaly_flag = bool(anomaly_model.predict(anomaly_frame)[0] == -1)

        text = payload.get("journal_text")
        journal_info = self.model_information.get(TASK_JOURNAL, {})
        journal: dict[str, Any] = {
            "status": "not_provided", "stress_class": None,
            "scope": "current generated-language demonstration; not diagnosis or forecast",
            "model_information": journal_info,
        }
        if text is not None and str(text).strip():
            journal_model = self.models[TASK_JOURNAL]
            journal["status"] = "experimental"
            journal["stress_class"] = str(journal_model.predict([str(text)])[0])
            if hasattr(journal_model, "predict_proba"):
                journal["model_class_probabilities"] = {
                    str(label): float(p) for label, p in zip(journal_model.classes_, journal_model.predict_proba([str(text)])[0])
                }

        timestamp = payload.get("observation_timestamp_utc")
        target_timestamp = None
        if timestamp:
            observed = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
            if observed.tzinfo is None:
                raise ValueError("observation_timestamp_utc must include a timezone.")
            target_timestamp = (observed.astimezone(timezone.utc) + timedelta(hours=24)).isoformat().replace("+00:00", "Z")

        actions = ["Review these demonstration outputs alongside the recorded measurements and their quality."]
        if fatigue_class in {"moderate", "high"}:
            actions.append("Review the approved work/rest schedule with the responsible crew or mission-support person.")
        if anomaly_flag:
            actions.append("Check measurement conditions and sensor quality; follow approved procedures for repeating a measurement or seeking human review.")
        actions.append("Use approved mission and medical procedures for concerning symptoms; this prototype makes no autonomous medical or mission decisions.")

        return _jsonable({
            "label": fatigue_class,
            "points": round(points, 1),
            "points_definition": "Prototype class-severity index: 0*P(low) + 50*P(moderate) + 100*P(high); not a clinical risk probability.",
            "reasons": shap_explanation["top_three_reasons"],
            "model_version": self.metadata.get("model_version", "unknown"),
            "data_origin": "synthetic_training_data",
            "clinical_validation": False,
            "participant_id": payload.get("participant_id"),
            "observation_timestamp_utc": timestamp,
            "forecast_horizon_hours": 24,
            "target_timestamp_utc": target_timestamp,
            "input_quality": self._input_quality(features),
            "next_day_forecasts": {
                "fatigue": {
                    "class": fatigue_class,
                    "model_class_probabilities": probabilities,
                    "probability_interpretation": "uncalibrated synthetic-model class probabilities; not clinical risk",
                    "score_estimate": round(fatigue_score, 4),
                    "score_definition": "custom simulated 0..10 fatigue self-report; classification is a separate model",
                },
                "reaction_time_median_ms": round(reaction_time, 3),
            },
            "current_observation": {
                "physiology": {
                    "outlier_flag": anomaly_flag,
                    "decision_score": round(anomaly_decision, 6),
                    "decision_definition": "IsolationForest decision_function; below zero is an outlier, not a medical diagnosis",
                },
                "journal": journal,
            },
            "explanation": {
                "tree_shap": shap_explanation,
                "personal_baseline_changes": {
                    "sleep_duration_hours": round(float(row["sleep_duration_delta_from_baseline_hours"]), 4),
                    "resting_heart_rate_bpm": round(float(row["heart_rate_delta_from_baseline_bpm"]), 4),
                    "hrv_rmssd_ms": round(float(row["hrv_delta_from_baseline_ms"]), 4),
                    "reaction_time_percent": round(float(row["reaction_time_change_from_baseline_pct"]), 4),
                },
                "reference_sensitivity": self._sensitivities(payload, probabilities.get("high", 0.0)),
                "method": "Actual TreeSHAP for the predicted fatigue class, observed baseline differences, and separately labeled grouped reference substitutions.",
                "interpretation": "TreeSHAP explains the selected classifier. Reference sensitivities are a separate non-additive calculation. Neither identifies causal or medically proven factors.",
            },
            "advisory_actions": actions,
            "limitations": LIMITATIONS,
        })
