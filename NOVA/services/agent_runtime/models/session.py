"""Shared, serialized model budgets for task execution and plan repair."""

from __future__ import annotations

import asyncio
import math
import time
from typing import Callable

from services.agent_runtime.contracts.event import EventType, Severity
from services.agent_runtime.contracts.model_usage import (
    BudgetExceededError, MeteredCompletion, ModelResponseError,
)
from services.agent_runtime.events.audit import AuditLog


class MeteredModelSession:
    def __init__(self, *, model, audit: AuditLog, max_tokens: int, max_usd: float,
                 timeout_seconds: float, task_id: str | None = None, agent: str = "planner",
                 is_cancelled: Callable[[], bool] | None = None) -> None:
        if (type(max_tokens) is not int or max_tokens <= 0 or not math.isfinite(max_usd) or max_usd < 0
                or not math.isfinite(timeout_seconds) or timeout_seconds <= 0):
            raise BudgetExceededError("MODEL_BUDGET_EXCEEDED")
        self.model = model
        self.audit = audit
        self.max_tokens = max_tokens
        self.max_usd = max_usd
        self.deadline = time.monotonic() + timeout_seconds
        self.task_id = task_id
        self.agent = agent
        self.tokens = 0
        self.usd = 0.0
        self.failed = False
        self.is_cancelled = is_cancelled or (lambda: False)
        self._lock = asyncio.Lock()

    async def _event(self, event_type: EventType, data: dict, *, severity: Severity = Severity.INFO) -> None:
        await self.audit.append_async(event_type, task_id=self.task_id, agent=self.agent,
                                      data=data, severity=severity)

    async def _charge(self, tokens: int | None, usd: float) -> None:
        known = tokens is not None
        charged_tokens = tokens if known else self.max_tokens - self.tokens
        charged_usd = usd if known else self.max_usd - self.usd
        self.tokens += charged_tokens
        self.usd += charged_usd
        try:
            await self._event(EventType.MODEL_USAGE, {"tokens": charged_tokens, "usd": charged_usd,
                                                     "accounting": "reported" if known else "reserved"})
        except BaseException:
            self.failed = True
            raise

    async def complete(self, *, system: str, content: str) -> MeteredCompletion:
        async with self._lock:
            if self.is_cancelled():
                raise asyncio.CancelledError()
            if self.failed:
                raise ModelResponseError("MODEL_SESSION_FAILED")
            remaining_tokens = self.max_tokens - self.tokens
            remaining_usd = self.max_usd - self.usd
            if remaining_tokens <= 0 or remaining_usd < 0 or time.monotonic() >= self.deadline:
                self.failed = True
                await self._event(EventType.BUDGET_EXCEEDED, {"dimension": "model"}, severity=Severity.HIGH)
                raise BudgetExceededError("MODEL_BUDGET_EXCEEDED")
            method = getattr(self.model, "complete_metered", None)
            if method is None:
                self.failed = True
                raise ModelResponseError("MODEL_USAGE_UNAVAILABLE")
            await self._event(EventType.MODEL_REQUESTED, {"max_tokens": remaining_tokens, "max_usd": remaining_usd})
            if self.is_cancelled():
                self.failed = True
                raise asyncio.CancelledError()
            try:
                remaining_seconds = self.deadline - time.monotonic()
                if remaining_seconds <= 0:
                    raise BudgetExceededError("MODEL_BUDGET_EXCEEDED")
                async with asyncio.timeout(remaining_seconds):
                    completion = await method(system=system, content=content,
                                              max_tokens=remaining_tokens, max_usd=remaining_usd)
                if not isinstance(completion, MeteredCompletion):
                    raise ModelResponseError("MODEL_USAGE_INVALID")
            except BudgetExceededError:
                self.failed = True
                await self._event(EventType.BUDGET_EXCEEDED, {"dimension": "model"}, severity=Severity.HIGH)
                raise
            except asyncio.CancelledError:
                self.failed = True
                await self._charge(None, 0)
                await self._event(EventType.MODEL_FAILED, {"reason": "MODEL_CANCELLED"})
                raise
            except Exception as error:
                known_error = isinstance(error, ModelResponseError)
                code = str(error) if known_error else "MODEL_USAGE_UNCERTAIN"
                tokens = error.tokens if known_error else None
                usd = error.usd if known_error else 0
                self.failed = code != "MODEL_JSON_INVALID" or tokens is None
                await self._charge(tokens, usd)
                await self._event(EventType.MODEL_FAILED, {"reason": code, "exception_type": type(error).__name__}, severity=Severity.WARN)
                if self.tokens > self.max_tokens or self.usd > self.max_usd:
                    self.failed = True
                    await self._event(EventType.BUDGET_EXCEEDED, {"dimension": "model"}, severity=Severity.HIGH)
                    raise BudgetExceededError("MODEL_BUDGET_EXCEEDED") from None
                raise ModelResponseError(code, tokens=tokens, usd=usd) from None
            await self._charge(completion.tokens, completion.usd)
            if self.tokens > self.max_tokens or self.usd > self.max_usd:
                self.failed = True
                await self._event(EventType.BUDGET_EXCEEDED, {"dimension": "model"}, severity=Severity.HIGH)
                raise BudgetExceededError("MODEL_BUDGET_EXCEEDED")
            return completion