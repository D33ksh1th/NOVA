"""
Base Tool
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class ToolResult:
    """Structured return of Tool.invoke(). Consumed by the agent-runtime broker.

    ``data`` is treated as UNTRUSTED by the broker (Constitution I4) and wrapped
    before it can reach any LLM prompt.
    """

    ok: bool
    data: dict = field(default_factory=dict)
    error: Optional[str] = None


class Tool(ABC):

    # ── Agent-runtime metadata (additive; ignored by the legacy intent router) ──
    # A tool without SUPPORTS_STRUCTURED_ARGS = True is capped at READ_ONLY and is
    # unreachable at LOW+ risk through the broker (Constitution I15).
    SUPPORTS_STRUCTURED_ARGS: bool = False
    ARG_SCHEMA: Optional[dict] = None  # JSON Schema for invoke(**args)
    PROVIDES_CAPABILITIES: frozenset[str] = frozenset()  # backs capabilities.yaml grants (I14)
    USES_URL_POLICY: bool = False  # required True for any net.egress tool (2E)

    @property
    @abstractmethod
    def name(self):
        pass

    @abstractmethod
    def can_handle(
        self,
        message: str,
    ) -> bool:
        pass

    @abstractmethod
    def execute(
        self,
        message: str,
    ):
        pass

    async def invoke(self, **args: Any) -> ToolResult:
        """Structured, broker-only entrypoint (Constitution I3/I15).

        The legacy intent router never calls this — it keeps using execute().
        Tools opt in by overriding invoke() and setting SUPPORTS_STRUCTURED_ARGS.
        """
        raise NotImplementedError(f"{type(self).__name__} has no structured invoke()")