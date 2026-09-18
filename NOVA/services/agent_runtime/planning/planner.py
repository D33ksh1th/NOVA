from __future__ import annotations

import asyncio

from services.agent_runtime.base import LLM
from services.agent_runtime.contracts.content import STANDING_RULE, wrap_untrusted
from services.agent_runtime.contracts.model_usage import ModelResponseError
from services.agent_runtime.graph.task_graph import GraphPlan, InvocationContext
from services.agent_runtime.models.session import MeteredModelSession
from services.agent_runtime.planning.plan_validator import PlanRejected, PlanValidator
from services.agent_runtime.policy.canonical import canonical_json


class Planner:
    def __init__(self, model: LLM, validator: PlanValidator, *, max_tokens: int = 40000,
                 max_usd: float = 0.5, timeout_seconds: float = 120) -> None:
        self.model = model
        self.validator = validator
        self.max_tokens = max_tokens
        self.max_usd = max_usd
        self.timeout_seconds = timeout_seconds

    async def propose(self, intent: str, context: InvocationContext) -> GraphPlan:
        async with asyncio.timeout(self.timeout_seconds):
            return await self._propose(intent, context)

    async def _propose(self, intent: str, context: InvocationContext) -> GraphPlan:
        system = (
            "Propose a task graph as JSON only. You cannot execute actions. "
            "Do not invent agents or capabilities. " + STANDING_RULE + "\n"
            + canonical_json(GraphPlan.model_json_schema())
        )
        inventory = [{"agent": name, "capabilities": self.validator.registry.get(name).capabilities,
                      "tools": self.validator.registry.get(name).allowed_tools,
                      "max_risk": self.validator.registry.get(name).max_risk}
                     for name in self.validator.registry.names()]
        content = canonical_json({"intent": intent, "inventory": inventory})
        session = MeteredModelSession(model=self.model, audit=self.validator.audit,
                                      max_tokens=self.max_tokens, max_usd=self.max_usd,
                                      timeout_seconds=self.timeout_seconds)
        for attempt in range(2):
            raw = ""
            try:
                completion = await session.complete(system=system, content=content)
                raw = canonical_json(completion.content)
            except ModelResponseError as error:
                if str(error) != "MODEL_JSON_INVALID" or error.tokens is None:
                    raise
            try:
                return await self.validator.validate_async(raw, context)
            except PlanRejected as error:
                if not error.repairable or attempt == 1:
                    raise
                content += "\n" + wrap_untrusted(raw, source="model:plan", task="planning")
                content += "\nValidation failed: SCHEMA_INVALID. Return one corrected JSON plan."
        raise AssertionError("Unreachable planning state")