#!/usr/bin/env python3
"""Browser + real HTTP integration checks using fictional, isolated demo IDs.

Start the application first. Requires Playwright and a Chromium browser. This
checks local app wiring, not clinical efficacy, Windows packaging, or model
accuracy. The secondary backend uses temporary storage and is stopped on exit.
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
import time
import traceback
import urllib.error
import urllib.request
import uuid

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "ai/integration/backend_review/proposed_backend"
REPORTS = ROOT / "integration-reports"
FIXTURE = BACKEND / "examples/synthetic_daily_sequence.json"
RECORDS = json.loads(FIXTURE.read_text())
FIELDS = [k for k in RECORDS[0] if k not in {"astronaut_id", "observation_timestamp_utc", "journal_text"}]


def request_json(url: str, body=None):
    request = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=40) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def wait_health(url: str, process=None, timeout=40):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if process is not None and process.poll() is not None:
            raise AssertionError("Secondary backend stopped before readiness.")
        try:
            code, body = request_json(url)
            if code == 200:
                return body
        except (OSError, ValueError):
            pass
        time.sleep(0.2)
    raise AssertionError(f"Health endpoint was not ready: {url}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frontend", default="http://127.0.0.1:4200")
    parser.add_argument("--model", default="http://127.0.0.1:8000")
    parser.add_argument("--secondary-port", type=int, default=3001)
    parser.add_argument("--chromium", default="/usr/bin/chromium")
    args = parser.parse_args()
    frontend = args.frontend.rstrip("/")
    REPORTS.mkdir(exist_ok=True)
    checks = []
    errors = []
    run_id = uuid.uuid4().hex[:10]
    report = {"run_id": run_id, "started_at_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "Linux Chromium, Angular frontend, real TypeScript backend and unchanged Python model",
              "data": "Fictional integration fixture; no test partition loaded or training performed",
              "windows_executed": False, "clinical_14_cases_executed": False,
              "checks": checks, "console_page_errors": errors, "passed": False}

    def check(name, condition, detail=None):
        checks.append({"name": name, "passed": bool(condition), **({"detail": detail} if detail is not None else {})})
        print(("PASS " if condition else "FAIL ") + name, flush=True)
        if not condition:
            raise AssertionError(name)

    secondary = None
    secondary_log = None

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

    def browser_post(page, url, body):
        return page.evaluate("""async ({url,body}) => {
            const response = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
            return {code:response.status, body:await response.json()};
        }""", {"url": url, "body": body})

    def choose_participant(page, identifier, api="/api/v1"):
        page.evaluate("""({identifier,api})=>{
            localStorage.setItem('astronautId',identifier);
            localStorage.setItem('apiBase',api);
            localStorage.removeItem('astraDemoMode');
        }""", {"identifier": identifier, "api": api})
        page.reload()
        expect(page.locator(".intro")).to_contain_text(identifier)
        expect(page.locator(".intro .env")).to_contain_text("Records from the backend")

    def fill_record(page, record, journal):
        page.get_by_role("tab", name="Check-in", exact=True).click()
        for field in FIELDS:
            page.locator("#f-" + field).fill(str(record[field]))
        page.locator("#log-journal").fill(journal)

    try:
        main_health = wait_health(frontend + "/api/v1/health")
        check("same-origin proxy reaches real model readiness", main_health["ai_service"]["model_ready"] is True)
        with tempfile.TemporaryDirectory(prefix="astra-app-checks-") as temp, sync_playwright() as p:
            browser = p.chromium.launch(executable_path=args.chromium, headless=True,
                                       args=["--no-sandbox", "--disable-dev-shm-usage"])
            context = browser.new_context(viewport={"width": 1440, "height": 1100})
            page = context.new_page()
            page.set_default_timeout(15000)
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(frontend)
            expect(page.locator(".intro .env")).to_contain_text("Records from the backend")
            check("initial page uses backend rather than automatic fixture fallback", page.locator(".intro .env").inner_text().strip() == "Records from the backend")
            identifier = "DEMO_E2E_" + run_id
            choose_participant(page, identifier)
            expect(page.get_by_role("heading", name="No records yet")).to_be_visible()
            check("fresh participant has empty history and no invented forecast", page.locator(".fc-index").count() == 0)

            for index, record in enumerate(RECORDS[:7]):
                body = {**record, "astronaut_id": identifier}
                response = browser_post(page, "/api/v1/assess", body)
                check(f"calibration record {index + 1} returns 202 without forecast",
                      response["code"] == 202 and response["body"]["status"] == "collecting_baseline"
                      and response["body"]["fatigue_points"] is None and response["body"]["model_result"] is None)
            page.reload()
            expect(page.locator("article[appFatigueCard] .fc-category")).to_have_text("Calibrating")
            check("record 7 UI shows calibration rather than prediction", page.locator(".fc-index").count() == 0)

            journal = "Synthetic E2E journal: interrupted sleep, no real participant."
            fill_record(page, RECORDS[7], journal)
            # Client-side required-field validation should not create a record.
            page.locator("#f-sleep_duration_hours").fill("")
            page.get_by_role("button", name="Save daily record", exact=True).click()
            expect(page.locator(".saved-note.bad")).to_contain_text("1 field(s) need attention")
            count_before = request_json(frontend + f"/api/v1/astronauts/{identifier}/history")[1]["total_assessments"]
            check("invalid client form does not save an observation", count_before == 7)
            page.locator("#f-sleep_duration_hours").fill(str(RECORDS[7]["sleep_duration_hours"]))
            with page.expect_response(lambda response: response.url.endswith("/api/v1/assess") and response.request.method == "POST", timeout=40000) as posted:
                page.get_by_role("button", name="Save daily record", exact=True).click()
            saved = posted.value.json()
            check("record 8 submitted through actual form returns real completed prediction", posted.value.status == 201 and saved["status"] == "completed" and saved["inference_source"] == "synthetic_model")
            check("real model produces 3 SHAP reasons", len(saved["explanation"]["top_contributing_factors"]) == 3)
            expect(page.locator(".saved-note[data-level='ok']")).to_contain_text("Record 8 saved")
            page.get_by_role("tab", name="Overview", exact=True).click()
            expect(page.locator("article[appFatigueCard] .fc-category")).to_have_text(saved["fatigue_risk_level"])
            expect(page.locator(".fc-index strong")).to_have_text(str(saved["fatigue_points"]).removesuffix(".0"))
            check("forecast category and index match actual backend response", True, {"category": saved["fatigue_risk_level"], "points": saved["fatigue_points"]})
            expect(page.locator("section[appInsightsPanel]")).to_contain_text("Why this forecast")
            for reason in saved["explanation"]["top_contributing_factors"]:
                text = f"{reason['shap_value']:+.3f}"
                expect(page.locator("section[appInsightsPanel]")).to_contain_text(text)
            check("UI renders the actual SHAP contribution values", True)
            expect(page.locator(".fc-note")).to_contain_text("not a medical percentage")
            history = request_json(frontend + f"/api/v1/astronauts/{identifier}/history")[1]
            check("saved history contains exact journal text and 8 observations", history["total_assessments"] == 8 and history["observations"][-1]["journal_text"] == journal)

            duplicate = browser_post(page, "/api/v1/assess", history["observations"][-1])
            check("duplicate completed observation returns 409", duplicate["code"] == 409 and duplicate["body"]["observation_saved"] is False)
            invalid = {**RECORDS[8], "astronaut_id": identifier, "resting_heart_rate_bpm": -1}
            rejected = browser_post(page, "/api/v1/assess", invalid)
            check("invalid numeric observation returns 422 without saving", rejected["code"] == 422 and rejected["body"]["observation_saved"] is False)
            check("rejections leave stored count unchanged", request_json(frontend + f"/api/v1/astronauts/{identifier}/history")[1]["total_assessments"] == 8)

            page.screenshot(path=str(REPORTS / "app-overview-desktop.png"), full_page=True)
            for _ in range(7):
                page.get_by_role("button", name="Previous record", exact=True).click()
            expect(page.locator("article[appFatigueCard] .fc-category")).to_have_text("Calibrating")
            check("early calibration record has no future cognition baseline classification", page.locator("article.tile-cognition").get_attribute("data-level") == "none")
            page.get_by_role("tab", name="Trends", exact=True).click()
            page.locator("article[appTrendChart] select").select_option("reaction_time_median_ms")
            check("early selected calibration record does not display later baseline", page.locator(".baseline-line").count() == 0)
            for _ in range(7):
                page.get_by_role("button", name="Next record", exact=True).click()
            expect(page.locator(".baseline-line")).to_have_count(1)
            check("baseline trend is available after calibration", True)
            page.get_by_role("tab", name="Guide", exact=True).click()
            expect(page.locator(".guide-intro")).to_contain_text("14 acceptance cases remain deferred")
            check("guide distinguishes demo guidance from deferred Clinical Alert V2", True)

            # These are presentation fixtures, not execution of Clinical Alert V2.
            demo_requests = []
            def record_demo_request(request):
                if "/api/" in request.url or "/v1/predict" in request.url:
                    demo_requests.append(request.url)
            page.on("request", record_demo_request)
            original_observations = request_json(frontend + f"/api/v1/astronauts/{identifier}/history")[1]["observations"]
            page.get_by_role("tab", name="Alert demo", exact=True).click()
            for preset, level, title in [
                ("healthy", "0", "No concern detected"), ("review", "1", "Review"),
                ("high", "2", "High concern"), ("urgent", "3", "Urgent"),
                ("unknown", "UNKNOWN", "Insufficient data"),
            ]:
                page.locator("#clinical-demo-scenario").select_option(preset)
                expect(page.locator(".demo-result")).to_have_attribute("data-demo-level", level)
                expect(page.locator(".demo-result h3")).to_have_text(title)
                expect(page.locator(".demo-forecast strong")).to_have_text("Low")
                check(f"fictional alert preset {preset} displays its predefined level and separate placeholder", True)
            check("switching all five alert presets makes no API or model request", demo_requests == [], demo_requests)
            page.remove_listener("request", record_demo_request)
            after_demo = request_json(frontend + f"/api/v1/astronauts/{identifier}/history")[1]
            check("alert preview does not modify observations or stored forecast", after_demo["observations"] == original_observations and after_demo["history"][-1]["fatigue_points"] == saved["fatigue_points"])
            page.get_by_role("tab", name="Overview", exact=True).click()
            for width in [320, 375]:
                page.set_viewport_size({"width": width, "height": 900})
                check(f"mobile overview at {width}px has no document horizontal overflow", page.evaluate("Math.max(document.documentElement.scrollWidth,document.body.scrollWidth)<=innerWidth"))
                tab_bounds = page.get_by_role("tab").evaluate_all("""elements => elements.map(element => {
                    const bounds = element.getBoundingClientRect();
                    const parent = element.parentElement.getBoundingClientRect();
                    return {label:element.textContent.trim(), left:bounds.left, right:bounds.right,
                            visible:bounds.left >= Math.max(0,parent.left)-1 && bounds.right <= Math.min(innerWidth,parent.right)+1};
                })""")
                check(f"all mobile navigation tabs fit their visible container at {width}px", all(item["visible"] for item in tab_bounds), tab_bounds)
            page.screenshot(path=str(REPORTS / "app-overview-mobile.png"), full_page=True)
            page.locator("article[appFatigueCard]").scroll_into_view_if_needed()
            page.screenshot(path=str(REPORTS / "app-forecast-mobile.png"), full_page=True)
            page.get_by_role("tab", name="Check-in", exact=True).click()
            check("mobile check-in has no document horizontal overflow", page.evaluate("Math.max(document.documentElement.scrollWidth,document.body.scrollWidth)<=innerWidth"))
            page.set_viewport_size({"width": 1440, "height": 1100})

            # Actual model-unavailable backend; main model and supervised stack stay running.
            second_url = f"http://127.0.0.1:{args.secondary_port}"
            secondary_log = (Path(temp) / "secondary-backend.log").open("w")
            db_file = Path(temp) / "history_db_v2.json"

            def start_secondary(ai_url):
                nonlocal secondary
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                    if os.name == "nt":
                        probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                    else:
                        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    probe.bind(("127.0.0.1", args.secondary_port))
                environment = {**os.environ, "HOST": "127.0.0.1", "PORT": str(args.secondary_port),
                               "DB_FILE": str(db_file), "AI_SERVICE_URL": ai_url}
                secondary = subprocess.Popen(["node", str(BACKEND / "node_modules/tsx/dist/cli.mjs"), "server.ts"],
                                             cwd=BACKEND, env=environment, stdout=secondary_log, stderr=subprocess.STDOUT,
                                             start_new_session=os.name == "posix")
                return wait_health(second_url + "/api/v1/health", secondary)

            off_health = start_secondary("")
            check("secondary actual backend reports model unavailable", off_health["ai_service"]["model_ready"] is False)
            outage_id = "DEMO_RETRY_" + run_id
            choose_participant(page, outage_id, second_url + "/api/v1")
            for record in RECORDS[:7]:
                response = browser_post(page, second_url + "/api/v1/assess", {**record, "astronaut_id": outage_id})
                assert response["code"] == 202
            page.reload()
            expect(page.locator(".intro")).to_contain_text(outage_id)
            outage_journal = "Exact retry after reload — synthetic journal with punctuation & context."
            fill_record(page, RECORDS[7], outage_journal)
            with page.expect_response(lambda response: response.url == second_url + "/api/v1/assess", timeout=40000) as posted:
                page.get_by_role("button", name="Save daily record", exact=True).click()
            outage = posted.value.json()
            check("actual model outage saves record with 503 and no fabricated forecast", posted.value.status == 503 and outage["observation_saved"] is True and outage["fatigue_points"] is None and outage["model_result"] is None)
            expect(page.locator(".saved-note[data-level='warning']")).to_contain_text("saved without a prediction")
            saved_outage = request_json(second_url + f"/api/v1/astronauts/{outage_id}/history")[1]["observations"][-1]
            stop_secondary()
            online_health = start_secondary(args.model)
            check("same backend storage recovers with the actual model connected", online_health["ai_service"]["model_ready"] is True)
            page.reload()
            expect(page.locator(".intro")).to_contain_text(outage_id)
            page.get_by_role("tab", name="Check-in", exact=True).click()
            with page.expect_response(lambda response: response.url == second_url + "/api/v1/assess", timeout=40000) as retried:
                page.get_by_role("button", name="Retry the prediction", exact=True).click()
            retry = retried.value.json()
            check("retry after browser reload produces real prediction", retried.value.status == 201 and retry["status"] == "completed")
            sent_retry = retried.value.request.post_data_json
            check("retry body preserves exact original timestamp, measurements and journal", sent_retry == saved_outage)
            recovered_history = request_json(second_url + f"/api/v1/astronauts/{outage_id}/history")[1]
            check("retry updates existing day without adding a ninth observation", recovered_history["total_assessments"] == 8 and recovered_history["observations"][-1] == saved_outage)
            stop_secondary()

            # Deliberate transport fault is labeled separately from the real outage above.
            failure_context = browser.new_context(viewport={"width": 1100, "height": 900})
            failure_page = failure_context.new_page()
            failure_page.set_default_timeout(15000)
            failure_page.on("pageerror", lambda error: errors.append(str(error)))
            failure_page.route("**/api/v1/health", lambda route: route.abort("connectionrefused"))
            failure_page.goto(frontend)
            expect(failure_page.get_by_role("heading", name="Backend connection unavailable")).to_be_visible()
            check("simulated transport failure does not silently switch to demo records", failure_page.locator(".intro").count() == 0)
            failure_page.get_by_role("button", name="Open simulated demo", exact=True).click()
            expect(failure_page.locator(".intro .env")).to_contain_text("Simulated example records (demo mode)")
            check("offline demo requires explicit user choice and is labeled", True)
            failure_context.close()

            # History failure after a successful load must preserve existing real records.
            choose_participant(page, identifier)
            page.route("**/api/v1/astronauts/*/history", lambda route: route.fulfill(status=503, content_type="application/json", body='{"error":"simulated_storage_failure"}'))
            page.get_by_role("button", name="Refresh data", exact=True).click()
            expect(page.locator(".connection-error")).to_be_visible()
            check("simulated history read failure preserves live participant and forecast", identifier in page.locator(".intro").inner_text() and page.locator(".fc-index").count() == 1)
            check("simulated history failure never selects fixture mode", page.evaluate("localStorage.getItem('astraDemoMode')") is None)
            page.unroute("**/api/v1/astronauts/*/history")
            page.get_by_role("button", name="Refresh data", exact=True).click()
            expect(page.locator(".connection-error")).to_have_count(0)
            check("history refresh recovers after transport fault removed", True)
            check("no browser JavaScript page errors", errors == [], errors)
            report["main_participant_id"] = identifier
            report["outage_participant_id"] = outage_id
            report["forecast_example"] = {"label": saved["fatigue_risk_level"], "points": saved["fatigue_points"],
                                          "model_version": saved["model_version"]}
            report["browser_version"] = browser.version
            browser.close()
        report["passed"] = True
    except BaseException as error:
        report["failure"] = {"type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()}
        raise
    finally:
        stop_secondary()
        if secondary_log is not None:
            secondary_log.close()
        report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        report["checks_passed"] = sum(check["passed"] for check in checks)
        report["checks_failed"] = sum(not check["passed"] for check in checks)
        source_paths = [FIXTURE, ROOT / "ai/artifacts/bundle.joblib", Path(__file__),
                        ROOT / "frontend/angular.json", ROOT / "frontend/proxy.conf.cjs",
                        BACKEND / "server.ts", BACKEND / "featureHistory.ts", BACKEND / "modelClient.ts"]
        source_paths.extend(sorted((ROOT / "frontend/src").rglob("*.ts")))
        source_paths.extend(sorted((ROOT / "frontend/src").rglob("*.css")))
        source_paths.extend(sorted((ROOT / "ai/astra_shield_ml").glob("*.py")))
        report["sha256"] = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                            for path in source_paths}
        (REPORTS / "APP_INTEGRATION_CHECKS.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
