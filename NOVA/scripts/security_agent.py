#!/usr/bin/env python3
from __future__ import annotations

import ipaddress
import hmac
import json
import os
import platform
import re
import socket
import ssl
import subprocess
import sqlite3
import threading
import time
import uuid
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Tuple

import psutil
import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from collectors.scheduler import CollectorScheduler
from collectors.scope import DiscoveryScopeEngine
from collectors.host import (
    HostCollector,
    PassiveDiscoveryCollector,
)
from collectors.sbom import SbomCollector, collect_sbom_document
from collectors.cbom import CbomCollector, collect_cbom
from collectors.hbom import HbomCollector, collect_hbom
from collectors.correlation import correlate_telemetry
from collectors.ot import OtCollector


NOVA_URL = os.getenv("NOVA_SECURITY_URL", "http://127.0.0.1:8000")
AGENT_TOKEN = os.getenv("NOVA_SECURITY_TOKEN", "")
AGENT_ID = os.getenv("NOVA_SECURITY_AGENT_ID", socket.gethostname())
INTERVAL = int(os.getenv("NOVA_SECURITY_INTERVAL", "60"))
TIMEOUT = int(os.getenv("NOVA_SECURITY_TIMEOUT", "15"))
PUSH_ENABLED = os.getenv("NOVA_SECURITY_PUSH_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
PULL_ENABLED = os.getenv("NOVA_SECURITY_PULL_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
PULL_BIND_HOST = os.getenv("NOVA_SECURITY_PULL_HOST", "127.0.0.1")
PULL_BIND_PORT = int(os.getenv("NOVA_SECURITY_PULL_PORT", "8765"))
PULL_TOKEN = os.getenv("NOVA_SECURITY_PULL_TOKEN", AGENT_TOKEN)
SNAPSHOT_CACHE_SECONDS = int(os.getenv("NOVA_SECURITY_SNAPSHOT_CACHE_SECONDS", "10"))
DISCOVERY_ENABLED = os.getenv("NOVA_SECURITY_DISCOVERY", "false").strip().lower() in {"1", "true", "yes", "on"}
DISCOVERY_INTERVAL = int(os.getenv("NOVA_SECURITY_DISCOVERY_INTERVAL", "300"))
DISCOVERY_TIMEOUT = float(os.getenv("NOVA_SECURITY_DISCOVERY_TIMEOUT", "0.2"))
DISCOVERY_MAX_HOSTS = int(os.getenv("NOVA_SECURITY_DISCOVERY_MAX_HOSTS", "256"))
SCAN_ALLOW_CIDRS = [item.strip() for item in os.getenv("SCAN_ALLOW_CIDRS", "").split(",") if item.strip()]
SCAN_DENY_CIDRS = [item.strip() for item in os.getenv("SCAN_DENY_CIDRS", "").split(",") if item.strip()]
ZONE_MAP_RAW = os.getenv("ZONE_MAP", "").strip()
DISCOVERY_REQUESTED_TIER = int(os.getenv("NOVA_SECURITY_DISCOVERY_TIER", "0"))
DISCOVERY_REQUESTED_CONCURRENCY = int(os.getenv("NOVA_SECURITY_DISCOVERY_CONCURRENCY", "32"))
DISCOVERY_REQUESTED_PPS = int(os.getenv("NOVA_SECURITY_DISCOVERY_PPS", "2000"))
ACTIVE_PROBE_AUTH_REF = os.getenv("NOVA_SECURITY_ACTIVE_AUTH_REF", "").strip()
ACTIVE_PROBE_APPROVER = os.getenv("NOVA_SECURITY_ACTIVE_APPROVER", "").strip()
PULL_TLS_CERT_FILE = os.getenv("NOVA_SECURITY_PULL_TLS_CERT_FILE", "").strip()
PULL_TLS_KEY_FILE = os.getenv("NOVA_SECURITY_PULL_TLS_KEY_FILE", "").strip()
PULL_TLS_CA_FILE = os.getenv("NOVA_SECURITY_PULL_TLS_CA_FILE", "").strip()
PULL_TLS_REQUIRE_CLIENT_CERT = os.getenv("NOVA_SECURITY_PULL_TLS_REQUIRE_CLIENT_CERT", "false").strip().lower() in {"1", "true", "yes", "on"}
PUSH_CA_BUNDLE = os.getenv("NOVA_SECURITY_CA_BUNDLE", "").strip()
PUSH_CLIENT_CERT = os.getenv("NOVA_SECURITY_CLIENT_CERT", "").strip()
PUSH_CLIENT_KEY = os.getenv("NOVA_SECURITY_CLIENT_KEY", "").strip()
SIGNING_PRIVATE_KEY_PATH = os.getenv("NOVA_SECURITY_SIGNING_PRIVATE_KEY_PATH", "").strip()
SIGNING_KEY_ID = os.getenv("NOVA_SECURITY_SIGNING_KEY_ID", AGENT_ID).strip() or AGENT_ID
SPOOL_DB_PATH = os.getenv("NOVA_SECURITY_SPOOL_DB", str(Path.home() / ".nova" / "security-agent-spool.db"))
SPOOL_MAX_ROWS = int(os.getenv("NOVA_SECURITY_SPOOL_MAX_ROWS", "5000"))
COLLECTOR_BUDGET = int(os.getenv("NOVA_SECURITY_COLLECTOR_BUDGET", "20"))
COLLECTOR_TIMEOUT_SECONDS = int(os.getenv("NOVA_SECURITY_COLLECTOR_TIMEOUT_SECONDS", "30"))
PROCESS_LIMIT = int(os.getenv("NOVA_SECURITY_PROCESS_LIMIT", "40"))
LISTEN_PORT_LIMIT = int(os.getenv("NOVA_SECURITY_LISTEN_PORT_LIMIT", "40"))
DRIVE_LIMIT = int(os.getenv("NOVA_SECURITY_DRIVE_LIMIT", "30"))
PERSISTENCE_LIMIT = int(os.getenv("NOVA_SECURITY_PERSISTENCE_LIMIT", "80"))
LOGIN_SNAPSHOT_LIMIT = int(os.getenv("NOVA_SECURITY_LOGIN_SNAPSHOT_LIMIT", "20"))
CONNECTION_DETAIL_LIMIT = int(os.getenv("NOVA_SECURITY_CONNECTION_DETAIL_LIMIT", "60"))
PROCESS_INCLUDE_REGEX = os.getenv("NOVA_SECURITY_PROCESS_INCLUDE_REGEX", "").strip()
PROCESS_EXCLUDE_REGEX = os.getenv("NOVA_SECURITY_PROCESS_EXCLUDE_REGEX", "").strip()
LISTEN_PORT_ALLOW = {int(port.strip()) for port in os.getenv("NOVA_SECURITY_LISTEN_PORT_ALLOW", "").split(",") if port.strip().isdigit()}

_DISCOVERY_CACHE: Dict[str, Any] = {"timestamp": 0.0, "data": None}
_SNAPSHOT_CACHE: Dict[str, Any] = {"timestamp": 0.0, "data": None}
_SIGNING_PRIVATE_KEY: Ed25519PrivateKey | None = None
_LAST_BOM_HASHES: Dict[str, str] = {}


def _parse_zone_map(raw: str) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for chunk in (raw or "").split(","):
        item = chunk.strip()
        if not item or "=" not in item:
            continue
        cidr, zone = item.split("=", 1)
        result[cidr.strip()] = zone.strip().lower()
    return result


_SCOPE_ENGINE = DiscoveryScopeEngine(
    allow_cidrs=SCAN_ALLOW_CIDRS,
    deny_cidrs=SCAN_DENY_CIDRS,
    zone_map=_parse_zone_map(ZONE_MAP_RAW),
)

_VIRTUAL_MAC_PREFIXES = {
    "00:05:69",  # VMware
    "00:0c:29",  # VMware
    "00:1c:14",  # VMware
    "00:50:56",  # VMware
    "08:00:27",  # VirtualBox
    "52:54:00",  # QEMU/KVM
    "00:15:5d",  # Hyper-V
    "00:03:ff",  # Microsoft virtual switch
}


def _canonical_json_bytes(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _load_signing_private_key() -> Ed25519PrivateKey:
    global _SIGNING_PRIVATE_KEY
    if _SIGNING_PRIVATE_KEY is not None:
        return _SIGNING_PRIVATE_KEY
    if not SIGNING_PRIVATE_KEY_PATH:
        raise RuntimeError("NOVA_SECURITY_SIGNING_PRIVATE_KEY_PATH is required")
    key_path = Path(SIGNING_PRIVATE_KEY_PATH)
    if not key_path.exists():
        raise RuntimeError(f"signing key not found: {key_path}")
    key_data = key_path.read_bytes()
    private_key = serialization.load_pem_private_key(key_data, password=None)
    if not isinstance(private_key, Ed25519PrivateKey):
        raise RuntimeError("signing key must be Ed25519 PEM private key")
    _SIGNING_PRIVATE_KEY = private_key
    return private_key


def _sign_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    key = _load_signing_private_key()
    signed = dict(payload)
    signed.pop("signature", None)
    signed.pop("signature_key_id", None)
    signature = key.sign(_canonical_json_bytes(signed))
    signed["signature_key_id"] = SIGNING_KEY_ID
    signed["signature"] = signature.hex()
    return signed


class LocalSpool:
    def __init__(self, db_path: str, max_rows: int = 5000):
        self.db_path = Path(db_path)
        self.max_rows = max(100, max_rows)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS heartbeat_spool (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at INTEGER NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS probe_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target TEXT NOT NULL,
                    port INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    auth_ref TEXT NOT NULL,
                    approver TEXT NOT NULL
                )
                """
            )

    def enqueue(self, payload: Dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO heartbeat_spool(created_at, payload) VALUES (?, ?)",
                (int(time.time()), json.dumps(payload, separators=(",", ":"), ensure_ascii=True)),
            )
            conn.execute(
                "DELETE FROM heartbeat_spool WHERE id IN (SELECT id FROM heartbeat_spool ORDER BY id DESC LIMIT -1 OFFSET ?)",
                (self.max_rows,),
            )

    def peek_batch(self, limit: int = 50) -> List[Tuple[int, Dict[str, Any]]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, payload FROM heartbeat_spool ORDER BY id ASC LIMIT ?",
                (max(1, min(limit, 500)),),
            ).fetchall()
        results: List[Tuple[int, Dict[str, Any]]] = []
        for row_id, payload_raw in rows:
            try:
                parsed = json.loads(payload_raw)
                if isinstance(parsed, dict):
                    results.append((int(row_id), parsed))
            except Exception:
                continue
        return results

    def ack(self, row_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM heartbeat_spool WHERE id = ?", (int(row_id),))

    def audit_probe(self, target: str, port: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO probe_audit(target, port, created_at, auth_ref, approver) VALUES (?, ?, ?, ?, ?)",
                (
                    str(target),
                    int(port),
                    int(time.time()),
                    ACTIVE_PROBE_AUTH_REF,
                    ACTIVE_PROBE_APPROVER,
                ),
            )


_SPOOL = LocalSpool(SPOOL_DB_PATH, SPOOL_MAX_ROWS)


def _host_core_telemetry() -> Dict[str, Any]:
    processes = process_inventory(limit=PROCESS_LIMIT)
    ports = listening_ports(limit=LISTEN_PORT_LIMIT)
    drives = mounted_drives(limit=DRIVE_LIMIT)
    persistence = persistence_artifacts(limit=PERSISTENCE_LIMIT)
    logins = login_snapshot(limit=LOGIN_SNAPSHOT_LIMIT)
    connection_detail = established_connections(limit=CONNECTION_DETAIL_LIMIT)
    virtualization = virtualization_profile()
    return {
        "agent_version": "0.4.0",
        "hostname": socket.gethostname(),
        "fqdn": socket.getfqdn(),
        "platform": platform.platform(),
        "virtualization": virtualization,
        "process_count": len(psutil.pids()),
        "boot_time": psutil.boot_time(),
        "load_avg": list(os.getloadavg()) if hasattr(os, "getloadavg") else [],
        "cpu_percent": psutil.cpu_percent(interval=0.5),
        "memory_percent": psutil.virtual_memory().percent,
        "top_processes": processes[:8],
        "processes": processes,
        "listening_ports": ports,
        "mounted_drives": drives,
        "persistence": persistence,
        "packages": package_posture(),
        "login_snapshot": logins,
        "connections": connections_summary(),
        "connection_details": connection_detail,
    }


def _passive_discovery_telemetry() -> Dict[str, Any]:
    return {"host_discovery": host_discovery()}


def _sbom_telemetry() -> Dict[str, Any]:
    return {"sbom": collect_sbom_document()}


def _cbom_telemetry() -> Dict[str, Any]:
    return {"cbom": collect_cbom()}


def _hbom_telemetry() -> Dict[str, Any]:
    return {"hbom": collect_hbom(), "ot_discovery": ot_discovery_profile()}


def _ot_targets() -> List[str]:
    discovery = host_discovery()
    targets: List[str] = []
    for row in discovery.get("discovered_hosts", []) or []:
        if not isinstance(row, dict):
            continue
        ip = str(row.get("ip") or "").strip()
        if not ip:
            continue
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            continue
        zone = _SCOPE_ENGINE.zone_for_ip(ip)
        if zone not in {"ot", "unknown"}:
            continue
        targets.append(ip)
    return targets[:64]


_COLLECTOR_SCHEDULER = CollectorScheduler(
    collectors=[
        HostCollector(collect_fn=_host_core_telemetry),
        PassiveDiscoveryCollector(collect_fn=_passive_discovery_telemetry),
        SbomCollector(),
        CbomCollector(),
        HbomCollector(),
        OtCollector(targets_fn=_ot_targets, audit_probe=_SPOOL.audit_probe),
    ],
    budget=COLLECTOR_BUDGET,
    timeout_seconds=COLLECTOR_TIMEOUT_SECONDS,
)


def _is_pull_request_authorized(provided_token: str) -> bool:
    expected = (PULL_TOKEN or "").strip()
    if not expected:
        return False
    provided = (provided_token or "").strip()
    if not provided:
        return False
    return hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


def _validate_pull_server_config() -> None:
    token = (PULL_TOKEN or "").strip()
    if not token:
        raise RuntimeError("pull API token is required")
    if PULL_BIND_HOST == "0.0.0.0" and not PULL_TLS_CERT_FILE:
        raise RuntimeError("refusing 0.0.0.0 bind without TLS certificate")


def virtualization_profile() -> Dict[str, Any]:
    system = platform.system().lower()
    result = {
        "host_type": "unknown",
        "virtualization": "unknown",
        "detail": "",
    }

    if system != "linux":
        return result

    try:
        output = subprocess.check_output(["systemd-detect-virt"], text=True, timeout=3).strip().lower()
        if output and output != "none":
            result["host_type"] = "virtual"
            result["virtualization"] = output
            result["detail"] = output
            return result
        result["host_type"] = "physical"
        result["virtualization"] = "none"
    except Exception:
        pass

    try:
        product_name = Path("/sys/devices/virtual/dmi/id/product_name")
        if product_name.exists():
            raw = product_name.read_text(errors="ignore").strip().lower()
            if any(token in raw for token in ("kvm", "vmware", "virtualbox", "hyper-v", "qemu", "xen")):
                result["host_type"] = "virtual"
                result["virtualization"] = "dmi-detected"
                result["detail"] = raw[:80]
                return result
    except Exception:
        pass

    return result


def _read_arp_table() -> Dict[str, str]:
    arp: Dict[str, str] = {}
    arp_path = Path("/proc/net/arp")
    if not arp_path.exists():
        return arp
    try:
        for line in arp_path.read_text().splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 4:
                ip = parts[0]
                mac = parts[3].lower()
                if ip and re.match(r"^([0-9a-f]{2}:){5}[0-9a-f]{2}$", mac):
                    arp[ip] = mac
    except Exception:
        return {}
    return arp


def _classify_host_type_from_mac(mac: str) -> str:
    if not mac:
        return "unknown"
    prefix = mac.lower()[0:8]
    if prefix in _VIRTUAL_MAC_PREFIXES:
        return "virtual_likely"
    return "physical_likely"


def _guess_os_hint(open_ports: List[int]) -> str:
    ports = set(open_ports)
    if 3389 in ports and 445 in ports:
        return "windows_likely"
    if 22 in ports and 445 not in ports:
        return "linux_likely"
    if 9100 in ports:
        return "printer_or_embedded"
    return "unknown"


def _host_exposure_score(open_ports: List[int]) -> int:
    weights = {
        22: 8,
        80: 4,
        443: 3,
        445: 16,
        3389: 18,
        3306: 12,
        5432: 12,
        6379: 14,
        9200: 14,
        2375: 20,
        8000: 5,
    }
    score = 0
    for port in open_ports:
        score += int(weights.get(int(port), 2))
    return min(100, score)


def _risk_from_score(score: int) -> str:
    if score >= 45:
        return "high"
    if score >= 20:
        return "medium"
    return "low"


def _resolve_hostname(ip: str) -> str:
    try:
        return socket.gethostbyaddr(ip)[0]
    except Exception:
        return ""


def _grab_banner(ip: str, port: int, payload: bytes = b"", recv_bytes: int = 256) -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(max(0.15, DISCOVERY_TIMEOUT))
    try:
        if sock.connect_ex((ip, port)) != 0:
            return ""
        if payload:
            sock.sendall(payload)
        data = sock.recv(recv_bytes)
        return data.decode("utf-8", errors="ignore").strip()
    except Exception:
        return ""
    finally:
        sock.close()


def _extract_http_server_header(response_text: str) -> str:
    for line in response_text.splitlines():
        if line.lower().startswith("server:"):
            return line.split(":", 1)[1].strip()
    return ""


def _fingerprint_os_name(ip: str, open_ports: List[int], os_hint: str) -> Dict[str, Any]:
    ports = set(open_ports)
    result = {
        "os_name": "Unknown",
        "os_confidence": 0.2,
        "service_banner": "",
    }

    if 3389 in ports and 445 in ports:
        return {"os_name": "Windows", "os_confidence": 0.82, "service_banner": "rdp+smb"}
    if 445 in ports and 139 in ports:
        return {"os_name": "Windows or Samba host", "os_confidence": 0.72, "service_banner": "smb"}

    if 22 in ports:
        banner = _grab_banner(ip, 22)
        if banner:
            lowered = banner.lower()
            if "ubuntu" in lowered:
                return {"os_name": "Ubuntu Linux", "os_confidence": 0.92, "service_banner": banner[:120]}
            if "debian" in lowered:
                return {"os_name": "Debian Linux", "os_confidence": 0.9, "service_banner": banner[:120]}
            if "centos" in lowered:
                return {"os_name": "CentOS Linux", "os_confidence": 0.9, "service_banner": banner[:120]}
            if "alpine" in lowered:
                return {"os_name": "Alpine Linux", "os_confidence": 0.88, "service_banner": banner[:120]}
            if "openssh" in lowered:
                return {"os_name": "Linux/Unix (OpenSSH)", "os_confidence": 0.74, "service_banner": banner[:120]}
            if "dropbear" in lowered:
                return {"os_name": "Embedded Linux (Dropbear)", "os_confidence": 0.81, "service_banner": banner[:120]}

    if 80 in ports:
        response = _grab_banner(ip, 80, payload=b"HEAD / HTTP/1.0\r\nHost: localhost\r\n\r\n", recv_bytes=512)
        server_header = _extract_http_server_header(response)
        if server_header:
            lowered = server_header.lower()
            if "microsoft-iis" in lowered:
                return {"os_name": "Windows Server (IIS)", "os_confidence": 0.86, "service_banner": server_header[:120]}
            if "apache" in lowered or "nginx" in lowered or "caddy" in lowered:
                return {"os_name": "Linux/Unix web host", "os_confidence": 0.62, "service_banner": server_header[:120]}
            return {"os_name": f"HTTP host ({server_header[:40]})", "os_confidence": 0.52, "service_banner": server_header[:120]}

    if os_hint == "linux_likely":
        return {"os_name": "Linux-like host", "os_confidence": 0.6, "service_banner": ""}
    if os_hint == "windows_likely":
        return {"os_name": "Windows-like host", "os_confidence": 0.65, "service_banner": ""}
    if os_hint == "printer_or_embedded":
        return {"os_name": "Printer or embedded device", "os_confidence": 0.7, "service_banner": ""}
    return result


def _compile_regex(pattern: str) -> re.Pattern[str] | None:
    value = (pattern or "").strip()
    if not value:
        return None
    try:
        return re.compile(value, re.IGNORECASE)
    except re.error:
        return None


def process_inventory(limit: int = 40) -> List[Dict[str, Any]]:
    include_re = _compile_regex(PROCESS_INCLUDE_REGEX)
    exclude_re = _compile_regex(PROCESS_EXCLUDE_REGEX)
    rows: List[Dict[str, Any]] = []
    attrs = ["pid", "ppid", "name", "username", "cpu_percent", "memory_percent", "exe", "status", "create_time", "cmdline", "num_threads"]
    for proc in psutil.process_iter(attrs):
        try:
            info = proc.info
            name = str(info.get("name") or "")
            exe = str(info.get("exe") or "")
            cmdline_items = info.get("cmdline") or []
            cmdline = " ".join(str(item) for item in cmdline_items if str(item).strip())
            haystack = " ".join(part for part in (name, exe, cmdline) if part)
            if include_re and not include_re.search(haystack):
                continue
            if exclude_re and exclude_re.search(haystack):
                continue
            rows.append(
                {
                    "pid": info.get("pid"),
                    "ppid": info.get("ppid"),
                    "name": name,
                    "user": info.get("username"),
                    "cpu_percent": round(float(info.get("cpu_percent") or 0.0), 2),
                    "memory_percent": round(float(info.get("memory_percent") or 0.0), 2),
                    "exe": exe,
                    "cmdline": cmdline,
                    "status": str(info.get("status") or ""),
                    "created_at": float(info.get("create_time") or 0.0),
                    "threads": int(info.get("num_threads") or 0),
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    rows.sort(key=lambda item: (item["cpu_percent"], item["memory_percent"]), reverse=True)
    return rows[: max(1, min(limit, 500))]


def top_processes(limit: int = 8) -> List[Dict[str, Any]]:
    return process_inventory(limit=limit)


def listening_ports(limit: int = 20) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    try:
        for conn in psutil.net_connections(kind="inet"):
            if conn.status != psutil.CONN_LISTEN:
                continue
            port = getattr(conn.laddr, "port", None)
            if LISTEN_PORT_ALLOW and int(port or 0) not in LISTEN_PORT_ALLOW:
                continue
            rows.append(
                {
                    "ip": getattr(conn.laddr, "ip", None),
                    "port": port,
                    "pid": conn.pid,
                }
            )
    except Exception:
        return []
    return rows[: max(1, min(limit, 500))]


def mounted_drives(limit: int = 20) -> List[Dict[str, Any]]:
    rows = []
    for part in psutil.disk_partitions(all=False):
        rows.append(
            {
                "device": part.device,
                "mountpoint": part.mountpoint,
                "fstype": part.fstype,
                "opts": part.opts,
            }
        )
    return rows[: max(1, min(limit, 200))]


def persistence_artifacts(limit: int = 30) -> Dict[str, List[str]]:
    system = platform.system().lower()
    result: Dict[str, List[str]] = {
        "launch_agents": [],
        "systemd_units": [],
        "systemd_timers": [],
        "cron_entries": [],
        "autostart_entries": [],
    }

    if system == "darwin":
        roots = [
            Path.home() / "Library" / "LaunchAgents",
            Path("/Library/LaunchAgents"),
            Path("/Library/LaunchDaemons"),
        ]
        items: List[str] = []
        for root in roots:
            if not root.exists():
                continue
            for item in sorted(root.glob("*.plist")):
                items.append(str(item))
                if len(items) >= limit:
                    break
            if len(items) >= limit:
                break
        result["launch_agents"] = items
        return result

    if system == "linux":
        unit_roots = [
            Path("/etc/systemd/system"),
            Path("/lib/systemd/system"),
            Path.home() / ".config" / "systemd" / "user",
        ]
        units: List[str] = []
        for root in unit_roots:
            if not root.exists():
                continue
            for item in sorted(root.glob("*.service")):
                units.append(str(item))
                if len(units) >= limit:
                    break
            if len(units) >= limit:
                break
        result["systemd_units"] = units

        timers: List[str] = []
        for root in unit_roots:
            if not root.exists():
                continue
            for item in sorted(root.glob("*.timer")):
                timers.append(str(item))
                if len(timers) >= limit:
                    break
            if len(timers) >= limit:
                break
        result["systemd_timers"] = timers

        cron_items: List[str] = []
        cron_paths = [
            Path("/etc/crontab"),
            Path("/etc/cron.d"),
            Path("/var/spool/cron"),
            Path("/var/spool/cron/crontabs"),
        ]
        for root in cron_paths:
            if not root.exists():
                continue
            if root.is_file():
                cron_items.append(str(root))
            else:
                for item in sorted(root.iterdir()):
                    cron_items.append(str(item))
                    if len(cron_items) >= limit:
                        break
            if len(cron_items) >= limit:
                break
        result["cron_entries"] = cron_items[:limit]

        autostart_roots = [
            Path("/etc/rc.local"),
            Path("/etc/init.d"),
            Path("/etc/profile.d"),
            Path.home() / ".config" / "autostart",
        ]
        autostart: List[str] = []
        for root in autostart_roots:
            if not root.exists():
                continue
            if root.is_file():
                autostart.append(str(root))
            else:
                for item in sorted(root.iterdir()):
                    autostart.append(str(item))
                    if len(autostart) >= limit:
                        break
            if len(autostart) >= limit:
                break
        result["autostart_entries"] = autostart[:limit]
        return result

    return result


def login_snapshot(limit: int = 10) -> List[str]:
    try:
        output = subprocess.check_output(["who"], text=True, timeout=5)
    except Exception:
        return []
    return [line.strip() for line in output.splitlines() if line.strip()][: max(1, min(limit, 100))]


def established_connections(limit: int = 60) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    try:
        for conn in psutil.net_connections(kind="inet"):
            if conn.status != psutil.CONN_ESTABLISHED:
                continue
            rows.append(
                {
                    "local": f"{getattr(conn.laddr, 'ip', '')}:{getattr(conn.laddr, 'port', '')}",
                    "remote": f"{getattr(conn.raddr, 'ip', '')}:{getattr(conn.raddr, 'port', '')}" if conn.raddr else "",
                    "pid": conn.pid,
                    "family": str(conn.family),
                    "type": str(conn.type),
                    "status": conn.status,
                }
            )
    except Exception:
        return []
    return rows[: max(1, min(limit, 1000))]


def connections_summary() -> Dict[str, Any]:
    established = 0
    remote_hosts = set()
    try:
        for conn in psutil.net_connections(kind="inet"):
            if conn.status != psutil.CONN_ESTABLISHED:
                continue
            established += 1
            if conn.raddr:
                remote_hosts.add(getattr(conn.raddr, "ip", ""))
    except Exception:
        pass
    return {
        "established": established,
        "unique_remote_hosts": len([host for host in remote_hosts if host]),
    }


def package_posture() -> Dict[str, Any]:
    if platform.system().lower() != "linux":
        return {
            "manager": "unsupported",
            "total_packages": 0,
            "upgradable_count": 0,
            "upgradable": [],
        }

    total_packages = 0
    try:
        output = subprocess.check_output(
            ["dpkg-query", "-W", "-f=${binary:Package}\n"],
            text=True,
            timeout=10,
        )
        total_packages = len([line for line in output.splitlines() if line.strip()])
    except Exception:
        total_packages = 0

    upgradable: List[Dict[str, str]] = []
    try:
        output = subprocess.check_output(
            ["apt-get", "-s", "upgrade"],
            text=True,
            timeout=15,
            env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C", "LC_ALL": "C"},
        )
        for line in output.splitlines():
            line = line.strip()
            if not line.startswith("Inst "):
                continue
            parts = line.split()
            package = parts[1].strip() if len(parts) >= 2 else ""
            if not package:
                continue
            upgradable.append({"package": package, "raw": line})
    except Exception:
        pass

    return {
        "manager": "apt/dpkg",
        "total_packages": total_packages,
        "upgradable_count": len(upgradable),
        "upgradable": upgradable[:50],
    }


def _run_command(command: List[str], timeout: int = 10) -> str:
    try:
        output = subprocess.check_output(command, text=True, timeout=timeout, stderr=subprocess.DEVNULL)
        return output.strip()
    except Exception:
        return ""


def software_bom(limit: int = 300) -> Dict[str, Any]:
    components: List[Dict[str, str]] = []
    package_manager = "unknown"

    if platform.system().lower() == "linux":
        dpkg_output = _run_command(["dpkg-query", "-W", "-f=${binary:Package}\t${Version}\n"], timeout=15)
        if dpkg_output:
            package_manager = "dpkg"
            for line in dpkg_output.splitlines():
                parts = line.split("\t", 1)
                if not parts or not parts[0].strip():
                    continue
                name = parts[0].strip()
                version = parts[1].strip() if len(parts) > 1 else "unknown"
                components.append(
                    {
                        "type": "os-package",
                        "name": name,
                        "version": version,
                        "purl": f"pkg:deb/{name}@{version}",
                    }
                )
                if len(components) >= limit:
                    break

        if package_manager == "unknown":
            rpm_output = _run_command(["rpm", "-qa", "--qf", "%{NAME}\t%{VERSION}-%{RELEASE}\n"], timeout=15)
            if rpm_output:
                package_manager = "rpm"
                for line in rpm_output.splitlines():
                    parts = line.split("\t", 1)
                    if not parts or not parts[0].strip():
                        continue
                    name = parts[0].strip()
                    version = parts[1].strip() if len(parts) > 1 else "unknown"
                    components.append(
                        {
                            "type": "os-package",
                            "name": name,
                            "version": version,
                            "purl": f"pkg:rpm/{name}@{version}",
                        }
                    )
                    if len(components) >= limit:
                        break

    pip_freeze = _run_command(["python3", "-m", "pip", "freeze"], timeout=12)
    for line in pip_freeze.splitlines()[:120]:
        line = line.strip()
        if not line or "==" not in line:
            continue
        name, version = line.split("==", 1)
        components.append(
            {
                "type": "python-package",
                "name": name.strip(),
                "version": version.strip(),
                "purl": f"pkg:pypi/{name.strip()}@{version.strip()}",
            }
        )
        if len(components) >= limit:
            break

    return {
        "schema": "cyclonedx-lite",
        "generated_at": int(time.time()),
        "package_manager": package_manager,
        "component_count": len(components),
        "components": components,
    }


def _extract_tls_min_protocol() -> str:
    openssl_cfg_candidates = [
        Path("/etc/ssl/openssl.cnf"),
        Path("/usr/lib/ssl/openssl.cnf"),
        Path("/etc/pki/tls/openssl.cnf"),
    ]
    pattern = re.compile(r"^\s*MinProtocol\s*=\s*(.+)$", re.IGNORECASE)
    for cfg in openssl_cfg_candidates:
        if not cfg.exists():
            continue
        try:
            for line in cfg.read_text(errors="ignore").splitlines():
                match = pattern.match(line)
                if match:
                    return match.group(1).strip()
        except Exception:
            continue
    return "unknown"


def cryptographic_bom() -> Dict[str, Any]:
    openssl_version = _run_command(["openssl", "version"], timeout=5) or "unknown"
    cert_paths = [Path("/etc/ssl/certs"), Path("/usr/local/share/ca-certificates")]
    cert_count = 0
    for base in cert_paths:
        if not base.exists() or not base.is_dir():
            continue
        try:
            cert_count += len([p for p in base.rglob("*") if p.is_file() and p.suffix.lower() in {".crt", ".pem", ".cer"}])
        except Exception:
            continue

    ssh_host_keys = []
    ssh_dir = Path("/etc/ssh")
    if ssh_dir.exists():
        try:
            for item in sorted(ssh_dir.glob("ssh_host_*_key.pub")):
                ssh_host_keys.append(item.name)
        except Exception:
            ssh_host_keys = []

    tls_min_protocol = _extract_tls_min_protocol()
    weak_tls_allowed = tls_min_protocol.lower() in {"sslv3", "tlsv1", "tlsv1.1"}
    return {
        "schema": "cbom-lite",
        "generated_at": int(time.time()),
        "openssl_version": openssl_version,
        "python_ssl": getattr(ssl, "OPENSSL_VERSION", "unknown"),
        "tls_min_protocol": tls_min_protocol,
        "weak_tls_allowed": weak_tls_allowed,
        "cert_inventory_count": cert_count,
        "ssh_host_keys": ssh_host_keys,
    }


def hardware_bom() -> Dict[str, Any]:
    dmi_files = {
        "vendor": Path("/sys/devices/virtual/dmi/id/sys_vendor"),
        "product": Path("/sys/devices/virtual/dmi/id/product_name"),
        "board": Path("/sys/devices/virtual/dmi/id/board_name"),
        "bios_version": Path("/sys/devices/virtual/dmi/id/bios_version"),
    }
    dmi: Dict[str, str] = {}
    for key, path in dmi_files.items():
        if not path.exists():
            dmi[key] = "unknown"
            continue
        try:
            dmi[key] = path.read_text(errors="ignore").strip() or "unknown"
        except Exception:
            dmi[key] = "unknown"

    cpu_model = "unknown"
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.exists():
        try:
            for line in cpuinfo.read_text(errors="ignore").splitlines():
                if line.lower().startswith("model name") and ":" in line:
                    cpu_model = line.split(":", 1)[1].strip()
                    break
        except Exception:
            cpu_model = "unknown"

    interfaces: List[Dict[str, str]] = []
    try:
        for iface, addrs in psutil.net_if_addrs().items():
            mac = ""
            for addr in addrs:
                if getattr(addr, "family", None) == psutil.AF_LINK:
                    mac = str(getattr(addr, "address", "") or "")
                    break
            if mac:
                interfaces.append({"interface": iface, "mac": mac})
    except Exception:
        interfaces = []

    disks = []
    for partition in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(partition.mountpoint)
            disks.append(
                {
                    "mountpoint": partition.mountpoint,
                    "fstype": partition.fstype,
                    "total_bytes": int(usage.total),
                }
            )
        except Exception:
            continue

    return {
        "schema": "hbom-lite",
        "generated_at": int(time.time()),
        "platform": platform.platform(),
        "architecture": platform.machine(),
        "cpu_model": cpu_model,
        "cpu_count": psutil.cpu_count(logical=True),
        "memory_total_bytes": int(psutil.virtual_memory().total),
        "dmi": dmi,
        "interfaces": interfaces,
        "disks": disks,
    }


def ot_discovery_profile() -> Dict[str, Any]:
    cidr_allowlist = [item.strip() for item in os.getenv("NOVA_SECURITY_DISCOVERY_ALLOWLIST", "").split(",") if item.strip()]
    cidr_denylist = [item.strip() for item in os.getenv("NOVA_SECURITY_DISCOVERY_DENYLIST", "").split(",") if item.strip()]
    return {
        "mode": "safe-identity-only",
        "allowlist": cidr_allowlist,
        "denylist": cidr_denylist,
        "protocol_probes": [
            {"protocol": "EtherNet/IP", "port": 44818, "probe": "ListIdentity", "state_mutating": False},
            {"protocol": "BACnet", "port": 47808, "probe": "Who-Is / I-Am", "state_mutating": False},
            {"protocol": "PROFINET", "port": 0, "probe": "DCP Identify", "state_mutating": False},
            {"protocol": "OPC UA", "port": 4840, "probe": "GetEndpoints", "state_mutating": False},
            {"protocol": "Modbus/TCP", "port": 502, "probe": "FC43/MEI Identification", "state_mutating": False},
            {"protocol": "S7comm", "port": 102, "probe": "COTP connect + SZL read", "state_mutating": False},
        ],
    }


def host_enrichment_summary(discovery: Dict[str, Any]) -> Dict[str, Any]:
    hosts = discovery.get("discovered_hosts", []) or []
    if not isinstance(hosts, list):
        hosts = []

    risky = 0
    unknown_hostname = 0
    low_os_confidence = 0
    for host in hosts:
        if not isinstance(host, dict):
            continue
        if str(host.get("risk_level") or "").lower() in {"high", "critical"}:
            risky += 1
        if not str(host.get("hostname") or "").strip():
            unknown_hostname += 1
        if float(host.get("os_confidence", 0.0) or 0.0) < 0.55:
            low_os_confidence += 1

    total_hosts = len(hosts)
    confidence = 0.0
    if total_hosts > 0:
        confidence = round(max(0.0, 1.0 - (low_os_confidence / total_hosts)), 3)

    return {
        "discovered_host_count": total_hosts,
        "risky_host_count": risky,
        "unknown_hostname_count": unknown_hostname,
        "os_fingerprint_confidence": confidence,
    }


def _private_ipv4_interfaces() -> List[Tuple[str, str, str]]:
    results: List[Tuple[str, str, str]] = []
    for iface, addrs in psutil.net_if_addrs().items():
        for addr in addrs:
            if addr.family != socket.AF_INET:
                continue
            ip = getattr(addr, "address", "")
            netmask = getattr(addr, "netmask", "")
            if not ip or ip.startswith("127."):
                continue
            try:
                parsed = ipaddress.ip_address(ip)
            except ValueError:
                continue
            if parsed.is_private:
                results.append((iface, ip, netmask or "255.255.255.0"))
    return results


def _choose_discovery_network() -> Dict[str, Any]:
    if not _SCOPE_ENGINE.has_allow_scope():
        return {"enabled": False, "reason": "missing_scan_allow_cidrs"}

    interfaces = _private_ipv4_interfaces()
    if not interfaces:
        return {"enabled": False, "reason": "no_private_ipv4"}

    iface, ip, netmask = interfaces[0]
    try:
        network = ipaddress.ip_network(f"{ip}/{netmask}", strict=False)
    except ValueError:
        network = ipaddress.ip_network(f"{ip}/24", strict=False)

    if network.num_addresses > DISCOVERY_MAX_HOSTS:
        network = ipaddress.ip_network(f"{ip}/24", strict=False)

    selected_network: ipaddress._BaseNetwork | None = None
    for allowed in _SCOPE_ENGINE.allow_networks:
        if ipaddress.ip_address(ip) in allowed:
            selected_network = allowed
            break
    if selected_network is None:
        return {"enabled": False, "reason": "self_ip_outside_scan_allow_cidrs", "self_ip": ip}

    return {
        "enabled": DISCOVERY_ENABLED,
        "interface": iface,
        "self_ip": ip,
        "subnet": str(selected_network),
        "host_count": max(0, selected_network.num_addresses - 2),
        "network": selected_network,
    }


def _probe_host(ip: str, mac: str = "") -> Dict[str, Any] | None:
    if not _SCOPE_ENGINE.is_allowed(ip):
        return None
    policy = _SCOPE_ENGINE.policy_for_ip(
        target=ip,
        requested_tier=DISCOVERY_REQUESTED_TIER,
        requested_concurrency=DISCOVERY_REQUESTED_CONCURRENCY,
        requested_pps=DISCOVERY_REQUESTED_PPS,
    )
    effective_tier = _SCOPE_ENGINE.effective_tier_for_ip(ip, DISCOVERY_REQUESTED_TIER)
    if effective_tier <= 0:
        return None

    open_ports: List[int] = []
    for port in (22, 80, 135, 139, 443, 445, 3389, 8000):
        _SPOOL.audit_probe(ip, port)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(max(DISCOVERY_TIMEOUT, policy.connect_timeout_s))
        try:
            if sock.connect_ex((ip, port)) == 0:
                open_ports.append(port)
        finally:
            sock.close()

    hostname = ""
    if open_ports:
        hostname = _resolve_hostname(ip)
        exposure_score = _host_exposure_score(open_ports)
        os_hint = _guess_os_hint(open_ports)
        os_fingerprint = _fingerprint_os_name(ip, open_ports, os_hint)
        return {
            "ip": ip,
            "hostname": hostname,
            "mac": mac,
            "host_type": _classify_host_type_from_mac(mac),
            "os_hint": os_hint,
            "os_name": str(os_fingerprint.get("os_name") or "Unknown"),
            "os_confidence": float(os_fingerprint.get("os_confidence", 0.0) or 0.0),
            "service_banner": str(os_fingerprint.get("service_banner") or ""),
            "open_ports": open_ports,
            "exposure_score": exposure_score,
            "risk_level": _risk_from_score(exposure_score),
            "status": "reachable",
            "source": "tcp_probe",
        }
    return None


def host_discovery() -> Dict[str, Any]:
    if not DISCOVERY_ENABLED:
        return {"enabled": False, "discovered_hosts": []}

    if not ACTIVE_PROBE_AUTH_REF or not ACTIVE_PROBE_APPROVER:
        return {
            "enabled": False,
            "reason": "missing_active_probe_authorization",
            "discovered_hosts": [],
        }

    now = time.time()
    if _DISCOVERY_CACHE.get("data") and (now - float(_DISCOVERY_CACHE.get("timestamp", 0.0))) < DISCOVERY_INTERVAL:
        return _DISCOVERY_CACHE["data"]

    plan = _choose_discovery_network()
    network = plan.pop("network", None)
    if not network:
        return plan

    discovered: Dict[str, Dict[str, Any]] = {}
    arp_table = _read_arp_table()
    for ip, mac in arp_table.items():
        if ip == plan["self_ip"]:
            continue
        discovered[ip] = {
            "ip": ip,
            "hostname": _resolve_hostname(ip),
            "mac": mac,
            "host_type": _classify_host_type_from_mac(mac),
            "os_hint": "unknown",
            "os_name": "Unknown",
            "os_confidence": 0.0,
            "service_banner": "",
            "open_ports": [],
            "exposure_score": 0,
            "risk_level": "low",
            "status": "seen",
            "source": "arp",
        }

    hosts_to_probe = [
        str(ip)
        for ip in network.hosts()
        if str(ip) != plan["self_ip"] and _SCOPE_ENGINE.is_allowed(str(ip))
    ]

    self_policy = _SCOPE_ENGINE.policy_for_ip(
        target=plan["self_ip"],
        requested_tier=DISCOVERY_REQUESTED_TIER,
        requested_concurrency=DISCOVERY_REQUESTED_CONCURRENCY,
        requested_pps=DISCOVERY_REQUESTED_PPS,
    )
    with ThreadPoolExecutor(max_workers=self_policy.concurrency) as executor:
        futures = {executor.submit(_probe_host, ip, arp_table.get(ip, "")): ip for ip in hosts_to_probe}
        for future in as_completed(futures):
            try:
                result = future.result()
            except Exception:
                continue
            if result:
                discovered[result["ip"]] = result

    data = {
        **plan,
        "discovered_hosts": sorted(discovered.values(), key=lambda item: tuple(int(x) for x in item["ip"].split("."))),
        "discovered_count": len(discovered),
    }
    _DISCOVERY_CACHE["timestamp"] = now
    _DISCOVERY_CACHE["data"] = data
    return data


def build_findings(telemetry: Dict[str, Any]) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    for proc in telemetry.get("top_processes", []):
        exe = str(proc.get("exe") or "")
        cpu = float(proc.get("cpu_percent") or 0.0)
        if exe.startswith(str(Path.home() / "Downloads")) and cpu >= 40:
            findings.append(
                {
                    "title": "High-CPU process launched from Downloads",
                    "summary": f"{proc.get('name')} (pid {proc.get('pid')}) is running from Downloads with elevated CPU usage.",
                    "risk": "high",
                    "confidence": 0.7,
                    "tags": ["execution", "downloads", "cpu_spike"],
                    "evidence": proc,
                }
            )

    if telemetry.get("connections", {}).get("established", 0) > 60:
        findings.append(
            {
                "title": "Unusually high number of established network connections",
                "summary": "The endpoint currently has a high number of active network sessions.",
                "risk": "medium",
                "confidence": 0.55,
                "tags": ["network", "anomaly"],
                "evidence": telemetry.get("connections", {}),
            }
        )

    package_info = telemetry.get("packages", {})
    upgradable_count = int(package_info.get("upgradable_count", 0) or 0)
    if upgradable_count >= 25:
        risky = []
        for item in package_info.get("upgradable", []):
            package = str(item.get("package", ""))
            if any(keyword in package for keyword in ("openssl", "openssh", "sudo", "linux-image", "curl", "python3")):
                risky.append(package)
        findings.append(
            {
                "title": "Patch backlog detected on host",
                "summary": f"This endpoint has {upgradable_count} pending package upgrades" + (f", including security-relevant packages: {', '.join(risky[:6])}." if risky else "."),
                "risk": "high" if risky else "medium",
                "confidence": 0.8,
                "tags": ["patching", "packages", "ubuntu"],
                "evidence": {
                    "upgradable_count": upgradable_count,
                    "sample_packages": package_info.get("upgradable", [])[:10],
                },
            }
        )

    cbom = telemetry.get("cbom", {}) or {}
    if bool(cbom.get("weak_tls_allowed")):
        findings.append(
            {
                "title": "Weak TLS minimum protocol detected",
                "summary": f"System crypto policy permits legacy protocol floor: {cbom.get('tls_min_protocol', 'unknown')}.",
                "risk": "high",
                "confidence": 0.84,
                "tags": ["crypto", "cbom", "tls"],
                "evidence": {
                    "tls_min_protocol": cbom.get("tls_min_protocol"),
                    "openssl_version": cbom.get("openssl_version"),
                },
            }
        )

    hbom = telemetry.get("hbom", {}) or {}
    dmi = hbom.get("dmi", {}) or {}
    if str(dmi.get("bios_version") or "").strip().lower() in {"", "unknown"}:
        findings.append(
            {
                "title": "Firmware baseline visibility gap",
                "summary": "BIOS or firmware version is unavailable; HBOM posture may be incomplete for this host.",
                "risk": "low",
                "confidence": 0.6,
                "tags": ["hbom", "firmware", "visibility"],
                "evidence": {"dmi": dmi},
            }
        )

    discovery = telemetry.get("host_discovery", {})
    discovered_count = int(discovery.get("discovered_count", 0) or 0)
    if discovered_count >= 20:
        findings.append(
            {
                "title": "Broad local network surface detected",
                "summary": f"The agent discovered {discovered_count} reachable or recently seen hosts on subnet {discovery.get('subnet', 'unknown')}.",
                "risk": "low",
                "confidence": 0.65,
                "tags": ["network", "discovery", "inventory"],
                "evidence": {
                    "subnet": discovery.get("subnet"),
                    "sample_hosts": discovery.get("discovered_hosts", [])[:8],
                },
            }
        )

    risky_hosts = []
    virtual_hosts = 0
    unknown_hosts = 0
    for host in discovery.get("discovered_hosts", []) or []:
        if not isinstance(host, dict):
            continue
        if str(host.get("host_type") or "") == "virtual_likely":
            virtual_hosts += 1
        if not str(host.get("hostname") or "").strip():
            unknown_hosts += 1
        risk_level = str(host.get("risk_level") or "")
        exposure_score = int(host.get("exposure_score", 0) or 0)
        if risk_level in {"high", "critical"} or exposure_score >= 45:
            risky_hosts.append(
                {
                    "ip": host.get("ip"),
                    "open_ports": host.get("open_ports", []),
                    "exposure_score": exposure_score,
                    "risk_level": risk_level or _risk_from_score(exposure_score),
                    "hostname": host.get("hostname"),
                }
            )

    if len(risky_hosts) >= 3:
        findings.append(
            {
                "title": "Multiple high-exposure assets discovered",
                "summary": f"Discovered {len(risky_hosts)} assets with elevated exposure based on open services.",
                "risk": "high",
                "confidence": 0.76,
                "tags": ["asset-discovery", "exposure", "network"],
                "evidence": {"sample_hosts": risky_hosts[:12]},
            }
        )

    if virtual_hosts >= 5:
        findings.append(
            {
                "title": "High virtual host density on subnet",
                "summary": f"{virtual_hosts} discovered hosts appear virtual based on MAC signatures.",
                "risk": "low",
                "confidence": 0.63,
                "tags": ["inventory", "virtualization", "network"],
                "evidence": {"virtual_hosts": virtual_hosts, "subnet": discovery.get("subnet")},
            }
        )

    if unknown_hosts >= max(8, discovered_count // 2):
        findings.append(
            {
                "title": "Large number of unmanaged or unnamed assets",
                "summary": "Many discovered hosts could not be resolved to hostnames, reducing attribution quality.",
                "risk": "medium",
                "confidence": 0.57,
                "tags": ["inventory", "hygiene", "asset-discovery"],
                "evidence": {"unknown_hostname_count": unknown_hosts, "discovered_count": discovered_count},
            }
        )

    low_conf_os = sum(1 for host in discovery.get("discovered_hosts", []) or [] if isinstance(host, dict) and float(host.get("os_confidence", 0.0) or 0.0) < 0.55)
    if discovered_count >= 10 and low_conf_os >= max(5, discovered_count // 2):
        findings.append(
            {
                "title": "OS fingerprint confidence is low for many assets",
                "summary": "A large part of the subnet did not expose enough banner data for high-confidence OS identification.",
                "risk": "low",
                "confidence": 0.52,
                "tags": ["asset-discovery", "os-fingerprinting", "visibility"],
                "evidence": {"low_confidence_hosts": low_conf_os, "discovered_count": discovered_count},
            }
        )

    correlation = telemetry.get("correlation", {})
    queue = []
    if isinstance(correlation, dict):
        queue = correlation.get("queue", []) or []
    if isinstance(queue, list) and queue:
        findings.append(
            {
                "title": "Prioritized vulnerability work queue generated",
                "summary": f"Correlation selected {len(queue)} high-priority items using KEV/EPSS + reachability + cross-zone exposure.",
                "risk": "high",
                "confidence": 0.89,
                "tags": ["correlation", "kev", "epss", "prioritization"],
                "evidence": {"queue_preview": queue[:20]},
            }
        )

    return findings


def _hash_json(value: Dict[str, Any]) -> str:
    import hashlib

    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _apply_bom_hash_diff(telemetry: Dict[str, Any]) -> Dict[str, Any]:
    bom_hashes: Dict[str, str] = {}
    bom_documents: Dict[str, Any] = {}
    for key in ("sbom", "cbom", "hbom"):
        value = telemetry.get(key)
        if not isinstance(value, dict):
            continue
        digest = _hash_json(value)
        bom_hashes[key] = digest
        if _LAST_BOM_HASHES.get(key) != digest:
            bom_documents[key] = value
            _LAST_BOM_HASHES[key] = digest
        else:
            telemetry[key] = {"hash": digest, "deferred": True}

    telemetry["bom_hashes"] = bom_hashes
    if bom_documents:
        telemetry["bom_documents"] = bom_documents
    return telemetry


def collect_telemetry() -> Dict[str, Any]:
    _COLLECTOR_SCHEDULER.collect_due()
    telemetry = _COLLECTOR_SCHEDULER.latest_payload()
    discovery = dict(telemetry.get("passive_discovery", {}) or {}).get("host_discovery", {})
    if "host_discovery" not in telemetry and isinstance(discovery, dict):
        telemetry["host_discovery"] = discovery
    if isinstance(discovery, dict):
        telemetry["host_enrichment"] = host_enrichment_summary(discovery)

    for collector_name in ("host", "passive_discovery", "sbom", "cbom", "hbom"):
        block = telemetry.pop(collector_name, None)
        if not isinstance(block, dict):
            continue
        telemetry.update(block)

    telemetry["correlation"] = correlate_telemetry(telemetry)

    return _apply_bom_hash_diff(telemetry)


def build_snapshot_payload() -> Dict[str, Any]:
    now = time.time()
    cached = _SNAPSHOT_CACHE.get("data")
    if cached and (now - float(_SNAPSHOT_CACHE.get("timestamp", 0.0))) < SNAPSHOT_CACHE_SECONDS:
        return cached

    telemetry = collect_telemetry()
    findings = build_findings(telemetry)
    payload = {
        "agent_id": AGENT_ID,
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "sent_at": int(time.time()),
        "nonce": str(uuid.uuid4()),
        "telemetry": telemetry,
        "findings": findings,
    }
    payload = _sign_payload(payload)
    _SNAPSHOT_CACHE["timestamp"] = now
    _SNAPSHOT_CACHE["data"] = payload
    return payload


class _SnapshotHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        return

    def _write_json(self, payload: Dict[str, Any], status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _is_authorized(self) -> bool:
        return _is_pull_request_authorized(self.headers.get("X-Nova-Agent-Token", ""))

    def do_GET(self) -> None:
        if self.path not in {"/health", "/security/agent/snapshot"}:
            self._write_json({"ok": False, "error": "not_found"}, status=HTTPStatus.NOT_FOUND)
            return
        if self.path == "/health":
            self._write_json({"ok": True, "agent_id": AGENT_ID})
            return
        if not self._is_authorized():
            self._write_json({"ok": False, "error": "unauthorized"}, status=HTTPStatus.UNAUTHORIZED)
            return
        self._write_json(build_snapshot_payload())


def _start_pull_server() -> ThreadingHTTPServer:
    _validate_pull_server_config()

    server = ThreadingHTTPServer((PULL_BIND_HOST, PULL_BIND_PORT), _SnapshotHandler)
    if PULL_TLS_CERT_FILE:
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        context.load_cert_chain(certfile=PULL_TLS_CERT_FILE, keyfile=PULL_TLS_KEY_FILE or None)
        if PULL_TLS_CA_FILE:
            context.load_verify_locations(cafile=PULL_TLS_CA_FILE)
        if PULL_TLS_REQUIRE_CLIENT_CERT:
            context.verify_mode = ssl.CERT_REQUIRED
        server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, name="security-agent-pull-api", daemon=True)
    thread.start()
    scheme = "https" if PULL_TLS_CERT_FILE else "http"
    print(
        json.dumps(
            {
                "ok": True,
                "agent_id": AGENT_ID,
                "pull_api": f"{scheme}://{PULL_BIND_HOST}:{PULL_BIND_PORT}/security/agent/snapshot",
                "message": "pull API enabled",
            }
        )
    )
    return server


def post_heartbeat(session: requests.Session, payload: Dict[str, Any] | None = None) -> None:
    payload = payload or build_snapshot_payload()
    findings = payload.get("findings", [])
    headers = {"Content-Type": "application/json"}
    if AGENT_TOKEN:
        headers["X-Nova-Agent-Token"] = AGENT_TOKEN

    response = session.post(
        f"{NOVA_URL.rstrip('/')}/security/agents/heartbeat",
        headers=headers,
        json=payload,
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    print(json.dumps({"ok": True, "agent_id": AGENT_ID, "findings": len(findings)}))


def _replay_spool(session: requests.Session) -> int:
    sent = 0
    for row_id, payload in _SPOOL.peek_batch(limit=50):
        post_heartbeat(session, payload=payload)
        _SPOOL.ack(row_id)
        sent += 1
    return sent


def _configure_push_tls(session: requests.Session) -> None:
    url = NOVA_URL.rstrip("/")
    if not url.lower().startswith("https://"):
        raise RuntimeError("NOVA_SECURITY_URL must use HTTPS")
    if not PUSH_CA_BUNDLE:
        raise RuntimeError("NOVA_SECURITY_CA_BUNDLE is required")
    if not Path(PUSH_CA_BUNDLE).exists():
        raise RuntimeError(f"CA bundle not found: {PUSH_CA_BUNDLE}")
    session.verify = PUSH_CA_BUNDLE
    if PUSH_CLIENT_CERT and PUSH_CLIENT_KEY:
        session.cert = (PUSH_CLIENT_CERT, PUSH_CLIENT_KEY)


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--snapshot", action="store_true", help="Print a single JSON snapshot and exit (used by NOVA local scan).")
    args, _ = parser.parse_known_args()

    if args.snapshot:
        # Used by SecurityCenter.local_scan() — collect once, print, exit.
        payload = build_snapshot_payload()
        print(json.dumps(payload))
        return 0

    server = None
    if PULL_ENABLED:
        try:
            server = _start_pull_server()
        except Exception as exc:
            print(json.dumps({"ok": False, "agent_id": AGENT_ID, "error": f"pull_api_start_failed: {exc}"}))
            if not PUSH_ENABLED:
                return 1

    if not PUSH_ENABLED:
        if not server:
            print(json.dumps({"ok": False, "agent_id": AGENT_ID, "error": "both push and pull are disabled"}))
            return 1
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            return 0

    session = requests.Session()
    if PUSH_ENABLED:
        _configure_push_tls(session)
    while True:
        try:
            _replay_spool(session)
            post_heartbeat(session)
        except KeyboardInterrupt:
            return 0
        except Exception as exc:
            try:
                _SPOOL.enqueue(build_snapshot_payload())
            except Exception:
                pass
            print(json.dumps({"ok": False, "agent_id": AGENT_ID, "error": str(exc)}))
        time.sleep(INTERVAL)


if __name__ == "__main__":
    raise SystemExit(main())
