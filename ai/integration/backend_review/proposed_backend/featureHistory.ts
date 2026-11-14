/** Causal, fixed-daily-cutoff feature preparation for the original model.
 *
 * No synthetic history is invented. The first seven accepted daily records form
 * a fixed calibration window. Prediction begins on record eight, using only
 * earlier records. Python calculates the four deltas from these 22 raw inputs.
 */

export const CURRENT_FIELDS = [
  "sleep_duration_hours", "sleep_efficiency_pct", "sleep_onset_delay_minutes",
  "awakenings_count", "sleep_midpoint_deviation_minutes", "resting_heart_rate_bpm",
  "hrv_rmssd_ms", "reaction_time_median_ms", "reaction_time_lapses_count",
  "attention_accuracy_pct", "self_report_stress_score", "self_report_fatigue_score",
  "self_report_mood_score", "workload_hours", "exercise_minutes",
] as const;

export type CurrentField = typeof CURRENT_FIELDS[number];
export type CurrentMeasurement = Record<CurrentField, number>;
export type CurrentObservation = CurrentMeasurement & {
  astronaut_id: string;
  observation_timestamp_utc: string;
  journal_text?: string | null;
};
export type HistoryRecord = { observation: CurrentObservation };
export type CalibrationFeatures = {
  baseline_sleep_duration_hours: number;
  baseline_resting_heart_rate_bpm: number;
  baseline_hrv_rmssd_ms: number;
  baseline_reaction_time_median_ms: number;
};
export type ModelFeatures = CurrentMeasurement & CalibrationFeatures & {
  prior_3day_mean_sleep_hours: number;
  prior_3day_mean_resting_heart_rate_bpm: number;
  prior_3day_mean_reaction_time_ms: number;
  participant_id: string;
  observation_timestamp_utc: string;
  journal_text?: string | null;
};
export type AssessmentPreparation = {
  ready: boolean;
  status: "collecting_baseline" | "ready";
  calibrationCount: number;
  calibrationComplete: boolean;
  calibrationVersion: "fixed-initial-7-daily-v1";
  baseline: CalibrationFeatures | null;
  features: ModelFeatures | null;
  calibrationTimestamps: string[];
};

export class FeatureHistoryError extends Error {
  readonly status: 422 | 409;
  readonly code: string;
  readonly details: Record<string, unknown>;

  constructor(status: 422 | 409, code: string, message: string,
              details: Record<string, unknown> = {}) {
    super(message);
    this.name = "FeatureHistoryError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

// Broad engineering validity bounds exactly match Python features.BOUNDS for
// current observations. They are not diagnostic or operational thresholds.
const BOUNDS: Record<CurrentField, readonly [number, number]> = {
  sleep_duration_hours: [0.1, 16], sleep_efficiency_pct: [10, 100],
  sleep_onset_delay_minutes: [0, 300], awakenings_count: [0, 100],
  sleep_midpoint_deviation_minutes: [-720, 720],
  resting_heart_rate_bpm: [30, 220], hrv_rmssd_ms: [1, 300],
  reaction_time_median_ms: [100, 2000], reaction_time_lapses_count: [0, 60],
  attention_accuracy_pct: [0, 100], self_report_stress_score: [0, 10],
  self_report_fatigue_score: [0, 10], self_report_mood_score: [0, 10],
  workload_hours: [0, 24], exercise_minutes: [0, 480],
};
const ALLOWED = new Set<string>([...CURRENT_FIELDS, "astronaut_id", "observation_timestamp_utc", "journal_text"]);
const RESERVED_IDS = new Set([...Object.getOwnPropertyNames(Object.prototype), "prototype"]
  .map(value => value.toLowerCase()));
const DAY_MS = 24 * 60 * 60 * 1000;

function objectBody(value: unknown): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new FeatureHistoryError(422, "invalid_observation", "Observation must be a JSON object.");
  }
  const prototype = Object.getPrototypeOf(value);
  if (prototype !== Object.prototype && prototype !== null) {
    throw new FeatureHistoryError(422, "invalid_observation", "Observation must be a plain JSON object.");
  }
  return value as Record<string, unknown>;
}

/** Strict ISO timestamp with an explicit timezone and millisecond precision.
 * Inputs using nonzero microseconds are rejected rather than silently rounded.
 */
function normalizedTimestamp(value: unknown): string {
  if (typeof value !== "string") {
    throw new FeatureHistoryError(422, "invalid_timestamp", "observation_timestamp_utc must be an ISO timestamp with a timezone.");
  }
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,3}))?(Z|[+-]\d{2}:\d{2})$/.exec(value);
  if (!match) {
    throw new FeatureHistoryError(422, "invalid_timestamp", "Use ISO 8601 with seconds, explicit Z or ±HH:MM timezone, and at most three fractional digits.");
  }
  const year = Number(match[1]), month = Number(match[2]), day = Number(match[3]);
  const hour = Number(match[4]), minute = Number(match[5]), second = Number(match[6]);
  const offset = match[8]!;
  const calendar = new Date(0);
  calendar.setUTCFullYear(year, month - 1, day);
  calendar.setUTCHours(hour, minute, second, 0);
  if (year < 1 || month < 1 || month > 12 || day < 1 || hour > 23 || minute > 59 || second > 59
      || calendar.getUTCFullYear() !== year || calendar.getUTCMonth() !== month - 1
      || calendar.getUTCDate() !== day
      || (offset !== "Z" && (Number(offset.slice(1, 3)) > 23 || Number(offset.slice(4, 6)) > 59))) {
    throw new FeatureHistoryError(422, "invalid_timestamp", "Timestamp contains an invalid calendar date, time or timezone offset.");
  }
  const milliseconds = Date.parse(value);
  if (!Number.isFinite(milliseconds)) {
    throw new FeatureHistoryError(422, "invalid_timestamp", "Timestamp cannot be parsed.");
  }
  return new Date(milliseconds).toISOString();
}

export function validateCurrentObservation(body: unknown): CurrentObservation {
  const source = objectBody(body);
  const unknown = [...Object.keys(source).filter(key => !ALLOWED.has(key)),
    ...Object.getOwnPropertySymbols(source).map(String)];
  if (unknown.length) {
    throw new FeatureHistoryError(422, "unknown_fields", "Only canonical current measurements are accepted; legacy names, targets and derived features are not inputs.", { fields: unknown });
  }
  const id = source.astronaut_id;
  if (typeof id !== "string" || !/^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(id)
      || RESERVED_IDS.has(id.toLowerCase())) {
    throw new FeatureHistoryError(422, "invalid_astronaut_id", "astronaut_id must be 1–64 safe letters/digits/underscores/hyphens, start with a letter or digit, and not be a reserved key.");
  }
  const timestamp = normalizedTimestamp(source.observation_timestamp_utc);
  const measurements = {} as CurrentMeasurement;
  for (const field of CURRENT_FIELDS) {
    const value = source[field];
    const [minimum, maximum] = BOUNDS[field];
    if (typeof value !== "number" || !Number.isFinite(value) || value < minimum || value > maximum) {
      throw new FeatureHistoryError(422, "invalid_measurement", `${field} must be a finite number between ${minimum} and ${maximum}. These are input bounds, not medical thresholds.`, { field, minimum, maximum });
    }
    if ((field === "awakenings_count" || field === "reaction_time_lapses_count") && !Number.isInteger(value)) {
      throw new FeatureHistoryError(422, "invalid_count", `${field} must be a whole count.`, { field });
    }
    measurements[field] = value;
  }
  const journal = source.journal_text;
  if (journal !== undefined && journal !== null && (typeof journal !== "string" || [...journal].length > 5000)) {
    throw new FeatureHistoryError(422, "invalid_journal", "journal_text must be text of at most 5000 characters or null.");
  }
  const opportunity = measurements.sleep_duration_hours / (measurements.sleep_efficiency_pct / 100);
  const awakeMinutes = 60 * (opportunity - measurements.sleep_duration_hours);
  if (measurements.sleep_onset_delay_minutes > awakeMinutes + 0.1) {
    throw new FeatureHistoryError(422, "inconsistent_sleep", "Sleep onset delay exceeds awake time implied by sleep duration and efficiency.");
  }
  if (opportunity + measurements.workload_hours + measurements.exercise_minutes / 60 > 24.01) {
    throw new FeatureHistoryError(422, "inconsistent_daily_budget", "Non-overlapping sleep opportunity, duty and exercise exceed the 24-hour recording window.");
  }
  const result: CurrentObservation = { astronaut_id: id, observation_timestamp_utc: timestamp, ...measurements };
  if (journal !== undefined) result.journal_text = journal as string | null;
  return result;
}

function stableSum(values: number[]): number {
  // Compensated positive-measurement summation follows Python 3.12's high/low
  // strategy and avoids unnecessary float-order differences before rounding.
  let high = 0, low = 0;
  for (const value of values) {
    const total = high + value;
    low += Math.abs(high) >= Math.abs(value) ? (high - total) + value : (value - total) + high;
    high = total;
  }
  return high + low;
}

function round6(value: number): number {
  // Round the exact IEEE-754 value to six decimal places, ties to even, matching
  // Python round(value, 6). Math.round/toFixed use different tie conventions.
  if (value === 0) return value;
  const bytes = new DataView(new ArrayBuffer(8));
  bytes.setFloat64(0, Math.abs(value), false);
  const bits = bytes.getBigUint64(0, false);
  const exponent = Number((bits >> 52n) & 0x7ffn);
  const fraction = bits & ((1n << 52n) - 1n);
  const mantissa = exponent === 0 ? fraction : fraction | (1n << 52n);
  const shift = exponent === 0 ? -1074 : exponent - 1023 - 52;
  let numerator = mantissa * 1000000n;
  let denominator = 1n;
  if (shift >= 0) numerator <<= BigInt(shift);
  else denominator <<= BigInt(-shift);
  let quotient = numerator / denominator;
  const remainder = numerator % denominator;
  if (2n * remainder > denominator || (2n * remainder === denominator && quotient % 2n === 1n)) quotient += 1n;
  return (value < 0 ? -1 : 1) * Number(quotient) / 1_000_000;
}

function mean(records: CurrentObservation[], field: CurrentField): number {
  return round6(stableSum(records.map(record => record[field])) / records.length);
}

function baselineFor(records: CurrentObservation[]): CalibrationFeatures {
  return {
    baseline_sleep_duration_hours: mean(records, "sleep_duration_hours"),
    baseline_resting_heart_rate_bpm: mean(records, "resting_heart_rate_bpm"),
    baseline_hrv_rmssd_ms: mean(records, "hrv_rmssd_ms"),
    baseline_reaction_time_median_ms: mean(records, "reaction_time_median_ms"),
  };
}

export function prepareAssessment(current: CurrentObservation, history: HistoryRecord[]): AssessmentPreparation {
  const observation = validateCurrentObservation(current);
  if (!Array.isArray(history)) {
    throw new FeatureHistoryError(409, "invalid_history", "History must contain every previously accepted daily observation.");
  }
  const earlier = history.map((record, index) => {
    try {
      if (!record || typeof record !== "object" || !("observation" in record)) {
        throw new Error("History record has no observation.");
      }
      return validateCurrentObservation(record.observation);
    } catch (error) {
      throw new FeatureHistoryError(409, "invalid_history", "A stored historical observation is invalid; no values were filled or replaced.", { index, reason: error instanceof Error ? error.message : String(error) });
    }
  });
  const currentTime = Date.parse(observation.observation_timestamp_utc);
  for (let index = 0; index < earlier.length; index += 1) {
    const record = earlier[index]!;
    if (record.astronaut_id !== observation.astronaut_id) {
      throw new FeatureHistoryError(409, "history_person_mismatch", "All calibration and history records must belong to the current astronaut.", { index });
    }
    const timestamp = Date.parse(record.observation_timestamp_utc);
    if (timestamp >= currentTime) {
      throw new FeatureHistoryError(409, timestamp === currentTime ? "duplicate_observation" : "future_history", "History must strictly precede the current observation; duplicates and future records are rejected.", { index });
    }
    if (index > 0) {
      const difference = timestamp - Date.parse(earlier[index - 1]!.observation_timestamp_utc);
      if (difference <= 0) {
        throw new FeatureHistoryError(409, difference === 0 ? "duplicate_history" : "out_of_order_history", "Stored history must be chronological, without duplicate timestamps.", { index });
      }
      if (difference !== DAY_MS) {
        throw new FeatureHistoryError(409, "history_gap", "This prototype requires exactly one observation at each 24-hour daily cutoff; missing or irregular intervals cannot be filled automatically.", { index });
      }
    }
  }
  if (earlier.length > 0 && currentTime - Date.parse(earlier[earlier.length - 1]!.observation_timestamp_utc) !== DAY_MS) {
    throw new FeatureHistoryError(409, "current_cutoff_gap", "Current observation must be exactly 24 hours after the latest accepted record; no history or baseline was silently changed.");
  }
  const ready = earlier.length >= 7;
  const calibration = ready ? earlier.slice(0, 7) : [...earlier, observation];
  const baseline = calibration.length === 7 ? baselineFor(calibration) : null;
  const result: AssessmentPreparation = {
    ready, status: ready ? "ready" : "collecting_baseline",
    calibrationCount: calibration.length, calibrationComplete: calibration.length === 7,
    calibrationVersion: "fixed-initial-7-daily-v1", baseline, features: null,
    calibrationTimestamps: calibration.map(record => record.observation_timestamp_utc),
  };
  if (!ready || baseline === null) return result;
  const recent = earlier.slice(-3);
  const measurements = Object.fromEntries(CURRENT_FIELDS.map(field => [field, observation[field]])) as CurrentMeasurement;
  const features: ModelFeatures = {
    ...measurements, ...baseline,
    prior_3day_mean_sleep_hours: mean(recent, "sleep_duration_hours"),
    prior_3day_mean_resting_heart_rate_bpm: mean(recent, "resting_heart_rate_bpm"),
    prior_3day_mean_reaction_time_ms: mean(recent, "reaction_time_median_ms"),
    participant_id: observation.astronaut_id,
    observation_timestamp_utc: observation.observation_timestamp_utc,
  };
  if (observation.journal_text !== undefined) features.journal_text = observation.journal_text;
  result.features = features;
  return result;
}

// Aliases preserve the naming used in the initial integration sketch.
export { FeatureHistoryError as InputError };
export const validateObservation = validateCurrentObservation;
