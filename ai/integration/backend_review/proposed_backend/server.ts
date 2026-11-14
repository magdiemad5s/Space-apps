/** Reviewable extension of the teammate's uploaded TypeScript/Express backend.
 * Original routes are retained; the current model contract is explicit.
 * No legacy measurement aliases, invented personal baselines or mock SHAP.
 */
import express, { type Request, type Response } from "express";
import cors from "cors";
import { promises as fs } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import crypto from "node:crypto";
import { AstraShieldModelClient, ModelClientError, type Prediction } from "./modelClient.ts";
import {
  validateCurrentObservation, prepareAssessment, FeatureHistoryError,
  type CurrentObservation, type HistoryRecord,
} from "./featureHistory.ts";

type AssessmentStatus = "collecting_baseline" | "model_unavailable" | "completed";
interface Assessment extends Record<string, unknown> {
  assessment_id: string;
  astronaut_id: string;
  timestamp: string;
  observation_timestamp_utc: string;
  status: AssessmentStatus;
  inference_source: "none" | "synthetic_model";
  observation_saved: boolean;
  ai_service_connected: boolean;
  fatigue_score: number | null;
  fatigue_risk_level: "Low" | "Moderate" | "High" | null;
  fatigue_points: number | null;
  fatigue_risk_percentage: null;
  used_personal_baseline: boolean;
  personal_baseline_ready: boolean;
  personal_baseline: Record<string, number> | null;
  calibration_count: number;
  calibration_required: 7;
  calibration_timestamps: string[];
}
interface StoredRecord extends HistoryRecord {
  assessment: Assessment;
}
interface Store {
  schema_version: 2;
  participants: Record<string, StoredRecord[]>;
}
export interface BackendOptions {
  dbFile?: string;
  aiServiceUrl?: string;
  modelTimeoutMs?: number;
  fetchImpl?: typeof fetch;
}

class StoreError extends Error {}
const MODULE_DIRECTORY = path.dirname(fileURLToPath(import.meta.url));

function emptyStore(): Store {
  return { schema_version: 2, participants: Object.create(null) as Record<string, StoredRecord[]> };
}
function recordList(store: Store, id: string): StoredRecord[] {
  return Object.hasOwn(store.participants, id) ? store.participants[id]! : [];
}
function putRecords(store: Store, id: string, records: StoredRecord[]): void {
  Object.defineProperty(store.participants, id, { value: records, enumerable: true, writable: true, configurable: true });
}
function sameObservation(a: CurrentObservation, b: CurrentObservation): boolean {
  const normalized = (value: CurrentObservation) => JSON.stringify(Object.entries(value).sort(([a], [b]) => a.localeCompare(b)));
  return normalized(a) === normalized(b);
}

async function loadStore(file: string): Promise<Store> {
  let text: string;
  try { text = await fs.readFile(file, "utf8"); }
  catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return emptyStore();
    throw new StoreError("History storage could not be read.");
  }
  try {
    const parsed: unknown = JSON.parse(text);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("object required");
    const candidate = parsed as Partial<Store>;
    if (candidate.schema_version !== 2 || !candidate.participants || typeof candidate.participants !== "object" || Array.isArray(candidate.participants)) {
      throw new Error("schema mismatch");
    }
    for (const [id, records] of Object.entries(candidate.participants)) {
      if (!Array.isArray(records)) throw new Error("invalid history");
      for (const record of records) {
        if (!record || typeof record !== "object" || !record.assessment || typeof record.assessment !== "object") throw new Error("invalid record");
        const observation = validateCurrentObservation(record.observation);
        if (observation.astronaut_id !== id || !["collecting_baseline", "model_unavailable", "completed"].includes(record.assessment.status)) {
          throw new Error("invalid participant/status");
        }
      }
    }
    return candidate as Store;
  } catch {
    // A corrupt or old-format file is not silently replaced with an empty store.
    throw new StoreError("History file is invalid or uses an unsupported schema. Preserve it and review it before continuing.");
  }
}

async function saveStore(file: string, store: Store): Promise<void> {
  const temporary = `${file}.${process.pid}.${crypto.randomUUID()}.tmp`;
  try {
    await fs.mkdir(path.dirname(file), { recursive: true });
    await fs.writeFile(temporary, JSON.stringify(store, null, 2), { encoding: "utf8", mode: 0o600 });
    await fs.rename(temporary, file);
  } catch {
    await fs.unlink(temporary).catch(() => undefined);
    throw new StoreError("History storage could not be saved; no successful assessment is returned.");
  }
}

function classifyUpstream(error: unknown): { status: number; code: string; message: string } {
  if (error instanceof ModelClientError) {
    if (error.kind === "input" || error.kind === "validation") return { status: 422, code: "model_input_rejected", message: error.message };
    if (error.kind === "timeout") return { status: 504, code: "model_timeout", message: error.message };
    if (error.kind === "protocol") return { status: 502, code: "model_response_incompatible", message: error.message };
    return { status: 503, code: "model_unavailable", message: error.message };
  }
  return { status: 503, code: "model_unavailable", message: "The private inference service is unavailable." };
}

export function createApp(options: BackendOptions = {}) {
  const app = express();
  const dbFile = path.resolve(options.dbFile ?? process.env.DB_FILE ?? path.join(MODULE_DIRECTORY, "history_db_v2.json"));
  const aiServiceUrl = (options.aiServiceUrl ?? process.env.AI_SERVICE_URL ?? "").trim();
  const timeoutMs = options.modelTimeoutMs ?? 10_000;
  const fetchImpl = options.fetchImpl ?? fetch;
  const client = aiServiceUrl ? new AstraShieldModelClient(aiServiceUrl, { timeoutMs, fetchImpl }) : null;
  let queue: Promise<unknown> = Promise.resolve();
  function serialized<T>(operation: () => Promise<T>): Promise<T> {
    const next = queue.then(operation, operation);
    queue = next.then(() => undefined, () => undefined);
    return next;
  }
  app.use(cors());
  app.use(express.json({ limit: "100kb" }));

  app.get("/api/v1/health", async (_req: Request, res: Response) => {
    let reachable = false;
    let modelReady = false;
    if (aiServiceUrl) {
      try {
        const base = new URL(aiServiceUrl);
        if (!base.pathname.endsWith("/")) base.pathname += "/";
        const upstream = await fetchImpl(new URL("health", base), { signal: AbortSignal.timeout(timeoutMs) });
        reachable = true;
        const payload = await upstream.json() as Record<string, unknown>;
        modelReady = upstream.ok && payload.status === "ready" && payload.clinical_validation === false && payload.data_origin === "synthetic";
      } catch { /* No claimed connection or fake health payload. */ }
    }
    res.json({ service: "ASTRA-SHIELD TypeScript Backend API", status: "online",
      ai_integration_mode: modelReady ? "connected_to_private_model" : "model_unavailable",
      ai_service: { configured: Boolean(aiServiceUrl), reachable, model_ready: modelReady },
      history_schema_version: 2, clinical_validation: false });
  });

  app.post("/api/v1/assess", async (req: Request, res: Response) => {
    try {
      const current = validateCurrentObservation(req.body);
      const outcome = await serialized(async () => {
        const store = await loadStore(dbFile);
        const allRecords = recordList(store, current.astronaut_id);
        let history: StoredRecord[] = allRecords;
        let retry: StoredRecord | undefined;
        const last = allRecords.at(-1);
        if (last && last.observation.observation_timestamp_utc === current.observation_timestamp_utc &&
            last.assessment.status === "model_unavailable" && sameObservation(last.observation, current)) {
          retry = last;
          history = allRecords.slice(0, -1); // identical latest outage retry never creates an extra day
        }
        const prepared = prepareAssessment(current, history);
        const assessment: Assessment = {
          assessment_id: retry?.assessment.assessment_id ?? crypto.randomUUID(),
          astronaut_id: current.astronaut_id,
          timestamp: new Date().toISOString(),
          observation_timestamp_utc: current.observation_timestamp_utc,
          status: prepared.ready ? "model_unavailable" : "collecting_baseline",
          inference_source: "none", observation_saved: true, ai_service_connected: false,
          fatigue_score: null, fatigue_risk_level: null, fatigue_points: null,
          fatigue_risk_percentage: null,
          used_personal_baseline: false, personal_baseline_ready: prepared.calibrationComplete,
          personal_baseline: prepared.baseline,
          calibration_count: prepared.calibrationCount, calibration_required: 7,
          calibration_timestamps: prepared.calibrationTimestamps,
          baseline_protocol: "fixed_first_seven_consecutive_daily_records; prior_three_daily_cutoffs",
          forecast_horizon_hours: 24,
          data_origin: "user_entered_observations_for_synthetic_model_prototype",
          clinical_validation: false,
          explanation: { summary_en: prepared.ready ? "No model prediction is available yet." : "Collecting earlier daily calibration observations; no model prediction was made.",
            summary_ar: prepared.ready ? "لا تتوفر نتيجة من الموديل حاليًا." : "يتم جمع سجلات المعايرة اليومية السابقة؛ لم يتم إصدار توقع من الموديل.",
            top_contributing_factors: [] },
          recommendations: [], model_result: null,
        };
        let status = prepared.ready ? 503 : 202;
        if (prepared.ready && prepared.features && client) {
          try {
            const prediction: Prediction = await client.predict(prepared.features);
            // Build the success mapping first; no partly completed assessment
            // survives a missing/malformed nested response or unexpected error.
            const success = {
              status: "completed" as const,
              inference_source: "synthetic_model" as const,
              ai_service_connected: true,
              used_personal_baseline: true,
              fatigue_score: prediction.next_day_forecasts.fatigue.score_estimate,
              fatigue_risk_level: ({ low: "Low", moderate: "Moderate", high: "High" } as const)[prediction.label],
              fatigue_points: prediction.points,
              fatigue_points_definition: prediction.points_definition,
              target_timestamp_utc: prediction.target_timestamp_utc,
              model_version: prediction.model_version,
              model_training_data_origin: prediction.data_origin,
              model_result: prediction,
              explanation: {
                summary_en: "Next-day synthetic-model fatigue forecast. SHAP explains the classifier, not medical causes.",
                summary_ar: "توقع تعب لليوم التالي من موديل مدرب على بيانات اصطناعية؛ SHAP يفسر الموديل ولا يثبت أسبابًا طبية.",
                top_contributing_factors: prediction.reasons,
                explained_class: prediction.explanation.tree_shap.explained_class,
                model_output_space: prediction.explanation.tree_shap.model_output_space,
              },
              advisory_actions: prediction.advisory_actions,
              limitations: prediction.limitations,
            };
            Object.assign(assessment, success);
            status = 201;
          } catch (error) {
            const failure = classifyUpstream(error);
            Object.assign(assessment, {
              status: "model_unavailable", inference_source: "none",
              ai_service_connected: false, used_personal_baseline: false,
              fatigue_score: null, fatigue_risk_level: null, fatigue_points: null,
              model_result: null, recommendations: [], advisory_actions: [],
              explanation: { summary_en: "No valid model prediction is available.", summary_ar: "لا تتوفر نتيجة صالحة من الموديل.", top_contributing_factors: [] },
            });
            if (failure.status === 422) {
              // A model-contract rejection is not an outage: do not save a bad observation.
              return { status: 422, assessment: { ...assessment, observation_saved: false, error: failure.code, message: failure.message } };
            }
            status = failure.status;
            assessment.error = failure.code;
            assessment.message = failure.message;
          }
        } else if (prepared.ready) {
          assessment.error = "model_not_configured";
          assessment.message = "AI_SERVICE_URL is not configured. The observation is saved, but no model prediction or SHAP reasons were fabricated.";
        }
        const saved: StoredRecord = { observation: current, assessment };
        putRecords(store, current.astronaut_id, retry ? [...history, saved] : [...allRecords, saved]);
        await saveStore(dbFile, store);
        return { status, assessment };
      });
      res.status(outcome.status).json(outcome.assessment);
    } catch (error) {
      if (error instanceof FeatureHistoryError) {
        res.status(error.status).json({ error: error.code, message: error.message, details: error.details, observation_saved: false });
      } else if (error instanceof StoreError) {
        res.status(503).json({ error: "history_store_unavailable", message: error.message, observation_saved: false });
      } else {
        res.status(500).json({ error: "assessment_processing_failed", message: "The assessment could not be processed.", observation_saved: false });
      }
    }
  });

  app.get("/api/v1/astronauts/:id/history", async (req: Request, res: Response) => {
    try {
      const id = String(req.params.id);
      const store = await loadStore(dbFile);
      const records = recordList(store, id);
      const calibration = records.slice(0, 7);
      res.json({ astronaut_id: id, total_assessments: records.length,
        calibration_count: Math.min(records.length, 7), calibration_required: 7,
        calibration_timestamps: calibration.map((record) => record.observation.observation_timestamp_utc),
        personal_baseline: records.at(-1)?.assessment.personal_baseline ?? null,
        history: records.map((record) => record.assessment),
        observations: records.map((record) => record.observation),
        history_schema_version: 2, clinical_validation: false });
    } catch (error) {
      res.status(503).json({ error: "history_store_unavailable", message: error instanceof StoreError ? error.message : "History could not be loaded." });
    }
  });

  app.delete("/api/v1/astronauts/:id/history", async (req: Request, res: Response) => {
    try {
      const id = String(req.params.id);
      await serialized(async () => {
        const store = await loadStore(dbFile);
        delete store.participants[id];
        await saveStore(dbFile, store);
      });
      res.json({ astronaut_id: id, message: "History and calibration records cleared." });
    } catch (error) {
      res.status(503).json({ error: "history_store_unavailable", message: error instanceof StoreError ? error.message : "History could not be cleared." });
    }
  });

  app.use((error: unknown, _req: Request, res: Response, _next: express.NextFunction) => {
    if (error instanceof SyntaxError) {
      res.status(400).json({ error: "invalid_json", message: "Request body must be valid JSON." });
    } else {
      res.status(500).json({ error: "request_processing_failed" });
    }
  });
  return app;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const port = Number(process.env.PORT ?? 3000);
  const host = process.env.HOST ?? "127.0.0.1";
  if (!Number.isInteger(port) || port < 0 || port > 65535) throw new Error("PORT must be an integer from 0 to65535.");
  createApp().listen(port, host, () => {
    console.log(`[ASTRA-SHIELD TypeScript Backend] Listening on http://${host}:${port}`);
  });
}
