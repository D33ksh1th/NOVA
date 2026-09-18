"""Permission engine: the pure decision logic the broker enforces.

Given a static AgentSpec, a task, and a requested tool call, ``decide`` returns
an allow/deny Decision. It performs no I/O and executes nothing — the broker
owns side effects (action_gate, the tool call, budget accounting).

Check order mirrors Constitution I3 (minus the task-running and budget checks,
which the broker performs around this call).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from services.agent_runtime.contracts.plan import Plan
from services.agent_runtime.contracts.task import AgentTask, RiskTier, risk_at_most
from services.agent_runtime.exceptions import (
    UnknownAgentError,
    UnknownCapabilityError,
    UnknownToolError,
)
from services.agent_runtime.registry import AgentRegistry, AgentSpec

# Map the existing action_gate tiers to runtime risk tiers.
_GATE_TIER_TO_RISK = {0: RiskTier.READ_ONLY, 1: RiskTier.LOW, 2: RiskTier.HIGH}


class DenialReason(StrEnum):
    TASK_AGENT_MISMATCH = "TASK_AGENT_MISMATCH"
    IDEMPOTENCY_KEY_REQUIRED = "IDEMPOTENCY_KEY_REQUIRED"
    IDEMPOTENCY_REPLAY = "IDEMPOTENCY_REPLAY"
    TASK_NOT_RUNNING = "TASK_NOT_RUNNING"
    TASK_CANCELLED = "TASK_CANCELLED"
    CAPABILITY_NOT_GRANTED = "CAPABILITY_NOT_GRANTED"
    TOOL_DENIED_EXPLICIT = "TOOL_DENIED_EXPLICIT"
    NO_STRUCTURED_ENTRYPOINT = "NO_STRUCTURED_ENTRYPOINT"
    NET_EGRESS_NO_URL_POLICY = "NET_EGRESS_NO_URL_POLICY"
    ARG_SCHEMA_VIOLATION = "ARG_SCHEMA_VIOLATION"
    RESOURCE_SCOPE_DENIED = "RESOURCE_SCOPE_DENIED"
    RISK_EXCEEDS_AGENT = "RISK_EXCEEDS_AGENT"
    RISK_EXCEEDS_TASK = "RISK_EXCEEDS_TASK"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    APPROVAL_INVALID = "APPROVAL_INVALID"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    ACTION_GATE_DENIED = "ACTION_GATE_DENIED"


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: DenialReason | None
    risk: RiskTier
    detail: str = ""


def compute_tool_risk(action_gate, tool) -> RiskTier:
    tier = int(action_gate.get_tier(type(tool).__name__))
    return _GATE_TIER_TO_RISK.get(tier, RiskTier.HIGH)


def _validate_args(schema: dict | None, args: dict) -> str | None:
    """Minimal JSON-Schema subset sufficient for Phase 1 tool arg validation."""
    if schema is None:
        return None
    if schema.get("type") == "object":
        props = schema.get("properties", {})
        if schema.get("additionalProperties", True) is False:
            extra = set(args) - set(props)
            if extra:
                return f"unexpected args: {sorted(extra)}"
        for req in schema.get("required", []):
            if req not in args:
                return f"missing required arg: {req}"
        for key, value in args.items():
            spec = props.get(key)
            if spec is None:
                continue
            err = _validate_scalar(key, value, spec)
            if err:
                return err
    return None


def _validate_scalar(key: str, value, spec: dict) -> str | None:
    typ = spec.get("type")
    if typ == "string":
        if not isinstance(value, str):
            return f"{key} must be string"
        if "minLength" in spec and len(value) < spec["minLength"]:
            return f"{key} too short"
        if "maxLength" in spec and len(value) > spec["maxLength"]:
            return f"{key} too long"
    elif typ == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            return f"{key} must be integer"
        if "minimum" in spec and value < spec["minimum"]:
            return f"{key} below minimum"
        if "maximum" in spec and value > spec["maximum"]:
            return f"{key} above maximum"
    elif typ == "number":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return f"{key} must be number"
    elif typ == "boolean":
        if not isinstance(value, bool):
            return f"{key} must be boolean"
    return None


def decide(
    *,
    spec: AgentSpec,
    task: AgentTask,
    tool_id: str,
    tool,
    args: dict,
    risk: RiskTier,
    has_valid_approval: bool = False,
) -> Decision:
    # (2) capability / tool grant — deny by default.
    if tool_id not in spec.allowed_tools:
        return Decision(False, DenialReason.CAPABILITY_NOT_GRANTED, risk,
                        f"{tool_id} not in allowed_tools")
    if tool_id in spec.denied_tools:
        return Decision(False, DenialReason.TOOL_DENIED_EXPLICIT, risk, tool_id)

    # (I15 / 3E) structured entrypoint required — no render-to-string fallback.
    if not getattr(tool, "SUPPORTS_STRUCTURED_ARGS", False):
        return Decision(False, DenialReason.NO_STRUCTURED_ENTRYPOINT, risk,
                        f"{tool_id} has no invoke()")

    # (2E) any net.egress tool must route through url_policy.
    if "net.egress" in set(getattr(tool, "PROVIDES_CAPABILITIES", frozenset())):
        if not getattr(tool, "USES_URL_POLICY", False):
            return Decision(False, DenialReason.NET_EGRESS_NO_URL_POLICY, risk, tool_id)

    # (3) resource-scope check on args.
    arg_err = _validate_args(getattr(tool, "ARG_SCHEMA", None), args)
    if arg_err:
        return Decision(False, DenialReason.ARG_SCHEMA_VIOLATION, risk, arg_err)

    if "repo.read" in getattr(tool, "PROVIDES_CAPABILITIES", ()):
        scope = spec.resource_scopes.get("repository")
        files = task.inputs.get("files")
        if (scope != "nova-desktop" or task.inputs.get("repository") != scope
                or not isinstance(files, (list, tuple)) or not 1 <= len(files) <= 3
                or args.get("path") not in files):
            return Decision(False, DenialReason.RESOURCE_SCOPE_DENIED, risk, "File outside task scope")

    # (4) computed risk <= agent max_risk AND <= task risk.
    if not risk_at_most(risk, spec.max_risk):
        return Decision(False, DenialReason.RISK_EXCEEDS_AGENT, risk,
                        f"{risk} > agent max {spec.max_risk}")
    if not risk_at_most(risk, task.risk):
        return Decision(False, DenialReason.RISK_EXCEEDS_TASK, risk,
                        f"{risk} > task risk {task.risk}")

    # (5) MEDIUM+ requires a valid, bound, single-use approval token.
    if not risk_at_most(risk, RiskTier.LOW) and not has_valid_approval:
        return Decision(False, DenialReason.APPROVAL_REQUIRED, risk, str(risk))

    return Decision(True, None, risk, "ok")


def validate_plan(plan: Plan, registry: AgentRegistry) -> None:
    """Reject a plan that references unknown agents/tools/capabilities (I1)."""
    for step in plan.steps:
        if not registry.has(step.agent):
            raise UnknownAgentError(f"plan references unknown agent {step.agent!r}")
        spec = registry.get(step.agent)
        if step.capability not in spec.capabilities:
            raise UnknownCapabilityError(
                f"agent {step.agent!r} not granted capability {step.capability!r}"
            )
        if step.tool is not None and step.tool not in spec.allowed_tools:
            raise UnknownToolError(
                f"agent {step.agent!r} not allowed tool {step.tool!r}"
            )
