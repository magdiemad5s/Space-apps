# Application integration verification

These checks use fictional integration observations and the existing model. They test software behavior, not clinical performance or model accuracy. **No training or test-partition evaluation was performed.**

| Check | Result | Evidence |
|---|---|---|
| Real Angular/browser → TypeScript → Python flow | 48 passed, zero browser JavaScript errors | [APP_INTEGRATION_CHECKS.json](APP_INTEGRATION_CHECKS.json) |
| Frontend API mapping/error/retry regressions | 19 passed | `frontend/tests/source.test.ts`; `npm test` |
| Frontend strict typecheck and production build | Passed | `npm run typecheck`, `npm run build` |
| Launcher helper/process tests | 9 passed | `scripts/test_launcher.py` |
| Actual startup, duplicate-start protection, shutdown and restart persistence | Passed | [LAUNCHER_INTEGRATION_CHECKS.json](LAUNCHER_INTEGRATION_CHECKS.json) |
| Original model and main dataset | Unchanged SHA-256 | [preserved-model-data.json](preserved-model-data.json) |
| Native Windows execution | **Not run in this Linux workspace** | Rehearsal required on the presentation laptop |
| Clinical Alert V2's 14 medical scenarios | **Not run** | Five preset UI examples are not a clinical engine |

The browser checks cover seven calibration records, eighth-record form submission, real category/index/SHAP rendering, invalid and duplicate input, preserved history, exact journal-aware retry after an actual model-unavailable backend and restart, explicit demo selection, calibration baseline visibility, and layouts at 320/375px. Network/read-failure simulations are named separately in the report. The five Alert demo states make no API/model calls and do not change actual observations or forecasts.

The example model output was **Moderate, index 33.1** for the fictional eighth-day request. That number is an integration observation, not accuracy, a risk percentage, or a new model evaluation.

## Reproduce

Use the normal setup first. From the project root:

```bash
cd frontend
npm test
npm run typecheck
npm run build
cd ..
.venv/bin/python scripts/test_launcher.py
```

For browser checks, install Playwright into a development environment and use a Chromium executable. Playwright is a test dependency, not required to run the application:

```bash
.venv/bin/python -m pip install playwright
./start.sh --seed-demo --no-browser --db-file .local/browser-checks/history_db_v2.json
```

In a second terminal:

```bash
.venv/bin/python scripts/test_app_integration.py --chromium /usr/bin/chromium
```

The supplied browser script was run on Linux and defaults to local ports 4200/8000, with temporary secondary backend port 3001. Use its `--help` for overrides. It adds uniquely named synthetic `DEMO_E2E_...` participants to the chosen test database, starts/stops a separate temporary backend for the outage test, and rewrites this directory's browser report/screenshots. It never needs the held-out ML test partition. Run it against isolated demo storage rather than a participant's actual history.

The model/data hashes and 51 browser-relevant source/artifact hashes were checked after verification. [FRONTEND_PROVENANCE.json](FRONTEND_PROVENANCE.json) records the user-supplied archive and original file hashes; it does not invent an upstream commit ID.

## Screenshots

- [Desktop overview](app-overview-desktop.png)
- [Mobile overview](app-overview-mobile.png)
- [Mobile forecast](app-forecast-mobile.png)

These screenshots use fictional observations with the actual local model computation. Services started for verification were stopped afterward; this is not a hosted deployment.
