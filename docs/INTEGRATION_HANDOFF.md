# Frontend integration handoff

## Goal

Connect the existing 26-feature synthetic-data model to the team's actual Angular/Ionic interface, make it practical to run on a Windows presentation laptop, document Linux startup, and keep the same frontend usable as a web application. The delivery includes source launchers and a [self-contained Windows installer](../desktop/README.md) with bundled Python, Node and the selected models.

The model is not retrained, replaced, or threshold-tuned during this integration. The full Clinical Alert V2 engine is deferred. Its appearance is illustrated with five predefined scenarios, separate from real inference.

## Teammate's starting point

Source: <https://github.com/Karam-Eyad/crew-health-console>, imported from the user-supplied `crew-health-console-main.zip`. GitHub access was unavailable, so this is an archive snapshot rather than a verified checkout of a particular commit. [FRONTEND_PROVENANCE.json](../integration-reports/FRONTEND_PROVENANCE.json) records the archive hash and original file hashes.

The teammate provided Angular 22/Ionic 9 screens, the astronaut illustration/body map, 15-measurement form, history/trend components, forecast displays, SHAP explanation rendering, guidance/source text, and a 60-response/10-response reaction prototype. The original documentation correctly distinguished synthetic model training and a prototype severity index from medical probability. Original SI/AI-assistance disclosures and team credits remain in the frontend.

## Integration changes

- Import the app under `frontend/`, keeping its design and components.
- Route browser calls through same-origin `/api/v1`; local Angular proxy uses `BACKEND_URL`, and a web deployment can use an ordinary reverse proxy.
- Make offline examples an explicit choice. Backend/history failures remain visible instead of silently replacing records with simulated history.
- Start daily measurement fields blank. A simulated fill button exists only in explicit offline demo mode; ordinary Check-in does not copy yesterday's measurements.
- Require an external attention-accuracy value. **Not measured** clears that field and blocks saving/forecasting; incomplete records are not stored as drafts.
- Label simulated example forecasts separately from model-generated forecasts, and use neutral guidance when a record has no forecast.
- Preserve acknowledged saves if refreshing history fails; withhold malformed forecasts instead of inventing zero values or declaring successful inference.
- Preserve exact observation timestamps, measurements, and journal text for retry after a model outage, including after a page reload.
- Correct mapping of nullable results, SHAP's neutral direction, and object-shaped training-range warnings.
- Avoid displaying a future calibration baseline against the first six calibration records.
- Prevent the quick 10-response reaction demo from filling model inputs intended for 60 responses; interrupted/hidden/blurred runs require a retake.
- State that the reaction task is count-limited, not a timed five-minute PVT or a validated NASA protocol. Attention remains manual input.
- Label existing measurement colors and recommendations as illustrative dashboard guidance. They differ from V2 and lack its full clinical input/quality/state requirements.
- Add an independent Alert demo tab with five fictional states and hide unrelated selected-record context there; no new medical measurements enter the existing model.
- Bundle the original Manrope typeface locally to preserve the teammate's typography without external font fetching; replace the model wrapper's blanket XGBoost exception suppression with the ordinary trusted model service.
- Add Windows/Linux setup, supervised startup, explicit synthetic seeding, logs, port checks and storage paths. The 0.1.1 presentation launch paths select a separate demo store rather than the normal history file.

## What to tell the team

The dashboard connects to the TypeScript backend, which builds calibration/history inputs and calls the Python model. The current-alert preview is predefined UI behavior, not a trained model and not an implemented clinical decision engine. The 14 cases in the medical acceptance PDF still require a real V2 engine and tests; browser checks of the five demo presets do not count as those medical tests.

The visible measurement guidance inherited from the frontend has its own prototype thresholds. For example, its HR guidance uses an absolute value and its HRV guidance uses its own relative threshold. These must not be presented as implementation of V2's resting-HR delta, RMSSD, quality-gate, urgent-state, and symptom rules.

The supplied observation fixtures and existing training data are synthetic. A live connection and real model calculation describe the software execution, not real astronaut observations. Real-data use still needs valid comparable measurements, a suitable protocol, and independent evaluation.

Public demonstrations, repository files, and screenshots must use synthetic records. Do not upload real human health observations or journals. The new demo directory does not automatically migrate or delete records from an older installation.

## Platform and web scope

- Windows: the [0.1.0 prototype installer](https://github.com/magdiemad5s/Space-apps/releases/tag/v0.1.0-prototype) passed native Windows checks. Version **0.1.1** with these latest UI and storage changes is being built and needs its own matching verification evidence. From source, run `Setup-Astra.cmd` once and then `Start-Demo.cmd` or `Start-Astra.cmd`. Interactive rehearsal on the team's laptop remains part of the handoff.
- Presentation storage: `Start-Demo.cmd` uses `.local/demo/history_db_v2.json`; the 0.1.1 installer Demo shortcut and post-install launch use `%LOCALAPPDATA%\ASTRA-SHIELD\demo`. Normal startup retains its existing default store.
- Linux: `python3.12 scripts/setup.py`, then `./start.sh --seed-demo --db-file .local/demo/history_db_v2.json`.
- Web: `frontend` can be built to static files. A host must route `/api/v1` to the backend; no frontend rewrite or desktop-only fork is required.
- Public/multi-user hosting remains separate work. The Windows installer opens the same dashboard locally in the browser; it does not publish a web deployment.

See [RUNNING.md](RUNNING.md), [WEB_DEPLOYMENT.md](WEB_DEPLOYMENT.md) and the [submission disclosure](SUBMISSION_DISCLOSURE.md) for team/tool credits and final presentation requirements.
