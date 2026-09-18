from __future__ import annotations

from .base import BaseSecurityCollector


class NetworkMonitorCollector(BaseSecurityCollector):
    name = "network_monitor"
    description = "Phase 3 network SOC collector for DNS, HTTP/S, SSH, SMB, FTP, and beaconing indicators."
    coverage = [
        "dns",
        "http",
        "https",
        "ssh",
        "smb",
        "ftp",
        "arp",
        "outbound_destinations",
    ]
