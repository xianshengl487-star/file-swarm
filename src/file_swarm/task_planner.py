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


_COMMON_FORBIDDEN = [
    "Do not modify files outside allowed_files",
    "Do not add dependencies",
    "Do not expose secrets",
    "Return unified diff patch only",
]

_AGENT_FORBIDDEN = [
    "Do not execute destructive commands (rm -rf, format, shutdown)",
    "Do not modify system files or registry",
    "Do not install software without permission",
    "Do not expose secrets in command output",
]


def split_agent_tasks(user_request: str, scan: RepoScanResult) -> list[PlannedTask]:
    """Plan agent_worker tasks for non-programming requests.

    Only triggers when the request is clearly a system/ops task, not code.
    """
    normalized = user_request.lower()

    # Hard exclusion: if any coding keyword present, NOT an agent task
    coding_keywords = [
        "实现", "implement", "refactor", "fix bug", "patch", "函数", "function",
        "def ", "class ", "import ", "subtract", "clicker", "add test",
        "todo", "stub", "pass\n",
    ]
    if any(kw in normalized for kw in coding_keywords):
        return []

    # Strong agent signals: these phrases clearly indicate non-coding tasks
    agent_phrases = [
        "检查系统", "运行命令", "执行命令", "系统报告", "系统诊断",
        "电脑操控", "电脑操作", "管理",
        "check system", "run command", "execute command", "system report",
        "system diagnose", "computer control", "list files", "show status",
        "monitor", "deploy", "build project", "run tests", "clean up",
        "check disk", "network status", "process list",
    ]

    is_agent = any(phrase in normalized for phrase in agent_phrases)

    if not is_agent:
        return []

    # Single agent task for the whole request
    context_files = []
    if scan.config_files:
        context_files = scan.config_files[:2]

    return [
        PlannedTask(
            task_id="agent_001",
            task_type="agent_worker",
            assigned_files=[],
            allowed_files=[],
            readonly_context_files=context_files,
            goal=user_request,
            requirements=["Execute commands safely and report results."],
            forbidden=_AGENT_FORBIDDEN,
        )
    ]


def _collect_source_files(scan: RepoScanResult) -> list[str]:
    """Pick concrete source files (not __init__, not __pycache__) for per-file tasks."""
    ignored_basenames = {"__init__.py", "conftest.py"}
    collected: list[str] = []
    source_prefixes = tuple(f"{d}/" for d in scan.source_dirs) if scan.source_dirs else ("",)
    for path in scan.files:
        if not path.endswith(".py"):
            continue
        if any(path.startswith(f"{d}/") for d in scan.test_dirs):
            continue
        if Path(path).name in ignored_basenames:
            continue
        if scan.source_dirs and not any(path.startswith(prefix) for prefix in source_prefixes):
            continue
        collected.append(path)
    return collected


def split_tasks(scan: RepoScanResult, user_request: str) -> list[PlannedTask]:
    normalized = user_request.lower()

    # ── Check for agent (non-coding) tasks first ──────────────
    agent_tasks = split_agent_tasks(user_request, scan)
    if agent_tasks:
        return agent_tasks

    if ("mouse clicker" in normalized or "auto clicker" in normalized or "连点器" in normalized) and {
        "src/clicker_core.py",
        "src/clicker_ui.py",
        "tests/test_clicker_design.py",
    }.issubset(set(scan.files)):
        return [
            PlannedTask(
                task_id="task_001",
                task_type="patch_worker",
                assigned_files=["src/clicker_core.py"],
                allowed_files=["src/clicker_core.py"],
                readonly_context_files=[],
                goal="Implement the safe clicker domain model and schedule builder.",
                requirements=["Keep mouse behavior as data-only planning, not real OS clicks."],
                forbidden=_COMMON_FORBIDDEN + ["Do not call operating-system mouse APIs in tests"],
            ),
            PlannedTask(
                task_id="task_002",
                task_type="patch_worker",
                assigned_files=["src/clicker_ui.py"],
                allowed_files=["src/clicker_ui.py"],
                readonly_context_files=["src/clicker_core.py"],
                goal="Implement a designed text UI layer for the clicker.",
                requirements=["Expose a status card, safety banner, and theme tokens."],
                forbidden=_COMMON_FORBIDDEN + ["Do not call operating-system mouse APIs in tests"],
            ),
            PlannedTask(
                task_id="task_003",
                task_type="patch_worker",
                assigned_files=["tests/test_clicker_design.py"],
                allowed_files=["tests/test_clicker_design.py"],
                readonly_context_files=["src/clicker_core.py", "src/clicker_ui.py"],
                goal="Add tests proving the clicker plan and UI contract work together.",
                requirements=["Test schedule generation, safety validation, and UI copy."],
                forbidden=_COMMON_FORBIDDEN + ["Do not call operating-system mouse APIs in tests"],
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
                forbidden=_COMMON_FORBIDDEN,
            )
        ]

    # ---- Generic branch: one task per concrete source file ----
    # This lets the dispatcher spread tasks across multiple slots (different
    # APIs) so each "pseudo-agent" works on a different file in parallel.
    source_files = _collect_source_files(scan)
    max_tasks = 8
    if source_files:
        source_files = source_files[:max_tasks]
        tasks: list[PlannedTask] = []
        for index, file_path in enumerate(source_files, start=1):
            tasks.append(
                PlannedTask(
                    task_id=f"task_{index:03d}",
                    task_type="patch_worker",
                    assigned_files=[file_path],
                    allowed_files=[file_path],
                    # Pass the file itself as read-only context so a provider can
                    # read its current content and produce a meaningful diff.
                    readonly_context_files=[file_path],
                    goal=user_request or f"Apply the requested change to {file_path}.",
                    requirements=["Follow existing style; do not break existing tests."],
                    forbidden=_COMMON_FORBIDDEN,
                )
            )
        return tasks

    # ---- Final fallback: create one new file (no existing sources) ----
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
            forbidden=_COMMON_FORBIDDEN,
        )
    ]
