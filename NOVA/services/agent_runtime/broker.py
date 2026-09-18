"""ToolBroker — the single choke point between agents and tools (Constitution I3).

Agents never import or call tools. They call ``broker.invoke(...)``. The broker
runs the policy checks in order, delegates authorization to the EXISTING
action_gate, calls the tool's structured ``invoke``, wraps the output as
untrusted content (I4), mints runtime evidence into the ledger (I16), charges
the budget (I9), and records every step in the hash-chained audit log (I8).

There is no code path that lets an agent construct a tool call downstream of the
broker, and no render-to-string fallback to the legacy ``execute`` (resolution 3E).
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import time
from urllib.parse import urldefrag
from dataclasses import dataclass, field
from typing import Callable

from services.tools.action_gate import ActionRequest
from services.tools.base import ToolResult

from services.agent_runtime.contracts.content import wrap_untrusted
from services.agent_runtime.contracts.event import EventType, Severity
from services.agent_runtime.contracts.result import Evidence
from services.agent_runtime.contracts.task import AgentTask, RiskTier, TaskBudget, TaskStatus
from services.agent_runtime.events.audit import AuditLog
from services.agent_runtime.ledger import EvidenceLedger
from services.agent_runtime.models.session import MeteredModelSession
from services.agent_runtime.policy import permission_engine as pe
from services.agent_runtime.registry import AgentRegistry
from services.agent_runtime.policy.relevance import relevance_score


class BudgetTracker:
    def __init__(self, budget: TaskBudget, clock: Callable[[], float] = time.monotonic) -> None:
        self._budget = budget
        self._clock = clock
        self._start = clock()
        self.tool_calls = 0
        self.usd = 0.0
        self.model_usd = 0.0
        self.llm_tokens = 0
        self.retries = 0

    def elapsed_ms(self) -> float:
        return (self._clock() - self._start) * 1000.0

    def has_headroom(self, usd_cost: float = 0.0) -> bool:
        if self.tool_calls >= self._budget.max_tool_calls:
            return False
        if self.usd + usd_cost > self._budget.max_usd:
            return False
        if self.elapsed_ms() >= self._budget.wall_clock_ms:
            return False
        return True

    def charge_tool_call(self, usd_cost: float = 0.0) -> None:
        self.tool_calls += 1
        self.usd += usd_cost

    def add_tokens(self, n: int) -> bool:
        self.llm_tokens += n
        return self.llm_tokens <= self._budget.max_llm_tokens


@dataclass
class TaskContext:
    task: AgentTask
    budget: BudgetTracker
    cancelled: bool = False
    model_session: MeteredModelSession | None = None


@dataclass
class ToolCallResult:
    ok: bool
    denied: bool
    reason: str | None = None
    raw: ToolResult | None = None
    evidence_ids: list[str] = field(default_factory=list)
    untrusted_blocks: list[str] = field(default_factory=list)
    prose: str | None = None


class ToolBroker:
    def __init__(
        self,
        *,
        registry: AgentRegistry,
        action_gate,
        audit: AuditLog,
        ledger: EvidenceLedger,
    ) -> None:
        self._registry = registry
        self._gate = action_gate
        self._audit = audit
        self._ledger = ledger
        self._tasks: dict[str, TaskContext] = {}
        self._idempotency_keys: set[tuple[str, str, str]] = set()

    # ── task lifecycle (owned by the manager) ──────────────────────────────
    def register_task(self, ctx: TaskContext) -> None:
        self._tasks[ctx.task.id] = ctx

    def unregister_task(self, task_id: str) -> None:
        self._tasks.pop(task_id, None)

    def cancel_task(self, task_id: str) -> None:
        ctx = self._tasks.get(task_id)
        if ctx:
            ctx.cancelled = True

    def context(self, task_id: str) -> TaskContext | None:
        return self._tasks.get(task_id)

    async def complete(self, agent_id: str, task_id: str, model, *, system: str, content: str) -> dict:
        ctx = self._tasks.get(task_id)
        if (ctx is None or ctx.cancelled or ctx.task.status != TaskStatus.RUNNING
                or ctx.task.assigned_agent != agent_id):
            raise RuntimeError("MODEL_TASK_NOT_RUNNING")
        if ctx.model_session is None:
            ctx.model_session = MeteredModelSession(
                model=model, audit=self._audit, max_tokens=ctx.task.budget.max_llm_tokens,
                max_usd=ctx.task.budget.max_usd - ctx.budget.usd, task_id=task_id, agent=agent_id,
                timeout_seconds=(ctx.task.budget.wall_clock_ms - ctx.budget.elapsed_ms()) / 1000,
                is_cancelled=lambda: ctx.cancelled,
            )
        session = ctx.model_session
        try:
            completion = await session.complete(system=system, content=content)
        finally:
            ctx.budget.llm_tokens = session.tokens
            ctx.budget.usd += session.usd - ctx.budget.model_usd
            ctx.budget.model_usd = session.usd
            if session.failed:
                ctx.cancelled = True
        if ctx.cancelled:
            raise asyncio.CancelledError()
        return completion.content

    # ── the choke point ────────────────────────────────────────────────────
    async def invoke(self, agent_id: str, task_id: str, tool_name: str, args: dict,
                     *, idempotency_key: str | None = None) -> ToolCallResult:
        ctx = self._tasks.get(task_id)

        # (1) task must be RUNNING and not cancelled.
        if ctx is None:
            return await self._deny(task_id, agent_id, tool_name, pe.DenialReason.TASK_NOT_RUNNING, "no task context")
        if ctx.task.assigned_agent != agent_id:
            return await self._deny(task_id, agent_id, tool_name, pe.DenialReason.TASK_AGENT_MISMATCH,
                              "caller is not assigned to this task")
        if ctx.cancelled:
            return await self._deny(task_id, agent_id, tool_name, pe.DenialReason.TASK_CANCELLED, "cancelled")
        if ctx.task.status != TaskStatus.RUNNING:
            return await self._deny(task_id, agent_id, tool_name, pe.DenialReason.TASK_NOT_RUNNING, str(ctx.task.status))

        spec = self._registry.get(agent_id)

        # (2) grant check first — do not even resolve a tool the agent can't use.
        if tool_name not in spec.allowed_tools:
            return await self._deny(task_id, agent_id, tool_name,
                              pe.DenialReason.CAPABILITY_NOT_GRANTED, f"{tool_name} not granted")

        tool = self._registry.resolve_tool(tool_name)
        if tool is None:
            return await self._deny(task_id, agent_id, tool_name,
                              pe.DenialReason.CAPABILITY_NOT_GRANTED, "tool not in registry")

        args = copy.deepcopy(args)
        risk = pe.compute_tool_risk(self._gate, tool)
        decision = pe.decide(spec=spec, task=ctx.task, tool_id=tool_name,
                             tool=tool, args=args, risk=risk)
        if not decision.allowed:
            return await self._deny(task_id, agent_id, tool_name, decision.reason, decision.detail)

        if tool_name == "web_page_tool":
            if not any(item.kind == "search_result" and urldefrag(item.ref)[0] == urldefrag(args["url"])[0]
                       for item in self._ledger.all_for(task_id)):
                return await self._deny(task_id, agent_id, tool_name, pe.DenialReason.RESOURCE_SCOPE_DENIED,
                                        "URL not discovered by this task")

        non_idempotent = risk != RiskTier.READ_ONLY or getattr(tool, "NON_IDEMPOTENT", False)
        if non_idempotent and not idempotency_key:
            return await self._deny(task_id, agent_id, tool_name, pe.DenialReason.IDEMPOTENCY_KEY_REQUIRED,
                              "non-idempotent calls require a stable operation key")
        operation_key = (agent_id, tool_name, idempotency_key) if idempotency_key else None
        if operation_key is not None and operation_key in self._idempotency_keys:
            return await self._deny(task_id, agent_id, tool_name, pe.DenialReason.IDEMPOTENCY_REPLAY,
                              "operation key already reserved")

        # (7) budget headroom — exhaustion is fatal (I9).
        if not ctx.budget.has_headroom():
            ctx.cancelled = True
            await self._audit.append_async(EventType.BUDGET_EXCEEDED, task_id=task_id, agent=agent_id,
                               data={"tool": tool_name}, severity=Severity.HIGH)
            return ToolCallResult(ok=False, denied=True, reason=str(pe.DenialReason.BUDGET_EXCEEDED))

        # (8) delegate authorization to the EXISTING action_gate — never bypass it.
        if operation_key is not None:
            self._idempotency_keys.add(operation_key)
        ctx.budget.charge_tool_call()
        if not await asyncio.to_thread(self._authorize_via_gate, tool, args):
            return await self._deny(task_id, agent_id, tool_name, pe.DenialReason.ACTION_GATE_DENIED, "gate refused")
        if ctx.cancelled:
            return await self._deny(task_id, agent_id, tool_name, pe.DenialReason.TASK_CANCELLED, "cancelled")

        await self._audit.append_async(EventType.TOOL_INVOKED, task_id=task_id, agent=agent_id,
                           data={"tool": tool_name, "args": args, "risk": str(risk)})
        if ctx.cancelled:
            return await self._deny(task_id, agent_id, tool_name, pe.DenialReason.TASK_CANCELLED, "cancelled")
        try:
            result = await tool.invoke(**args)
        except Exception as ex:  # tool failure is a result, not a crash
            await self._audit.append_async(EventType.TOOL_RETURNED, task_id=task_id, agent=agent_id,
                               data={"tool": tool_name, "ok": False, "error": str(ex)},
                               severity=Severity.WARN)
            return ToolCallResult(ok=False, denied=False, reason=str(ex))

        if ctx.cancelled:
            return await self._deny(task_id, agent_id, tool_name, pe.DenialReason.TASK_CANCELLED, "cancelled")
        call = await self._ingest(task_id, agent_id, tool_name, result)
        await self._audit.append_async(EventType.TOOL_RETURNED, task_id=task_id, agent=agent_id,
                           data={"tool": tool_name, "ok": result.ok,
                                 "evidence_ids": call.evidence_ids})
        return call

    # ── helpers ────────────────────────────────────────────────────────────
    def _authorize_via_gate(self, tool, args: dict) -> bool:
        try:
            req = ActionRequest(
                tool=type(tool).__name__,
                action="invoke",
                params=dict(args),
                tier=self._gate.get_tier(type(tool).__name__),
                description=f"agent-runtime invoke {type(tool).__name__}",
            )
            verdict = self._gate.request(req)
            return bool(verdict.get("approved"))
        except Exception:
            return False

    async def _ingest(self, task_id: str, agent_id: str, tool_name: str, result: ToolResult) -> ToolCallResult:
        """Wrap output as untrusted (I4) and mint evidence into the ledger (I16).

        Evidence-bearing shape is the stable results contract; the broker is
        agnostic to which search backend produced it (resolution 4G).
        """
        data = result.data or {}
        prose = data.get("response")
        evidence_ids: list[str] = []
        blocks: list[str] = []
        context = self._tasks.get(task_id)
        query = (context.task.inputs.get("query") or context.task.objective) if context else None

        if result.ok and tool_name == "web_page_tool" and "page" in data:
            page = data["page"]
            digest = Evidence.digest_of(page)
            evidence = Evidence(kind="page_extract", ref=page["url"], digest=digest, trusted=False,
                task_id=task_id, tool=tool_name, title=page["title"],
                relevance=relevance_score(query, page["title"], page["text"]) if query else None)
            self._ledger.record(evidence)
            evidence_ids.append(evidence.evidence_id)
            blocks.append(wrap_untrusted(f"Page extract (possibly truncated): {page['title']}\n{page['text']}",
                source=f"page:{page['url']}", task=task_id, evidence_id=evidence.evidence_id))
            await self._audit.append_async(EventType.EVIDENCE_RECORDED, task_id=task_id, agent=agent_id,
                data={"evidence_id": evidence.evidence_id, "ref": evidence.ref, "digest": digest, "kind": evidence.kind})

        if result.ok and tool_name == "repository_read_tool" and "file" in data:
            file = data["file"]
            try:
                path, text = file["path"], file["text"]
                encoded = text.encode("utf-8")
                content_digest = hashlib.sha256(encoded).hexdigest()
                if (not isinstance(path, str) or not path or path.startswith("/")
                        or any(part in {"", ".", ".."} for part in path.split("/"))
                        or len(encoded) > 65536 or file["bytes"] != len(encoded)
                        or file["sha256"] != content_digest):
                    raise ValueError("invalid file evidence")
            except (KeyError, TypeError, AttributeError, ValueError):
                return ToolCallResult(ok=False, denied=False, reason="INVALID_FILE_EVIDENCE")
            reference = f"repo:{path}"
            digest = Evidence.digest_of({"path": path, "sha256": content_digest, "bytes": len(encoded)})
            evidence = Evidence(kind="file_content", ref=reference, digest=digest, trusted=False,
                                task_id=task_id, tool=tool_name, title=path)
            self._ledger.record(evidence)
            evidence_ids.append(evidence.evidence_id)
            blocks.append(wrap_untrusted(text, source=reference, task=task_id,
                                         evidence_id=evidence.evidence_id))
            await self._audit.append_async(EventType.EVIDENCE_RECORDED, task_id=task_id, agent=agent_id,
                data={"evidence_id": evidence.evidence_id, "ref": reference, "digest": digest,
                      "kind": "file_content"})

        for item in data.get("results", []) or []:
            url = item.get("url")
            if not url:  # never fabricate an id for an unattributed result (4A)
                continue
            title = item.get("title", "")
            snippet = item.get("snippet", "")
            digest = Evidence.digest_of({"title": title, "url": url, "snippet": snippet})
            ev = Evidence(kind="search_result", ref=url, digest=digest, trusted=False,
                          task_id=task_id, tool=tool_name, title=title,
                          relevance=relevance_score(query, title, snippet) if query else None)
            self._ledger.record(ev)
            evidence_ids.append(ev.evidence_id)
            blocks.append(wrap_untrusted(
                f"{title}\n{snippet}\n({url})", source=f"web:{url}",
                task=task_id, evidence_id=ev.evidence_id,
            ))
            await self._audit.append_async(EventType.EVIDENCE_RECORDED, task_id=task_id, agent=agent_id,
                               data={"evidence_id": ev.evidence_id, "ref": url, "digest": digest})

        for image in data.get("images", [])[:3]:
            evidence = Evidence(kind="image_reference", ref=image["url"], image_url=image["image_url"],
                                title=image["title"], digest=Evidence.digest_of(image), trusted=False,
                                task_id=task_id, tool=tool_name,
                                relevance=relevance_score(query, image["title"]) if query else None)
            self._ledger.record(evidence)
            await self._audit.append_async(EventType.EVIDENCE_RECORDED, task_id=task_id, agent=agent_id,
                                          data={"evidence_id": evidence.evidence_id, "ref": evidence.ref,
                                                "digest": evidence.digest, "kind": "image_reference"})

        return ToolCallResult(ok=result.ok, denied=False, raw=result,
                              evidence_ids=evidence_ids, untrusted_blocks=blocks, prose=prose)

    async def _deny(self, task_id, agent_id, tool_name, reason, detail: str) -> ToolCallResult:
        await self._audit.append_async(EventType.TOOL_DENIED, task_id=task_id, agent=agent_id,
                           data={"tool": tool_name, "reason": str(reason), "detail": detail},
                           severity=Severity.WARN)
        return ToolCallResult(ok=False, denied=True, reason=str(reason))
