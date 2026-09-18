from __future__ import annotations

from services.agent_runtime.graph.task_graph import Node


class Scheduler:
    def __init__(self, max_parallel: int, age_interval: float = 5.0) -> None:
        if not 1 <= max_parallel <= 4 or age_interval <= 0:
            raise ValueError("Invalid scheduler limits")
        self.max_parallel = max_parallel
        self.age_interval = age_interval

    def select(
        self, ready: list[Node], running: dict[str, int],
        limits: dict[str, int], queued_at: dict[str, float], now: float,
    ) -> list[Node]:
        capacity = self.max_parallel - sum(running.values())
        selected: list[Node] = []
        counts = dict(running)
        ordered = sorted(ready, key=lambda node: (
            -(node.priority + int((now - queued_at[node.id]) / self.age_interval)),
            queued_at[node.id],
        ))
        for node in ordered:
            if len(selected) >= capacity:
                break
            if counts.get(node.agent, 0) < limits[node.agent]:
                selected.append(node)
                counts[node.agent] = counts.get(node.agent, 0) + 1
        return selected