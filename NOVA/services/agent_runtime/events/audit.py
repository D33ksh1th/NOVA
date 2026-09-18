"""Hash-chained events with optional fsync-backed JSONL storage.

Disk operations are awaited outside the event loop. Damaged logs are never
repaired silently. Retain a trusted head hash externally to detect truncation
or replacement of an otherwise valid chain; hashing alone is not a signature.
"""

from __future__ import annotations

import asyncio
import copy
from dataclasses import asdict, dataclass, replace
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Callable, TypeVar

from services.agent_runtime.contracts.event import AgentEvent, EventType, Severity
from services.agent_runtime.events.journal import Journal, MAX_RECORD_BYTES
from services.agent_runtime.policy.canonical import canonical_bytes, canonical_json

_GENESIS = "0" * 64
_REDACTED = "[REDACTED]"
_SENSITIVE_FIELDS = frozenset({
    "password", "passwd", "secret", "clientsecret", "apikey", "accesstoken",
    "refreshtoken", "token", "authorization", "proxyauthorization", "privatekey",
    "awssecretaccesskey", "cookie", "setcookie",
})
_SECRET_PATTERNS = [
    re.compile(r"-----BEGIN ([A-Z ]*PRIVATE KEY)-----.*?-----END \1-----", re.DOTALL),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*", re.DOTALL),
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"AIza[0-9A-Za-z_-]{35}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),
    re.compile(r"(?i)\b(?:bearer|basic)\s+[A-Za-z0-9._+/=-]+"),
    re.compile(r"(?i)\b(?:api[_-]?key|password|client[_-]?secret|access[_-]?token)\s*[=:]\s*[^\s&;,]+"),
]
_FIELDS = {"version", "seq", "type", "task_id", "agent", "data", "prev_hash", "self_hash",
           "severity", "event_id", "ts"}
_Value = TypeVar("_Value")


def _redact_str(value: str) -> str:
    for pattern in _SECRET_PATTERNS:
        value = pattern.sub(_REDACTED, value)
    return value


def _redact(obj: Any) -> Any:
    if isinstance(obj, str):
        return _redact_str(obj)
    if isinstance(obj, dict):
        result: dict[str, Any] = {}
        for key, value in obj.items():
            if not isinstance(key, str):
                raise TypeError("audit object keys must be strings")
            safe_key = _redact_str(key)
            if safe_key in result:
                raise ValueError("audit redaction key collision")
            sensitive = re.sub(r"[^a-z]", "", key.lower()) in _SENSITIVE_FIELDS
            result[safe_key] = (_REDACTED if sensitive and not (
                isinstance(value, str) and value.startswith("cred:")
            ) else _redact(value))
        return result
    if isinstance(obj, (list, tuple)):
        return [_redact(value) for value in obj]
    return obj


async def _offload(operation: Callable[..., _Value], *args: Any) -> _Value:
    work = asyncio.create_task(asyncio.to_thread(operation, *args))
    cancelled = False
    while not work.done():
        try:
            await asyncio.shield(work)
        except asyncio.CancelledError:
            cancelled = True
    result = work.result()
    if cancelled:
        raise asyncio.CancelledError()
    return result


def _wire(event: AgentEvent) -> dict[str, Any]:
    record = asdict(event)
    record["version"] = 1
    record["ts"] = event.ts.isoformat()
    return record


def _digest(record: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes({key: value for key, value in record.items()
                                           if key != "self_hash"})).hexdigest()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("audit record contains duplicate keys")
        result[key] = value
    return result


@dataclass(frozen=True)
class AuditVerification:
    valid: bool
    record_count: int
    head_hash: str
    break_index: int | None = None
    reason: str = ""


def _decode(lines: list[bytes], expected_head: str | None = None) -> tuple[list[AgentEvent], AuditVerification]:
    records: list[AgentEvent] = []
    previous = _GENESIS
    for index, line in enumerate(lines):
        try:
            raw = json.loads(line, object_pairs_hook=_unique_object)
            if not isinstance(raw, dict) or set(raw) != _FIELDS:
                raise ValueError("invalid record fields")
            if type(raw["version"]) is not int or raw["version"] != 1:
                raise ValueError("unsupported journal version")
            if type(raw["seq"]) is not int or raw["seq"] != index or raw["prev_hash"] != previous:
                raise ValueError("sequence or previous hash mismatch")
            if not isinstance(raw["data"], dict) or not isinstance(raw["event_id"], str):
                raise ValueError("invalid event contract")
            if any(raw[key] is not None and not isinstance(raw[key], str) for key in ("task_id", "agent")):
                raise ValueError("invalid event identity")
            if _digest(raw) != raw["self_hash"]:
                raise ValueError("record hash mismatch")
            timestamp = datetime.fromisoformat(raw["ts"])
            if timestamp.utcoffset() is None:
                raise ValueError("timestamp must include a timezone")
            record = AgentEvent(seq=index, type=EventType(raw["type"]), task_id=raw["task_id"],
                                agent=raw["agent"], data=raw["data"], prev_hash=previous,
                                self_hash=raw["self_hash"], severity=Severity(raw["severity"]),
                                event_id=raw["event_id"], ts=timestamp)
        except (ValueError, TypeError, KeyError, OverflowError) as error:
            return records, AuditVerification(False, index, previous, index, str(error))
        records.append(record)
        previous = record.self_hash
    valid = expected_head is None or expected_head == previous
    return records, AuditVerification(valid, len(records), previous, None if valid else len(records),
                                      "" if valid else "trusted head hash mismatch")


class AuditLog:
    def __init__(self) -> None:
        self._records: list[AgentEvent] = []
        self._journal: Journal | None = None
        self._lock = asyncio.Lock()
        self._closed = False

    @classmethod
    async def open(cls, path: str | Path) -> AuditLog:
        log = cls()
        try:
            await _offload(log._open, Path(path))
        except BaseException:
            await log.close()
            raise
        return log

    def _open(self, path: Path) -> None:
        self._journal = Journal(path)
        records, report = _decode(self._journal.read_lines())
        if not report.valid:
            raise ValueError(f"audit corruption at index {report.break_index}: {report.reason}")
        self._records = records

    @property
    def records(self) -> list[AgentEvent]:
        return copy.deepcopy(self._records)

    @property
    def durable(self) -> bool:
        return self._journal is not None

    def _prepare(self, etype: EventType, task_id: str | None, agent: str | None,
                 data: dict | None, severity: Severity) -> AgentEvent:
        if self._closed:
            raise RuntimeError("audit log is closed")
        safe = _redact({"task_id": task_id, "agent": agent, "data": data or {}})
        event = AgentEvent(seq=len(self._records), type=EventType(etype),
                           task_id=safe["task_id"], agent=safe["agent"], data=safe["data"],
                           prev_hash=self._records[-1].self_hash if self._records else _GENESIS,
                           self_hash="", severity=Severity(severity))
        event = replace(event, self_hash=_digest(_wire(event)))
        if len(canonical_bytes(_wire(event))) + 1 > MAX_RECORD_BYTES:
            raise ValueError("audit record exceeds size limit")
        return event

    def append(self, etype: EventType, *, task_id: str | None = None, agent: str | None = None,
               data: dict | None = None, severity: Severity = Severity.INFO) -> AgentEvent:
        if self.durable:
            raise RuntimeError("durable audit requires await append_async()")
        event = self._prepare(etype, task_id, agent, data, severity)
        self._records.append(event)
        return copy.deepcopy(event)

    async def append_async(self, etype: EventType, *, task_id: str | None = None,
                           agent: str | None = None, data: dict | None = None,
                           severity: Severity = Severity.INFO) -> AgentEvent:
        async with self._lock:
            event = self._prepare(etype, task_id, agent, data, severity)
            if self._journal is not None:
                await _offload(self._commit, event)
            else:
                self._records.append(event)
            return copy.deepcopy(event)

    def _commit(self, event: AgentEvent) -> None:
        assert self._journal is not None
        self._journal.write(canonical_bytes(_wire(event)) + b"\n")
        self._records.append(event)

    def verify(self) -> bool:
        return _decode([canonical_bytes(_wire(record)) for record in self._records])[1].valid

    async def verify_async(self) -> bool:
        async with self._lock:
            if self._journal is None:
                return self.verify()
            head = self._records[-1].self_hash if self._records else _GENESIS
            return await _offload(self._verify_disk, head)

    def _verify_disk(self, head: str) -> bool:
        assert self._journal is not None
        try:
            return _decode(self._journal.read_lines(), head)[1].valid
        except (ValueError, OSError, RuntimeError):
            return False

    @staticmethod
    async def check_file(path: str | Path, *, expected_head: str | None = None) -> AuditVerification:
        def check() -> AuditVerification:
            journal: Journal | None = None
            try:
                journal = Journal(Path(path), readonly=True)
                return _decode(journal.read_lines(), expected_head)[1]
            except (ValueError, OSError) as error:
                return AuditVerification(False, 0, _GENESIS, reason=str(error))
            finally:
                if journal is not None:
                    journal.close()

        return await _offload(check)

    async def close(self) -> None:
        async with self._lock:
            self._closed = True
            if self._journal is not None:
                await _offload(self._journal.close)

    async def __aenter__(self) -> AuditLog:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    def dump(self) -> str:
        return canonical_json([_wire(record) for record in self._records])
