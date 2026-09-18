from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Set


@dataclass(slots=True)
class CorrelationRecord:
    vuln_id: str
    asset: str
    component: str
    severity: str
    reachable: bool
    cross_zone_exposed: bool
    epss: float
    kev: bool


def _safe_text(value: Any, max_len: int = 256) -> str:
    text = str(value or "")
    cleaned = "".join(ch if ch.isalnum() or ch in " .,:;_@/+=()-[]{}" else "?" for ch in text)
    return cleaned[:max_len]


def _load_json(path: str) -> Any:
    if not path:
        return None
    file_path = Path(path)
    if not file_path.exists() or not file_path.is_file():
        return None
    try:
        return json.loads(file_path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return None


def load_kev_ids(path: str) -> Set[str]:
    payload = _load_json(path)
    if isinstance(payload, dict) and isinstance(payload.get("vulnerabilities"), list):
        ids = set()
        for item in payload["vulnerabilities"]:
            if not isinstance(item, dict):
                continue
            cve = _safe_text(item.get("cveID") or item.get("cve") or "")
            if cve:
                ids.add(cve.upper())
        return ids
    if isinstance(payload, list):
        return {_safe_text(item).upper() for item in payload if str(item).strip()}
    return set()


def load_epss_scores(path: str) -> Dict[str, float]:
    payload = _load_json(path)
    scores: Dict[str, float] = {}
    if isinstance(payload, dict):
        rows = payload.get("scores")
        if isinstance(rows, list):
            for item in rows:
                if not isinstance(item, dict):
                    continue
                vuln_id = _safe_text(item.get("cve") or item.get("id") or "").upper()
                try:
                    score = float(item.get("epss", 0.0) or 0.0)
                except Exception:
                    score = 0.0
                if vuln_id:
                    scores[vuln_id] = score
        else:
            for key, value in payload.items():
                vuln_id = _safe_text(key).upper()
                try:
                    scores[vuln_id] = float(value)
                except Exception:
                    scores[vuln_id] = 0.0
    return scores


def _extract_candidates_from_sbom(telemetry: Dict[str, Any]) -> List[Dict[str, Any]]:
    sbom = telemetry.get("sbom")
    if not isinstance(sbom, dict):
        return []
    vulnerabilities = sbom.get("vulnerabilities", [])
    components = sbom.get("components", [])
    if not isinstance(vulnerabilities, list):
        return []

    component_by_ref: Dict[str, Dict[str, Any]] = {}
    if isinstance(components, list):
        for item in components:
            if not isinstance(item, dict):
                continue
            ref = str(item.get("bom-ref") or item.get("purl") or "").strip()
            if ref:
                component_by_ref[ref] = item

    candidates: List[Dict[str, Any]] = []
    for vuln in vulnerabilities:
        if not isinstance(vuln, dict):
            continue
        vuln_id = _safe_text(vuln.get("id") or "").upper()
        if not vuln_id:
            continue

        affects = vuln.get("affects", [])
        affected_refs = []
        if isinstance(affects, list):
            for row in affects:
                if isinstance(row, dict):
                    ref = str(row.get("ref") or "").strip()
                    if ref:
                        affected_refs.append(ref)

        if not affected_refs:
            affected_refs = [""]

        for ref in affected_refs:
            component = component_by_ref.get(ref, {}) if ref else {}
            component_name = _safe_text(component.get("name") or ref or "unknown")
            props = component.get("properties", []) if isinstance(component, dict) else []
            reachable = False
            cross_zone_exposed = False
            if isinstance(props, list):
                for prop in props:
                    if not isinstance(prop, dict):
                        continue
                    key = str(prop.get("name") or "")
                    value = str(prop.get("value") or "").lower()
                    if key == "nova:reachable_off_host" and value == "true":
                        reachable = True
                    if key == "nova:cross_zone_exposed" and value == "true":
                        cross_zone_exposed = True

            ratings = vuln.get("ratings", [])
            severity = "unknown"
            if isinstance(ratings, list) and ratings:
                first = ratings[0]
                if isinstance(first, dict):
                    severity = _safe_text(first.get("severity") or "unknown").lower()

            candidates.append(
                {
                    "vuln_id": vuln_id,
                    "asset": _safe_text(telemetry.get("hostname") or telemetry.get("fqdn") or "endpoint"),
                    "component": component_name,
                    "severity": severity,
                    "reachable": reachable,
                    "cross_zone_exposed": cross_zone_exposed,
                }
            )
    return candidates


def prioritize_queue(candidates: List[Dict[str, Any]], kev_ids: Set[str], epss_scores: Dict[str, float]) -> List[CorrelationRecord]:
    queue: List[CorrelationRecord] = []
    for item in candidates:
        vuln_id = _safe_text(item.get("vuln_id") or "").upper()
        if not vuln_id:
            continue

        reachable = bool(item.get("reachable"))
        cross_zone_exposed = bool(item.get("cross_zone_exposed"))
        epss = float(epss_scores.get(vuln_id, item.get("epss", 0.0) or 0.0))
        kev = vuln_id in kev_ids

        if not reachable or not cross_zone_exposed:
            continue
        if not kev and epss <= 0.1:
            continue

        queue.append(
            CorrelationRecord(
                vuln_id=vuln_id,
                asset=_safe_text(item.get("asset") or "endpoint"),
                component=_safe_text(item.get("component") or "unknown"),
                severity=_safe_text(item.get("severity") or "unknown"),
                reachable=reachable,
                cross_zone_exposed=cross_zone_exposed,
                epss=epss,
                kev=kev,
            )
        )

    queue.sort(key=lambda row: (not row.kev, -row.epss, row.vuln_id))
    return queue


def correlate_telemetry(telemetry: Dict[str, Any]) -> Dict[str, Any]:
    kev_ids = load_kev_ids(os.getenv("NOVA_SECURITY_KEV_MIRROR", ""))
    epss_scores = load_epss_scores(os.getenv("NOVA_SECURITY_EPSS_MIRROR", ""))
    candidates = _extract_candidates_from_sbom(telemetry)

    extra_candidates = telemetry.get("vuln_candidates")
    if isinstance(extra_candidates, list):
        for item in extra_candidates:
            if isinstance(item, dict):
                candidates.append(item)

    queue = prioritize_queue(candidates, kev_ids=kev_ids, epss_scores=epss_scores)
    return {
        "queue_size": len(queue),
        "queue": [
            {
                "vuln_id": row.vuln_id,
                "asset": row.asset,
                "component": row.component,
                "severity": row.severity,
                "reachable": row.reachable,
                "cross_zone_exposed": row.cross_zone_exposed,
                "epss": row.epss,
                "kev": row.kev,
            }
            for row in queue[:100]
        ],
    }
