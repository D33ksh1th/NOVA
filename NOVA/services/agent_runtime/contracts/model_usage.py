from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


MODEL_FAILURE_MESSAGES = {
    "MODEL_USAGE_UNAVAILABLE": "The model response lacked valid token counts; usage could not be verified.",
    "MODEL_USAGE_UNCERTAIN": "The model call ended without verifiable usage; it was not retried.",
    "MODEL_TOKEN_CONTRACT_VIOLATION": "The model token counts did not match the configured tokenizer or output limit.",
    "MODEL_TIMEOUT": "The model did not respond within its time limit.",
    "MODEL_PROVIDER_ERROR": "The local model server returned an error instead of a completion.",
    "MODEL_HTTP_400": "The local model server rejected the request format or generation settings.",
    "MODEL_HTTP_404": "The configured model or endpoint was not found on the local server.",
    "MODEL_HTTP_429": "The local model server rejected the request because it was busy.",
    "MODEL_HTTP_500": "The local model server reported an internal error.",
    "MODEL_HTTP_502": "The local model server reported an upstream error.",
    "MODEL_HTTP_503": "The local model server was unavailable.",
    "MODEL_HTTP_504": "The local model server reported a timeout.",
    "MODEL_INCOMPLETE": "The model stopped before completing its answer.",
    "MODEL_JSON_INVALID": "The model returned invalid JSON.",
    "MODEL_SCHEMA_INVALID": "The model output did not match the required research schema.",
    "MODEL_RESPONSE_TOO_LARGE": "The model response exceeded the allowed size.",
    "MODEL_TRANSPORT_OR_RESPONSE_INVALID": "The model connection failed or returned an unreadable response.",
}


class MeteredCompletion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    content: dict[str, Any]
    tokens: int = Field(ge=0, strict=True)
    usd: float = Field(ge=0, allow_inf_nan=False)


class BudgetExceededError(RuntimeError):
    pass


class ModelResponseError(RuntimeError):
    def __init__(self, code: str, *, tokens: int | None = None, usd: float = 0) -> None:
        usage = MeteredCompletion(content={}, tokens=0 if tokens is None else tokens, usd=usd)
        super().__init__(code)
        self.tokens = tokens
        self.usd = usage.usd