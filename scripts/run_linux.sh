#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
    echo "Create .venv and install -e '.[dev]' as described in README first." >&2
    exit 1
fi
exec "$ROOT/.venv/bin/python" -m denon_controller "$@"
