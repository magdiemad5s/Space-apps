"""Process and readiness checks for the launcher; no trained model is loaded."""
from __future__ import annotations

import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest

from launcher_common import LauncherError, node_supported, checked_python, default_model_path, ROOT, AI
from start import Stack, parser, port_available


SERVER = """
import http.server, json, sys
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'status': sys.argv[2]}).encode())
    def log_message(self, *args): pass
http.server.HTTPServer(('127.0.0.1', int(sys.argv[1])), Handler).serve_forever()
"""


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.stack = Stack(Path(self.temp.name))

    def tearDown(self):
        self.stack.stop()
        self.temp.cleanup()

    def server(self, status="ready"):
        port = free_port()
        child = self.stack.launch("fixture", [sys.executable, "-u", "-c", SERVER, str(port), status],
                                  Path(self.temp.name), dict(os.environ))
        return child, f"http://127.0.0.1:{port}/health"

    def test_node_version_boundaries(self):
        for version in ["v22.22.3", "22.23.0", "24.15.0", "v24.22.1", "26.0.0"]:
            self.assertTrue(node_supported(version), version)
        for version in ["22.22.2", "24.14.99", "20.99.99", "23.99.99", "25.0.0", "nonsense"]:
            self.assertFalse(node_supported(version), version)

    def test_windows_uses_portable_inference_export_and_linux_keeps_research_bundle(self):
        self.assertEqual(default_model_path('nt'), ROOT / 'desktop/artifacts/inference_bundle.joblib')
        self.assertEqual(default_model_path('posix'), AI / 'artifacts/bundle.joblib')

    @unittest.skipIf(os.name == "nt", "POSIX venv interpreters use symlinks")
    def test_python_virtualenv_symlink_is_not_dereferenced(self):
        alias = Path(self.temp.name) / "python-venv"
        alias.symlink_to(sys.executable)
        self.assertEqual(checked_python(alias), str(alias.absolute()))
        self.assertNotEqual(checked_python(alias), str(alias.resolve()))

    def test_occupied_port_is_not_available(self):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            sock.listen()
            self.assertFalse(port_available(sock.getsockname()[1]))
            # The existing listener stays alive; nothing is killed or replaced.
            self.assertNotEqual(sock.fileno(), -1)

    def test_ready_requires_expected_payload(self):
        _, url = self.server("starting")
        with self.assertRaisesRegex(LauncherError, "was not ready"):
            self.stack.ready("Fixture", url, lambda value: value.get("status") == "ready", 0.6)

    def test_real_ready_endpoint_is_accepted(self):
        _, url = self.server()
        self.stack.ready("Fixture", url, lambda value: value.get("status") == "ready", 5)

    def test_early_child_death_stops_startup(self):
        self.stack.launch("failed", [sys.executable, "-c", "raise SystemExit(7)"], Path(self.temp.name), dict(os.environ))
        with self.assertRaisesRegex(LauncherError, "failed stopped"):
            self.stack.ready("Fixture", f"http://127.0.0.1:{free_port()}/health", lambda value: True, 5)

    def test_shutdown_releases_owned_port(self):
        child, url = self.server()
        self.stack.ready("Fixture", url, lambda value: value.get("status") == "ready", 5)
        port = int(url.split(":")[2].split("/")[0])
        self.stack.stop()
        self.assertIsNotNone(child.process.poll())
        self.assertTrue(port_available(port))
        self.stack.children.clear()

    @unittest.skipIf(os.name == "nt", "POSIX process-group check; Windows tree termination requires a Windows host")
    def test_shutdown_terminates_descendant_even_if_parent_exits(self):
        pidfile = Path(self.temp.name) / "descendant.pid"
        code = "import pathlib,subprocess,sys; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); pathlib.Path(sys.argv[1]).write_text(str(p.pid))"
        parent = self.stack.launch("parent", [sys.executable, "-c", code, str(pidfile)], Path(self.temp.name), dict(os.environ), required=False)
        parent.process.wait(timeout=5)
        descendant = int(pidfile.read_text())
        os.kill(descendant, 0)
        self.stack.stop()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            stat = Path(f"/proc/{descendant}/stat")
            if not stat.exists() or stat.read_text().split()[2] == "Z":
                break
            time.sleep(0.05)
        else:
            self.fail("Descendant remained running after stop")
        self.stack.children.clear()

    def test_cli_custom_paths_and_ports(self):
        args = parser().parse_args(["--python", "C:/My Python/python.exe", "--db-file", "My data/history.json",
                                  "--model-port", "18000", "--backend-port", "13000", "--frontend-port", "14200", "--no-browser"])
        self.assertEqual(args.python, "C:/My Python/python.exe")
        self.assertEqual(args.db_file, Path("My data/history.json"))
        self.assertEqual((args.model_port, args.backend_port, args.frontend_port), (18000, 13000, 14200))
        self.assertTrue(args.no_browser)


if __name__ == "__main__":
    unittest.main(verbosity=2)
