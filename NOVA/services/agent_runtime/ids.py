"""Time-ordered unique ids (UUIDv7-style) for tasks, events, and evidence.

RFC 9562 v7 layout is not in the stdlib yet, so we build a compact, sortable id:
48-bit millisecond timestamp + 74 bits of randomness. Good enough for ordering
and uniqueness within the runtime; not a security token.
"""

from __future__ import annotations

import os
import time


def uuid7_hex() -> str:
    ms = int(time.time() * 1000) & 0xFFFFFFFFFFFF
    rand = int.from_bytes(os.urandom(10), "big")
    value = (ms << 80) | rand
    return f"{value:032x}"


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid7_hex()}"
