/** Server-side adapter for the existing private Python model service.
 * Keep this client in the TypeScript backend, not in Angular/Ionic browser code.
 */
export type FatigueLabel = "low" | "moderate" | "high";

export interface ModelFeatures {
  sleep_duration_hours: number;
  sleep_efficiency_pct: number;
  sleep_onset_delay_minutes: number;
  awakenings_count: number;
  sleep_midpoint_deviation_minutes: number;
  resting_heart_rate_bpm: number;
  hrv_rmssd_ms: number;
  reaction_time_median_ms: number;
  reaction_time_lapses_count: number;
  attention_accuracy_pct: number;
  self_report_stress_score: number;
  self_report_fatigue_score: number;
  self_report_mood_score: number;
  workload_hours: number;
  exercise_minutes: number;
  baseline_sleep_duration_hours: number;
  baseline_resting_heart_rate_bpm: number;
  baseline_hrv_rmssd_ms: number;
  baseline_reaction_time_median_ms: number;
  prior_3day_mean_sleep_hours: number;
  prior_3day_mean_resting_heart_rate_bpm: number;
  prior_3day_mean_reaction_time_ms: number;
  journal_text?: string | null;
  participant_id?: string | null;
  observation_timestamp_utc?: string | null;
}

export interface ShapReason {
  feature: string;
  value: number;
  shap_value: number;
  direction: "supports_prediction" | "opposes_prediction" | "neutral";
  reason: string;
}

export interface Prediction {
  label: FatigueLabel;
  /** Uncalibrated 0..100 prototype severity index, not medical risk. */
  points: number;
  points_definition: string;
  reasons: ShapReason[];
  model_version: string;
  data_origin: "synthetic_training_data";
  clinical_validation: false;
  participant_id: string | null;
  observation_timestamp_utc: string | null;
  forecast_horizon_hours: 24;
  target_timestamp_utc: string | null;
  input_quality: {
    status: string;
    out_of_training_range_features: Array<{
      feature: string; observed: number; training_min: number; training_max: number;
    }>;
    interpretation: string;
  };
  next_day_forecasts: {
    fatigue: {
      class: FatigueLabel;
      model_class_probabilities: Record<FatigueLabel, number>;
      probability_interpretation: string;
      score_estimate: number;
      score_definition: string;
    };
    reaction_time_median_ms: number;
  };
  current_observation: {
    physiology: { outlier_flag: boolean; decision_score: number; decision_definition: string };
    journal: {
      status: "not_provided" | "experimental";
      stress_class: FatigueLabel | null;
      scope: string;
      model_information: Record<string, unknown>;
      model_class_probabilities?: Record<FatigueLabel, number>;
    };
  };
  explanation: {
    tree_shap: {
      method: "TreeSHAP";
      explained_class: FatigueLabel;
      model_output_space: "class_probability" | "raw_class_margin";
      base_value: number;
      sum_feature_contributions: number;
      reconstructed_model_output: number;
      top_three_reasons: ShapReason[];
      all_feature_contributions: Array<Omit<ShapReason, "reason">>;
      interpretation: string;
    };
    personal_baseline_changes: Record<string, number>;
    reference_sensitivity: Array<{
      group: string;
      high_class_probability_difference: number;
      direction_relative_to_training_reference: "higher" | "lower" | "unchanged";
    }>;
    method: string;
    interpretation: string;
  };
  advisory_actions: string[];
  limitations: string[];
}

export const REQUIRED_NUMERIC_FIELDS = [
  "sleep_duration_hours", "sleep_efficiency_pct", "sleep_onset_delay_minutes",
  "awakenings_count", "sleep_midpoint_deviation_minutes", "resting_heart_rate_bpm",
  "hrv_rmssd_ms", "reaction_time_median_ms", "reaction_time_lapses_count",
  "attention_accuracy_pct", "self_report_stress_score", "self_report_fatigue_score",
  "self_report_mood_score", "workload_hours", "exercise_minutes",
  "baseline_sleep_duration_hours", "baseline_resting_heart_rate_bpm",
  "baseline_hrv_rmssd_ms", "baseline_reaction_time_median_ms",
  "prior_3day_mean_sleep_hours", "prior_3day_mean_resting_heart_rate_bpm",
  "prior_3day_mean_reaction_time_ms",
] as const;
const OPTIONAL_FIELDS = ["journal_text", "participant_id", "observation_timestamp_utc"];

export class ModelClientError extends Error {
  readonly kind: "input" | "validation" | "unavailable" | "timeout" | "network" | "protocol" | "http";
  readonly status: number | undefined;
  constructor(kind: ModelClientError["kind"], message: string, status?: number) {
    super(message);
    this.name = "ModelClientError";
    this.kind = kind;
    this.status = status;
  }
}

function validateRequest(input: ModelFeatures): void {
  if (!input || typeof input !== "object" || Array.isArray(input)) {
    throw new ModelClientError("input", "Model input must be an object.");
  }
  const record = input as unknown as Record<string, unknown>;
  const allowed = new Set<string>([...REQUIRED_NUMERIC_FIELDS, ...OPTIONAL_FIELDS]);
  if (Object.keys(record).some((key) => !allowed.has(key))) {
    throw new ModelClientError("input", "Unexpected input field; labels, targets and derived features are not model inputs.");
  }
  for (const key of REQUIRED_NUMERIC_FIELDS) {
    if (typeof record[key] !== "number" || !Number.isFinite(record[key])) {
      throw new ModelClientError("input", `A finite numeric value is required for ${key}.`);
    }
  }
  for (const key of ["awakenings_count", "reaction_time_lapses_count"] as const) {
    if (!Number.isInteger(input[key])) {
      throw new ModelClientError("input", `${key} must be an integer.`);
    }
  }
  for (const key of OPTIONAL_FIELDS) {
    if (record[key] != null && typeof record[key] !== "string") {
      throw new ModelClientError("input", `${key} must be text or null.`);
    }
  }
  // Semantic ranges, units, timezone and sleep-consistency rules are owned by
  // the model service's single documented feature contract, not duplicated here.
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function validateResponse(value: unknown): asserts value is Prediction {
  // Validate the summary fields used by the route adapter and the scope flags.
  // Full output typing tracks OpenAPI; this is not a full runtime JSON-schema validator.
  if (!isRecord(value) || !["low", "moderate", "high"].includes(String(value.label)) ||
      typeof value.points !== "number" || !Number.isFinite(value.points) || value.points < 0 || value.points > 100 ||
      value.clinical_validation !== false || value.data_origin !== "synthetic_training_data" ||
      value.forecast_horizon_hours !== 24 || !Array.isArray(value.reasons) || value.reasons.length !== 3) {
    throw new ModelClientError("protocol", "The model service returned an incompatible prediction response.");
  }
  for (const reason of value.reasons) {
    if (!isRecord(reason) || typeof reason.feature !== "string" || typeof reason.reason !== "string" ||
        typeof reason.value !== "number" || !Number.isFinite(reason.value) ||
        typeof reason.shap_value !== "number" || !Number.isFinite(reason.shap_value) ||
        !["supports_prediction", "opposes_prediction", "neutral"].includes(String(reason.direction))) {
      throw new ModelClientError("protocol", "The model service returned invalid SHAP summary reasons.");
    }
  }
}

export class AstraShieldModelClient {
  private readonly predictionUrl: URL;
  private readonly timeoutMs: number;
  private readonly fetchImpl: typeof fetch;

  constructor(baseUrl: string, options: { timeoutMs?: number; fetchImpl?: typeof fetch } = {}) {
    const url = new URL(baseUrl);
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
      throw new ModelClientError("input", "Use a configured HTTP(S) model-service URL without credentials, query or fragment.");
    }
    if (!url.pathname.endsWith("/")) url.pathname += "/";
    this.predictionUrl = new URL("v1/predict", url);
    this.timeoutMs = options.timeoutMs ?? 10_000;
    if (!Number.isInteger(this.timeoutMs) || this.timeoutMs < 1 || this.timeoutMs > 120_000) {
      throw new ModelClientError("input", "timeoutMs must be an integer from 1 to 120000.");
    }
    this.fetchImpl = options.fetchImpl ?? fetch;
  }

  async predict(features: ModelFeatures): Promise<Prediction> {
    validateRequest(features);
    try {
      const response = await this.fetchImpl(this.predictionUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Accept": "application/json" },
        body: JSON.stringify(features),
        signal: AbortSignal.timeout(this.timeoutMs),
      });
      if (!response.ok) {
        if (response.status === 422) {
          throw new ModelClientError("validation", "The model service rejected the measurements or their consistency. Check the documented input contract.", 422);
        }
        if (response.status === 503) {
          throw new ModelClientError("unavailable", "The model artifact is unavailable in the private inference service.", 503);
        }
        throw new ModelClientError("http", `The model service returned HTTP ${response.status}.`, response.status);
      }
      let payload: unknown;
      try { payload = await response.json(); }
      catch { throw new ModelClientError("protocol", "The model service returned invalid JSON."); }
      validateResponse(payload);
      return payload;
    } catch (error) {
      if (error instanceof ModelClientError) throw error;
      if (error instanceof Error && ["TimeoutError", "AbortError"].includes(error.name)) {
        throw new ModelClientError("timeout", "The model prediction timed out.");
      }
      throw new ModelClientError("network", "Could not reach the configured private model service.");
    }
  }
}
