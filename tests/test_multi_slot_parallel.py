"""End-to-end test: multiple pseudo-agent slots (different APIs) run different
file tasks in parallel, then merge + apply cleanly.

This exercises the core P0 fix: the generic task planner splits work by source
file, the dispatcher spreads tasks across multiple slots, and each slot's
pseudo-agent produces a non-conflicting patch for its own file.
"""

import json
import asyncio
import shutil
import subprocess
import sys
from pathlib import Path

from file_swarm.cli import apply as apply_run
from file_swarm.cli import auto
from file_swarm.providers.mock_provider import MockProvider


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Force LF line endings so generated unified diffs apply cleanly with
    # core.autocrlf=false (avoids CRLF/LF mismatch on Windows).
    path.write_text(content, encoding="utf-8", newline="\n")


def _build_multi_file_repo(repo: Path) -> None:
    """A repo with three independent source modules + one test file."""
    _write(
        repo / "src" / "alpha.py",
        '"""Alpha module."""\n\n\ndef alpha_value() -> int:\n    return 1\n',
    )
    _write(
        repo / "src" / "beta.py",
        '"""Beta module."""\n\n\ndef beta_value() -> int:\n    return 2\n',
    )
    _write(
        repo / "src" / "gamma.py",
        '"""Gamma module."""\n\n\ndef gamma_value() -> int:\n    return 3\n',
    )
    _write(
        repo / "tests" / "test_modules.py",
        "from src.alpha import alpha_value\n"
        "from src.beta import beta_value\n"
        "from src.gamma import gamma_value\n\n\n"
        "def test_values():\n"
        "    assert alpha_value() + beta_value() + gamma_value() == 6\n",
    )
    _write(
        repo / "pyproject.toml",
        '[build-system]\nrequires = ["setuptools"]\nbuild-backend = "setuptools.build_meta"\n\n'
        '[project]\nname = "multi-file-demo"\nversion = "0.1.0"\n\n'
        '[tool.setuptools]\npackage-dir = {"" = "src"}\n\n'
        '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n',
    )


def _three_mock_slots_config() -> str:
    """Three slots simulating three different APIs (all mock provider)."""
    return (
        "model_slots:\n"
        "  - id: api_alpha\n"
        "    provider: mock\n"
        "    api_key_env: MOCK_API_KEY\n"
        "    enabled: true\n"
        "    allowed_models: [mock-model]\n"
        "    default_model: mock-model\n"
        "    max_concurrent_tasks: 1\n"
        "  - id: api_beta\n"
        "    provider: mock\n"
        "    api_key_env: MOCK_API_KEY\n"
        "    enabled: true\n"
        "    allowed_models: [mock-model]\n"
        "    default_model: mock-model\n"
        "    max_concurrent_tasks: 1\n"
        "  - id: api_gamma\n"
        "    provider: mock\n"
        "    api_key_env: MOCK_API_KEY\n"
        "    enabled: true\n"
        "    allowed_models: [mock-model]\n"
        "    default_model: mock-model\n"
        "    max_concurrent_tasks: 1\n"
    )


def test_multi_slot_parallel_different_files(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "multi_file"
    _build_multi_file_repo(repo)
    (repo / ".swarm" / "config").mkdir(parents=True, exist_ok=True)
    (repo / ".swarm" / "config" / "model_slots.yaml").write_text(
        _three_mock_slots_config(), encoding="utf-8"
    )

    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "core.autocrlf", "false"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True, text=True)
    monkeypatch.chdir(repo)

    # Slow down the mock provider so tasks truly overlap in time; otherwise the
    # mock returns instantly and all tasks would serially grab the first slot.
    original_chat = MockProvider.chat

    async def slow_chat(self, model, messages, **kwargs):
        await asyncio.sleep(0.08)
        return await original_chat(self, model, messages, **kwargs)

    monkeypatch.setattr(MockProvider, "chat", slow_chat)

    auto(
        task="给每个源文件追加一个标记函数，用于标识 swarm 处理记录。",
        repo=".",
        parallel=3,
        dry_merge=True,
    )

    run_dir = sorted((repo / ".swarm" / "runs").iterdir())[-1]
    run_id = run_dir.name

    # 1. The generic planner produced one task per source file.
    task_payload = json.loads((run_dir / "file_tasks.json").read_text(encoding="utf-8"))
    task_ids = [task["task_id"] for task in task_payload]
    assert len(task_payload) == 3, f"expected 3 per-file tasks, got {len(task_payload)}: {task_ids}"
    assigned = {task["assigned_files"][0] for task in task_payload}
    assert assigned == {"src/alpha.py", "src/beta.py", "src/gamma.py"}

    # 2. Tasks were spread across multiple slots (different pseudo-agents).
    dispatch_report = json.loads((run_dir / "dispatch_report.json").read_text(encoding="utf-8"))
    used_slots = set(dispatch_report["used_slots"])
    assert len(used_slots) >= 2, f"expected >=2 distinct slots, got {used_slots}"
    assert used_slots.issubset({"api_alpha", "api_beta", "api_gamma"})

    # 3. Every task passed guard.
    for item in dispatch_report["tasks"]:
        assert item["status"] == "passed", f"{item['task_id']} status={item['status']}"

    # 4. final.patch covers all three files.
    final_patch = (run_dir / "final.patch").read_text(encoding="utf-8")
    assert "src/alpha.py" in final_patch
    assert "src/beta.py" in final_patch
    assert "src/gamma.py" in final_patch

    # 5. Apply + validate.
    apply_run(run=run_id, allow_dirty=True, no_validate=False, allow_fallback_apply=False)

    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr

    # 6. Each source file now carries a swarm marker function.
    for module in ["alpha", "beta", "gamma"]:
        content = (repo / "src" / f"{module}.py").read_text(encoding="utf-8")
        assert "swarm_marker_src" in content, f"marker missing in src/{module}.py"


def test_max_concurrent_tasks_respected(tmp_path: Path, monkeypatch) -> None:
    """A slot with max_concurrent_tasks=2 can serve two tasks concurrently."""
    import asyncio
    from file_swarm.dispatcher import dispatch_run_async
    from file_swarm.models import ModelSlot
    from file_swarm.providers.mock_provider import MockProvider
    from file_swarm.run_state import RunState
    from file_swarm.slot_registry import SlotRegistry
    from file_swarm.task_planner import PlannedTask

    repo = tmp_path
    (repo / "src").mkdir()
    state = RunState(
        run_id="20260101010101000001",
        root=repo,
        user_request="concurrency demo",
        repo_root=str(repo),
    )
    state.ensure_dirs()
    state.save()
    (state.run_dir / "hard_constraints.yaml").write_text(
        "hard_constraints:\n  file_modification:\n    reject_out_of_scope_patch: true\n",
        encoding="utf-8",
    )
    (state.run_dir / "interface_contract.yaml").write_text("interface_contract: {}\n", encoding="utf-8")

    # Single slot allowing 2 concurrent tasks.
    slot = ModelSlot(
        id="shared_slot",
        provider="mock",
        base_url=None,
        base_url_env=None,
        api_key_env="MOCK_API_KEY",
        enabled=True,
        allowed_models=["mock-model"],
        default_model="mock-model",
        max_concurrent_tasks=2,
    )
    registry = SlotRegistry(slots={slot.id: slot})
    tasks = [
        PlannedTask(
            task_id=f"task_{i:03d}",
            task_type="patch_worker",
            assigned_files=[f"src/file_{i}.py"],
            allowed_files=[f"src/file_{i}.py"],
            readonly_context_files=[],
            goal="demo",
            requirements=[],
            forbidden=[],
        )
        for i in range(1, 5)
    ]

    active = 0
    max_active = 0
    original_chat = MockProvider.chat

    async def tracked_chat(self, model, messages, **kwargs):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        try:
            await asyncio.sleep(0.08)
            return await original_chat(self, model, messages, **kwargs)
        finally:
            active -= 1

    monkeypatch.setattr(MockProvider, "chat", tracked_chat)

    results = asyncio.run(dispatch_run_async(state, tasks=tasks, registry=registry, parallel=4))

    # The single slot should have run 2 tasks concurrently (its configured max).
    assert max_active == 2, f"expected peak concurrency 2, got {max_active}"
    assert all(result.slot_id == "shared_slot" for result in results)
    assert all(result.status == "passed" for result in results)
