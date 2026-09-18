#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE_NAME="nova-security-agent.service"
UNIT_PATH="/etc/systemd/system/${SERVICE_NAME}"
PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
AGENT_SCRIPT="${ROOT_DIR}/scripts/security_agent.py"
ENV_FILE="${ROOT_DIR}/configs/security-agent.env"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Missing venv python at $PYTHON_BIN"
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  cat > "$ENV_FILE" <<'EOF'
NOVA_SECURITY_URL=http://127.0.0.1:8000
NOVA_SECURITY_TOKEN=
NOVA_SECURITY_AGENT_ID=
NOVA_SECURITY_INTERVAL=60
NOVA_SECURITY_TIMEOUT=15
NOVA_SECURITY_PUSH_ENABLED=true
NOVA_SECURITY_PULL_ENABLED=false
NOVA_SECURITY_PULL_HOST=0.0.0.0
NOVA_SECURITY_PULL_PORT=8765
NOVA_SECURITY_PULL_TOKEN=
NOVA_SECURITY_SNAPSHOT_CACHE_SECONDS=10
NOVA_SECURITY_DISCOVERY=true
NOVA_SECURITY_DISCOVERY_INTERVAL=300
NOVA_SECURITY_DISCOVERY_TIMEOUT=0.2
NOVA_SECURITY_DISCOVERY_MAX_HOSTS=256
EOF
  echo "Created $ENV_FILE. Edit it before starting the service."
fi

sudo tee "$UNIT_PATH" >/dev/null <<EOF
[Unit]
Description=NOVA Security Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
EnvironmentFile=$ENV_FILE
WorkingDirectory=$ROOT_DIR
ExecStart=$PYTHON_BIN $AGENT_SCRIPT
Restart=always
RestartSec=10
User=$(id -un)
Group=$(id -gn)

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"

echo "Installed $SERVICE_NAME"
echo "Next: edit $ENV_FILE, then run: sudo systemctl start $SERVICE_NAME"
