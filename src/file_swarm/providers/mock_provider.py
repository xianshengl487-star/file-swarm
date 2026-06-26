from __future__ import annotations

from dataclasses import dataclass
import difflib


@dataclass(slots=True)
class MockProvider:
    """Deterministic fallback used when no real API key is configured."""

    def _extract_allowed_files(self, text: str) -> list[str]:
        allowed: list[str] = []
        in_allowed = False
        for line in text.splitlines():
            stripped = line.strip()
            if stripped == "ALLOWED_FILES:":
                in_allowed = True
                continue
            if stripped.endswith(":") and in_allowed and not stripped.startswith("- "):
                if stripped != "ALLOWED_FILES:":
                    break
            if in_allowed and stripped.startswith("- "):
                allowed.append(stripped[2:].strip())
        return allowed

    def _patch_from_strings(self, old: str, new: str, path: str) -> str:
        diff = difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm="\n",
        )
        return "".join(diff)

    def _demo_math_patch(self, allowed_files: list[str]) -> str:
        patches: list[str] = []
        if "src/demo_math.py" in allowed_files:
            old = "def add(a: int, b: int) -> int:\n    return a + b\n"
            new = (
                "def add(a: int, b: int) -> int:\n    return a + b\n\n\n"
                "def subtract(a: int, b: int) -> int:\n    return a - b\n"
            )
            patches.append(self._patch_from_strings(old, new, "src/demo_math.py"))
        if "tests/test_demo_math.py" in allowed_files:
            old = "from src.demo_math import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n"
            new = (
                "from src.demo_math import add, subtract\n\n\n"
                "def test_add():\n    assert add(1, 2) == 3\n\n\n"
                "def test_subtract():\n    assert subtract(3, 1) == 2\n"
            )
            patches.append(self._patch_from_strings(old, new, "tests/test_demo_math.py"))
        return "\n".join(patches)

    def _hello_patch(self, allowed_files: list[str]) -> str:
        path = "hello.py" if "hello.py" in allowed_files else allowed_files[0]
        new = 'def hello() -> str:\n    return "OK"\n'
        return self._patch_from_strings("", new, path)

    async def chat(self, model: str, messages: list[dict], **kwargs) -> str:
        user_text = "\n".join(str(message.get("content", "")) for message in messages)
        allowed_files = self._extract_allowed_files(user_text)

        if "Reply with OK." in user_text:
            return "OK"

        if "subtract" in user_text and (
            "src/demo_math.py" in allowed_files or "tests/test_demo_math.py" in allowed_files
        ):
            patch = self._demo_math_patch(allowed_files)
        elif "hello.py" in user_text and allowed_files:
            patch = self._hello_patch(allowed_files)
        elif allowed_files:
            path = allowed_files[0]
            patch = self._patch_from_strings(
                "",
                'def generated_message() -> str:\n    return "file-swarm mock run"\n',
                path,
            )
        else:
            path = "src/file_swarm/mock_generated.py"
            patch = self._patch_from_strings(
                "",
                'def generated_message() -> str:\n    return "file-swarm mock run"\n',
                path,
            )

        return (
            "## Implementation Summary\n\n"
            f"Mock provider produced a deterministic patch for model {model}.\n\n"
            "## Patch\n\n"
            "```diff\n"
            f"{patch.rstrip()}\n"
            "```\n\n"
            "## Risk Notes\n\n"
            "This is a fallback implementation for local dry runs.\n\n"
            "## Suggested Tests\n\n"
            "Add or update focused tests for the changed files.\n\n"
            "## Input Echo\n\n"
            f"{user_text[:200]}\n"
        )
