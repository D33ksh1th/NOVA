from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_prioritization_uses_kev_union_epss_with_reachability_and_cross_zone():
    module = _load_module(
        Path(__file__).resolve().parents[1] / "scripts" / "collectors" / "correlation.py",
        "collector_correlation_module",
    )

    candidates = [
        {
            "vuln_id": "CVE-2026-0001",
            "asset": "host-a",
            "component": "openssl",
            "severity": "high",
            "reachable": True,
            "cross_zone_exposed": True,
        },
        {
            "vuln_id": "CVE-2026-0002",
            "asset": "host-b",
            "component": "curl",
            "severity": "high",
            "reachable": True,
            "cross_zone_exposed": True,
            "epss": 0.2,
        },
        {
            "vuln_id": "CVE-2026-0003",
            "asset": "host-c",
            "component": "zlib",
            "severity": "medium",
            "reachable": False,
            "cross_zone_exposed": True,
            "epss": 0.9,
        },
    ]

    queue = module.prioritize_queue(
        candidates,
        kev_ids={"CVE-2026-0001"},
        epss_scores={"CVE-2026-0002": 0.2, "CVE-2026-0003": 0.9},
    )

    ids = [row.vuln_id for row in queue]
    assert "CVE-2026-0001" in ids
    assert "CVE-2026-0002" in ids
    assert "CVE-2026-0003" not in ids


def test_correlate_telemetry_loads_local_mirrors(tmp_path: Path):
    module = _load_module(
        Path(__file__).resolve().parents[1] / "scripts" / "collectors" / "correlation.py",
        "collector_correlation_module_2",
    )

    kev_file = tmp_path / "kev.json"
    kev_file.write_text(json.dumps({"vulnerabilities": [{"cveID": "CVE-2026-1111"}]}))

    epss_file = tmp_path / "epss.json"
    epss_file.write_text(json.dumps({"scores": [{"cve": "CVE-2026-2222", "epss": 0.42}]}))

    os.environ["NOVA_SECURITY_KEV_MIRROR"] = str(kev_file)
    os.environ["NOVA_SECURITY_EPSS_MIRROR"] = str(epss_file)

    telemetry = {
        "hostname": "edge-host",
        "vuln_candidates": [
            {
                "vuln_id": "CVE-2026-1111",
                "asset": "edge-host",
                "component": "libssl",
                "severity": "high",
                "reachable": True,
                "cross_zone_exposed": True,
            },
            {
                "vuln_id": "CVE-2026-2222",
                "asset": "edge-host",
                "component": "libcurl",
                "severity": "high",
                "reachable": True,
                "cross_zone_exposed": True,
            },
        ],
    }

    result = module.correlate_telemetry(telemetry)
    assert result["queue_size"] == 2
