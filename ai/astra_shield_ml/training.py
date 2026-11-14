"""Train using train/validation only; final test evaluation is a separate command.

All observations are synthetic demonstration data. No model is clinically
validated and probabilities must not be interpreted as medical risks.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version as package_version
import json
import os
from pathlib import Path
import platform
import time

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.ensemble import (HistGradientBoostingClassifier,
                              HistGradientBoostingRegressor, IsolationForest,
                              RandomForestClassifier, RandomForestRegressor)
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, average_precision_score,
                             balanced_accuracy_score, classification_report,
                             confusion_matrix, f1_score, mean_absolute_error,
                             precision_score, r2_score, recall_score,
                             roc_auc_score, root_mean_squared_error)
from sklearn.pipeline import Pipeline

from .estimators import EncodedXGBClassifier, PersistenceClassifier, PersistenceRegressor

SEED = 20261114
PRIMARY = "next_day_fatigue_classification"
CLASS_LABELS = ["low", "moderate", "high"]
ABLATION_EXCLUSIONS = [
    "self_report_fatigue_score",
    "reaction_time_median_ms", "reaction_time_lapses_count",
    "baseline_reaction_time_median_ms", "reaction_time_change_from_baseline_pct",
    "prior_3day_mean_reaction_time_ms",
]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def classification_metrics(y, prediction):
    return {
        "accuracy": float(accuracy_score(y, prediction)),
        "balanced_accuracy": float(balanced_accuracy_score(y, prediction)),
        "macro_f1": float(f1_score(y, prediction, labels=CLASS_LABELS,
                                    average="macro", zero_division=0)),
        "classification_report": classification_report(
            y, prediction, labels=CLASS_LABELS, output_dict=True, zero_division=0),
        "confusion_matrix_labels": CLASS_LABELS,
        "confusion_matrix": confusion_matrix(y, prediction, labels=CLASS_LABELS).tolist(),
    }


def regression_metrics(y, prediction):
    return {"mae": float(mean_absolute_error(y, prediction)),
            "rmse": float(root_mean_squared_error(y, prediction)),
            "r2": float(r2_score(y, prediction))}


def anomaly_metrics(y, model, X):
    prediction = (model.predict(X) == -1).astype(int)
    score = -model.decision_function(X)
    return {"precision": float(precision_score(y, prediction, zero_division=0)),
            "recall": float(recall_score(y, prediction, zero_division=0)),
            "f1": float(f1_score(y, prediction, zero_division=0)),
            "average_precision": float(average_precision_score(y, score)),
            "roc_auc": float(roc_auc_score(y, score)),
            "confusion_matrix_labels": [0, 1],
            "confusion_matrix": confusion_matrix(y, prediction, labels=[0, 1]).tolist()}


def numeric_pipeline(estimator):
    # Imputation is fitted on training observations only. No global scaling is
    # needed for these tree models; physical units are preserved at the boundary.
    return Pipeline([("imputer", SimpleImputer(strategy="median")),
                     ("model", estimator)])


def candidate_models(task):
    if task == PRIMARY:
        return {
            "random_forest_balanced": numeric_pipeline(RandomForestClassifier(
                n_estimators=200, max_depth=14, min_samples_leaf=8,
                class_weight="balanced", random_state=SEED, n_jobs=2)),
            "xgboost_balanced": numeric_pipeline(EncodedXGBClassifier()),
        }
    if task in {"next_day_fatigue_regression", "next_day_reaction_time_regression"}:
        return {
            "random_forest_regressor": numeric_pipeline(RandomForestRegressor(
                n_estimators=160, max_depth=16, min_samples_leaf=8,
                random_state=SEED, n_jobs=2)),
            "hist_gradient_boosting_regressor": numeric_pipeline(
                HistGradientBoostingRegressor(max_iter=150, max_leaf_nodes=15,
                    learning_rate=.06, l2_regularization=10., random_state=SEED)),
        }
    if task == "journal_stress_classification":
        return {
            "word_tfidf_logistic": Pipeline([
                ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=2,
                                           max_features=5000, sublinear_tf=True)),
                ("model", LogisticRegression(C=1., class_weight="balanced",
                                               max_iter=1000, random_state=SEED))]),
            "character_tfidf_logistic": Pipeline([
                ("tfidf", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5),
                                           min_df=2, max_features=10000,
                                           sublinear_tf=True)),
                ("model", LogisticRegression(C=1., class_weight="balanced",
                                               max_iter=1000, random_state=SEED))]),
        }
    raise ValueError(f"No candidates configured for {task}")


def baseline_models(task):
    if task == PRIMARY:
        return {"majority_class": DummyClassifier(strategy="most_frequent"),
                "current_fatigue_persistence": PersistenceClassifier()}
    if task == "next_day_fatigue_regression":
        return {"training_mean": DummyRegressor(strategy="mean"),
                "current_fatigue_persistence": PersistenceRegressor("self_report_fatigue_score")}
    if task == "next_day_reaction_time_regression":
        return {"training_mean": DummyRegressor(strategy="mean"),
                "current_reaction_time_persistence": PersistenceRegressor("reaction_time_median_ms")}
    if task == "journal_stress_classification":
        return {"majority_class": Pipeline([
            ("tfidf", TfidfVectorizer(min_df=2)),
            ("model", DummyClassifier(strategy="most_frequent"))])}
    return {}


def read_prepared_data(project):
    # Deliberately no test.csv read or test-target inspection in this module.
    train = pd.read_csv(project / "data/train.csv")
    validation = pd.read_csv(project / "data/validation.csv")
    config = json.loads((project / "data/task_config.json").read_text())
    assert set(train.participant_id).isdisjoint(validation.participant_id)
    assert train.split.eq("train").all() and validation.split.eq("validation").all()
    for frame in [train, validation]:
        assert frame.is_synthetic.eq(1).all()
        assert frame.record_id.is_unique and not frame.isna().any().any()
        for task in config["tasks"].values():
            assert not any(c.startswith("target_") for c in task["predictors"])
    return train, validation, config


def main(project_dir=None):
    project = Path(project_dir or Path(__file__).resolve().parents[1])
    artifacts, reports = project / "artifacts", project / "reports"
    artifacts.mkdir(exist_ok=True); reports.mkdir(exist_ok=True)
    if (reports / "test_metrics.json").exists():
        raise RuntimeError("Final test has already been evaluated. Use a new experiment directory; do not tune against the used test set.")
    start = time.perf_counter()
    train, validation, config = read_prepared_data(project)
    models, fitted_baselines, information, candidates_report = {}, {}, {}, {}
    for task_name, task in config["tasks"].items():
        predictors = task["predictors"]
        is_text = task_name == "journal_stress_classification"
        X_train = train.journal_text if is_text else train[predictors]
        X_validation = validation.journal_text if is_text else validation[predictors]
        if task_name == "physiology_anomaly_detection":
            # Fixed a priori settings. Injected-event labels are never used by fit,
            # model choice, contamination selection, or a normal-only subset.
            estimator = numeric_pipeline(IsolationForest(
                n_estimators=200, max_samples=256, contamination=.065,
                random_state=SEED, n_jobs=2))
            elapsed = time.perf_counter()
            estimator.fit(X_train)
            fit_seconds = time.perf_counter()-elapsed
            metrics = anomaly_metrics(validation[task["evaluation_target"]],
                                      estimator, X_validation)
            models[task_name] = estimator
            fitted_baselines[task_name] = {}
            information[task_name] = {
                "selected_model": "fixed_isolation_forest", "selection_basis": "fixed a priori; no anomaly labels in training/selection",
                "fit_seconds": fit_seconds, "validation_metrics": metrics,
                "baseline_validation_metrics": {}, "quality_status": "synthetic_injected_events_only",
                "threshold": "fixed sklearn decision_function zero; contamination .065 specified before fitting",
            }
            candidates_report[task_name] = information[task_name]
            print(f"{task_name}: fitted fixed IsolationForest in {fit_seconds:.2f}s", flush=True)
            continue
        target = task["target"]
        y_train, y_validation = train[target], validation[target]
        classification = task_name.endswith("classification")
        metric_function = classification_metrics if classification else regression_metrics
        ranked = {}
        baseline_results, candidate_results = {}, {}
        fitted_baselines[task_name] = {}
        for name, estimator in {**baseline_models(task_name), **candidate_models(task_name)}.items():
            before = time.perf_counter()
            estimator.fit(X_train, y_train)
            elapsed = time.perf_counter()-before
            metrics = metric_function(y_validation, estimator.predict(X_validation))
            ranked[name] = (estimator, metrics, elapsed)
            entry = {"fit_seconds": elapsed, "validation_metrics": metrics,
                     "parameters": str(estimator)}
            if name in baseline_models(task_name):
                baseline_results[name] = entry
                fitted_baselines[task_name][name] = estimator
            else:
                candidate_results[name] = entry
            print(f"{task_name} / {name}: {elapsed:.2f}s; "
                  f"validation {'macro_f1' if classification else 'MAE'}="
                  f"{metrics['macro_f1' if classification else 'mae']:.4f}", flush=True)
        metric = "macro_f1" if classification else "mae"
        eligible_names = list(candidate_results) if task_name == PRIMARY else list(ranked)
        selected_name = (max(eligible_names, key=lambda n: ranked[n][1][metric]) if classification
                         else min(eligible_names, key=lambda n: ranked[n][1][metric]))
        selected, selected_metrics, fit_seconds = ranked[selected_name]
        baseline_best = (max(baseline_results, key=lambda n: baseline_results[n]["validation_metrics"][metric])
                         if classification else min(baseline_results, key=lambda n: baseline_results[n]["validation_metrics"][metric]))
        baseline_metric = baseline_results[baseline_best]["validation_metrics"][metric]
        improvement = selected_metrics[metric]-baseline_metric if classification else baseline_metric-selected_metrics[metric]
        models[task_name] = selected
        information[task_name] = {
            "selected_model": selected_name,
            "selection_basis": "validation macro F1" if classification else "validation MAE",
            "validation_metrics": selected_metrics,
            "baseline_validation_metrics": {n: r["validation_metrics"] for n,r in baseline_results.items()},
            "best_baseline": baseline_best, "improvement_over_best_baseline": improvement,
            "fit_seconds": fit_seconds,
            "quality_status": "synthetic_demo_only" if improvement > 0 else "no_improvement_over_baseline",
            "trained_on": "train only; validation used for candidate selection; no train+validation refit",
        }
        candidates_report[task_name] = {"baselines": baseline_results,
                                       "candidates": candidate_results,
                                       "selection": information[task_name]}
    # Sensitivity experiment on our original longitudinal dataset: remove
    # current fatigue self-report and the full reaction-time feature family.
    full_features = config["tasks"][PRIMARY]["predictors"]
    ablation_features = [c for c in full_features if c not in ABLATION_EXCLUSIONS]
    ablation_models, ablation_results = {}, {}
    y_train = train[config["tasks"][PRIMARY]["target"]]
    y_validation = validation[config["tasks"][PRIMARY]["target"]]
    for name, estimator in candidate_models(PRIMARY).items():
        before = time.perf_counter()
        estimator.fit(train[ablation_features], y_train)
        elapsed = time.perf_counter()-before
        metrics = classification_metrics(y_validation, estimator.predict(validation[ablation_features]))
        ablation_models[name] = estimator
        ablation_results[name] = {"fit_seconds": elapsed, "validation_metrics": metrics}
        print(f"ablation / {name}: {elapsed:.2f}s; validation macro_f1={metrics['macro_f1']:.4f}", flush=True)
    ablation_report = {
        "data_origin": "synthetic", "test_used": False,
        "actual_target": config["tasks"][PRIMARY]["target"],
        "scope": "Without current fatigue self-report and current/baseline/historical reaction-time features",
        "excluded_available_proxies": ABLATION_EXCLUSIONS,
        "remaining_predictors": ablation_features,
        "full_predictor_count": len(full_features), "ablation_predictor_count": len(ablation_features),
        "full_model_results": candidates_report[PRIMARY]["candidates"],
        "ablation_model_results": ablation_results,
        "deployment_selection": "Full-model RF versus XGBoost comparison on validation macro F1 only; ablation does not choose deployment model",
    }
    write_json(reports / "ablation_validation_metrics.json", ablation_report)
    # Train medians provide explicit reference observations for descriptive
    # sensitivity checks. They do not use validation/test statistics.
    numeric_features = config["tasks"][PRIMARY]["predictors"]
    reference = {c: float(train[c].median()) for c in numeric_features}
    split_manifest_path = project / "data/split_manifest.json"
    split_manifest = json.loads(split_manifest_path.read_text()) if split_manifest_path.exists() else {}
    metadata = {
        "model_version": "0.1.0", "data_origin": "synthetic",
        "forecast_horizon_hours": 24, "clinical_validation": False,
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_sha256": split_manifest.get("source_sha256", split_manifest.get("dataset_sha256", "see data/split_manifest.json")),
        "random_seed": SEED, "training_location": "attached cloud workspace CPU",
        "training_rows": len(train), "validation_rows": len(validation),
        "training_participants": int(train.participant_id.nunique()),
        "validation_participants": int(validation.participant_id.nunique()),
        "test_accessed_during_training": False,
        "actual_fatigue_target": config["tasks"][PRIMARY]["target"],
        "package_versions": {"python": platform.python_version(), "numpy": np.__version__,
                             "pandas": pd.__version__, "scikit_learn": sklearn.__version__,
                             "joblib": joblib.__version__, "xgboost": package_version("xgboost-cpu")},
        "cpu_logical_count": os.cpu_count(),
        "probability_interpretation": "Uncalibrated model class scores on simulated data; not medical-risk probabilities",
        "limitations": ["Every training and validation observation is synthetic.",
                        "Journal text is generated from split-specific sentence banks.",
                        "Fatigue labels use arbitrary custom score thresholds 4 and 7.",
                        "No medical diagnosis or operational readiness inference is validated."],
    }
    bundle = {"format_version": 1, "models": models,
              "baselines": fitted_baselines, "task_config": config,
              "ablation_models": ablation_models,
              "ablation_predictors": ablation_features,
              "metadata": metadata, "reference_values": reference,
              "training_feature_ranges": {
                  c: {"min": float(train[c].min()), "max": float(train[c].max())}
                  for c in numeric_features},
              "model_information": information}
    joblib.dump(bundle, artifacts / "bundle.joblib", compress=3)
    write_json(reports / "validation_metrics.json", {
        "data_origin": "synthetic", "clinical_validation": False,
        "selection_data": "validation only", "test_used": False,
        "tasks": candidates_report})
    # Interpretability is evaluated on validation only and is global association,
    # not a per-person causal explanation. Keep it small for the hackathon.
    before = time.perf_counter()
    importance = permutation_importance(models[PRIMARY], validation[numeric_features],
                                       validation[config["tasks"][PRIMARY]["target"]],
                                       scoring="f1_macro", n_repeats=3,
                                       random_state=SEED, n_jobs=2)
    pd.DataFrame({"feature": numeric_features,
                  "validation_macro_f1_drop_mean": importance.importances_mean,
                  "validation_macro_f1_drop_std": importance.importances_std}).sort_values(
                      "validation_macro_f1_drop_mean", ascending=False).to_csv(
                          reports / "fatigue_validation_permutation_importance.csv", index=False)
    write_json(reports / "training_summary.json", {
        "metadata": metadata,
        "total_training_selection_seconds": time.perf_counter()-start,
        "permutation_importance_seconds": time.perf_counter()-before,
        "selected_models": {name: info["selected_model"] for name,info in information.items()},
        "quality_status": {name: info["quality_status"] for name,info in information.items()},
    })
    freeze = {
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "selection_complete": True, "test_used_for_selection": False,
        "artifact_sha256": {p.relative_to(project).as_posix(): sha256(p)
                            for p in [artifacts / "bundle.joblib", reports / "validation_metrics.json",
                                      reports / "training_summary.json", reports / "ablation_validation_metrics.json"]},
        "data_sha256": {"data/train.csv": sha256(project / "data/train.csv"),
                        "data/validation.csv": sha256(project / "data/validation.csv")},
        "task_config_sha256": sha256(project / "data/task_config.json"),
        "note": "The final test CSV has not been loaded by training; run the separate evaluation command once.",
    }
    # Root stages and hashes all partitions. Copy the already recorded test hash
    # without opening the test CSV; support common manifest layouts.
    for key in ["files", "partitions", "splits", "data_sha256", "file_sha256"]:
        entries = split_manifest.get(key, {})
        if isinstance(entries, dict):
            for entry_name, value in entries.items():
                if entry_name in {"test", "test.csv", "data/test.csv"}:
                    digest = value.get("sha256") if isinstance(value, dict) else value
                    if isinstance(digest, str) and len(digest) == 64:
                        freeze["data_sha256"]["data/test.csv"] = digest
    write_json(artifacts / "frozen_manifest.json", freeze)
    (reports / "MODEL_CARD.txt").write_text(
        "ASTRA-SHIELD 0.1.0 — SYNTHETIC PROTOTYPE\n\n"
        "Five components were trained in the attached cloud CPU workspace.\n"
        "The primary full model compares Random Forest and XGBoost by validation\n"
        "macro F1. A separate sensitivity ablation excludes current custom\n"
        "fatigue self-report and all current/historical PVT-like predictors.\n"
        "Primary task: predict next-day custom low/moderate/high fatigue from\n"
        "today's data. Secondary tasks: next-day fatigue score, next-day median\n"
        "reaction time, current injected physiology-event detection, current\n"
        "generated-journal stress classification. These are separate tasks.\n\n"
        "All values and target labels are simulated. They are not NASA astronaut\n"
        "measurements, clinical labels, or validated medical-risk probabilities.\n"
        "Fatigue cutoffs 4 and 7 are engineering demo choices. Physiological\n"
        "events are injected by the generator, not diagnosed diseases. Journal\n"
        "language is templated and its held-out performance cannot validate real\n"
        "human-language or psychiatric assessment.\n\n"
        "Training uses 84 virtual participants; validation uses 18 different\n"
        "participants. Seven premission days establish personal baselines,\n"
        "including for held-out participants. Historical means use prior days\n"
        "only. Every target and identifier is excluded from model input.\n"
        "Preprocessing is fitted on training data only. Validation selects\n"
        "among small prespecified candidates and baseline alternatives; no\n"
        "train+validation refit is performed. IsolationForest is fitted without\n"
        "event annotations; its configuration and threshold are fixed.\n\n"
        "Final test evaluation must be executed separately after this freeze.\n"
        "Do not tune the frozen models against test results.\n\n"
        "Only load joblib artifacts from trusted sources: they contain Python\n"
        "pickle objects. Keep the model, feature contract and dependency versions\n"
        "together. No external AI services or API keys are used.\n")
    print(json.dumps({"status": "frozen", "seconds": time.perf_counter()-start,
                      "selected": {n:i["selected_model"] for n,i in information.items()},
                      "test_accessed": False}, indent=2), flush=True)
    return bundle


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path, default=None)
    args = parser.parse_args()
    main(args.project_dir)
