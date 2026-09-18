"""Tool schema registry — JSON-schema descriptions for every tool.

Used by the planner and action gate to understand tool capabilities,
required parameters, and risk classification.
"""

from __future__ import annotations

from typing import Any, Dict, List

TOOL_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "run_shell": {
        "name": "run_shell",
        "description": "Run a shell command on the local machine",
        "tier": 2,
        "params": {
            "command": {"type": "string", "description": "The shell command to execute"},
        },
        "returns": "Command stdout/stderr and exit code",
    },
    "run_playbook": {
        "name": "run_playbook",
        "description": "Run an Ansible playbook against target hosts",
        "tier": 2,
        "params": {
            "playbook": {"type": "string", "description": "Path to the playbook YAML file"},
            "inventory": {"type": "string", "description": "Target hosts or inventory file"},
            "check_mode": {"type": "boolean", "description": "If true, run --check --diff (dry run)", "default": True},
        },
        "returns": "Playbook output and changed/failed task counts",
    },
    "isolate_host": {
        "name": "isolate_host",
        "description": "Network-isolate a compromised host via firewall rules",
        "tier": 2,
        "params": {
            "host": {"type": "string", "description": "IP or hostname to isolate"},
            "reason": {"type": "string", "description": "Reason for isolation"},
        },
        "returns": "Isolation status and applied rules",
    },
    "send_mail": {
        "name": "send_mail",
        "description": "Send an email via Gmail",
        "tier": 1,
        "params": {
            "to": {"type": "string", "description": "Recipient email address"},
            "subject": {"type": "string", "description": "Email subject"},
            "body": {"type": "string", "description": "Email body text"},
        },
        "returns": "Send status and message ID",
    },
    "query_assets": {
        "name": "query_assets",
        "description": "Query discovered network assets",
        "tier": 0,
        "params": {
            "filter": {"type": "string", "description": "Optional filter (ip, hostname, risk level)"},
        },
        "returns": "List of matching assets with metadata",
    },
    "security_scan": {
        "name": "security_scan",
        "description": "Run an immediate security scan on the local host",
        "tier": 0,
        "params": {},
        "returns": "Scan results with findings count",
    },
    "set_reminder": {
        "name": "set_reminder",
        "description": "Set a timed reminder",
        "tier": 1,
        "params": {
            "message": {"type": "string", "description": "Reminder text"},
            "minutes": {"type": "integer", "description": "Minutes from now"},
        },
        "returns": "Reminder confirmation",
    },
    "schedule_event": {
        "name": "schedule_event",
        "description": "Create a calendar event (stub)",
        "tier": 1,
        "params": {
            "title": {"type": "string"},
            "time": {"type": "string", "description": "ISO datetime or natural language"},
        },
        "returns": "Event confirmation",
    },
    "rotate_credential": {
        "name": "rotate_credential",
        "description": "Rotate a service credential or API key",
        "tier": 2,
        "params": {
            "service": {"type": "string", "description": "Service name"},
            "credential_type": {"type": "string", "description": "Key type (api_key, password, token)"},
        },
        "returns": "Rotation status",
    },
}


def get_tool_schema(name: str) -> Dict[str, Any] | None:
    return TOOL_SCHEMAS.get(name)


def list_tool_schemas() -> List[Dict[str, Any]]:
    return list(TOOL_SCHEMAS.values())


def tools_by_tier(tier: int) -> List[Dict[str, Any]]:
    return [s for s in TOOL_SCHEMAS.values() if s.get("tier") == tier]
