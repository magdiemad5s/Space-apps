import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  CURRENT_FIELDS, FeatureHistoryError, prepareAssessment, validateCurrentObservation,
} from "./featureHistory.ts";
import type { CurrentObservation, HistoryRecord } from "./featureHistory.ts";

function observation(day: number, overrides: Record<string, unknown> = {}): CurrentObservation {
  return validateCurrentObservation({
    astronaut_id: "ASTRA_001",
    observation_timestamp_utc: new Date(Date.UTC(2026, 0, day, 18)).toISOString(),
    sleep_duration_hours: 7 + (day % 3) / 10,
    sleep_efficiency_pct: 90,
    sleep_onset_delay_minutes: 15,
    awakenings_count: 1,
    sleep_midpoint_deviation_minutes: 0,
    resting_heart_rate_bpm: 60 + day / 10,
    hrv_rmssd_ms: 50 + day,
    reaction_time_median_ms: 300 + day,
    reaction_time_lapses_count: 2,
    attention_accuracy_pct: 95,
    self_report_stress_score: 3,
    self_report_fatigue_score: 3,
    self_report_mood_score: 7,
    workload_hours: 8,
    exercise_minutes: 30,
    journal_text: "Routine tasks felt manageable.",
    ...overrides,
  });
}

function history(days: number): HistoryRecord[] {
  return Array.from({ length: days }, (_, i) => ({ observation: observation(i + 1) }));
}

function rejects(action: () => unknown, status: 422 | 409, code?: string): void {
  assert.throws(action, (error: unknown) => error instanceof FeatureHistoryError
    && error.status === status && (code === undefined || error.code === code));
}

test("canonical fields validate and explicit offsets normalize to UTC", () => {
  const value = observation(1, { observation_timestamp_utc: "2026-01-01T21:00:00+03:00" });
  assert.equal(CURRENT_FIELDS.length, 15);
  assert.equal(value.observation_timestamp_utc, "2026-01-01T18:00:00.000Z");
  assert.equal(value.astronaut_id, "ASTRA_001");
});

test("non-object bodies, non-numbers, NaN/infinity, and missing values are rejected", () => {
  for (const body of [null, [], "text", new Date()]) rejects(() => validateCurrentObservation(body), 422);
  for (const bad of [NaN, Infinity, -Infinity, null, "70", true, undefined]) {
    rejects(() => observation(1, { resting_heart_rate_bpm: bad }), 422, "invalid_measurement");
  }
  const body = { ...observation(1) } as Record<string, unknown>;
  delete body.hrv_rmssd_ms;
  rejects(() => validateCurrentObservation(body), 422, "invalid_measurement");
});

test("all current numerical API bounds match the Python contract", () => {
  const lowHigh: Record<string, [number, number]> = {
    sleep_duration_hours: [.1, 16], sleep_efficiency_pct: [10, 100],
    sleep_onset_delay_minutes: [0, 300], awakenings_count: [0, 100],
    sleep_midpoint_deviation_minutes: [-720, 720], resting_heart_rate_bpm: [30, 220],
    hrv_rmssd_ms: [1, 300], reaction_time_median_ms: [100, 2000],
    reaction_time_lapses_count: [0, 60], attention_accuracy_pct: [0, 100],
    self_report_stress_score: [0, 10], self_report_fatigue_score: [0, 10],
    self_report_mood_score: [0, 10], workload_hours: [0, 24], exercise_minutes: [0, 480],
  };
  for (const [name, [low, high]] of Object.entries(lowHigh)) {
    rejects(() => observation(1, { [name]: low - .01 }), 422, "invalid_measurement");
    rejects(() => observation(1, { [name]: high + .01 }), 422, "invalid_measurement");
  }
  rejects(() => observation(1, { awakenings_count: 1.5 }), 422, "invalid_count");
  rejects(() => observation(1, { reaction_time_lapses_count: 2.5 }), 422, "invalid_count");
});

test("targets, derived features, legacy PVT and nested schemas are not silently mapped", () => {
  for (const field of ["PVT_speed_seconds", "fatigue_risk_label_v3", "target_next_day_fatigue_class",
    "baseline_hrv_rmssd_ms", "heart_rate_delta_from_baseline_bpm", "metrics", "heart_rate", "participant_id"]) {
    rejects(() => observation(1, { [field]: 1 }), 422, "unknown_fields");
  }
});

test("identifiers reject reserved keys and path-like or oversized values", () => {
  for (const id of ["constructor", "prototype", "__proto__", "toString", "../x", "A/B", "A B", "A".repeat(65), ""]) {
    rejects(() => observation(1, { astronaut_id: id }), 422, "invalid_astronaut_id");
  }
  assert.equal(observation(1, { astronaut_id: "A".repeat(64) }).astronaut_id.length, 64);
  const protoKey = JSON.parse(JSON.stringify(observation(1)).replace(/}$/, ',"__proto__":{}}'));
  rejects(() => validateCurrentObservation(protoKey), 422, "unknown_fields");
});

test("timestamps require timezone, real dates, regular clock and supported precision", () => {
  for (const timestamp of ["2026-01-01T18:00:00", "2026-02-30T18:00:00Z", "2025-02-29T18:00:00Z",
    "2026-01-01T24:00:00Z", "2026-01-01T18:60:00Z", "2026-01-01T18:00:00+24:00",
    "2026-01-01T18:00:00.123456Z", "tomorrow"]) {
    rejects(() => observation(1, { observation_timestamp_utc: timestamp }), 422, "invalid_timestamp");
  }
  assert.equal(observation(1, { observation_timestamp_utc: "2024-02-29T18:00:00.123Z" }).observation_timestamp_utc,
    "2024-02-29T18:00:00.123Z");
});

test("sleep opportunity and non-overlapping daily time budget are checked", () => {
  rejects(() => observation(1, { sleep_efficiency_pct: 100, sleep_onset_delay_minutes: 15 }), 422, "inconsistent_sleep");
  rejects(() => observation(1, { workload_hours: 20 }), 422, "inconsistent_daily_budget");
});

test("optional journals allow null but reject invalid or oversized values", () => {
  assert.equal(observation(1, { journal_text: null }).journal_text, null);
  assert.equal(observation(1, { journal_text: "🚀".repeat(3000) }).journal_text, "🚀".repeat(3000));
  rejects(() => observation(1, { journal_text: 5 }), 422, "invalid_journal");
  rejects(() => observation(1, { journal_text: "x".repeat(5001) }), 422, "invalid_journal");
});

test("first six records collect baseline; seventh completes it but does not predict", () => {
  for (let day = 1; day <= 7; day += 1) {
    const prepared = prepareAssessment(observation(day), history(day - 1));
    assert.equal(prepared.ready, false);
    assert.equal(prepared.status, "collecting_baseline");
    assert.equal(prepared.calibrationCount, day);
    assert.equal(prepared.calibrationComplete, day === 7);
    assert.equal(prepared.features, null);
    assert.equal(prepared.baseline === null, day < 7);
  }
});

test("eighth record uses fixed earlier seven and previous three only", () => {
  const prepared = prepareAssessment(observation(8), history(7));
  assert.equal(prepared.ready, true);
  assert.equal(prepared.calibrationCount, 7);
  assert.equal(prepared.calibrationTimestamps.length, 7);
  assert.equal(prepared.baseline?.baseline_resting_heart_rate_bpm, 60.4);
  assert.equal(prepared.features?.prior_3day_mean_resting_heart_rate_bpm, 60.6);
  assert.equal(prepared.features?.participant_id, "ASTRA_001");
  assert.equal(Object.keys(prepared.features ?? {}).filter(key => typeof (prepared.features as Record<string, unknown>)[key] === "number").length, 22);
  assert.equal("heart_rate_delta_from_baseline_bpm" in (prepared.features ?? {}), false);
});

test("calibration remains immutable after warm-up and current values never enter means", () => {
  const earlier = history(7);
  const normal = prepareAssessment(observation(8), earlier);
  const extreme = prepareAssessment(observation(8, { resting_heart_rate_bpm: 200, hrv_rmssd_ms: 290 }), earlier);
  assert.deepEqual(normal.baseline, extreme.baseline);
  assert.equal(normal.features?.prior_3day_mean_resting_heart_rate_bpm,
    extreme.features?.prior_3day_mean_resting_heart_rate_bpm);
  const ninth = prepareAssessment(observation(9), [...earlier,
    { observation: observation(8, { resting_heart_rate_bpm: 200 }) }]);
  assert.deepEqual(ninth.baseline, normal.baseline);
  assert.deepEqual(ninth.calibrationTimestamps, normal.calibrationTimestamps);
  assert.notEqual(ninth.features?.prior_3day_mean_resting_heart_rate_bpm,
    normal.features?.prior_3day_mean_resting_heart_rate_bpm);
});

test("history rejects duplicate, stale, out-of-order, future and other-person records", () => {
  rejects(() => prepareAssessment(observation(8), [...history(6), { observation: observation(6) }]), 409, "duplicate_history");
  rejects(() => prepareAssessment(observation(8), [{ observation: observation(2) }, { observation: observation(1) }]), 409, "out_of_order_history");
  rejects(() => prepareAssessment(observation(8), [...history(7), { observation: observation(8) }]), 409, "duplicate_observation");
  rejects(() => prepareAssessment(observation(8), [...history(7), { observation: observation(9) }]), 409, "future_history");
  rejects(() => prepareAssessment(observation(6), history(7)), 409);
  rejects(() => prepareAssessment(observation(8), [{ observation: observation(1, { astronaut_id: "OTHER" }) }]), 409, "history_person_mismatch");
});

test("missing or irregular daily cutoffs are rejected rather than filled", () => {
  rejects(() => prepareAssessment(observation(4), [{ observation: observation(1) }, { observation: observation(3) }]), 409, "history_gap");
  rejects(() => prepareAssessment(observation(9), history(7)), 409, "current_cutoff_gap");
  rejects(() => prepareAssessment(observation(2, { observation_timestamp_utc: "2026-01-02T19:00:00Z" }), history(1)), 409, "current_cutoff_gap");
});

test("normalized timezone-equivalent timestamps are detected as duplicates", () => {
  rejects(() => prepareAssessment(observation(3), [
    { observation: observation(1) },
    { observation: observation(1, { observation_timestamp_utc: "2026-01-01T21:00:00+03:00" }) },
  ]), 409, "duplicate_history");
});

test("preparation is pure and tolerates frozen input records", () => {
  const earlier = history(7);
  for (const record of earlier) { Object.freeze(record.observation); Object.freeze(record); }
  Object.freeze(earlier);
  const current = observation(8);
  Object.freeze(current);
  const before = JSON.stringify({ current, earlier });
  const result = prepareAssessment(current, earlier);
  assert.equal(result.ready, true);
  assert.equal(JSON.stringify({ current, earlier }), before);
});

test("22 model inputs match the saved Python reference from TRAIN calibration fixtures", () => {
  // These portable fixtures were produced by the existing Python helper using
  // training participant SIM_001's calibration records. No local Python install
  // or original training CSV is required to run the backend's unit tests.
  const raw = JSON.parse(readFileSync(new URL("./examples/synthetic_daily_sequence.json", import.meta.url), "utf8")) as unknown[];
  const expected = JSON.parse(readFileSync(new URL("./examples/expected_model_request_day8.json", import.meta.url), "utf8"));
  expected.observation_timestamp_utc = new Date(expected.observation_timestamp_utc).toISOString();
  const observations = raw.map(validateCurrentObservation);
  const prepared = prepareAssessment(observations[7]!, observations.slice(0, 7).map(observation => ({ observation })));
  assert.equal(prepared.ready, true);
  assert.deepEqual(prepared.features, expected);
});
