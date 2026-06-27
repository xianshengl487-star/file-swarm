from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from anthropic import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncAnthropic,
    AuthenticationError,
    RateLimitError,
)

from .base import ProviderResult


@dataclass(slots=True)
class AnthropicProvider:
    """Anthropic Messages API provider (used for Mimo and similar proxies)."""

    base_url: str
    api_key: str
    timeout: float = 60.0

    def _client(self) -> AsyncAnthropic:
        return AsyncAnthropic(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=self.timeout,
            max_retries=0,
        )

    async def chat(self, model: str, messages: list[dict], **kwargs: Any) -> ProviderResult:
        client = self._client()
        # Anthropic separates system prompt from messages.
        system_parts: list[str] = []
        user_parts: list[str] = []
        for msg in messages:
            content = str(msg.get("content", ""))
            role = msg.get("role", "user")
            if (
                "HARD_CONSTRAINTS" in content
                or "INTERFACE_CONTRACT" in content
                or "FORBIDDEN:" in content
                or "REQUIREMENTS:" in content
            ):
                system_parts.append(content)
            elif role == "user":
                user_parts.append(content)

        prompt = "\n\n".join(user_parts)
        if system_parts:
            system = "\n\n".join(system_parts)
        else:
            # Detect task type from the prompt content
            if "JSON array" in prompt or "shell commands" in prompt.lower() or "system agent" in prompt.lower():
                system = "You are a system agent. Respond ONLY with the requested format."
            else:
                system = "You are a stateless patch worker. Return ONLY unified diff patches."

        max_tokens = kwargs.pop("max_tokens", 2048)
        # Anthropic models may consume tokens for internal reasoning/thinking;
        # add headroom so the actual text output is not truncated.
        if max_tokens < 1024:
            max_tokens = 1024
        try:
            response = await client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                **kwargs,
            )
        except APITimeoutError:
            return ProviderResult(ok=False, error="timeout", model=model, provider="anthropic")
        except AuthenticationError:
            return ProviderResult(ok=False, error="authentication_error", model=model, provider="anthropic")
        except RateLimitError:
            return ProviderResult(ok=False, error="rate_limit", model=model, provider="anthropic")
        except APIConnectionError:
            return ProviderResult(ok=False, error="connection_error", model=model, provider="anthropic")
        except APIStatusError as exc:
            return ProviderResult(
                ok=False,
                error=f"api_error_status_{exc.status_code}",
                model=model,
                provider="anthropic",
            )
        except Exception as exc:  # pragma: no cover
            return ProviderResult(
                ok=False,
                error=f"unknown_api_error:{type(exc).__name__}",
                model=model,
                provider="anthropic",
            )

        text = ""
        input_tokens = None
        output_tokens = None
        for block in response.content:
            if getattr(block, "type", "") == "text":
                text += getattr(block, "text", "")
        usage = getattr(response, "usage", None)
        if usage:
            input_tokens = getattr(usage, "input_tokens", None)
            output_tokens = getattr(usage, "output_tokens", None)

        return ProviderResult(
            ok=True,
            text=text,
            model=model,
            provider="anthropic",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
