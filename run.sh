#!/usr/bin/env bash
# Launch 495 from the repository root with a single command.
# Creates a local virtual environment on first use, installs the package, then runs the CLI.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$ROOT/.venv"
STAMP="$VENV/.four95-installed"

find_python() {
    for candidate in python3.13 python3.12 python3.11 python3; do
        if command -v "$candidate" >/dev/null 2>&1; then
            if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
                echo "$candidate"
                return 0
            fi
        fi
    done
    return 1
}

bootstrap() {
    if [ ! -x "$VENV/bin/python" ]; then
        if command -v uv >/dev/null 2>&1; then
            uv venv -q --python ">=3.11" "$VENV"
        else
            PY="$(find_python)" || { echo "495: Python >= 3.11 is required" >&2; exit 1; }
            "$PY" -m venv "$VENV"
        fi
    fi
    if [ ! -f "$STAMP" ] || [ "$ROOT/pyproject.toml" -nt "$STAMP" ]; then
        if command -v uv >/dev/null 2>&1; then
            uv pip install -q --python "$VENV/bin/python" -e "$ROOT[dev]"
        else
            "$VENV/bin/python" -m pip install -q --upgrade pip
            "$VENV/bin/python" -m pip install -q -e "$ROOT[dev]"
        fi
        touch "$STAMP"
    fi
}

bootstrap
exec "$VENV/bin/python" -m four95 "$@"
