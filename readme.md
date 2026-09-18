# NOVA Workspace Setup

This workspace contains three main apps:

1. NOVA backend API and core services
2. nova-desktop frontend UI
3. nova-broadcast video generation pipeline

## Prerequisites

1. macOS or Linux
2. Python 3.12+
3. Node.js 18+
4. npm
5. Redis
6. Ollama

## Workspace Structure

1. NOVA
2. nova-desktop
3. nova-broadcast

## 1) Setup NOVA Backend

Run from workspace root:

```bash
cd NOVA
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Update `.env` with these minimum values:

```env
API_HOST=127.0.0.1
API_PORT=8000
REDIS_ENABLED=true
REDIS_URL=redis://127.0.0.1:6379/0
OLLAMA_HOST=http://127.0.0.1:11434
CHAT_MODEL=gemma4:12b
CODE_MODEL=gemma4:12b
REASONING_MODEL=gemma4:12b
```

## 2) Start Infrastructure Services

Start Redis:

```bash
redis-server --daemonize yes
```

Start Ollama:

```bash
ollama serve
```

In another terminal, pull required model:

```bash
ollama pull gemma4:12b
```

## 3) Start NOVA Backend

From workspace root:

```bash
cd NOVA
source .venv/bin/activate
python -m scripts.run
```

Alternative start command:

```bash
cd NOVA
./bash.sh
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

## 4) Setup and Start nova-desktop

From workspace root:

```bash
cd nova-desktop
npm install
npm run dev
```

## 5) Setup and Start nova-broadcast

From workspace root:

```bash
cd nova-broadcast
npm install
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Open Remotion studio:

```bash
cd nova-broadcast
npm run studio
```

Run full local broadcast pipeline:

```bash
cd nova-broadcast
npm run run -- --dry-run
```

## 6) Security Agent Remote Setup

On remote machine where security agent runs:

```bash
NOVA_SECURITY_PUSH_ENABLED=false NOVA_SECURITY_PULL_ENABLED=true NOVA_SECURITY_PULL_HOST=0.0.0.0 NOVA_SECURITY_PULL_PORT=3009 NOVA_SECURITY_PULL_TOKEN=demo-token python security_agent.py
```

Test remote agent endpoint:

```bash
curl -H "X-Nova-Agent-Token: demo-token" "http://10.20.40.144:3009/security/agent/snapshot"
```

Pull remote agent into NOVA backend:

```bash
curl -X POST "http://127.0.0.1:8000/security/agents/pull" -H "Content-Type: application/json" -d '{"agent_url":"http://10.20.40.144:3009","token":"demo-token","timeout":45,"verify_ssl":false}'
```

Verify ingestion:

```bash
curl http://127.0.0.1:8000/security/agents
curl http://127.0.0.1:8000/security/status
```

## 7) Redis Cache Verification

Check Redis is up:

```bash
redis-cli -u redis://127.0.0.1:6379/0 ping
```

Check cache keys:

```bash
redis-cli -u redis://127.0.0.1:6379/0 --scan --pattern 'nova:security:*' | sort
redis-cli -u redis://127.0.0.1:6379/0 --scan --pattern 'nova:gmail:*' | sort
```

## 8) Common API Endpoints

1. `GET /health`
2. `GET /security/status`
3. `GET /security/agents`
4. `POST /security/agents/pull`
5. `GET /gmail/status`
6. `GET /gmail/inbox?max_results=20`

Base URL:

```text
http://127.0.0.1:8000
```