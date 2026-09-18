from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Dict, List


ZONE_IT = "it"
ZONE_OT = "ot"
ZONE_UNKNOWN = "unknown"


@dataclass(slots=True)
class ZonePolicy:
    tiers: tuple[int, ...]
    concurrency: int
    inter_host_delay_ms: int
    connect_timeout_s: float
    packets_per_second: int


ZONE_POLICIES: Dict[str, ZonePolicy] = {
    ZONE_IT: ZonePolicy(tiers=(0, 1, 2, 3), concurrency=32, inter_host_delay_ms=0, connect_timeout_s=0.2, packets_per_second=2000),
    ZONE_OT: ZonePolicy(tiers=(0,), concurrency=1, inter_host_delay_ms=1000, connect_timeout_s=5.0, packets_per_second=5),
    ZONE_UNKNOWN: ZonePolicy(tiers=(0,), concurrency=1, inter_host_delay_ms=1000, connect_timeout_s=5.0, packets_per_second=5),
}


class DiscoveryScopeEngine:
    def __init__(self, allow_cidrs: List[str], deny_cidrs: List[str], zone_map: Dict[str, str]):
        self.allow_networks = self._parse_networks(allow_cidrs)
        self.deny_networks = self._parse_networks(deny_cidrs)
        self.zone_networks = [(net, (zone or "").strip().lower() or ZONE_UNKNOWN) for net, zone in self._parse_zone_map(zone_map).items()]

    @staticmethod
    def _parse_networks(cidrs: List[str]) -> List[ipaddress._BaseNetwork]:
        nets: List[ipaddress._BaseNetwork] = []
        for cidr in cidrs:
            try:
                nets.append(ipaddress.ip_network(cidr.strip(), strict=False))
            except ValueError:
                continue
        return nets

    @staticmethod
    def _parse_zone_map(raw_map: Dict[str, str]) -> Dict[ipaddress._BaseNetwork, str]:
        parsed: Dict[ipaddress._BaseNetwork, str] = {}
        for cidr, zone in raw_map.items():
            try:
                net = ipaddress.ip_network(str(cidr).strip(), strict=False)
            except ValueError:
                continue
            parsed[net] = str(zone).strip().lower()
        return parsed

    def has_allow_scope(self) -> bool:
        return len(self.allow_networks) > 0

    def _ip(self, target: str) -> ipaddress._BaseAddress:
        return ipaddress.ip_address(target)

    def is_allowed(self, target: str) -> bool:
        if not self.has_allow_scope():
            return False
        ip_obj = self._ip(target)
        if any(ip_obj in net for net in self.deny_networks):
            return False
        return any(ip_obj in net for net in self.allow_networks)

    def zone_for_ip(self, target: str) -> str:
        ip_obj = self._ip(target)
        for network, zone in self.zone_networks:
            if ip_obj in network:
                if zone == ZONE_IT:
                    return ZONE_IT
                if zone == ZONE_OT:
                    return ZONE_OT
                return ZONE_UNKNOWN
        return ZONE_UNKNOWN

    def effective_tier_for_ip(self, target: str, requested_tier: int) -> int:
        zone = self.zone_for_ip(target)
        policy = ZONE_POLICIES.get(zone, ZONE_POLICIES[ZONE_UNKNOWN])
        return max(policy.tiers)

    def policy_for_ip(self, target: str, requested_tier: int, requested_concurrency: int, requested_pps: int) -> ZonePolicy:
        zone = self.zone_for_ip(target)
        base = ZONE_POLICIES.get(zone, ZONE_POLICIES[ZONE_UNKNOWN])
        max_tier = max(base.tiers)
        selected_tier = min(max(0, int(requested_tier)), max_tier)
        allowed_tiers = tuple(t for t in base.tiers if t <= selected_tier)
        return ZonePolicy(
            tiers=allowed_tiers or (0,),
            concurrency=min(max(1, int(requested_concurrency)), base.concurrency),
            inter_host_delay_ms=base.inter_host_delay_ms,
            connect_timeout_s=base.connect_timeout_s,
            packets_per_second=min(max(1, int(requested_pps)), base.packets_per_second),
        )
