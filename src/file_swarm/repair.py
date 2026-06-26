from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from .contract_builder import load_contract_texts
from .patch_guard import guard_patch
from .providers.base import ProviderResult
from .providers.mock_provider import MockProvider
from .run_state import RunState
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


async def _run_mock_repair(state: RunState, task_id: str, prompt: str, allowed_files: list[str]) -> tuple[str, ProviderResult]:
    provider = MockProvider()
    result = await provider.chat("mock-model", [{"role": "user", "content": prompt}], max_tokens=2048)
    if not result.ok:
        return "", result
    return result.text, result


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

    hard_yaml, interface_yaml = load_contract_texts(state.run_dir)
    completed: list[str] = []
    failed: list[str] = []

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
        output_text, result = asyncio.run(_run_mock_repair(state, task_id, prompt, allowed_files))
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
            "mock_repair_slot",
            "mock",
            "mock-model",
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
        if guard.passed:
            completed.append(repair_task_id)
        else:
            failed.append(f"{repair_task_id}: {guard.reason}")

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
