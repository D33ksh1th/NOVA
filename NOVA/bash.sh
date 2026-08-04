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

# Use certifi's CA bundle for outbound HTTPS (Google OAuth/token exchange).
# This avoids local trust-store mismatch issues on some macOS Python setups.
CERTIFI_CA="$($VENV_PYTHON -c 'import certifi; print(certifi.where())' 2>/dev/null || true)"
if [[ -n "$CERTIFI_CA" && -f "$CERTIFI_CA" ]]; then
	export SSL_CERT_FILE="$CERTIFI_CA"
	export REQUESTS_CA_BUNDLE="$CERTIFI_CA"
fi

exec "$VENV_PYTHON" -m scripts.run
