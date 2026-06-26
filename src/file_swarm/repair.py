from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from .contract_builder import load_contract_texts
from .lease_manager import LeaseManager
from .patch_guard import guard_patch
from .providers.base import ProviderResult
from .providers.mock_provider import MockProvider
from .providers.openai_compatible_provider import OpenAICompatibleProvider
from .providers.anthropic_provider import AnthropicProvider
from .run_state import RunState
from .slot_registry import SlotRegistry
from .summary import write_codex_summary
from .transcript_logger import log_worker_call, write_json, write_text


def _load_guard_rows(run_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted((run_dir / "guard_reports").glob("*.guard.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload.setdefault("task_id", path.stem.removesuffix(".guard"))
        rows.append(payload)
    return rows


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def _allowed_files_for_task(state: RunState, task_id: str) -> list[str]:
    tasks_path = state.run_dir / "file_tasks.json"
    if not tasks_path.exists():
        return []
    for item in json.loads(tasks_path.read_text(encoding="utf-8")):
        if item.get("task_id") == task_id:
            return list(item.get("allowed_files", []))
    return []


def _slot_id_for_task(state: RunState, task_id: str) -> str | None:
    """Find which slot originally handled task_id (skip repair_* tasks)."""
    report_path = state.run_dir / "dispatch_report.json"
    if not report_path.exists():
        return None
    report = json.loads(report_path.read_text(encoding="utf-8"))
    for item in report.get("tasks", []):
        if item.get("task_id") == task_id:
            return item.get("slot_id")
    return None


def _load_registry(state: RunState) -> SlotRegistry:
    registry_path = state.root / ".swarm" / "config" / "model_slots.yaml"
    if registry_path.exists():
        return SlotRegistry.from_yaml(registry_path)
    return SlotRegistry()


def _provider_for_slot(slot, registry: SlotRegistry):
    api_key = registry.env_value(slot.api_key_env)
    base_url = registry.resolve_base_url(slot) or ""
    if slot.provider == "mock" or not api_key:
        return MockProvider(), "mock", None
    if slot.provider == "anthropic":
        return AnthropicProvider(base_url=base_url, api_key=api_key), "anthropic", api_key
    return OpenAICompatibleProvider(base_url=base_url, api_key=api_key), "openai_compatible", api_key


async def _run_repair_with_slot(
    state: RunState,
    task_id: str,
    prompt: str,
    slot,
    model: str,
    registry: SlotRegistry,
    lease_manager: LeaseManager,
    timeout_seconds: float = 30.0,
) -> tuple[str, ProviderResult, str, str]:
    """Return (output_text, provider_result, slot_id, provider_name)."""
    # Acquire the slot (respect its max_concurrent_tasks) before calling.
    while not await lease_manager.try_acquire(
        slot.id, task_id=task_id, max_concurrent_tasks=slot.max_concurrent_tasks
    ):
        await asyncio.sleep(0.05)
    try:
        provider, provider_name, api_key = _provider_for_slot(slot, registry)
        try:
            result = await asyncio.wait_for(
                provider.chat(model, [{"role": "user", "content": prompt}], max_tokens=2048),
                timeout=timeout_seconds,
            )
        except TimeoutError:
            result = ProviderResult(ok=False, error="timeout", model=model, provider=provider_name)
        except Exception as exc:  # pragma: no cover - defensive
            result = ProviderResult(ok=False, error=type(exc).__name__, model=model, provider=provider_name)
        output_text = result.text if result.ok else ""
        return output_text, result, slot.id, provider_name
    finally:
        lease_manager.release(slot.id, task_id)


async def _run_repairs_async(state: RunState, repairable: list[dict[str, Any]]) -> list[dict[str, Any]]:
    registry = _load_registry(state)
    lease_manager = LeaseManager()
    hard_yaml, interface_yaml = load_contract_texts(state.run_dir)
    validation_error = _read(state.run_dir / "validation_report.md")[:2000]
    outcomes: list[dict[str, Any]] = []

    for row in repairable:
        task_id = str(row.get("task_id", "unknown"))
        allowed_files = _allowed_files_for_task(state, task_id)
        original_input = _read(state.run_dir / "transcripts" / f"{task_id}.input.md")
        original_patch = _read(state.run_dir / "patches" / f"{task_id}.patch")
        prompt = "\n".join(
            [
                f"REPAIR_TASK_FOR: {task_id}",
                "",
                "HARD_CONSTRAINTS_YAML:",
                "```yaml",
                hard_yaml,
                "```",
                "",
                "INTERFACE_CONTRACT_YAML:",
                "```yaml",
                interface_yaml,
                "```",
                "",
                "ORIGINAL_TASK_INPUT:",
                original_input,
                "",
                "ORIGINAL_PATCH:",
                "```diff",
                original_patch,
                "```",
                "",
                f"GUARD_VIOLATION: {row.get('reason', 'unknown')}",
                "",
                "VALIDATION_ERROR_SUMMARY:",
                validation_error or "none",
                "",
                "Return a corrected unified diff patch only. Keep changes inside ALLOWED_FILES.",
                "ALLOWED_FILES:",
                *[f"- {path}" for path in allowed_files],
            ]
        )
        repair_task_id = f"repair_{task_id}"

        # Resolve the slot + model that originally handled this task so the
        # repair goes through the same provider (real API) when available.
        original_slot_id = _slot_id_for_task(state, task_id)
        slot = None
        model = "mock-model"
        if original_slot_id and original_slot_id in registry.slots:
            slot = registry.slots[original_slot_id]
            model = slot.default_model
        if slot is None:
            # Fall back to first enabled mock slot, or any enabled slot.
            enabled = registry.list_enabled()
            slot = next((s for s in enabled if s.provider == "mock"), None) or (enabled[0] if enabled else None)
            if slot:
                model = slot.default_model

        if slot is None:
            # No registry at all — pure mock fallback.
            provider = MockProvider()
            try:
                result = await provider.chat(model, [{"role": "user", "content": prompt}], max_tokens=2048)
            except Exception as exc:  # pragma: no cover
                result = ProviderResult(ok=False, error=type(exc).__name__, model=model, provider="mock")
            output_text = result.text if result.ok else ""
            used_slot_id = "mock_repair_slot"
            provider_name = "mock"
        else:
            output_text, result, used_slot_id, provider_name = await _run_repair_with_slot(
                state, repair_task_id, prompt, slot, model, registry, lease_manager
            )

        patch_path = state.run_dir / "patches" / f"{repair_task_id}.patch"
        write_text(patch_path, output_text or "# repair provider failed\n")
        guard = guard_patch(
            output_text,
            allowed_files,
            hard_constraints_path=state.run_dir / "hard_constraints.yaml",
        )
        write_json(
            state.run_dir / "guard_reports" / f"{repair_task_id}.guard.json",
            {
                "task_id": repair_task_id,
                "passed": guard.passed,
                "reason": guard.reason if result.ok else result.error or "provider_error",
                "modified_files": guard.modified_files,
            },
        )
        log_worker_call(
            state.run_dir,
            repair_task_id,
            prompt,
            output_text,
            used_slot_id,
            provider_name,
            model,
            None,
            "passed" if guard.passed else "rejected",
            allowed_files,
            allowed_files,
            guard.modified_files,
            provider_ok=result.ok,
            provider_error=result.error,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        )
        outcomes.append(
            {
                "repair_task_id": repair_task_id,
                "passed": guard.passed,
                "reason": guard.reason if result.ok else result.error or "provider_error",
            }
        )
    return outcomes


def repair_run(state: RunState) -> Path:
    state.ensure_dirs()
    guard_rows = _load_guard_rows(state.run_dir)
    validation_error = _read(state.run_dir / "validation_report.md")[:2000]
    repairable = [row for row in guard_rows if not row.get("passed")]
    report_path = state.run_dir / "repair_report.md"

    if not repairable and "status: failed" not in validation_error:
        write_text(report_path, "repair_status: skipped\nreason: no rejected or failed tasks\n")
        write_codex_summary(state)
        return report_path

    outcomes = asyncio.run(_run_repairs_async(state, repairable))

    completed = [item["repair_task_id"] for item in outcomes if item["passed"]]
    failed = [f"{item['repair_task_id']}: {item['reason']}" for item in outcomes if not item["passed"]]
    status = "completed" if completed and not failed else "failed"
    write_text(
        report_path,
        "\n".join(
            [
                f"repair_status: {status}",
                f"repaired_tasks: {', '.join(completed) if completed else 'none'}",
                f"failed_repairs: {'; '.join(failed) if failed else 'none'}",
            ]
        )
        + "\n",
    )
    write_codex_summary(state)
    return report_path
