from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Set


def _run_command(command: List[str], timeout: int = 15) -> str:
    try:
        output = subprocess.check_output(
            command,
            text=True,
            timeout=timeout,
            stderr=subprocess.DEVNULL,
            env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C", "LC_ALL": "C"},
        )
        return output
    except Exception:
        return ""


def _collect_os_packages(limit: int = 2000) -> List[Dict[str, Any]]:
    components: List[Dict[str, Any]] = []
    os_name = os.uname().sysname.lower()

    if os_name == "linux":
        dpkg_output = _run_command(["dpkg-query", "-W", "-f=${Package}\t${Version}\t${Architecture}\t${Source}\n"])
        if dpkg_output:
            for line in dpkg_output.splitlines():
                parts = line.split("\t")
                if len(parts) < 2:
                    continue
                name = parts[0].strip()
                version = parts[1].strip()
                arch = parts[2].strip() if len(parts) >= 3 else ""
                source = parts[3].strip() if len(parts) >= 4 else name
                if not name:
                    continue
                purl = f"pkg:deb/{name}@{version}"
                if arch:
                    purl += f"?arch={arch}"
                components.append(
                    {
                        "type": "library",
                        "name": name,
                        "version": version,
                        "purl": purl,
                        "properties": [
                            {"name": "nova:source_package", "value": source},
                            {"name": "nova:package_arch", "value": arch or "unknown"},
                        ],
                    }
                )
                if len(components) >= limit:
                    break

        if not components:
            rpm_output = _run_command(["rpm", "-qa", "--qf", "%{NAME}\t%{VERSION}-%{RELEASE}\t%{ARCH}\n"])
            for line in rpm_output.splitlines()[:limit]:
                parts = line.split("\t")
                if len(parts) < 2:
                    continue
                name = parts[0].strip()
                version = parts[1].strip()
                arch = parts[2].strip() if len(parts) >= 3 else ""
                if not name:
                    continue
                purl = f"pkg:rpm/{name}@{version}"
                if arch:
                    purl += f"?arch={arch}"
                components.append(
                    {
                        "type": "library",
                        "name": name,
                        "version": version,
                        "purl": purl,
                        "properties": [{"name": "nova:package_arch", "value": arch or "unknown"}],
                    }
                )
    return components


def build_cyclonedx_document(components: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": f"urn:uuid:{uuid.uuid4()}",
        "version": 1,
        "metadata": {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "tools": [{"vendor": "NOVA", "name": "nova-security-agent", "version": "0.4.0"}],
        },
        "components": components,
        "vulnerabilities": [],
        "annotations": [
            {
                "subjects": [],
                "text": "VEX store is empty by default; set per component/cve/asset during correlation.",
            }
        ],
    }


def collect_sbom_document() -> Dict[str, Any]:
    syft_path = Path("/usr/local/bin/syft")
    if syft_path.exists():
        try:
            output = subprocess.check_output([str(syft_path), "/", "-o", "cyclonedx-json"], text=True, timeout=120)
            parsed = json.loads(output)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

    components = _collect_os_packages()
    return build_cyclonedx_document(components)


class SbomCollector:
    name = "sbom"
    interval = 21600
    cost = 5
    zones: Set[str] = {"it"}

    def collect(self) -> dict[str, Any]:
        return {"sbom": collect_sbom_document()}
