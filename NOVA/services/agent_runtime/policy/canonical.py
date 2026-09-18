"""Deterministic canonical JSON and action fingerprinting (Constitution I7, 3F).

Every approval token in the system binds an ``action_fingerprint`` computed
here. Two machines (or the same machine at two points in time) MUST agree on
these exact bytes, otherwise a legitimately approved action would be rejected or
— far worse — a subtly different action would be accepted against an old token.
So the rules are fixed, minimal, and covered by a round-trip test:

  - object keys are sorted lexicographically by their NFC-normalized form
  - no insignificant whitespace (separators are exactly "," and ":")
  - every string is Unicode NFC-normalized and encoded UTF-8
  - ``None`` is preserved explicitly as JSON ``null`` and never dropped
  - only JSON-primitive types are accepted; anything else raises (a bug, not
    a value to silently coerce)
  - non-finite floats (NaN, +/-inf) are rejected — they have no canonical form
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from typing import Any


def _normalize(value: Any) -> Any:
    """Recursively NFC-normalize strings and validate the type is canonicalizable."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("non-finite float has no canonical form")
        return value
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, val in value.items():
            if not isinstance(key, str):
                raise TypeError("canonical json requires string object keys")
            out[unicodedata.normalize("NFC", key)] = _normalize(val)
        return out
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    raise TypeError(f"type {type(value).__name__!r} is not canonicalizable")


def canonical_json(obj: Any) -> str:
    """Return the canonical JSON string for ``obj`` (stable across key orderings)."""
    return json.dumps(
        _normalize(obj),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def canonical_bytes(obj: Any) -> bytes:
    """Return the canonical UTF-8 bytes for ``obj``."""
    return canonical_json(obj).encode("utf-8")


def action_fingerprint(
    *,
    tool: str,
    args: dict,
    agent: str,
    task_id: str,
    method: str = "invoke",
) -> str:
    """sha256 hex of the canonicalized exact action, per Constitution I7.

    The fingerprint binds the tool, the method, the *validated structured args*,
    the agent, and the task. If any of these changes by one byte after an
    approval token was issued, the recomputed fingerprint no longer matches and
    the token is invalid.
    """
    payload = {
        "tool": tool,
        "method": method,
        "args": args,
        "agent": agent,
        "task_id": task_id,
    }
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()
