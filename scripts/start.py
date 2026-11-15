#!/usr/bin/env python3
"""Supervise the local frontend -> TypeScript backend -> unchanged Python model."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
from typing import IO, Callable
import urllib.error
import urllib.request
import webbrowser

from launcher_common import (ROOT, AI, BACKEND, FRONTEND, LOCAL, LauncherError,
                             checked_node, checked_python, check_file, default_python, fail)


@dataclass
class Child:
    name: str
    process: subprocess.Popen
    log: IO[str]
    log_path: Path
    required: bool = True


def port_number(value: str) -> int:
    number = int(value)
    if not 1 <= number <= 65535:
        raise argparse.ArgumentTypeError("Port must be between 1 and 65535.")
    return number


def port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        if os.name == "nt":
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            # Match normal local HTTP servers: a recently closed connection in
            # TIME_WAIT must not falsely block a restart. A live listener still
            # prevents this bind.
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def json_get(url: str, timeout: float = 2.0) -> dict:
    # Local service traffic should not be routed through HTTP_PROXY.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url, timeout=timeout) as response:
        return json.load(response)


class Stack:
    def __init__(self, log_directory: Path):
        self.children: list[Child] = []
        self.log_directory = log_directory
        self.log_directory.mkdir(parents=True, exist_ok=True)

    def launch(self, name: str, argv: list[str], cwd: Path, env: dict[str, str], required: bool = True) -> Child:
        log_path = self.log_directory / f"{name}.log"
        stream = log_path.open("w", encoding="utf-8")
        options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
        try:
            process = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                       stdout=stream, stderr=subprocess.STDOUT, **options)
        except BaseException:
            stream.close()
            raise
        child = Child(name, process, stream, log_path, required)
        self.children.append(child)
        print(f"Starting {name}; log: {log_path}", flush=True)
        return child

    def require_running(self) -> None:
        for child in self.children:
            if child.required and child.process.poll() is not None:
                raise LauncherError(f"{child.name} stopped (exit {child.process.returncode}). Read {child.log_path}.")

    def ready(self, name: str, url: str, predicate: Callable[[dict], bool], timeout: float) -> None:
        deadline = time.monotonic() + timeout
        next_progress = time.monotonic() + 10
        while time.monotonic() < deadline:
            self.require_running()
            try:
                payload = json_get(url)
                self.require_running()
                if predicate(payload):
                    print(f"{name} ready: {url}", flush=True)
                    return
            except (OSError, ValueError, urllib.error.URLError):
                pass
            if time.monotonic() >= next_progress:
                print(f"Waiting for {name} readiness…", flush=True)
                next_progress = time.monotonic() + 10
            time.sleep(0.25)
        raise LauncherError(f"{name} was not ready after {timeout:g}s. Check logs in {self.log_directory}.")

    def web_ready(self, url: str, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        next_progress = time.monotonic() + 10
        while time.monotonic() < deadline:
            self.require_running()
            try:
                with opener.open(url, timeout=2) as response:
                    body = response.read(100_000)
                    self.require_running()
                    if response.status == 200 and b"<app-root" in body:
                        print(f"Dashboard ready: {url}", flush=True)
                        return
            except (OSError, urllib.error.URLError):
                pass
            if time.monotonic() >= next_progress:
                print("Waiting for Angular to compile…", flush=True)
                next_progress = time.monotonic() + 10
            time.sleep(0.25)
        raise LauncherError(f"Dashboard was not ready after {timeout:g}s. Read {self.log_directory / 'frontend.log'}.")

    def stop(self) -> None:
        if not self.children:
            return
        print("\nStopping this launcher's services…", flush=True)
        if os.name == "nt":
            # Kill the full tree while its original PID still exists. Killing a
            # cmd/npm parent first can leave Node workers behind on Windows.
            for child in reversed(self.children):
                if child.process.poll() is None:
                    try:
                        result = subprocess.run(["taskkill", "/PID", str(child.process.pid), "/T", "/F"],
                                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10, check=False)
                        if result.returncode != 0 and child.process.poll() is None:
                            child.process.terminate()
                    except (OSError, subprocess.SubprocessError) as exc:
                        print(f"Warning: process-tree cleanup for {child.name} failed: {exc}", file=sys.stderr)
                        try:
                            child.process.terminate()
                        except OSError:
                            pass
        else:
            for child in reversed(self.children):
                try:
                    os.killpg(child.process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                except OSError as exc:
                    print(f"Warning: could not stop {child.name}: {exc}", file=sys.stderr)
            deadline = time.monotonic() + 4
            for child in self.children:
                try:
                    child.process.wait(timeout=max(0.05, deadline - time.monotonic()))
                except subprocess.TimeoutExpired:
                    pass
            for child in reversed(self.children):
                # The group may outlive its leader, so poll() alone is not enough.
                try:
                    os.killpg(child.process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                except OSError as exc:
                    print(f"Warning: could not kill {child.name} process group: {exc}", file=sys.stderr)
        for child in self.children:
            try:
                child.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    child.process.kill()
                    child.process.wait(timeout=5)
                except (OSError, subprocess.SubprocessError) as exc:
                    print(f"Warning: {child.name} may still be running (PID {child.process.pid}): {exc}", file=sys.stderr)
            finally:
                child.log.close()
        self.children.clear()


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--python", default=os.environ.get("ASTRA_PYTHON", str(default_python())), help="Python 3.12 environment executable (default: .venv)")
    result.add_argument("--model-port", type=port_number, default=8000)
    result.add_argument("--backend-port", type=port_number, default=3000)
    result.add_argument("--frontend-port", type=port_number, default=4200)
    result.add_argument("--db-file", type=Path, default=LOCAL / "history_db_v2.json", help="Persistent observation history; never cleared by the launcher")
    result.add_argument("--no-browser", action="store_true")
    result.add_argument("--seed-demo", action="store_true", help="Load synthetic DEMO_ history only if the ID has no records; never overwrite")
    result.add_argument("--demo-id", default="DEMO_SIM_001")
    result.add_argument("--startup-timeout", type=float, default=180, help="Seconds allowed per service readiness check")
    result.add_argument("--check", action="store_true", help="Check prerequisites and free ports, then exit without starting services")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if not 1 <= args.startup_timeout <= 600:
        raise LauncherError("--startup-timeout must be between 1 and 600 seconds.")
    ports = [args.model_port, args.backend_port, args.frontend_port]
    if len(set(ports)) != 3:
        raise LauncherError("Model, backend and frontend must use different ports.")
    node = checked_node()
    python = checked_python(args.python)
    model_path = AI / "artifacts" / "bundle.joblib"
    check_file(model_path, "trusted model artifact")
    tsx = BACKEND / "node_modules" / "tsx" / "dist" / "cli.mjs"
    angular = FRONTEND / "node_modules" / "@angular" / "cli" / "bin" / "ng.js"
    check_file(tsx, "backend dependencies")
    check_file(angular, "frontend dependencies")
    check_file(FRONTEND / "proxy.conf.cjs", "same-origin frontend proxy configuration")
    for port in ports:
        if not port_available(port):
            raise LauncherError(f"127.0.0.1:{port} is already in use. Stop your own previous server or choose another port; this launcher will not kill it.")
    if args.seed_demo:
        import re
        if not re.fullmatch(r"DEMO_[A-Za-z0-9_-]{1,48}", args.demo_id):
            raise LauncherError("--demo-id must start with DEMO_ and contain 1–48 letters, numbers, underscores or hyphens after it.")
    if args.check:
        print("Prerequisite files, Python/Node versions, and all three ports checked. No services started.")
        return 0

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + f"-{os.getpid()}"
    stack = Stack(LOCAL / "logs" / stamp)
    model_url = f"http://127.0.0.1:{args.model_port}"
    backend_url = f"http://127.0.0.1:{args.backend_port}"
    frontend_url = f"http://127.0.0.1:{args.frontend_port}"
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    env["ASTRA_MODEL_PATH"] = str(model_path)
    env["NG_CLI_ANALYTICS"] = "false"
    try:
        stack.launch("model", [python, "-m", "uvicorn", "astra_shield_ml.api:app", "--host", "127.0.0.1", "--port", str(args.model_port)], AI, env)
        stack.ready("Model", model_url + "/health", lambda x: x.get("status") == "ready" and x.get("data_origin") == "synthetic" and x.get("clinical_validation") is False, args.startup_timeout)
        backend_env = {**env, "AI_SERVICE_URL": model_url, "HOST": "127.0.0.1", "PORT": str(args.backend_port), "DB_FILE": str(args.db_file.expanduser().resolve())}
        stack.launch("backend", [node, str(tsx), "server.ts"], BACKEND, backend_env)
        stack.ready("Backend", backend_url + "/api/v1/health", lambda x: x.get("status") == "online" and x.get("ai_service", {}).get("model_ready") is True, args.startup_timeout)
        if args.seed_demo:
            history = json_get(backend_url + f"/api/v1/astronauts/{args.demo_id}/history")
            if history.get("total_assessments", 0) > 0 or history.get("history"):
                print(f"Synthetic demo seed skipped: {args.demo_id} already has history. Nothing overwritten.", flush=True)
            else:
                seed_env = {**env, "DEMO_BACKEND_URL": backend_url, "DEMO_ASTRONAUT_ID": args.demo_id}
                seeder = stack.launch("demo-seed", [node, "demo.mjs"], BACKEND, seed_env, required=False)
                deadline = time.monotonic() + 180
                next_progress = time.monotonic() + 10
                while seeder.process.poll() is None:
                    stack.require_running()
                    if time.monotonic() >= deadline:
                        raise LauncherError(f"Demo loader timed out. Review {seeder.log_path}; partial history is preserved.")
                    if time.monotonic() >= next_progress:
                        print("Loading synthetic calibration and forecast examples…", flush=True)
                        next_progress = time.monotonic() + 10
                    time.sleep(0.25)
                code = seeder.process.returncode
                if code != 0:
                    raise LauncherError(f"Demo loader failed. Review {seeder.log_path}; partial history is preserved.")
                print(f"Nine synthetic example records loaded for {args.demo_id}.", flush=True)
        frontend_env = {**env, "BACKEND_URL": backend_url}
        stack.launch("frontend", [node, str(angular), "serve", "--host", "127.0.0.1", "--port", str(args.frontend_port), "--proxy-config", "proxy.conf.cjs"], FRONTEND, frontend_env)
        stack.web_ready(frontend_url, args.startup_timeout)
        # Verify the browser's same-origin route traverses Angular -> backend -> model.
        stack.ready("Dashboard API proxy", frontend_url + "/api/v1/health", lambda x: x.get("ai_service", {}).get("model_ready") is True, args.startup_timeout)
        print(f"\nASTRA-SHIELD is running: {frontend_url}\nHistory: {args.db_file.expanduser().resolve()}\nLogs: {stack.log_directory}\nKeep this terminal open. Press Ctrl+C to stop all three services.\n", flush=True)
        if not args.no_browser:
            try:
                if not webbrowser.open(frontend_url):
                    print("Could not open a browser automatically; open the dashboard URL above.", flush=True)
            except webbrowser.Error:
                print("Could not open a browser automatically; open the dashboard URL above.", flush=True)
        while True:
            stack.require_running()
            time.sleep(0.5)
    finally:
        # A second Ctrl+C must not interrupt owned-process cleanup halfway through.
        previous = signal.signal(signal.SIGINT, signal.SIG_IGN)
        try:
            stack.stop()
        finally:
            signal.signal(signal.SIGINT, previous)


def interrupted(_signal: int, _frame: object) -> None:
    raise KeyboardInterrupt


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, interrupted)
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("ASTRA stopped. Saved observations have been preserved.", flush=True)
        raise SystemExit(0)
    except (LauncherError, OSError, subprocess.SubprocessError, ValueError) as exc:
        raise SystemExit(fail(exc))
