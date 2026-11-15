#!/usr/bin/env python3
"""Expanded Chromium UI audit, complementary to test_app_integration.py.

Start the three-service application first. This uses only fictional fixtures and
an isolated DEMO_UI_* participant. Reaction-task checks use Playwright's virtual
clock and synthetic keyboard events: they verify UI state, not human timing.
No training, model scoring study, clinical validation, or Windows execution.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import traceback
import urllib.error
import urllib.request
import uuid

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "integration-reports"
FIXTURE = ROOT / "ai/integration/backend_review/proposed_backend/examples/synthetic_daily_sequence.json"
RECORDS = json.loads(FIXTURE.read_text())
FIELDS = [k for k in RECORDS[0] if k not in {"astronaut_id", "observation_timestamp_utc", "journal_text"}]


def request_json(url, body=None):
    req = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=40) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frontend", default="http://127.0.0.1:4200")
    parser.add_argument("--chromium", default="/usr/bin/chromium")
    args = parser.parse_args()
    frontend = args.frontend.rstrip("/")
    run_id = uuid.uuid4().hex[:10]
    identifier = "DEMO_UI_" + run_id
    checks, findings, errors, screenshots = [], [], [], []
    report = {"started_at_utc": datetime.now(timezone.utc).isoformat(), "run_id": run_id,
              "scope": "Expanded Linux Chromium UI audit with real local backend/model and fictional records",
              "data": "Synthetic integration fixture only; no training or held-out model evaluation",
              "reaction_timing": "Virtual clock and synthetic key events; not hardware timing validation",
              "screenshots_note": "Viewport captures; Ionic scroll content is not represented by the browser full-page height",
              "windows_executed": False, "clinical_14_cases_executed": False,
              "full_accessibility_audit": False, "checks": checks, "findings": findings,
              "console_page_errors": errors, "screenshots": screenshots, "passed": False}
    REPORTS.mkdir(exist_ok=True)

    def check(name, passed, detail=None):
        checks.append({"name": name, "passed": bool(passed), **({"detail": detail} if detail is not None else {})})
        print(("PASS " if passed else "FAIL ") + name, flush=True)
        if not passed:
            raise AssertionError(name)

    def finding(name, detail, severity="observation"):
        findings.append({"name": name, "severity": severity, "detail": detail})
        print("FINDING " + name, flush=True)

    def shot(page, name):
        target = REPORTS / name
        page.screenshot(path=str(target), full_page=True)
        screenshots.append({"path": str(target.relative_to(ROOT)), "sha256": hashlib.sha256(target.read_bytes()).hexdigest()})

    def fill(page, record):
        for key in FIELDS:
            page.locator("#f-" + key).fill(str(record[key]))

    try:
        for record in RECORDS[:9]:
            code, body = request_json(frontend + "/api/v1/assess", {**record, "astronaut_id": identifier})
            if code not in {201, 202}:
                raise AssertionError(f"Fixture setup failed: {code}: {body}")
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=args.chromium, headless=True,
                                       args=["--no-sandbox", "--disable-dev-shm-usage"])
            context = browser.new_context(viewport={"width": 1440, "height": 1100}, reduced_motion="reduce")
            context.add_init_script("localStorage.setItem('astronautId', " + json.dumps(identifier) + ");")
            page = context.new_page()
            page.set_default_timeout(12000)
            page.on("pageerror", lambda error: errors.append(str(error)))
            requests = []
            page.on("request", lambda r: requests.append({"url": r.url, "method": r.method}) if "/api/" in r.url else None)
            page.goto(frontend)
            expect(page.locator(".intro .env")).to_contain_text("Records from the backend")
            page.evaluate("document.fonts.ready")
            check("original Manrope font loads locally", page.evaluate("document.fonts.check('400 16px \"Manrope Variable\"')"))
            check("all five primary navigation views are present", page.get_by_role("tab").count() == 5)
            check("latest seeded record selected", page.locator(".timeline-pill").inner_text().endswith("Record 9"))
            expect(page.get_by_role("button", name="Next record", exact=True)).to_be_disabled()
            page.get_by_role("button", name="Previous record", exact=True).click()
            expect(page.locator(".timeline-pill")).to_contain_text("Record 8")
            page.get_by_role("button", name="Record 1: Calibration", exact=True).click()
            expect(page.get_by_role("button", name="Previous record", exact=True)).to_be_disabled()
            check("history supports previous, direct selection, and endpoint guards", page.locator(".fc-category").inner_text() == "Calibrating")
            page.get_by_role("button", name="Record 9:").click()

            for zone, target in [("Sleep & alertness", "sleep_duration_hours"), ("Mood & stress", "self_report_fatigue_score"),
                                 ("Heart", "resting_heart_rate_bpm"), ("Next-day fatigue", "forecast")]:
                page.get_by_role("button", name=zone + ":", exact=False).click()
                expect(page.locator(".zone-label")).to_have_text(zone)
                page.get_by_role("button", name="How to read this").click()
                expect(page.get_by_role("tab", name="Guide", exact=True)).to_have_attribute("aria-selected", "true")
                expect(page.locator("#guide-" + target)).to_be_visible()
                check(f"body map {zone} opens matching Guide section", True)
            check("Guide contains forecast plus all 15 measurement explanations", page.locator(".guide-card").count() == 16)
            check("Guide external links use noreferrer", page.locator(".guide a[target='_blank']:not([rel~='noreferrer'])").count() == 0)

            page.get_by_role("tab", name="Trends", exact=True).click()
            select = page.locator("article[appTrendChart] select")
            expect(select.locator("option")).to_have_count(16)
            check("Trends offers forecast and all 15 measurement series", select.locator("option").count() == 16)
            for key in ["forecast", *FIELDS]:
                select.select_option(key)
                expect(page.locator("svg.trend circle").first).to_be_visible()
                check("trend series renders finite coordinates: " + key, page.locator("svg.trend").evaluate("s => !/NaN|Infinity/.test(s.innerHTML)"))
            select.select_option("reaction_time_median_ms")
            expect(page.locator(".baseline-line")).to_have_count(1)
            bounds = page.locator("svg.trend").bounding_box()
            page.mouse.move(bounds["x"] + bounds["width"] / 2, bounds["y"] + bounds["height"] / 2)
            expect(page.locator(".tooltip-day")).to_contain_text("Record")
            check("trend pointer tooltip and baseline render", True)

            page.get_by_role("tab", name="Overview", exact=True).click()
            rec = page.locator(".rec-check").first
            rec.click()
            expect(rec).to_have_attribute("aria-pressed", "true")
            rec.press("Space")
            expect(rec).to_have_attribute("aria-pressed", "false")
            rec.click()
            page.get_by_role("button", name="Previous record", exact=True).click()
            expect(page.locator(".rec-check[aria-pressed='true']")).to_have_count(0)
            check("recommendation toggles support pointer and keyboard and reset per record", page.locator(".rec-check[aria-pressed='true']").count() == 0)
            page.locator(".seam").click()
            expect(page.locator(".seam")).to_have_attribute("aria-expanded", "false")
            expect(page.locator(".dark-summary")).to_be_visible()
            page.locator(".dark-summary").click()
            expect(page.locator(".seam")).to_have_attribute("aria-expanded", "true")
            check("action panel collapse and summary reopen", True)

            page.get_by_role("tab", name="Check-in", exact=True).click()
            expect(page.locator("input[type='number']")).to_have_count(15)
            check("Check-in exposes 15 numeric fields with associated labels", page.locator("input[type='number']").count() == 15 and
                  page.locator("input[type='number']").evaluate_all("xs => xs.every(x=>x.labels.length>0)"))
            before = len([r for r in requests if r["method"] == "POST"])
            for key in FIELDS:
                field = page.locator("#f-" + key)
                old = field.input_value()
                field.fill("")
                page.get_by_role("button", name="Save daily record", exact=True).click()
                expect(field).to_have_attribute("aria-invalid", "true")
                field.fill(old)
            check("each of 15 missing fields is rejected before network submission", len([r for r in requests if r["method"] == "POST"]) == before)
            for key, bad in [("awakenings_count", "2.5"), ("reaction_time_lapses_count", "2.5"),
                             ("sleep_duration_hours", "0"), ("hrv_rmssd_ms", "301"), ("self_report_fatigue_score", "11")]:
                field = page.locator("#f-" + key)
                old = field.input_value()
                field.fill(bad)
                page.get_by_role("button", name="Save daily record", exact=True).click()
                expect(field).to_have_attribute("aria-invalid", "true")
                field.fill(old)
            check("representative integer and range violations are blocked in UI", len([r for r in requests if r["method"] == "POST"]) == before)
            for name, changes in [("impossible sleep latency", {"sleep_duration_hours": 8, "sleep_efficiency_pct": 100, "sleep_onset_delay_minutes": 60}),
                                  ("over 24-hour daily budget", {"sleep_duration_hours": 8, "sleep_efficiency_pct": 90, "workload_hours": 20})]:
                fill(page, {**RECORDS[0], **changes})
                with page.expect_response(lambda r: r.url.endswith("/api/v1/assess") and r.request.method == "POST") as response:
                    page.get_by_role("button", name="Save daily record", exact=True).click()
                check(name + " rejected by backend and surfaced as not saved", response.value.status == 422)
                expect(page.locator(".saved-note[data-level='critical']")).to_contain_text("Not saved")
            fill(page, RECORDS[0])

            # A virtual clock controls task delays; every response event is synthetic.
            page.clock.install()
            page.clock.pause_at(datetime.now(timezone.utc))
            page.evaluate("window.auditOriginalRandom=Math.random;Math.random=()=>0")
            pad = page.locator("article[appReactionTest] .pad")
            old_rt = page.locator("#f-reaction_time_median_ms").input_value()
            page.get_by_role("button", name="Quick demo · 10 taps", exact=True).click()
            page.clock.run_for(20)  # Flush Angular's scheduled render under the virtual clock.
            pad.press("Enter")
            page.clock.run_for(20)
            pad.press("Enter")
            page.clock.run_for(20)
            expect(pad).to_have_attribute("data-phase", "early")
            page.clock.run_for(1000)
            for _ in range(10):
                page.clock.run_for(1200)
                page.clock.run_for(200)
                pad.press("Enter")
                page.clock.run_for(20)
            expect(pad).to_have_attribute("data-phase", "done")
            expect(page.get_by_role("button", name="Use these results", exact=True)).to_be_disabled()
            check("quick reaction demo counts early taps but cannot populate model fields", "1 false start" in pad.inner_text() and page.locator("#f-reaction_time_median_ms").input_value() == old_rt)
            page.get_by_role("button", name="Full demo · 60 taps", exact=True).click()
            page.clock.run_for(20)
            expect(pad).to_have_attribute("data-phase", "idle")
            pad.press("Enter")
            page.clock.run_for(20)
            for index in range(60):
                page.clock.run_for(2000)
                page.clock.run_for(700 if index == 0 else 200)
                pad.press("Enter")
                page.clock.run_for(20)
            expect(pad).to_have_attribute("data-phase", "done")
            expect(page.get_by_role("button", name="Use these results", exact=True)).to_be_enabled()
            page.get_by_role("button", name="Use these results", exact=True).click()
            page.clock.run_for(20)
            median_value = float(page.locator("#f-reaction_time_median_ms").input_value())
            check("full synthetic median reflects scripted responses", 200 <= median_value <= 240, median_value)
            expect(page.locator("#f-reaction_time_lapses_count")).to_have_value("1")
            expect(page.get_by_role("button", name="Added to the form", exact=True)).to_be_disabled()
            check("full 60-response synthetic session applies median and lapse count only once", True)
            page.get_by_role("button", name="Retake", exact=True).click()
            page.clock.run_for(20)
            page.evaluate("window.dispatchEvent(new Event('blur'))")
            page.clock.run_for(20)
            expect(pad).to_have_attribute("data-phase", "interrupted")
            expect(page.get_by_role("button", name="Use these results", exact=True)).to_be_disabled()
            check("reaction session invalidates on focus loss", True)
            page.get_by_role("button", name="Retake", exact=True).click()
            page.clock.run_for(20)
            expect(pad).to_have_attribute("data-phase", "waiting")
            page.get_by_role("tab", name="Overview", exact=True).click()
            page.clock.run_for(20)
            page.get_by_role("tab", name="Check-in", exact=True).click()
            page.clock.run_for(20)
            expect(pad).to_have_attribute("data-phase", "idle")
            check("navigating away cancels task and return starts fresh", True)
            page.evaluate("Math.random=window.auditOriginalRandom;delete window.auditOriginalRandom")
            page.clock.resume()

            # Exact demo state switching is already covered by integration tests; include a no-network assertion here.
            page.get_by_role("tab", name="Alert demo", exact=True).click()
            before = len(requests)
            for preset, level in [("healthy", "0"), ("review", "1"), ("high", "2"), ("urgent", "3"), ("unknown", "UNKNOWN")]:
                page.locator("#clinical-demo-scenario").select_option(preset)
                expect(page.locator(".demo-result")).to_have_attribute("data-demo-level", level)
            check("all five illustrative alert states cause no API traffic", len(requests) == before)

            for width in [320, 375, 768, 1440]:
                page.set_viewport_size({"width": width, "height": 1000})
                for view in ["Overview", "Check-in", "Trends", "Guide", "Alert demo"]:
                    page.get_by_role("tab", name=view, exact=True).click()
                    expect(page.get_by_role("tab", name=view, exact=True)).to_have_attribute("aria-selected", "true")
                    dimensions = page.evaluate("""() => ({width:innerWidth, doc:document.documentElement.scrollWidth,
                      bad:[...document.querySelectorAll('.shell,.light,.main-col,.topnav,.pills')].filter(e=>e.getBoundingClientRect().right>innerWidth+2).map(e=>e.className)})""")
                    check(f"{view} fits {width}px viewport", dimensions["doc"] <= width + 2 and not dimensions["bad"], dimensions)
                tabs = page.get_by_role("tab").evaluate_all("xs=>xs.map(x=>({name:x.textContent.trim(),...{width:x.getBoundingClientRect().width,height:x.getBoundingClientRect().height,left:x.getBoundingClientRect().left,right:x.getBoundingClientRect().right}}))")
                check(f"all primary tabs remain visible at {width}px", all(x["left"] >= 0 and x["right"] <= width + 1 for x in tabs))
                page.get_by_role("tab", name="Overview", exact=True).click()
                expect(page.get_by_role("tab", name="Overview", exact=True)).to_have_attribute("aria-selected", "true")
                expect(page.locator("article[appFatigueCard]")).to_be_visible()
                shot(page, f"ui-final-overview-{width}.png")
                if width < 800:
                    page.locator("article[appFatigueCard]").scroll_into_view_if_needed()
                    shot(page, f"ui-final-forecast-{width}.png")
            page.set_viewport_size({"width": 1440, "height": 1100})
            page.get_by_role("tab", name="Check-in", exact=True).focus()
            page.keyboard.press("Enter")
            expect(page.locator("article[appLogForm]")).to_be_visible()
            page.keyboard.press("Tab")
            check("keyboard activates primary view and advances focus", page.evaluate("document.activeElement !== document.body"))
            finding("Accessibility audit scope", "Primary navigation, reaction task and recommendation controls are keyboard-operable, and all numeric inputs have labels. Screen-reader behavior, contrast ratios and full WCAG conformance were not audited. Trend pointer tooltips do not have keyboard equivalents.")

            # Explicit offline demo uses in-memory observations and must never imply backend persistence.
            page.get_by_role("button", name="Preview demo data", exact=True).click()
            expect(page.locator(".intro .env")).to_contain_text("demo mode")
            page.get_by_role("tab", name="Check-in", exact=True).click()
            before = len(requests)
            fill(page, {**RECORDS[0], "sleep_duration_hours": 8, "sleep_efficiency_pct": 90, "workload_hours": 20})
            page.get_by_role("button", name="Save daily record", exact=True).click()
            expect(page.locator(".saved-note[data-level='critical']")).to_contain_text("Not saved")
            check("offline demo rejects impossible daily budget without network or append", len(requests) == before)
            fill(page, {**RECORDS[0], "sleep_duration_hours": 8, "sleep_efficiency_pct": 100, "sleep_onset_delay_minutes": 60})
            page.get_by_role("button", name="Save daily record", exact=True).click()
            expect(page.locator(".saved-note[data-level='critical']")).to_contain_text("Not saved")
            check("offline demo rejects impossible sleep latency", len(requests) == before)
            fill(page, RECORDS[0])
            page.locator("#log-journal").fill("Synthetic session-only audit note")
            page.get_by_role("button", name="Save daily record", exact=True).click()
            expect(page.locator(".saved-note[data-level='warning']")).to_contain_text("only in this browser session")
            check("explicit offline save is labeled session-only and makes no API call", len(requests) == before)
            page.get_by_role("tab", name="Overview", exact=True).click()
            expect(page.locator(".fc-index")).to_have_count(0)
            check("new offline observation has no fabricated forecast", page.locator(".fc-index").count() == 0)
            page.reload()
            expect(page.locator(".intro .env")).to_contain_text("demo mode")
            check("reload resets unsaved demo session to eight fictional example records", page.locator(".timeline-pill").inner_text().endswith("Record 8"))
            page.get_by_role("button", name="Connect to backend", exact=True).click()
            expect(page.locator(".intro .env")).to_contain_text("Records from the backend")
            check("return from demo restores unchanged backend history", page.locator(".timeline-pill").inner_text().endswith("Record 9"))

            # URL configuration and recovery: capture behavior rather than assume validated input.
            page.get_by_role("tab", name="Check-in", exact=True).click()
            page.once("dialog", lambda dialog: dialog.dismiss())
            page.get_by_role("button", name="change", exact=True).click()
            check("canceling backend settings leaves valid connection intact", page.locator(".intro .env").inner_text().strip() == "Records from the backend")
            prior_url = page.evaluate("localStorage.getItem('apiBase')")
            for invalid_url in ["not a valid URL", "javascript:alert(1)", "https://user:password@example.test/api/v1", "//example.test/api/v1"]:
                page.once("dialog", lambda dialog, value=invalid_url: dialog.accept(value))
                page.get_by_role("button", name="change", exact=True).click()
                expect(page.locator("article[appCalibrationCard] [role='alert']")).to_be_visible()
                check("malformed backend address rejected without losing valid connection: " + invalid_url.split(":")[0],
                      page.evaluate("localStorage.getItem('apiBase')") == prior_url and "Records from the backend" in page.locator(".intro .env").inner_text())
            page.once("dialog", lambda dialog: dialog.accept(""))
            page.get_by_role("button", name="change", exact=True).click()
            expect(page.locator(".intro .env")).to_contain_text("Records from the backend")
            check("empty backend setting restores working same-origin default", page.evaluate("localStorage.getItem('apiBase')") is None)
            check("no uncaught browser JavaScript errors", not errors, errors)
            check("UI validation did not modify backend fixture", request_json(frontend + f"/api/v1/astronauts/{identifier}/history")[1]["total_assessments"] == 9)
            report["passed"] = True
            browser.close()
    except Exception:
        report["exception"] = traceback.format_exc()
        print(report["exception"], flush=True)
    finally:
        report["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
        report["passed_check_count"] = sum(c["passed"] for c in checks)
        report["failed_check_count"] = sum(not c["passed"] for c in checks)
        sources = [*sorted((ROOT / "frontend/src").rglob("*.ts")), ROOT / "frontend/src/styles.css", Path(__file__)]
        report["source_sha256"] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources if p.is_file()}
        (REPORTS / "UI_FINAL_CHECKS.json").write_text(json.dumps(report, indent=2) + "\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
