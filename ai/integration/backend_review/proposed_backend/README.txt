ASTRA-SHIELD — REVIEWABLE UPDATED COPY OF THE TEAMMATE'S TYPESCRIPT BACKEND

This is an extended copy of the uploaded Express backend, not a second competing
application backend. The original uploaded server.ts/package.json were preserved.
The Python model/API and its learned artifacts were not changed. Existing public
route names are retained. Review the changes before replacing the teammate's file.

The user chose to extend frontend measurement fields to fit the current model.
The old form payload cannot be converted by renaming arbitrary fields or filling
defaults. See ../input_field_mapping.csv and ../COMPATIBILITY_REVIEW.txt.

RUN (tested with Node 24, TypeScript 5.9)

  npm ci
  npm run typecheck
  npm test

Set these backend-side environment variables before npm start:
  AI_SERVICE_URL=http://127.0.0.1:8000
  DB_FILE=/your/writable/path/history_db_v2.json
  HOST=127.0.0.1
  PORT=3000

  npm start          # normal server
  npm run dev       # optional development watch mode
  npm run build     # optional compiled JavaScript in dist/

The Python model service is started separately using its existing package:
  python -m uvicorn astra_shield_ml.api:app --host 127.0.0.1 --port 8000
Use the private service hostname instead of loopback if workers are in different
containers. Angular/Ionic should continue calling this TypeScript application API,
not the private inference worker directly. No model artifact is loaded in Node.

ROUTES

GET /api/v1/health
  Reports backend online status plus actual model configuration/reachability/
  readiness. A configured URL alone is not reported as a successful connection.
  Makes a bounded GET /health upstream; does not change history or models.

POST /api/v1/assess
  Body: astronaut_id, timezone-aware observation_timestamp_utc, and all 15 current
  canonical numeric measurements listed below. Optional journal_text may be text
  or null. Do not submit baseline means, target labels, derived features, legacy
  aliases or arbitrary extra fields. Semantic ranges and sleep/time consistency
  are checked. Numeric strings, booleans, missing or non-finite numbers are invalid.

  sleep_duration_hours
  sleep_efficiency_pct
  sleep_onset_delay_minutes
  awakenings_count
  sleep_midpoint_deviation_minutes
  resting_heart_rate_bpm
  hrv_rmssd_ms
  reaction_time_median_ms
  reaction_time_lapses_count
  attention_accuracy_pct
  self_report_stress_score
  self_report_fatigue_score
  self_report_mood_score
  workload_hours
  exercise_minutes

  Measurement definitions matter: sleep quality is not sleep efficiency, unknown
  HRV is not necessarily RMSSD, unspecified HR is not necessarily a resting
  recording, PVT transformed slowness is not median reaction time in milliseconds,
  and PVT accuracy is not this model's separate attention-task accuracy.

  Records 1–7: HTTP 202 status=collecting_baseline. No model values/reasons are
  fabricated. Seven records must be exactly 24 hours apart for the same participant.
  On record 7 the fixed baseline becomes available; prediction still begins only
  with record 8, so calibration always precedes the observation being predicted.

  Record 8+: fixed means of the first 7 records plus means of the immediately
  preceding 3 daily records produce the 7 historical model inputs. They are never
  provided by the frontend or recalculated across all history. The existing model
  service receives exactly 22 numeric fields plus allowed metadata at /v1/predict.

  Success: HTTP 201 status=completed, inference_source=synthetic_model, label
  displayed as Low/Moderate/High, fatigue_score from the custom 0–10 regressor,
  fatigue_points from the declared 0–100 prototype severity index, actual SHAP
  reasons, baseline provenance, source and 24-hour forecast metadata. The complete
  original worker response is retained under model_result for traceability.

  fatigue_risk_percentage remains null and deprecated; severity points are not a
  clinical percentage. The custom score and category come from separate models.
  No assertion that measurements are healthy or operationally safe is generated.

  Invalid inputs: 422; duplicate/out-of-order/gapped records: 409. Completed records
  cannot be resubmitted to advance calibration. Model timeout: 504; unavailable
  service/configuration: 503; incompatible model response: 502. Model 400-series
  input rejection: 422 and the observation is not saved as valid history.

  On worker outage or missing AI_SERVICE_URL, validated observations ARE saved
  with status=model_unavailable, observation_saved=true, null scores and no fake
  SHAP/recommendations. Thus a temporary outage does not create daily history gaps.
  Only the latest failed observation can be retried: submit its identical
  canonical body/timestamp. It replaces that same record, does not add another
  day, and may become completed when the worker recovers. Older failed records
  cannot be inserted out of order after later observations already exist.

GET /api/v1/astronauts/:id/history
  Returns assessment history and raw canonical observations for graphs, total
  count, fixed calibration timestamps and baseline. First 7 calibration records are
  distinguishable from predictions by assessment.status and inference_source.

DELETE /api/v1/astronauts/:id/history
  Clears that person's observations and calibration state in this prototype.
  Authentication/authorization remains the application team's responsibility.

HISTORY STORAGE

The default is a NEW history_db_v2.json next to this source; DB_FILE overrides it.
The schema is {schema_version:2, participants:{id:[{observation,assessment}]}}.
Old history_db.json data is not silently imported as valid calibration. Corrupt,
unreadable or mismatched-schema files cause an explicit error, not an empty store
that overwrites the records. Saves use temporary-file rename. Assessment/delete
operations are serialized in this single process to prevent local race loss.
This is a local prototype file store, not a multi-instance production database.

FRONTEND DEMONSTRATION

The parent handoff supplies examples/synthetic_daily_sequence.json (9 daily raw
observations), assess_request_day8.json and expected_model_request_day8.json.
These are explicitly synthetic examples, not invented personal baselines for
actual people. With the Python worker and backend running, node demo.mjs sends
the historical demo sequence; it refuses an already populated demo ID rather
than deleting or duplicating existing history. The frontend can graph the raw
observations and show collecting-baseline versus completed states directly.

FILE OWNERSHIP

server.ts and modelClient.ts implement the reviewed connector/backend changes.
featureHistory.ts owns the shared causal history and measurement contract.
featureHistory.test.ts verifies that contract; parent integration checks exercise
the live TypeScript backend plus real private Python model service.
The source review manifest records hashes of the untouched original uploads.

ملخص للفريق:
هذا تحديث قابل للمراجعة لنفس backend TypeScript الذي رفعتموه. زدنا الحقول
الحقيقية المطلوبة من الفرونت إند، وثبتنا معايرة 7 أيام وسجل 3 أيام سابقة، ووصلنا
الموديل الخاص ببايثون عبر HTTP. أول 7 سجلات لا يصدر فيها توقع؛ يبدأ التوقع في
السجل الثامن. لا نعوض القياسات أو الـbaseline بقيم افتراضية، ولا نعرض points
كنسبة خطر طبي، ولا نخترع SHAP عندما تكون الخدمة غير متصلة. الملفات الأصلية
والموديل المدرب لم يتم تعديلهما. يبقى تطوير واجهات التطبيق عند مطورة الـbackend.

FRONTEND MIGRATION CHECKLIST / قائمة نقل الفرونت إند

1. Send all 15 canonical measurements, the actual observation cutoff and astronaut_id.
   Use ../input_field_mapping.csv; no automatic legacy PVT/HRV conversions.
2. Show HTTP 202 collecting_baseline as enrollment progress, without a fatigue
   label/score or green healthy-state message. Prediction begins on day 8.
3. Show fatigue_points as a demo severity index /100, not a medical percentage.
   fatigue_risk_percentage is intentionally null; update that old UI binding.
4. Plot observations from the history endpoint; preserve each recorded day and
   actual timestamp. Repeated button clicks must not create extra calibration days.
5. A 503/504/502 model outage can still contain observation_saved=true. Show that
   the daily measurement was retained while the model is unavailable. A retry
   must send the identical latest failed observation; it does not add another day.
6. Use top_contributing_factors as actual SHAP reason objects (feature/value/
   shap_value/direction/reason), with the explained class/output space retained.
   Do not invent baseline values or turn them into causal medical instructions.

للفرونت إند: أرسلوا الحقول الـ15 بأسمائها الجديدة مع هوية الشخص ووقت القياس،
واعرضوا تقدّم المعايرة خلال أول 7 أيام بدون درجات تعب افتراضية. اربطوا خانة
النقاط بـfatigue_points بدل fatigue_risk_percentage، وارسموا السجلات الخام
من observations. إذا تعطّل الموديل وكان observation_saved=true فالقياس
محفوظ ولا نضيف نفس اليوم من جديد. نعيد فقط آخر طلب فاشل بنفس محتواه ووقته.

EXACT START COMMANDS

Start the Python worker in its existing model project with its virtual environment
activated. Install that project's requirements first if this is a new machine.
This backend-only handoff does not include Python model weights.

Linux/macOS, from this proposed_backend directory:
  npm ci
  AI_SERVICE_URL=http://127.0.0.1:8000 npm start

Windows PowerShell, from this proposed_backend directory:
  npm ci
  $env:AI_SERVICE_URL = "http://127.0.0.1:8000"
  npm start

In a separate terminal, from this same backend directory:
  node demo.mjs

Keep server.ts, featureHistory.ts and modelClient.ts together with package.json,
package-lock.json and tsconfig.json. Copying only the original two files is no
longer sufficient. FRONTEND_MEASUREMENTS.csv defines the 15 required current
measurement fields and units. The frontend additionally supplies astronaut_id,
observation_timestamp_utc and optional journal_text.

DAILY CADENCE AND LIMITS

observation_timestamp_utc is the agreed daily prediction cutoff, not the time
someone happened to click Submit. Use the same UTC cutoff on consecutive days,
with measurements already available by that cutoff. This prototype rejects gaps
in daily history; it does not implement a missing-day recovery or dropout model.
The first seven valid records form a computational calibration reference; they
are not automatically a clinically established healthy baseline.

VALIDATION COMPLETED

Strict TypeScript checking and compilation passed. All 16 feature-history tests
passed, including agreement with the existing Python causal feature helper.
29 checks passed using the real TypeScript HTTP backend and frozen Python model
on local loopback ports, with a temporary history store and synthetic fixtures.
The original trained artifact and uploaded files were preserved. The Angular/Ionic
application itself, production deployment and clinical performance were not tested.
