"""
Event envelope — validated at publish and consume.

Every event in Nova flows through this schema.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Optional

from pydantic import BaseModel, Field


def _ulid_like() -> str:
    ts = int(time.time() * 1000)
    rand = uuid.uuid4().hex[:20]
    return f"{ts:012x}-{rand}"


class EventEnvelope(BaseModel):
    id: str = Field(default_factory=_ulid_like)
    source: str
    type: str
    ts: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()))
    severity: int = Field(default=0, ge=0, le=4)
    payload: Any = None
    requires_speech: bool = False
    correlation_id: Optional[str] = None

    model_config = {"frozen": False, "extra": "forbid"}
