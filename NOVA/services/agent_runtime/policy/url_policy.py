"""Pure SSRF URL policy (resolutions 2C/2D; supports Constitution I14/net.egress).

PURE FUNCTION. No network, no DNS, no disk, no imports beyond the stdlib
(``ipaddress`` / ``urllib.parse``). ``check_url`` has NO caller in Phase 1 by
design — it is the guard a future fetch tool must route through, built and
tested now so the future implementer inherits a proven denial table.

RESOLVE-AND-PIN CONTRACT (2D) — read this before writing any fetch tool.
``check_url`` is necessary but NOT sufficient on its own. Checking a hostname
and then connecting is the exact TOCTOU class of bug that Constitution I7 exists
to prevent: DNS can hand a public IP to the check and a private IP to the
connect (DNS rebinding). A conforming fetch tool MUST:

    1. resolve the hostname to its A/AAAA records
    2. run ``check_url`` on the original URL AND classify EVERY resolved IP
       with ``check_ip``; if any record is denied, abort the whole request
    3. connect to the PINNED resolved IP — never re-resolve for the connection
    4. on every redirect, re-run this entire procedure against the new URL
    5. cap the redirect chain at ``policy.max_redirects`` (default 3)

The hostname-level checks here are a fast fail. The resolved-IP checks (step 2)
are the real guard, because only the pinned IP is what actually gets dialed.
"""

from __future__ import annotations

import ipaddress
import urllib.parse
from dataclasses import dataclass, field
from enum import StrEnum


class UrlReason(StrEnum):
    ALLOWED = "ALLOWED"
    INVALID_URL = "INVALID_URL"
    BAD_SCHEME = "BAD_SCHEME"
    PARSER_CONFUSION = "PARSER_CONFUSION"
    CREDENTIALS_IN_AUTHORITY = "CREDENTIALS_IN_AUTHORITY"
    METADATA_HOST = "METADATA_HOST"
    LOOPBACK = "LOOPBACK"
    LINK_LOCAL = "LINK_LOCAL"
    PRIVATE_RANGE = "PRIVATE_RANGE"
    CGNAT = "CGNAT"
    MULTICAST = "MULTICAST"
    RESERVED = "RESERVED"
    BARE_HOSTNAME = "BARE_HOSTNAME"
    INTERNAL_TLD = "INTERNAL_TLD"
    DOMAIN_NOT_ALLOWED = "DOMAIN_NOT_ALLOWED"


@dataclass(frozen=True)
class UrlPolicy:
    allow_domains: frozenset[str] = field(default_factory=frozenset)
    allowed_schemes: frozenset[str] = field(default_factory=lambda: frozenset({"http", "https"}))
    block_private_ranges: bool = True
    max_redirects: int = 3


@dataclass(frozen=True)
class UrlVerdict:
    allowed: bool
    reason: UrlReason
    host: str | None = None
    detail: str = ""


_METADATA_NAMES = frozenset({"metadata.google.internal", "metadata"})
_INTERNAL_TLDS = (".local", ".internal", ".home.arpa")
_CGNAT = ipaddress.ip_network("100.64.0.0/10")
_ZERO_NET = ipaddress.ip_network("0.0.0.0/8")


def _parse_int_token(tok: str) -> int | None:
    """Parse a single IPv4 component honoring hex (0x), octal (0NNN) and decimal."""
    tok = tok.strip()
    if not tok:
        return None
    try:
        low = tok.lower()
        if low.startswith("0x"):
            return int(tok, 16)
        if tok.startswith("0") and len(tok) > 1:
            return int(tok, 8)
        return int(tok, 10)
    except ValueError:
        return None


def _coerce_ipv4_int(host: str) -> int | None:
    """Handle integer / hex / octal IPv4 spellings (2130706433, 0x7f000001, 0177.0.0.1)."""
    parts = host.split(".")
    if len(parts) == 1:
        val = _parse_int_token(parts[0])
        if val is None or not (0 <= val <= 0xFFFFFFFF):
            return None
        return val
    if len(parts) == 4:
        acc = 0
        for part in parts:
            octet = _parse_int_token(part)
            if octet is None or not (0 <= octet <= 0xFF):
                return None
            acc = (acc << 8) | octet
        return acc
    return None


def _unmap(ip: ipaddress._BaseAddress):
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    return ip


def _coerce_ip(host: str):
    """Return an ip_address for any IP literal spelling, else None (it's a name)."""
    candidate = host.strip()
    if candidate.startswith("[") and candidate.endswith("]"):
        candidate = candidate[1:-1]
    try:
        return _unmap(ipaddress.ip_address(candidate))
    except ValueError:
        pass
    as_int = _coerce_ipv4_int(candidate)
    if as_int is not None:
        return ipaddress.IPv4Address(as_int)
    return None


def check_ip(ip, policy: UrlPolicy | None = None) -> UrlVerdict:
    """Classify a resolved IP address. Used by step 2 of the resolve-and-pin contract."""
    policy = policy or UrlPolicy()
    if isinstance(ip, str):
        parsed = _coerce_ip(ip)
        if parsed is None:
            return UrlVerdict(False, UrlReason.INVALID_URL, ip, "not an ip literal")
        ip = parsed
    reason = _classify_ip(ip, policy)
    if reason is not None:
        return UrlVerdict(False, reason, str(ip), f"ip={ip}")
    return UrlVerdict(True, UrlReason.ALLOWED, str(ip), "public ip")


def _classify_ip(ip, policy: UrlPolicy) -> UrlReason | None:
    if ip.is_loopback or ip.is_unspecified or (ip.version == 4 and ip in _ZERO_NET):
        return UrlReason.LOOPBACK
    if ip.is_link_local:  # 169.254.0.0/16 (incl. 169.254.169.254) and fe80::/10
        return UrlReason.LINK_LOCAL
    if ip in _CGNAT:
        return UrlReason.CGNAT
    if ip.is_multicast:
        return UrlReason.MULTICAST
    # 240.0.0.0/4 reports both is_private and is_reserved; RESERVED is the real reason.
    if ip.is_reserved:
        return UrlReason.RESERVED
    if ip.is_private and policy.block_private_ranges:
        return UrlReason.PRIVATE_RANGE
    return None


def _parser_confusion(netloc: str) -> bool:
    """Detect authorities that two parsers would read differently (I7-class trap)."""
    if "\\" in netloc:
        return True
    if any(ord(c) <= 0x20 or ord(c) == 0x7F for c in netloc):
        return True
    if netloc.count("@") > 1:
        return True
    # first-'@' vs last-'@' userinfo split disagreeing => ambiguous host
    if "@" in netloc and netloc.split("@", 1)[-1] != netloc.rsplit("@", 1)[-1]:
        return True
    return False


def _host_in_domains(host: str, domains: frozenset[str]) -> bool:
    return any(host == d or host.endswith("." + d) for d in domains)


def check_url(url: str, policy: UrlPolicy | None = None) -> UrlVerdict:
    """Return a deny/allow verdict for ``url`` under ``policy``. Pure, no I/O.

    See the module docstring: a passing verdict here does NOT authorize a
    connection on its own — the caller must still resolve-and-pin per 2D.
    """
    policy = policy or UrlPolicy()
    if not isinstance(url, str) or not url.strip():
        return UrlVerdict(False, UrlReason.INVALID_URL, None, "empty url")

    try:
        parts = urllib.parse.urlsplit(url.strip())
    except ValueError as ex:
        return UrlVerdict(False, UrlReason.INVALID_URL, None, str(ex))

    scheme = (parts.scheme or "").lower()
    if scheme not in policy.allowed_schemes:
        return UrlVerdict(False, UrlReason.BAD_SCHEME, None, f"scheme={scheme!r}")

    netloc = parts.netloc
    if _parser_confusion(netloc):
        return UrlVerdict(False, UrlReason.PARSER_CONFUSION, None, f"netloc={netloc!r}")

    try:
        credentialed = "@" in netloc or parts.username is not None
    except ValueError as ex:
        return UrlVerdict(False, UrlReason.INVALID_URL, None, str(ex))
    if credentialed:
        return UrlVerdict(False, UrlReason.CREDENTIALS_IN_AUTHORITY, None, "userinfo present")

    try:
        host = parts.hostname
    except ValueError as ex:
        return UrlVerdict(False, UrlReason.INVALID_URL, None, str(ex))
    if not host:
        return UrlVerdict(False, UrlReason.INVALID_URL, None, "no host")
    host = host.lower()

    if host in _METADATA_NAMES:
        return UrlVerdict(False, UrlReason.METADATA_HOST, host, "cloud metadata endpoint")

    ip = _coerce_ip(host)
    if ip is not None:
        reason = _classify_ip(ip, policy)
        if reason is not None:
            return UrlVerdict(False, reason, host, f"ip={ip}")
        # A public IP literal is not a name; Phase 1 requires names in the allowlist.
        return UrlVerdict(False, UrlReason.DOMAIN_NOT_ALLOWED, host, "raw ip literal not permitted")

    for tld in _INTERNAL_TLDS:
        if host.endswith(tld):
            return UrlVerdict(False, UrlReason.INTERNAL_TLD, host, f"internal tld {tld}")

    if "." not in host:
        return UrlVerdict(False, UrlReason.BARE_HOSTNAME, host, "no dot in host")

    if not policy.allow_domains:
        return UrlVerdict(False, UrlReason.DOMAIN_NOT_ALLOWED, host, "empty allowlist denies all")
    if _host_in_domains(host, policy.allow_domains):
        return UrlVerdict(True, UrlReason.ALLOWED, host, "allowlisted")
    return UrlVerdict(False, UrlReason.DOMAIN_NOT_ALLOWED, host, "not in allowlist")
