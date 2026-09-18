"""Result contracts: AgentResult, Evidence, ResultStatus, CostRecord."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum

from services.agent_runtime.ids import new_id
from services.agent_runtime.policy.canonical import canonical_bytes

import hashlib


class ResultStatus(StrEnum):
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    REFUSED = "REFUSED"


@dataclass(frozen=True)
class Evidence:
    """Runtime-minted proof of a real tool call (Constitution I16).

    An LLM never authors this. ``digest`` covers the payload we actually
    received (e.g. a search snippet), never page contents we did not fetch —
    hence kind="search_result", not "citation" (resolution 4C).
    """

    kind: str                # "search_result" | "tool_output" | "file_hash" | "test_run"
    ref: str                 # the url / path / identifier
    digest: str              # sha256 of the canonical evidence payload
    trusted: bool            # False for anything web/user/file sourced
    task_id: str
    tool: str
    evidence_id: str = field(default_factory=lambda: new_id("ev"))
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    title: str = ""
    image_url: str | None = None
    relevance: dict | None = None

    @staticmethod
    def digest_of(payload: dict) -> str:
        return hashlib.sha256(canonical_bytes(payload)).hexdigest()


@dataclass(frozen=True)
class CostRecord:
    wall_clock_ms: int = 0
    tool_calls: int = 0
    llm_tokens: int = 0
    usd: float = 0.0
    retries: int = 0


@dataclass
class AgentResult:
    task_id: str
    agent: str
    status: ResultStatus
    summary: str
    payload: dict = field(default_factory=dict)
    evidence: list[Evidence] = field(default_factory=list)
    confidence: float = 0.0          # self-reported, advisory only
    cost: CostRecord = field(default_factory=CostRecord)
    errors: list[str] = field(default_factory=list)
    media: list[Evidence] = field(default_factory=list)
