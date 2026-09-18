from __future__ import annotations

import platform
import time
from pathlib import Path
from typing import Any, Dict, Set

import psutil


def parse_cpu_vulnerabilities(base_dir: Path = Path("/sys/devices/system/cpu/vulnerabilities")) -> Dict[str, str]:
    results: Dict[str, str] = {}
    if not base_dir.exists() or not base_dir.is_dir():
        return results
    for item in sorted(base_dir.iterdir()):
        if not item.is_file():
            continue
        try:
            results[item.name] = item.read_text(errors="ignore").strip()[:2000]
        except Exception:
            continue
    return results


def _read_text(path: Path) -> str:
    if not path.exists():
        return "unknown"
    try:
        return path.read_text(errors="ignore").strip() or "unknown"
    except Exception:
        return "unknown"


def collect_hbom() -> Dict[str, Any]:
    dmi = {
        "manufacturer": _read_text(Path("/sys/devices/virtual/dmi/id/sys_vendor")),
        "product": _read_text(Path("/sys/devices/virtual/dmi/id/product_name")),
        "serial": _read_text(Path("/sys/devices/virtual/dmi/id/product_serial")),
        "uuid": _read_text(Path("/sys/devices/virtual/dmi/id/product_uuid")),
        "bios_vendor": _read_text(Path("/sys/devices/virtual/dmi/id/bios_vendor")),
        "bios_version": _read_text(Path("/sys/devices/virtual/dmi/id/bios_version")),
        "bios_date": _read_text(Path("/sys/devices/virtual/dmi/id/bios_date")),
    }

    return {
        "schema": "hbom-lite",
        "generated_at": int(time.time()),
        "platform": platform.platform(),
        "architecture": platform.machine(),
        "cpu_count": psutil.cpu_count(logical=True),
        "memory_total_bytes": int(psutil.virtual_memory().total),
        "dmi": dmi,
        "cpu_vulnerabilities": parse_cpu_vulnerabilities(),
    }


class HbomCollector:
    name = "hbom"
    interval = 604800
    cost = 5
    zones: Set[str] = {"it", "ot"}

    def collect(self) -> dict[str, Any]:
        return {"hbom": collect_hbom()}
