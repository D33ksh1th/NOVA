"""Plan / PlanStep — the schema-validated output an LLM may emit (Constitution I1).

The LLM proposes a Plan; the runtime disposes. Validation against the registry
rejects unknown agents, skills, tools, or capabilities — it never repairs them.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class PlanStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent: str
    capability: str
    tool: str | None = None
    skill: str | None = None
    args: dict = {}


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str
    steps: list[PlanStep]
