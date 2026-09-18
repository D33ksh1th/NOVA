"""BaseAgent ABC and the minimal LLM protocol the runtime depends on.

Agents receive a ToolBroker and an LLM. They MUST NOT import services.tools.*
(enforced by an import-guard test) — every tool call goes through the broker.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol, runtime_checkable

from services.agent_runtime.broker import ToolBroker
from services.agent_runtime.contracts.result import AgentResult
from services.agent_runtime.contracts.model_usage import MeteredCompletion
from services.agent_runtime.contracts.task import AgentTask
from services.agent_runtime.registry import AgentSpec


@runtime_checkable
class LLM(Protocol):
    async def complete_metered(self, *, system: str, content: str,
                               max_tokens: int, max_usd: float) -> MeteredCompletion:
        """Return a structured object and total input/output token usage.

        Enforce the supplied total-token and provider-cost limits before dispatch.
        Failed calls with reported usage raise ModelResponseError; missing usage
        is reserved conservatively by the runtime. Propagate cancellation. The
        runtime validates content; models cannot mint evidence (Constitution I16).
        """
        ...


class BaseAgent(ABC):
    def __init__(self, spec: AgentSpec, broker: ToolBroker, llm: LLM) -> None:
        self.spec = spec
        self.name = spec.name
        self.broker = broker
        self.llm = llm

    @abstractmethod
    async def run(self, task: AgentTask) -> AgentResult:
        ...
