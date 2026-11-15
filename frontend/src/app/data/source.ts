import type {
  DayRecord,
  FatigueCategory,
  Forecast,
  Measurements,
  PersonalBaseline,
  RecordStatus,
  Reason,
  Snapshot,
} from '../types';
import { MEASUREMENT_KEYS } from '../types';
import { DEMO_ASTRONAUT_ID, DEMO_BASELINE, DEMO_DAY8_ASSESSMENT, DEMO_RECORDS } from './demo-data';

/*
 * The only place where the dashboard talks to data. It follows the contract of the AI team's backend
 * (ai/integration/backend_review/proposed_backend):
 *
 *   GET  /api/v1/health                      backend and model status
 *   GET  /api/v1/astronauts/:id/history      raw observations + assessments + calibration state
 *   POST /api/v1/assess                      one daily record: 15 measurements + astronaut_id + observation cutoff
 *
 * Demo mode is an explicit user choice. A backend failure never replaces live records with simulated data.
 */

/** Same-origin API: the dev proxy or deployed web server forwards this path to the backend. */
const DEFAULT_API_BASE = '/api/v1';
const READ_TIMEOUT_MS = 6000;
/** The backend waits up to 10 s for the model, so a record submission needs longer than a read. */
const SUBMIT_TIMEOUT_MS = 30000;
const CALIBRATION_REQUIRED = 7;
const DAY_MS = 24 * 60 * 60 * 1000;

function stored(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function apiBase(): string {
  return (stored('apiBase') || DEFAULT_API_BASE).replace(/\/+$/, '');
}

/** Saves a new backend address (empty = back to the default) for the next load. */
export function setApiBase(value: string): void {
  try {
    if (value.trim()) localStorage.setItem('apiBase', value.trim().replace(/\/+$/, ''));
    else localStorage.removeItem('apiBase');
  } catch {
    /* storage unavailable: the default stays */
  }
}

export function demoMode(): boolean { return stored('astraDemoMode') === 'true'; }

export function setDemoMode(enabled: boolean): void {
  try {
    if (enabled) localStorage.setItem('astraDemoMode', 'true');
    else localStorage.removeItem('astraDemoMode');
  } catch { /* A reload cannot preserve mode when browser storage is disabled. */ }
}

export class DataSourceError extends Error {
  constructor(message: string) { super(message); this.name = 'DataSourceError'; }
}

/** Who the records belong to. Change with localStorage.setItem('astronautId', 'DEMO_...'). */
export function astronautId(): string {
  return stored('astronautId') || DEMO_ASTRONAUT_ID;
}

// ---- backend response shapes (only the fields the dashboard uses) ----

interface HealthResponse {
  status?: string;
  ai_service?: { configured?: boolean; reachable?: boolean; model_ready?: boolean };
}

interface BackendReason {
  feature: string;
  value: number;
  shap_value: number;
  direction: 'supports_prediction' | 'opposes_prediction' | 'neutral';
}

interface BackendAssessment {
  status: RecordStatus;
  observation_timestamp_utc?: string;
  fatigue_points: number | null;
  fatigue_risk_level: FatigueCategory | null;
  fatigue_score: number | null;
  target_timestamp_utc?: string;
  explanation?: { top_contributing_factors?: BackendReason[] };
  advisory_actions?: string[];
  model_result?: {
    next_day_forecasts?: {
      reaction_time_median_ms?: number;
      fatigue?: { model_class_probabilities?: { low: number; moderate: number; high: number } };
    };
    input_quality?: { out_of_training_range_features?: { feature: string; observed: number; training_min: number; training_max: number }[] };
    current_observation?: { physiology?: { outlier_flag?: boolean | null } };
  } | null;
}

interface HistoryResponse {
  astronaut_id?: string;
  calibration_required?: number;
  personal_baseline: PersonalBaseline | null;
  history: BackendAssessment[];
  observations: (Measurements & { observation_timestamp_utc: string; journal_text?: string | null })[];
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${apiBase()}${path}`, { signal: AbortSignal.timeout(READ_TIMEOUT_MS) });
  if (!res.ok) throw new DataSourceError(`Backend returned HTTP ${res.status} for ${path}.`);
  return (await res.json()) as T;
}

function pickMeasurements(source: Measurements): Measurements {
  const out = {} as Measurements;
  for (const key of MEASUREMENT_KEYS) {
    const value = source[key];
    if (typeof value !== 'number' || !Number.isFinite(value)) {
      throw new DataSourceError(`Missing or invalid numeric measurement: ${key}.`);
    }
    out[key] = value;
  }
  return out;
}

function toForecast(a: BackendAssessment): Forecast | null {
  if (a.status !== 'completed') return null;
  if (typeof a.fatigue_points !== 'number' || !Number.isFinite(a.fatigue_points) ||
      a.fatigue_points < 0 || a.fatigue_points > 100 ||
      !['Low', 'Moderate', 'High'].includes(a.fatigue_risk_level ?? '')) {
    throw new DataSourceError('Completed assessment has an invalid forecast.');
  }
  if (a.fatigue_score !== null && (typeof a.fatigue_score !== 'number' || !Number.isFinite(a.fatigue_score))) {
    throw new DataSourceError('Completed assessment has an invalid score estimate.');
  }
  const reasons: Reason[] = (a.explanation?.top_contributing_factors ?? []).map((r) => ({
    feature: r.feature,
    value: r.value,
    shapValue: r.shap_value,
    direction: r.direction,
  }));
  return {
    points: a.fatigue_points,
    category: a.fatigue_risk_level as FatigueCategory,
    score: a.fatigue_score,
    probabilities: a.model_result?.next_day_forecasts?.fatigue?.model_class_probabilities ?? null,
    targetTimestamp: a.target_timestamp_utc ?? null,
    reasons,
    advisoryActions: a.advisory_actions ?? [],
    reactionForecastMs: a.model_result?.next_day_forecasts?.reaction_time_median_ms ?? null,
    outOfRangeFeatures: (a.model_result?.input_quality?.out_of_training_range_features ?? []).map(item => item.feature),
    physiologyOutlier: a.model_result?.current_observation?.physiology?.outlier_flag ?? null,
  };
}

function mapHistory(id: string, history: HistoryResponse, backend: Snapshot['backend']): Snapshot {
  if (!history || !Array.isArray(history.observations) || !Array.isArray(history.history) ||
      history.history.length !== history.observations.length ||
      (history.astronaut_id !== undefined && history.astronaut_id !== id)) {
    throw new DataSourceError('Backend history is malformed or belongs to a different astronaut.');
  }
  const records: DayRecord[] = history.observations.map((obs, i) => {
    const assessment = history.history[i];
    if (!assessment || !['completed', 'collecting_baseline', 'model_unavailable'].includes(assessment.status) ||
        !Number.isFinite(Date.parse(obs.observation_timestamp_utc)) ||
        (assessment.observation_timestamp_utc !== undefined &&
         Date.parse(assessment.observation_timestamp_utc) !== Date.parse(obs.observation_timestamp_utc)) ||
        (i > 0 && Date.parse(obs.observation_timestamp_utc) <= Date.parse(history.observations[i - 1].observation_timestamp_utc))) {
      throw new DataSourceError('Backend observation and assessment history do not align.');
    }
    return {
      index: i + 1,
      timestamp: obs.observation_timestamp_utc,
      measurements: pickMeasurements(obs),
      status: assessment?.status ?? 'model_unavailable',
      forecast: toForecast(assessment),
      ...(Object.hasOwn(obs, 'journal_text') ? { journalText: obs.journal_text } : {}),
    };
  });
  return {
    astronautId: id,
    source: 'backend',
    backend,
    calibrationRequired: history.calibration_required ?? CALIBRATION_REQUIRED,
    records,
    baseline: history.personal_baseline,
  };
}

function demoSnapshot(backend: Snapshot['backend']): Snapshot {
  const day8 = DEMO_DAY8_ASSESSMENT;
  const records: DayRecord[] = DEMO_RECORDS.map((r, i) => {
    const isDay8 = i === 7;
    return {
      index: i + 1,
      timestamp: r.timestamp,
      measurements: { ...r.measurements } as Measurements,
      status: isDay8 ? 'completed' : 'collecting_baseline',
      forecast: isDay8
        ? {
            points: day8.fatigue_points,
            category: day8.fatigue_risk_level as FatigueCategory,
            score: day8.fatigue_score,
            probabilities: { ...day8.probabilities },
            targetTimestamp: day8.target_timestamp_utc,
            reasons: day8.reasons.map((x) => ({
              feature: x.feature,
              value: x.value,
              shapValue: x.shap_value,
              direction: x.direction as Reason['direction'],
            })),
            advisoryActions: [...day8.advisory_actions],
            reactionForecastMs: day8.reaction_forecast_ms,
            outOfRangeFeatures: [...day8.out_of_range_features],
            physiologyOutlier: day8.physiology_outlier,
          }
        : null,
    };
  });
  return {
    astronautId: DEMO_ASTRONAUT_ID,
    source: 'demo',
    backend,
    calibrationRequired: CALIBRATION_REQUIRED,
    records,
    baseline: { ...DEMO_BASELINE },
  };
}

/** Reads actual backend history. Only explicit demo mode may show synthetic example records. */
export async function getSnapshot(): Promise<Snapshot> {
  if (demoMode()) return demoSnapshot({ online: false, modelReady: false });
  let health: HealthResponse;
  try {
    health = await getJson<HealthResponse>('/health');
  } catch (error) {
    throw new DataSourceError(`Backend unavailable. ${error instanceof Error ? error.message : ''} No demo data was substituted.`);
  }
  if (!health || health.status !== 'online') throw new DataSourceError('The backend did not report a valid online status.');
  const backend = { online: true, modelReady: health.ai_service?.model_ready === true };
  try {
    const id = astronautId();
    const history = await getJson<HistoryResponse>(`/astronauts/${encodeURIComponent(id)}/history`);
    return mapHistory(id, history, backend);
  } catch (error) {
    throw new DataSourceError(`Could not read backend history. ${error instanceof Error ? error.message : ''} No demo data was substituted.`);
  }
}

// ---- submitting a daily record ----

export interface AssessBody extends Measurements {
  astronaut_id: string;
  observation_timestamp_utc: string;
  journal_text?: string | null;
}

export type SubmitResult =
  | {
      kind: 'saved';
      snapshot: Snapshot;
      httpStatus: number;
      status: RecordStatus;
      /** Set when the record was saved but the model gave no prediction */
      modelError?: string;
      refreshWarning?: string;
      /** Identical body to send again for a retry after a model outage */
      body: AssessBody;
    }
  | { kind: 'rejected'; httpStatus: number; error: string; message: string }
  | { kind: 'unreachable'; message: string; body: AssessBody };

function isoNoMillis(ms: number): string {
  return new Date(ms).toISOString().replace('.000Z', 'Z');
}

/** The daily cutoff of the next record: exactly 24 hours after the last one (the backend rejects gaps). */
export function nextCutoff(records: DayRecord[]): string {
  const last = records[records.length - 1];
  if (last) return isoNoMillis(new Date(last.timestamp).getTime() + DAY_MS);
  const today = new Date().toISOString().slice(0, 10);
  return `${today}T18:00:00Z`;
}

export function buildBody(snapshot: Snapshot, measurements: Measurements, journalText?: string): AssessBody {
  const note = journalText?.trim();
  return {
    astronaut_id: snapshot.astronautId,
    observation_timestamp_utc: nextCutoff(snapshot.records),
    ...pickMeasurements(measurements),
    ...(note ? { journal_text: note } : {}),
  };
}

export function retryBodyFor(id: string, record: DayRecord): AssessBody {
  return { astronaut_id: id, observation_timestamp_utc: record.timestamp, ...record.measurements,
    ...(Object.hasOwn(record, 'journalText') ? { journal_text: record.journalText } : {}) };
}

/** Saves a record locally only in explicitly selected demo mode. No prediction is invented. */
function saveLocally(snapshot: Snapshot, body: AssessBody): SubmitResult {
  const record: DayRecord = {
    index: snapshot.records.length + 1,
    timestamp: body.observation_timestamp_utc,
    measurements: pickMeasurements(body),
    status: snapshot.records.length < snapshot.calibrationRequired ? 'collecting_baseline' : 'model_unavailable',
    forecast: null,
  };
  return {
    kind: 'saved',
    snapshot: { ...snapshot, records: [...snapshot.records, record] },
    httpStatus: 0,
    status: record.status,
    modelError: 'No backend is connected, so this record is kept only in this browser session and has no prediction.',
    body,
  };
}

/**
 * Sends one daily record. To retry after a model outage, pass the same body again (same timestamp):
 * the backend then updates that record instead of adding a new day.
 */
export async function submitRecord(snapshot: Snapshot, body: AssessBody): Promise<SubmitResult> {
  if (snapshot.source === 'demo') return saveLocally(snapshot, body);

  let res: Response;
  try {
    res = await fetch(`${apiBase()}/assess`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(SUBMIT_TIMEOUT_MS),
    });
  } catch {
    return { kind: 'unreachable', message: 'The backend could not be reached. Nothing was confirmed as saved.', body };
  }

  let payload: Record<string, unknown> = {};
  try {
    payload = (await res.json()) as Record<string, unknown>;
  } catch {
    /* non-JSON error body */
  }

  const saved = payload['observation_saved'] === true;
  if (saved && [201, 202, 502, 503, 504].includes(res.status)) {
    const status = payload['status'];
    if (!['completed', 'collecting_baseline', 'model_unavailable'].includes(String(status))) {
      return { kind: 'unreachable', message: 'The backend reported a save but returned an incompatible assessment. Refresh history before submitting another day.', body };
    }
    let forecast: Forecast | null = null;
    let forecastWarning: string | undefined;
    try { forecast = toForecast(payload as unknown as BackendAssessment); }
    catch (error) {
      forecastWarning = `The observation was saved, but its forecast was incompatible and has been withheld. Refresh history. ${error instanceof Error ? error.message : ''}`;
    }
    const modelError = status === 'model_unavailable' ? String(payload['message'] ?? 'The model is unavailable.') : undefined;
    // Acknowledged saved data remain visible even if the subsequent history read fails.
    // Never replace a successfully saved observation with the offline demo fixture.
    const existing = snapshot.records.findIndex(r => Date.parse(r.timestamp) === Date.parse(body.observation_timestamp_utc));
    const record: DayRecord = {
      index: existing < 0 ? snapshot.records.length + 1 : existing + 1,
      timestamp: body.observation_timestamp_utc,
      measurements: pickMeasurements(body), status: status as RecordStatus, forecast,
      ...(Object.hasOwn(body, 'journal_text') ? { journalText: body.journal_text } : {}),
    };
    const records = [...snapshot.records];
    if (existing < 0) records.push(record); else records[existing] = record;
    let fresh: Snapshot = { ...snapshot, records,
      backend: { online: true, modelReady: (status === 'completed' && forecast !== null) || (status === 'collecting_baseline' && snapshot.backend.modelReady) } };
    let refreshWarning: string | undefined = forecastWarning;
    try {
      const refreshed = await getSnapshot();
      if (refreshed.source !== 'backend' || refreshed.astronautId !== body.astronaut_id ||
          !refreshed.records.some(r => Date.parse(r.timestamp) === Date.parse(body.observation_timestamp_utc))) {
        throw new DataSourceError('Refreshed history does not contain the acknowledged observation.');
      }
      fresh = refreshed;
      refreshWarning = undefined;
    } catch {
      refreshWarning = forecastWarning ?? 'The save was confirmed, but history could not be refreshed. Showing the acknowledged result; refresh before the next record.';
    }
    return { kind: 'saved', snapshot: fresh, httpStatus: res.status, status: status as RecordStatus, modelError, refreshWarning, body };
  }

  return {
    kind: 'rejected',
    httpStatus: res.status,
    error: String(payload['error'] ?? 'request_failed'),
    message: String(payload['message'] ?? `The backend returned HTTP ${res.status}.`),
  };
}
