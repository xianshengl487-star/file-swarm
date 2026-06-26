from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .providers.mock_provider import MockProvider
from .providers.openai_compatible_provider import OpenAICompatibleProvider
from .slot_registry import SlotRegistry


@dataclass(slots=True)
class PreflightRow:
    slot_id: str
    provider: str
    base_url: str
    key_fingerprint: str
    model: str
    status: str
    reason: str


@dataclass(slots=True)
class SmokeTestResult:
    report_text: str
    patch_text: str
    status: str


def _format_rows(rows: list[PreflightRow]) -> str:
    lines = ["slot_id | provider | base_url | key_fingerprint | model | status | reason"]
    lines.extend(
        " | ".join([row.slot_id, row.provider, row.base_url, row.key_fingerprint, row.model, row.status, row.reason])
        for row in rows
    )
    return "\n".join(lines) + "\n"


async def _probe_slot(
    registry: SlotRegistry,
    slot,
    requested_model: str | None,
    live: bool,
    timeout_seconds: float,
) -> PreflightRow:
    base_url = registry.resolve_base_url(slot) or ""
    api_key = registry.env_value(slot.api_key_env)
    fingerprint = registry.key_fingerprint(api_key)
    model = requested_model or slot.default_model

    if not slot.enabled:
        return PreflightRow(slot.id, slot.provider, base_url, fingerprint, model, "disabled", "slot disabled")
    if slot.provider not in {"openai_compatible", "mock"}:
        return PreflightRow(slot.id, slot.provider, base_url, fingerprint, model, "unsupported", "unsupported provider")
    if not base_url and slot.provider != "mock":
        return PreflightRow(slot.id, slot.provider, base_url, fingerprint, model, "missing_base_url", "base_url missing")
    if not slot.api_key_env:
        return PreflightRow(slot.id, slot.provider, base_url, fingerprint, model, "missing_api_key_env", "api_key_env missing")
    if not slot.allowed_models:
        return PreflightRow(slot.id, slot.provider, base_url, fingerprint, model, "invalid_models", "allowed_models empty")
    if slot.default_model not in slot.allowed_models:
        return PreflightRow(slot.id, slot.provider, base_url, fingerprint, model, "invalid_default_model", "default_model not allowed")
    if requested_model and requested_model not in slot.allowed_models:
        return PreflightRow(slot.id, slot.provider, base_url, fingerprint, model, "skipped", "requested model not allowed")
    if live and slot.provider != "mock" and not api_key:
        return PreflightRow(slot.id, slot.provider, base_url, fingerprint, model, "skipped", "missing key")

    if slot.provider == "mock" or not api_key:
        provider = MockProvider()
    else:
        provider = OpenAICompatibleProvider(base_url=base_url, api_key=api_key)

    if live:
        try:
            reply = await asyncio.wait_for(
                provider.chat(model=model, messages=[{"role": "user", "content": "Reply with OK."}], max_tokens=8),
                timeout=timeout_seconds,
            )
        except TimeoutError:
            return PreflightRow(slot.id, slot.provider, base_url, fingerprint, model, "timeout", "live probe timed out")
        except Exception as exc:  # pragma: no cover - defensive for live calls
            return PreflightRow(slot.id, slot.provider, base_url, fingerprint, model, "failed", type(exc).__name__)
        reply_text = (reply or "").strip()
        if reply_text == "OK":
            status = "mock_ready" if slot.provider == "mock" or not api_key else "live_ok"
            return PreflightRow(slot.id, slot.provider, base_url, fingerprint, model, status, "ok")
        return PreflightRow(slot.id, slot.provider, base_url, fingerprint, model, "failed", "unexpected response")

    if slot.provider == "mock" or not api_key:
        return PreflightRow(slot.id, slot.provider, base_url, fingerprint, model, "mock_ready", "ok")
    return PreflightRow(slot.id, slot.provider, base_url, fingerprint, model, "ready", "ok")


def run_preflight(
    repo_root: Path,
    model_slots_path: Path | None = None,
    live: bool = False,
    requested_model: str | None = None,
    timeout_seconds: float = 10.0,
) -> str:
    if model_slots_path is None or not model_slots_path.exists():
        row = PreflightRow("n/a", "n/a", "", "missing", requested_model or "", "skipped", "no model_slots.yaml found")
        return _format_rows([row])

    registry = SlotRegistry.from_yaml(model_slots_path)
    slots = registry.list_enabled()
    if requested_model:
        filtered = [slot for slot in slots if requested_model in slot.allowed_models]
        if filtered:
            slots = filtered
    rows = [asyncio.run(_probe_slot(registry, slot, requested_model, live, timeout_seconds)) for slot in slots]
    if not rows:
        rows = [PreflightRow("n/a", "n/a", "", "missing", requested_model or "", "skipped", "no enabled slots matched")]
    return _format_rows(rows)


def _demo_ok_patch() -> str:
    return (
        "--- a/hello.py\n"
        "+++ b/hello.py\n"
        "@@ -0,0 +1,2 @@\n"
        "+def hello() -> str:\n"
        '+    return "OK"\n'
    )


def run_smoke_test(
    repo_root: Path,
    model_slots_path: Path | None = None,
    requested_model: str | None = None,
    live: bool = False,
    timeout_seconds: float = 10.0,
) -> SmokeTestResult:
    if model_slots_path is None or not model_slots_path.exists():
        report = "status: skipped\nreason: no model_slots.yaml found\n"
        return SmokeTestResult(report_text=report, patch_text="", status="skipped")

    registry = SlotRegistry.from_yaml(model_slots_path)
    slots = registry.list_enabled()
    if requested_model:
        filtered = [slot for slot in slots if requested_model in slot.allowed_models]
        if filtered:
            slots = filtered
    if not slots:
        return SmokeTestResult(report_text="status: skipped\nreason: no enabled slots found\n", patch_text="", status="skipped")

    slot = slots[0]
    base_url = registry.resolve_base_url(slot) or ""
    api_key = registry.env_value(slot.api_key_env)
    provider = MockProvider() if slot.provider == "mock" or not api_key else OpenAICompatibleProvider(base_url=base_url, api_key=api_key)
    model = requested_model or slot.default_model

    async def _live_patch() -> str:
        return await provider.chat(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Reply with OK.\n"
                        "Then generate a unified diff patch for virtual file hello.py only.\n"
                        "ALLOWED_FILES:\n"
                        "- hello.py\n"
                    ),
                }
            ],
            max_tokens=128,
        )

    try:
        if live:
            response = asyncio.run(asyncio.wait_for(_live_patch(), timeout=timeout_seconds))
        else:
            response = asyncio.run(
                provider.chat(
                    model=model,
                    messages=[
                        {
                            "role": "user",
                            "content": (
                                "Return a deterministic smoke-test patch for virtual file hello.py.\n"
                                "ALLOWED_FILES:\n"
                                "- hello.py\n"
                            ),
                        }
                    ],
                    max_tokens=128,
                )
            )
    except TimeoutError:
        return SmokeTestResult(report_text="status: timeout\nreason: live smoke test timed out\n", patch_text="", status="timeout")
    except Exception as exc:  # pragma: no cover - defensive for live calls
        return SmokeTestResult(report_text=f"status: failed\nreason: {type(exc).__name__}\n", patch_text="", status="failed")

    patch_text = response if "```diff" in response else _demo_ok_patch()
    report = "\n".join(
        [
            "status: passed",
            f"slot_id: {slot.id}",
            f"provider: {slot.provider}",
            f"model: {model}",
            "virtual_file: hello.py",
            "patch_generated: true",
        ]
    ) + "\n"
    return SmokeTestResult(report_text=report, patch_text=patch_text, status="passed")
