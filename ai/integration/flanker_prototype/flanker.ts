/** Browser-usable Flanker collection/scoring prototype. No Node imports,
 * network calls, trained-model routing or clinical/operational interpretation.
 */
export const PROTOCOL_ID = "astra-flanker-40-demo" as const;
export const PROTOCOL_VERSION = "0.1.0" as const;
export const DEADLINE_MS = 3000 as const;
export type Direction = "left" | "right";
export type Condition = "congruent" | "incongruent";
export type Phase = "practice" | "main";
export interface TrialPlan {
  readonly trial_id: string;
  readonly phase: Phase;
  readonly phase_index: number;
  readonly condition: Condition;
  readonly center_direction: Direction;
  readonly stimulus: string;
  readonly correct_response: Direction;
}
export interface FlankerPlan {
  readonly protocol_id: typeof PROTOCOL_ID;
  readonly protocol_version: typeof PROTOCOL_VERSION;
  readonly session_id: string;
  readonly deadline_ms: typeof DEADLINE_MS;
  readonly practice_trial_count: 4;
  readonly main_trial_count: 40;
  readonly trials: readonly TrialPlan[];
}
export interface TrialRecord {
  trial_id: string;
  stimulus_onset_ms: number;
  trial_end_ms: number;
  /** If recorded, this must equal actual onset + 3000, never a client-selected deadline. */
  deadline_at_ms?: number;
  rendered_stimulus?: string;
  /** First key/tap response only. Ignore keyboard repeats in the UI handler. */
  response: { direction: Direction; at_ms: number; raw_key?: string } | null;
}
export interface FlankerSession {
  protocol_id: typeof PROTOCOL_ID;
  protocol_version: typeof PROTOCOL_VERSION;
  session_id: string;
  status: "completed" | "interrupted" | "invalid";
  clock_source: "performance.now";
  time_origin_epoch_ms: number;
  started_at_ms: number;
  ended_at_ms: number;
  /** Same monotonic clock, sampled when collecting/submitting the finished session. */
  assessment_reference_ms: number;
  quality_events: Array<{ type: "visibility_hidden" | "window_blur"; at_ms: number }>;
  trials: TrialRecord[];
}
export interface TrialScore {
  trial_id: string;
  phase: Phase;
  condition: Condition;
  stimulus: string;
  expected_response: Direction;
  status: "correct" | "incorrect" | "timeout";
  correct: boolean;
  accepted_response: Direction | null;
  /** Recorded late RT remains here even though the response is ignored. */
  recorded_response_rt_ms: number | null;
  accepted_response_rt_ms: number | null;
  derived_deadline_at_ms: number;
}
export interface FlankerResult {
  status: "completed_demo" | "interrupted" | "invalid";
  protocol_id: typeof PROTOCOL_ID;
  protocol_version: typeof PROTOCOL_VERSION;
  session_id: string | null;
  provenance: "prototype_flanker_collection";
  clinical_validation: false;
  existing_model_compatibility_established: false;
  attention_trials_count: 40 | null;
  attention_correct_count: number | null;
  attention_accuracy_pct: number | null;
  flanker_incorrect_response_count: number | null;
  flanker_timeout_count: number | null;
  flanker_mean_correct_rt_ms: number | null;
  flanker_median_correct_rt_ms: number | null;
  flanker_congruent_mean_correct_rt_ms: number | null;
  flanker_incongruent_mean_correct_rt_ms: number | null;
  flanker_interference_correct_rt_ms: number | null;
  invalid_reasons: string[];
  trial_results: TrialScore[];
  raw_trial_records: readonly unknown[];
}

const CONDITIONS: Condition[] = ["congruent", "incongruent"];
const DIRECTIONS: Direction[] = ["left", "right"];
const plain = (v: unknown): v is Record<string, unknown> =>
  v !== null && typeof v === "object" && !Array.isArray(v);
const finiteTime = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v) && v >= 0;
const validId = (v: unknown): v is string => typeof v === "string" && /^[A-Za-z0-9_-]{1,80}$/.test(v);
const stimulusFor = (condition: Condition, center: Direction): string => {
  const middle = center === "left" ? "←" : "→";
  const side = condition === "congruent" ? middle : (middle === "←" ? "→" : "←");
  return side + side + middle + side + side;
};

function shuffled<T>(values: readonly T[], rng: () => number): T[] {
  const result = [...values];
  for (let i = result.length - 1; i > 0; i--) {
    const draw = rng();
    if (typeof draw !== "number" || !Number.isFinite(draw) || draw < 0 || draw >= 1) {
      throw new Error("RNG must return a finite number in [0, 1).");
    }
    const j = Math.floor(draw * (i + 1));
    [result[i], result[j]] = [result[j]!, result[i]!];
  }
  return result;
}

/** Save this original plan before rendering. A future backend must score against
 * its saved plan, not an untrusted plan replaced by the submitting client.
 */
export function createFlankerPlan(sessionId: string, rng: () => number = Math.random): FlankerPlan {
  if (!validId(sessionId)) throw new Error("sessionId must contain 1–80 safe letters/digits/underscores/hyphens.");
  if (typeof rng !== "function") throw new Error("rng must be a function.");
  const cells: Array<{ condition: Condition; center: Direction }> = [];
  for (const condition of CONDITIONS) for (const center of DIRECTIONS) cells.push({ condition, center });
  const practice = shuffled(cells, rng);
  const main = shuffled(cells.flatMap(cell => Array.from({ length: 10 }, () => ({ ...cell }))), rng);
  const make = (rows: typeof cells, phase: Phase) => rows.map((cell, i) => Object.freeze({
    trial_id: `${sessionId}:${phase}:${String(i + 1).padStart(3, "0")}`,
    phase, phase_index: i + 1, condition: cell.condition, center_direction: cell.center,
    stimulus: stimulusFor(cell.condition, cell.center), correct_response: cell.center,
  }));
  return Object.freeze({ protocol_id: PROTOCOL_ID, protocol_version: PROTOCOL_VERSION,
    session_id: sessionId, deadline_ms: DEADLINE_MS, practice_trial_count: 4,
    main_trial_count: 40, trials: Object.freeze([...make(practice, "practice"), ...make(main, "main")]) });
}

function validatePlan(value: unknown): asserts value is FlankerPlan {
  if (!plain(value) || value.protocol_id !== PROTOCOL_ID || value.protocol_version !== PROTOCOL_VERSION ||
      !validId(value.session_id) || value.deadline_ms !== DEADLINE_MS || value.practice_trial_count !== 4 ||
      value.main_trial_count !== 40 || !Array.isArray(value.trials) || value.trials.length !== 44) {
    throw new Error("Saved original plan has an invalid identity, version, deadline or trial count.");
  }
  const counts: Record<string, number> = {};
  for (let index = 0; index < value.trials.length; index++) {
    const row: unknown = value.trials[index];
    const phase: Phase = index < 4 ? "practice" : "main";
    const phaseIndex = phase === "practice" ? index + 1 : index - 3;
    if (!plain(row) || row.phase !== phase || row.phase_index !== phaseIndex ||
        !CONDITIONS.includes(row.condition as Condition) || !DIRECTIONS.includes(row.center_direction as Direction) ||
        row.correct_response !== row.center_direction || row.stimulus !== stimulusFor(row.condition as Condition, row.center_direction as Direction) ||
        row.trial_id !== `${value.session_id}:${phase}:${String(phaseIndex).padStart(3, "0")}`) {
      throw new Error(`Saved plan trial ${index + 1} is inconsistent.`);
    }
    const cell = `${phase}:${row.condition}:${row.center_direction}`;
    counts[cell] = (counts[cell] ?? 0) + 1;
  }
  for (const phase of ["practice", "main"]) for (const condition of CONDITIONS) for (const center of DIRECTIONS) {
    if (counts[`${phase}:${condition}:${center}`] !== (phase === "practice" ? 1 : 10)) {
      throw new Error("Saved plan is not balanced by condition and center direction.");
    }
  }
}

function mean(values: number[]): number | null {
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
}
function median(values: number[]): number | null {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle]! : (sorted[middle - 1]! + sorted[middle]!) / 2;
}

/** Strict complete-session scoring. Interrupted/invalid submissions retain audit
 * records but return null summary fields, never a fabricated forty-trial score.
 */
export function scoreFlankerSession(savedPlan: FlankerPlan, submission: unknown): FlankerResult {
  const raw = plain(submission) && Array.isArray(submission.trials) ? submission.trials : [];
  const result: FlankerResult = {
    status: "invalid", protocol_id: PROTOCOL_ID, protocol_version: PROTOCOL_VERSION,
    session_id: plain(submission) && typeof submission.session_id === "string" ? submission.session_id : null,
    provenance: "prototype_flanker_collection", clinical_validation: false,
    existing_model_compatibility_established: false,
    attention_trials_count: null, attention_correct_count: null, attention_accuracy_pct: null,
    flanker_incorrect_response_count: null, flanker_timeout_count: null,
    flanker_mean_correct_rt_ms: null, flanker_median_correct_rt_ms: null,
    flanker_congruent_mean_correct_rt_ms: null, flanker_incongruent_mean_correct_rt_ms: null,
    flanker_interference_correct_rt_ms: null, invalid_reasons: [], trial_results: [], raw_trial_records: raw,
  };
  try {
    validatePlan(savedPlan);
    if (!plain(submission) || submission.protocol_id !== PROTOCOL_ID || submission.protocol_version !== PROTOCOL_VERSION ||
        submission.session_id !== savedPlan.session_id || submission.clock_source !== "performance.now" ||
        !["completed", "interrupted", "invalid"].includes(String(submission.status))) throw new Error("Session identity, version, clock or declared status is invalid.");
    for (const name of ["time_origin_epoch_ms", "started_at_ms", "ended_at_ms", "assessment_reference_ms"]) {
      if (!finiteTime(submission[name])) throw new Error(`${name} must be finite and nonnegative.`);
    }
    const start = submission.started_at_ms as number;
    const end = submission.ended_at_ms as number;
    const reference = submission.assessment_reference_ms as number;
    if (start > end || end > reference) throw new Error("Session times are out of order or in the future relative to the assessment reference.");
    if (!Array.isArray(submission.quality_events)) throw new Error("quality_events must explicitly record an array, including an empty array when none occurred.");
    for (const event of submission.quality_events) {
      if (!plain(event) || !["visibility_hidden", "window_blur"].includes(String(event.type)) || !finiteTime(event.at_ms) || event.at_ms < start || event.at_ms > reference) {
        throw new Error("Invalid visibility/focus quality event.");
      }
    }
    if (submission.quality_events.length) throw new Error("Visibility loss or window blur invalidates this prototype session; do not resume it as a valid complete test.");
    if (!Array.isArray(submission.trials)) throw new Error("trials must contain actual recorded trial data.");
    if (submission.status === "completed" && submission.trials.length !== 44) throw new Error("A completed protocol requires exactly four practice records followed by forty main records.");
    if (submission.trials.length > 44) throw new Error("Too many trial records.");
    const seen = new Set<string>();
    let previousEnd = start;
    for (let index = 0; index < submission.trials.length; index++) {
      const trial = submission.trials[index];
      const expected = savedPlan.trials[index]!;
      if (!plain(trial) || Object.keys(trial).some(key => !["trial_id", "stimulus_onset_ms", "trial_end_ms", "deadline_at_ms", "rendered_stimulus", "response"].includes(key))) throw new Error(`Trial ${index + 1} has an invalid record shape.`);
      if (typeof trial.trial_id !== "string" || seen.has(trial.trial_id) || trial.trial_id !== expected.trial_id) throw new Error(`Trial ${index + 1} is missing, duplicated, reordered or not in the original plan.`);
      seen.add(trial.trial_id);
      if (!finiteTime(trial.stimulus_onset_ms) || !finiteTime(trial.trial_end_ms) || trial.stimulus_onset_ms < previousEnd ||
          trial.trial_end_ms < trial.stimulus_onset_ms || trial.trial_end_ms > end) throw new Error(`Trial ${index + 1} has negative, overlapping, future or out-of-order times.`);
      const onset = trial.stimulus_onset_ms;
      const deadline = onset + DEADLINE_MS;
      if (trial.deadline_at_ms !== undefined && (!finiteTime(trial.deadline_at_ms) || Math.abs(trial.deadline_at_ms - deadline) > 1e-6)) throw new Error(`Trial ${index + 1} supplied an inconsistent deadline.`);
      if (trial.rendered_stimulus !== undefined && trial.rendered_stimulus !== expected.stimulus) throw new Error(`Trial ${index + 1} rendered stimulus differs from its original plan.`);
      let rt: number | null = null;
      let direction: Direction | null = null;
      if (trial.response !== null) {
        if (!plain(trial.response) || Object.keys(trial.response).some(key => !["direction", "at_ms", "raw_key"].includes(key)) ||
            !DIRECTIONS.includes(trial.response.direction as Direction) || !finiteTime(trial.response.at_ms) ||
            trial.response.at_ms < onset || trial.response.at_ms > trial.trial_end_ms || trial.response.at_ms > reference ||
            (trial.response.raw_key !== undefined && (typeof trial.response.raw_key !== "string" || trial.response.raw_key.length > 80))) throw new Error(`Trial ${index + 1} has an invalid or future response.`);
        rt = trial.response.at_ms - onset;
        direction = trial.response.direction as Direction;
      }
      const timeout = rt === null || rt >= DEADLINE_MS;
      if (timeout && trial.trial_end_ms < deadline) throw new Error(`Trial ${index + 1} claims a timeout before its actual deadline.`);
      const status: TrialScore["status"] = timeout ? "timeout" : direction === expected.correct_response ? "correct" : "incorrect";
      result.trial_results.push({ trial_id: expected.trial_id, phase: expected.phase,
        condition: expected.condition, stimulus: expected.stimulus,
        expected_response: expected.correct_response, status, correct: status === "correct",
        accepted_response: timeout ? null : direction,
        recorded_response_rt_ms: rt, accepted_response_rt_ms: timeout ? null : rt,
        derived_deadline_at_ms: deadline });
      previousEnd = trial.trial_end_ms;
    }
    if (submission.status === "invalid") throw new Error("The collector declared this session invalid.");
    if (submission.status === "interrupted") { result.status = "interrupted"; return result; }
    const main = result.trial_results.filter(trial => trial.phase === "main");
    if (main.length !== 40) throw new Error("Forty main trials are required for a valid summary.");
    const correct = main.filter(trial => trial.correct);
    const correctRts = correct.map(trial => trial.accepted_response_rt_ms!);
    const congruent = correct.filter(trial => trial.condition === "congruent").map(trial => trial.accepted_response_rt_ms!);
    const incongruent = correct.filter(trial => trial.condition === "incongruent").map(trial => trial.accepted_response_rt_ms!);
    const congruentMean = mean(congruent), incongruentMean = mean(incongruent);
    Object.assign(result, { status: "completed_demo", attention_trials_count: 40,
      attention_correct_count: correct.length, attention_accuracy_pct: correct.length / 40 * 100,
      flanker_incorrect_response_count: main.filter(trial => trial.status === "incorrect").length,
      flanker_timeout_count: main.filter(trial => trial.status === "timeout").length,
      flanker_mean_correct_rt_ms: mean(correctRts), flanker_median_correct_rt_ms: median(correctRts),
      flanker_congruent_mean_correct_rt_ms: congruentMean,
      flanker_incongruent_mean_correct_rt_ms: incongruentMean,
      flanker_interference_correct_rt_ms: congruentMean === null || incongruentMean === null ? null : incongruentMean - congruentMean });
  } catch (error) {
    result.status = "invalid";
    result.invalid_reasons.push(error instanceof Error ? error.message : String(error));
  }
  return result;
}
