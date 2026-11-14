"""Causal feature contract shared by offline clients and the HTTP service.

The backend supplies 15 current measurements, four fixed calibration means and
three prior-only means. Target columns and identity never enter model inputs.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
from numbers import Real

import pandas as pd


CURRENT_FIELDS = [
    "sleep_duration_hours", "sleep_efficiency_pct", "sleep_onset_delay_minutes",
    "awakenings_count", "sleep_midpoint_deviation_minutes", "resting_heart_rate_bpm",
    "hrv_rmssd_ms", "reaction_time_median_ms", "reaction_time_lapses_count",
    "attention_accuracy_pct", "self_report_stress_score", "self_report_fatigue_score",
    "self_report_mood_score", "workload_hours", "exercise_minutes",
]
BASELINE_FIELDS = [
    "baseline_sleep_duration_hours", "baseline_resting_heart_rate_bpm",
    "baseline_hrv_rmssd_ms", "baseline_reaction_time_median_ms",
]
HISTORY_FIELDS = [
    "prior_3day_mean_sleep_hours", "prior_3day_mean_resting_heart_rate_bpm",
    "prior_3day_mean_reaction_time_ms",
]
DERIVED_FIELDS = [
    "sleep_duration_delta_from_baseline_hours", "heart_rate_delta_from_baseline_bpm",
    "hrv_delta_from_baseline_ms", "reaction_time_change_from_baseline_pct",
]
# Preserve the exact training contract order, including the past-only means last.
FEATURE_COLUMNS = CURRENT_FIELDS + BASELINE_FIELDS + DERIVED_FIELDS + HISTORY_FIELDS
INPUT_FIELDS = CURRENT_FIELDS + BASELINE_FIELDS + HISTORY_FIELDS
OPTIONAL_FIELDS = {"journal_text", "participant_id", "observation_timestamp_utc"}

# Broad input validity bounds, not diagnostic limits or confidence intervals.
BOUNDS = {
    "sleep_duration_hours": (0.1, 16), "sleep_efficiency_pct": (10, 100),
    "sleep_onset_delay_minutes": (0, 300), "awakenings_count": (0, 100),
    "sleep_midpoint_deviation_minutes": (-720, 720),
    "resting_heart_rate_bpm": (30, 220), "hrv_rmssd_ms": (1, 300),
    "reaction_time_median_ms": (100, 2000), "reaction_time_lapses_count": (0, 60),
    "attention_accuracy_pct": (0, 100), "self_report_stress_score": (0, 10),
    "self_report_fatigue_score": (0, 10), "self_report_mood_score": (0, 10),
    "workload_hours": (0, 24), "exercise_minutes": (0, 480),
}
for _name in BASELINE_FIELDS:
    BOUNDS[_name] = BOUNDS[_name.removeprefix("baseline_")]
BOUNDS.update({
    "prior_3day_mean_sleep_hours": BOUNDS["sleep_duration_hours"],
    "prior_3day_mean_resting_heart_rate_bpm": BOUNDS["resting_heart_rate_bpm"],
    "prior_3day_mean_reaction_time_ms": BOUNDS["reaction_time_median_ms"],
})


def parse_timestamp(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("observation_timestamp_utc must be an ISO 8601 string")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("observation_timestamp_utc must be an ISO 8601 timestamp") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("observation_timestamp_utc must include a timezone")
    return result.astimezone(timezone.utc)


def _number(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a numeric measurement, not a string or boolean")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    low, high = BOUNDS[name]
    if not low <= result <= high:
        raise ValueError(f"{name} must be between {low} and {high}; these are input bounds, not medical thresholds")
    if name in {"awakenings_count", "reaction_time_lapses_count"} and not result.is_integer():
        raise ValueError(f"{name} must be a whole count")
    return result


def prepare_features(payload: dict) -> pd.DataFrame:
    """Validate one request and calculate the four deltas; never accept labels."""
    if not isinstance(payload, dict):
        raise ValueError("Expected a JSON object")
    unknown = set(payload) - set(INPUT_FIELDS) - OPTIONAL_FIELDS
    if unknown:
        raise ValueError("Unexpected fields (targets/derived fields are not inputs): " + ", ".join(sorted(unknown)))
    missing = set(INPUT_FIELDS) - set(payload)
    if missing:
        raise ValueError("Missing required fields: " + ", ".join(sorted(missing)))
    values = {name: _number(name, payload[name]) for name in INPUT_FIELDS}
    if payload.get("participant_id") is not None:
        if not isinstance(payload["participant_id"], str) or not 1 <= len(payload["participant_id"].strip()) <= 100:
            raise ValueError("participant_id must be nonempty text of at most 100 characters")
    journal = payload.get("journal_text")
    if journal is not None and (not isinstance(journal, str) or len(journal) > 5000):
        raise ValueError("journal_text must be text of at most 5000 characters or null")
    if payload.get("observation_timestamp_utc") is not None:
        parse_timestamp(payload["observation_timestamp_utc"])

    opportunity = values["sleep_duration_hours"] / (values["sleep_efficiency_pct"] / 100)
    awake_minutes = 60 * (opportunity - values["sleep_duration_hours"])
    if values["sleep_onset_delay_minutes"] > awake_minutes + 0.1:
        raise ValueError("Sleep onset delay exceeds the awake time implied by sleep duration and efficiency")
    if opportunity + values["workload_hours"] + values["exercise_minutes"] / 60 > 24.01:
        raise ValueError("Sleep opportunity, non-overlapping duty and exercise exceed a 24-hour recording window")
    values["sleep_duration_delta_from_baseline_hours"] = values["sleep_duration_hours"] - values["baseline_sleep_duration_hours"]
    values["heart_rate_delta_from_baseline_bpm"] = values["resting_heart_rate_bpm"] - values["baseline_resting_heart_rate_bpm"]
    values["hrv_delta_from_baseline_ms"] = values["hrv_rmssd_ms"] - values["baseline_hrv_rmssd_ms"]
    values["reaction_time_change_from_baseline_pct"] = 100 * (values["reaction_time_median_ms"] / values["baseline_reaction_time_median_ms"] - 1)
    # Training data publishes deltas rounded to six decimal places.
    for name in DERIVED_FIELDS:
        values[name] = round(values[name], 6)
    return pd.DataFrame([{name: values[name] for name in FEATURE_COLUMNS}])


def build_request_from_history(current: dict, calibration_history: list[dict], recent_history: list[dict]) -> dict:
    """Build an API request from a current row, seven fixed earlier calibration
    records and at least three prior daily records. No future data is accepted.

    Every history row must have participant_id, observation_timestamp_utc and the
    sleep/heart-rate/RMSSD/reaction-time measurements used in its means. Calibration
    remains fixed for the participant; supply the same initial seven rows each day.
    """
    missing_current = set(CURRENT_FIELDS) - set(current)
    if missing_current:
        raise ValueError("Current observation missing: " + ", ".join(sorted(missing_current)))
    if len(calibration_history) != 7:
        raise ValueError("Exactly seven initial calibration records are required")
    if len(recent_history) < 3:
        raise ValueError("At least three prior daily observations are required; abstain during warm-up")
    pid = current.get("participant_id")
    if not isinstance(pid, str) or not pid:
        raise ValueError("A participant_id is required when deriving history")
    now = parse_timestamp(current.get("observation_timestamp_utc"))
    base_names = [name.removeprefix("baseline_") for name in BASELINE_FIELDS]
    def checked(rows):
        stamped = []
        for row in rows:
            if row.get("participant_id") != pid:
                raise ValueError("History must belong to the current participant")
            stamp = parse_timestamp(row.get("observation_timestamp_utc"))
            if stamp >= now:
                raise ValueError("History and calibration must strictly precede the prediction cutoff")
            for name in base_names:
                _number(name, row.get(name))
            stamped.append((stamp, row))
        stamped.sort(key=lambda pair: pair[0])
        if len({stamp for stamp, _ in stamped}) != len(stamped):
            raise ValueError("History timestamps must be unique within each history collection")
        return stamped
    calibration = checked(calibration_history)
    recent = checked(recent_history)[-3:]
    if any(calibration[i][0] - calibration[i-1][0] != timedelta(days=1) for i in range(1, 7)):
        raise ValueError("Calibration must consist of seven consecutive daily observations")
    if [stamp for stamp, _ in recent] != [now-timedelta(days=d) for d in (3, 2, 1)]:
        raise ValueError("The most recent three observations must be the three preceding daily cutoffs")
    payload = {name: current[name] for name in CURRENT_FIELDS}
    payload.update({name: current[name] for name in OPTIONAL_FIELDS if name in current})
    for field in BASELINE_FIELDS:
        raw = field.removeprefix("baseline_")
        payload[field] = round(sum(float(row[raw]) for _, row in calibration) / 7, 6)
    for field, raw in [
        ("prior_3day_mean_sleep_hours", "sleep_duration_hours"),
        ("prior_3day_mean_resting_heart_rate_bpm", "resting_heart_rate_bpm"),
        ("prior_3day_mean_reaction_time_ms", "reaction_time_median_ms"),
    ]:
        payload[field] = round(sum(float(row[raw]) for _, row in recent) / 3, 6)
    prepare_features(payload)
    return payload
