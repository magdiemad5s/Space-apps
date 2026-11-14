#!/usr/bin/env python3
"""Verify the archive or reproduce one fixed study in a fresh local workspace.

This layout adapter preserves the original scripts, hashes and result files.
It never supplies final-test, raw-observation or full-dataset CSVs to a rerun.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ARCHIVE = Path(__file__).resolve().parent
AI = ARCHIVE.parent
MODULES = {
    "eda_first_001": "eda_first_experiment",
    "improvement_002": "improvement_experiment",
    "history_003": "history_feature_experiment",
    "noise_004": "noise_cleaning_experiment",
    "filter_validation_005": "filter_validation_experiment",
}
USES_VALIDATION = {"eda_first_001", "improvement_002", "filter_validation_005"}


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify() -> dict:
    manifest = json.loads((ARCHIVE / "ARCHIVE_MANIFEST.json").read_text())
    for item in manifest["files"]:
        path = ARCHIVE / item["path"]
        if not path.is_file() or sha256(path) != item["sha256"]:
            raise RuntimeError(f"Archive hash mismatch: {item['path']}")
    for experiment in ("improvement_002", "history_003", "noise_004", "filter_validation_005"):
        plan = json.loads((ARCHIVE / experiment / "plan.json").read_text())
        path = ARCHIVE / "source/astra_shield_ml" / f"{MODULES[experiment]}.py"
        if sha256(path) != plan["script_sha256"]:
            raise RuntimeError(f"Historical script hash mismatch: {experiment}")
    filtered = json.loads((ARCHIVE / "filter_validation_005/plan.json").read_text())
    if sha256(ARCHIVE / "source/astra_shield_ml/noise_cleaning_experiment.py") != filtered["reused_noise_rule_script_sha256"]:
        raise RuntimeError("Filtered-validation helper differs from its frozen plan")
    # The first study did not originally hash its source code. Its source is
    # covered by this archive manifest without inventing a historical hash.
    first = json.loads((ARCHIVE / "eda_first_001/FROZEN_BEFORE_TRAINING.json").read_text())
    for name, key in [("FEATURE_DECISIONS.json", "feature_decisions_sha256"),
                      ("EDA_GRAPH_REVIEW.txt", "graph_review_sha256")]:
        if sha256(ARCHIVE / "eda_first_001" / name) != first[key]:
            raise RuntimeError(f"EDA-first frozen input mismatch: {name}")
    return {"files_verified": len(manifest["files"]), "historical_script_hashes_verified": 4,
            "source_model_loaded": False, "final_test_read": False}


def prepare(experiment: str, output: Path) -> dict:
    verification = verify()
    output = output.expanduser().resolve()
    if output.exists():
        raise ValueError("Output must be a new directory; existing results are never overwritten.")
    if output == AI or AI in output.parents:
        raise ValueError("Choose a scratch output outside ai/ to preserve the committed archive.")
    inputs = [(AI / "data/train.csv", "data/train.csv"),
              (AI / "data/task_config.json", "data/task_config.json")]
    if experiment in USES_VALIDATION:
        inputs.append((AI / "data/validation.csv", "data/validation.csv"))
    if experiment in {"history_003", "noise_004", "filter_validation_005"}:
        inputs.append((AI / "artifacts/bundle.joblib", "artifacts/bundle.joblib"))
    if experiment in {"history_003", "noise_004"}:
        relative = "improvement_002/participant_folds.csv"
        inputs.append((ARCHIVE / relative, "experiments/" + relative))
    if experiment == "eda_first_001":
        for name in ("FEATURE_DECISIONS.json", "EDA_GRAPH_REVIEW.txt"):
            relative = f"eda_first_001/{name}"
            inputs.append((ARCHIVE / relative, "experiments/" + relative))
        inputs.append((AI / "reports/eda/data_quality_summary.json", "reports/eda/data_quality_summary.json"))
    if experiment == "filter_validation_005":
        inputs.append((AI / "artifacts/frozen_manifest.json", "artifacts/frozen_manifest.json"))
        for relative in ("eda_first_001/validation_predictions.csv", "noise_004/summary.json"):
            inputs.append((ARCHIVE / relative, "experiments/" + relative))
    for source, _ in inputs:
        if not source.is_file():
            raise FileNotFoundError(f"Required reproduction input is missing: {source}")
    # Verify original input bytes without inspecting held-out observations.
    frozen = json.loads((AI / "artifacts/frozen_manifest.json").read_text())
    for source, destination in inputs:
        expected = frozen.get("data_sha256", {}).get(destination)
        expected = expected or frozen.get("artifact_sha256", {}).get(destination)
        if destination == "data/task_config.json":
            expected = frozen["task_config_sha256"]
        if expected and sha256(source) != expected:
            raise RuntimeError(f"Original input hash mismatch: {destination}")
    output.mkdir(parents=True)
    shutil.copytree(ARCHIVE / "source/astra_shield_ml", output / "astra_shield_ml",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for source, destination in inputs:
        path = output / destination
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, path)
    assert not any((output / "data" / name).exists() for name in
                   ("test.csv", "raw_observations.csv", "astra_shield_synthetic_ml.csv"))
    command = [sys.executable, "-m", "astra_shield_ml." + MODULES[experiment]]
    # EDA-first derives ROOT from __file__ and has no --project-dir option.
    if experiment != "eda_first_001":
        command.extend(["--project-dir", str(output)])
    record = {"experiment": experiment, "output": str(output), "command": command,
              "copy_policy": "Required training/development inputs only; no final-test/raw/full CSV",
              "validation_supplied": experiment in USES_VALIDATION,
              "archive_verification": verification, "run_started": False,
              "inputs": [{"path": destination, "sha256": sha256(source)} for source, destination in inputs]}
    (output / "REPRODUCTION_SETUP.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("verify", help="Check archive bytes and historical source hashes; no training")
    for action in ("prepare", "run"):
        sub = commands.add_parser(action, help="Stage a fresh compatible workspace" + (" and run one study" if action == "run" else " without fitting"))
        sub.add_argument("experiment", choices=MODULES)
        sub.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "verify":
        print(json.dumps(verify(), indent=2))
        return
    record = prepare(args.experiment, args.output)
    if args.action == "prepare":
        print(json.dumps(record, indent=2))
        return
    environment = os.environ.copy()
    environment["PYTHONPATH"] = record["output"]
    record["run_started"] = True
    completed = subprocess.run(record["command"], cwd=record["output"], env=environment, check=False)
    record["exit_code"] = completed.returncode
    (Path(record["output"]) / "REPRODUCTION_SETUP.json").write_text(json.dumps(record, indent=2) + "\n")
    raise SystemExit(completed.returncode)


if __name__ == "__main__":
    main()
