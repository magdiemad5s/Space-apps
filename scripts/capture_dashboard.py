"""Capture the running local app with its original, locally bundled Manrope font.

Requires Playwright and Chromium; no model training or external requests.
"""
from pathlib import Path
import argparse
import hashlib
import json
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:4200')
    parser.add_argument('--chromium', default='/usr/bin/chromium')
    args = parser.parse_args()
    report_dir = ROOT / 'integration-reports'
    report_dir.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=args.chromium, headless=True,
                                   args=['--no-sandbox', '--disable-dev-shm-usage'])
        page = browser.new_page(viewport={'width': 1440, 'height': 1080}, device_scale_factor=1)
        external = []
        errors = []
        expected_host = urlparse(args.url).netloc
        page.on('request', lambda request: external.append(request.url)
                if urlparse(request.url).scheme in ('http', 'https') and urlparse(request.url).netloc != expected_host else None)
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(args.url)
        expect(page.locator('.intro .env')).to_contain_text('Records from the backend')
        expect(page.locator('article[appFatigueCard] .fc-category')).to_be_visible()
        page.evaluate('document.fonts.ready')
        font_loaded = page.evaluate('document.fonts.check(\'400 16px "Manrope Variable"\')')
        assert font_loaded
        page.screenshot(path=str(report_dir / 'dashboard-current.png'))
        desktop_font = page.evaluate('getComputedStyle(document.body).fontFamily')
        page.set_viewport_size({'width': 375, 'height': 1000})
        page.evaluate('document.fonts.ready')
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.screenshot(path=str(report_dir / 'dashboard-current-mobile.png'))
        assert not external, external
        assert not errors, errors
        browser.close()
    record = {'original_font_restored_locally': font_loaded, 'computed_body_font_family': desktop_font,
              'external_network_requests': external, 'browser_errors': errors,
              'desktop_viewport': [1440, 1080], 'mobile_viewport': [375, 1000],
              'scope': 'Actual local dashboard and unchanged model; synthetic demo history',
              'files_sha256': {str(f.relative_to(ROOT)): hashlib.sha256(f.read_bytes()).hexdigest()
                              for f in [ROOT/'frontend/src/styles.css', ROOT/'frontend/src/index.html',
                                        ROOT/'frontend/package-lock.json', report_dir/'dashboard-current.png',
                                        report_dir/'dashboard-current-mobile.png']}}
    (report_dir/'DASHBOARD_VISUAL_CHECKS.json').write_text(json.dumps(record, indent=2)+'\n')
    print(json.dumps(record, indent=2))

if __name__ == '__main__':
    main()
