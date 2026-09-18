"""Explicit deployment checks; probes never enable the runtime or download assets."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, dataclass, field
import json
from pathlib import Path

import httpx

from services.agent_runtime.contracts.model_usage import ModelResponseError
from services.agent_runtime.models.ollama import OllamaRuntimeModel, load_local_tokenizer


@dataclass
class QualificationReport:
    model: str
    status: str = "BLOCKED"
    digest: str | None = None
    checks: list[str] = field(default_factory=list)
    reason: str = ""
    probe_tokens: list[int] = field(default_factory=list)


async def qualify(*, model: str, tokenizer_path: Path, probe: bool = False,
                  expected_digest: str | None = None, base_url: str = "http://127.0.0.1:11434",
                  transport: httpx.AsyncBaseTransport | None = None) -> QualificationReport:
    report = QualificationReport(model=model)
    endpoint = httpx.URL(base_url)
    if (endpoint.scheme != "http" or endpoint.host not in {"127.0.0.1", "::1"}
            or endpoint.userinfo or endpoint.path not in {"", "/"} or endpoint.query or endpoint.fragment):
        report.reason = "LOCAL_MODEL_ENDPOINT_REQUIRED"
        return report
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=5, trust_env=False,
                                     follow_redirects=False, transport=transport) as client:
            inventory = await client.get("/api/tags")
            inventory.raise_for_status()
            installed = next((item for item in inventory.json()["models"] if item.get("name") == model), None)
            if installed is None:
                report.reason = "MODEL_NOT_INSTALLED"
                return report
            report.digest = installed.get("digest")
            if not isinstance(report.digest, str) or len(report.digest) != 64:
                report.reason = "MODEL_DIGEST_INVALID"
                return report
            if expected_digest is not None and expected_digest != report.digest:
                report.reason = "MODEL_DIGEST_MISMATCH"
                return report
            report.checks.append("installed_model")
            details = await client.post("/api/show", json={"model": model})
            details.raise_for_status()
            info = details.json()
            if info.get("remote_host") or info.get("remote_model") or model.endswith(":cloud"):
                report.reason = "REMOTE_MODEL_REJECTED"
                return report
            if "completion" not in info.get("capabilities", []):
                report.reason = "COMPLETION_UNSUPPORTED"
                return report
            report.checks.append("local_completion")
            if not tokenizer_path.is_dir():
                report.reason = "TOKENIZER_DIRECTORY_REQUIRED"
                return report
            tokenizer = await asyncio.to_thread(load_local_tokenizer, tokenizer_path)
            report.checks.append("local_tokenizer")
            if not probe:
                report.status = "PREFLIGHT_ONLY"
                report.reason = "EXPLICIT_PROBE_REQUIRED"
                return report
            async with OllamaRuntimeModel(model=model, tokenizer=tokenizer, base_url=base_url,
                                          output_tokens=64, timeout_seconds=60, transport=transport) as adapter:
                for content in ("Return exactly {\"ok\":true} as JSON.",
                                "Return exactly {\"ok\":true}. Input: caf\u00e9, \u6771\u4eac, 12345.\nSecond line."):
                    completion = await adapter.complete_metered(system="Return a JSON object only.",
                                                                  content=content, max_tokens=1024, max_usd=0)
                    if completion.content != {"ok": True}:
                        report.reason = "PROBE_OUTPUT_MISMATCH"
                        return report
                    report.probe_tokens.append(completion.tokens)
            current = await client.get("/api/tags")
            current.raise_for_status()
            if not any(item.get("name") == model and item.get("digest") == report.digest
                       for item in current.json()["models"]):
                report.reason = "MODEL_CHANGED_DURING_PROBE"
                return report
            report.checks.extend(["token_counts_match", "bounded_json_output", "digest_stable"])
            report.status = "PROBES_PASSED"
            return report
    except ModelResponseError as error:
        safe_codes = {"MODEL_TOKEN_CONTRACT_VIOLATION", "MODEL_USAGE_UNAVAILABLE", "MODEL_INCOMPLETE",
                      "MODEL_JSON_INVALID", "MODEL_RESPONSE_TOO_LARGE", "MODEL_TRANSPORT_OR_RESPONSE_INVALID"}
        report.reason = str(error) if str(error) in safe_codes else "MODEL_RESPONSE_INVALID"
        return report
    except Exception as error:
        report.reason = "QUALIFICATION_FAILED:" + type(error).__name__
        return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check local Ollama deployment without enabling agents.")
    parser.add_argument("--model", required=True)
    parser.add_argument("--tokenizer", required=True, type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--expected-digest")
    parser.add_argument("--probe", action="store_true", help="Run two bounded synthetic inference probes")
    args = parser.parse_args(argv)
    report = asyncio.run(qualify(model=args.model, tokenizer_path=args.tokenizer, probe=args.probe,
                                 expected_digest=args.expected_digest, base_url=args.base_url))
    print(json.dumps(asdict(report), sort_keys=True))
    return 0 if report.status == "PROBES_PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())