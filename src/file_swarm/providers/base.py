"""Base provider interface."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel


class ProviderResult(BaseModel):
    ok: bool
    text: str = ""
    error: str | None = None
    model: str | None = None
    provider: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


class LLMProvider(Protocol):
    async def chat(self, model: str, messages: list[dict], **kwargs) -> ProviderResult: ...
