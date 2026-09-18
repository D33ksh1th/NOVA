"""Append-only per-task evidence ledger (Constitution I16).

Only the ToolBroker writes to this, and only from real tool returns. An agent's
result may cite evidence_ids; the manager resolves them here. An id absent from
the ledger means the agent fabricated it — the result is rejected, never trusted.
"""

from __future__ import annotations

from collections import defaultdict

from services.agent_runtime.contracts.result import Evidence


class EvidenceLedger:
    def __init__(self) -> None:
        self._by_task: dict[str, dict[str, Evidence]] = defaultdict(dict)

    def record(self, evidence: Evidence) -> None:
        bucket = self._by_task[evidence.task_id]
        if evidence.evidence_id in bucket:
            raise ValueError(f"evidence {evidence.evidence_id} already recorded (append-only)")
        bucket[evidence.evidence_id] = evidence

    def contains(self, task_id: str, evidence_id: str) -> bool:
        return evidence_id in self._by_task.get(task_id, {})

    def get(self, task_id: str, evidence_id: str) -> Evidence | None:
        return self._by_task.get(task_id, {}).get(evidence_id)

    def all_for(self, task_id: str) -> list[Evidence]:
        return list(self._by_task.get(task_id, {}).values())
