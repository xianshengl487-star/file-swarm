import json
import shutil
import subprocess
from pathlib import Path

from file_swarm.cli import apply as apply_run
from file_swarm.cli import auto


def test_mouse_clicker_multi_task_collaboration(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "mouse_clicker"
    shutil.copytree(Path("test/mouse_clicker_project"), repo)
    (repo / ".swarm" / "config").mkdir(parents=True, exist_ok=True)
    (repo / ".swarm" / "config" / "model_slots.yaml").write_text(
        "model_slots:\n"
        "  - id: mock1\n"
        "    provider: mock\n"
        "    api_key_env: MOCK_API_KEY\n"
        "    enabled: true\n"
        "    allowed_models: [mock-model]\n"
        "    default_model: mock-model\n"
        "  - id: mock2\n"
        "    provider: mock\n"
        "    api_key_env: MOCK_API_KEY\n"
        "    enabled: true\n"
        "    allowed_models: [mock-model]\n"
        "    default_model: mock-model\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "core.autocrlf", "false"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True)
    subprocess.run(["git", "add", "src/clicker_core.py", "src/clicker_ui.py", "tests/test_clicker_design.py"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True, text=True)
    monkeypatch.chdir(repo)

    auto(
        task="做一个比较有设计的鼠标连点器 mouse clicker，核心、界面和测试多任务合作完成。",
        repo=".",
        parallel=2,
        dry_merge=True,
    )

    run_dir = sorted((repo / ".swarm" / "runs").iterdir())[-1]
    run_id = run_dir.name
    task_payload = json.loads((run_dir / "file_tasks.json").read_text(encoding="utf-8"))
    assert [task["task_id"] for task in task_payload] == ["task_001", "task_002", "task_003"]
    assert (run_dir / "final.patch").exists()
    assert "src/clicker_core.py" in (run_dir / "final.patch").read_text(encoding="utf-8")
    assert "src/clicker_ui.py" in (run_dir / "final.patch").read_text(encoding="utf-8")
    assert "tests/test_clicker_design.py" in (run_dir / "final.patch").read_text(encoding="utf-8")

    apply_run(run=run_id, allow_dirty=True, no_validate=False, allow_fallback_apply=False)

    proc = subprocess.run(["python", "-m", "pytest", "-q"], cwd=repo, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stdout + proc.stderr

    summary = (run_dir / "codex_summary.md").read_text(encoding="utf-8")
    assert "total_tasks: 3" in summary
    assert "modified_files: src/clicker_core.py, src/clicker_ui.py, tests/test_clicker_design.py" in summary
