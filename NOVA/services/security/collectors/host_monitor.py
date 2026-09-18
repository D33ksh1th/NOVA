from __future__ import annotations

from .base import BaseSecurityCollector


class HostMonitorCollector(BaseSecurityCollector):
    name = "host_monitor"
    description = "Phase 1 endpoint telemetry collector for process, persistence, ports, file, and device signals."
    coverage = [
        "running_processes",
        "process_tree",
        "listening_ports",
        "network_connections",
        "launch_agents",
        "mounted_drives",
        "usb_devices",
        "login_events",
    ]
