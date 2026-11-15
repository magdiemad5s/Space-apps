#!/usr/bin/env bash
set -euo pipefail
astra_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ -x "${astra_root}/.venv/bin/python" ]]; then
  exec "${astra_root}/.venv/bin/python" "${astra_root}/scripts/start.py" "$@"
elif command -v python3.12 >/dev/null 2>&1; then
  exec python3.12 "${astra_root}/scripts/start.py" "$@"
else
  printf '%s\n' 'Install Python 3.12, then run: python3.12 scripts/setup.py' >&2
  exit 1
fi
