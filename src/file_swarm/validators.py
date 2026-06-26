from __future__ import annotations

import shutil
from pathlib import Path


def detect_test_command(root: Path) -> str | None:
    if (root / "pyproject.toml").exists():
        return "pytest"
    if (root / "package.json").exists():
        return "npm test"
    if (root / "pnpm-lock.yaml").exists():
        return "pnpm test"
    if (root / "yarn.lock").exists():
        return "yarn test"
    return None


def run_static_validation(run_dir: Path, project_root: Path) -> str:
    command = detect_test_command(project_root)
    report = [f"project_root: {project_root}", f"test_command: {command or 'skipped'}"]
    if command is None:
        report.append("status: skipped")
    else:
        report.append("status: deferred_in_scaffold_mode")
    return "\n".join(report) + "\n"
