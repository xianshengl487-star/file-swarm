from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from .models import RepoScanResult

SKIP_DIRS = {".git", "node_modules", "dist", "build", "vendor", ".env", "venv", ".venv", "__pycache__", ".swarm"}
CONFIG_NAMES = {"pyproject.toml", "requirements.txt", "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock"}


def scan_repo(root: Path, max_file_size: int = 200_000) -> RepoScanResult:
    directories: list[str] = []
    files: list[str] = []
    source_dirs: list[str] = []
    test_dirs: list[str] = []
    config_files: list[str] = []
    project_type = "unknown"
    test_command = None

    for path in root.rglob("*"):
        rel = path.relative_to(root)
        parts = set(rel.parts)
        if parts & SKIP_DIRS:
            continue
        if path.is_dir():
            directories.append(rel.as_posix())
            if rel.name in {"src", "lib", "app"}:
                source_dirs.append(rel.as_posix())
            if "tests" in rel.parts or rel.name in {"tests", "test"}:
                test_dirs.append(rel.as_posix())
            continue
        if path.stat().st_size > max_file_size:
            continue
        files.append(rel.as_posix())
        if path.name in CONFIG_NAMES:
            config_files.append(rel.as_posix())
        if path.name == "pyproject.toml":
            project_type = "python"
            test_command = "pytest"
        elif path.name in {"package.json", "pnpm-lock.yaml", "yarn.lock", "package-lock.json"} and project_type == "unknown":
            project_type = "node"
            test_command = "npm test"

    return RepoScanResult(
        root=root,
        directories=sorted(set(directories)),
        files=sorted(set(files)),
        source_dirs=sorted(set(source_dirs)),
        test_dirs=sorted(set(test_dirs)),
        config_files=sorted(set(config_files)),
        test_command=test_command,
        project_type=project_type,
    )
