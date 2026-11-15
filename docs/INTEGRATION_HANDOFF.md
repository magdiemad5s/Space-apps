# Frontend integration handoff

## Goal

Connect the existing 26-feature synthetic-data model to the team's actual Angular/Ionic interface, make it practical to run on a Windows presentation laptop, document Linux startup, and keep the same frontend usable as a web application. The user selected a one-click Windows launcher after dependency setup; a self-contained executable was not requested for this delivery.

The model is not retrained, replaced, or threshold-tuned during this integration. The full Clinical Alert V2 engine is deferred. Its appearance is illustrated with five predefined scenarios, separate from real inference.

## Teammate's starting point

Source: <https://github.com/Karam-Eyad/crew-health-console>, imported from the user-supplied `crew-health-console-main.zip`. GitHub access was unavailable, so this is an archive snapshot rather than a verified checkout of a particular commit. [FRONTEND_PROVENANCE.json](../integration-reports/FRONTEND_PROVENANCE.json) records the archive hash and original file hashes.

The teammate provided Angular 22/Ionic 9 screens, the astronaut illustration/body map, 15-measurement form, history/trend components, forecast displays, SHAP explanation rendering, guidance/source text, and a 60-response/10-response reaction prototype. The original documentation correctly distinguished synthetic model training and a prototype severity index from medical probability. Original SI/AI-assistance disclosures and team credits remain in the frontend.

## Integration changes

- Import the app under `frontend/`, keeping its design and components.
- Route browser calls through same-origin `/api/v1`; local Angular proxy uses `BACKEND_URL`, and a web deployment can use an ordinary reverse proxy.
- Make offline examples an explicit choice. Backend/history failures remain visible instead of silently replacing records with simulated history.
- Preserve acknowledged saves if refreshing history fails; withhold malformed forecasts instead of inventing zero values or declaring successful inference.
- Preserve exact observation timestamps, measurements, and journal text for retry after a model outage, including after a page reload.
- Correct mapping of nullable results, SHAP's neutral direction, and object-shaped training-range warnings.
- Avoid displaying a future calibration baseline against the first six calibration records.
- Prevent the quick 10-response reaction demo from filling model inputs intended for 60 responses; interrupted/hidden/blurred runs require a retake.
- State that the reaction task is count-limited, not a timed five-minute PVT or a validated NASA protocol. Attention remains manual input.
- Label existing measurement colors and recommendations as illustrative dashboard guidance. They differ from V2 and lack its full clinical input/quality/state requirements.
- Add an independent Alert demo tab with five fictional states; no new medical measurements enter the existing model.
- Bundle the original Manrope typeface locally to preserve the teammate's typography without external font fetching; replace the model wrapper's blanket XGBoost exception suppression with the ordinary trusted model service.
- Add Windows/Linux setup, supervised startup, explicit synthetic seeding, logs, port checks and storage paths.

## What to tell the team

The dashboard connects to the TypeScript backend, which builds calibration/history inputs and calls the Python model. The current-alert preview is predefined UI behavior, not a trained model and not an implemented clinical decision engine. The 14 cases in the medical acceptance PDF still require a real V2 engine and tests; browser checks of the five demo presets do not count as those medical tests.

The visible measurement guidance inherited from the frontend has its own prototype thresholds. For example, its HR guidance uses an absolute value and its HRV guidance uses its own relative threshold. These must not be presented as implementation of V2's resting-HR delta, RMSSD, quality-gate, urgent-state, and symptom rules.

The supplied observation fixtures and existing training data are synthetic. A live connection and real model calculation describe the software execution, not real astronaut observations. Real-data use still needs valid comparable measurements, a suitable protocol, and independent evaluation.

## Platform and web scope

- Windows: `Setup-Astra.cmd` once, then `Start-Demo.cmd` or `Start-Astra.cmd`. Native Windows execution must be checked on the team's laptop.
- Linux: `python3.12 scripts/setup.py`, then `./start.sh --seed-demo`.
- Web: `frontend` can be built to static files. A host must route `/api/v1` to the backend; no frontend rewrite or desktop-only fork is required.
- Public/multi-user hosting and a standalone installer are not completed by this local launcher.

See [RUNNING.md](RUNNING.md) and [WEB_DEPLOYMENT.md](WEB_DEPLOYMENT.md).
