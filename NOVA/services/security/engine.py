from __future__ import annotations

import json
import platform
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple
from uuid import uuid4

from packages.common import logger, cache
from packages.config import settings
from packages.events import bus, Event

from .collectors import (
    BrowserGuardianCollector,
    HostMonitorCollector,
    IdentityGuardianCollector,
    NetworkMonitorCollector,
)
from .risk_engine import SecurityRiskEngine
from .timeline import SecurityTimeline
from .types import SecurityFinding

_AGENT_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "security_agent.py"
_LOCAL_AGENT_ID = f"local:{socket.gethostname()}"
_LOCAL_SCAN_INTERVAL = 300  # seconds (5 min)


class SecurityCenter:
    def __init__(self):
        self.collectors = {
            "host": HostMonitorCollector(),
            "browser": BrowserGuardianCollector(),
            "network": NetworkMonitorCollector(),
            "identity": IdentityGuardianCollector(),
        }
        self.risk_engine = SecurityRiskEngine()
        from .anomaly_engine import AnomalyDetectionEngine
        self.anomaly_engine = AnomalyDetectionEngine()
        self.timeline = SecurityTimeline(limit=1000)
        self.findings: List[SecurityFinding] = []
        self.finding_index: Dict[str, SecurityFinding] = {}
        self.agents: Dict[str, Dict[str, object]] = {}
        self.assets: Dict[str, Dict[str, object]] = {}
        restored = self._restore_state_from_cache()
        if not restored:
            # Ensure route-level response caches do not return stale data from a prior run.
            cache.delete("security:status")
            cache.delete("security:agents")
            cache.delete("security:assets")
            cache.delete("security:findings")
            cache.delete_pattern("security:timeline:*")
            self.timeline.add(
                category="security_center",
                title="Security Center initialized",
                detail="Phase 1 foundation is active: collectors, timeline, risk engine, and correlation shell are ready.",
            )
            self._persist_state_to_cache()
        logger.info("Security Center Initialized")
        # Run first local scan immediately then repeat every 5 minutes.
        self._start_local_scanner()

    def _state_cache_key(self) -> str:
        return "security:center:state"

    def _serialize_state(self) -> Dict[str, object]:
        return {
            "version": 1,
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "agents": self.agents,
            "assets": self.assets,
            "findings": [finding.to_dict() for finding in self.findings],
            "timeline": self.timeline.list_recent(limit=1000),
        }

    def _persist_state_to_cache(self) -> None:
        try:
            cache.set_json(
                self._state_cache_key(),
                self._serialize_state(),
                settings.SECURITY_STATE_CACHE_TTL,
            )
        except Exception as ex:
            logger.warning(f"SecurityCenter: state cache persist failed: {ex}")

    def _restore_state_from_cache(self) -> bool:
        try:
            payload = cache.get_json(self._state_cache_key())
        except Exception as ex:
            logger.warning(f"SecurityCenter: state cache restore failed: {ex}")
            return False

        if not isinstance(payload, dict):
            return False

        agents = payload.get("agents")
        assets = payload.get("assets")
        findings_raw = payload.get("findings")
        timeline_raw = payload.get("timeline")

        if isinstance(agents, dict):
            self.agents = {str(k): v for k, v in agents.items() if isinstance(v, dict)}
        if isinstance(assets, dict):
            self.assets = {str(k): v for k, v in assets.items() if isinstance(v, dict)}

        restored_findings: List[SecurityFinding] = []
        if isinstance(findings_raw, list):
            for item in findings_raw:
                if not isinstance(item, dict):
                    continue
                try:
                    finding = SecurityFinding(
                        id=str(item.get("id") or str(uuid4())),
                        source=str(item.get("source") or "agent:unknown"),
                        title=str(item.get("title") or "Security finding"),
                        summary=str(item.get("summary") or ""),
                        risk=str(item.get("risk") or "medium"),
                        confidence=float(item.get("confidence", 0.0) or 0.0),
                        tags=list(item.get("tags") or []),
                        evidence=dict(item.get("evidence") or {}),
                        created_at=str(item.get("created_at") or datetime.now(timezone.utc).isoformat()),
                    )
                    restored_findings.append(finding)
                except Exception:
                    continue

        self.findings = restored_findings
        self.finding_index = {
            self._finding_fingerprint(
                source=f.source,
                title=f.title,
                summary=f.summary,
                risk=f.risk,
            ): f
            for f in self.findings
        }

        restored_events = 0
        if isinstance(timeline_raw, list):
            restored_events = self.timeline.restore(timeline_raw)

        if self.agents or self.assets or self.findings or restored_events:
            logger.info(
                "SecurityCenter: restored state from cache",
                agents=len(self.agents),
                assets=len(self.assets),
                findings=len(self.findings),
                events=restored_events,
            )
            return True
        return False

    # ── Local self-scan ──────────────────────────────────────────

    def _start_local_scanner(self) -> None:
        """Spawn a daemon thread that periodically runs the local security agent."""
        t = threading.Thread(
            target=self._local_scan_loop, daemon=True, name="nova-local-security-scan"
        )
        t.start()
        logger.info("SecurityCenter: local scanner thread started")

    def _local_scan_loop(self) -> None:
        # Small boot delay so the rest of the registry finishes initialising.
        time.sleep(4)
        while True:
            try:
                self.local_scan()
            except Exception as ex:
                logger.warning(f"SecurityCenter: local scan error: {ex}")
            time.sleep(_LOCAL_SCAN_INTERVAL)

    def local_scan(self) -> Dict[str, object]:
        """Run the security_agent script as a subprocess with --snapshot flag
        and ingest the result directly, no HTTP needed."""
        if not _AGENT_SCRIPT.exists():
            logger.warning(f"SecurityCenter: agent script not found at {_AGENT_SCRIPT}")
            return {"ok": False, "error": "agent script not found"}

        bus.emit(Event.SECURITY_SCAN_STARTED, source="security-center", severity=0)
        logger.info("SecurityCenter: running local security scan…")
        try:
            result = subprocess.run(
                [sys.executable, str(_AGENT_SCRIPT), "--snapshot"],
                capture_output=True,
                text=True,
                timeout=120,
            )
            raw = (result.stdout or "").strip()
            if not raw:
                stderr = (result.stderr or "").strip()
                logger.warning(f"SecurityCenter: local scan produced no output. stderr={stderr[:300]}")
                return {"ok": False, "error": "no output"}

            payload = json.loads(raw)
            findings_raw = payload.get("findings", [])
            telemetry = payload.get("telemetry", {})

            self.ingest_agent_heartbeat(
                agent_id=_LOCAL_AGENT_ID,
                hostname=payload.get("hostname", socket.gethostname()),
                platform=payload.get("platform", platform.platform()),
                telemetry=telemetry,
                findings=findings_raw,
            )
            logger.info(
                f"SecurityCenter: local scan complete — {len(findings_raw)} finding(s), "
                f"{len(telemetry)} telemetry keys"
            )
            bus.emit(
                Event.SECURITY_SCAN_COMPLETED,
                source="security-center",
                payload={"findings": len(findings_raw), "telemetry_keys": len(telemetry)},
                severity=2 if findings_raw else 0,
            )
            return {"ok": True, "findings": len(findings_raw)}
        except subprocess.TimeoutExpired:
            logger.warning("SecurityCenter: local scan timed out")
            return {"ok": False, "error": "timeout"}
        except json.JSONDecodeError as ex:
            logger.warning(f"SecurityCenter: local scan output was not valid JSON: {ex}")
            return {"ok": False, "error": f"json decode: {ex}"}
        except Exception as ex:
            logger.warning(f"SecurityCenter: local scan failed: {ex}")
            return {"ok": False, "error": str(ex)}

    def status(self) -> Dict[str, object]:
        return {
            "phase": "phase_6_anomaly_detection",
            "mission": "Personal AI SOC analyst with statistical + ML anomaly detection.",
            "collectors": {key: collector.status().to_dict() for key, collector in self.collectors.items()},
            "scores": self.risk_engine.score(self.findings),
            "active_findings": len(self.findings),
            "connected_agents": len(self.agents),
            "asset_count": len(self.assets),
            "timeline_events": len(self.timeline.list_recent(limit=1000)),
            "anomaly_detection": self.anomaly_engine.stats(),
            "phases": self.phases(),
        }

    def phases(self) -> List[Dict[str, object]]:
        return [
            {
                "id": 1,
                "name": "Foundation + Host telemetry",
                "status": "in_progress",
                "outcomes": [
                    "Security Center service",
                    "collector registry",
                    "timeline",
                    "risk scoring",
                    "host telemetry adapters",
                ],
            },
            {
                "id": 2,
                "name": "Browser Guardian + Prompt Security",
                "status": "planned",
                "outcomes": [
                    "URL risk checks",
                    "lookalike-domain detection",
                    "download inspection",
                    "prompt injection alerts",
                ],
            },
            {
                "id": 3,
                "name": "Network SOC + Identity Guardian",
                "status": "planned",
                "outcomes": [
                    "DNS and flow visibility",
                    "beaconing detection",
                    "login anomaly detection",
                    "home lab multi-node support",
                ],
            },
            {
                "id": 4,
                "name": "AI Correlation + Response",
                "status": "planned",
                "outcomes": [
                    "cross-signal investigations",
                    "incident explanations",
                    "guided response actions",
                    "threat hunting queries",
                ],
            },
        ]

    def timeline_recent(self, limit: int = 50):
        return self.timeline.list_recent(limit=limit)

    def list_findings(self) -> List[Dict[str, object]]:
        return [finding.to_dict() for finding in self.findings]

    def list_agents(self) -> List[Dict[str, object]]:
        return list(self.agents.values())

    def list_assets(self) -> List[Dict[str, object]]:
        assets = sorted(
            self.assets.values(),
            key=lambda item: (str(item.get("last_seen", "")), str(item.get("asset_id", ""))),
            reverse=True,
        )
        return assets

    @staticmethod
    def _finding_fingerprint(source: str, title: str, summary: str, risk: str) -> str:
        return "|".join(
            [
                source.strip().lower(),
                title.strip().lower(),
                summary.strip().lower(),
                risk.strip().lower(),
            ]
        )

    @staticmethod
    def _guess_asset_role(open_ports: List[int]) -> str:
        port_roles: List[Tuple[int, str]] = [
            (22, "ssh"),
            (80, "http"),
            (443, "https"),
            (445, "smb"),
            (3389, "rdp"),
            (5432, "postgres"),
            (3306, "mysql"),
            (6379, "redis"),
            (9200, "elasticsearch"),
        ]
        roles = [label for port, label in port_roles if port in open_ports]
        if roles:
            return ",".join(roles[:3])
        return "unknown"

    def _merge_asset(self, asset: Dict[str, object]) -> None:
        asset_id = str(asset.get("asset_id") or "").strip()
        if not asset_id:
            return
        now = datetime.now(timezone.utc).isoformat()
        existing = self.assets.get(asset_id)
        if not existing:
            merged = {**asset, "first_seen": now, "last_seen": now}
            self.assets[asset_id] = merged
            return

        merged = {**existing, **asset}
        merged["first_seen"] = existing.get("first_seen", now)
        merged["last_seen"] = now
        self.assets[asset_id] = merged

    def _ingest_assets_from_agent(
        self,
        agent_id: str,
        hostname: str,
        platform: str,
        telemetry: Dict[str, object],
    ) -> int:
        before = len(self.assets)
        host_discovery = dict(telemetry.get("host_discovery", {}) or {})
        self_ip = str(host_discovery.get("self_ip") or "").strip()
        subnet = str(host_discovery.get("subnet") or "").strip()

        self._merge_asset(
            {
                "asset_id": f"endpoint:{agent_id}",
                "source_agent": agent_id,
                "hostname": hostname,
                "ip": self_ip,
                "platform": platform,
                "role": "endpoint",
                "host_type": str(dict(telemetry.get("virtualization", {}) or {}).get("host_type") or "unknown"),
                "virtualization": str(dict(telemetry.get("virtualization", {}) or {}).get("virtualization") or "unknown"),
                "subnet": subnet,
                "status": "online",
                "open_ports": [],
                "exposure_score": 0,
                "risk_level": "low",
            }
        )

        for item in host_discovery.get("discovered_hosts", []) or []:
            if not isinstance(item, dict):
                continue
            ip = str(item.get("ip") or "").strip()
            if not ip:
                continue
            open_ports_raw = item.get("open_ports", [])
            open_ports = [int(port) for port in open_ports_raw if isinstance(port, int)]
            self._merge_asset(
                {
                    "asset_id": f"host:{ip}",
                    "source_agent": agent_id,
                    "hostname": str(item.get("hostname") or "").strip(),
                    "ip": ip,
                    "platform": "unknown",
                    "role": self._guess_asset_role(open_ports),
                    "host_type": str(item.get("host_type") or "unknown"),
                    "virtualization": "unknown",
                    "os_hint": str(item.get("os_hint") or "unknown"),
                    "os_name": str(item.get("os_name") or "Unknown"),
                    "os_confidence": float(item.get("os_confidence", 0.0) or 0.0),
                    "service_banner": str(item.get("service_banner") or ""),
                    "mac": str(item.get("mac") or ""),
                    "subnet": subnet,
                    "status": str(item.get("status") or "seen"),
                    "open_ports": open_ports,
                    "exposure_score": int(item.get("exposure_score", 0) or 0),
                    "risk_level": str(item.get("risk_level") or "low"),
                }
            )

        return max(0, len(self.assets) - before)

    def _derived_findings(self, agent_id: str, telemetry: Dict[str, object]) -> List[Dict[str, object]]:
        derived: List[Dict[str, object]] = []
        listening_ports = list(telemetry.get("listening_ports", []) or [])
        exposed_admin = []
        risky_ports = {22, 2375, 3306, 5432, 6379, 9200}
        for row in listening_ports:
            if not isinstance(row, dict):
                continue
            ip = str(row.get("ip") or "")
            port = row.get("port")
            if not isinstance(port, int):
                continue
            if port in risky_ports and ip not in {"127.0.0.1", "::1", "localhost"}:
                exposed_admin.append({"ip": ip, "port": port, "pid": row.get("pid")})
        if exposed_admin:
            derived.append(
                {
                    "title": "Administrative service exposed",
                    "summary": f"Detected {len(exposed_admin)} administrative service listener(s) exposed beyond localhost.",
                    "risk": "high",
                    "confidence": 0.8,
                    "tags": ["exposure", "network", "hardening"],
                    "evidence": {"listeners": exposed_admin[:10]},
                }
            )

        discovery = dict(telemetry.get("host_discovery", {}) or {})
        lateral_targets = []
        for host in discovery.get("discovered_hosts", []) or []:
            if not isinstance(host, dict):
                continue
            ports = host.get("open_ports", []) or []
            if any(port in {445, 3389} for port in ports if isinstance(port, int)):
                lateral_targets.append({"ip": host.get("ip"), "open_ports": ports})
        if len(lateral_targets) >= 3:
            derived.append(
                {
                    "title": "Multiple lateral movement surfaces detected",
                    "summary": f"{len(lateral_targets)} hosts expose SMB or RDP on the discovered subnet.",
                    "risk": "medium",
                    "confidence": 0.7,
                    "tags": ["network", "lateral-movement", "asset-discovery"],
                    "evidence": {"hosts": lateral_targets[:12], "subnet": discovery.get("subnet")},
                }
            )

        persistence = dict(telemetry.get("persistence", {}) or {})
        suspicious = []
        for path in (persistence.get("systemd_units", []) or []) + (persistence.get("cron_entries", []) or []):
            raw = str(path).lower()
            if any(token in raw for token in ("tmp", "cache", "wget", "curl", "base64", "python -c", "nc")):
                suspicious.append(path)
        if suspicious:
            derived.append(
                {
                    "title": "Potentially suspicious persistence artifact names",
                    "summary": "One or more systemd/cron persistence artifacts match high-risk naming patterns.",
                    "risk": "medium",
                    "confidence": 0.62,
                    "tags": ["persistence", "linux", "hunting"],
                    "evidence": {"artifacts": suspicious[:15]},
                }
            )

        connections = dict(telemetry.get("connections", {}) or {})
        if int(connections.get("unique_remote_hosts", 0) or 0) >= 40:
            derived.append(
                {
                    "title": "High remote host fan-out",
                    "summary": "Endpoint maintains sessions to a large number of distinct remote hosts.",
                    "risk": "medium",
                    "confidence": 0.58,
                    "tags": ["network", "anomaly", "beaconing"],
                    "evidence": connections,
                }
            )

        return derived

    def add_finding(
        self,
        source: str,
        title: str,
        summary: str,
        risk: str,
        confidence: float = 0.0,
        tags: List[str] | None = None,
        evidence: Dict[str, object] | None = None,
        persist: bool = True,
    ) -> Dict[str, object]:
        fingerprint = self._finding_fingerprint(source=source, title=title, summary=summary, risk=risk)
        now = datetime.now(timezone.utc).isoformat()
        existing = self.finding_index.get(fingerprint)
        if existing:
            existing.confidence = max(existing.confidence, confidence)
            existing.tags = sorted(set(existing.tags + (tags or [])))
            existing.evidence = dict(existing.evidence or {})
            existing.evidence["last_seen"] = now
            existing.evidence["occurrences"] = int(existing.evidence.get("occurrences", 1) or 1) + 1
            self.timeline.add(
                category=source,
                title="Finding repeated",
                detail=f"{title} was observed again.",
                related_finding_id=existing.id,
                risk=risk,
            )
            if persist:
                self._persist_state_to_cache()
            return existing.to_dict()

        enriched_evidence = dict(evidence or {})
        enriched_evidence.setdefault("first_seen", now)
        enriched_evidence["last_seen"] = now
        enriched_evidence.setdefault("occurrences", 1)

        finding = SecurityFinding(
            id=str(uuid4()),
            source=source,
            title=title,
            summary=summary,
            risk=risk,
            confidence=confidence,
            tags=tags or [],
            evidence=enriched_evidence,
        )
        self.findings.insert(0, finding)
        self.finding_index[fingerprint] = finding
        self.timeline.add(
            category=source,
            title=title,
            detail=summary,
            related_finding_id=finding.id,
            risk=risk,
        )
        severity_map = {"critical": 4, "high": 3, "medium": 2, "low": 1}
        bus.emit(
            Event.SECURITY_ANOMALY,
            source=source,
            payload={"finding_id": finding.id, "title": title, "risk": risk},
            severity=severity_map.get(risk, 1),
            requires_speech=risk in ("critical", "high"),
        )
        if persist:
            self._persist_state_to_cache()
        return finding.to_dict()

    def ingest_agent_heartbeat(
        self,
        agent_id: str,
        hostname: str,
        platform: str,
        telemetry: Dict[str, object],
        findings: List[Dict[str, object]] | None = None,
    ) -> Dict[str, object]:
        now = datetime.now(timezone.utc).isoformat()
        first_seen = agent_id not in self.agents
        record = {
            "agent_id": agent_id,
            "hostname": hostname,
            "platform": platform,
            "last_seen": now,
            "telemetry": telemetry,
            "finding_count": len(findings or []),
        }
        self.agents[agent_id] = record

        if first_seen:
            self.timeline.add(
                category="agent",
                title="Security agent registered",
                detail=f"Agent {agent_id} from {hostname} ({platform}) connected to NOVA.",
                agent_id=agent_id,
            )

        new_assets = self._ingest_assets_from_agent(
            agent_id=agent_id,
            hostname=hostname,
            platform=platform,
            telemetry=telemetry,
        )
        if new_assets > 0:
            self.timeline.add(
                category="asset_discovery",
                title="New assets discovered",
                detail=f"{new_assets} newly observed asset(s) added from agent {agent_id}.",
                agent_id=agent_id,
            )

        combined_findings = list(findings or []) + self._derived_findings(agent_id=agent_id, telemetry=telemetry)

        # Layer 1-3 anomaly detection on telemetry
        anomalies = self.anomaly_engine.process_telemetry(
            telemetry,
            context={"hostname": hostname, "platform": platform, "agent_id": agent_id},
        )
        for a in anomalies:
            combined_findings.append({
                "title": a.get("title", "Anomaly detected"),
                "summary": a.get("explanation", f"Metric {a.get('metric', '?')} deviated {a.get('z_score', '?')} sigma from baseline."),
                "risk": a.get("risk", "medium"),
                "confidence": min(1.0, (a.get("z_score", 0) or 0) / 10.0),
                "tags": ["anomaly", f"layer-{a.get('layer', 1)}"],
                "evidence": a,
            })

        for item in combined_findings:
            self.add_finding(
                source=f"agent:{agent_id}",
                title=str(item.get("title", "Remote security finding")),
                summary=str(item.get("summary", "No summary provided.")),
                risk=str(item.get("risk", "medium")),
                confidence=float(item.get("confidence", 0.0) or 0.0),
                tags=list(item.get("tags", []) or []),
                evidence=dict(item.get("evidence", {}) or {}),
                persist=False,
            )

        self._persist_state_to_cache()

        bus.emit(
            Event.SECURITY_HEARTBEAT,
            source=f"agent:{agent_id}",
            payload={"agent_id": agent_id, "hostname": hostname, "finding_count": len(combined_findings)},
            severity=2 if combined_findings else 0,
        )

        return record
