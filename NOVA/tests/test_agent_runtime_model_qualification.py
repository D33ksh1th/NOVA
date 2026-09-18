import asyncio

import httpx

from services.agent_runtime.models.qualify import qualify
from test_agent_runtime_model import Tokenizer, response_data


def server(calls, *, installed=True, remote=False, changed=False):
    inventories = 0

    def respond(request):
        nonlocal inventories
        calls.append(request.url.path)
        if request.url.path == "/api/tags":
            inventories += 1
            return httpx.Response(200, json={"models": [{"name": "local:test", "digest":
                ("b" if changed and inventories > 1 else "a") * 64}] if installed else []})
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"capabilities": ["completion"], "remote_host": "remote" if remote else ""})
        if request.url.path == "/api/generate":
            return httpx.Response(200, json=response_data(response='{"ok":true}'))
        raise AssertionError("Unexpected endpoint")

    return httpx.MockTransport(respond)


def test_missing_tokenizer_blocks_inference(tmp_path):
    calls = []
    report = asyncio.run(qualify(model="local:test", tokenizer_path=tmp_path / "missing", probe=True,
                                 transport=server(calls)))
    assert report.status == "BLOCKED" and report.reason == "TOKENIZER_DIRECTORY_REQUIRED"
    assert "/api/generate" not in calls


def test_preflight_does_not_claim_probe_success(tmp_path, monkeypatch):
    monkeypatch.setattr("services.agent_runtime.models.qualify.load_local_tokenizer", lambda path: Tokenizer())
    calls = []
    report = asyncio.run(qualify(model="local:test", tokenizer_path=tmp_path, transport=server(calls)))
    assert report.status == "PREFLIGHT_ONLY"
    assert "/api/generate" not in calls


def test_bounded_probes_verify_stable_digest(tmp_path, monkeypatch):
    monkeypatch.setattr("services.agent_runtime.models.qualify.load_local_tokenizer", lambda path: Tokenizer())
    calls = []
    report = asyncio.run(qualify(model="local:test", tokenizer_path=tmp_path, probe=True,
                                 expected_digest="a" * 64, transport=server(calls)))
    assert report.status == "PROBES_PASSED" and report.probe_tokens == [13, 13]
    assert calls.count("/api/generate") == 2 and calls.count("/api/tags") == 2


def test_model_change_fails_qualification(tmp_path, monkeypatch):
    monkeypatch.setattr("services.agent_runtime.models.qualify.load_local_tokenizer", lambda path: Tokenizer())
    report = asyncio.run(qualify(model="local:test", tokenizer_path=tmp_path, probe=True,
                                 transport=server([], changed=True)))
    assert report.status == "BLOCKED" and report.reason == "MODEL_CHANGED_DURING_PROBE"


def test_remote_model_fails_before_tokenizer_or_generation(tmp_path):
    calls = []
    report = asyncio.run(qualify(model="local:test", tokenizer_path=tmp_path, probe=True,
                                 transport=server(calls, remote=True)))
    assert report.reason == "REMOTE_MODEL_REJECTED"
    assert "/api/generate" not in calls


def test_digest_mismatch_fails_before_generation(tmp_path):
    calls = []
    report = asyncio.run(qualify(model="local:test", tokenizer_path=tmp_path, probe=True,
                                 expected_digest="b" * 64, transport=server(calls)))
    assert report.reason == "MODEL_DIGEST_MISMATCH" and calls == ["/api/tags"]


def test_usage_failure_exposes_safe_reason(tmp_path, monkeypatch):
    monkeypatch.setattr("services.agent_runtime.models.qualify.load_local_tokenizer", lambda path: Tokenizer())
    respond = server([]).handler

    def mismatched(request):
        if request.url.path == "/api/generate":
            return httpx.Response(200, json=response_data(prompt_eval_count=11))
        return respond(request)

    report = asyncio.run(qualify(model="local:test", tokenizer_path=tmp_path, probe=True,
                                 transport=httpx.MockTransport(mismatched)))
    assert report.status == "BLOCKED" and report.reason == "MODEL_TOKEN_CONTRACT_VIOLATION"