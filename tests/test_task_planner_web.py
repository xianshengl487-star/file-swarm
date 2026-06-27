from pathlib import Path

from file_swarm.models import RepoScanResult
from file_swarm.task_planner import split_tasks


def test_split_tasks_includes_web_source_files() -> None:
    scan = RepoScanResult(
        root=Path("."),
        directories=["src", "tests"],
        files=[
            "src/index.html",
            "src/main.js",
            "src/scene.js",
            "src/materials.css",
            "src/types.ts",
            "tests/scene.test.js",
            "package.json",
        ],
        source_dirs=["src"],
        test_dirs=["tests"],
        config_files=["package.json"],
        test_command="npm test",
        project_type="node",
    )

    tasks = split_tasks(scan, "Improve the 3D web scene with better rendering modules.")

    assert [task.allowed_files for task in tasks] == [
        ["src/index.html"],
        ["src/main.js"],
        ["src/scene.js"],
        ["src/materials.css"],
        ["src/types.ts"],
    ]
    assert all(task.task_type == "patch_worker" for task in tasks)
    assert all(task.readonly_context_files == task.allowed_files for task in tasks)


def test_split_tasks_does_not_truncate_medium_web_project_at_twelve_files() -> None:
    files = [f"src/module_{index:02d}.js" for index in range(13)]
    scan = RepoScanResult(
        root=Path("."),
        directories=["src"],
        files=files,
        source_dirs=["src"],
        test_dirs=[],
        config_files=[],
        test_command=None,
        project_type="node",
    )

    tasks = split_tasks(scan, "Complete the medium 3D web project.")

    assert len(tasks) == 13
    assert tasks[-1].allowed_files == ["src/module_12.js"]
