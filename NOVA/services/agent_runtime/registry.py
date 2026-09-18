"""AgentSpec + AgentRegistry. Loads static capability grants and FAILS FAST.

Validation at load time (Constitution I2, I14):
  - every allowed_tool must exist in the live tool registry -> UnknownToolError
  - every granted capability must be PROVIDED by an allowed tool -> OrphanCapabilityError
There is no runtime mutation and no wildcard grant.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

import yaml

from services.agent_runtime.contracts.task import RiskTier, TaskBudget
from services.agent_runtime.exceptions import (
    OrphanCapabilityError,
    UnknownAgentError,
    UnknownToolError,
    PolicyError,
)

_CAMEL_RE = re.compile(r"(?<!^)(?=[A-Z])")

_DEFAULT_YAML = Path(__file__).parent / "policy" / "capabilities.yaml"


def tool_id_of(tool) -> str:
    """Canonical snake_case id for a tool, e.g. WebSearchTool -> web_search_tool.

    A tool may override by declaring a class attribute ``TOOL_ID``.
    """
    explicit = getattr(tool, "TOOL_ID", None)
    if explicit:
        return explicit
    return _CAMEL_RE.sub("_", type(tool).__name__).lower()


@dataclass(frozen=True)
class AgentSpec:
    name: str
    capabilities: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    denied_tools: tuple[str, ...]
    max_risk: RiskTier
    concurrency_limit: int
    default_budget: TaskBudget
    resource_scopes: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    skills: tuple[str, ...] = ()
    description: str = ""
    enabled: bool = True


class AgentRegistry:
    def __init__(self, tool_registry) -> None:
        self._tool_registry = tool_registry
        self._specs: Mapping[str, AgentSpec] = {}
        self._loaded = False
        self._tools_by_id = {tool_id_of(t): t for t in tool_registry.all()}

    def resolve_tool(self, tool_id: str):
        return self._tools_by_id.get(tool_id)

    def load(self, path: str | Path | None = None, *, repository_reader: bool = False, page_reader: bool = False) -> "AgentRegistry":
        if self._loaded:
            raise PolicyError("Capability policy is startup-only; restart to change grants")
        raw = yaml.safe_load(Path(path or _DEFAULT_YAML).read_text()) or {}
        if page_reader:
            extra = yaml.safe_load((_DEFAULT_YAML.parent / "page_capabilities.yaml").read_text())
            for key in ("capabilities", "allowed_tools"):
                raw["research_agent"][key] = [*raw["research_agent"][key], *extra[key]]
        if repository_reader:
            extra = yaml.safe_load((_DEFAULT_YAML.parent / "repository_capabilities.yaml").read_text())
            if set(raw) & set(extra):
                raise PolicyError("Duplicate repository policy")
            raw.update(extra)
        specs: dict[str, AgentSpec] = {}
        for name, cfg in raw.items():
            spec = self._build_spec(name, cfg)
            self._validate(spec)
            specs[name] = spec
        self._specs = MappingProxyType(specs)
        self._loaded = True
        return self

    def _build_spec(self, name: str, cfg: dict) -> AgentSpec:
        budget = cfg["default_budget"]
        return AgentSpec(
            name=name,
            capabilities=tuple(cfg.get("capabilities", [])),
            allowed_tools=tuple(cfg.get("allowed_tools", [])),
            denied_tools=tuple(cfg.get("denied_tools", [])),
            max_risk=RiskTier(cfg["max_risk"]),
            concurrency_limit=int(cfg.get("concurrency_limit", 1)),
            default_budget=TaskBudget(
                wall_clock_ms=int(budget["wall_clock_ms"]),
                max_tool_calls=int(budget["max_tool_calls"]),
                max_llm_tokens=int(budget["max_llm_tokens"]),
                max_usd=float(budget["max_usd"]),
                max_retries=int(budget["max_retries"]),
            ),
            resource_scopes=_freeze(cfg.get("resource_scopes", {})),
            skills=tuple(cfg.get("skills", [])),
            description=cfg.get("description", ""),
            enabled=bool(cfg.get("enabled", True)),
        )

    def _validate(self, spec: AgentSpec) -> None:
        if any("*" in grant for grant in (*spec.capabilities, *spec.allowed_tools, *spec.skills)):
            raise PolicyError("Wildcard grants are forbidden")
        if spec.concurrency_limit < 1:
            raise PolicyError("Concurrency limit must be positive")
        # 1. Every allowed tool must exist in the live tool registry.
        provided: set[str] = set()
        for tool_id in spec.allowed_tools:
            tool = self.resolve_tool(tool_id)
            if tool is None:
                raise UnknownToolError(
                    f"agent {spec.name!r} allows unknown tool {tool_id!r}"
                )
            provided |= set(tool.PROVIDES_CAPABILITIES)
        # 2. Every granted capability must be backed by an allowed tool (I14).
        for capability in spec.capabilities:
            if capability not in provided:
                raise OrphanCapabilityError(
                    f"agent {spec.name!r} grants capability {capability!r} "
                    f"with no backing tool in allowed_tools"
                )

    def get(self, name: str) -> AgentSpec:
        try:
            return self._specs[name]
        except KeyError:
            raise UnknownAgentError(f"unknown agent {name!r}")

    def has(self, name: str) -> bool:
        return name in self._specs

    def names(self) -> list[str]:
        return list(self._specs)


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value
