from __future__ import annotations

from typing import Dict, Iterable

from .types import SecurityFinding


class SecurityRiskEngine:
    _WEIGHTS = {
        "critical": 35,
        "high": 20,
        "medium": 10,
        "low": 4,
    }

    def score(self, findings: Iterable[SecurityFinding]) -> Dict[str, int]:
        scores = {
            "host": 100,
            "browser": 100,
            "network": 100,
            "identity": 100,
        }

        for finding in findings:
            penalty = self._WEIGHTS.get(finding.risk, 0)
            source = finding.source.lower()
            tags = " ".join(finding.tags or []).lower()
            affected = set()

            if "host" in source or "endpoint" in source or "command" in source:
                affected.add("host")
            if "browser" in source or "prompt" in source or "site" in source:
                affected.add("browser")
            if "network" in source or "dns" in source:
                affected.add("network")
            if "identity" in source or "login" in source:
                affected.add("identity")

            if any(token in tags for token in ("execution", "persistence", "packages", "patching", "linux", "host")):
                affected.add("host")
            if any(token in tags for token in ("browser", "phishing", "prompt", "download")):
                affected.add("browser")
            if any(token in tags for token in ("network", "discovery", "dns", "beaconing", "lateral")):
                affected.add("network")
            if any(token in tags for token in ("identity", "login", "credential", "auth")):
                affected.add("identity")

            if not affected:
                affected = {"host"}

            per_domain_penalty = max(1, round(penalty / len(affected)))
            for domain in affected:
                scores[domain] -= per_domain_penalty

        host = max(0, scores["host"])
        browser = max(0, scores["browser"])
        network = max(0, scores["network"])
        identity = max(0, scores["identity"])
        overall = round((host + browser + network + identity) / 4)

        return {
            "host": host,
            "browser": browser,
            "network": network,
            "identity": identity,
            "overall": overall,
        }
