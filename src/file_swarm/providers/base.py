"""Base provider interface."""

from __future__ import annotations

from typing import Protocol


class LLMProvider(Protocol):
    async def chat(self, model: str, messages: list[dict], **kwargs) -> str: ...
