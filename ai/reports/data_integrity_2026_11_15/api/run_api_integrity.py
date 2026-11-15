"""Reproduce read-only dataset/serving-contract integrity checks.

No fitting, promotion, threshold selection or model-performance evaluation.
The original37unit/API tests execute inference on existing training fixtures.
The7,200-row replay uses only schema/feature construction, not model prediction.
Run using the project's Python dependencies and Node24; local TS deps must exist.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd


DEFAULT_ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def main(project):
    project = Path(project).resolve()
    sys.path.insert(0, str(project))
    from astra_shield_ml.features import INPUT_FIELDS, CURRENT_FIELDS, FEATURE_COLUMNS, prepare_features
    from astra_shield_ml.api import Observation
    from pydantic import ValidationError
    protected_paths = [
        project / "artifacts/bundle.joblib",
        *[project / "data" / name for name in ["astra_shield_synthetic_ml.csv", "raw_observations.csv", "train.csv", "validation.csv", "test.csv"]],
        *[project / "astra_shield_ml" / name for name in ["api.py", "features.py", "service.py"]],
        *[project / "integration/backend_review/proposed_backend" / name for name in ["server.ts", "modelClient.ts", "featureHistory.ts"]],
        project / "reports/test_metrics.json", project / "reports/test_predictions.csv",
        project / "integration/backend_review/LIVE_INTEGRATION_VERIFICATION.json",
    ]
    before = {str(p.relative_to(project)): sha(p) for p in protected_paths}
    report = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(), "status": "running",
        "scope": "Original synthetic dataset serving/schema/causal-feature consistency and existing API/unit tests",
        "model_fitted": False, "model_promoted": False, "new_model_performance_evaluation": False,
        "all_row_replay_uses_test_partition_features_for_integrity_only": True,
        "all_row_model_predictions_computed": False,
        "frontend_application_tested": False,
        "limitations": [
            "Consistency checks do not establish clinical validity or identify all sensor/biological errors.",
            "No actual Angular/Ionic application source was supplied or tested.",
            "Specific new-field checks are identified as schema-validator or in-process FastAPI route checks, not live TCP tests.",
            "Historical live29check reports were not rerun or changed in this audit.",
            "Existing installed Python/Node dependencies are reused; this is not a clean operating-system installation.",
        ], "failures": [],
    }
    try:
        stream = io.StringIO()
        suite = unittest.defaultTestLoader.discover(str(project / "tests"), pattern="test_contracts.py")
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
        (OUT / "python_21_contracts.log").write_text(stream.getvalue())
        report["existing_python_tests"] = {"run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors), "skipped": len(result.skipped), "http_scope": "FastAPI TestClient in-process routes, not external TCP"}
        assert result.testsRun == 21 and result.wasSuccessful()

        backend = project / "integration/backend_review/proposed_backend"
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        node_tests = subprocess.run(["npm", "test"], cwd=backend, env=env, text=True, capture_output=True, timeout=90)
        (OUT / "typescript_16_contracts.log").write_text(node_tests.stdout + node_tests.stderr)
        import re
        assert node_tests.returncode == 0
        assert re.search(r"(?:#|ℹ)\s*tests\s+16\b", node_tests.stdout)
        report["existing_typescript_tests"] = {"run": 16, "failures": 0, "scope": "feature-history validation and saved Python reference parity; no HTTP server"}
        compile_result = subprocess.run(["npm", "run", "typecheck"], cwd=backend, env=env, text=True, capture_output=True, timeout=60)
        (OUT / "typescript_strict_typecheck.log").write_text(compile_result.stdout + compile_result.stderr)
        assert compile_result.returncode == 0
        report["typescript_strict_typecheck"] = "passed"

        cols = ["record_id", "participant_id", "observation_timestamp_utc", "mission_day", "split", "journal_text"] + FEATURE_COLUMNS
        rows = pd.read_csv(project / "data/astra_shield_synthetic_ml.csv", usecols=cols)
        assert len(rows) == 7200
        prepared, schema_failures = [], []
        for row in rows.to_dict("records"):
            payload = {key: row[key] for key in INPUT_FIELDS}
            payload.update({key: row[key] for key in ["participant_id", "observation_timestamp_utc", "journal_text"]})
            try:
                Observation.model_validate(payload)
                prepared.append(prepare_features(payload).iloc[0].to_numpy(dtype=float))
            except Exception as exc:
                schema_failures.append({"record_id": row["record_id"], "error": str(exc)})
        assert not schema_failures, schema_failures[:3]
        matrix = np.asarray(prepared)
        errors = np.abs(matrix - rows[FEATURE_COLUMNS].to_numpy(dtype=float))
        assert np.isfinite(matrix).all() and np.all(errors <= 1e-6)
        report["python_all_rows"] = {"strict_schema_rows": len(prepared), "feature_rows": len(prepared), "numeric_features_per_row": 26,
                                     "scalar_feature_values_compared": int(errors.size), "maximum_absolute_error": float(errors.max()),
                                     "schema_failures": schema_failures, "split_counts": rows.split.value_counts().to_dict()}
        sample = rows.iloc[0].to_dict()
        payload = {key: sample[key] for key in INPUT_FIELDS}
        unsupported = {
            "KSS": 5, "KSS_score": 5, "kss_score": 5, "SP": 3, "samn_perelli_score": 3,
            "kss_sleepiness_score": 5, "samn_perelli_fatigue_score": 3,
            "nap_start_time_utc": None, "nap_end_time_utc": None,
            "caffeine_mg_last_6h": 0, "exercise_minutes_last_2h": 0,
            "acute_symptoms_present": False, "medication_use": False,
            "phq2_score": 0, "gad2_score": 0,
            "sleep_onset_time_utc": "2026-01-01T23:00:00Z", "wake_time_utc": "2026-01-02T07:00:00Z",
            "time_awake_hours": 10, "nap_start_utc": None, "nap_end_utc": None, "nap_duration_minutes": 0,
            "total_sleep_24h_hours": 8, "total_sleep24_hours": 8, "waso_minutes": 0,
            "wake_after_sleep_onset_minutes": 0, "sleep_target_hours": 8, "sleep_deficit_3day_hours": 0,
            "caffeine_last_6h_mg": 0, "caffeine_6h_mg": 0, "exercise_last_2h_minutes": 0,
            "acute_symptoms": [], "medication": [], "medications": [],
            "reaction_time_false_starts_count": 0, "pvt_false_starts_count": 0, "collection_context": {},
        }
        invalid_cases = 0
        def must_reject(value):
            for check in (Observation.model_validate, prepare_features):
                try:
                    check(value)
                except (ValidationError, ValueError, TypeError):
                    continue
                raise AssertionError("Invalid model payload was unexpectedly accepted")
        for key in INPUT_FIELDS:
            missing = dict(payload); del missing[key]
            must_reject(missing); invalid_cases += 1
            for value in [None, "1", True, float("nan"), float("inf"), -float("inf")]:
                must_reject({**payload, key: value}); invalid_cases += 1
        for field in ["awakenings_count", "reaction_time_lapses_count"]:
            for value in [1.5, -1]:
                must_reject({**payload, field: value}); invalid_cases += 1
        report["python_invalid_input_cases_rejected_by_both_schema_and_feature_builder"] = invalid_cases
        from fastapi.testclient import TestClient
        from astra_shield_ml.api import app
        new_field_checks = []
        with TestClient(app) as client:
            for field, value in unsupported.items():
                extra = {**payload, field: value}
                must_reject(extra)
                response = client.post("/v1/predict", json=extra)
                assert response.status_code == 422
                new_field_checks.append({"field": field, "classification": "EXPECTED_UNSUPPORTED", "python_schema_rejected": True,
                                         "feature_builder_rejected": True, "fastapi_in_process_http_status": 422})
        report["new_measurement_fields"] = new_field_checks
        report["custom_scale_semantic_limit"] = "Values1,7,9 are valid numbers on the existing custom0to10 field; they must not be relabeled as KSS/SP. Named KSS/SP fields were rejected as unsupported."

        raw_columns = ["participant_id", "mission_day", "observation_timestamp_utc", "journal_text"] + CURRENT_FIELDS
        raw = pd.read_csv(project / "data/raw_observations.csv", usecols=raw_columns)
        expected = {(record["participant_id"], record["mission_day"]): record for record in rows.to_dict("records")}
        people = []
        for pid, frame in raw.loc[raw.mission_day.le(60)].groupby("participant_id", sort=True):
            person = {"id": pid, "rows": []}
            for record in frame.sort_values("mission_day").to_dict("records"):
                observation = {key: record[key] for key in CURRENT_FIELDS}
                observation.update({"astronaut_id": pid, "observation_timestamp_utc": record["observation_timestamp_utc"], "journal_text": record["journal_text"]})
                wanted = expected.get((pid, record["mission_day"]))
                reference = None if wanted is None else {**{key: wanted[key] for key in INPUT_FIELDS}, "observation_timestamp_utc": wanted["observation_timestamp_utc"]}
                person["rows"].append({"day": record["mission_day"], "observation": observation, "expected": reference})
            people.append(person)
        with tempfile.TemporaryDirectory(prefix="astra-allrow-contracts-") as temporary:
            temporary = Path(temporary)
            fixture = temporary / "cases.json"
            write_json(fixture, {"people": people, "numericInputFields": INPUT_FIELDS, "unsupportedFields": unsupported})
            target = temporary / "typescript_results.json"
            replay = subprocess.run(["node", str(OUT / "audit_typescript_contracts.mjs"), str(backend / "featureHistory.ts"), str(fixture), str(target)],
                                    cwd=backend, env=env, text=True, capture_output=True, timeout=120)
            (OUT / "typescript_all_rows.log").write_text(replay.stdout + replay.stderr)
            assert target.exists(), replay.stderr
            ts_result = json.loads(target.read_text())
            write_json(OUT / "typescript_all_rows.json", ts_result)
            assert replay.returncode == 0 and ts_result["status"] == "passed"
            report["typescript_all_rows"] = ts_result

        report["protected_hashes_unchanged"] = all(sha(project / rel) == value for rel, value in before.items())
        assert report["protected_hashes_unchanged"]
        report["protected_hashes"] = before
        report["status"] = "passed"
    except Exception as exc:
        import traceback
        report["status"] = "failed"
        report["failures"].append({"message": str(exc), "traceback": traceback.format_exc()})
    finally:
        report["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
        report["protected_hashes_unchanged"] = all(sha(project / rel) == value for rel, value in before.items())
        write_json(OUT / "API_CONTRACT_INTEGRITY.json", report)
    print(json.dumps({k: v for k, v in report.items() if k not in {"protected_hashes", "typescript_all_rows", "new_measurement_fields"}}, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    raise SystemExit(main(args.project))
