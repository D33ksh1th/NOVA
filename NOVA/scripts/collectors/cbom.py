from __future__ import annotations

import hashlib
import os
import re
import stat
import time
from pathlib import Path
from typing import Any, Dict, List, Set

from cryptography import x509
from cryptography.hazmat.primitives import serialization


_CERT_LOCATIONS = [
    Path("/etc/ssl"),
    Path("/etc/pki"),
    Path("/usr/local/share/ca-certificates"),
]

_KEY_LOCATIONS = [
    Path.home() / ".ssh",
    Path("/etc/ssh"),
]


def _safe_text(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9 .,:;_@/+=()-]", "?", value or "")
    return cleaned[:512]


def _file_mode(path: Path) -> str:
    try:
        mode = path.stat().st_mode
        return oct(stat.S_IMODE(mode))
    except Exception:
        return "unknown"


def _is_world_readable(path: Path) -> bool:
    try:
        return bool(path.stat().st_mode & stat.S_IROTH)
    except Exception:
        return False


def inspect_certificate(path: Path) -> Dict[str, Any] | None:
    try:
        blob = path.read_bytes()
    except Exception:
        return None
    try:
        cert = x509.load_pem_x509_certificate(blob)
    except Exception:
        try:
            cert = x509.load_der_x509_certificate(blob)
        except Exception:
            return None

    return {
        "path": str(path),
        "subject": _safe_text(cert.subject.rfc4514_string()),
        "issuer": _safe_text(cert.issuer.rfc4514_string()),
        "serial": hex(cert.serial_number),
        "not_before": cert.not_valid_before_utc.isoformat(),
        "not_after": cert.not_valid_after_utc.isoformat(),
        "signature_algorithm": _safe_text(getattr(cert.signature_algorithm_oid, "_name", "unknown")),
        "self_signed": cert.subject == cert.issuer,
        "world_readable": _is_world_readable(path),
    }


def inspect_key_metadata(path: Path) -> Dict[str, Any] | None:
    try:
        data = path.read_bytes()
    except Exception:
        return None

    # Never emit private key body; only metadata and public fingerprint.
    encrypted = b"ENCRYPTED" in data[:2048]
    fingerprint = hashlib.sha256(data[:2048]).hexdigest()
    key_algorithm = "unknown"
    key_size = 0

    if path.suffix == ".pub":
        try:
            key = serialization.load_ssh_public_key(data)
            key_algorithm = key.__class__.__name__
            if hasattr(key, "key_size"):
                key_size = int(getattr(key, "key_size") or 0)
            pub_bytes = key.public_bytes(
                encoding=serialization.Encoding.OpenSSH,
                format=serialization.PublicFormat.OpenSSH,
            )
            fingerprint = hashlib.sha256(pub_bytes).hexdigest()
        except Exception:
            pass

    return {
        "path": str(path),
        "algorithm": key_algorithm,
        "key_size": key_size,
        "mode": _file_mode(path),
        "encrypted": bool(encrypted),
        "public_fingerprint_sha256": fingerprint,
    }


def collect_cbom() -> Dict[str, Any]:
    certs: List[Dict[str, Any]] = []
    keys: List[Dict[str, Any]] = []

    for root in _CERT_LOCATIONS:
        if not root.exists():
            continue
        for item in root.rglob("*"):
            if not item.is_file() or item.suffix.lower() not in {".crt", ".pem", ".cer"}:
                continue
            cert = inspect_certificate(item)
            if cert:
                certs.append(cert)
            if len(certs) >= 400:
                break

    for root in _KEY_LOCATIONS:
        if not root.exists():
            continue
        for item in root.rglob("*"):
            if not item.is_file():
                continue
            name = item.name.lower()
            if "id_" not in name and "_key" not in name and not name.endswith(".pub"):
                continue
            meta = inspect_key_metadata(item)
            if meta:
                keys.append(meta)
            if len(keys) >= 400:
                break

    return {
        "schema": "cyclonedx-1.6-cryptographic-asset",
        "generated_at": int(time.time()),
        "certificates": certs,
        "keys": keys,
    }


class CbomCollector:
    name = "cbom"
    interval = 86400
    cost = 5
    zones: Set[str] = {"it"}

    def collect(self) -> dict[str, Any]:
        return {"cbom": collect_cbom()}
