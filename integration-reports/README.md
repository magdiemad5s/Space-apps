# Application integration verification

These checks use fictional integration observations and the existing model. They test software behavior, not clinical performance or model accuracy. **No training or test-partition evaluation was performed.**

| Check | Result | Evidence |
|---|---|---|
| Real Angular/browser → TypeScript → Python flow | 48 passed, zero browser JavaScript errors | [APP_INTEGRATION_CHECKS.json](APP_INTEGRATION_CHECKS.json) |
| Frontend API mapping/error/retry regressions | 25 passed | `frontend/tests/source.test.ts`; `npm test` |
| Expanded final UI audit | 80 passed, zero uncaught JS errors | [UI_FINAL_CHECKS.json](UI_FINAL_CHECKS.json) |
| Bundled runtime on Linux (unfrozen) | 19 passed including real forecast, SHAP, and shutdown | [DESKTOP_RUNTIME_LINUX_CHECKS.json](DESKTOP_RUNTIME_LINUX_CHECKS.json) |
| Production static dashboard through bundled runtime | 15 passed, real form → model → SHAP | [DESKTOP_PRODUCTION_UI_CHECKS.json](DESKTOP_PRODUCTION_UI_CHECKS.json) |
| Bundled runtime lifecycle on Linux | 21 passed; duplicate launch, persistence, crash cleanup | [DESKTOP_LIFECYCLE_CHECKS.json](DESKTOP_LIFECYCLE_CHECKS.json) |
| Desktop runtime regressions | 13 passed on Linux; one Windows-only test deferred to CI | `desktop/runtime_tests.py` |
| Frontend strict typecheck and production build | Passed | `npm run typecheck`, `npm run build` |
| Launcher helper/process tests | 10 passed | `scripts/test_launcher.py` |
| Actual startup, duplicate-start protection, shutdown and restart persistence | Passed | [LAUNCHER_INTEGRATION_CHECKS.json](LAUNCHER_INTEGRATION_CHECKS.json) |
| Original model and main dataset | Unchanged SHA-256 | [preserved-model-data.json](preserved-model-data.json) |
| Native Windows portable and installed executables | **19 checks passed each** on a Windows runner | [Windows build evidence](windows-build-4/verification.json) |
| Inference-only deployment export | 130 original/deployment comparisons; six Windows reference cases passed | [Equivalence report](DEPLOYMENT_MODEL_EQUIVALENCE.json) |
| Interactive Windows laptop rehearsal | Still required | [Tester checklist](../docs/FRIEND_TEST_CHECKLIST.md) |
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

## Final UI audit

`python scripts/test_ui_final.py` exercises all five views at 320/375/768/1440px, all 16 trend series, body-map/Guide navigation, form ranges and time budgets, full/quick reaction-task behavior, alert presets, backend settings, and explicit offline sessions. Two discovered defects were fixed and retested: invalid backend addresses no longer replace settings, and impossible offline measurements are not appended. Reaction-task checks use an automated clock and fabricated responses, not measured human performance. Chart hover tooltips still lack a keyboard equivalent; this is not a full accessibility certification.

The Windows build workflow exercises the actual frozen executable, installs its installer, and repeats inference checks. Consult its matching artifact reports for native Windows results; Linux runtime checks alone do not establish Windows compatibility.

For the production runtime browser smoke, run `python scripts/test_desktop_ui.py --url http://127.0.0.1:4173` against an isolated running desktop runtime. The Linux lifecycle harness is `scripts/test_desktop_lifecycle.py`; its `--help` describes resource/interpreter overrides. These add synthetic records only to their test stores and retain reports under this directory.
