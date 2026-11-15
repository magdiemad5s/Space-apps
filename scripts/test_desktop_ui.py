#!/usr/bin/env python3
"""Browser smoke against the compiled dashboard served by desktop/runtime.py.

Run a runtime with isolated synthetic storage first. This checks UI integration,
not medical behavior. Playwright/Chromium are development-only dependencies.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import uuid

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:4173')
    parser.add_argument('--chromium', default='/usr/bin/chromium')
    args = parser.parse_args()
    checks, errors, external = [], [], []
    report = {'passed': False, 'checked_at_utc': datetime.now(timezone.utc).isoformat(),
              'scope': 'Linux Chromium, compiled production Angular, unfrozen desktop runtime, real backend/model',
              'clinical_validation': False, 'checks': checks, 'browser_errors': errors,
              'external_requests': external}
    destination = ROOT / 'integration-reports/DESKTOP_PRODUCTION_UI_CHECKS.json'
    fixture = json.loads((ROOT / 'ai/integration/backend_review/proposed_backend/examples/synthetic_daily_sequence.json').read_text())
    identifier = 'DEMO_PRODUCTION_' + uuid.uuid4().hex[:10]

    def check(name, value):
        checks.append({'name': name, 'passed': bool(value)})
        if not value:
            raise AssertionError(name)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=args.chromium, args=['--no-sandbox', '--disable-dev-shm-usage'])
            page = browser.new_page(viewport={'width': 1440, 'height': 1080})
            page.set_default_timeout(20000)
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('request', lambda request: external.append(request.url) if not request.url.startswith(args.url.rstrip('/') + '/') else None)
            page.goto(args.url)
            expect(page.locator('.intro .env')).to_contain_text('Records from the backend')
            page.evaluate('document.fonts.ready')
            check('compiled UI loads original local Manrope font', page.evaluate('document.fonts.check(\'16px "Manrope Variable"\')'))
            for record in fixture[:7]:
                response = page.request.post(args.url + '/api/v1/assess', data={**record, 'astronaut_id': identifier})
                check('production proxy calibration ' + str(len(checks)), response.status == 202)
            page.evaluate('(id)=>{localStorage.setItem("astronautId",id);localStorage.removeItem("astraDemoMode");localStorage.removeItem("apiBase")}', identifier)
            page.reload()
            expect(page.locator('article[appFatigueCard] .fc-category')).to_have_text('Calibrating')
            page.get_by_role('tab', name='Check-in', exact=True).click()
            for key, value in fixture[7].items():
                if key not in {'astronaut_id', 'observation_timestamp_utc', 'journal_text'}:
                    page.locator('#f-' + key).fill(str(value))
            page.locator('#log-journal').fill('Fictional production-build browser check.')
            with page.expect_response(lambda r: r.url.endswith('/api/v1/assess') and r.request.method == 'POST', timeout=40000) as posted:
                page.get_by_role('button', name='Save daily record', exact=True).click()
            result = posted.value.json()
            check('production form produces actual day-eight forecast', posted.value.status == 201 and result['inference_source'] == 'synthetic_model')
            page.get_by_role('tab', name='Overview', exact=True).click()
            expect(page.locator('article[appFatigueCard] .fc-category')).to_have_text(result['fatigue_risk_level'])
            reasons = result['explanation']['top_contributing_factors']
            check('actual model returns three SHAP reasons', len(reasons) == 3)
            for reason in reasons:
                expect(page.locator('section[appInsightsPanel]')).to_contain_text(f"{reason['shap_value']:+.3f}")
            check('compiled UI displays actual SHAP values', True)
            for name in ['Check-in', 'Trends', 'Guide', 'Alert demo', 'Overview']:
                page.get_by_role('tab', name=name, exact=True).click()
            check('all five production views open', not errors)
            page.set_viewport_size({'width': 375, 'height': 900})
            check('production mobile page fits viewport', page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
            page.screenshot(path=str(ROOT / 'integration-reports/desktop-production-mobile.png'), full_page=True)
            check('production UI makes no external requests', not external)
            check('production UI has no uncaught JavaScript errors', not errors)
            report['forecast'] = {'category': result['fatigue_risk_level'], 'points': result['fatigue_points']}
            report['passed'] = True
            browser.close()
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        report['source_sha256'] = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                                   for path in [ROOT / 'desktop/runtime.py', Path(__file__), ROOT / 'ai/artifacts/bundle.joblib']}
        destination.write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps({'passed': report['passed'], 'checks': len(checks), 'report': str(destination)}))


if __name__ == '__main__':
    main()
