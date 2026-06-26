from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from openai import APIConnectionError, APIStatusError, APITimeoutError, AuthenticationError, AsyncOpenAI, RateLimitError

from .base import ProviderResult


@dataclass(slots=True)
class OpenAICompatibleProvider:
    base_url: str
    api_key: str
    timeout: float = 30.0

    def _client(self) -> AsyncOpenAI:
        return AsyncOpenAI(base_url=self.base_url, api_key=self.api_key, timeout=self.timeout)

    async def chat(self, model: str, messages: list[dict], **kwargs: Any) -> ProviderResult:
        client = self._client()
        try:
            response = await client.chat.completions.create(model=model, messages=messages, **kwargs)
        except APITimeoutError:
            return ProviderResult(ok=False, error="timeout", model=model, provider="openai_compatible")
        except AuthenticationError:
            return ProviderResult(ok=False, error="authentication_error", model=model, provider="openai_compatible")
        except RateLimitError:
            return ProviderResult(ok=False, error="rate_limit", model=model, provider="openai_compatible")
        except APIConnectionError:
            return ProviderResult(ok=False, error="connection_error", model=model, provider="openai_compatible")
        except APIStatusError as exc:
            return ProviderResult(
                ok=False,
                error=f"api_error_status_{exc.status_code}",
                model=model,
                provider="openai_compatible",
            )
        except Exception as exc:  # pragma: no cover - defensive for SDK/runtime surprises
            return ProviderResult(ok=False, error=f"unknown_api_error:{type(exc).__name__}", model=model, provider="openai_compatible")

        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "prompt_tokens", None) if usage else None
        output_tokens = getattr(usage, "completion_tokens", None) if usage else None
        return ProviderResult(
            ok=True,
            text=response.choices[0].message.content or "",
            model=model,
            provider="openai_compatible",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
