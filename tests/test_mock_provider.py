import asyncio

from file_swarm.patch_guard import guard_patch
from file_swarm.providers.mock_provider import MockProvider


def test_mock_provider_demo_patch_is_valid() -> None:
    provider = MockProvider()
    prompt = (
        "TASK_ID: task_001\n"
        "ALLOWED_FILES:\n"
        "- src/demo_math.py\n"
        "- tests/test_demo_math.py\n"
        "USER_REQUEST: Add subtract(a: int, b: int) -> int and add tests.\n"
    )
    output = asyncio.run(provider.chat("mock-model", [{"role": "user", "content": prompt}]))

    assert "src/demo_math.py" in output
    assert "tests/test_demo_math.py" in output

    guard = guard_patch(
        output,
        ["src/demo_math.py", "tests/test_demo_math.py"],
        hard_constraints={
            "hard_constraints": {
                "file_modification": {"reject_file_deletion_by_default": True, "reject_out_of_scope_patch": True},
                "dependencies": {"forbidden_files": []},
            }
        },
    )
    assert guard.passed
