# ASTRA-SHIELD AI

**Status: synthetic-data prototype, now connected to the team's Angular/Ionic frontend.** Use the [repository launcher guide](../docs/RUNNING.md) for the Windows/Linux application; the commands below remain useful for the model service alone. The supplied model is already trained. No GPU, external model API, or API key is needed for inference.

The primary task predicts **the following day's custom simulated fatigue self-report category** (`low`, `moderate`, or `high`). It does not establish medical risk or astronaut readiness. Separate components estimate fatigue score and reaction time, detect current physiological outliers, and classify generated journal text.

## Run the current model

The recorded environment used **Python 3.12 on Linux**. From the repository root:

```bash
cd ai
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m astra_shield_ml.predict examples/example_request.json
```

On Windows, prefer the root `Setup-Astra.cmd` and `Start-Astra.cmd`. The pinned `xgboost-cpu==3.4.1` release provides Windows wheels, but this workspace has only executed the stack on Linux. Keep Python 3.12 and the serialized model's pinned dependencies; do not hide deserialization errors or assume an untested dependency substitution works.

Start the private model service from `ai/` with that environment active:

```bash
python -m uvicorn astra_shield_ml.api:app --host 127.0.0.1 --port 8000
```

| Endpoint | Purpose |
|---|---|
| `GET /health` | Model availability and loaded tasks |
| `GET /v1/model-info` | Input definitions and model information |
| `POST /v1/predict` | Predict from one model request |
| `POST /v1/predict/batch` | Predict up to 64 model requests |
| `/docs` | Interactive FastAPI documentation |

Use [`examples/example_request.json`](examples/example_request.json) for the Python interface. Its baseline/history fields have already been calculated. The frontend submits a different, raw-measurement contract to the TypeScript backend.

## Run the reviewed TypeScript backend

This is a proposed update of the teammate's application backend, prepared for review and integration. It is included under `integration/` so it can be merged into the team's working backend. **Use the entire folder**, including `featureHistory.ts` and `modelClient.ts`.

With the Python worker running, open another terminal. **Node.js 22 or newer** is required; local checks used Node 24.

```bash
cd ai/integration/backend_review/proposed_backend
npm ci
AI_SERVICE_URL=http://127.0.0.1:8000 npm start
```

PowerShell environment-variable syntax:

```powershell
$env:AI_SERVICE_URL = "http://127.0.0.1:8000"
npm start
```

The application API listens on port 3000 by default:

- `GET /api/v1/health`
- `POST /api/v1/assess`
- `GET /api/v1/astronauts/:id/history`

Run the included synthetic sequence in another terminal from the backend folder:

```bash
node demo.mjs
```

It sends nine historical simulated days, so a demonstration does not require waiting a week. It refuses to overwrite an already populated demo participant. These fixtures must be presented as simulated records.

Both services need to be reachable from their callers. `localhost` on a teammate's laptop or an Ionic device does not refer to another computer. The backend's default history file is `history_db_v2.json`; set `DB_FILE` to choose a writable location. This is a local, single-process prototype store. Authentication, production hosting, and multi-instance storage are application work still to complete.

See the [frontend contract](docs/FRONTEND_INTEGRATION.md), [measurement CSV](integration/backend_review/proposed_backend/FRONTEND_MEASUREMENTS.csv), and [full backend instructions](integration/backend_review/proposed_backend/README.txt).

## Data and feature contract

The original longitudinal simulation contains **7,200 forecast rows from 120 virtual participants**, with 60 daily observations each. Download the standalone [original CSV](data/astra_shield_synthetic_ml.csv) or use the already separated partitions described in the [data guide](data/README.md). The separate uploaded V2/V3 datasets and real research records were not merged into this model.

| Partition | Participants | Rows | Use |
|---|---:|---:|---|
| Train | 84 | 5,040 | Fitting; grouped development experiments |
| Validation | 18 | 1,080 | Candidate comparison; already reused during development |
| Historical final test | 18 | 1,080 | Evaluated after the original model was frozen |

The **70/15/15 split is by participant**, not by shuffling an individual's days across partitions. The fatigue target is exactly 24 hours later. Its categories use custom cutoffs: below 4, 4 to below 7, and 7 or above on a simulated 0–10 score.

The classifier uses **26 predictors**:

- 15 current measurements.
- Four fixed means from seven earlier calibration days.
- Four current-versus-baseline changes, calculated by the Python service.
- Three averages from the preceding three days, excluding today and future days.

The backend supplies 22 numeric inputs; Python derives the other four. Participant identifiers, target columns, future timestamps, and provenance metadata are excluded from prediction inputs. The CSV has 46 columns because it also carries these grouping, audit, and target fields.

[`data/data_dictionary.csv`](data/data_dictionary.csv) defines units and timing. [`data/task_config.json`](data/task_config.json) contains the allowlists. [`data/raw_observations.csv`](data/raw_observations.csv) is a synthetic causality-audit file containing calibration and future-outcome records; **it is not a training table**. Running the generator writes files beside it, so use a fresh directory for generation experiments.

## Models and output meaning

| Component | Method | Output scope |
|---|---|---|
| Next-day fatigue category | Random Forest, selected against XGBoost | Custom simulated self-report category |
| Next-day fatigue score | Histogram gradient boosting | Custom simulated 0–10 score |
| Next-day median reaction time | Histogram gradient boosting | Simulated PVT-like task measurement |
| Current physiological outliers | Isolation Forest | Simulator-injected HR/HRV deviations |
| Current journal stress | TF-IDF + logistic regression | Experimental generated-language category |

The selected Random Forest has 200 trees, maximum depth 14, minimum leaf size 8, balanced class weights, and seed `20261114`. Its median imputer is fitted on training inputs only. Journal predictions remain separate from the numeric fatigue classifier.

The single Python entry point is `ModelService().predict(payload)`:

- `label`: next-day fatigue category.
- `points`: `round(50 × P(moderate) + 100 × P(high), 1)`, a **prototype severity index**, not a medical-risk percentage or calibrated confidence.
- `reasons`: three actual TreeSHAP explanations for the predicted fatigue class. They do not explain the other model components or establish causes.

The category and continuous fatigue score come from separate models, so their bands can disagree. Load only trusted `joblib` artifacts; the files contain Python serialization.

## Recorded results

| Evaluation | Random Forest Macro-F1 | Relevant comparison |
|---|---:|---|
| Original validation, 1,080 rows | **0.5273** | XGBoost 0.4857 |
| Historical final test, 1,080 rows | **0.5285** | Persistence 0.5181 |
| Three-fold participant CV inside TRAIN, 5,040 rows | **0.5163** | Persistence 0.5140 |

These are different evaluation setups. **Macro-F1 is not accuracy.** Historical test accuracy was 61.85%, below the majority-class accuracy of 67.04%; the selected objective was Macro-F1. Historical High-fatigue recall was 45.77%, and the gain over persistence was uncertain.

The reduced 17-feature model, extra history features, and filtering treatments are documented under [`experimental/`](experimental/README.md). The final fixed-filter comparison retained all 1,080 validation records and scored **0.5178**, below the original **0.5273**. The demo continues to load [`artifacts/bundle.joblib`](artifacts/bundle.joblib); experimental artifacts are separate.

All metrics describe this simulator. Real astronaut performance and clinical validity have not been established. Application integration is checked separately in the [application reports](../integration-reports/); it is not a new evaluation of model accuracy. See [findings and limitations](docs/FINDINGS.md).

## Verification and reproducibility

Historical local verification includes 21 Python contract tests, 16 TypeScript feature-history tests, and 29 real HTTP backend-to-model checks. Those archived reports predate the actual frontend. New browser/application checks are recorded separately under [integration-reports](../integration-reports/) and use isolated synthetic history.

The repository layout passed these checks again using the existing pinned environments. See [packaging checks](docs/PACKAGING_CHECKS.json) and [packaged integration checks](docs/PACKAGED_INTEGRATION_CHECKS.json). This verifies the packaged paths and contracts; it is not a clean operating-system installation or a frontend test.

From `ai/`, with the Python environment active:

```bash
python -m unittest discover -s tests -v
python integration/backend_review/verify_live_integration.py --model-project .
```

Install the backend's Node dependencies before the live integration command. That verifier uses temporary history storage, starts local test services, and stops them afterward. From the backend folder:

```bash
npm run typecheck
npm test
npm run build
```

For EDA/report dependencies:

```bash
python -m pip install -r requirements-report.txt
```

Use the [experimental archive instructions](experimental/README.md) to verify frozen results or rerun a study in a fresh output directory. Routine setup does not require retraining or rerunning final-test evaluation. Historical final-test results must not become a tuning target.

The initial training preceded the standalone formal EDA report. The later EDA follow-up reviewed graphs and froze feature decisions before its new fits; both stages are documented in the [workflow findings](docs/FINDINGS.md#pipeline-and-eda-chronology).

## Application handoff

The team's actual frontend is included under `frontend/` and uses this backend/model contract through the root launchers. Rehearse on the actual Windows presentation laptop, and keep the full clinical engine and real-world validation separate from the working software demo. The [status checklist](docs/STATUS.md) tracks those limits.
