from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .contract_builder import load_contract_dicts, load_contract_texts
from .lease_manager import LeaseManager
from .models import ModelSlot, TaskResult
from .model_router import ModelRouter
from .patch_guard import guard_patch
from .patch_merger import MergeResult, merge_patches
from .providers.base import ProviderResult
from .providers.mock_provider import MockProvider
from .providers.openai_compatible_provider import OpenAICompatibleProvider
from .repo_scanner import scan_repo
from .run_state import RunState
from .slot_registry import SlotRegistry
from .summary import write_codex_summary
from .task_planner import PlannedTask, build_plan, split_tasks
from .transcript_logger import append_timeline_event, log_worker_call, write_json, write_text
from .validators import ValidationResult, render_validation_report, run_validation


def _read_optional_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _load_tasks(run_dir: Path, scan, user_request: str) -> list[PlannedTask]:
    tasks_path = run_dir / "file_tasks.json"
    if not tasks_path.exists():
        return split_tasks(scan, user_request)
    payload = json.loads(tasks_path.read_text(encoding="utf-8"))
    tasks: list[PlannedTask] = []
    for item in payload:
        tasks.append(
            PlannedTask(
                task_id=item["task_id"],
                task_type=item["task_type"],
                assigned_files=list(item.get("assigned_files", [])),
                allowed_files=list(item.get("allowed_files", [])),
                readonly_context_files=list(item.get("readonly_context_files", [])),
                goal=item.get("goal", ""),
                requirements=list(item.get("requirements", [])),
                forbidden=list(item.get("forbidden", [])),
                status=item.get("status", "pending"),
            )
        )
    return tasks


def _store_tasks(run_dir: Path, tasks: list[PlannedTask]) -> None:
    payload = [asdict(task) for task in tasks]
    write_json(run_dir / "file_tasks.json", payload)


def _build_repo_map(scan) -> str:
    lines = [
        "# Repo Map",
        "",
        f"- project_type: {scan.project_type}",
        f"- source_dirs: {', '.join(scan.source_dirs) or 'none'}",
        f"- test_dirs: {', '.join(scan.test_dirs) or 'none'}",
        f"- config_files: {', '.join(scan.config_files) or 'none'}",
    ]
    return "\n".join(lines) + "\n"


def _read_context(repo_root: Path, file_path: str) -> str:
    path = repo_root / file_path
    if not path.exists():
        return "<missing>"
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return "<unreadable>"


def _build_worker_input(
    state: RunState,
    task: PlannedTask,
    scan,
    hard_constraints_yaml: str,
    interface_contract_yaml: str,
    repo_map: str,
) -> str:
    context_chunks: list[str] = []
    for context_file in task.readonly_context_files:
        context_chunks.append(f"FILE: {context_file}\n```text\n{_read_context(state.root, context_file)}\n```")
    readonly_block = "\n\n".join(context_chunks) if context_chunks else "<none>"
    allowed_lines = "\n".join(f"- {path}" for path in task.allowed_files)
    assigned_lines = "\n".join(f"- {path}" for path in task.assigned_files)
    forbidden_lines = "\n".join(f"- {item}" for item in task.forbidden)
    requirements_lines = "\n".join(f"- {item}" for item in task.requirements) if task.requirements else "- none"
    return (
        f"TASK_ID: {task.task_id}\n"
        f"TASK_TYPE: {task.task_type}\n"
        f"USER_REQUEST: {state.user_request}\n"
        f"GOAL: {task.goal}\n"
        f"ASSIGNED_FILES:\n{assigned_lines or '- none'}\n"
        f"ALLOWED_FILES:\n{allowed_lines or '- none'}\n"
        f"READ_ONLY_CONTEXT_FILES:\n{readonly_block}\n\n"
        f"REQUIREMENTS:\n{requirements_lines}\n"
        f"FORBIDDEN:\n{forbidden_lines}\n\n"
        f"HARD_CONSTRAINTS_YAML:\n```yaml\n{hard_constraints_yaml}\n```\n\n"
        f"INTERFACE_CONTRACT_YAML:\n```yaml\n{interface_contract_yaml}\n```\n\n"
        f"REPO_MAP:\n{repo_map}\n\n"
        "You are a stateless patch worker.\n"
        "You do not have permission to write files.\n"
        "You must return a unified diff patch.\n"
        "You must only modify allowed_files.\n"
        "You must obey hard_constraints and interface_contract.\n"
        "Do not add dependencies.\n"
        "Do not output secrets.\n"
        "Do not change public APIs unless explicitly allowed.\n"
        "Return output in this shape:\n"
        "## Implementation Summary\n\n"
        "## Patch\n\n```diff\n...\n```\n\n"
        "## Risk Notes\n\n"
        "## Suggested Tests\n"
    )


def _candidate_models(registry: SlotRegistry, router: ModelRouter | None, task_type: str) -> list[str]:
    enabled_slots = registry.list_enabled()
    if not enabled_slots:
        raise RuntimeError("no enabled slots available")
    models: list[str] = []
    if router:
        preferred = router.routing.get(task_type, [])
        models.extend(preferred)
    models.extend(slot.default_model for slot in enabled_slots)
    for slot in enabled_slots:
        models.extend(slot.allowed_models)
    return list(dict.fromkeys(model for model in models if model))


def _slot_has_key_or_mock(slot: ModelSlot, registry: SlotRegistry) -> bool:
    return slot.provider == "mock" or bool(registry.env_value(slot.api_key_env))


async def _acquire_available_slot(
    task: PlannedTask,
    registry: SlotRegistry,
    router: ModelRouter | None,
    lease_manager: LeaseManager,
) -> tuple[ModelSlot, str]:
    candidate_models = _candidate_models(registry, router, task.task_type)
    while True:
        for model in candidate_models:
            for slot in registry.list_enabled_for_model(model):
                if not slot.enabled or slot.max_concurrent_tasks <= 0:
                    continue
                if not _slot_has_key_or_mock(slot, registry):
                    continue
                if lease_manager.is_leased(slot.id):
                    continue
                acquired = await lease_manager.try_acquire(slot.id, task_id=task.task_id, max_concurrent_tasks=1)
                if acquired:
                    return slot, model
        await asyncio.sleep(0.05)


def _provider_for_slot(slot: ModelSlot, registry: SlotRegistry):
    api_key = registry.env_value(slot.api_key_env)
    base_url = registry.resolve_base_url(slot) or ""
    if slot.provider == "mock" or not api_key:
        return MockProvider(), "mock", None
    return OpenAICompatibleProvider(base_url=base_url, api_key=api_key), "openai_compatible", api_key


def _coerce_provider_result(result: ProviderResult | str, model: str, provider: str) -> ProviderResult:
    if isinstance(result, ProviderResult):
        return result
    return ProviderResult(ok=True, text=str(result), model=model, provider=provider)


def _ensure_dispatch_registry(registry: SlotRegistry) -> SlotRegistry:
    if registry.slots:
        return registry
    fallback = ModelSlot(
        id="mock_slot",
        provider="mock",
        base_url=None,
        base_url_env=None,
        api_key_env="MOCK_API_KEY",
        enabled=True,
        allowed_models=["mock-model"],
        default_model="mock-model",
        max_concurrent_tasks=1,
    )
    return SlotRegistry(slots={fallback.id: fallback})


async def _run_task(
    state: RunState,
    task: PlannedTask,
    registry: SlotRegistry,
    router: ModelRouter | None,
    lease_manager: LeaseManager,
    global_sem: asyncio.Semaphore,
    hard_constraints_yaml: str,
    interface_contract_yaml: str,
    hard_constraints: dict[str, Any],
    repo_map: str,
    timeout_seconds: float,
) -> TaskResult:
    async with global_sem:
        slot, model = await _acquire_available_slot(task, registry, router, lease_manager)
        append_timeline_event(
            state.run_dir,
            "slot_acquired",
            {"task_id": task.task_id, "slot_id": slot.id, "model": model, "provider": slot.provider},
        )
        worker_input = _build_worker_input(state, task, scan_repo(state.root), hard_constraints_yaml, interface_contract_yaml, repo_map)
        prompt = worker_input
        patches_dir = state.run_dir / "patches"
        transcripts_dir = state.run_dir / "transcripts"
        guard_dir = state.run_dir / "guard_reports"
        patch_path = patches_dir / f"{task.task_id}.patch"
        provider, provider_name, api_key = _provider_for_slot(slot, registry)

        start_prompt = prompt
        status = "passed"
        error: str | None = None
        output_text = ""
        modified_files: list[str] = []
        provider_result = ProviderResult(ok=False, error="not_started", model=model, provider=provider_name)
        try:
            append_timeline_event(
                state.run_dir,
                "worker_started",
                {"task_id": task.task_id, "slot_id": slot.id, "model": model, "provider": provider_name},
            )
            provider_result = _coerce_provider_result(
                await asyncio.wait_for(
                    provider.chat(
                        model=model or slot.default_model,
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=2048,
                    ),
                    timeout=timeout_seconds,
                ),
                model or slot.default_model,
                provider_name,
            )
            output_text = provider_result.text
            if not provider_result.ok:
                status = "failed"
                error = provider_result.error or "provider_error"
                write_text(patch_path, f"# file-swarm provider failed: {error}\n")
                write_json(
                    guard_dir / f"{task.task_id}.guard.json",
                    {
                        "task_id": task.task_id,
                        "passed": False,
                        "reason": error,
                        "modified_files": [],
                    },
                )
            else:
                guard = guard_patch(
                    output_text,
                    task.allowed_files,
                    hard_constraints=hard_constraints,
                    hard_constraints_path=state.run_dir / "hard_constraints.yaml",
                )
                modified_files = guard.modified_files
                if not guard.passed:
                    status = "rejected"
                    error = guard.reason
                write_text(patch_path, output_text if output_text.strip() else "# empty patch rejected\n")
                write_json(
                    guard_dir / f"{task.task_id}.guard.json",
                    {
                        "task_id": task.task_id,
                        "passed": guard.passed,
                        "reason": guard.reason,
                        "modified_files": guard.modified_files,
                    },
                )
        except TimeoutError:
            status = "timeout"
            error = "timeout"
            output_text = "timeout"
            provider_result = ProviderResult(ok=False, error="timeout", model=model, provider=provider_name)
            write_text(patch_path, "# file-swarm task timed out\n")
            write_json(
                guard_dir / f"{task.task_id}.guard.json",
                {
                    "task_id": task.task_id,
                    "passed": False,
                    "reason": "timeout",
                    "modified_files": [],
                },
            )
        except Exception as exc:  # pragma: no cover - defensive against provider/plugin failures
            status = "failed"
            error = type(exc).__name__
            output_text = f"ERROR: {type(exc).__name__}"
            provider_result = ProviderResult(ok=False, error=error, model=model, provider=provider_name)
            write_text(patch_path, f"# file-swarm worker failed: {type(exc).__name__}\n")
            write_json(
                guard_dir / f"{task.task_id}.guard.json",
                {
                    "task_id": task.task_id,
                    "passed": False,
                    "reason": type(exc).__name__,
                    "modified_files": [],
                },
            )
        finally:
            append_timeline_event(
                state.run_dir,
                "worker_finished",
                {"task_id": task.task_id, "slot_id": slot.id, "model": model, "status": status},
            )
            log_worker_call(
                state.run_dir,
                task.task_id,
                start_prompt,
                output_text,
                slot.id,
                slot.provider,
                model or slot.default_model,
                api_key,
                status,
                task.assigned_files,
                task.allowed_files,
                modified_files,
                provider_ok=provider_result.ok,
                provider_error=provider_result.error,
                input_tokens=provider_result.input_tokens,
                output_tokens=provider_result.output_tokens,
            )
            lease_manager.release(slot.id, task.task_id)
            append_timeline_event(
                state.run_dir,
                "slot_released",
                {"task_id": task.task_id, "slot_id": slot.id, "model": model, "status": status},
            )

        return TaskResult(
            task_id=task.task_id,
            slot_id=slot.id,
            model=model or slot.default_model,
            provider=provider_name,
            status=status,
            patch_path=str(patch_path),
            modified_files=modified_files,
            error=error,
            provider_ok=provider_result.ok,
            provider_error=provider_result.error,
            input_tokens=provider_result.input_tokens,
            output_tokens=provider_result.output_tokens,
            is_mock=provider_name == "mock",
        )


async def dispatch_run_async(
    state: RunState,
    tasks: list[PlannedTask] | None = None,
    registry: SlotRegistry | None = None,
    parallel: int = 1,
    timeout_seconds: float = 30.0,
) -> list[TaskResult]:
    state.ensure_dirs()
    scan = scan_repo(state.root)
    state.run_dir.mkdir(parents=True, exist_ok=True)
    if registry is None:
        registry_path = state.root / ".swarm" / "config" / "model_slots.yaml"
        registry = SlotRegistry.from_yaml(registry_path) if registry_path.exists() else SlotRegistry()
    registry = _ensure_dispatch_registry(registry)
    router_path = state.root / ".swarm" / "config" / "routing.yaml"
    router = ModelRouter.from_yaml(router_path) if router_path.exists() else None
    hard_constraints_yaml, interface_contract_yaml = load_contract_texts(state.run_dir)
    hard_constraints, interface_contract = load_contract_dicts(state.run_dir)
    repo_map = _build_repo_map(scan)
    write_text(state.run_dir / "repo_map.md", repo_map)
    tasks = tasks or _load_tasks(state.run_dir, scan, state.user_request)
    _store_tasks(state.run_dir, tasks)
    write_text(state.run_dir / "plan.md", build_plan(state.user_request, scan, {}, interface_contract))
    lease_manager = LeaseManager()
    global_sem = asyncio.Semaphore(max(1, parallel))
    task_runs = [
        asyncio.create_task(
            _run_task(
                state,
                task,
                registry,
                router,
                lease_manager,
                global_sem,
                hard_constraints_yaml,
                interface_contract_yaml,
                hard_constraints,
                repo_map,
                timeout_seconds,
            )
        )
        for task in tasks
    ]
    results = await asyncio.gather(*task_runs)
    state.status = "completed" if all(result.status == "passed" for result in results) else "partial"
    state.data["task_results"] = [asdict(result) for result in results]
    write_json(
        state.run_dir / "dispatch_report.json",
        {
            "parallel": parallel,
            "tasks": [asdict(result) for result in results],
            "used_slots": sorted({result.slot_id for result in results}),
            "used_models": sorted({result.model for result in results}),
        },
    )
    write_text(
        state.run_dir / "dispatch_report.md",
        "\n".join(
            ["# Dispatch Report", ""]
            + [
                f"- {result.task_id}: slot={result.slot_id}, model={result.model}, provider={result.provider}, mock={result.is_mock}, status={result.status}"
                for result in results
            ]
        )
        + "\n",
    )
    state.save()
    return results


def dispatch_run(
    state: RunState,
    tasks: list[PlannedTask] | None = None,
    registry: SlotRegistry | None = None,
    parallel: int = 1,
    timeout_seconds: float = 30.0,
) -> list[TaskResult]:
    return asyncio.run(dispatch_run_async(state, tasks=tasks, registry=registry, parallel=parallel, timeout_seconds=timeout_seconds))


def guard_run(state: RunState) -> str:
    guard_dir = state.run_dir / "guard_reports"
    rows: list[dict[str, Any]] = []
    for path in sorted(guard_dir.glob("*.json")):
        rows.append(json.loads(path.read_text(encoding="utf-8")))
    report = {
        "status": "ok" if rows and all(row.get("passed") for row in rows) else "partial",
        "task_count": len(rows),
        "passed_count": sum(1 for row in rows if row.get("passed")),
        "failed_count": sum(1 for row in rows if not row.get("passed")),
        "rows": rows,
    }
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    (state.run_dir / "guard_report.md").write_text(text, encoding="utf-8")
    return text


def write_auto_summary(state: RunState, task_count: int, merge_result: MergeResult, validation_result) -> None:
    write_codex_summary(state)
