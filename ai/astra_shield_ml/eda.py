"""Create reproducible, training-only data-quality evidence and static EDA.

This command does not load model artifacts, validation.csv, or test.csv. It does
not alter observations, labels, fitted models, or frozen training reports.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "astra_shield_matplotlib_cache"))
Path(os.environ["MPLCONFIGDIR"]).mkdir(parents=True, exist_ok=True)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .features import BOUNDS, FEATURE_COLUMNS, INPUT_FIELDS


PRIMARY = "next_day_fatigue_classification"
LABELS = ["low", "moderate", "high"]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def role(column, features):
    if column in features:
        return "primary_predictor"
    if column.startswith("target_"):
        return "target_or_evaluation_label"
    if column == "journal_text":
        return "separate_NLP_input"
    return "metadata_or_redundant_protocol_field"


def exclusion_reason(column):
    specific = {
        "record_id": "Traceability key; identifier must not become a predictive shortcut.",
        "participant_id": "Grouping key retained to enforce participant-disjoint partitions; not a predictor.",
        "observation_timestamp_utc": "Prediction-cutoff audit; temporal history is supplied only through causal summary features.",
        "mission_day": "Simulation timeline metadata; omitted from the fixed primary feature contract.",
        "split": "Development partition assignment; never an input.",
        "is_synthetic": "Constant provenance flag; retained to prevent misrepresentation as observed astronaut data.",
        "data_origin": "Constant provenance; not a health measurement.",
        "generator_version": "Constant generation provenance; not a health measurement.",
        "reaction_time_trials_count": "Constant 60-trial protocol metadata; reaction time and lapse count already represent the simulated task.",
        "attention_correct_count": "Redundant with attention_accuracy_pct and the constant trial count; retain only accuracy in the model.",
        "attention_trials_count": "Constant 40-trial protocol metadata.",
        "journal_text": "Text is handled by the separate NLP model; excluded only from the numerical fatigue model.",
        "baseline_days_count": "Constant seven-day calibration protocol metadata.",
        "prediction_horizon_hours": "Constant 24-hour forecast contract metadata.",
        "target_timestamp_utc": "Future-outcome audit timestamp; unavailable as a current health feature.",
    }
    if column in specific:
        return specific[column]
    if column.startswith("target_"):
        return "Outcome/evaluation annotation; exclude from all predictors to prevent label leakage."
    return "Not selected by the frozen task-specific predictor allowlist."


def main(project_dir=None):
    root = Path(project_dir or Path(__file__).resolve().parents[1])
    output = root / "reports/eda"
    output.mkdir(parents=True, exist_ok=True)
    train_path, config_path = root / "data/train.csv", root / "data/task_config.json"
    # The only observation file loaded by this command is the training partition.
    frame = pd.read_csv(train_path)
    config = json.loads(config_path.read_text())
    features = config["tasks"][PRIMARY]["predictors"]
    target = config["tasks"][PRIMARY]["target"]
    if list(features) != list(FEATURE_COLUMNS):
        raise ValueError("EDA task allowlist does not match the deployed feature contract")
    if not frame.split.eq("train").all():
        raise ValueError("EDA must operate on the training partition only")
    checks = []

    def audit(name, invalid_count, details):
        checks.append({"check": name, "status": "pass" if invalid_count == 0 else "review",
                       "invalid_count": int(invalid_count), "details": details})

    numeric = frame.select_dtypes(include="number")
    audit("missing_cells", frame.isna().sum().sum(), "No imputation was necessary in this prepared synthetic partition.")
    audit("nonfinite_numeric_cells", (~np.isfinite(numeric.to_numpy())).sum(), "NaN and infinity are invalid model values.")
    audit("exact_duplicate_rows", frame.duplicated().sum(), "Complete duplicate rows are distinct from legitimate repeated participant IDs.")
    audit("duplicate_record_ids", frame.record_id.duplicated().sum(), "Each observation must have a unique participant-day record ID.")
    audit("duplicate_participant_day_keys", frame.duplicated(["participant_id", "mission_day"]).sum(), "Each participant has one observation per mission day.")
    audit("duplicate_primary_predictor_vectors", frame[features].duplicated().sum(), "Exact duplicate 26-feature numerical vectors; no near-duplicate claim is made.")
    audit("non_training_partition_rows", (~frame.split.eq("train")).sum(), "No validation/test observations are included in EDA.")
    audit("non_synthetic_flags", (~frame.is_synthetic.eq(1)).sum(), "This dataset is explicitly a synthetic engineering demonstration.")
    audit("future_or_target_predictors", sum(c.startswith("target_") for c in features), "All outcome annotations and future labels are excluded from the predictor allowlist.")
    zero_variance = [c for c in features if frame[c].nunique(dropna=False) <= 1]
    audit("zero_variance_primary_predictors", len(zero_variance), "Constant provenance/protocol columns exist in the source table but are not model inputs.")
    sizes = frame.groupby("participant_id").size()
    audit("participants_without_60_daily_rows", (~sizes.eq(60)).sum(), "Repeated IDs represent valid longitudinal data, not duplicate people to remove.")
    invalid_schedules = sum(sorted(group.mission_day.tolist()) != list(range(1, 61))
                            for _, group in frame.groupby("participant_id"))
    audit("participants_without_days_1_to_60", invalid_schedules, "The training partition contains 60 consecutive simulation days per person.")
    for column in INPUT_FIELDS:
        lo, hi = BOUNDS[column]
        audit("input_bounds__" + column, (~frame[column].between(lo, hi)).sum(),
              f"Broad numerical API bounds [{lo}, {hi}]; engineering input validation, not clinical thresholds.")
    for column in ["awakenings_count", "reaction_time_lapses_count"]:
        audit("whole_count__" + column, (~np.isclose(frame[column], np.round(frame[column]))).sum(),
              "Count variables must contain whole counts.")
    opportunity = frame.sleep_duration_hours / (frame.sleep_efficiency_pct / 100)
    awake_minutes = (opportunity - frame.sleep_duration_hours) * 60
    audit("sleep_onset_exceeds_awake_opportunity", (frame.sleep_onset_delay_minutes > awake_minutes + .1).sum(),
          "Sleep efficiency and duration must allow the reported onset delay.")
    audit("daily_time_budget_exceeds_24_hours", (opportunity + frame.workload_hours + frame.exercise_minutes/60 > 24.01).sum(),
          "The simulator defines sleep opportunity, duty and exercise as non-overlapping parts of one day.")
    horizon = pd.to_datetime(frame.target_timestamp_utc, utc=True) - pd.to_datetime(frame.observation_timestamp_utc, utc=True)
    audit("forecast_horizon_not_24_hours", (~horizon.eq(pd.Timedelta(hours=24))).sum(), "Future target timestamps are exactly one day after observation cutoffs.")
    audit("invalid_custom_fatigue_score", (~frame.target_next_day_fatigue_score.between(0, 10)).sum(), "The target is a custom simulated score, not KSS or a clinical scale.")
    expected_class = np.where(frame.target_next_day_fatigue_score < 4, "low",
                              np.where(frame.target_next_day_fatigue_score < 7, "moderate", "high"))
    audit("fatigue_class_not_matching_documented_rule", (frame[target].to_numpy() != expected_class).sum(),
          "Future demo fatigue score uses arbitrary category cutoffs 4 and 7; score itself is not an input.")

    missingness = pd.DataFrame({"column": frame.columns, "dtype": [str(frame[c].dtype) for c in frame],
                               "missing_cells": [int(frame[c].isna().sum()) for c in frame],
                               "missing_pct": [float(frame[c].isna().mean()*100) for c in frame],
                               "role": [role(c, features) for c in frame]})
    missingness.to_csv(output / "missingness.csv", index=False)
    summary = numeric.describe(percentiles=[.25, .5, .75]).T.reset_index(names="column")
    summary["unique_values"] = summary.column.map(lambda c: frame[c].nunique())
    summary["role"] = summary.column.map(lambda c: role(c, features))
    summary.to_csv(output / "numeric_summary.csv", index=False)
    counts = frame[target].value_counts().reindex(LABELS, fill_value=0)
    classes = pd.DataFrame({"class": counts.index, "count": counts.values,
                            "percentage": counts.values / len(frame) * 100})
    classes.to_csv(output / "target_class_counts.csv", index=False)
    excluded = pd.DataFrame([{"column": c, "primary_model_action": "excluded_from_predictors; retained_in_audit_table",
                              "reason": exclusion_reason(c), "unique_values": int(frame[c].nunique()),
                              "used_by_separate_NLP_task": c == "journal_text"}
                             for c in frame if c not in features])
    excluded.to_csv(output / "excluded_columns.csv", index=False)
    correlation = frame[features].corr(method="pearson")
    correlation.to_csv(output / "predictor_correlations.csv", index=True)
    pairs = []
    for i, first in enumerate(features):
        for second in features[i+1:]:
            value = float(correlation.loc[first, second])
            if abs(value) >= .85:
                pairs.append({"feature_1": first, "feature_2": second, "pearson_r": value,
                              "abs_r": abs(value), "action": "retained_by_design; correlated derived/baseline measurements require cautious importance interpretation"})
    high = pd.DataFrame(pairs, columns=["feature_1", "feature_2", "pearson_r", "abs_r", "action"])
    if len(high):
        high = high.sort_values("abs_r", ascending=False)
    high.to_csv(output / "high_correlations.csv", index=False)
    pd.DataFrame(checks).to_csv(output / "data_quality_summary.csv", index=False)
    result = {
        "scope": "Training-only EDA and schema-quality audit; not clinical validation",
        "prepared_at_utc": datetime.now(timezone.utc).isoformat(),
        "observation_files_read": ["data/train.csv"],
        "train_sha256": sha256(train_path), "task_config_sha256": sha256(config_path),
        "rows": len(frame), "columns": len(frame.columns),
        "virtual_participants": int(frame.participant_id.nunique()),
        "daily_observations_per_participant": int(sizes.iloc[0]),
        "primary_predictor_count": len(features), "excluded_primary_columns": len(excluded),
        "legitimate_repeated_participant_id_occurrences": int(frame.participant_id.duplicated().sum()),
        "zero_variance_primary_predictors": zero_variance,
        "class_counts": {str(k): int(v) for k,v in counts.items()},
        "majority_class_training_accuracy": float(counts.max()/len(frame)),
        "high_correlation_threshold_abs_r": .85, "high_correlation_pairs": len(high),
        "rows_removed_by_this_audit": 0,
        "cells_imputed_in_prepared_training_csv": 0,
        "cleaning_action": "Already prepared source retained unchanged; no observed invalid rows required deletion or repair.",
        "pipeline_imputer": "Median imputer was fitted on training data as a defensive pipeline step; supplied training inputs have no missing cells.",
        "clinical_validation": False,
        "all_checks_passed": all(check["status"] == "pass" for check in checks),
        "checks": checks,
    }
    (output / "data_quality_summary.json").write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")

    plt.style.use("default")
    fig, axes = plt.subplots(2, 3, figsize=(13, 7.5), constrained_layout=True)
    histograms = [("sleep_duration_hours", "Sleep duration (hours)"),
                  ("resting_heart_rate_bpm", "Resting heart rate (bpm)"),
                  ("hrv_rmssd_ms", "RMSSD (ms)"),
                  ("reaction_time_median_ms", "Reaction-time median (ms)"),
                  ("self_report_stress_score", "Custom stress score (0–10)"),
                  ("self_report_fatigue_score", "Custom fatigue score (0–10)")]
    for ax, (column, title) in zip(axes.flat, histograms):
        ax.hist(frame[column], bins=35, color="#3876a6", alpha=.9, edgecolor="white", linewidth=.35)
        ax.set_title(title, fontsize=11); ax.set_ylabel("Training observations")
        ax.grid(axis="y", alpha=.2)
    fig.suptitle("ASTRA-SHIELD: synthetic training data only (5,040 rows / 84 virtual people)", fontsize=13)
    fig.savefig(output / "training_feature_distributions.png", dpi=160)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(7.5, 5), constrained_layout=True)
    bars = ax.bar(LABELS, counts.values, color=["#429c82", "#e6ae45", "#c96969"])
    for bar, count in zip(bars, counts.values):
        ax.text(bar.get_x()+bar.get_width()/2, count+40, f"{count:,}\n({count/len(frame):.1%})", ha="center", fontsize=10)
    ax.set_ylim(0, counts.max()*1.18); ax.set_ylabel("Training observations")
    ax.set_title("Next-day simulated fatigue categories — training partition")
    ax.grid(axis="y", alpha=.2); ax.set_axisbelow(True)
    fig.savefig(output / "training_class_distribution.png", dpi=160)
    plt.close(fig)
    labels = [c.replace("_", " ") for c in features]
    fig, ax = plt.subplots(figsize=(14, 12.5), constrained_layout=True)
    im = ax.imshow(correlation, vmin=-1, vmax=1, cmap="RdBu_r")
    ax.set_xticks(range(len(features)), labels, rotation=90, fontsize=7)
    ax.set_yticks(range(len(features)), labels, fontsize=7)
    ax.set_title("Pearson correlations of 26 synthetic TRAINING predictors\nAssociation includes intentionally derived and baseline features", fontsize=12)
    fig.colorbar(im, ax=ax, shrink=.75, label="Pearson r")
    fig.savefig(output / "numeric_correlation_heatmap.png", dpi=160)
    plt.close(fig)

    report = [
        "ASTRA-SHIELD — TRAINING-ONLY DATA QUALITY AND EDA",
        "",
        f"Observation source: data/train.csv (SHA-256 {result['train_sha256']}).",
        "No validation or test observation file was loaded for these summaries or plots.",
        "The original longitudinal synthetic dataset is used; supplied V2/V3 files are not mixed in.",
        "",
        f"Shape: {len(frame):,} rows, {len(frame.columns)} columns, {frame.participant_id.nunique()} virtual participants.",
        "Every participant has 60 daily observations. Repeated participant IDs are",
        "intentional longitudinal structure and must not be removed as duplicates.",
        f"All {len(checks)} quality checks passed: {result['all_checks_passed']}.",
        "Complete-row duplicates, duplicate participant-day keys and duplicate numerical",
        "predictor vectors are checked separately; counts appear in data_quality_summary.csv.",
        "",
        "CLEANING EVIDENCE",
        "The already prepared synthetic data contains no missing/non-finite cells or",
        "invalid values under the documented engineering input bounds. No rows were",
        "deleted, no measurements were rewritten, and no imputation was necessary.",
        "The model pipeline's training-fitted median imputer is defensive and unused",
        "for this complete partition. This audit does not claim to have repaired raw",
        "sensor artifacts, clinically adjudicated observations or cleaned real astronauts.",
        "",
        "RELEVANCE AND LEAKAGE",
        "The primary model uses the exact 26-column allowlist. Other columns remain in",
        "the audit table for provenance, grouping, protocol context or evaluation; they",
        "are excluded from the prediction input. Journal text is used by a separate NLP",
        "task. Excluded columns and reasons appear individually in excluded_columns.csv.",
        "All target columns, record/participant identifiers, split information and future",
        "outcome timestamps are excluded. Baseline/history causality has separate source",
        "and unit-test checks; this training-only EDA does not open the calibration audit file.",
        "",
        "CLASS BALANCE",
    ]
    for label, count in counts.items():
        report.append(f"{label}: {count:,} ({count/len(frame):.2%}).")
    report.extend([
        f"Always predicting the majority category gives {counts.max()/len(frame):.2%} training accuracy.",
        "Model comparisons therefore use macro F1 and per-class precision/recall,",
        "with persistence baselines and final held-out evaluation reported separately.",
        "The category thresholds (4 and 7 on a custom simulated 0–10 score) are",
        "engineering choices and do not establish clinical or operational risk.",
        "",
        "CORRELATION AND LIMITATIONS",
        f"{len(high)} primary-predictor pairs have absolute Pearson r >= 0.85.",
        "Strongly correlated baseline/delta/history variables are retained deliberately",
        "for personalization. Correlation is not causation, and derived-feature redundancy",
        "can affect permutation/SHAP importance allocation. No claim is made that all",
        "statistically redundant or clinically irrelevant information has been eliminated.",
        "Training-only charts describe the simulator, not measured human physiology.",
        "Generated journals and target labels are not human clinical annotations.",
        "",
        "REPRODUCE",
        ".venv/bin/python -m astra_shield_ml.eda",
    ])
    (output / "EDA_REPORT.txt").write_text("\n".join(report)+"\n")
    print(json.dumps({k:result[k] for k in ["rows", "columns", "virtual_participants",
        "primary_predictor_count", "excluded_primary_columns", "high_correlation_pairs",
        "all_checks_passed", "rows_removed_by_this_audit", "cells_imputed_in_prepared_training_csv"]}, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path)
    arguments = parser.parse_args()
    main(arguments.project_dir)
