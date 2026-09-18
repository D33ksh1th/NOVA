"""
LLM Models
"""

from pydantic import BaseModel


class LLMRequest(BaseModel):

    prompt: str

    model: str


class LLMResponse(BaseModel):

    text: str

    model: str