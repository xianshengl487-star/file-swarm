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
from .providers.mock_provider import MockProvider
from .providers.openai_compatible_provider import OpenAICompatibleProvider
from .repo_scanner import scan_repo
from .run_state import RunState
from .slot_registry import SlotRegistry
from .task_planner import PlannedTask, build_plan, split_tasks
from .transcript_logger import log_worker_call, write_json, write_text
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


def _select_slot(registry: SlotRegistry, router: ModelRouter | None, task_type: str) -> tuple[ModelSlot, str | None]:
    enabled_slots = registry.list_enabled()
    if not enabled_slots:
        raise RuntimeError("no enabled slots available")
    preferred_model = router.preferred_model(task_type, enabled_slots[0].default_model) if router else None
    if preferred_model:
        matching = registry.list_enabled_for_model(preferred_model)
        if matching:
            for slot in matching:
                if slot.max_concurrent_tasks > 0:
                    return slot, preferred_model
    return enabled_slots[0], enabled_slots[0].default_model


def _provider_for_slot(slot: ModelSlot, registry: SlotRegistry):
    api_key = registry.env_value(slot.api_key_env)
    base_url = registry.resolve_base_url(slot) or ""
    if slot.provider == "mock" or not api_key:
        return MockProvider(), "mock", None
    return OpenAICompatibleProvider(base_url=base_url, api_key=api_key), "openai_compatible", api_key


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
        slot, model = _select_slot(registry, router, task.task_type)
        worker_input = _build_worker_input(state, task, scan_repo(state.root), hard_constraints_yaml, interface_contract_yaml, repo_map)
        prompt = worker_input
        patches_dir = state.run_dir / "patches"
        transcripts_dir = state.run_dir / "transcripts"
        guard_dir = state.run_dir / "guard_reports"
        patch_path = patches_dir / f"{task.task_id}.patch"
        provider, provider_name, api_key = _provider_for_slot(slot, registry)

        async with lease_manager.hold(slot.id, 1):
            start_prompt = prompt
            status = "passed"
            error: str | None = None
            output_text = ""
            modified_files: list[str] = []
            try:
                output_text = await asyncio.wait_for(
                    provider.chat(
                        model=model or slot.default_model,
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=2048,
                    ),
                    timeout=timeout_seconds,
                )
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
            except Exception as exc:  # pragma: no cover - defensive against live provider failures
                status = "failed"
                error = type(exc).__name__
                output_text = f"ERROR: {type(exc).__name__}: {exc}"
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
    hard_exists = (state.run_dir / "hard_constraints.yaml").exists()
    interface_exists = (state.run_dir / "interface_contract.yaml").exists()
    summary = "\n".join(
        [
            f"- user_request: {state.user_request}",
            f"- run_id: {state.run_id}",
            f"- task_count: {task_count}",
            f"- hard_constraints_loaded: {hard_exists}",
            f"- interface_contract_exists: {interface_exists}",
            f"- patch_guard_passed: {merge_result.merged}",
            f"- final_patch_generated: {merge_result.final_patch_path is not None and merge_result.final_patch_path.exists()}",
            f"- recommend_apply: {merge_result.merged and validation_result.status in {'skipped', 'passed'}}",
            f"- validation_status: {validation_result.status}",
        ]
    )
    (state.run_dir / "codex_summary.md").write_text(summary + "\n", encoding="utf-8")
