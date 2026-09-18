#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PYTHON="$ROOT_DIR/.venv/bin/python"

if [[ ! -x "$VENV_PYTHON" ]]; then
	echo "Missing virtual environment at $ROOT_DIR/.venv"
	echo "Create it with: python3 -m venv .venv"
	exit 1
fi

cd "$ROOT_DIR"
exec "$VENV_PYTHON" -m scripts.run
