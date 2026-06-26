import shutil
import subprocess
import sys
from pathlib import Path

from file_swarm.cli import apply as apply_run
from file_swarm.cli import auto


def test_demo_project_end_to_end(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "demo"
    shutil.copytree(Path("examples/demo_python_project"), repo)
    (repo / ".swarm" / "config").mkdir(parents=True, exist_ok=True)
    (repo / ".swarm" / "config" / "model_slots.yaml").write_text(
        "model_slots:\n"
        "  - id: mock1\n"
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
    subprocess.run(["git", "add", "src/demo_math.py", "tests/test_demo_math.py"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True, text=True)
    monkeypatch.chdir(repo)

    auto(task="Add subtract(a: int, b: int) -> int and add tests.", repo=".", parallel=2, dry_merge=True)

    runs = sorted((repo / ".swarm" / "runs").iterdir())
    assert runs
    run_id = runs[-1].name
    run_dir = runs[-1]

    assert (run_dir / "final.patch").exists()
    assert (run_dir / "guard_report.md").exists()
    assert (run_dir / "codex_summary.md").exists()

    apply_run(run=run_id, allow_dirty=True, no_validate=False, allow_fallback_apply=False)

    proc = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=repo, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stdout + proc.stderr
