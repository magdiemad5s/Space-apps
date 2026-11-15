import assert from "node:assert/strict";
import test from "node:test";
import { createFlankerPlan, scoreFlankerSession, PROTOCOL_ID, PROTOCOL_VERSION } from "./flanker.ts";
import type { FlankerPlan, FlankerSession } from "./flanker.ts";

function rng(seed: number) { return () => { seed = (Math.imul(1664525, seed) + 1013904223) >>> 0; return seed / 4294967296; }; }
function complete(plan: FlankerPlan): FlankerSession {
  let now = 100;
  const trials = plan.trials.map(trial => {
    const onset = now; now += 600;
    return { trial_id: trial.trial_id, stimulus_onset_ms: onset,
      trial_end_ms: onset + 500, deadline_at_ms: onset + 3000,
      rendered_stimulus: trial.stimulus,
      response: { direction: trial.correct_response, at_ms: onset + 400 } };
  });
  return { protocol_id: PROTOCOL_ID, protocol_version: PROTOCOL_VERSION,
    session_id: plan.session_id, status: "completed", clock_source: "performance.now",
    time_origin_epoch_ms: 1760000000000, started_at_ms: 50, ended_at_ms: now,
    assessment_reference_ms: now + 10, quality_events: [], trials };
}
const fixture = () => { const plan = createFlankerPlan("demo_001", rng(42)); return { plan, session: complete(plan) }; };

test("plan is balanced40main+4practice and expected center responses are derived", () => {
  const { plan } = fixture();
  assert.equal(plan.trials.length, 44);
  const main = plan.trials.filter(t => t.phase === "main");
  assert.equal(main.filter(t => t.condition === "congruent").length, 20);
  assert.equal(main.filter(t => t.condition === "incongruent").length, 20);
  for (const phase of ["practice", "main"]) for (const condition of ["congruent", "incongruent"]) for (const direction of ["left", "right"]) {
    assert.equal(plan.trials.filter(t => t.phase === phase && t.condition === condition && t.center_direction === direction).length, phase === "practice" ? 1 : 10);
  }
  for (const trial of plan.trials) {
    assert.equal(trial.stimulus.length, 5);
    assert.equal(trial.stimulus[2], trial.correct_response === "left" ? "←" : "→");
  }
  assert.equal(new Set(plan.trials.map(t => t.trial_id)).size, 44);
  assert.ok(Object.isFrozen(plan)); assert.ok(Object.isFrozen(plan.trials));
});

test("FisherYates order is deterministic with injected seed, changes with seed, preserves cells", () => {
  assert.deepEqual(createFlankerPlan("x", rng(7)), createFlankerPlan("x", rng(7)));
  assert.notDeepEqual(createFlankerPlan("x", rng(7)), createFlankerPlan("x", rng(8)));
  for (const bad of [NaN, Infinity, -1, 1, "0.5"]) assert.throws(() => createFlankerPlan("x", () => bad as number), /RNG/);
  assert.throws(() => createFlankerPlan("../x"), /sessionId/);
});

test("allcorrect completed session gives40/40 and exact accuracy/FlankerRT only", () => {
  const { plan, session } = fixture(); const result = scoreFlankerSession(plan, session);
  assert.equal(result.status, "completed_demo");
  assert.equal(result.attention_trials_count, 40); assert.equal(result.attention_correct_count, 40);
  assert.equal(result.attention_accuracy_pct, 100); assert.equal(result.flanker_mean_correct_rt_ms, 400);
  assert.equal(result.flanker_timeout_count, 0); assert.equal(result.flanker_incorrect_response_count, 0);
  assert.equal(result.clinical_validation, false); assert.equal(result.existing_model_compatibility_established, false);
  assert.equal("reaction_time_median_ms" in result, false); assert.equal("PVT_speed_seconds" in result, false);
});

test("practice errors do not reduce40trial score", () => {
  const { plan, session } = fixture();
  for (let i = 0; i < 4; i++) session.trials[i]!.response!.direction = plan.trials[i]!.correct_response === "left" ? "right" : "left";
  const result = scoreFlankerSession(plan, session);
  assert.equal(result.attention_correct_count, 40); assert.equal(result.attention_accuracy_pct, 100);
  assert.equal(result.trial_results.filter(t => t.phase === "practice" && t.status === "incorrect").length, 4);
});

test("wrong key and omission are distinct, both included as incorrect in denominator40", () => {
  const { plan, session } = fixture();
  session.trials[4]!.response!.direction = plan.trials[4]!.correct_response === "left" ? "right" : "left";
  const omission = session.trials.at(-1)!;
  omission.response = null; omission.trial_end_ms = omission.stimulus_onset_ms + 3000;
  session.ended_at_ms = omission.trial_end_ms; session.assessment_reference_ms = session.ended_at_ms;
  const result = scoreFlankerSession(plan, session);
  assert.equal(result.status, "completed_demo"); assert.equal(result.attention_correct_count, 38);
  assert.equal(result.attention_accuracy_pct, 95); assert.equal(result.flanker_incorrect_response_count, 1);
  assert.equal(result.flanker_timeout_count, 1);
});

test("RT0 and2999accepted; RT3000andlater timeout even if directioncorrect", () => {
  for (const [rt, accepted] of [[0, true], [2999, true], [3000, false], [3500, false]] as const) {
    const { plan, session } = fixture(); const row = session.trials.at(-1)!;
    row.response!.at_ms = row.stimulus_onset_ms + rt;
    row.trial_end_ms = row.stimulus_onset_ms + Math.max(rt, 3000);
    session.ended_at_ms = row.trial_end_ms; session.assessment_reference_ms = session.ended_at_ms;
    const result = scoreFlankerSession(plan, session); const scored = result.trial_results.at(-1)!;
    assert.equal(result.status, "completed_demo"); assert.equal(scored.status, accepted ? "correct" : "timeout");
    assert.equal(scored.recorded_response_rt_ms, rt);
    assert.equal(scored.accepted_response_rt_ms, accepted ? rt : null);
    assert.equal(result.attention_correct_count, accepted ? 40 : 39);
  }
});

test("no-response timeout cannot be declared before3000ms", () => {
  const { plan, session } = fixture(); session.trials[5]!.response = null;
  const result = scoreFlankerSession(plan, session);
  assert.equal(result.status, "invalid"); assert.equal(result.attention_accuracy_pct, null);
  assert.match(result.invalid_reasons[0]!, /before.*deadline/);
});

test("completed session rejects missing/extra/duplicate/reordered trial records", () => {
  for (const mutate of [
    (s: FlankerSession) => { s.trials.pop(); },
    (s: FlankerSession) => { s.trials.push(structuredClone(s.trials[0]!)); },
    (s: FlankerSession) => { s.trials[5] = structuredClone(s.trials[4]!); },
    (s: FlankerSession) => { [s.trials[4], s.trials[5]] = [s.trials[5]!, s.trials[4]!]; },
    (s: FlankerSession) => { s.trials.splice(0, 4); },
  ]) {
    const { plan, session } = fixture(); mutate(session);
    const result = scoreFlankerSession(plan, session);
    assert.equal(result.status, "invalid"); assert.equal(result.attention_trials_count, null);
    assert.equal(result.attention_correct_count, null); assert.equal(result.attention_accuracy_pct, null);
  }
});

test("negative/nonfinite/future/overlapping timestamps and inconsistent deadline reject", () => {
  const mutations = [
    (s: FlankerSession) => { s.trials[0]!.response!.at_ms = s.trials[0]!.stimulus_onset_ms - 1; },
    (s: FlankerSession) => { s.trials[0]!.response!.at_ms = NaN; },
    (s: FlankerSession) => { s.trials[0]!.stimulus_onset_ms = Infinity; },
    (s: FlankerSession) => { s.trials[0]!.stimulus_onset_ms = -1; },
    (s: FlankerSession) => { s.trials[0]!.trial_end_ms = s.ended_at_ms + 1; },
    (s: FlankerSession) => { s.trials[0]!.response!.at_ms = s.ended_at_ms + 1; },
    (s: FlankerSession) => { s.assessment_reference_ms = s.ended_at_ms - 1; },
    (s: FlankerSession) => { s.trials[1]!.stimulus_onset_ms = s.trials[0]!.trial_end_ms - 1; },
    (s: FlankerSession) => { s.trials[0]!.deadline_at_ms = s.trials[0]!.stimulus_onset_ms + 2999; },
  ];
  for (const mutate of mutations) {
    const { plan, session } = fixture(); mutate(session);
    const result = scoreFlankerSession(plan, session);
    assert.equal(result.status, "invalid"); assert.equal(result.attention_accuracy_pct, null);
  }
});

test("planned stimulus/response cannot be overridden by submitted correctness labels", () => {
  const { plan, session } = fixture();
  session.trials[4]!.rendered_stimulus = "wrong";
  assert.equal(scoreFlankerSession(plan, session).status, "invalid");
  const fresh = fixture();
  (fresh.session.trials[4] as unknown as Record<string, unknown>).correct = true;
  assert.equal(scoreFlankerSession(fresh.plan, fresh.session).status, "invalid");
  const altered = structuredClone(plan); (altered.trials[4] as { correct_response: string }).correct_response = "not-a-direction";
  assert.equal(scoreFlankerSession(altered, complete(plan)).status, "invalid");
});

test("interrupted, declaredinvalid, visibilityhidden or blurred session cannot emit summary", () => {
  for (const kind of ["interrupted", "invalid", "hidden", "blurred"]) {
    const { plan, session } = fixture();
    if (kind === "interrupted") { session.status = "interrupted"; session.trials = session.trials.slice(0, 12); }
    if (kind === "invalid") session.status = "invalid";
    if (kind === "hidden") session.quality_events.push({ type: "visibility_hidden", at_ms: 600 });
    if (kind === "blurred") session.quality_events.push({ type: "window_blur", at_ms: 600 });
    const result = scoreFlankerSession(plan, session);
    assert.equal(result.status, kind === "interrupted" ? "interrupted" : "invalid");
    for (const key of ["attention_trials_count", "attention_correct_count", "attention_accuracy_pct", "flanker_mean_correct_rt_ms"] as const) assert.equal(result[key], null);
    assert.equal(result.raw_trial_records.length, session.trials.length);
  }
});

test("allwrong valid completion has zeroaccuracy and unknowncorrectRT, not a fabricated0ms", () => {
  const { plan, session } = fixture();
  for (let i = 4; i < 44; i++) session.trials[i]!.response!.direction = plan.trials[i]!.correct_response === "left" ? "right" : "left";
  const result = scoreFlankerSession(plan, session);
  assert.equal(result.status, "completed_demo"); assert.equal(result.attention_accuracy_pct, 0);
  assert.equal(result.flanker_mean_correct_rt_ms, null); assert.equal(result.flanker_median_correct_rt_ms, null);
  assert.equal(result.flanker_incorrect_response_count, 40);
});

test("wrongprotocol/session IDs, missingrecord response and nonfinite origin invalidate", () => {
  for (const mutate of [
    (s: FlankerSession) => { (s as unknown as Record<string, unknown>).protocol_version = "other"; },
    (s: FlankerSession) => { s.session_id = "another"; },
    (s: FlankerSession) => { delete (s.trials[5] as unknown as Record<string, unknown>).response; },
    (s: FlankerSession) => { s.time_origin_epoch_ms = NaN; },
  ]) {
    const { plan, session } = fixture(); mutate(session);
    assert.equal(scoreFlankerSession(plan, session).status, "invalid");
  }
});
