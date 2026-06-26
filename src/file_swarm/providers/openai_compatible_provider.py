from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI


@dataclass(slots=True)
class OpenAICompatibleProvider:
    base_url: str
    api_key: str
    timeout: float = 30.0

    def _client(self) -> AsyncOpenAI:
        return AsyncOpenAI(base_url=self.base_url, api_key=self.api_key, timeout=self.timeout)

    async def chat(self, model: str, messages: list[dict], **kwargs: Any) -> str:
        client = self._client()
        response = await client.chat.completions.create(model=model, messages=messages, **kwargs)
        return response.choices[0].message.content or ""
