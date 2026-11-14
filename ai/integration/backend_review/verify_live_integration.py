"""Exercise the real TypeScript backend and frozen Python model on loopback.

Creates a temporary history store, uses explicitly synthetic fixtures, and never
fits a model or loads the test dataset. All child processes are stopped in finally.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
BACKEND = HERE / "proposed_backend"


def http(url, body=None, method=None):
    payload = None if body is None else json.dumps(body).encode()
    request = Request(url, data=payload, method=method or ("POST" if body is not None else "GET"),
                      headers={"Content-Type": "application/json"})
    try:
        response = urlopen(request, timeout=25)
    except HTTPError as error:
        response = error
    with response:
        return response.status if hasattr(response, "status") else response.code, json.load(response)


def free_port():
    with socket.socket() as handle:
        handle.bind(("127.0.0.1", 0))
        return handle.getsockname()[1]


def wait_ready(process, url):
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Child process exited with {process.returncode}: {url}")
        try:
            status, result = http(url)
            if status == 200:
                return result
        except (URLError, ConnectionError, TimeoutError):
            pass
        time.sleep(.15)
    raise RuntimeError(f"Local service did not become ready: {url}")


def stop(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def main(model_project):
    model_project = Path(model_project).resolve()
    artifact = model_project / "artifacts/bundle.joblib"
    digest = lambda: hashlib.sha256(artifact.read_bytes()).hexdigest()
    artifact_before = digest()
    rows = json.loads((BACKEND / "examples/synthetic_daily_sequence.json").read_text())
    expected = json.loads((BACKEND / "examples/expected_model_request_day8.json").read_text())
    checks, processes, log_handles = [], [], []
    result_path = HERE / "LIVE_INTEGRATION_VERIFICATION.json"

    def check(name, condition):
        assert condition, name
        checks.append(name)

    with tempfile.TemporaryDirectory(prefix="astra-live-backend-") as temporary:
        temp = Path(temporary)
        model_port, backend_port = free_port(), free_port()
        while backend_port == model_port:
            backend_port = free_port()
        model_url, backend_url = f"http://127.0.0.1:{model_port}", f"http://127.0.0.1:{backend_port}"
        model_command = [sys.executable, "-m", "uvicorn", "astra_shield_ml.api:app", "--host", "127.0.0.1", "--port", str(model_port), "--log-level", "error"]

        def spawn(command, cwd, env, name):
            log = (temp / f"{name}.log").open("w+")
            log_handles.append(log)
            process = subprocess.Popen(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT)
            processes.append(process)
            return process

        try:
            model = spawn(model_command, model_project, os.environ.copy(), "model")
            model_health = wait_ready(model, model_url + "/health")
            check("real_frozen_model_ready", model_health["status"] == "ready")
            env = {**os.environ, "HOST": "127.0.0.1", "PORT": str(backend_port),
                   "DB_FILE": str(temp / "test_history.json"), "AI_SERVICE_URL": model_url}
            backend = spawn([str(BACKEND / "node_modules/.bin/tsx"), "server.ts"], BACKEND, env, "backend")
            health = wait_ready(backend, backend_url + "/api/v1/health")
            check("backend_checks_actual_model_readiness", health["ai_service"]["model_ready"] is True)
            old = {"astronaut_id": "AST-01", "heart_rate_bpm": 84, "hrv_ms": 34,
                   "sleep_duration_hours": 5.2, "sleep_quality_score_1_10": 4.5, "PVT_speed_seconds": 5.65}
            code, _ = http(model_url + "/predict", old)
            check("original_model_path_is_not_predict", code == 404)
            code, _ = http(model_url + "/v1/predict", old)
            check("legacy_payload_rejected_by_model", code == 422)
            code, bad = http(backend_url + "/api/v1/assess", old)
            check("legacy_units_and_fields_rejected_by_backend", code == 422 and bad["observation_saved"] is False)
            for index, row in enumerate(rows[:7]):
                code, warmup = http(backend_url + "/api/v1/assess", row)
                check(f"calibration_day_{index+1}_has_no_prediction", code == 202 and warmup["status"] == "collecting_baseline"
                      and warmup["calibration_count"] == index+1 and warmup["fatigue_points"] is None
                      and warmup["inference_source"] == "none" and warmup["observation_saved"] is True)
            check("seven_days_complete_fixed_calibration", warmup["personal_baseline_ready"] is True)
            code, direct = http(model_url + "/v1/predict", expected)
            check("python_reference_request_accepted", code == 200)
            code, predicted = http(backend_url + "/api/v1/assess", rows[7])
            check("eighth_day_calls_real_model", code == 201 and predicted["status"] == "completed"
                  and predicted["ai_service_connected"] is True and predicted["inference_source"] == "synthetic_model")
            check("typescript_features_match_python_prediction", predicted["fatigue_points"] == direct["points"]
                  and predicted["fatigue_risk_level"].lower() == direct["label"]
                  and predicted["fatigue_score"] == direct["next_day_forecasts"]["fatigue"]["score_estimate"])
            check("three_genuine_shap_reasons_preserved", predicted["explanation"]["top_contributing_factors"] == direct["reasons"])
            check("severity_not_reported_as_medical_percentage", predicted["fatigue_risk_percentage"] is None
                  and predicted["clinical_validation"] is False and predicted["forecast_horizon_hours"] == 24)
            baseline = predicted["personal_baseline"]
            check("baseline_matches_earlier_seven_day_reference", all(baseline[k] == v for k, v in expected.items() if k.startswith("baseline_")))
            code, duplicate = http(backend_url + "/api/v1/assess", rows[7])
            check("repeated_click_not_an_extra_day", code == 409 and duplicate["observation_saved"] is False)
            code, history = http(backend_url + f"/api/v1/astronauts/{rows[0]['astronaut_id']}/history")
            check("graphs_receive_raw_observations", code == 200 and history["total_assessments"] == 8
                  and len(history["observations"]) == 8
                  and history["observations"][-1]["self_report_fatigue_score"] == rows[7]["self_report_fatigue_score"])
            stop(model)
            code, health_down = http(backend_url + "/api/v1/health")
            check("configured_url_is_not_claimed_connected_during_outage", code == 200 and health_down["ai_service"]["configured"]
                  and not health_down["ai_service"]["model_ready"])
            code, unavailable = http(backend_url + "/api/v1/assess", rows[8])
            check("outage_saves_measurement_without_inventing_prediction", code == 503 and unavailable["status"] == "model_unavailable"
                  and unavailable["observation_saved"] is True and unavailable["fatigue_points"] is None
                  and not unavailable["ai_service_connected"] and unavailable["model_result"] is None)
            model = spawn(model_command, model_project, os.environ.copy(), "model-restarted")
            wait_ready(model, model_url + "/health")
            code, recovered = http(backend_url + "/api/v1/assess", rows[8])
            check("identical_latest_outage_can_retry_without_new_day", code == 201 and recovered["status"] == "completed"
                  and recovered["assessment_id"] == unavailable["assessment_id"])
            check("baseline_stays_fixed_after_new_measurement", recovered["personal_baseline"] == baseline)
            _, history = http(backend_url + f"/api/v1/astronauts/{rows[0]['astronaut_id']}/history")
            check("retry_did_not_duplicate_history", history["total_assessments"] == 9 and len(history["observations"]) == 9)
            invalid = {**rows[8], "astronaut_id": "DEMO_INVALID", "self_report_fatigue_score": "5"}
            code, rejected = http(backend_url + "/api/v1/assess", invalid)
            check("numeric_strings_rejected", code == 422 and rejected["observation_saved"] is False)
            invalid = {**rows[8], "astronaut_id": "DEMO_INVALID", "target_next_day_fatigue_class": "high"}
            code, rejected = http(backend_url + "/api/v1/assess", invalid)
            check("target_injection_rejected", code == 422 and rejected["observation_saved"] is False)
            check("frozen_model_not_changed", digest() == artifact_before)
            result = {"status": "passed", "verified_at_utc": datetime.now(timezone.utc).isoformat(),
                      "scope": "Real local TypeScript backend to frozen Python model; synthetic integration fixtures only",
                      "checks_passed": len(checks), "checks": checks, "example_label": predicted["fatigue_risk_level"],
                      "example_points": predicted["fatigue_points"], "model_sha256": artifact_before,
                      "model_trained": False, "test_dataset_used": False, "angular_ionic_application_tested": False,
                      "temporary_history_store": True, "child_services_stopped_after_test": True}
            result_path.write_text(json.dumps(result, indent=2)+"\n")
            (BACKEND / "examples/assessment_response_day8.json").write_text(json.dumps(predicted, indent=2)+"\n")
            print(json.dumps(result, indent=2), flush=True)
        except Exception:
            for log in log_handles:
                log.flush()
                log.seek(0)
                print(log.name, log.read()[-2500:], file=sys.stderr)
            raise
        finally:
            for process in reversed(processes):
                stop(process)
            for log in log_handles:
                log.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-project", type=Path, default=HERE.parents[1])
    main(parser.parse_args().model_project)
