# Reproducing threshold experiment 007

The saved experiment is an archive. The runner refuses to overwrite its frozen
run record or results directory. Reproduce in a separate, new directory; do not
delete its guards to retune or overwrite the original analysis.

Use Python 3.12 with [requirements-experiment.txt](requirements-experiment.txt).
The models are trusted project joblib artifacts and must not be replaced with
untrusted uploads. Only inference and decision-rule arithmetic are performed.

From the repository root, stage the required source and inputs:

```bash
python - <<'PY'
from pathlib import Path
import json
import shutil

repo = Path.cwd().resolve()
ai = repo / "ai"
source = ai / "experimental/high_threshold_007"
destination = repo.parent / "astra-threshold007-reproduction"
destination.mkdir(exist_ok=False)
shutil.copytree(ai / "astra_shield_ml", destination / "ai/astra_shield_ml",
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
plan = json.loads((source / "PLAN.json").read_text())
for relative in plan["protected_scientific_inputs_sha256"]:
    target = destination / "ai" / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ai / relative, target)
target = destination / "ai/experimental/high_threshold_007"
target.mkdir(parents=True, exist_ok=True)
for name in ["PLAN.json", "PLAN.sha256", "run_thresholds.py",
             "test_thresholds.py", "render_report.py", "requirements-experiment.txt"]:
    shutil.copy2(source / name, target / name)
print(destination)
PY
```

This copies the original validation data and saved experiment 006 validation
probabilities. It does not supply raw test observations or test prediction files.
The copied manifests may contain historical test-file hashes; the runner never
loads those observations.

Create/activate a Python 3.12 environment in the new directory, install the
requirements, then run from its `ai/experimental/high_threshold_007` directory:

```bash
python -m pip install -r requirements-experiment.txt
python -m unittest -v test_thresholds
python run_thresholds.py freeze
python run_thresholds.py run
python render_report.py
```

The exact plan and scientific input hashes are checked before loading the model.
Every original argmax result must reproduce its archived validation metrics before
threshold comparisons proceed. The primary model is loaded once for inference;
the secondary analysis uses its existing validation scores. No model training,
calibration, test scoring or deployment occurs.

Inspect the resulting shortlist, full sweep, PR curve, confusion matrices and
report. This is a reproduction of an already viewed validation study, not new
independent evidence. Timestamps, PDF metadata and serialization hashes can differ
between runs; compare scientific inputs, settings, counts and metrics.

The archived independent numerical review can be rerun in the complete original
repository with `python independent_review.py`. It prints a summary and does not
overwrite the archived review. `--output` may name a new report file. It requires
the full original repository because it verifies all 255 preservation hashes in
addition to recomputing validation arithmetic. No fitted model is loaded by that
review script.
