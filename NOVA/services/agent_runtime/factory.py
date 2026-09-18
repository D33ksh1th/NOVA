"""Manual wiring for the agent runtime (Phase 1: not auto-wired into NOVA).

This is the single seam the Brain will eventually call through
``AgentManager.run_task``. It is intentionally a plain factory, not registered in
the service container, so NOVA boots identically whether or not it is used.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from services.agent_runtime.base import LLM
from services.agent_runtime.broker import ToolBroker
from services.agent_runtime.events.audit import AuditLog
from services.agent_runtime.ledger import EvidenceLedger
from services.agent_runtime.manager import AgentManager
from services.agent_runtime.registry import AgentRegistry


def build_runtime(*, tool_registry, action_gate, llm: LLM,
                  capabilities_path: str | Path | None = None,
                  audit: AuditLog | None = None, repository_root: Path | None = None,
                  read_pages: bool = False) -> AgentManager:
    if read_pages:
        from services.tools.web_page_tool import WebPageTool
        from types import SimpleNamespace
        page_tools = [*tool_registry.all(), WebPageTool()]
        tool_registry = SimpleNamespace(all=lambda: page_tools)
    if repository_root is not None:
        from services.tools.repository_read_tool import RepositoryReadTool
        from types import SimpleNamespace
        tools = [*tool_registry.all(), RepositoryReadTool(repository_root)]
        tool_registry = SimpleNamespace(all=lambda: tools)
    registry = AgentRegistry(tool_registry).load(capabilities_path, repository_reader=repository_root is not None,
                                                page_reader=read_pages)
    audit = audit if audit is not None else AuditLog()
    ledger = EvidenceLedger()
    broker = ToolBroker(registry=registry, action_gate=action_gate, audit=audit, ledger=ledger)
    return AgentManager(registry=registry, broker=broker, audit=audit, ledger=ledger, llm=llm)


async def build_runtime_async(*, tool_registry, action_gate, llm: LLM,
                              audit_path: str | Path,
                              capabilities_path: str | Path | None = None,
                              repository_root: Path | None = None, read_pages: bool = False) -> AgentManager:
    """Open durable audit storage; callers must await manager.close() after work.

    The injected model remains caller-owned. For OllamaRuntimeModel, keep its
    async context open until all tasks/graphs finish and the manager is closed.
    """
    audit = await AuditLog.open(audit_path)
    try:
        return await asyncio.to_thread(build_runtime, tool_registry=tool_registry,
                                       action_gate=action_gate, llm=llm,
                                       capabilities_path=capabilities_path, audit=audit, repository_root=repository_root,
                                       read_pages=read_pages)
    except BaseException:
        await audit.close()
        raise
