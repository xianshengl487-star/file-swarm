from __future__ import annotations

from dataclasses import dataclass
import shutil
import subprocess
import sys
from pathlib import Path


@dataclass(slots=True)
class ValidationResult:
    command: str | None
    status: str
    stdout: str
    stderr: str


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


def _pytest_available() -> bool:
    """Probe whether pytest is importable by the current interpreter."""
    proc = subprocess.run(
        [sys.executable, "-c", "import pytest"],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode == 0


def run_validation(repo_root: Path, apply_mode: bool = False) -> ValidationResult:
    command = detect_test_command(repo_root)
    if command is None:
        return ValidationResult(command=None, status="skipped", stdout="", stderr="")
    if not apply_mode:
        return ValidationResult(command=command, status="skipped", stdout="", stderr="")

    if command == "pytest":
        if not _pytest_available():
            return ValidationResult(
                command=command,
                status="skipped",
                stdout="",
                stderr="pytest not installed in current interpreter; skipping validation",
            )
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q"],
            cwd=repo_root,
            text=True,
            capture_output=True,
            check=False,
            encoding="utf-8",
            errors="replace",
        )
    elif command == "npm test":
        npm_bin = shutil.which("npm")
        if not npm_bin:
            return ValidationResult(command=command, status="skipped", stdout="", stderr="npm not on PATH")
        proc = subprocess.run([npm_bin, "test"], cwd=repo_root, text=True, capture_output=True, check=False)
    elif command == "pnpm test":
        pnpm_bin = shutil.which("pnpm")
        if not pnpm_bin:
            return ValidationResult(command=command, status="skipped", stdout="", stderr="pnpm not on PATH")
        proc = subprocess.run([pnpm_bin, "test"], cwd=repo_root, text=True, capture_output=True, check=False)
    else:
        yarn_bin = shutil.which("yarn")
        if not yarn_bin:
            return ValidationResult(command=command, status="skipped", stdout="", stderr="yarn not on PATH")
        proc = subprocess.run([yarn_bin, "test"], cwd=repo_root, text=True, capture_output=True, check=False)

    status = "passed" if proc.returncode == 0 else "failed"
    return ValidationResult(command=command, status=status, stdout=proc.stdout, stderr=proc.stderr)


def render_validation_report(result: ValidationResult) -> str:
    return "\n".join(
        [
            f"command: {result.command or 'skipped'}",
            f"status: {result.status}",
            "stdout:",
            result.stdout.strip() if result.stdout else "",
            "stderr:",
            result.stderr.strip() if result.stderr else "",
        ]
    ).strip() + "\n"
