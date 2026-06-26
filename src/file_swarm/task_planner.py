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
        f"- contracts_loaded: {bool(hard_constraints) and bool(interface_contract)}",
        "",
        "## Execution Notes",
        "- Prefer the existing code style.",
        "- Return patches only from workers.",
        "- Keep scope tight.",
    ]
    return "\n".join(lines) + "\n"


def split_tasks(scan: RepoScanResult, user_request: str) -> list[PlannedTask]:
    normalized = user_request.lower()
    if ("mouse clicker" in normalized or "auto clicker" in normalized or "连点器" in normalized) and {
        "src/clicker_core.py",
        "src/clicker_ui.py",
        "tests/test_clicker_design.py",
    }.issubset(set(scan.files)):
        common_forbidden = [
            "Do not modify files outside allowed_files",
            "Do not add dependencies",
            "Do not call operating-system mouse APIs in tests",
            "Do not expose secrets",
            "Return unified diff patch only",
        ]
        return [
            PlannedTask(
                task_id="task_001",
                task_type="patch_worker",
                assigned_files=["src/clicker_core.py"],
                allowed_files=["src/clicker_core.py"],
                readonly_context_files=[],
                goal="Implement the safe clicker domain model and schedule builder.",
                requirements=["Keep mouse behavior as data-only planning, not real OS clicks."],
                forbidden=common_forbidden,
            ),
            PlannedTask(
                task_id="task_002",
                task_type="patch_worker",
                assigned_files=["src/clicker_ui.py"],
                allowed_files=["src/clicker_ui.py"],
                readonly_context_files=["src/clicker_core.py"],
                goal="Implement a designed text UI layer for the clicker.",
                requirements=["Expose a status card, safety banner, and theme tokens."],
                forbidden=common_forbidden,
            ),
            PlannedTask(
                task_id="task_003",
                task_type="patch_worker",
                assigned_files=["tests/test_clicker_design.py"],
                allowed_files=["tests/test_clicker_design.py"],
                readonly_context_files=["src/clicker_core.py", "src/clicker_ui.py"],
                goal="Add tests proving the clicker plan and UI contract work together.",
                requirements=["Test schedule generation, safety validation, and UI copy."],
                forbidden=common_forbidden,
            ),
        ]

    if "subtract" in normalized and ("src/demo_math.py" in scan.files or "tests/test_demo_math.py" in scan.files):
        allowed = [path for path in ["src/demo_math.py", "tests/test_demo_math.py"] if path in scan.files]
        if not allowed:
            allowed = ["src/demo_math.py", "tests/test_demo_math.py"]
        return [
            PlannedTask(
                task_id="task_001",
                task_type="patch_worker",
                assigned_files=allowed,
                allowed_files=allowed,
                readonly_context_files=[path for path in allowed if path.endswith("test_demo_math.py")],
                goal=user_request or "Implement the requested change.",
                requirements=["Update demo math subtraction and tests."],
                forbidden=[
                    "Do not modify files outside allowed_files",
                    "Do not add dependencies",
                    "Do not expose secrets",
                    "Return unified diff patch only",
                ],
            )
        ]

    targets = scan.source_dirs or ["src"]
    task_file = f"{targets[0]}/generated_change.py"
    readonly = scan.test_dirs[:1] or scan.files[:1]
    return [
        PlannedTask(
            task_id="task_001",
            task_type="patch_worker",
            assigned_files=[task_file],
            allowed_files=[task_file],
            readonly_context_files=readonly,
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
