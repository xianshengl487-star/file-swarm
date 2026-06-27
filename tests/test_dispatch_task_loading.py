import json
from pathlib import Path

from file_swarm.dispatcher import _load_tasks
from file_swarm.models import RepoScanResult


def test_load_tasks_accepts_utf8_bom(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    payload = [
        {
            "task_id": "task_001",
            "task_type": "patch_worker",
            "assigned_files": ["src/styles.css"],
            "allowed_files": ["src/styles.css"],
            "readonly_context_files": ["src/styles.css"],
            "goal": "Update CSS",
            "requirements": [],
            "forbidden": [],
        }
    ]
    (run_dir / "file_tasks.json").write_text(json.dumps(payload), encoding="utf-8-sig")
    scan = RepoScanResult(
        root=tmp_path,
        directories=["src"],
        files=["src/styles.css"],
        source_dirs=["src"],
        test_dirs=[],
        config_files=[],
        test_command=None,
        project_type="node",
    )

    tasks = _load_tasks(run_dir, scan, "Update CSS")

    assert len(tasks) == 1
    assert tasks[0].allowed_files == ["src/styles.css"]
