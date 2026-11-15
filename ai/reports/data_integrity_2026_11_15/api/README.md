# API and feature integrity audit

This directory contains a reproducible, read-only check of the **current original synthetic dataset and serving contracts**. It does not train or promote a model, score new model performance, publish code, or change the service/data/artifacts. JSON and logs in this directory are refreshed when the audit runs.

## Prerequisites

- Python 3.12 with the dependencies in `ai/requirements.txt` installed.
- Node 24, including native TypeScript type stripping.
- The proposed TypeScript backend's local dependencies installed from its existing lock file.
- The packaged source data, fitted artifact, and saved contract fixtures in their existing locations under `ai/`.

From the repository root, an example setup is:

```sh
cd ai
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
(cd integration/backend_review/proposed_backend && npm ci)
```

The recorded run reused already installed dependencies; it was **not** a clean operating-system or fresh dependency-installation test.

## Reproduce

From `ai/`, using that Python environment:

```sh
python reports/data_integrity_2026_11_15/api/run_api_integrity.py --project .
```

In the managed cloud workspace, the existing FastAPI and Node test runners require approved execution outside the command sandbox because its event-loop/worker restrictions prevent normal execution. This is an execution-environment condition, not permission to change project data or models.

## What the counts mean

There are **37 existing tests**, consisting of 21 Python contract/API tests and 16 TypeScript feature-history unit tests. Strict TypeScript type checking also runs. These are separate from the additional all-row comparisons and adversarial-input cases:

- All 7,200 current ML rows pass the Python schema and reconstruct 26 numerical features: 187,200 scalar comparisons.
- TypeScript replays 8,040 raw observations: 840 calibration records plus 7,200 prediction-ready rows. The resulting 22 numerical inputs match 158,400 stored reference values.
- 158 additional invalid Python payload cases must fail both the strict schema and feature builder.
- 109 additional invalid TypeScript payload cases must fail; four checks distinguish zero counts from unknown/null counts.
- 36 representative unsupported field names and aliases, including the exact proposed KSS/SP, naps, caffeine, exercise, symptom and medication names, are tested separately. Optional PHQ-2/GAD-2 names are included in this unsupported inventory.

An unsupported-field rejection is recorded as **`EXPECTED_UNSUPPORTED`**, not as a failing test and not as an implementation of that measurement. The current custom 0–10 fatigue field is not a semantic substitute for KSS or Samn–Perelli simply because their numbers fit within its bounds.

## Limits and evidence

The Python suite and new-field checks exercise in-process FastAPI `TestClient` routes. TypeScript all-row/new-field checks call its exported validators and history helper, not its HTTP routes. The previous 29-check live loopback integration report is historical evidence; it is not rerun here.

All-row checks read test-partition **features only for integrity comparison**, not outcome scoring or model selection. No all-row predictions are computed. Existing Python tests use previously fitted models and training fixtures to verify response consistency and actual SHAP additivity; they do not fit models.

Source data, fitted artifact, service/backend source and historical evaluation reports are hash-checked for preservation. Results do not establish clinical validity, real astronaut performance, or correctness of all underlying biological assumptions. No actual Angular/Ionic frontend source was provided or tested.

Read `API_CONTRACT_INTEGRITY.json` for the combined results, `typescript_all_rows.json` for cross-language replay details, and the `.log` files for the existing suites and typecheck. `SUMMARY.txt` is the compact human-readable report.
