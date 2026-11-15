# Project status

**15 November 2026: integrated local software prototype.** The actual Angular/Ionic frontend is included and connected to the TypeScript backend and unchanged Python model. Application behavior is exercised with fictional integration fixtures, not human clinical validation.

## Implemented

- Original synthetic dataset, participant partitions, provenance, consistency audit and visual EDA.
- Causal baseline/history features, trained baseline models and genuine fatigue TreeSHAP.
- Python inference API and TypeScript backend with validation, history, calibration and outage-safe retry.
- Team frontend: daily form, forecast, SHAP, observation trends, guidance and reaction prototype.
- Same-origin frontend/API routing, explicit offline-demo choice, connection/error handling and exact journal-preserving retries.
- Seven calibration records before the eighth-day forecast; existing model artifact retained.
- Separate five-scenario Alert demo, clearly labeled fictional and independent of the model.
- Windows setup/start/demo launchers and Linux startup; production web build and routing guidance.
- Separate experimental studies, none automatically promoted into the running application.

New evidence is under [integration-reports](../../integration-reports/). It records actual browser/HTTP checks and their limits; historical AI reports remain separate. Launching or packaging the source does not publish a live site.

## Still to do

- Rehearse installation, prediction and shutdown on the actual Windows presentation laptop. Native Windows execution has not been verified in this Linux workspace.
- Confirm real measurement protocols and collection. Attention remains a manual accuracy field; the separate Flanker scoring module has no complete app UI.
- Implement the full Clinical Alert V2 engine if the team later resumes it. The 14 medical scenarios are **not run** by the five illustrative UI presets.
- Validate baseline provenance, device measurements, sleep timing, symptoms and repeat/state handling before claiming clinical rule implementation.
- Add authentication, authorized history access and suitable storage before public/multi-user hosting.
- Validate on representative real human longitudinal data; synthetic model scores and browser tests do not establish astronaut-health performance.

The model remains the original selected baseline. The threshold experiment and extra-measurement study remain exploratory; application integration does not retrain the model or adopt their candidates.
