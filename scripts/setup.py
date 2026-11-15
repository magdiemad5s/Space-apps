#!/usr/bin/env python3
"""Install the pinned local demo dependencies. Run using Python 3.12."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

from launcher_common import (ROOT, AI, BACKEND, FRONTEND, LOCAL, LauncherError,
                             checked_node, checked_python, default_python, npm_command, fail)


def run(command: list[str], cwd: Path) -> None:
    print(f"\n[{cwd.relative_to(ROOT) or '.'}] {Path(command[0]).name} {' '.join(command[1:])}", flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def main() -> int:
    if sys.version_info[:2] != (3, 12):
        raise LauncherError("Run setup with Python 3.12: py -3.12 scripts/setup.py (Windows) or python3.12 scripts/setup.py (Linux).")
    node = checked_node()
    npm = npm_command(node)
    for project in (FRONTEND, BACKEND):
        if not (project / "package-lock.json").is_file():
            raise LauncherError(f"Missing package-lock.json in {project}; restore the complete project before setup.")
    environment = ROOT / ".venv"
    python = default_python()
    if environment.exists() and not python.is_file():
        raise LauncherError(f"{environment} already exists but is not a usable environment for this OS. Preserve/remove it manually before setup.")
    if not environment.exists():
        run([sys.executable, "-m", "venv", str(environment)], ROOT)
    checked_python(python)
    run([str(python), "-m", "pip", "install", "--upgrade", "pip"], ROOT)
    run([str(python), "-m", "pip", "install", "-r", str(AI / "requirements.txt")], ROOT)
    for project in (BACKEND, FRONTEND):
        run([*npm, "ci", "--no-audit", "--no-fund"], project)
    LOCAL.mkdir(exist_ok=True)
    stamp = {"completed_at_utc": datetime.now(timezone.utc).isoformat(),
             "python": str(python), "node": node,
             "inputs_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in (AI / "requirements.txt", BACKEND / "package-lock.json", FRONTEND / "package-lock.json")}}
    (LOCAL / "setup.json").write_text(json.dumps(stamp, indent=2) + "\n", encoding="utf-8")
    print("\nSetup complete. Run Start-Astra.cmd (Windows) or ./start.sh (Linux/macOS).", flush=True)
    print("Use --seed-demo on the launcher to load explicitly synthetic example history; existing history is preserved.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nSetup interrupted. You can run it again; recorded history has not been deleted.", file=sys.stderr)
        raise SystemExit(130)
    except (LauncherError, OSError, subprocess.SubprocessError) as exc:
        raise SystemExit(fail(exc))
