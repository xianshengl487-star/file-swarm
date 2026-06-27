from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from openai import APIConnectionError, APIStatusError, APITimeoutError, AuthenticationError, AsyncOpenAI, RateLimitError

from .base import ProviderResult
from ..rate_limiter import RateLimiter


@dataclass(slots=True)
class OpenAICompatibleProvider:
    base_url: str
    api_key: str
    timeout: float = 30.0
    rate_limiter: RateLimiter | None = None
    _enable_retry: bool = True

    def _client(self) -> AsyncOpenAI:
        return AsyncOpenAI(base_url=self.base_url, api_key=self.api_key, timeout=self.timeout)

    async def chat(self, model: str, messages: list[dict], **kwargs: Any) -> ProviderResult:
        """Send a chat completion with optional rate limiting and retry.

        When rate_limiter is configured, calls are rate-limited and
        automatically retried with exponential backoff on 429/503 errors.
        """
        limiter = self.rate_limiter
        max_tokens_est = kwargs.get("max_tokens", 2048)

        # Estimate input tokens: rough heuristic (4 chars ≈ 1 token for English,
        # but messages can be mixed. Use 3 chars/token for safety margin.)
        msg_text = "".join(m.get("content", "") for m in messages if isinstance(m, dict))
        estimated_input_tokens = max(1, len(msg_text) // 3)

        async def _do_call():
            """The raw API call function."""
            nonlocal model
            client = self._client()
            try:
                response = await client.chat.completions.create(model=model, messages=messages, **kwargs)
            except RateLimitError:
                return ProviderResult(ok=False, error="rate_limit", model=model, provider="openai_compatible")
            except APITimeoutError:
                return ProviderResult(ok=False, error="timeout", model=model, provider="openai_compatible")
            except AuthenticationError:
                return ProviderResult(ok=False, error="authentication_error", model=model, provider="openai_compatible")
            except APIConnectionError:
                return ProviderResult(ok=False, error="connection_error", model=model, provider="openai_compatible")
            except APIStatusError as exc:
                return ProviderResult(
                    ok=False,
                    error=f"api_error_status_{exc.status_code}",
                    model=model,
                    provider="openai_compatible",
                )
            except Exception as exc:
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

        # ── Rate-limited call with retry ─────────────────────────
        if limiter is not None and self._enable_retry:
            max_retries = limiter.config.max_retries
        else:
            max_retries = 0

        for attempt in range(max_retries + 1):
            if limiter is not None:
                # Wait for rate limit permission
                wait = await limiter.acquire(tokens_in=estimated_input_tokens)

            result = await _do_call()

            if limiter is not None:
                # Track actual usage and release in-flight slot
                limiter.record_usage(
                    tokens_in=result.input_tokens or estimated_input_tokens,
                    tokens_out=result.output_tokens or max_tokens_est,
                )
                await limiter.release()

            # Check if retryable
            is_rate_limit = "rate_limit" in (result.error or "")
            is_server_busy = any(code in (result.error or "") for code in ["502", "503"])
            is_connection = "connection_error" in (result.error or "")

            if (is_rate_limit or is_server_busy or is_connection) and attempt < max_retries:
                backoff = min(2.0 * (2 ** attempt), limiter.config.max_backoff_s if limiter else 10.0)
                await asyncio.sleep(backoff)
                continue

            return result

        # Should not reach here
        return result  # type: ignore[possibly-undefined]  # pragma: no cover
