from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .run_state import RunState


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def _guard_rows(run_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted((run_dir / "guard_reports").glob("*.guard.json")):
        payload = _load_json(path, {})
        if payload:
            payload.setdefault("task_id", path.stem.removesuffix(".guard"))
            rows.append(payload)
    return rows


def _validation_status(run_dir: Path) -> str:
    path = run_dir / "validation_report.md"
    if not path.exists():
        return "not_run"
    text = path.read_text(encoding="utf-8", errors="replace")
    for status in ["passed", "failed", "skipped"]:
        if f"status: {status}" in text:
            return status
    return "not_run"


def _apply_status(run_dir: Path) -> str:
    path = run_dir / "apply_report.md"
    if not path.exists():
        return "not_applied"
    text = path.read_text(encoding="utf-8", errors="replace")
    if "patch_applied: true" in text:
        return "applied"
    return "failed"


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def write_codex_summary(state: RunState) -> Path:
    run_dir = state.run_dir
    task_results = state.data.get("task_results", [])
    if not task_results:
        task_results = _load_json(run_dir / "dispatch_report.json", {}).get("tasks", [])
    guard_rows = _guard_rows(run_dir)
    final_patch = run_dir / "final.patch"
    final_patch_exists = final_patch.exists()
    final_patch_empty = True
    if final_patch_exists:
        final_patch_empty = not final_patch.read_text(encoding="utf-8", errors="replace").strip()
    merge_text = (run_dir / "merge_report.md").read_text(encoding="utf-8", errors="replace") if (run_dir / "merge_report.md").exists() else ""
    has_conflict = "status: conflict" in merge_text
    hard_loaded = (run_dir / "hard_constraints.yaml").exists()
    interface_loaded = (run_dir / "interface_contract.yaml").exists()

    used_slots = sorted({str(item.get("slot_id")) for item in task_results if item.get("slot_id")})
    used_models = sorted({str(item.get("model")) for item in task_results if item.get("model")})
    mock_slots = sorted({str(item.get("slot_id")) for item in task_results if item.get("is_mock") or item.get("provider") == "mock"})
    live_slots = sorted({str(item.get("slot_id")) for item in task_results if item.get("provider") == "openai_compatible"})
    modified_files = sorted({path for row in guard_rows if row.get("passed") for path in row.get("modified_files", [])})

    total_tasks = len(task_results) or len(guard_rows)
    completed_tasks = sum(1 for item in task_results if item.get("status") == "passed")
    failed_tasks = sum(1 for item in task_results if item.get("status") not in {"passed", None})
    guard_passed = sum(1 for row in guard_rows if row.get("passed"))
    guard_rejected = sum(1 for row in guard_rows if not row.get("passed"))
    validation_status = _validation_status(run_dir)
    apply_status = _apply_status(run_dir)
    failed_or_rejected = [
        f"{row.get('task_id', 'unknown')}: {row.get('reason', 'unknown')}"
        for row in guard_rows
        if not row.get("passed")
    ]

    all_final_guarded = final_patch_exists and not final_patch_empty and guard_rows and guard_rejected == 0
    no_failed_critical = failed_tasks == 0
    if all_final_guarded and not has_conflict and hard_loaded and interface_loaded and no_failed_critical:
        if validation_status == "passed":
            recommend = "yes"
            reason = "guarded final.patch exists and validation passed"
        else:
            recommend = "yes_with_caution"
            reason = "dry merge generated guarded patch; run apply to validate"
    else:
        recommend = "no"
        reason_parts = []
        if not final_patch_exists:
            reason_parts.append("final.patch missing")
        if final_patch_empty:
            reason_parts.append("final.patch empty")
        if guard_rejected:
            reason_parts.append("guard rejected tasks")
        if has_conflict:
            reason_parts.append("merge conflict")
        if not hard_loaded:
            reason_parts.append("hard_constraints not loaded")
        if not interface_loaded:
            reason_parts.append("interface_contract not loaded")
        if failed_tasks:
            reason_parts.append("failed task present")
        reason = "; ".join(reason_parts) or "not enough successful guarded output"

    execution_mode = "mock"
    if mock_slots and live_slots:
        execution_mode = "mixed"
    elif live_slots:
        execution_mode = "live"

    lines = [
        "# Codex Summary",
        "",
        f"- run_id: {state.run_id}",
        f"- user_request: {state.user_request}",
        f"- repo_path: {state.root}",
        f"- execution_mode: {execution_mode}",
        f"- hard_constraints_loaded: {_yes_no(hard_loaded)}",
        f"- interface_contract_loaded: {_yes_no(interface_loaded)}",
        f"- total_tasks: {total_tasks}",
        f"- completed_tasks: {completed_tasks}",
        f"- failed_tasks: {failed_tasks}",
        f"- guard_passed_tasks: {guard_passed}",
        f"- guard_rejected_tasks: {guard_rejected}",
        f"- used_slots: {', '.join(used_slots) if used_slots else 'none'}",
        f"- used_models: {', '.join(used_models) if used_models else 'none'}",
        f"- mock_slots_used: {', '.join(mock_slots) if mock_slots else 'none'}",
        f"- live_slots_used: {', '.join(live_slots) if live_slots else 'none'}",
        f"- modified_files: {', '.join(modified_files) if modified_files else 'none'}",
        f"- final_patch_generated: {_yes_no(final_patch_exists)}",
        f"- final_patch_empty: {_yes_no(final_patch_empty)}",
        f"- validation_status: {validation_status}",
        f"- apply_status: {apply_status}",
        f"- recommend_apply: {recommend}",
        f"- recommend_apply_reason: {reason}",
        f"- need_repair: {_yes_no(bool(failed_or_rejected) or validation_status == 'failed')}",
        f"- failed_or_rejected_task_summary: {'; '.join(failed_or_rejected) if failed_or_rejected else 'none'}",
        "- next_commands_for_codex:",
        f"  - file-swarm summary --run {state.run_id} --for-codex",
        f"  - file-swarm apply --run {state.run_id} --allow-dirty",
        f"  - file-swarm repair --run {state.run_id}",
    ]
    path = run_dir / "codex_summary.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
