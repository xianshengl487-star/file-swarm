import subprocess
from pathlib import Path

import pytest
import typer

from file_swarm.cli import apply as apply_run
from file_swarm.run_state import RunState


def _init_repo(repo: Path) -> None:
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True)
    (repo / "hello.py").write_text('def hello():\n    return "hello"\n', encoding="utf-8")
    subprocess.run(["git", "add", "hello.py"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True, text=True)


def _run(repo: Path, guard_passed: bool = True, with_patch: bool = True) -> RunState:
    state = RunState(run_id="run1", root=repo, user_request="change hello", repo_root=str(repo))
    state.ensure_dirs()
    state.save()
    if with_patch:
        (state.run_dir / "final.patch").write_text(
            "--- a/hello.py\n+++ b/hello.py\n@@ -1,2 +1,2 @@\n def hello():\n-    return \"hello\"\n+    return \"hello world\"\n",
            encoding="utf-8",
        )
    (state.run_dir / "guard_report.md").write_text("status: ok\n", encoding="utf-8")
    (state.run_dir / "guard_reports" / "task_001.guard.json").write_text(
        f'{{"task_id":"task_001","passed": {str(guard_passed).lower()},"reason":"passed","modified_files":["hello.py"]}}\n',
        encoding="utf-8",
    )
    (state.run_dir / "hard_constraints.yaml").write_text("hard_constraints: {}\n", encoding="utf-8")
    (state.run_dir / "interface_contract.yaml").write_text("interface_contract: {}\n", encoding="utf-8")
    return state


def test_apply_rejects_dirty_worktree_by_default(tmp_path: Path, monkeypatch) -> None:
    _init_repo(tmp_path)
    _run(tmp_path)
    (tmp_path / "dirty.txt").write_text("dirty\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(typer.BadParameter):
        apply_run(run="run1")

    assert "worktree dirty" in (tmp_path / ".swarm" / "runs" / "run1" / "apply_report.md").read_text(encoding="utf-8")


def test_apply_allows_dirty_with_flag_and_writes_reports(tmp_path: Path, monkeypatch) -> None:
    _init_repo(tmp_path)
    _run(tmp_path)
    (tmp_path / "dirty.txt").write_text("dirty\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    apply_run(run="run1", allow_dirty=True, no_validate=True, allow_fallback_apply=False)

    run_dir = tmp_path / ".swarm" / "runs" / "run1"
    assert (run_dir / "before_apply.diff").exists()
    report = (run_dir / "apply_report.md").read_text(encoding="utf-8")
    assert "patch_applied: true" in report
    assert "allow_dirty_used: true" in report


def test_apply_fails_when_final_patch_missing(tmp_path: Path, monkeypatch) -> None:
    _init_repo(tmp_path)
    _run(tmp_path, with_patch=False)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(typer.BadParameter):
        apply_run(run="run1", allow_dirty=True)

    assert "final.patch not found" in (tmp_path / ".swarm" / "runs" / "run1" / "apply_report.md").read_text(encoding="utf-8")


def test_apply_rejects_guard_rejected_patch(tmp_path: Path, monkeypatch) -> None:
    _init_repo(tmp_path)
    _run(tmp_path, guard_passed=False)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(typer.BadParameter):
        apply_run(run="run1", allow_dirty=True)

    assert "guard report missing or rejected" in (tmp_path / ".swarm" / "runs" / "run1" / "apply_report.md").read_text(encoding="utf-8")
