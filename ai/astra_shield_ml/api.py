"""Standalone local FastAPI interface. Run uvicorn astra_shield_ml.api:app."""
from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
import math
import os
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .features import BOUNDS
from .service import ArtifactUnavailableError, ModelService


def _bound(name: str):
    low, high = BOUNDS[name]
    return Field(ge=low, le=high)


class Observation(BaseModel):
    """Today’s observations and genuinely earlier baseline/history summaries.

    All quantities retain their documented units. The service computes the four
    baseline-difference features; callers must never submit labels or deltas.
    """
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    sleep_duration_hours: float = _bound("sleep_duration_hours")
    sleep_efficiency_pct: float = _bound("sleep_efficiency_pct")
    sleep_onset_delay_minutes: float = _bound("sleep_onset_delay_minutes")
    awakenings_count: int = _bound("awakenings_count")
    sleep_midpoint_deviation_minutes: float = _bound("sleep_midpoint_deviation_minutes")
    resting_heart_rate_bpm: float = _bound("resting_heart_rate_bpm")
    hrv_rmssd_ms: float = _bound("hrv_rmssd_ms")
    reaction_time_median_ms: float = _bound("reaction_time_median_ms")
    reaction_time_lapses_count: int = _bound("reaction_time_lapses_count")
    attention_accuracy_pct: float = _bound("attention_accuracy_pct")
    self_report_stress_score: float = _bound("self_report_stress_score")
    self_report_fatigue_score: float = _bound("self_report_fatigue_score")
    self_report_mood_score: float = _bound("self_report_mood_score")
    workload_hours: float = _bound("workload_hours")
    exercise_minutes: float = _bound("exercise_minutes")
    baseline_sleep_duration_hours: float = _bound("sleep_duration_hours")
    baseline_resting_heart_rate_bpm: float = _bound("resting_heart_rate_bpm")
    baseline_hrv_rmssd_ms: float = _bound("hrv_rmssd_ms")
    baseline_reaction_time_median_ms: float = _bound("reaction_time_median_ms")
    prior_3day_mean_sleep_hours: float = _bound("prior_3day_mean_sleep_hours")
    prior_3day_mean_resting_heart_rate_bpm: float = _bound("resting_heart_rate_bpm")
    prior_3day_mean_reaction_time_ms: float = _bound("prior_3day_mean_reaction_time_ms")
    journal_text: str | None = Field(default=None, max_length=5000)
    participant_id: str | None = Field(default=None, min_length=1, max_length=100)
    observation_timestamp_utc: str | None = None

    @field_validator("observation_timestamp_utc")
    @classmethod
    def timestamp_with_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("Use an ISO-8601 timestamp including timezone, for example 2026-01-01T18:00:00Z.") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("Timestamp must include a timezone.")
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class BatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    observations: list[Observation] = Field(min_length=1, max_length=64)


app = FastAPI(
    title="ASTRA-SHIELD Prototype Model API",
    version="0.1.0",
    description=("Offline inference for synthetic-data fatigue and cognitive forecasts, current physiology outliers, "
                 "and generated-journal analysis. No clinical or astronaut-health validation is claimed. "
                 "This local development service has no authentication; do not expose it publicly without the deployment controls your team requires."),
)


@lru_cache(maxsize=1)
def get_service() -> ModelService:
    return ModelService(os.environ.get("ASTRA_MODEL_PATH"))


def _safe_error(value: Any) -> Any:
    """Validation messages must remain valid JSON even for NaN/Infinity input."""
    if isinstance(value, dict):
        return {str(k): _safe_error(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_error(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"detail": _safe_error(exc.errors())})


def available_service() -> ModelService:
    try:
        return get_service()
    except ArtifactUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/health")
def health():
    service = available_service()
    return {"status": "ready", "model_version": service.metadata.get("model_version", "unknown"),
            "tasks_loaded": len(service.models), "data_origin": "synthetic", "clinical_validation": False}


@app.get("/v1/model-info")
def model_info(service: Annotated[ModelService, Depends(available_service)]):
    return service.model_info()


@app.post("/v1/predict")
def predict(observation: Observation, service: Annotated[ModelService, Depends(available_service)]):
    try:
        return service.predict(observation.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/v1/predict/batch")
def predict_batch(batch: BatchRequest, service: Annotated[ModelService, Depends(available_service)]):
    predictions = []
    for index, observation in enumerate(batch.observations):
        try:
            predictions.append(service.predict(observation.model_dump(exclude_none=True)))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail={"observation_index": index, "message": str(exc)}) from exc
    return {"count": len(predictions), "predictions": predictions}
