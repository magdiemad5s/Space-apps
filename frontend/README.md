# Crew Health Console · integrated frontend

Angular 22 · Ionic 9 · TypeScript · SVG charts. Based on **Karam Alhams's [crew-health-console](https://github.com/Karam-Eyad/crew-health-console)**, supplied by the team as a ZIP and integrated into ASTRA-SHIELD. The application remains a web app on Windows and Linux.

**Start with the [repository README](../README.md)** for the Windows **0.1.1 prototype installer** and source launchers, or [Linux instructions](../docs/RUNNING.md#linux). The portable and installed Windows executables passed [native Windows checks](../integration-reports/windows-build-5/verification.json); they open this same frontend in a browser. The original teammate README is preserved as [a historical snapshot](docs/UPSTREAM_README_SNAPSHOT.md); its automatic-demo fallback, quick-test transfer, and lenient model-loader instructions have been superseded.

This NASA Space Apps 2026 submission is a hackathon prototype. Its model-training and example records are synthetic, not NASA astronaut measurements. It is not a medical diagnosis or a validated astronaut-health system. See the [project submission disclosure](../docs/SUBMISSION_DISCLOSURE.md) and [machine-readable provenance](../PROVENANCE.json) for project-wide sources, AI assistance, and limitations.

The full [team roster](../README.md#team) credits all six project contributors.

## What the teammate provided

| Screen | Function |
|---|---|
| Overview | Daily measurements grouped by sleep, heart, cognition, self-report, and workload; calibration or next-day forecast |
| Body map | Clickable astronaut figure with measurement context and links to the Guide |
| Check-in | All 15 canonical measurements, optional journal, daily cutoff, calibration, reaction-time prototype and retry |
| Trends | Measurement and forecast histories, with personal-baseline comparisons after calibration |
| Guide | Measurement definitions, prototype color rules, escalation context, and cited background sources |
| Bottom panel | Model SHAP explanations, illustrative measurement guidance, and example suggestions |

Integration adds an **Alert demo** tab: five prewritten fictional examples showing current alert levels 0/1/2/3/UNKNOWN beside a separate example forecast. It makes no clinical inference or model request and does not execute the 14 Clinical Alert V2 acceptance cases. This tab hides the unrelated record body-map details and forecast/recommendation panel, so its example Low forecast cannot be confused with the selected record.

## Develop in a browser

```bash
npm ci
npm start
```

Open <http://localhost:4200>. Node **22.22.3+, 24.15+ LTS, or 26+** is required by the locked Angular toolchain. The integrated frontend defaults to **`/api/v1`**. `proxy.conf.cjs` forwards requests to `http://127.0.0.1:3000`; `BACKEND_URL` can change the backend origin at startup.

Without a backend, the UI shows a connection error and offers an **explicit simulated demo**. It does not silently substitute fixture records after a backend/history failure. Offline demo additions are in-memory only and get no new prediction.

```bash
npm run typecheck
npm test
npm run build
```

The build is in `dist/dashboard-angular/browser/`. It can be hosted as static assets with a reverse proxy for `/api/v1`. See [the web path](../docs/WEB_DEPLOYMENT.md). The Windows launcher uses this same frontend, not a desktop-specific fork. The teammate's original Manrope typeface is bundled locally through pinned `@fontsource-variable/manrope`, preserving its appearance without downloading Google Fonts at runtime.

## Connected contract

The backend receives an `astronaut_id`, an explicit `observation_timestamp_utc`, **15 numeric measurements**, and optional `journal_text`. Exact fields, units, and bounds are documented in [FRONTEND_MEASUREMENTS.csv](../ai/integration/backend_review/proposed_backend/FRONTEND_MEASUREMENTS.csv) and [the backend contract](../ai/docs/FRONTEND_INTEGRATION.md).

It accepts current observations, not target labels or client-computed baselines. First seven consecutive 24-hour records calibrate; prediction begins on the eighth. Python receives 22 numeric inputs and derives four baseline deltas for the original 26-feature classifier.

| Backend result | UI behavior |
|---|---|
| `202 collecting_baseline` | Progress and observed measurements; no forecast |
| `201 completed` | Returned next-day category/index, target time and SHAP reasons |
| `409` or `422` | Rejection reason; no saved-success claim |
| `502/503/504` with `observation_saved: true` | Record retained without a prediction; latest identical observation can be retried |
| Failed read or history refresh | Visible error; real/acknowledged observations never silently replaced by demo history |
| Malformed forecast after an acknowledged save | Saved observation retained, forecast withheld, refresh warning |

Forecast cards identify “Simulated example forecast” versus “Model-generated forecast” and show the full target time in UTC. Fixture advice is labeled “Example advisory.” Missing forecasts have a neutral “No forecast-based recommendation available.” message; current measurement concerns remain visible.

Retries preserve the exact timestamp, fields and journal, including after reload. `fatigue_points` is a prototype index, not a medical risk percentage. Classifier scores are uncalibrated; the separate regression score can disagree with the predicted category. SHAP explains the predicted model class, not causes of disease or fatigue.

## Reaction and attention scope

- Full reaction mode collects **60 responses** with random waits and a `>=500 ms` lapse rule. It is a count-limited prototype, not a timed five-minute PVT or a validated NASA/ISS task.
- Quick mode collects **10 responses** for demonstration. Its results cannot be transferred into the 60-response model fields.
- Losing focus or hiding the page invalidates an active run and requires a retake. Browser/device latency and transfer to synthetic training data are not clinically validated.
- Attention accuracy remains a **manual field**. The separate [Flanker scoring prototype](../ai/integration/flanker_prototype/README.md) is not a complete interactive task in this app.

The form starts blank for each new record. All 15 current measurements remain required. “Not measured” clears attention and blocks saving/inference until a value is supplied; it never inserts zero or copies an old result. Example autofill is available only in the explicitly selected offline demo. The next-cutoff mechanism is useful for advancing historical demo sequences but is not a measurement timestamp audit.

## Guidance is not Clinical Alert V2

`src/app/lib/metrics.ts`, `guide.ts`, and `insights.ts` contain the frontend's prototype measurement colors and example suggestions. These do not alter model predictions. They are not the V2 rule engine: they lack the full KSS/SP, symptom, quality, timing, verified baseline, repeat and unresolved-emergency state contract.

The separate Alert demo is predefined presentation content. Neither the existing guidance nor those five presets proves that all 14 medical scenarios pass. The full V2 engine remains deferred by the team's decision.

## Structure

```text
src/app/
  app.ts                 State, navigation, loading, submission, retry
  types.ts               Observation/history/forecast interfaces
  data/source.ts         API mapping and explicit offline-demo choice
  data/demo-data.ts      Synthetic example observations and archived example forecast
  lib/                   Measurement definitions, guidance, recommendations, time helpers
  components/            Dashboard, forms, charts, reaction prototype, alert demo
tests/source.test.ts     API mapping, save/error, and retry regressions
proxy.conf.cjs           Local same-origin API proxy
```

`scripts/serve-model.py` is a compatibility entry point to the ordinary Python service. The original global XGBoost exception suppression was removed. Use Python 3.12 and `ai/requirements.txt`; a model-load error must remain an error.

## Use of SI (AI tools)

**The team designed and developed Crew Health Console**, including its interface direction, measurement workflow and integration requirements. Karam Alhams supplied the frontend implementation; Majdi Abu Ahour coordinated the subsequent integration and verification. SI tools supported that team-led work by accelerating implementation, analysis, debugging, documentation and testing.

The provided **NASA Space Apps Challenge 2026 Project Submission Guide** (November 13, 2026) uses the term **Super Intelligence (SI)** for tools including machine learning, chatbots, image generation and large language models. The disclosures below identify the specific assistance used within the team's development process.

| Scope | Tool and disclosed use |
|---|---|
| Original frontend supplied by Karam Alhams as a ZIP | Its [original disclosure](docs/UPSTREAM_README_SNAPSHOT.md#use-of-si-ai-tools) states that **Claude (Anthropic)** assisted with dashboard code, SVG illustrations (astronaut, silhouette and watch), and Guide text from the team's idea and requirements, with team review. |
| Integration and later project work | Majdi Abu Ahour used **OpenAI ChatGPT/Codex** for frontend/backend integration, the synthetic-data generator and model workflow, error fixes, testing, Windows packaging, and documentation. The resulting synthetic records remain simulated data; AI assistance does not establish medical validity. |

The original frontend credit is retained alongside the later integration disclosure. The [project-wide disclosure](../docs/SUBMISSION_DISCLOSURE.md) and [provenance metadata](../PROVENANCE.json) document AI-assisted code and data; the [frontend archive record](../integration-reports/FRONTEND_PROVENANCE.json) records the supplied source separately.

Completed verification includes **81 UI checks, 48 end-to-end integration checks and 30 frontend regression tests**. Native Windows tests also exercised the packaged and installed app's real predictions, SHAP explanations and shutdown. See the [test evidence](../integration-reports/README.md). Further teammate testing is part of ongoing prototype development; these completed software checks do not establish clinical validation.

### Illustration labels and submission exports

The artwork now contains its own visible labels: **“SI-generated illustration”** is SVG text in [`astronaut-figure.ts`](src/app/components/astronaut-figure.ts), and **“SI-generated”** is SVG text in the watch in [`tile-visuals.ts`](src/app/components/tile-visuals.ts). The labels were added through code to the existing illustrations, without generating replacement artwork. They are part of the SVGs, rather than captions outside them. The app footer in [`app.ts`](src/app/app.ts) also acknowledges SI-assisted code and illustrations, and [`src/index.html`](src/index.html) contains a `si-disclosure` metadata tag.

The submission guide requires a **visible watermark on SI-generated images and videos**. Keep these labels visible when exporting an SVG or capturing the dashboard; a crop can still remove a label. Screenshots, slides and video must retain or add a clearly readable mark in the actual exported media. A README statement or hidden metadata alone does not satisfy that requirement. The [seven-slide presentation](../Project_SuperMoon_Final_Presentation.pdf) also identifies the astronaut and watch artwork in its screenshot caption. Checks of desktop/mobile rendering and standalone SVG exports are tracked in [the artwork verification report](../integration-reports/ARTWORK_WATERMARK_CHECKS.json); inspect that report's status before distributing a new build or export. This is not a claim that every historical screenshot or future crop is marked.

The guide also prohibits SI-generated content from using, containing or modifying **NASA branding or design elements, including NASA logos, flags and mission identifiers**. The current illustrations are generic astronaut/watch graphics.

## NASA resources, other sources and credits

- Frontend origin: Karam Alhams / `crew-health-console`; [archive provenance](../integration-reports/FRONTEND_PROVENANCE.json).
- Model/backend: the ASTRA-SHIELD team, [Space-apps](https://github.com/magdiemad5s/Space-apps).
- NASA [5 Hazards of Human Spaceflight](https://www.nasa.gov/hrp/hazards/) and [Human Spaceflight Risks](https://www.nasa.gov/hrp/risks/): background for the Guide and Body map's sleep, behavioral-health and cardiovascular context.
- NASA [Reaction Self Test background](https://spinoff.nasa.gov/Spinoff2013/hm_1.html): motivation for the reaction-time demonstration; it does not validate our count-limited task as the NASA/ISS test.
- Published background: [ISS sleep/neurobehavioral research](https://pmc.ncbi.nlm.nih.gov/articles/PMC8919197/), [Barger et al.](https://pmc.ncbi.nlm.nih.gov/articles/PMC4188436/), [adult sleep-duration consensus](https://pmc.ncbi.nlm.nih.gov/articles/PMC4434546/), and [brief PVT research](https://pmc.ncbi.nlm.nih.gov/articles/PMC3197786/).
- American Heart Association [tachycardia background](https://www.heart.org/en/health-topics/arrhythmia/about-arrhythmia/tachycardia--fast-heart-rate), cited by the Guide.

These NASA resources are used as public reference material, not as training datasets. The sources support the project background, not our exact demo task, thresholds, or medical validity. Their use does not imply NASA endorsement. Library licenses remain with Angular, Ionic, RxJS, TypeScript, and their dependencies. [Manrope source and license](https://github.com/google/fonts/tree/main/ofl/manrope) are available through Google Fonts; the font is by the Manrope Project Authors and is locally distributed under the [SIL Open Font License](public/licenses/manrope-OFL.txt).

All model-training data is synthetic. The full dataset contains 7,200 forecast rows from 120 virtual participants; the original fatigue training partition contains **5,040**, not all 7,200. Neither these records nor the offline-demo examples are NASA astronaut measurements. This local prototype has no authenticated multi-user deployment. See [integration decisions and limits](../docs/INTEGRATION_HANDOFF.md).
