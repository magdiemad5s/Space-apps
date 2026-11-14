ASTRA-SHIELD — CLIENT FOR THE TEAMMATE'S TYPESCRIPT BACKEND

This directory is a small HTTP client and a framework-neutral adapter function.
It is not another application backend, Express server, database or user system.
The existing TypeScript backend remains the owner of application routes,
authentication, authorization, participant records and business logic.

Architecture:
  Angular / Ionic frontend
       -> teammate's TypeScript application API
       -> private Python model service: POST /v1/predict

Angular/Ionic can consume JSON APIs implemented in any language. They do not
require the trained model to be rewritten in JavaScript. The trained joblib
artifact is loaded by the private Python worker; Node does not load that pickle.

BACKEND-SIDE USE

  import { createFatiguePredictionHandler } from './backendAdapter.ts';
  import type { ModelFeatures } from './modelClient.ts';

  // Create once at startup using server configuration, never a request-supplied URL.
  const predictFatigue = createFatiguePredictionHandler('http://127.0.0.1:8000');

  // Inside the teammate's existing authenticated route or service:
  const prediction = await predictFatigue(features as ModelFeatures);
  // prediction.label, prediction.points, prediction.reasons
  // Also includes separate next-day forecasts and current physiology/journal outputs.

Use the service address appropriate to the actual deployment. A backend in a
different container needs its private model-service hostname, not its own loopback.
Do not place the model-service URL/client in the browser or Ionic app. Frontend
requests should continue to use the team's existing TypeScript application API.

INPUT / OUTPUT CONTRACT

modelClient.ts types match the Python model service's 22 required numeric inputs:
15 current observations + 4 earlier calibration means + 3 prior-three-day means.
Optional: journal_text, participant_id, observation_timestamp_utc.
The Python service computes 4 baseline-difference features. Do not send those,
target labels, split fields or future measurements. The client rejects unexpected
columns and non-finite/non-numeric values before serialization. The Python
service owns the complete range, time and sleep-consistency validation rules.
The backend must supply genuinely earlier participant calibration/history.

The summary response is runtime-checked; the full response is TypeScript-typed
against OpenAPI but is not a full runtime JSON-schema validation library.
label is low/moderate/high for the next day's simulated fatigue category.
points is an uncalibrated prototype 0..100 severity index, not medical risk.
reasons contains 3 actual SHAP feature explanations. All outputs retain the
synthetic-data/non-clinical scope flags. No new model training occurs in this client.

ERROR HANDLING

ModelClientError.kind: input, validation, unavailable, timeout, network,
protocol or http. Errors do not echo the measurements returned by the worker.
There are no automatic prediction retries. Default request timeout: 10 seconds.
The adapter's suggested application mapping is 422 for bad inputs, 504 for model
timeout, and 502 for upstream availability/protocol/network errors. Your existing
backend remains responsible for its final error response format and logging.

VALIDATION

Node 24+ can run these .ts files directly using built-in type stripping.
  npm test

For strict static type checking after installing the local dev dependency:
  npm install
  npm run typecheck
  npm run build

The build emits standard ES-module JavaScript and declarations into dist/.
You can import the built adapter from your existing Node backend without a
TypeScript runtime loader. The compiler rewrites relative .ts imports to .js.

No framework or production runtime dependency is added by this adapter.
package-lock.json pins the compiler used for the checked handoff.
fixtures/ contains synthetic request/response and OpenAPI snapshots from the
actual Python model service, allowing this adapter folder to be tested alone.
VALIDATION.json records the verified compiler and the 8 runtime tests.

ملخص للفريق:
الـbackend الأساسي يظل TypeScript عند مطورته. أضفنا client صغير يستدعي
خدمة الموديل الخاصة ببايثون عبر HTTP ويرجع النتيجة لنفس الـbackend.
ما بنينا backend تطبيق ثاني، وما غيرنا الموديل أو الداتا أو اللغة اللي
تشتغل عليها مطورة الـbackend. يظل Angular/Ionic يتواصل مع API التطبيق الحالي.
