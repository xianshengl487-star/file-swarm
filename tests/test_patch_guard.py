from pathlib import Path

from file_swarm.patch_guard import guard_patch


def test_patch_guard_accepts_allowed_patch() -> None:
    patch = (
        "--- a/src/demo_math.py\n"
        "+++ b/src/demo_math.py\n"
        "@@ -1,2 +1,4 @@\n"
        " def add(a: int, b: int) -> int:\n"
        "     return a + b\n"
        "+\n"
        "+def subtract(a: int, b: int) -> int:\n"
        "+    return a - b\n"
    )

    result = guard_patch(
        patch,
        ["src/demo_math.py"],
        hard_constraints={
            "hard_constraints": {
                "file_modification": {"reject_file_deletion_by_default": True, "reject_out_of_scope_patch": True},
                "dependencies": {"forbidden_files": []},
            }
        },
    )

    assert result.passed


def test_patch_guard_rejects_forbidden_files() -> None:
    forbidden_cases = [
        "--- a/.env\n+++ b/.env\n@@ -0,0 +1,1 @@\n+SECRET=1\n",
        "--- a/package.json\n+++ b/package.json\n@@ -0,0 +1,1 @@\n+{}\n",
        "--- a/pyproject.toml\n+++ b/pyproject.toml\n@@ -0,0 +1,1 @@\n+[project]\n",
    ]
    for patch in forbidden_cases:
        result = guard_patch(
            patch,
            [".env", "package.json", "pyproject.toml"],
            hard_constraints={
                "hard_constraints": {
                    "file_modification": {"reject_file_deletion_by_default": True, "reject_out_of_scope_patch": True},
                    "dependencies": {"forbidden_files": ["package.json", "pyproject.toml", "requirements.txt"]},
                }
            },
        )
        assert not result.passed


def test_patch_guard_rejects_absolute_paths_and_secrets() -> None:
    absolute_patch = (
        "--- a/C:/temp/evil.py\n"
        "+++ b/C:/temp/evil.py\n"
        "@@ -0,0 +1,1 @@\n"
        "+print('bad')\n"
    )
    secret_patch = (
        "--- a/src/demo_math.py\n"
        "+++ b/src/demo_math.py\n"
        "@@ -1,1 +1,2 @@\n"
        " print('x')\n"
        "+API_KEY=tp-fakefakefakefakefakefakefakefake\n"
    )

    abs_result = guard_patch(absolute_patch, ["C:/temp/evil.py"])
    secret_result = guard_patch(secret_patch, ["src/demo_math.py"])

    assert not abs_result.passed
    assert not secret_result.passed
