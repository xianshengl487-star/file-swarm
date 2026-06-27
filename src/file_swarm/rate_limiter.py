"""Rate limiter for API calls to prevent 429 / rate-limit errors.

Uses a sliding-window token bucket approach with configurable
requests-per-minute (RPM) and tokens-per-minute (TPM).

Also provides a retry wrapper with exponential backoff for
rate-limit (429) and server-busy (503) errors.

Thread/async-safe via asyncio.Lock.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RateLimitConfig:
    """Configuration for a rate-limited API endpoint.

    All limits are per-minute. Set to 0 to disable that limit.
    """
    # Max requests per minute. 0 = unlimited.
    rpm: int = 60

    # Max input tokens per minute. 0 = unlimited.
    tpm_input: int = 0

    # Max output tokens per minute. 0 = unlimited.
    tpm_output: int = 0

    # Max concurrent in-flight requests. 0 = unlimited.
    max_concurrent: int = 5

    # Minimum interval between requests (seconds). Useful for slow endpoints.
    min_interval_s: float = 0.0

    # Retry settings
    max_retries: int = 3
    base_backoff_s: float = 1.0
    max_backoff_s: float = 30.0

    # Burst allowance: allow up to this many extra requests before enforcing strict RPM
    burst: int = 3


# ── Default configs for known APIs ───────────────────────────────────────

NVIDIA_NGC_CONFIG = RateLimitConfig(
    rpm=30,         # 30 requests/min — conservative for NVCF public endpoint
    tpm_input=200000,   # 200K input tokens/min
    tpm_output=50000,   # 50K output tokens/min
    max_concurrent=4,   # 4 concurrent requests
    min_interval_s=0.2,  # at least 200ms between requests
    max_retries=3,
    base_backoff_s=2.0,
    max_backoff_s=20.0,
    burst=5,
)

MIMO_CONFIG = RateLimitConfig(
    rpm=0,          # No rate limit — user doesn't need it for Mimo
    tpm_input=0,
    tpm_output=0,
    max_concurrent=0,   # unlimited concurrency
    min_interval_s=0.0,
    max_retries=1,
    base_backoff_s=1.0,
    max_backoff_s=5.0,
    burst=0,
)

RELAXED_CONFIG = RateLimitConfig(
    rpm=0,          # No rate limit — only NVIDIA needs throttling
    tpm_input=0,
    tpm_output=0,
    max_concurrent=0,   # unlimited concurrency
    min_interval_s=0.0,
    max_retries=1,
    base_backoff_s=1.0,
    max_backoff_s=5.0,
    burst=0,
)

# Dict-based configs for quick access
PRESETS: dict[str, RateLimitConfig] = {
    "nvidia": NVIDIA_NGC_CONFIG,
    "mimo": MIMO_CONFIG,
    "relaxed": RELAXED_CONFIG,
}


@dataclass
class RateLimiter:
    """Async rate limiter using sliding window + token bucket.

    Usage:
        limiter = RateLimiter(config=NVIDIA_NGC_CONFIG)
        async with limiter.acquire(tokens_in=500):
            # make API call
            result = await provider.chat(...)
            limiter.record_usage(tokens_in=500, tokens_out=100)
    """

    config: RateLimitConfig = field(default_factory=RateLimitConfig)

    # Internal state
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _request_times: list[float] = field(default_factory=list)
    _tokens_in_times: list[tuple[float, int]] = field(default_factory=list)
    _tokens_out_times: list[tuple[float, int]] = field(default_factory=list)
    _in_flight: int = 0
    _last_request_time: float = 0.0

    # Stats
    total_requests: int = 0
    total_retries: int = 0
    total_throttled: int = 0
    total_tokens_in: int = 0
    total_tokens_out: int = 0

    async def acquire(self, tokens_in: int = 0) -> float:
        """Request permission to make an API call.

        Blocks until the request can be made within rate limits.
        Returns the wait time in seconds (for logging).

        Uses retry loop with lock-release-during-sleep to avoid deadlocks.
        """
        wait_time = 0.0

        while True:
            async with self._lock:
                now = time.monotonic()

                # 1. Enforce min_interval (non-blocking — just check)
                if self.config.min_interval_s > 0 and self._last_request_time > 0:
                    elapsed = now - self._last_request_time
                    if elapsed < self.config.min_interval_s:
                        wait = self.config.min_interval_s - elapsed
                        # Release lock and sleep outside
                        sleep_needed = wait
                        _will_sleep = True
                    else:
                        sleep_needed = 0.0
                        _will_sleep = False
                else:
                    sleep_needed = 0.0
                    _will_sleep = False

                # 2. Check max_concurrent
                if self.config.max_concurrent > 0 and self._in_flight >= self.config.max_concurrent:
                    # Need to wait: release lock, sleep, retry
                    _will_sleep = True
                    sleep_needed = max(sleep_needed, 0.1)

                # 3. Check RPM
                if self.config.rpm > 0 and not _will_sleep:
                    cutoff = now - 60.0
                    self._request_times = [t for t in self._request_times if t > cutoff]
                    effective_rpm = self.config.rpm + self.config.burst
                    if len(self._request_times) >= effective_rpm:
                        oldest = self._request_times[0]
                        wait_for = oldest - cutoff
                        if wait_for > 0:
                            _will_sleep = True
                            sleep_needed = wait_for

                # 4. Check TPM input
                if self.config.tpm_input > 0 and tokens_in > 0 and not _will_sleep:
                    cutoff = now - 60.0
                    self._tokens_in_times = [(t, tok) for t, tok in self._tokens_in_times if t > cutoff]
                    current_in = sum(tok for _, tok in self._tokens_in_times)
                    if current_in + tokens_in > self.config.tpm_input and self._tokens_in_times:
                        oldest_t, oldest_tok = self._tokens_in_times[0]
                        wait_for = oldest_t - cutoff
                        if wait_for > 0:
                            _will_sleep = True
                            sleep_needed = wait_for

                # If all checks passed, book the slot and return
                if not _will_sleep:
                    self._last_request_time = now
                    self._in_flight += 1
                    # Final cleanup
                    cutoff = now - 60.0
                    self._request_times = [t for t in self._request_times if t > cutoff]
                    self._tokens_in_times = [(t, tok) for t, tok in self._tokens_in_times if t > cutoff]
                    self._tokens_out_times = [(t, tok) for t, tok in self._tokens_out_times if t > cutoff]
                    self._request_times.append(now)
                    if tokens_in > 0:
                        self._tokens_in_times.append((now, tokens_in))
                    break

            # Sleep outside the lock to allow others to release
            await asyncio.sleep(sleep_needed)
            wait_time += sleep_needed

        if wait_time > 0.01:
            self.total_throttled += 1

        return wait_time

    async def release(self):
        """Release the in-flight slot after request completes."""
        async with self._lock:
            if self._in_flight > 0:
                self._in_flight -= 1

    def record_usage(self, tokens_in: int = 0, tokens_out: int = 0):
        """Record actual token usage after a successful API call."""
        now = time.monotonic()
        if tokens_out > 0:
            self._tokens_out_times.append((now, tokens_out))
        self.total_requests += 1
        self.total_tokens_in += tokens_in
        self.total_tokens_out += tokens_out

    async def call_with_retry(
        self,
        call_fn,
        tokens_in: int = 0,
    ) -> Any:
        """Call an async function with rate limiting and exponential backoff retry.

        Args:
            call_fn: Async callable that returns a result. Should raise
                     RateLimitError or APIStatusError on rate limits.
            tokens_in: Estimated input tokens for this call.

        Returns:
            The result from call_fn.
        """
        for attempt in range(self.config.max_retries + 1):
            # Acquire rate limit permission
            wait = await self.acquire(tokens_in=tokens_in)
            if wait > 0.5:
                pass  # Throttled — caller can log if needed

            try:
                result = await call_fn()
                await self.release()
                return result
            except Exception as exc:
                await self.release()

                is_rate_limit = self._is_retryable(exc)
                if not is_rate_limit or attempt >= self.config.max_retries:
                    raise

                # Exponential backoff
                backoff = min(
                    self.config.base_backoff_s * (2 ** attempt),
                    self.config.max_backoff_s,
                )
                self.total_retries += 1
                await asyncio.sleep(backoff)

        # Should not reach here
        raise RuntimeError("max_retries exceeded")  # pragma: no cover

    def _is_retryable(self, exc: Exception) -> bool:
        """Check if an exception is a rate-limit error that can be retried."""
        ex_type = type(exc).__name__
        ex_msg = str(exc).lower()

        # OpenAI SDK exceptions
        if "RateLimitError" in ex_type:
            return True
        if "APIStatusError" in ex_type or "APIConnectionError" in ex_type:
            # Check status code
            status_str = str(exc)
            if any(code in status_str for code in ["429", "503", "502"]):
                return True
        # Generic checks
        if any(word in ex_msg for word in ["rate limit", "ratelimit", "too many requests", "throttle"]):
            return True
        if "status_code=429" in ex_msg or "status_code=503" in ex_msg:
            return True

        return False

    @property
    def stats(self) -> dict[str, int | float]:
        """Return current statistics."""
        return {
            "total_requests": self.total_requests,
            "total_retries": self.total_retries,
            "total_throttled": self.total_throttled,
            "total_tokens_in": self.total_tokens_in,
            "total_tokens_out": self.total_tokens_out,
            "in_flight": self._in_flight,
            "requests_in_window": len(self._request_times),
            "tokens_in_window": sum(tok for _, tok in self._tokens_in_times),
            "tokens_out_window": sum(tok for _, tok in self._tokens_out_times),
        }
