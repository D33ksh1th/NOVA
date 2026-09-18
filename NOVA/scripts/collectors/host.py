from __future__ import annotations

from typing import Any, Callable, Set


class HostCollector:
    name = "host"
    interval = 60
    cost = 2
    zones: Set[str] = {"it", "ot"}

    def __init__(self, collect_fn: Callable[[], dict[str, Any]]):
        self._collect_fn = collect_fn

    def collect(self) -> dict[str, Any]:
        return self._collect_fn()


class PassiveDiscoveryCollector:
    name = "passive_discovery"
    interval = 60
    cost = 1
    zones: Set[str] = {"it", "ot"}

    def __init__(self, collect_fn: Callable[[], dict[str, Any]]):
        self._collect_fn = collect_fn

    def collect(self) -> dict[str, Any]:
        return self._collect_fn()
