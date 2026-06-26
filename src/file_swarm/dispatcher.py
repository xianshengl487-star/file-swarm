from __future__ import annotations

import json
import asyncio
from dataclasses import asdict
from pathlib import Path

from .lease_manager import LeaseManager
from .models import ModelSlot
from .patch_guard import guard_patch
from .repo_scanner import scan_repo
from .slot_registry import SlotRegistry
from .task_planner import PlannedTask, split_tasks
from .transcript_logger import log_worker_call, write_text, write_json
from .providers.mock_provider import MockProvider
from .providers.openai_compatible_provider import OpenAICompatibleProvider


def _read_example(root: Path, name: str) -> str:
    return (root / "configs" / name).read_text(encoding="utf-8")


def _load_provider(slot: ModelSlot, registry: SlotRegistry):
    api_key = registry.env_value(slot.api_key_env)
    if not api_key:
        return MockProvider(), "mock"
    return OpenAICompatibleProvider(base_url=slot.base_url or "", api_key=api_key), "openai_compatible"


def dispatch_run(state, tasks: list[PlannedTask] | None = None, registry: SlotRegistry | None = None) -> None:
    root = state.root
    state.ensure_dirs()
    if registry is None:
        registry_path = root / ".swarm" / "config" / "model_slots.yaml"
        registry = SlotRegistry.from_yaml(registry_path) if registry_path.exists() else SlotRegistry()
    tasks = tasks or split_tasks(scan_repo(root), state.user_request)
    lease = LeaseManager()
    patches_dir = state.run_dir / "patches"
    guard_dir = state.run_dir / "guard_reports"
    patches_dir.mkdir(parents=True, exist_ok=True)
    guard_dir.mkdir(parents=True, exist_ok=True)

    for task in tasks:
        slot = next(iter(registry.slots.values()), None)
        if slot is None:
            slot = ModelSlot(
                id="mock_slot",
                provider="mock",
                base_url=None,
                base_url_env=None,
                api_key_env="",
                enabled=True,
                allowed_models=["mock-model"],
                default_model="mock-model",
            )
        if not lease.can_acquire(slot.id, slot.max_concurrent_tasks):
            raise RuntimeError(f"slot {slot.id} is busy")
        lease.acquire(slot.id, slot.max_concurrent_tasks)
        try:
            provider, _ = _load_provider(slot, registry)
            model = slot.default_model
            prompt = _read_example(root, "policy.example.yaml")
            messages = [{"role": "user", "content": f"{task.goal}\n\n{prompt}"}]
            output_text = asyncio.run(provider.chat(model=model, messages=messages))
            patch_text = output_text
            write_text(patches_dir / f"{task.task_id}.patch", patch_text)
            guard = guard_patch(patch_text, task.allowed_files)
            write_json(guard_dir / f"{task.task_id}.guard.json", {"passed": guard.passed, "reason": guard.reason, "modified_files": guard.modified_files})
            log_worker_call(
                state.run_dir,
                task.task_id,
                f"{task.goal}\n{messages[0]['content']}",
                output_text,
                slot.id,
                slot.provider,
                model,
                registry.env_value(slot.api_key_env),
                "passed" if guard.passed else "rejected",
                task.assigned_files,
                task.allowed_files,
                guard.modified_files,
            )
        finally:
            lease.release(slot.id)
    state.status = "completed"
    state.save()


def guard_run(state) -> str:
    reports = []
    for patch_path in sorted((state.run_dir / "patches").glob("*.patch")):
        task_id = patch_path.stem
        guard_path = state.run_dir / "guard_reports" / f"{task_id}.guard.json"
        if guard_path.exists():
            reports.append(guard_path.read_text(encoding="utf-8"))
    report = "\n".join(reports) + ("\n" if reports else "")
    (state.run_dir / "guard_report.md").write_text(report or "no guard reports\n", encoding="utf-8")
    return report or "no guard reports\n"
