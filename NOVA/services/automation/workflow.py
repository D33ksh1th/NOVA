"""
Generic workflow engine for autonomous multi-step pipelines.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Protocol

from packages.common import logger


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class WorkflowContext:
    run_id: str
    payload: Dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.payload.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.payload[key] = value


class WorkflowAgent(Protocol):
    @property
    def name(self) -> str:
        ...

    def run(self, context: WorkflowContext) -> Dict[str, Any]:
        ...


@dataclass
class WorkflowStep:
    name: str
    started_at: str
    ended_at: str
    status: str
    output: Dict[str, Any] = field(default_factory=dict)
    error: str = ""


@dataclass
class WorkflowRun:
    run_id: str
    started_at: str
    ended_at: str
    status: str
    steps: List[WorkflowStep]
    context: Dict[str, Any]


class WorkflowEngine:
    """
    Executes agents in strict order with shared mutable context.
    """

    def run(
        self,
        run_id: str,
        agents: Iterable[WorkflowAgent],
        seed_context: Dict[str, Any] | None = None,
    ) -> WorkflowRun:
        started_at = _utc_now()
        context = WorkflowContext(run_id=run_id, payload=dict(seed_context or {}))
        steps: List[WorkflowStep] = []

        for agent in agents:
            step_started = _utc_now()
            logger.info("WorkflowEngine: starting step", run_id=run_id, step=agent.name)
            try:
                output = agent.run(context) or {}
                status = "ok"
                error = ""
                if output:
                    context.set(agent.name, output)
            except Exception as exc:
                output = {}
                status = "failed"
                error = str(exc)
                steps.append(
                    WorkflowStep(
                        name=agent.name,
                        started_at=step_started,
                        ended_at=_utc_now(),
                        status=status,
                        output=output,
                        error=error,
                    )
                )
                logger.error("WorkflowEngine: step failed", run_id=run_id, step=agent.name, error=error)
                return WorkflowRun(
                    run_id=run_id,
                    started_at=started_at,
                    ended_at=_utc_now(),
                    status="failed",
                    steps=steps,
                    context=context.payload,
                )

            steps.append(
                WorkflowStep(
                    name=agent.name,
                    started_at=step_started,
                    ended_at=_utc_now(),
                    status=status,
                    output=output,
                )
            )

        return WorkflowRun(
            run_id=run_id,
            started_at=started_at,
            ended_at=_utc_now(),
            status="ok",
            steps=steps,
            context=context.payload,
        )
