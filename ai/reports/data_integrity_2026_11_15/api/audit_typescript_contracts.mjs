/** Read-only all-row TypeScript contract replay. No model prediction or fitting. */
import assert from "node:assert/strict";
import fs from "node:fs";
import { pathToFileURL } from "node:url";

const [helperPath, inputPath, outputPath] = process.argv.slice(2);
if (!helperPath || !inputPath || !outputPath) throw new Error("Pass helper.ts, input.json and output.json paths.");
const { validateCurrentObservation, prepareAssessment, FeatureHistoryError, CURRENT_FIELDS } = await import(pathToFileURL(helperPath).href);
const fixture = JSON.parse(fs.readFileSync(inputPath, "utf8"));
const result = { status: "passed", model_prediction_or_fit: false, subjects: 0,
  canonical_observations_validated: 0, warmup_observations: 0,
  prediction_ready_feature_rows: 0, numeric_history_values_compared: 0,
  maximum_absolute_numeric_error: 0, unsupported_fields: [],
  invalid_input_cases_rejected: 0, unknown_is_not_zero_checks: 0,
  failures: [] };

try {
  for (const person of fixture.people) {
    result.subjects++;
    const history = [];
    let fixedBaseline = null;
    for (const row of person.rows) {
      const observation = validateCurrentObservation(row.observation);
      result.canonical_observations_validated++;
      const prepared = prepareAssessment(observation, history);
      if (row.expected === null) {
        assert.equal(prepared.ready, false);
        assert.equal(prepared.features, null);
        assert.equal(prepared.calibrationCount, history.length + 1);
        result.warmup_observations++;
      } else {
        assert.equal(prepared.ready, true);
        assert.ok(prepared.features);
        assert.equal(prepared.calibrationCount, 7);
        if (fixedBaseline === null) fixedBaseline = prepared.baseline;
        else assert.deepEqual(prepared.baseline, fixedBaseline);
        for (const key of fixture.numericInputFields) {
          assert.equal(typeof prepared.features[key], "number");
          const error = Math.abs(prepared.features[key] - row.expected[key]);
          result.maximum_absolute_numeric_error = Math.max(result.maximum_absolute_numeric_error, error);
          assert.ok(error <= 1e-6, `${person.id} ${row.day} ${key}: ${error}`);
          result.numeric_history_values_compared++;
        }
        assert.equal(prepared.features.participant_id, person.id);
        assert.equal(Date.parse(prepared.features.observation_timestamp_utc), Date.parse(row.expected.observation_timestamp_utc));
        assert.equal(Object.keys(prepared.features).filter(k => typeof prepared.features[k] === "number").length, 22);
        result.prediction_ready_feature_rows++;
      }
      history.push({ observation });
    }
  }
  const current = fixture.people[0].rows[7].observation;
  const rejected = (payload, code) => {
    assert.throws(() => validateCurrentObservation(payload), e =>
      e instanceof FeatureHistoryError && e.status === 422 && (!code || e.code === code));
  };
  for (const [field, value] of Object.entries(fixture.unsupportedFields)) {
    rejected({ ...current, [field]: value }, "unknown_fields");
    result.unsupported_fields.push({ field, result: "EXPECTED_UNSUPPORTED", status: 422, code: "unknown_fields" });
  }
  for (const key of CURRENT_FIELDS) {
    const missing = { ...current }; delete missing[key];
    rejected(missing); result.invalid_input_cases_rejected++;
    for (const value of [null, "1", true, NaN, Infinity, -Infinity]) {
      rejected({ ...current, [key]: value }); result.invalid_input_cases_rejected++;
    }
  }
  for (const key of ["awakenings_count", "reaction_time_lapses_count"]) {
    rejected({ ...current, [key]: 1.5 }, "invalid_count"); result.invalid_input_cases_rejected++;
    rejected({ ...current, [key]: -1 }); result.invalid_input_cases_rejected++;
    validateCurrentObservation({ ...current, [key]: 0 }); result.unknown_is_not_zero_checks++;
    rejected({ ...current, [key]: null }); result.unknown_is_not_zero_checks++;
  }
  for (const value of [1, 7, 9]) {
    validateCurrentObservation({ ...current, self_report_fatigue_score: value });
  }
  result.custom_scale_limitation = "Custom0to10 accepts numeric1/7/9; this is not KSS/SP semantic equivalence. Named KSS/SP fields remain EXPECTED_UNSUPPORTED.";
  assert.equal(result.subjects, 120);
  assert.equal(result.prediction_ready_feature_rows, 7200);
  assert.equal(result.warmup_observations, 840);
} catch (error) {
  result.status = "failed";
  result.failures.push(error instanceof Error ? error.stack : String(error));
}
fs.writeFileSync(outputPath, JSON.stringify(result, null, 2) + "\n");
console.log(JSON.stringify(result, null, 2));
if (result.status !== "passed") process.exitCode = 1;
