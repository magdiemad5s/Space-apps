#!/usr/bin/env python3
"""Linux bundled-runtime lifecycle checks using isolated fictional history.

Run with the pinned model Python environment; --resources must contain staged
compiled backend/frontend, the Node executable and the unchanged model.
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
import sys
import time
import traceback
import urllib.parse
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--resources', type=Path, default=ROOT / '.local/desktop-test/resources')
parser.add_argument('--python', default=sys.executable, help='Pinned model Python interpreter')
parser.add_argument('--report', type=Path, default=ROOT / 'integration-reports/DESKTOP_LIFECYCLE_CHECKS.json')
parser.add_argument('--run-dir', type=Path, default=ROOT / '.local/desktop-lifecycle', help='Parent for a new isolated run directory')
args = parser.parse_args()
if not sys.platform.startswith('linux'):
    parser.error('This process/port lifecycle check requires Linux; Windows uses the executable smoke test and runtime unit tests.')
RESOURCES = args.resources.expanduser().resolve()
RUN = args.run_dir.expanduser().resolve() / uuid.uuid4().hex[:12]
RUN.mkdir(parents=True)
DATA = RUN / 'data'
REPORT = args.report.expanduser().resolve()
PYTHON = args.python


def path_label(path):
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
checks = []
report = {
    'started_at_utc': datetime.now(timezone.utc).isoformat(),
    'scope': 'Linux unfrozen Python launcher with compiled Angular, compiled Node backend and unchanged model artifact',
    'windows_executed': False,
    'frozen_executable': False,
    'data': 'Isolated fictional DEMO_SIM_001 records; no model training or ML accuracy evaluation',
    'data_directory': path_label(DATA),
    'checks': checks,
    'passed': False,
}
processes = []
logs = []
ports_by_run = []


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(name, passed, detail=None):
    checks.append({'name': name, 'passed': bool(passed), **({'detail': detail} if detail is not None else {})})
    print(('PASS ' if passed else 'FAIL ') + name, flush=True)
    if not passed:
        raise AssertionError(name)


def wait_for(predicate, timeout=180, process=None):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if process is not None and process.poll() is not None:
            raise AssertionError('Launcher exited before expected readiness: ' + str(process.returncode))
        result = predicate()
        if result:
            return result
        time.sleep(.15)
    raise AssertionError('Lifecycle condition timed out')


def launch(name):
    logpath = RUN / (name + '.log')
    handle = logpath.open('wb')
    logs.append(handle)
    process = subprocess.Popen([PYTHON, str(ROOT / 'desktop/runtime.py'), '--resources', str(RESOURCES),
                                '--data-dir', str(DATA), '--port', '0', '--no-browser', '--seed-demo'],
                               cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT, start_new_session=True)
    processes.append(process)
    return process, logpath


def info_for(process):
    paths = sorted((DATA / 'logs').glob('*-' + str(process.pid) + '/runtime.json'))
    if not paths:
        return None
    return json.loads(paths[-1].read_text())


def request_json(url):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url, timeout=10) as response:
        return json.load(response)


def history_ready(url, expected):
    try:
        value = request_json(url + '/api/v1/astronauts/DEMO_SIM_001/history')
        return value if len(value['observations']) == expected else None
    except Exception:
        return None


def ports_for(info):
    # Read only our known backend process's environment and retain three
    # runtime settings; do not log other environment variables.
    env = {}
    for item in Path(f"/proc/{info['backend_pid']}/environ").read_bytes().split(b'\0'):
        key, _, value = item.partition(b'=')
        if key in {b'PORT', b'AI_SERVICE_URL', b'DB_FILE'}:
            env[key.decode()] = value.decode()
    assert Path(env['DB_FILE']) == DATA / 'history_db_v2.json'
    return [urllib.parse.urlparse(info['url']).port, int(env['PORT']),
            urllib.parse.urlparse(env['AI_SERVICE_URL']).port]


def port_is_free(port):
    sock = socket.socket()
    sock.settimeout(.2)
    try:
        return sock.connect_ex(('127.0.0.1', port)) != 0
    finally:
        sock.close()


def process_stopped(pid):
    path = Path(f'/proc/{pid}/stat')
    return not path.exists() or path.read_text().split()[2] == 'Z'


def staged_backend_pids():
    output = subprocess.check_output(['ps', '-eo', 'pid,args'], text=True)
    target = str(RESOURCES / 'backend/server.js')
    return sorted(int(line.strip().split(None, 1)[0]) for line in output.splitlines()[1:] if target in line)


try:
    source_paths = [Path(__file__).resolve(), ROOT / 'desktop/runtime.py', ROOT / 'desktop/runtime_tests.py',
                    ROOT / 'ai/astra_shield_ml/api.py', ROOT / 'ai/astra_shield_ml/service.py',
                    ROOT / 'ai/astra_shield_ml/features.py', ROOT / 'ai/astra_shield_ml/estimators.py',
                    ROOT / 'ai/artifacts/bundle.joblib']
    source_paths += [RESOURCES / name for name in ['backend/server.js', 'backend/featureHistory.js',
                     'backend/modelClient.js', 'backend/package.json', 'frontend/index.html',
                     'fixtures/synthetic_daily_sequence.json', 'model/bundle.joblib']]
    report['source_sha256'] = {path_label(path): sha(path) for path in source_paths}
    check('staged model is byte-identical to unchanged source artifact', sha(RESOURCES / 'model/bundle.joblib') == sha(ROOT / 'ai/artifacts/bundle.joblib'))

    first, first_log = launch('initial')
    first_info = wait_for(lambda: info_for(first), process=first)
    first_ports = ports_for(first_info)
    ports_by_run.append(first_ports)
    history = wait_for(lambda: history_ready(first_info['url'], 9), process=first)
    check('initial seed stores exactly nine fictional observations', len(history['observations']) == 9)
    check('day-eight and day-nine records use real synthetic model', all(record['inference_source'] == 'synthetic_model' for record in history['history'][-2:]))
    db_path = DATA / 'history_db_v2.json'
    original_hash = sha(db_path)
    report['seeded_history_sha256'] = original_hash
    initial_backends = staged_backend_pids()

    duplicate, duplicate_log = launch('duplicate')
    duplicate.wait(timeout=25)
    check('second instance fails visibly before opening shared storage', duplicate.returncode == 1 and 'already using this data directory' in duplicate_log.read_text())
    check('second instance does not alter history bytes', sha(db_path) == original_hash)
    check('second instance leaves no additional backend process', staged_backend_pids() == initial_backends)
    check('original instance remains healthy after rejected second launch', request_json(first_info['url'] + '/api/v1/health')['ai_service']['model_ready'] is True)

    first.send_signal(signal.SIGINT)
    first.wait(timeout=25)
    check('Ctrl+C shuts launcher down successfully', first.returncode == 0)
    wait_for(lambda: all(port_is_free(port) for port in first_ports), timeout=15)
    check('Ctrl+C releases web, backend and model ports', all(port_is_free(port) for port in first_ports), {'ports': first_ports})
    check('Ctrl+C leaves no Node child', process_stopped(first_info['backend_pid']))
    check('Ctrl+C preserves history bytes', sha(db_path) == original_hash)

    restarted, restart_log = launch('restart')
    restart_info = wait_for(lambda: info_for(restarted), process=restarted)
    restart_ports = ports_for(restart_info)
    ports_by_run.append(restart_ports)
    wait_for(lambda: 'seeding skipped' in restart_log.read_text(), process=restarted)
    restored = request_json(restart_info['url'] + '/api/v1/astronauts/DEMO_SIM_001/history')
    check('restart skips seeding existing participant', 'seeding skipped' in restart_log.read_text())
    check('restart returns the same nine observations', restored['observations'] == history['observations'] and len(restored['observations']) == 9)
    check('restart leaves history byte-identical', sha(db_path) == original_hash)

    os.kill(restart_info['backend_pid'], signal.SIGKILL)
    restarted.wait(timeout=25)
    check('forced backend exit triggers supervisor failure', restarted.returncode == 1 and 'A local service exited' in restart_log.read_text())
    wait_for(lambda: all(port_is_free(port) for port in restart_ports), timeout=15)
    check('backend failure releases all three service ports', all(port_is_free(port) for port in restart_ports), {'ports': restart_ports})
    check('backend failure leaves no Node child', process_stopped(restart_info['backend_pid']))
    check('backend failure preserves history bytes', sha(db_path) == original_hash)
    error_path = DATA / 'logs' / next(path.name for path in (DATA / 'logs').iterdir() if path.name.endswith('-' + str(restarted.pid))) / 'error.log'
    check('supervisor failure is recorded in persistent error log', error_path.exists() and 'A local service exited' in error_path.read_text())

    # Restart once more to prove that forced failure did not leave a stale lock.
    recovered, recovered_log = launch('recovery')
    recovered_info = wait_for(lambda: info_for(recovered), process=recovered)
    recovery_ports = ports_for(recovered_info)
    ports_by_run.append(recovery_ports)
    wait_for(lambda: 'seeding skipped' in recovered_log.read_text(), process=recovered)
    check('restart after forced failure reacquires lock and restores readiness', request_json(recovered_info['url'] + '/api/v1/health')['ai_service']['model_ready'] is True)
    recovered.send_signal(signal.SIGINT)
    recovered.wait(timeout=25)
    wait_for(lambda: all(port_is_free(port) for port in recovery_ports), timeout=15)
    check('recovery shutdown is clean and history remains unchanged', recovered.returncode == 0 and all(port_is_free(port) for port in recovery_ports) and sha(db_path) == original_hash)
    report['passed'] = True
except Exception:
    report['error'] = traceback.format_exc()
    print(report['error'], flush=True)
finally:
    for process in processes:
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
    for log in logs:
        log.close()
    report['completed_at_utc'] = datetime.now(timezone.utc).isoformat()
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + '\n')
    print('REPORT ' + str(REPORT), flush=True)
sys.exit(0 if report['passed'] else 1)
