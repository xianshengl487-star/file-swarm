from pathlib import Path

from file_swarm.run_state import RunState
from file_swarm.summary import write_codex_summary


def _state(repo: Path) -> RunState:
    state = RunState(run_id="sum1", root=repo, user_request="demo", repo_root=str(repo))
    state.ensure_dirs()
    state.data["task_results"] = [
        {
            "task_id": "task_001",
            "slot_id": "mock1",
            "model": "mock-model",
            "provider": "mock",
            "status": "passed",
            "patch_path": "patches/task_001.patch",
            "modified_files": ["src/demo_math.py"],
            "is_mock": True,
        }
    ]
    state.save()
    (state.run_dir / "hard_constraints.yaml").write_text("hard_constraints: {}\n", encoding="utf-8")
    (state.run_dir / "interface_contract.yaml").write_text("interface_contract: {}\n", encoding="utf-8")
    (state.run_dir / "final.patch").write_text("--- a/src/demo_math.py\n+++ b/src/demo_math.py\n@@ -1 +1 @@\n-a\n+b\n", encoding="utf-8")
    (state.run_dir / "guard_reports" / "task_001.guard.json").write_text(
        '{"task_id":"task_001","passed":true,"reason":"passed","modified_files":["src/demo_math.py"]}\n',
        encoding="utf-8",
    )
    (state.run_dir / "merge_report.md").write_text("status: merged\n", encoding="utf-8")
    return state


def test_summary_contains_slots_models_and_modified_files(tmp_path: Path) -> None:
    state = _state(tmp_path)

    path = write_codex_summary(state)
    text = path.read_text(encoding="utf-8")

    assert "used_slots: mock1" in text
    assert "used_models: mock-model" in text
    assert "modified_files: src/demo_math.py" in text


def test_summary_recommends_no_when_task_rejected(tmp_path: Path) -> None:
    state = _state(tmp_path)
    (state.run_dir / "guard_reports" / "task_001.guard.json").write_text(
        '{"task_id":"task_001","passed":false,"reason":"out_of_scope","modified_files":["evil.py"]}\n',
        encoding="utf-8",
    )

    text = write_codex_summary(state).read_text(encoding="utf-8")

    assert "recommend_apply: no" in text
    assert "need_repair: yes" in text


def test_summary_recommends_no_when_final_patch_empty(tmp_path: Path) -> None:
    state = _state(tmp_path)
    (state.run_dir / "final.patch").write_text("", encoding="utf-8")

    text = write_codex_summary(state).read_text(encoding="utf-8")

    assert "final_patch_empty: yes" in text
    assert "recommend_apply: no" in text


def test_summary_recommends_yes_with_caution_for_guarded_dry_merge(tmp_path: Path) -> None:
    state = _state(tmp_path)

    text = write_codex_summary(state).read_text(encoding="utf-8")

    assert "recommend_apply: yes_with_caution" in text
