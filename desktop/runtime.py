"""Local bundled ASTRA-SHIELD app: frozen model, Node backend, Angular browser UI.

This launcher never trains a model. Its smoke test uses fictional observations,
an isolated participant, and the shipped artifact, not the ML test partition.
"""
from __future__ import annotations

import argparse
from contextlib import asynccontextmanager
import ctypes
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import uuid
import webbrowser

LOOPBACK = "127.0.0.1"
HOP_HEADERS = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
               "te", "trailer", "transfer-encoding", "upgrade", "host", "content-length"}
MAX_BODY_BYTES = 100 * 1024


def resource_directory(override: str | None = None) -> Path:
    if override:
        return Path(override).expanduser().resolve()
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / "resources"


def default_data_directory() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "ASTRA-SHIELD"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "astra-shield"


def validate_resources(root: Path) -> None:
    required = ["frontend/index.html", "backend/server.js", "backend/package.json",
                "model/bundle.joblib", "fixtures/synthetic_daily_sequence.json",
                "node/node.exe" if os.name == "nt" else "node/node"]
    missing = [str(root / name) for name in required if not (root / name).is_file()]
    if missing:
        raise RuntimeError("Bundled resources are missing: " + ", ".join(missing))
    if json.loads((root / "backend/package.json").read_text(encoding="utf-8")).get("type") != "module":
        raise RuntimeError("Bundled Node backend requires package.json type=module.")


def listening_socket(port: int = 0, fallback: bool = False) -> socket.socket:
    """Reserve the actual socket used by uvicorn; do not probe and then rebind."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if os.name == "nt":
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    try:
        try:
            sock.bind((LOOPBACK, port))
        except OSError:
            if not fallback or port == 0:
                raise
            sock.bind((LOOPBACK, 0))
        sock.listen(128)
        return sock
    except BaseException:
        sock.close()
        raise


class DataDirectoryLock:
    """One backend writer per history directory; OS releases locks on crashes."""
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        self.file = (directory / ".runtime.lock").open("a+b")
        self.file.seek(0, os.SEEK_END)
        if self.file.tell() == 0:
            self.file.write(b"0")
            self.file.flush()
        self.file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self.file.close()
            raise RuntimeError("ASTRA-SHIELD is already using this data directory. Close the other launcher first: " + str(directory)) from error

    def close(self):
        if not self.file.closed:
            if os.name == "nt":
                import msvcrt
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
            self.file.close()


class WindowsJob:
    """Close a Windows Job handle to terminate Node and any descendants.

    Windows closes this non-inheritable handle even if the console window is
    closed or the launcher is forcibly terminated. Python threads need no job.
    """
    def __init__(self):
        from ctypes import wintypes

        class BASIC(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                        ("SchedulingClass", wintypes.DWORD)]

        class IO(ctypes.Structure):
            _fields_ = [(name, ctypes.c_ulonglong) for name in
                        ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                         "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

        class EXTENDED(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", BASIC), ("IoInfo", IO),
                        ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.kernel.CreateJobObjectW.restype = wintypes.HANDLE
        self.kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        self.kernel.SetInformationJobObject.restype = wintypes.BOOL
        self.kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.kernel.AssignProcessToJobObject.restype = wintypes.BOOL
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.CloseHandle.restype = wintypes.BOOL
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = EXTENDED()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            code = ctypes.get_last_error()
            self.close()
            raise ctypes.WinError(code)

    def assign(self, process: subprocess.Popen) -> None:
        if not self.kernel.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


class BackendProcess:
    def __init__(self, command: list[str], cwd: Path, env: dict[str, str], log_path: Path):
        self.job = WindowsJob() if os.name == "nt" else None
        self.log = log_path.open("ab", buffering=0)
        self.process = None
        try:
            options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
            self.process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                            stdout=self.log, stderr=subprocess.STDOUT, **options)
            if self.job:
                self.job.assign(self.process)
        except BaseException:
            self.close()
            raise

    def close(self):
        process = self.process
        if self.job:
            self.job.close()
        if process is not None:
            if os.name == "posix":
                # The process group may still exist after its leader has exited.
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            elif process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                if os.name == "posix":
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                else:
                    process.kill()
                process.wait(timeout=5)
            # Reap descendants that did not handle TERM, even if Node exited.
            if os.name == "posix":
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        self.log.close()


class ServerThread:
    def __init__(self, app, sock: socket.socket, name: str):
        import uvicorn
        self.socket = sock
        self.server = uvicorn.Server(uvicorn.Config(app, host=LOOPBACK, port=sock.getsockname()[1],
                                                   log_level="warning", access_log=False, loop="asyncio",
                                                   http="h11", lifespan="on", timeout_graceful_shutdown=5))
        self.error = None

        def run():
            try:
                self.server.run(sockets=[sock])
            except BaseException as error:
                self.error = error

        self.thread = threading.Thread(target=run, name=name, daemon=True)
        self.thread.start()

    def close(self):
        self.server.should_exit = True
        self.thread.join(timeout=8)
        self.socket.close()


def make_web_app(frontend: Path, backend_url: str):
    """Production static host and local reverse proxy; no Angular dev server."""
    import httpx
    from fastapi import FastAPI, Request
    from starlette.responses import FileResponse, JSONResponse, Response

    @asynccontextmanager
    async def lifespan(app):
        async with httpx.AsyncClient(base_url=backend_url, trust_env=False, timeout=90, follow_redirects=False) as client:
            app.state.backend = client
            yield

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    async def proxy(request: Request):
        chunks = []
        total = 0
        async for chunk in request.stream():
            total += len(chunk)
            if total > MAX_BODY_BYTES:
                return JSONResponse({"error": "Request exceeds the 100 KiB limit."}, status_code=413)
            chunks.append(chunk)
        headers = {key: value for key, value in request.headers.items() if key.lower() not in HOP_HEADERS}
        # Prevent httpx's decompression from invalidating response encodings.
        headers["accept-encoding"] = "identity"
        path = request.url.path + ("?" + request.url.query if request.url.query else "")
        try:
            response = await request.app.state.backend.request(request.method, path, headers=headers, content=b"".join(chunks))
        except httpx.RequestError:
            return JSONResponse({"error": "Local backend is unavailable. Restart ASTRA-SHIELD; no prediction was invented."}, status_code=503)
        outgoing = {key: value for key, value in response.headers.items()
                    if key.lower() not in HOP_HEADERS | {"content-encoding"}}
        return Response(response.content, status_code=response.status_code, headers=outgoing)

    # Register with an explicit annotation: future annotations cannot resolve
    # locally imported Request in FastAPI's annotation inspection.
    proxy.__annotations__["request"] = Request
    methods = ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    app.add_api_route("/api/{path:path}", proxy, methods=methods)

    @app.api_route("/{path:path}", methods=["GET", "HEAD"])
    def static_file(path: str):
        target = (frontend / path).resolve()
        if not target.is_relative_to(frontend.resolve()):
            return Response(status_code=404)
        if target.is_file():
            return FileResponse(target, headers={"Cache-Control": "no-cache"} if target.name == "index.html" else {})
        if Path(path).suffix:
            return Response(status_code=404)
        return FileResponse(frontend / "index.html", headers={"Cache-Control": "no-cache"})

    return app


def wait_json(client, url: str, predicate, timeout: float, alive, stopping: threading.Event, request_timeout: float = 5):
    end = time.monotonic() + timeout
    detail = "not listening"
    while time.monotonic() < end:
        if stopping.is_set():
            raise InterruptedError("Startup interrupted.")
        if not alive():
            raise RuntimeError("A local service stopped during startup: " + url)
        try:
            response = client.get(url, timeout=min(request_timeout, max(0.1, end - time.monotonic())))
            body = response.json()
            if response.status_code == 200 and predicate(body):
                return body
            detail = str(body)
        except Exception as error:
            detail = str(error)
        stopping.wait(0.2)
    raise RuntimeError(f"Service readiness timed out ({url}): {detail}")


class Runtime:
    def __init__(self, resources: Path, data_dir: Path, port: int | None = None):
        self.resources = resources
        self.data_dir = data_dir
        self.port = port
        self.model = self.web = self.backend = None
        self.data_lock = None
        self.stopping = threading.Event()
        self.url = ""
        self.log_dir = data_dir / "logs" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + str(os.getpid()))

    def start(self):
        import httpx
        validate_resources(self.resources)
        self.data_lock = DataDirectoryLock(self.data_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        os.environ["ASTRA_MODEL_PATH"] = str(self.resources / "model/bundle.joblib")
        os.environ.setdefault("MPLCONFIGDIR", str(self.data_dir / "cache/matplotlib"))
        os.environ.setdefault("NUMBA_CACHE_DIR", str(self.data_dir / "cache/numba"))
        if not getattr(sys, "frozen", False):
            sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ai"))
        from astra_shield_ml.api import app as model_app, get_service
        get_service.cache_clear()
        model_socket = listening_socket()
        model_url = f"http://{LOOPBACK}:{model_socket.getsockname()[1]}"
        self.model = ServerThread(model_app, model_socket, "astra-model")
        with httpx.Client(trust_env=False) as client:
            wait_json(client, model_url + "/health", lambda body: body.get("status") == "ready" and body.get("tasks_loaded") == 5,
                      180, lambda: self.model.thread.is_alive(), self.stopping, request_timeout=120)
            # Node owns its listening socket; reject startup failure rather than
            # silently connecting to an unrelated process if this port is taken.
            probe = listening_socket()
            backend_port = probe.getsockname()[1]
            probe.close()
            backend_url = f"http://{LOOPBACK}:{backend_port}"
            env = os.environ.copy()
            for key in ("NODE_OPTIONS", "NODE_PATH"):
                env.pop(key, None)
            env.update(HOST=LOOPBACK, PORT=str(backend_port), AI_SERVICE_URL=model_url,
                       DB_FILE=str(self.data_dir / "history_db_v2.json"))
            node = self.resources / "node" / ("node.exe" if os.name == "nt" else "node")
            self.backend = BackendProcess([str(node), str(self.resources / "backend/server.js")],
                                          self.resources / "backend", env, self.log_dir / "backend.log")
            backend_ready = lambda body: body.get("ai_service", {}).get("model_ready") is True
            wait_json(client, backend_url + "/api/v1/health", backend_ready, 30,
                      lambda: self.backend.process.poll() is None, self.stopping)
            web_socket = listening_socket(4173 if self.port is None else self.port, fallback=self.port is None)
            self.url = f"http://{LOOPBACK}:{web_socket.getsockname()[1]}"
            self.web = ServerThread(make_web_app(self.resources / "frontend", backend_url), web_socket, "astra-web")
            wait_json(client, self.url + "/api/v1/health", backend_ready, 20,
                      lambda: self.web.thread.is_alive() and self.backend.process.poll() is None, self.stopping)
        (self.log_dir / "runtime.json").write_text(json.dumps({"url": self.url, "pid": os.getpid(),
            "backend_pid": self.backend.process.pid, "data_directory": str(self.data_dir),
            "model_artifact_sha256": hashlib.sha256((self.resources / "model/bundle.joblib").read_bytes()).hexdigest()}, indent=2), encoding="utf-8")
        print("ASTRA-SHIELD is ready: " + self.url, flush=True)
        print("History: " + str(self.data_dir / "history_db_v2.json"), flush=True)
        print("Logs: " + str(self.log_dir), flush=True)
        print("Synthetic research prototype. Keep this console open; Ctrl+C stops the app.", flush=True)

    def close(self):
        self.stopping.set()
        clean = True
        for service in (self.web, self.backend, self.model):
            if service:
                try:
                    service.close()
                except Exception as error:
                    clean = False
                    print("Shutdown error: " + str(error), file=sys.stderr)
        clean = clean and all(not service.thread.is_alive() for service in (self.web, self.model) if service)
        clean = clean and (self.backend is None or self.backend.process is None or self.backend.process.poll() is not None)
        if self.data_lock:
            self.data_lock.close()
        return clean

    def run_until_stopped(self):
        while not self.stopping.wait(0.5):
            if not self.web.thread.is_alive() or not self.model.thread.is_alive() or self.backend.process.poll() is not None:
                raise RuntimeError("A local service exited. Restart the app; see logs in " + str(self.log_dir))


def seed_demo(runtime: Runtime):
    import httpx
    records = json.loads((runtime.resources / "fixtures/synthetic_daily_sequence.json").read_text(encoding="utf-8"))
    identifier = "DEMO_SIM_001"
    with httpx.Client(base_url=runtime.url, trust_env=False, timeout=90) as client:
        response = client.get(f"/api/v1/astronauts/{identifier}/history")
        response.raise_for_status()
        if response.json().get("observations"):
            print("Existing DEMO_SIM_001 history preserved; synthetic seeding skipped.", flush=True)
            return
        print("Adding fictional demonstration observations for DEMO_SIM_001 only.", flush=True)
        for record in records:
            response = client.post("/api/v1/assess", json={**record, "astronaut_id": identifier})
            if response.status_code not in (201, 202):
                raise RuntimeError(f"Synthetic seeding stopped (HTTP {response.status_code}); existing observations were preserved.")


def smoke_test(runtime: Runtime) -> dict:
    """Verify packaged inference, actual SHAP and proxy behavior, not accuracy."""
    import httpx
    checks = []

    def check(name, passed):
        checks.append({"name": name, "passed": bool(passed)})
        if not passed:
            raise AssertionError(name)

    records = json.loads((runtime.resources / "fixtures/synthetic_daily_sequence.json").read_text(encoding="utf-8"))
    identifier = "DEMO_PACKAGING_" + uuid.uuid4().hex[:12]
    with httpx.Client(base_url=runtime.url, trust_env=False, timeout=90) as client:
        index = client.get("/")
        check("compiled Angular index served", index.status_code == 200 and "<app-root" in index.text)
        check("SPA route serves index", client.get("/dashboard").text == index.text)
        check("missing asset is 404", client.get("/missing-smoke-test.js").status_code == 404)
        check("unknown API is not frontend HTML", client.get("/api/v1/no-such-route").status_code == 404)
        for day, record in enumerate(records[:8], start=1):
            response = client.post("/api/v1/assess", json={**record, "astronaut_id": identifier})
            body = response.json()
            if day <= 7:
                check(f"day {day} calibration preserves 202 and null forecast",
                      response.status_code == 202 and body.get("model_result") is None and body.get("fatigue_points") is None)
            else:
                check("day 8 actual model forecast", response.status_code == 201 and body.get("inference_source") == "synthetic_model")
                model = body["model_result"]
                shap = model["explanation"]["tree_shap"]
                check("actual TreeSHAP three reasons", shap["method"] == "TreeSHAP" and len(shap["top_three_reasons"]) == 3
                      and all(math.isfinite(reason["shap_value"]) for reason in shap["top_three_reasons"]))
                probabilities = model["next_day_forecasts"]["fatigue"]["model_class_probabilities"]
                check("TreeSHAP reconstructs predicted class probability",
                      abs(shap["reconstructed_model_output"] - probabilities[model["label"]]) < 1e-5)
                check("synthetic scope retained", model["clinical_validation"] is False and model["data_origin"] == "synthetic_training_data")
                forecast = {"label": model["label"], "points": model["points"], "shap_method": shap["method"]}
        duplicate = client.post("/api/v1/assess", json={**records[7], "astronaut_id": identifier})
        check("duplicate status preserved", duplicate.status_code == 409)
        invalid = client.post("/api/v1/assess", json={"astronaut_id": identifier})
        check("validation status preserved", invalid.status_code == 422)
        history = client.get(f"/api/v1/astronauts/{identifier}/history").json()
        check("eight observations persisted with no duplicates", len(history["observations"]) == 8)
    return {"passed": True, "platform": sys.platform, "frozen": bool(getattr(sys, "frozen", False)),
            "scope": "Packaging and local inference integration; not model accuracy or clinical validation",
            "model_artifact_sha256": hashlib.sha256((runtime.resources / "model/bundle.joblib").read_bytes()).hexdigest(),
            "forecast": forecast, "checks": checks}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resources", help="Override bundled resource directory for development/testing")
    parser.add_argument("--data-dir", help="Persistent history/log directory; never the install directory by default")
    parser.add_argument("--port", type=int, help="Exact browser port, or 0 for automatic. Default prefers 4173 then a free port")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--seed-demo", action="store_true", help="Seed fictional DEMO_SIM_001 only when its history is empty")
    parser.add_argument("--smoke-test", action="store_true", help="Run real packaged inference checks, then stop")
    parser.add_argument("--report", help="Write smoke-test JSON report")
    args = parser.parse_args(argv)
    if args.port is not None and not 0 <= args.port <= 65535:
        parser.error("--port must be 0..65535")
    if args.report and not args.smoke_test:
        parser.error("--report requires --smoke-test")
    temporary = tempfile.TemporaryDirectory(prefix="astra-bundle-smoke-") if args.smoke_test and not args.data_dir else None
    data_dir = Path(args.data_dir or (temporary.name if temporary else default_data_directory())).expanduser().resolve()
    runtime = Runtime(resource_directory(args.resources), data_dir, args.port)
    old_signals = {}
    for signum in (signal.SIGINT, signal.SIGTERM):
        old_signals[signum] = signal.signal(signum, lambda *_: runtime.stopping.set())
    result = {"passed": False, "platform": sys.platform, "frozen": bool(getattr(sys, "frozen", False))}
    exit_code = 0
    try:
        runtime.start()
        if args.smoke_test:
            result = smoke_test(runtime)
            print(json.dumps(result, indent=2), flush=True)
        else:
            if args.seed_demo:
                seed_demo(runtime)
            if not args.no_browser:
                webbrowser.open(runtime.url)
            runtime.run_until_stopped()
    except (KeyboardInterrupt, InterruptedError):
        exit_code = 130
    except Exception as error:
        exit_code = 1
        result["error"] = str(error)
        print("ASTRA-SHIELD could not complete: " + str(error), file=sys.stderr, flush=True)
        if runtime.log_dir.is_dir():
            (runtime.log_dir / "error.log").write_text(traceback.format_exc(), encoding="utf-8")
    finally:
        clean = runtime.close()
        if args.smoke_test:
            result.setdefault("checks", []).append({"name": "local services stopped cleanly", "passed": clean})
        if not clean:
            result["passed"] = False
            result["shutdown_error"] = "A local service did not stop cleanly."
            exit_code = 1
        for signum, handler in old_signals.items():
            signal.signal(signum, handler)
        if args.report:
            report = Path(args.report).expanduser().resolve()
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        if temporary:
            temporary.cleanup()
    if exit_code and getattr(sys, "frozen", False) and not args.smoke_test and sys.stdin and sys.stdin.isatty():
        try:
            input("Press Enter to close this window. The error and log location are shown above.")
        except (EOFError, KeyboardInterrupt):
            pass
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
