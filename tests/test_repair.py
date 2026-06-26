from pathlib import Path

from file_swarm.repair import repair_run
from file_swarm.run_state import RunState


def _state(repo: Path, rejected: bool = True) -> RunState:
    state = RunState(
        run_id="repair1",
        root=repo,
        user_request="Add subtract(a: int, b: int) -> int and add tests.",
        repo_root=str(repo),
    )
    state.ensure_dirs()
    state.save()
    (state.run_dir / "hard_constraints.yaml").write_text("hard_constraints:\n  security: {}\n", encoding="utf-8")
    (state.run_dir / "interface_contract.yaml").write_text("interface_contract:\n  naming: {}\n", encoding="utf-8")
    (state.run_dir / "file_tasks.json").write_text(
        '[{"task_id":"task_001","task_type":"patch_worker","allowed_files":["src/demo_math.py","tests/test_demo_math.py"],"assigned_files":["src/demo_math.py"],"readonly_context_files":[]}]\n',
        encoding="utf-8",
    )
    (state.run_dir / "transcripts" / "task_001.input.md").write_text(
        "USER_REQUEST: Add subtract(a: int, b: int) -> int and add tests.\nALLOWED_FILES:\n- src/demo_math.py\n- tests/test_demo_math.py\n",
        encoding="utf-8",
    )
    (state.run_dir / "patches" / "task_001.patch").write_text("not a diff\n", encoding="utf-8")
    (state.run_dir / "guard_reports" / "task_001.guard.json").write_text(
        f'{{"task_id":"task_001","passed":{str(not rejected).lower()},"reason":"empty_patch","modified_files":[]}}\n',
        encoding="utf-8",
    )
    return state


def test_repair_generates_report_for_rejected_task(tmp_path: Path) -> None:
    state = _state(tmp_path, rejected=True)

    report_path = repair_run(state)

    text = report_path.read_text(encoding="utf-8")
    assert "repair_status:" in text
    assert "repair_task_001" in text
    assert (state.run_dir / "patches" / "repair_task_001.patch").exists()


def test_repair_input_contains_contracts(tmp_path: Path) -> None:
    state = _state(tmp_path, rejected=True)

    repair_run(state)

    text = (state.run_dir / "transcripts" / "repair_task_001.input.md").read_text(encoding="utf-8")
    assert "HARD_CONSTRAINTS_YAML" in text
    assert "INTERFACE_CONTRACT_YAML" in text
    assert "hard_constraints:" in text
    assert "interface_contract:" in text


def test_repair_skips_when_no_repairable_tasks(tmp_path: Path) -> None:
    state = _state(tmp_path, rejected=False)

    report_path = repair_run(state)

    assert "repair_status: skipped" in report_path.read_text(encoding="utf-8")
