from __future__ import annotations

import ipaddress
import json
import os
import socket
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set


@dataclass(slots=True)
class AuthorizationRecord:
    approver: str
    ticket: str
    window_start_epoch: int
    window_end_epoch: int
    auth_ref: str


def _safe_text(value: Any, max_len: int = 256) -> str:
    text = str(value or "")
    cleaned = "".join(ch if ch.isalnum() or ch in " .,:;_@/+=()-[]{}" else "?" for ch in text)
    return cleaned[:max_len]


def _load_auth_record(path: str) -> Optional[AuthorizationRecord]:
    if not path:
        return None
    auth_path = Path(path)
    if not auth_path.exists() or not auth_path.is_file():
        return None
    try:
        payload = json.loads(auth_path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None

    try:
        record = AuthorizationRecord(
            approver=_safe_text(payload.get("approver")),
            ticket=_safe_text(payload.get("ticket")),
            window_start_epoch=int(payload.get("window_start_epoch") or 0),
            window_end_epoch=int(payload.get("window_end_epoch") or 0),
            auth_ref=_safe_text(payload.get("auth_ref") or payload.get("ticket") or ""),
        )
    except Exception:
        return None

    if not record.approver or not record.auth_ref or record.window_start_epoch <= 0 or record.window_end_epoch <= 0:
        return None
    return record


def _is_authorized(record: Optional[AuthorizationRecord], now_epoch: Optional[int] = None) -> bool:
    if record is None:
        return False
    now = int(now_epoch or time.time())
    return record.window_start_epoch <= now <= record.window_end_epoch


def build_modbus_fc43_request(transaction_id: int = 1, unit_id: int = 1) -> bytes:
    tid = int(transaction_id) & 0xFFFF
    uid = int(unit_id) & 0xFF
    # MBAP: transaction-id, protocol-id, length, unit-id
    # PDU: FC 43 (0x2B), MEI type 14 (0x0E), Read Device ID (0x01), Object ID (0x00)
    return bytes(
        [
            (tid >> 8) & 0xFF,
            tid & 0xFF,
            0x00,
            0x00,
            0x00,
            0x06,
            uid,
            0x2B,
            0x0E,
            0x01,
            0x00,
        ]
    )


def probe_modbus_fc43_identity(
    target_ip: str,
    timeout_s: float = 5.0,
    transport_factory: Optional[Callable[[], socket.socket]] = None,
) -> Dict[str, Any]:
    ipaddress.ip_address(target_ip)
    request = build_modbus_fc43_request()
    factory = transport_factory or (lambda: socket.socket(socket.AF_INET, socket.SOCK_STREAM))
    sock = factory()
    sock.settimeout(max(0.2, float(timeout_s)))
    started = time.monotonic()
    try:
        sock.connect((target_ip, 502))
        sock.sendall(request)
        response = sock.recv(1024)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        return {
            "ok": True,
            "protocol": "modbus",
            "primitive": "fc43_mei14",
            "target": target_ip,
            "elapsed_ms": elapsed_ms,
            "request_hex": request.hex(),
            "response_hex": response.hex(),
        }
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        return {
            "ok": False,
            "protocol": "modbus",
            "primitive": "fc43_mei14",
            "target": target_ip,
            "elapsed_ms": elapsed_ms,
            "error": _safe_text(exc),
            "request_hex": request.hex(),
        }
    finally:
        try:
            sock.close()
        except Exception:
            pass


def collect_ot_identity_snapshot(
    targets: List[str],
    audit_probe: Callable[[str, int], None],
    auth_record: Optional[AuthorizationRecord],
    kill_switch: bool,
    latency_breaker_ms: int,
) -> Dict[str, Any]:
    if kill_switch:
        return {
            "mode": "active_halted",
            "reason": "kill_switch",
            "results": [],
            "circuit_breaker_tripped": False,
        }

    if not _is_authorized(auth_record):
        return {
            "mode": "passive_only",
            "reason": "missing_or_expired_authorization",
            "results": [],
            "circuit_breaker_tripped": False,
        }

    results: List[Dict[str, Any]] = []
    circuit_breaker_tripped = False
    for idx, target in enumerate(targets):
        if idx > 0:
            # One connection per device, sequential, >=1s apart.
            time.sleep(1.0)

        try:
            ipaddress.ip_address(target)
        except ValueError:
            continue

        audit_probe(target, 502)
        result = probe_modbus_fc43_identity(target_ip=target, timeout_s=5.0)
        result["auth_ref"] = auth_record.auth_ref if auth_record else ""
        result["approver"] = auth_record.approver if auth_record else ""
        results.append(result)

        if int(result.get("elapsed_ms", 0) or 0) > int(latency_breaker_ms):
            circuit_breaker_tripped = True
            break

    return {
        "mode": "active_identity",
        "results": results,
        "circuit_breaker_tripped": circuit_breaker_tripped,
        "authorization": {
            "auth_ref": auth_record.auth_ref if auth_record else "",
            "approver": auth_record.approver if auth_record else "",
            "ticket": auth_record.ticket if auth_record else "",
        },
    }


class OtCollector:
    name = "ot"
    interval = 900
    cost = 3
    zones: Set[str] = {"ot", "unknown"}

    def __init__(self, targets_fn: Callable[[], List[str]], audit_probe: Callable[[str, int], None]):
        self._targets_fn = targets_fn
        self._audit_probe = audit_probe

    def collect(self) -> dict[str, Any]:
        kill_switch = os.getenv("NOVA_SECURITY_ACTIVE_PROBING_KILL_SWITCH", "false").strip().lower() in {"1", "true", "yes", "on"}
        auth_record = _load_auth_record(os.getenv("NOVA_SECURITY_OT_AUTH_FILE", "").strip())
        latency_breaker_ms = int(os.getenv("NOVA_SECURITY_OT_LATENCY_BREAKER_MS", "2000"))

        targets = self._targets_fn()
        snapshot = collect_ot_identity_snapshot(
            targets=targets,
            audit_probe=self._audit_probe,
            auth_record=auth_record,
            kill_switch=kill_switch,
            latency_breaker_ms=latency_breaker_ms,
        )

        # DNP3 is never actively probed.
        snapshot["dnp3_mode"] = "passive_only"
        return {"ot_identity": snapshot}
