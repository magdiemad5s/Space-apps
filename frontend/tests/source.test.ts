import assert from 'node:assert/strict';
import { beforeEach, after, test } from 'node:test';
import { readFileSync } from 'node:fs';
import { apiBase, buildBody, getSnapshot, nextCutoff, normalizeApiBase, retryBodyFor, setApiBase, setDemoMode, submitRecord } from '../src/app/data/source.ts';
import { validateCurrentObservation, FeatureHistoryError } from '../../ai/integration/backend_review/proposed_backend/featureHistory.ts';
import { MEASUREMENT_KEYS, type Measurements, type Snapshot } from '../src/app/types.ts';

const examples = new URL('../../ai/integration/backend_review/proposed_backend/examples/', import.meta.url);
const sequence = JSON.parse(readFileSync(new URL('synthetic_daily_sequence.json', examples), 'utf8'));
const completed = JSON.parse(readFileSync(new URL('assessment_response_day8.json', examples), 'utf8'));
const realFetch = globalThis.fetch;
const originalStorage = Object.getOwnPropertyDescriptor(globalThis, 'localStorage');
const memory = new Map<string, string>();
const measurement = Object.fromEntries(MEASUREMENT_KEYS.map(key => [key, sequence[0][key]])) as Measurements;
const empty: Snapshot = { astronautId: 'DEMO_SIM_001', source: 'backend', backend: { online: true, modelReady: true }, records: [], baseline: null, calibrationRequired: 7 };
const health = { status: 'online', ai_service: { configured: true, reachable: true, model_ready: true } };
const response = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
function history(observations = [sequence[7]], assessments = [completed]) {
  return { astronaut_id: 'DEMO_SIM_001', observations, history: assessments, personal_baseline: completed.personal_baseline, calibration_required: 7 };
}
function reads(payload: unknown) {
  globalThis.fetch = (async (url: string | URL | Request) => response(String(url).endsWith('/health') ? health : payload)) as typeof fetch;
}

beforeEach(() => {
  memory.clear();
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
    getItem: (key: string) => memory.get(key) ?? null,
    setItem: (key: string, value: string) => memory.set(key, value),
    removeItem: (key: string) => memory.delete(key),
  } });
});
after(() => {
  globalThis.fetch = realFetch;
  if (originalStorage) Object.defineProperty(globalThis, 'localStorage', originalStorage);
  else delete (globalThis as unknown as Record<string, unknown>)['localStorage'];
});

test('default API uses same-origin proxy; override strips trailing slash', () => {
  assert.equal(apiBase(), '/api/v1');
  setApiBase(' http://localhost:3000/api/v1/// ');
  assert.equal(apiBase(), 'http://localhost:3000/api/v1');
  setApiBase('');
  assert.equal(apiBase(), '/api/v1');
});

test('actual completed response maps next-day class, points, probability and SHAP values', async () => {
  reads(history());
  const actual = await getSnapshot();
  assert.equal(actual.source, 'backend');
  assert.equal(actual.records[0].forecast?.points, completed.fatigue_points);
  assert.equal(actual.records[0].forecast?.category, completed.fatigue_risk_level);
  assert.deepEqual(actual.records[0].forecast?.probabilities, completed.model_result.next_day_forecasts.fatigue.model_class_probabilities);
  assert.equal(actual.records[0].forecast?.reasons[0].shapValue, completed.explanation.top_contributing_factors[0].shap_value);
  assert.equal(actual.records[0].forecast?.targetTimestamp, completed.target_timestamp_utc);
});

test('backend outage never silently returns synthetic records', async () => {
  globalThis.fetch = async () => { throw new Error('offline'); };
  await assert.rejects(getSnapshot(), /Backend unavailable.*No demo data was substituted/);
});

test('history failure never silently returns synthetic records', async () => {
  globalThis.fetch = (async (url: string) => url.endsWith('/health') ? response(health) : response({ error: 'unavailable' }, 503)) as typeof fetch;
  await assert.rejects(getSnapshot(), /Could not read backend history.*No demo data was substituted/);
});

test('explicit demo selection makes no backend or model requests', async () => {
  globalThis.fetch = async () => { throw new Error('must not fetch'); };
  setDemoMode(true);
  const snapshot = await getSnapshot();
  assert.equal(snapshot.source, 'demo');
  assert.equal(snapshot.records.length, 8);
});

test('null score and missing optional physiology remain unavailable, never zero or normal', async () => {
  const item = structuredClone(completed);
  item.fatigue_score = null;
  delete item.model_result.current_observation.physiology;
  reads(history([sequence[7]], [item]));
  const snapshot = await getSnapshot();
  assert.equal(snapshot.records[0].forecast?.score, null);
  assert.equal(snapshot.records[0].forecast?.physiologyOutlier, null);
});

test('range warning objects and neutral SHAP direction map to usable frontend values', async () => {
  const item = structuredClone(completed);
  item.model_result.input_quality.out_of_training_range_features = [{ feature: 'resting_heart_rate_bpm', observed: 150, training_min: 50, training_max: 100 }];
  item.explanation.top_contributing_factors[0].direction = 'neutral';
  reads(history([sequence[7]], [item]));
  const f = (await getSnapshot()).records[0].forecast;
  assert.deepEqual(f?.outOfRangeFeatures, ['resting_heart_rate_bpm']);
  assert.equal(f?.reasons[0].direction, 'neutral');
});

test('invalid numeric history is rejected rather than coercing null into zero', async () => {
  reads(history([{ ...sequence[7], sleep_duration_hours: null }], [completed]));
  await assert.rejects(getSnapshot(), /invalid numeric measurement/);
});

test('misaligned history is rejected', async () => {
  reads(history([sequence[7]], []));
  await assert.rejects(getSnapshot(), /history is malformed/);
});

test('wrong participant history is rejected', async () => {
  reads({ ...history(), astronaut_id: 'OTHER_PERSON' });
  await assert.rejects(getSnapshot(), /different astronaut/);
});

test('forecast numeric strings are not accepted as model results', async () => {
  reads(history([sequence[7]], [{ ...completed, fatigue_points: '33.1' }]));
  await assert.rejects(getSnapshot(), /invalid forecast/);
});

test('loaded outage retry preserves exact journal text, including explicit null versus absent', async () => {
  const outage = { ...completed, status: 'model_unavailable', fatigue_points: null, fatigue_risk_level: null, fatigue_score: null, model_result: null };
  for (const observation of [{ ...sequence[7], journal_text: '  Exact submitted note.  ' }, { ...sequence[7], journal_text: null }, sequence[7]]) {
    reads(history([observation], [outage]));
    const snapshot = await getSnapshot();
    assert.deepEqual(retryBodyFor(snapshot.astronautId, snapshot.records[0]), observation);
  }
});

test('daily body uses canonical fields only and advances the cutoff by exactly24hours', () => {
  const snapshot = { ...empty, records: [{ index: 1, timestamp: '2026-03-28T18:00:00Z', measurements: measurement, status: 'collecting_baseline' as const, forecast: null }] };
  const body = buildBody(snapshot, measurement, '  note  ');
  assert.equal(nextCutoff(snapshot.records), '2026-03-29T18:00:00Z');
  assert.equal(body.journal_text, 'note');
  assert.equal(Object.keys(body).length, 18);
  assert.equal(Date.parse(body.observation_timestamp_utc) - Date.parse(snapshot.records[0].timestamp), 86400000);
});

test('calibration202 save remains real after a failed history refresh', async () => {
  const body = { ...sequence[0], journal_text: 'Original calibration note' };
  globalThis.fetch = (async (_url: string, init?: RequestInit) => {
    if (init?.method === 'POST') return response({ status: 'collecting_baseline', observation_saved: true }, 202);
    throw new Error('refresh unavailable');
  }) as typeof fetch;
  const result = await submitRecord(empty, body);
  assert.equal(result.kind, 'saved');
  if (result.kind !== 'saved') return;
  assert.equal(result.snapshot.source, 'backend');
  assert.equal(result.status, 'collecting_baseline');
  assert.equal(result.snapshot.records.length, 1);
  assert.equal(result.snapshot.records[0].forecast, null);
  assert.match(result.refreshWarning!, /save was confirmed/);
  assert.equal(result.snapshot.records[0].journalText, body.journal_text);
});

test('saved503 outage retry replaces its record and preserves identical body with journal', async () => {
  const body = { ...sequence[7], journal_text: 'A private note' };
  const existing = { ...empty, records: [{ index: 1, timestamp: body.observation_timestamp_utc, measurements: measurement, journalText: body.journal_text, status: 'model_unavailable' as const, forecast: null }] };
  let posted: unknown;
  globalThis.fetch = (async (_url: string, init?: RequestInit) => {
    if (init?.method === 'POST') { posted = JSON.parse(String(init.body)); return response({ ...completed, status: 'model_unavailable', observation_saved: true, model_result: null }, 503); }
    throw new Error('offline');
  }) as typeof fetch;
  const result = await submitRecord(existing, body);
  assert.deepEqual(posted, body);
  assert.equal(result.kind, 'saved');
  if (result.kind !== 'saved') return;
  assert.equal(result.snapshot.records.length, 1);
  assert.equal(result.snapshot.records[0].forecast, null);
  assert.equal(result.snapshot.backend.modelReady, false);
  assert.deepEqual(retryBodyFor(result.snapshot.astronautId, result.snapshot.records[0]), body);
});

test('rejected422 neither adds a record nor claims a save', async () => {
  globalThis.fetch = async () => response({ observation_saved: false, error: 'invalid_measurement', message: 'Invalid input.' }, 422);
  const result = await submitRecord(empty, sequence[0]);
  assert.equal(result.kind, 'rejected');
  assert.equal(empty.records.length, 0);
});

test('transport failure reports unknown save status rather than fabricating a result', async () => {
  globalThis.fetch = async () => { throw new Error('timeout'); };
  const result = await submitRecord(empty, sequence[0]);
  assert.equal(result.kind, 'unreachable');
  assert.equal(empty.records.length, 0);
});


test('a confirmed save with malformed forecast retains its actual observation without invented inference', async () => {
  globalThis.fetch = (async (_url: string, init?: RequestInit) => {
    if (init?.method === 'POST') return response({ ...completed, fatigue_points: 'not a number', observation_saved: true }, 201);
    throw new Error('history unavailable');
  }) as typeof fetch;
  const body = { ...sequence[7], journal_text: 'Keep this acknowledged observation' };
  const result = await submitRecord(empty, body);
  assert.equal(result.kind, 'saved');
  if (result.kind !== 'saved') return;
  assert.equal(result.status, 'completed');
  assert.equal(result.snapshot.source, 'backend');
  assert.equal(result.snapshot.records.length, 1);
  assert.equal(result.snapshot.records[0].forecast, null);
  assert.deepEqual(retryBodyFor(result.snapshot.astronautId, result.snapshot.records[0]), body);
  assert.match(result.refreshWarning!, /forecast was incompatible and has been withheld/);
});


test('a stale empty history response cannot erase an acknowledged save', async () => {
  globalThis.fetch = (async (url: string, init?: RequestInit) => {
    if (init?.method === 'POST') return response({ status: 'collecting_baseline', observation_saved: true }, 202);
    return response(url.endsWith('/health') ? health : history([], []));
  }) as typeof fetch;
  const result = await submitRecord(empty, sequence[0]);
  assert.equal(result.kind, 'saved');
  if (result.kind !== 'saved') return;
  assert.equal(result.snapshot.records.length, 1);
  assert.match(result.refreshWarning!, /save was confirmed/);
});

test('backend settings accept explicit HTTP(S) API URLs and the same-origin route', () => {
  assert.equal(normalizeApiBase(' /api/v1/ '), '/api/v1');
  assert.equal(normalizeApiBase('https://crew.example.test'), 'https://crew.example.test/api/v1');
  assert.equal(normalizeApiBase('HTTP://localhost:3000/api/v1///'), 'http://localhost:3000/api/v1');
  assert.equal(normalizeApiBase('https://crew.example.test/team/api/v1'), 'https://crew.example.test/team/api/v1');
});

test('invalid backend settings do not replace the previous working URL', () => {
  const previous = 'http://localhost:3000/api/v1';
  setApiBase(previous);
  for (const invalid of ['not a valid URL', 'javascript:alert(1)', '//evil.example/api/v1', 'file:///api/v1',
    'https://name:password@example.test/api/v1', 'https://example.test/api/v1?token=secret',
    'https://example.test/api/v1#fragment', 'https://example.test/other', 'https://example.test\\api\\v1']) {
    assert.throws(() => setApiBase(invalid), /http:\/\/ or https:\/\//, invalid);
    assert.equal(apiBase(), previous);
  }
});

test('an invalid setting left in browser storage is rejected before any network request', async () => {
  memory.set('apiBase', 'not a valid URL');
  let requests = 0;
  globalThis.fetch = async () => { requests++; return response(health); };
  await assert.rejects(getSnapshot(), /backend address/);
  assert.equal(requests, 0);
});

test('offline demo rejects invalid measurements and cross-field combinations like the backend', async () => {
  setDemoMode(true);
  globalThis.fetch = async () => { throw new Error('Demo must not make network requests'); };
  const snapshot = await getSnapshot();
  const valid = buildBody(snapshot, measurement);
  const invalidChanges: Record<string, unknown>[] = [
    { sleep_duration_hours: 8, sleep_efficiency_pct: 90, workload_hours: 20 },
    { sleep_duration_hours: 8, sleep_efficiency_pct: 100, sleep_onset_delay_minutes: 5 },
    { awakenings_count: -1 }, { reaction_time_lapses_count: 10.5 }, { self_report_stress_score: null },
    { sleep_duration_hours: 0 }, { exercise_minutes: Number.NaN }, { target_next_day_fatigue: 'high' },
  ];
  for (const change of invalidChanges) {
    const body = { ...valid, ...change };
    let backendError: FeatureHistoryError | undefined;
    try { validateCurrentObservation(body); } catch (error) { backendError = error as FeatureHistoryError; }
    assert.ok(backendError, 'The same body must fail authoritative backend validation.');
    const result = await submitRecord(snapshot, body);
    assert.equal(result.kind, 'rejected');
    if (result.kind !== 'rejected') continue;
    assert.equal(result.error, backendError.code);
    assert.equal(result.httpStatus, 422);
    assert.equal(snapshot.records.length, 8);
  }
});

test('offline demo rejects duplicate/gapped cutoffs and invalid calendar dates', async () => {
  setDemoMode(true);
  const snapshot = await getSnapshot();
  const body = buildBody(snapshot, measurement);
  for (const timestamp of [snapshot.records.at(-1)!.timestamp, '2026-01-05T18:00:00Z']) {
    const result = await submitRecord(snapshot, { ...body, observation_timestamp_utc: timestamp });
    assert.equal(result.kind, 'rejected');
    if (result.kind === 'rejected') assert.equal(result.httpStatus, 409);
  }
  const result = await submitRecord(snapshot, { ...body, observation_timestamp_utc: '2026-02-30T18:00:00Z' });
  assert.equal(result.kind, 'rejected');
  if (result.kind === 'rejected') assert.equal(result.error, 'invalid_timestamp');
  assert.equal(snapshot.records.length, 8);
});

test('valid offline demo records remain session-only, with no fabricated forecast', async () => {
  setDemoMode(true);
  globalThis.fetch = async () => { throw new Error('Demo must not make network requests'); };
  const snapshot = await getSnapshot();
  const result = await submitRecord(snapshot, buildBody(snapshot, measurement, 'Session-only example'));
  assert.equal(result.kind, 'saved');
  if (result.kind !== 'saved') return;
  assert.equal(result.httpStatus, 0);
  assert.equal(result.snapshot.source, 'demo');
  assert.equal(result.snapshot.records.length, 9);
  assert.equal(result.snapshot.records[8].forecast, null);
  assert.equal(result.snapshot.records[8].journalText, 'Session-only example');
  assert.equal(snapshot.records.length, 8);
});
