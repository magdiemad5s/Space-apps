# Reproducing EXP006 without overwriting the experiment

Use a separate directory. The generator refuses to replace an existing cohort,
and training stages deliberately refuse repeated selection or holdout scoring.
Retain the published files as the historical experiment record.

The original run used Python 3.12.14, NumPy 2.3.5, pandas 2.2.3,
scikit-learn 1.8.0, joblib 1.5.3 and xgboost-cpu 3.4.1 on the managed workspace's
CPU. Models used two estimator threads. A GPU or external model API is not needed.

## 1. Create an isolated source tree

From the repository root, this copies the required original inputs and experiment
source into a **new sibling directory**. It does not copy previous experimental
data, training decisions, fitted models, or evaluation reports.

```bash
python - <<'PY'
from pathlib import Path
import shutil

repo = Path.cwd().resolve()
destination = repo.parent / "Space-apps-exp006-reproduction"
destination.mkdir(exist_ok=False)
for name in ["data", "astra_shield_ml"]:
    shutil.copytree(repo / "ai" / name, destination / "ai" / name)

artifacts = destination / "ai" / "artifacts"
artifacts.mkdir()
shutil.copy2(repo / "ai/artifacts/bundle.joblib", artifacts / "bundle.joblib")

relative = Path("ai/experimental/measurement_extension_006")
source = repo / relative
target = destination / relative
target.mkdir(parents=True)
for name in [
    "data_generator.py", "prepare_eda.py", "train_experiment.py",
    "predict_experimental.py", "render_results.py", "ORIGINAL_PRESERVATION.json",
    "EXPERIMENT_PLAN.json", "EXPERIMENT_PLAN.sha256",
    "draftgenerationplan.json", "requirements-experiment.txt",
    "NASA_AND_PARTNER_RESOURCES.csv", "NASA_RESOURCE_VERIFICATION.json",
]:
    shutil.copy2(source / name, target / name)
(target / "data").mkdir()
shutil.copy2(source / "data/generation_plan_sha256.txt",
             target / "data/generation_plan_sha256.txt")
print(destination)
PY
```

The copied original model is a protected reference whose hash is checked; this
experiment trains new models from the fresh cohort. Copying its file does not
make it a pretrained component of the new fit.

## 2. Install the environment and freeze the run

Enter the newly created directory:

```bash
cd ../Space-apps-exp006-reproduction
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r ai/experimental/measurement_extension_006/requirements-experiment.txt
cd ai/experimental/measurement_extension_006
python train_experiment.py preregister
python data_generator.py
python train_experiment.py prepare-plan
python prepare_eda.py
```

On Windows, use the corresponding `.venv\Scripts\Activate.ps1` activation and
Python 3.12 executable. The source scripts resolve their own directories; a
different terminal working directory does not redirect generator output.

Both generation-plan hashes are embedded in the generator. Do not edit a seed,
noise level, target, threshold, or planned feature bundle to improve the score.
A changed scientific question needs a separately versioned and reviewed plan.

## 3. Review the actual training-only graphs before fitting

Open these newly generated files and read
[`reports/eda/TRAIN_ONLY_EDA.json`](reports/eda/TRAIN_ONLY_EDA.json):

- `reports/eda/questionnaires_and_target.png`
- `reports/eda/sleep_extension_distributions.png`
- `reports/eda/extension_correlations.png`
- `data/generation_quality.json`

Inspect class balance, ordinal categories, sleep/nap distributions, related
features, and the generator assumptions. In the archived run, this visual review
was completed before any estimator fit and is recorded in
[`training/REVIEW_BEFORE_TRAINING.json`](training/REVIEW_BEFORE_TRAINING.json).

For a new run, create a **new, truthful** `training/REVIEW_BEFORE_TRAINING.json`
after reviewing those artifacts. Do not copy the historical sign-off: the new
prepared plan has its own hash. Required fields are:

```json
{
  "generation_review_complete": true,
  "training_only_eda_complete": true,
  "plan_sha256": "SHA256 of training/PLAN.json",
  "data_manifest_sha256": "SHA256 of data/split_manifest.json",
  "eda_report_sha256": "SHA256 of reports/eda/TRAIN_ONLY_EDA.json",
  "reviewed_at_utc": "actual review timestamp",
  "review_notes": ["Your actual observations and the resulting decisions"]
}
```

Replace the explanatory strings with the actual hashes and review details.
Setting flags is not a substitute for inspecting the graphs. The training guard
checks the review record against the data and prepared plan. If a review changes
the study design, stop and version the plan before training; do not alter the
published experiment's guard files.

## 4. Fit and evaluate the frozen stages

Only after the new review is complete:

```bash
python train_experiment.py cv
python train_experiment.py validation
python train_experiment.py test
```

Three participant-disjoint folds within the 84 training people choose one RF
extension. Imputation is fitted inside each fitting fold. The chosen extension
and fitted artifacts are frozen before either holdout is scored. Validation and
test are each evaluated once; neither causes refitting, reselection, filtering,
or generator changes. The test report includes the prespecified paired bootstrap
over participants, retaining each sampled participant's complete daily history.

The expected dataset partitions can be checked against the archived
[`data/split_manifest.json`](data/split_manifest.json). Numerical results are
deterministic under the recorded implementation/environment; timestamps, paths,
review records, and their hashes naturally differ in a new run. A repeated run
on the same synthetic test data is a reproduction, not new independent evidence.

Then inspect the frozen feature contract, run the training-row inference smoke
checks, and regenerate the results PDF without fitting another model:

```bash
python predict_experimental.py --list-features
python predict_experimental.py --check
python render_results.py
```

For a supplied feature object, use
`python predict_experimental.py --input feature_values.json`. The helper enforces
the selected model's exact allowlist and leaves the existing backend untouched.

## Charts, reports and intentional exclusions

Matplotlib and Pillow are pinned for plots; ReportLab renders the results PDF
using its built-in Helvetica fonts, so no additional font installation is needed.
SHAP supports explanations in the experimental prediction helper. Plot/PDF byte
identity can depend on platform and rendering metadata. These presentation tools
do not change the already frozen selection or model results.

The experiment does not provide real questionnaire responses, physiological nap
effects, actual timed PVT validity, or frontend integration. NASA/CSA links supply
background, not the numeric dataset or simulator coefficients. Refer to the
[data card](data/DATA_CARD.md) and [frozen generation plan](draftgenerationplan.json)
before interpreting a reproduced score.
