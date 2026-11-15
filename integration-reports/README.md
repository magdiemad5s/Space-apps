# Application integration verification

These checks use fictional integration observations and the existing model. They test software behavior, not clinical performance or model accuracy. **No training or test-partition evaluation was performed.**

| Check | Result | Evidence |
|---|---|---|
| Real Angular/browser → TypeScript → Python flow | 48 passed, zero browser JavaScript errors | [APP_INTEGRATION_CHECKS.json](APP_INTEGRATION_CHECKS.json) |
| Frontend API mapping/error/retry regressions | 30 passed | `frontend/tests/source.test.ts`; `npm test` |
| Focused submission UI/data-entry fixes | 28 passed, zero browser JavaScript errors | [SUBMISSION_SAFETY_CHECKS.json](SUBMISSION_SAFETY_CHECKS.json) |
| Expanded final UI audit | 81 passed, zero uncaught JS errors | [UI_FINAL_CHECKS.json](UI_FINAL_CHECKS.json) |
| Bundled runtime on Linux (unfrozen) | 19 passed including real forecast, SHAP, and shutdown | [DESKTOP_RUNTIME_LINUX_CHECKS.json](DESKTOP_RUNTIME_LINUX_CHECKS.json) |
| Production static dashboard through bundled runtime | 15 passed, real form → model → SHAP | [DESKTOP_PRODUCTION_UI_CHECKS.json](DESKTOP_PRODUCTION_UI_CHECKS.json) |
| Bundled runtime lifecycle on Linux | 21 passed; duplicate launch, persistence, crash cleanup | [DESKTOP_LIFECYCLE_CHECKS.json](DESKTOP_LIFECYCLE_CHECKS.json) |
| Desktop runtime regressions | 13 passed on Linux; one Windows-only case omitted here and exercised in CI | `desktop/runtime_tests.py` |
| Frontend strict typecheck and production build | Passed | `npm run typecheck`, `npm run build` |
| Embedded artwork labels and standalone exports | 28 rendered checks passed at 1440/768/375/320px; no browser errors | [ARTWORK_WATERMARK_CHECKS.json](ARTWORK_WATERMARK_CHECKS.json) |
| Launcher helper/process tests | 10 passed | `scripts/test_launcher.py` |
| Actual startup, duplicate-start protection, shutdown and restart persistence | Passed | [LAUNCHER_INTEGRATION_CHECKS.json](LAUNCHER_INTEGRATION_CHECKS.json) |
| Original model and main dataset | Unchanged SHA-256 | [preserved-model-data.json](preserved-model-data.json) |
| Native Windows portable and installed executables | **19 checks passed each** on a Windows runner | [Windows build evidence](windows-build-6/verification.json) |
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

- [Current desktop overview with embedded artwork labels](dashboard-current.png)
- [Current mobile overview with embedded artwork labels](dashboard-current-mobile.png)
- [Watch label detail](watch-watermark-detail.png)
- [Labeled standalone PNG and SVG artwork](../docs/media/)
- [Mobile forecast](app-forecast-mobile.png)

These screenshots use fictional observations with the actual local model computation. Services started for verification were stopped afterward; this is not a hosted deployment.

Historical test captures are retained with their original reports and hashes. Use the current labeled exports above for presentation media. The artwork check confirms the label is part of each SVG, fits inside its bounds across the checked viewport sizes, and survives standalone SVG/PNG export; it does not validate future crops or recordings.

## Final UI audit

`python scripts/test_ui_final.py` exercises all five views at 320/375/768/1440px, all 16 trend series, body-map/Guide navigation, form ranges and time budgets, full/quick reaction-task behavior, alert presets, backend settings, and explicit offline sessions. Two discovered defects were fixed and retested: invalid backend addresses no longer replace settings, and impossible offline measurements are not appended. Reaction-task checks use an automated clock and fabricated responses, not measured human performance. Chart hover tooltips still lack a keyboard equivalent; this is not a full accessibility certification.

The Windows build workflow exercises the actual frozen executable, installs its installer, and repeats inference checks. Consult its matching artifact reports for native Windows results; Linux runtime checks alone do not establish Windows compatibility.

For the production runtime browser smoke, run `python scripts/test_desktop_ui.py --url http://127.0.0.1:4173` against an isolated running desktop runtime. The Linux lifecycle harness is `scripts/test_desktop_lifecycle.py`; its `--help` describes resource/interpreter overrides. These add synthetic records only to their test stores and retain reports under this directory.

## Submission fixes, November 15

The [focused safety regression](SUBMISSION_SAFETY_CHECKS.json) checks blank daily inputs, unmeasured attention blocking, fixture/model provenance, neutral missing-forecast guidance and isolated alert scenarios. It also exercises one uninterrupted scripted 60-response task → transfer → save → retrieve → actual model forecast/SHAP sequence. These 28 checks and the updated 81-check UI suite passed with fictional data in a separate database. The reaction clock is automated; this does not validate device timing or human performance.

Reproduce after starting the app against a separate synthetic database:

```bash
python scripts/test_submission_safety.py --isolated-db /absolute/path/to/your/separate/history_db_v2.json
```

The supplied path must be the database used by the running backend. The script verifies the new fixture participant is written there and refuses a store containing non-demo identities. See [the fix record](../docs/SUBMISSION_FIXES.md) for the changes and remaining prototype scope.
