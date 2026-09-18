# NOVA Security Center

NOVA Security Center is the path from utility scanners to a personal AI SOC analyst.

## Mission

NOVA should move from user-driven scans to continuous security awareness:

- Notice suspicious activity without waiting for a prompt
- Correlate host, browser, network, and identity signals
- Explain what happened in plain English
- Offer guided response actions instead of raw alerts

## Delivery Phases

### Phase 1 — Foundation + Host Telemetry

Goal: create the central Security Center service and the first endpoint-monitoring pipeline.

Scope:

- Security Center engine
- Collector registry
- Timeline store
- Risk scoring
- Host monitor collector contracts
- Security API endpoints

Planned host signals:

- Running processes
- Parent-child tree
- CPU and memory spikes
- Listening ports
- Network connections
- LaunchAgents and persistence
- Mounted drives and USB insertion
- Login/session events

Outcome:

NOVA gains a single place to ingest, score, and explain local host telemetry.

### Phase 2 — Browser Guardian + Prompt Security

Goal: protect browsing and AI tool usage.

Scope:

- URL and lookalike-domain checks
- Redirect-chain and certificate analysis
- Download reputation hooks
- Login form detection
- Prompt injection and jailbreak pattern detection
- Clipboard and extension-risk visibility where available

Outcome:

NOVA can say why a page or prompt looks dangerous before damage happens.

### Phase 3 — Network SOC + Identity Guardian

Goal: add network and identity context for stronger correlation.

Scope:

- DNS / HTTP / HTTPS / SSH / SMB / FTP visibility
- Beaconing, tunneling, scanning, and exfil indicators
- New outbound destinations and country anomalies
- Login anomalies, credential changes, MFA state, session abuse

Outcome:

NOVA sees the machine as part of a live environment, not just a local endpoint.

### Phase 4 — AI Correlation + Response

Goal: deliver Jarvis-style investigation and guided response.

Scope:

- Multi-signal threat correlation
- Natural-language investigation summaries
- Continuous risk score
- Incident timeline view
- Response hooks: kill process, remove persistence, quarantine, investigate
- Threat hunting queries over stored telemetry

Outcome:

NOVA behaves like a personal SOC analyst, not a passive antivirus.

## Target Service Layout

```text
services/security/
├── collectors/
├── detectors/
├── analyzers/
├── responders/
├── browser/
├── network/
├── endpoint/
├── prompts/
├── threat_intel/
├── timeline/
└── risk_engine/
```

## Phase 1 Implementation Status

Implemented in this repo now:

- `services/security/engine.py`
- `services/security/collectors/*`
- `services/security/risk_engine.py`
- `services/security/timeline.py`
- `GET /security/status`
- `GET /security/findings`
- `GET /security/timeline`

This is the platform layer. The next step is adding real macOS host collectors behind it.

## Remote Agent Strategy

For endpoint visibility, prefer a native security agent over Docker.

Why:

- Docker containers do not see host processes and persistence reliably enough for EDR-style use cases.
- macOS LaunchAgents, user sessions, mounted drives, shell behavior, and login events are better observed from a host-native daemon.
- A lightweight Python agent can be packaged later for macOS, Linux, and Windows while reusing the same ingest contract.

Current approach:

- Agent script: `scripts/security_agent.py`
- Heartbeat endpoint: `POST /security/agents/heartbeat`
- Agent inventory: `GET /security/agents`

Recommended deployment now:

1. Run NOVA centrally on one controller machine.
2. Run `scripts/security_agent.py` on the monitored endpoint using a Python venv.
3. Set:
	- `NOVA_SECURITY_URL=http://<nova-host>:8000`
	- `NOVA_SECURITY_TOKEN=<shared-token>`
	- `NOVA_SECURITY_INTERVAL=60`
4. Later, wrap the same script as:
	- macOS LaunchAgent
	- Linux systemd service
	- Windows service

Docker still makes sense later for server workloads, but not as the primary endpoint sensor.

### Ubuntu / Linux support

The current native agent can run on Ubuntu now.

On Ubuntu it collects:

- top processes
- CPU and memory load
- listening ports
- mounted drives
- login snapshot (`who`)
- connection summary
- persistence artifacts via:
	- `/etc/systemd/system`
	- `/lib/systemd/system`
	- `~/.config/systemd/user`
	- cron paths under `/etc/cron.d`, `/etc/crontab`, and spool locations

That makes Ubuntu a better first monitored host than a Docker container if you want meaningful security telemetry.

### Ubuntu deployment now

Quick manual run:

```bash
cd NOVA
python3 -m venv .venv
source .venv/bin/activate
pip install psutil requests

export NOVA_SECURITY_URL=http://<nova-controller>:8000
export NOVA_SECURITY_TOKEN=<shared-token-if-set>
export NOVA_SECURITY_AGENT_ID=$(hostname)
export NOVA_SECURITY_INTERVAL=60

python scripts/security_agent.py
```

Standalone host discovery test:

```bash
python scripts/discover_hosts.py
```

Persistent service install on Ubuntu:

```bash
bash scripts/install_security_agent_service.sh
sudo systemctl start nova-security-agent.service
sudo systemctl status nova-security-agent.service
```

## How to test connectivity in NOVA

1. Start NOVA backend on the controller.
2. Set `SECURITY_AGENT_SHARED_TOKEN` in NOVA `.env` if you want agent auth.
3. Run the Ubuntu agent with `NOVA_SECURITY_URL` pointing to the NOVA controller.
4. Verify from NOVA:

```bash
curl http://127.0.0.1:8000/security/agents
curl http://127.0.0.1:8000/security/findings
curl http://127.0.0.1:8000/security/timeline
```

5. In the NOVA desktop app, open the Security tab to see:

- host risk score
- remote agent inventory
- package update backlog
- subnet host discovery map
- findings and timeline
