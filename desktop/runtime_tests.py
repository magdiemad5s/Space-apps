"""Bundled launcher regressions. Run with the pinned model Python environment.

These tests exercise proxy semantics, filesystem boundaries, writable storage
locking and service cleanup. `runtime.py --smoke-test` additionally loads the
actual unchanged artifact and runs inference through the compiled backend.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from runtime import BackendProcess, DataDirectoryLock, listening_socket, make_web_app, validate_resources


class DirectoryLockTests(unittest.TestCase):
    def test_second_launcher_cannot_share_history_but_can_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = DataDirectoryLock(Path(tmp))
            try:
                with self.assertRaisesRegex(RuntimeError, "already using"):
                    DataDirectoryLock(Path(tmp))
            finally:
                first.close()
            restarted = DataDirectoryLock(Path(tmp))
            restarted.close()

    def test_separate_history_directories_can_run_independently(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = DataDirectoryLock(Path(tmp) / "one")
            second = DataDirectoryLock(Path(tmp) / "two")
            first.close()
            second.close()


class BindingTests(unittest.TestCase):
    def test_bind_only_loopback_and_fallback_without_stealing_port(self):
        first = listening_socket()
        try:
            self.assertEqual(first.getsockname()[0], "127.0.0.1")
            port = first.getsockname()[1]
            with self.assertRaises(OSError):
                listening_socket(port)
            second = listening_socket(port, fallback=True)
            try:
                self.assertNotEqual(second.getsockname()[1], port)
            finally:
                second.close()
        finally:
            first.close()

    def test_missing_bundle_fails_before_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError, "resources are missing"):
                validate_resources(Path(tmp))

    def test_missing_bundle_exits_nonzero_and_writes_failure_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "result.json"
            result = subprocess.run([sys.executable, str(Path(__file__).with_name("runtime.py")),
                                     "--resources", tmp, "--smoke-test", "--report", str(report)],
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 1)
            body = json.loads(report.read_text())
            self.assertIs(body["passed"], False)
            self.assertIn("resources are missing", body["error"])
            self.assertTrue(body["checks"][-1]["passed"])


class ProxyTests(unittest.TestCase):
    def setUp(self):
        import httpx
        from fastapi.testclient import TestClient

        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.frontend = self.root / "frontend"
        self.frontend.mkdir()
        (self.frontend / "index.html").write_text("<app-root>bundled UI</app-root>")
        (self.frontend / "main.js").write_text("window.loaded=true;")
        (self.root / "private.txt").write_text("PRIVATE")
        self.app = make_web_app(self.frontend, "http://127.0.0.1:12345")
        self.client = TestClient(self.app).__enter__()
        self.forwarded = []
        self.response_code = 201
        self.raise_error = False

        class FakeBackend:
            async def request(inner, method, path, headers, content):
                self.forwarded.append((method, path, headers, content))
                if self.raise_error:
                    raise httpx.ConnectError("offline")
                return httpx.Response(self.response_code, content=b'{"saved":true}',
                                      headers={"content-type": "application/json", "x-result": "model",
                                               "connection": "keep-alive"})

        self.app.state.backend = FakeBackend()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.tmp.cleanup()

    def test_same_origin_proxy_preserves_method_query_body_status_and_headers(self):
        response = self.client.post("/api/v1/assess?mode=trial&extra=2", content=b'{"feature":1}',
                                    headers={"content-type": "application/json", "x-client": "ui"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json(), {"saved": True})
        self.assertEqual(response.headers["x-result"], "model")
        self.assertNotIn("connection", response.headers)
        method, path, headers, body = self.forwarded[0]
        self.assertEqual(method, "POST")
        self.assertEqual(path, "/api/v1/assess?mode=trial&extra=2")
        self.assertEqual(body, b'{"feature":1}')
        self.assertNotIn("host", headers)
        self.assertEqual(headers["x-client"], "ui")

    def test_delete_and_validation_statuses_are_not_transformed(self):
        for status in (202, 409, 422, 503):
            self.response_code = status
            response = self.client.delete("/api/v1/astronauts/DEMO_TEST/history")
            self.assertEqual(response.status_code, status)
            self.assertEqual(self.forwarded[-1][0], "DELETE")

    def test_backend_outage_is_visible_without_demo_fallback(self):
        self.raise_error = True
        response = self.client.get("/api/v1/health")
        self.assertEqual(response.status_code, 503)
        self.assertIn("unavailable", response.json()["error"])
        self.assertNotIn("<app-root", response.text)

    def test_oversize_input_is_rejected_before_forwarding(self):
        response = self.client.post("/api/v1/assess", content=b"x" * (100 * 1024 + 1))
        self.assertEqual(response.status_code, 413)
        self.assertEqual(self.forwarded, [])

    def test_spa_routes_assets_and_api_are_distinct(self):
        index = self.client.get("/")
        self.assertEqual(index.status_code, 200)
        self.assertEqual(index.headers["cache-control"], "no-cache")
        self.assertEqual(self.client.get("/dashboard/deep").text, index.text)
        self.assertEqual(self.client.get("/main.js").text, "window.loaded=true;")
        self.assertEqual(self.client.get("/missing.js").status_code, 404)
        self.assertEqual(self.client.head("/main.js").content, b"")
        self.response_code = 404
        self.assertEqual(self.client.get("/api/v1/no-such-route").status_code, 404)

    def test_static_paths_cannot_escape_frontend(self):
        response = self.client.get("/%2e%2e%2fprivate.txt")
        self.assertEqual(response.status_code, 404)
        self.assertNotIn("PRIVATE", response.text)
        if hasattr(os, "symlink"):
            try:
                (self.frontend / "leak.txt").symlink_to(self.root / "private.txt")
            except OSError:
                return  # Ordinary Windows test runners may lack symlink privilege.
            self.assertEqual(self.client.get("/leak.txt").status_code, 404)


class ProcessCleanupTests(unittest.TestCase):
    def test_backend_stops_and_log_handle_closes(self):
        with tempfile.TemporaryDirectory() as tmp:
            child = BackendProcess([sys.executable, "-c", "import time; time.sleep(60)"], Path(tmp),
                                   os.environ.copy(), Path(tmp) / "child.log")
            child.close()
            self.assertIsNotNone(child.process.poll())
            self.assertTrue(child.log.closed)

    @unittest.skipUnless(os.name == "nt", "Windows Job Object cleanup regression")
    def test_windows_job_kills_descendants_after_leader_exits(self):
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        with tempfile.TemporaryDirectory() as tmp:
            pidfile = Path(tmp) / "descendant.pid"
            command = ("import pathlib,subprocess,sys,time; time.sleep(.3); "
                       "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
                       "pathlib.Path(sys.argv[1]).write_text(str(child.pid))")
            child = BackendProcess([sys.executable, "-c", command, str(pidfile)], Path(tmp), os.environ.copy(), Path(tmp) / "child.log")
            handle = None
            try:
                deadline = time.monotonic() + 5
                while not pidfile.exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue(pidfile.exists())
                handle = kernel.OpenProcess(0x00100000, False, int(pidfile.read_text()))  # SYNCHRONIZE
                self.assertTrue(handle)
                child.process.wait(timeout=5)
                child.close()
                self.assertEqual(kernel.WaitForSingleObject(handle, 5000), 0)  # WAIT_OBJECT_0
            finally:
                if not child.log.closed:
                    child.close()
                if handle:
                    kernel.CloseHandle(handle)

    @unittest.skipUnless(os.name == "posix", "Linux process-group cleanup regression")
    def test_cleanup_reaches_descendant_after_leader_exits(self):
        with tempfile.TemporaryDirectory() as tmp:
            pidfile = Path(tmp) / "descendant.pid"
            command = ("import pathlib,subprocess,sys; "
                       "child=subprocess.Popen([sys.executable,'-c','import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(60)']); "
                       "pathlib.Path(sys.argv[1]).write_text(str(child.pid))")
            child = BackendProcess([sys.executable, "-c", command, str(pidfile)], Path(tmp), os.environ.copy(), Path(tmp) / "child.log")
            try:
                deadline = time.monotonic() + 5
                while not pidfile.exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue(pidfile.exists())
                descendant = int(pidfile.read_text())
                child.process.wait(timeout=5)
            finally:
                child.close()
            deadline = time.monotonic() + 3
            status = Path(f"/proc/{descendant}/stat")
            while status.exists() and status.read_text().split()[2] != "Z" and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(not status.exists() or status.read_text().split()[2] == "Z")


if __name__ == "__main__":
    unittest.main(verbosity=2)
