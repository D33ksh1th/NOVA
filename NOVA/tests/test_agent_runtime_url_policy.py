"""Table-driven SSRF vector tests for the pure URL policy (2C/2F)."""

import pytest

from services.agent_runtime.policy.url_policy import (
    UrlPolicy,
    UrlReason,
    check_ip,
    check_url,
)

# (url, expected_reason) — every entry must be DENIED with the given reason.
DENY_VECTORS = [
    # non-http(s) schemes
    ("file:///etc/passwd", UrlReason.BAD_SCHEME),
    ("gopher://evil/", UrlReason.BAD_SCHEME),
    ("ftp://host/x", UrlReason.BAD_SCHEME),
    ("data:text/plain,hello", UrlReason.BAD_SCHEME),
    ("jar:http://x!/a", UrlReason.BAD_SCHEME),
    ("dict://host:2628/", UrlReason.BAD_SCHEME),
    # loopback (and integer/octal/hex/mapped spellings)
    ("http://127.0.0.1/", UrlReason.LOOPBACK),
    ("http://127.0.0.5/", UrlReason.LOOPBACK),
    ("http://[::1]/", UrlReason.LOOPBACK),
    ("http://0.0.0.0/", UrlReason.LOOPBACK),
    ("http://0x7f000001/", UrlReason.LOOPBACK),
    ("http://2130706433/", UrlReason.LOOPBACK),
    ("http://0177.0.0.1/", UrlReason.LOOPBACK),
    ("http://[::ffff:127.0.0.1]/", UrlReason.LOOPBACK),
    # link-local / metadata
    ("http://169.254.169.254/latest/meta-data/", UrlReason.LINK_LOCAL),
    ("http://169.254.1.1/", UrlReason.LINK_LOCAL),
    ("http://[fe80::1]/", UrlReason.LINK_LOCAL),
    ("http://metadata.google.internal/", UrlReason.METADATA_HOST),
    # private ranges
    ("http://10.0.0.1/", UrlReason.PRIVATE_RANGE),
    ("http://172.16.0.1/", UrlReason.PRIVATE_RANGE),
    ("http://192.168.1.1/", UrlReason.PRIVATE_RANGE),
    ("http://[fd00::1]/", UrlReason.PRIVATE_RANGE),
    # CGNAT / multicast / reserved
    ("http://100.64.0.1/", UrlReason.CGNAT),
    ("http://224.0.0.1/", UrlReason.MULTICAST),
    ("http://240.0.0.1/", UrlReason.RESERVED),
    # internal TLDs / bare hostnames
    ("http://printer.local/", UrlReason.INTERNAL_TLD),
    ("http://svc.internal/", UrlReason.INTERNAL_TLD),
    ("http://foo.home.arpa/", UrlReason.INTERNAL_TLD),
    ("http://localhost/", UrlReason.BARE_HOSTNAME),
    ("http://intranet/", UrlReason.BARE_HOSTNAME),
    # credentials in authority
    ("http://user:pass@example.com/", UrlReason.CREDENTIALS_IN_AUTHORITY),
    ("http://127.0.0.1@evil.com/", UrlReason.CREDENTIALS_IN_AUTHORITY),
    # parser confusion
    ("http://evil.com@@127.0.0.1/", UrlReason.PARSER_CONFUSION),
    ("http://foo@bar@127.0.0.1/", UrlReason.PARSER_CONFUSION),
    ("http://example.com\\@127.0.0.1/", UrlReason.PARSER_CONFUSION),
    ("http://example.com /path", UrlReason.PARSER_CONFUSION),
    # public IP literal is not a name
    ("http://8.8.8.8/", UrlReason.DOMAIN_NOT_ALLOWED),
]


@pytest.mark.parametrize("url,reason", DENY_VECTORS)
def test_deny_vectors(url, reason):
    verdict = check_url(url)
    assert verdict.allowed is False, f"{url} should be denied"
    assert verdict.reason == reason, f"{url}: expected {reason}, got {verdict.reason}"


def test_empty_allowlist_denies_public_name():
    v = check_url("https://example.com/")
    assert v.allowed is False
    assert v.reason == UrlReason.DOMAIN_NOT_ALLOWED


def test_allowlist_permits_domain_and_subdomains():
    policy = UrlPolicy(allow_domains=frozenset({"example.com"}))
    assert check_url("http://example.com/", policy).allowed is True
    assert check_url("https://www.example.com/path", policy).allowed is True
    assert check_url("http://a.b.example.com/", policy).allowed is True


def test_allowlist_rejects_unrelated_and_suffix_tricks():
    policy = UrlPolicy(allow_domains=frozenset({"example.com"}))
    assert check_url("http://notexample.com/", policy).allowed is False
    assert check_url("http://example.com.evil.com/", policy).allowed is False


def test_check_ip_direct():
    assert check_ip("127.0.0.1").reason == UrlReason.LOOPBACK
    assert check_ip("169.254.169.254").reason == UrlReason.LINK_LOCAL
    assert check_ip("10.1.2.3").reason == UrlReason.PRIVATE_RANGE
    assert check_ip("8.8.8.8").allowed is True
