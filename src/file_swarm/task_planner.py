from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import RepoScanResult


@dataclass(slots=True)
class PlannedTask:
    task_id: str
    task_type: str
    assigned_files: list[str]
    allowed_files: list[str]
    readonly_context_files: list[str]
    goal: str
    requirements: list[str]
    forbidden: list[str]
    status: str = "pending"


def build_plan(user_request: str, scan: RepoScanResult, hard_constraints: dict[str, Any], interface_contract: dict[str, Any]) -> str:
    lines = [
        f"# Plan for: {user_request}",
        "",
        f"- project_type: {scan.project_type}",
        f"- source_dirs: {', '.join(scan.source_dirs) or 'none'}",
        f"- test_dirs: {', '.join(scan.test_dirs) or 'none'}",
        "",
        "## Execution Notes",
        "- Prefer the existing code style.",
        "- Return patches only from workers.",
        "- Keep scope tight.",
    ]
    return "\n".join(lines) + "\n"


def split_tasks(scan: RepoScanResult, user_request: str) -> list[PlannedTask]:
    targets = scan.source_dirs or ["src"]
    task_file = f"{targets[0]}/generated_change.py"
    return [
        PlannedTask(
            task_id="task_001",
            task_type="patch_worker",
            assigned_files=[task_file],
            allowed_files=[task_file],
            readonly_context_files=scan.test_dirs[:1],
            goal=user_request or "Implement the requested change.",
            requirements=[],
            forbidden=[
                "Do not modify files outside allowed_files",
                "Do not add dependencies",
                "Do not expose secrets",
                "Return unified diff patch only",
            ],
        )
    ]
