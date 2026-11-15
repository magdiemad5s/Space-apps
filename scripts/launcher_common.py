"""Shared, standard-library-only helpers for the local ASTRA launchers."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
AI = ROOT / "ai"
BACKEND = AI / "integration" / "backend_review" / "proposed_backend"
FRONTEND = ROOT / "frontend"
LOCAL = ROOT / ".local"


class LauncherError(RuntimeError):
    pass


def default_python() -> Path:
    return ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def find_executable(name: str) -> str:
    executable = shutil.which(name)
    if not executable:
        raise LauncherError(f"{name} was not found on PATH. Install the prerequisites in README.md first.")
    return executable


def output(command: list[str]) -> str:
    try:
        return subprocess.check_output(command, text=True, stderr=subprocess.STDOUT, timeout=30).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise LauncherError(f"Could not run {command[0]}: {exc}") from exc


def node_supported(version: str) -> bool:
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", version.strip())
    if not match:
        return False
    major, minor, patch = map(int, match.groups())
    return ((major == 22 and (minor, patch) >= (22, 3))
            or (major == 24 and (minor, patch) >= (15, 0)) or major >= 26)


def checked_node() -> str:
    node = find_executable("node")
    version = output([node, "--version"])
    if not node_supported(version):
        raise LauncherError(f"Node {version} is unsupported by Angular 22. Use Node 22.22.3+, 24.15+, or 26+ (24 LTS recommended).")
    return node


def checked_python(value: str | Path) -> str:
    path = Path(value).expanduser()
    # A bare command such as python3.12 may be passed explicitly.
    # Resolving a venv's python symlink would run the base interpreter and lose
    # the venv's site-packages. Preserve its path, including on POSIX.
    executable = str(path.absolute()) if path.is_file() else shutil.which(str(value))
    if not executable:
        raise LauncherError(f"Python environment not found: {value}. Run Setup-Astra.cmd or python3.12 scripts/setup.py first.")
    version = output([executable, "-c", "import sys; print('.'.join(map(str, sys.version_info[:3])))"])
    if tuple(version.split(".")[:2]) != ("3", "12"):
        raise LauncherError(f"Python {version} is unsupported by this tested launcher. Use Python 3.12 and the pinned ai/requirements.txt.")
    return executable


def npm_command(node: str) -> list[str]:
    """Use npm's JS entry point, including on Windows; never interpolate a shell command."""
    npm = Path(find_executable("npm"))
    resolved = npm.resolve()
    candidates = [
        resolved,
        npm.parent / "node_modules/npm/bin/npm-cli.js",
        Path(node).parent / "node_modules/npm/bin/npm-cli.js",
        npm.parent.parent / "lib/node_modules/npm/bin/npm-cli.js",
    ]
    for candidate in candidates:
        if candidate.is_file() and candidate.name == "npm-cli.js":
            return [node, str(candidate)]
    raise LauncherError("Cannot locate npm-cli.js. Reinstall the standard Node.js distribution (which includes npm), or install dependencies manually with npm ci in frontend and the backend folder.")


def check_file(path: Path, description: str) -> None:
    if not path.is_file():
        raise LauncherError(f"Missing {description}: {path}. Run the setup script first.")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def fail(exc: Exception) -> int:
    print(f"\nASTRA startup error: {exc}", file=sys.stderr, flush=True)
    return 1
