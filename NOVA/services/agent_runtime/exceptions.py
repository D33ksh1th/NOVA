"""Typed errors for the agent runtime. Never resolve a policy failure silently."""

from __future__ import annotations


class AgentRuntimeError(Exception):
    """Base class for all agent-runtime errors."""


class PolicyError(AgentRuntimeError):
    """A capability/policy configuration is invalid; fail fast at startup."""


class UnknownAgentError(PolicyError):
    pass


class UnknownToolError(PolicyError):
    pass


class UnknownSkillError(PolicyError):
    pass


class UnknownCapabilityError(PolicyError):
    pass


class OrphanCapabilityError(PolicyError):
    """A granted capability is backed by no tool in allowed_tools (Constitution I14)."""


class FabricatedEvidenceError(AgentRuntimeError):
    """An agent cited an evidence_id absent from the task ledger (Constitution I16)."""
