#!/usr/bin/env python3
"""Submission UI regressions using isolated, explicitly fictional observations.

Start the application with a dedicated --db-file and pass that same path here.
This runs the full virtual-clock reaction task -> form -> save -> retrieve ->
actual model sequence. It verifies software behavior, not human reaction timing,
clinical validity, the 14 Clinical Alert V2 cases, or forecasting accuracy.
The temporary secondary backend has no AI service and exercises a real outage.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import tempfile
import traceback
import uuid

from playwright.sync_api import sync_playwright, expect

from test_app_integration import BACKEND, FIELDS, FIXTURE, RECORDS, ROOT, request_json, wait_health

REPORTS = ROOT / "integration-reports"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frontend", default="http://127.0.0.1:4200")
    parser.add_argument("--chromium", default="/usr/bin/chromium")
    parser.add_argument("--isolated-db", required=True, type=Path,
                        help="Dedicated synthetic database used by the running main backend")
    args = parser.parse_args()
    frontend = args.frontend.rstrip("/")
    database = args.isolated_db.resolve()
    run_id = uuid.uuid4().hex[:10]
    identifier = "DEMO_SAFETY_" + run_id
    checks, errors = [], []
    report = {
        "run_id": run_id,
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Linux Chromium, real TypeScript backend and unchanged Python model; focused submission UI regressions",
        "data": "Fictional synthetic integration observations; no training or held-out partition evaluation",
        "storage": {"main_database": str(database), "participant": identifier,
                    "outage_database": "TemporaryDirectory, removed after verification"},
        "reaction_timing": "Playwright virtual clock and scripted responses; not human/device timing validation",
        "windows_executed": False,
        "clinical_14_cases_executed": False,
        "checks": checks,
        "console_page_errors": errors,
        "passed": False,
    }
    secondary = None
    REPORTS.mkdir(exist_ok=True)

    def check(name, condition, detail=None):
        checks.append({"name": name, "passed": bool(condition),
                       **({"detail": detail} if detail is not None else {})})
        print(("PASS " if condition else "FAIL ") + name, flush=True)
        if not condition:
            raise AssertionError(name)

    def stop_secondary():
        nonlocal secondary
        if secondary is None:
            return
        if os.name == "posix":
            try:
                os.killpg(secondary.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        elif secondary.poll() is None:
            secondary.terminate()
        try:
            secondary.wait(timeout=8)
        except subprocess.TimeoutExpired:
            secondary.kill()
            secondary.wait(timeout=5)
        secondary = None

    def fill(page, values):
        for key in FIELDS:
            page.locator("#f-" + key).fill(str(values[key]))

    def blank(page):
        return page.locator("article[appLogForm] input[type='number']").evaluate_all(
            "xs => xs.length === 15 && xs.every(x => x.value === '')")

    def choose_participant(page, identity, api="/api/v1"):
        page.evaluate("""({identity,api})=>{
            localStorage.setItem('astronautId',identity);
            localStorage.setItem('apiBase',api);
            localStorage.removeItem('astraDemoMode');
        }""", {"identity": identity, "api": api})
        page.reload()
        expect(page.locator(".intro")).to_contain_text(identity)
        expect(page.locator(".intro .env")).to_contain_text("Records from the backend")

    try:
        # The test refuses a selected database containing non-demo identities,
        # then verifies that the real API wrote this run's identity to that file.
        if database.exists():
            initial = json.loads(database.read_text())
            initial_ids = list(initial["participants"])
        else:
            initial_ids = []
        check("selected main test database contains only explicit demo identities",
              all(value.startswith("DEMO_") for value in initial_ids),
              {"existing_demo_participant_count": len(initial_ids)})
        health = wait_health(frontend + "/api/v1/health")
        check("main backend reaches the actual unchanged model", health["ai_service"]["model_ready"] is True)
        for record in RECORDS[:7]:
            status, payload = request_json(frontend + "/api/v1/assess", {**record, "astronaut_id": identifier})
            assert status == 202 and payload["status"] == "collecting_baseline"
        persisted = json.loads(database.read_text())
        check("real API writes seven synthetic calibration records to the selected isolated database",
              len(persisted["participants"].get(identifier, [])) == 7)

        with tempfile.TemporaryDirectory(prefix="astra-submission-outage-") as temporary, sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=args.chromium, headless=True,
                                                 args=["--no-sandbox", "--disable-dev-shm-usage"])
            context = browser.new_context(viewport={"width": 1440, "height": 1100}, reduced_motion="reduce")
            context.add_init_script("if (!localStorage.getItem('astronautId')) localStorage.setItem('astronautId', " + json.dumps(identifier) + ");")
            page = context.new_page()
            page.set_default_timeout(15000)
            page.on("pageerror", lambda error: errors.append(str(error)))
            requests = []
            page.on("request", lambda request: requests.append({"url": request.url, "method": request.method})
                    if "/api/" in request.url else None)
            page.goto(frontend)
            expect(page.locator(".intro")).to_contain_text(identifier)
            page.get_by_role("tab", name="Check-in", exact=True).click()
            expect(page.locator("article[appLogForm]")).to_be_visible()
            check("new Check-in starts with all 15 measurements blank despite existing history", blank(page))
            check("backend Check-in does not offer simulated example filling",
                  page.get_by_role("button", name="Fill example values (simulated)", exact=True).count() == 0)
            page.locator("#f-resting_heart_rate_bpm").fill("70")
            page.get_by_role("tab", name="Overview", exact=True).click()
            expect(page.get_by_role("tab", name="Overview", exact=True)).to_have_attribute("aria-selected", "true")
            expect(page.locator("article[appLogForm]")).to_have_count(0)
            page.get_by_role("tab", name="Check-in", exact=True).click()
            expect(page.get_by_role("tab", name="Check-in", exact=True)).to_have_attribute("aria-selected", "true")
            expect(page.locator("article[appLogForm]")).to_be_visible()
            check("reopening Check-in starts fresh instead of restoring stale measurements", blank(page))
            fill(page, RECORDS[7])
            expect(page.locator("label[for='f-attention_accuracy_pct']")).to_contain_text("Externally measured attention-task accuracy")
            page.get_by_role("button", name="Not measured", exact=True).click()
            expect(page.locator("#f-attention_accuracy_pct")).to_have_value("")
            before = len([r for r in requests if r["method"] == "POST"])
            page.get_by_role("button", name="Save daily record", exact=True).click()
            expect(page.locator("#f-attention_accuracy_pct")).to_have_attribute("aria-invalid", "true")
            check("Not measured attention is explicit and blocks submission without substituting a score",
                  len([r for r in requests if r["method"] == "POST"]) == before)
            page.locator("#f-attention_accuracy_pct").fill(str(RECORDS[7]["attention_accuracy_pct"]))
            expect(page.locator("article[appReactionTest]")).to_contain_text("Custom 60-response PVT-inspired reaction-time test")

            # Full task, transfer, and actual save/inference remain one flow.
            page.clock.install()
            page.clock.pause_at(datetime.now(timezone.utc))
            page.evaluate("window.safetyOriginalRandom=Math.random;Math.random=()=>0")
            page.get_by_role("button", name="Full demo · 60 taps", exact=True).click()
            page.clock.run_for(20)
            pad = page.locator("article[appReactionTest] .pad")
            pad.press("Enter")
            page.clock.run_for(20)
            for trial in range(60):
                page.clock.run_for(2000)
                page.clock.run_for(700 if trial == 0 else 200)
                pad.press("Enter")
                page.clock.run_for(20)
            expect(pad).to_have_attribute("data-phase", "done")
            page.get_by_role("button", name="Use these results", exact=True).click()
            page.clock.run_for(20)
            median = float(page.locator("#f-reaction_time_median_ms").input_value())
            lapses = int(page.locator("#f-reaction_time_lapses_count").input_value())
            check("full 60-response synthetic task transfers its actual scripted median and lapse count",
                  200 <= median <= 240 and lapses == 1, {"median_ms": median, "lapses": lapses})
            expect(page.get_by_role("button", name="Added to the form", exact=True)).to_be_disabled()
            page.evaluate("Math.random=window.safetyOriginalRandom;delete window.safetyOriginalRandom")
            page.clock.resume()
            journal = "Synthetic submission regression: generated task responses; no real participant."
            page.locator("#log-journal").fill(journal)
            with page.expect_response(lambda response: response.url.endswith("/api/v1/assess") and response.request.method == "POST",
                                      timeout=40000) as posted:
                page.get_by_role("button", name="Save daily record", exact=True).click()
            saved = posted.value.json()
            sent = posted.value.request.post_data_json
            check("transferred reaction results reach a real completed model request",
                  posted.value.status == 201 and saved["status"] == "completed"
                  and saved["inference_source"] == "synthetic_model"
                  and sent["reaction_time_median_ms"] == median and sent["reaction_time_lapses_count"] == lapses)
            check("actual model response contains three SHAP explanations",
                  len(saved["explanation"]["top_contributing_factors"]) == 3)
            expect(page.locator(".saved-note[data-level='ok']")).to_contain_text("Record 8 saved")
            check("successful save clears daily numeric fields for the next record", blank(page))
            status, history = request_json(frontend + f"/api/v1/astronauts/{identifier}/history")
            retrieved = history["observations"][-1]
            # The backend canonicalizes ISO timestamps with milliseconds; compare
            # the instant while requiring exact equality for all measured values.
            observation_fields = set(sent) - {"observation_timestamp_utc"}
            same_instant = datetime.fromisoformat(retrieved["observation_timestamp_utc"].replace("Z", "+00:00")) == datetime.fromisoformat(sent["observation_timestamp_utc"].replace("Z", "+00:00"))
            check("retrieved record preserves exact task values and journal, with the same cutoff instant",
                  status == 200 and history["total_assessments"] == 8 and same_instant
                  and set(retrieved) == set(sent)
                  and all(retrieved[key] == sent[key] for key in observation_fields))
            page.get_by_role("tab", name="Overview", exact=True).click()
            card = page.locator("article[appFatigueCard]")
            expect(card).to_contain_text("Model-generated forecast")
            expect(card.locator(".fc-category")).to_have_text(saved["fatigue_risk_level"])
            expect(card.locator(".fc-index strong")).to_have_text(str(saved["fatigue_points"]).removesuffix(".0"))
            check("displayed model forecast category and index match the actual response", True)
            for reason in saved["explanation"]["top_contributing_factors"]:
                expect(page.locator("section[appInsightsPanel]")).to_contain_text(f"{reason['shap_value']:+.3f}")
            check("displayed SHAP contributions match this actual model request", True)
            expect(card).to_contain_text("Uncalibrated model class outputs")
            check("model forecast target includes a full year and UTC",
                  str(datetime.fromisoformat(saved["target_timestamp_utc"].replace("Z", "+00:00")).year) in card.inner_text()
                  and "UTC" in card.inner_text())
            check("actual prediction is not relabeled as a live result when read from stored history",
                  "Live model output" not in card.inner_text())

            before = len(requests)
            page.get_by_role("tab", name="Alert demo", exact=True).click()
            expect(page.locator("article[appClinicalDemo]")).to_be_visible()
            expect(page.locator(".intro .env")).to_contain_text("no participant record shown")
            check("Alert demo hides unrelated record body-map readings, forecast and recommendations",
                  page.locator(".hotspot,.zone-card").count() == 0
                  and page.locator("#action-panel").count() == 0
                  and page.locator("[appFatigueCard]").count() == 0
                  and page.locator("[appInsightsPanel]").count() == 0
                  and page.locator("[appRecommendationCards]").count() == 0)
            for scenario, level in [("healthy", "0"), ("review", "1"), ("high", "2"), ("urgent", "3"), ("unknown", "UNKNOWN")]:
                page.locator("#clinical-demo-scenario").select_option(scenario)
                expect(page.locator(".demo-result")).to_have_attribute("data-demo-level", level)
                expect(page.locator(".demo-forecast strong")).to_have_text("Low")
            check("five fictional alert scenarios remain independent and make no API request", len(requests) == before)
            page.locator("#clinical-demo-scenario").select_option("review")
            expect(page.locator(".demo-result")).to_contain_text("mission procedures")
            expect(page.locator(".demo-result")).to_contain_text("safety-critical task")
            check("sleepiness example has procedure-based reassessment without a fixed 1–2 hour rule",
                  "1–2" not in page.locator(".demo-result").inner_text())
            page.locator("#clinical-demo-scenario").select_option("urgent")
            expect(page.locator(".demo-result")).to_contain_text("immediately")
            check("urgent fictional example retains immediate medical contact and no wait for a model",
                  "Do not wait for a model result" in page.locator(".demo-result").inner_text())

            page.get_by_role("tab", name="Overview", exact=True).click()
            page.get_by_role("button", name="Preview demo data", exact=True).click()
            expect(page.locator(".intro .env")).to_contain_text("demo mode")
            card = page.locator("article[appFatigueCard]")
            expect(card).to_contain_text("Simulated example forecast")
            expect(page.locator("[appRecommendationCards]")).to_contain_text("Example advisory")
            check("offline forecast and advisory label their fictional example provenance",
                  "Advisory line from the model service" not in page.locator("[appRecommendationCards]").inner_text()
                  and "Model-generated forecast" not in card.inner_text())
            expect(card).to_contain_text("not a medical percentage or clinical risk probability")
            check("index card explicitly distinguishes its index from clinical risk probability", True)
            page.get_by_role("tab", name="Check-in", exact=True).click()
            expect(page.locator("article[appLogForm]")).to_be_visible()
            check("explicit offline demo Check-in also starts blank", blank(page))
            page.get_by_role("button", name="Fill example values (simulated)", exact=True).click()
            check("example filling is an explicit action confined to offline demo",
                  page.locator("input[type='number']").evaluate_all("xs => xs.every(x => x.value !== '')"))

            # A genuine backend without a model verifies the unavailable UI, using
            # nominal fictional inputs so the old reassurance branch is reached.
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.bind(("127.0.0.1", 0))
                port = probe.getsockname()[1]
            outage_url = f"http://127.0.0.1:{port}"
            outage_id = "DEMO_SAFETY_OUTAGE_" + run_id
            log_path = Path(temporary) / "backend.log"
            environment = {**os.environ, "HOST": "127.0.0.1", "PORT": str(port),
                           "DB_FILE": str(Path(temporary) / "history.json"), "AI_SERVICE_URL": ""}
            with log_path.open("w") as log:
                secondary = subprocess.Popen(["node", str(BACKEND / "node_modules/tsx/dist/cli.mjs"), "server.ts"],
                                             cwd=BACKEND, env=environment, stdout=log, stderr=subprocess.STDOUT,
                                             start_new_session=os.name == "posix")
                health = wait_health(outage_url + "/api/v1/health", secondary)
                check("real secondary backend reports model unavailable", health["ai_service"]["model_ready"] is False)
                nominal = {**RECORDS[0], "sleep_duration_hours": 8, "sleep_efficiency_pct": 95,
                           "sleep_onset_delay_minutes": 10, "resting_heart_rate_bpm": 65,
                           "hrv_rmssd_ms": 45, "reaction_time_median_ms": 280,
                           "reaction_time_lapses_count": 0, "self_report_fatigue_score": 2,
                           "self_report_stress_score": 2, "self_report_mood_score": 8}
                for index, record in enumerate(RECORDS[:8]):
                    status, response = request_json(outage_url + "/api/v1/assess",
                                                    {**nominal, "astronaut_id": outage_id,
                                                     "observation_timestamp_utc": record["observation_timestamp_utc"]})
                    assert status == (202 if index < 7 else 503), (status, response)
                choose_participant(page, outage_id, outage_url + "/api/v1")
                page.get_by_role("tab", name="Overview", exact=True).click()
                expect(page.locator("article[appFatigueCard] .fc-category")).to_have_text("No forecast")
                notice = page.locator("article.rec").filter(has_text="No forecast-based recommendation available.")
                expect(notice).to_be_visible()
                check("unavailable model has a neutral no-recommendation message without reassurance",
                      notice.get_attribute("data-level") in (None, "none")
                      and "Keep your current routine" not in page.locator("[appRecommendationCards]").inner_text())
                check("unavailable result does not invent a forecast index", page.locator(".fc-index").count() == 0)
                stop_secondary()

            check("no uncaught browser JavaScript errors", not errors, errors)
            report["browser_version"] = browser.version
            report["model_request_observation"] = {
                "participant": identifier,
                "observation_timestamp_utc": sent["observation_timestamp_utc"],
                "target_timestamp_utc": saved["target_timestamp_utc"],
                "reaction_time_median_ms": median,
                "reaction_time_lapses_count": lapses,
                "category": saved["fatigue_risk_level"],
                "points": saved["fatigue_points"],
                "note": "Integration output only, not accuracy or clinical risk",
            }
            browser.close()
        report["passed"] = True
    except BaseException:
        report["exception"] = traceback.format_exc()
        print(report["exception"], flush=True)
    finally:
        stop_secondary()
        report["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
        report["passed_check_count"] = sum(c["passed"] for c in checks)
        report["failed_check_count"] = sum(not c["passed"] for c in checks)
        sources = [Path(__file__), ROOT / "scripts/test_app_integration.py", FIXTURE,
                   ROOT / "ai/artifacts/bundle.joblib", BACKEND / "server.ts", BACKEND / "featureHistory.ts",
                   *sorted((ROOT / "frontend/src").rglob("*.ts")), ROOT / "frontend/src/styles.css"]
        report["source_sha256"] = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                                   for path in sources if path.is_file()}
        (REPORTS / "SUBMISSION_SAFETY_CHECKS.json").write_text(json.dumps(report, indent=2) + "\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
