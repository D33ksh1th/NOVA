from __future__ import annotations

import importlib.util
import threading
import sys
from pathlib import Path

import requests


def _load_agent_module(module_name: str, env: dict[str, str]):
    import os

    for key, value in env.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value

    agent_path = Path(__file__).resolve().parents[1] / "scripts" / "security_agent.py"
    spec = importlib.util.spec_from_file_location(module_name, agent_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_pull_snapshot_returns_401_without_token():
    agent = _load_agent_module(
        "security_agent_test_unauth",
        {
            "NOVA_SECURITY_PULL_TOKEN": "",
            "NOVA_SECURITY_SIGNING_PRIVATE_KEY_PATH": "",
            "NOVA_SECURITY_DISCOVERY": "false",
        },
    )

    server = agent.ThreadingHTTPServer(("127.0.0.1", 0), agent._SnapshotHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        resp = requests.get(f"http://{host}:{port}/security/agent/snapshot", timeout=5)
        assert resp.status_code == 401
    finally:
        server.shutdown()
        server.server_close()


def test_pull_server_refuses_wildcard_bind_without_token():
    agent = _load_agent_module(
        "security_agent_test_bind_refusal",
        {
            "NOVA_SECURITY_PULL_HOST": "0.0.0.0",
            "NOVA_SECURITY_PULL_TOKEN": "",
            "NOVA_SECURITY_PULL_TLS_CERT_FILE": "",
            "NOVA_SECURITY_DISCOVERY": "false",
        },
    )

    try:
        agent._validate_pull_server_config()
        raise AssertionError("expected _validate_pull_server_config to fail")
    except RuntimeError as exc:
        assert "token is required" in str(exc)
