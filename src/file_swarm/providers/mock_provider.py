from __future__ import annotations

from dataclasses import dataclass
import difflib

from .base import ProviderResult


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

    def _mouse_clicker_patch(self, allowed_files: list[str]) -> str:
        patches: list[str] = []
        if "src/clicker_core.py" in allowed_files:
            old = '"""Safe domain primitives for a mouse clicker demo."""\n\n'
            new = '''"""Safe domain primitives for a mouse clicker demo.

The demo deliberately models click behavior as data. It never touches the
operating system mouse API, which keeps tests deterministic and safe.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ClickProfile:
    name: str
    interval_ms: int
    burst_count: int
    start_hotkey: str = "F6"
    stop_hotkey: str = "F7"

    def clicks_per_second(self) -> float:
        return round(1000 / self.interval_ms, 2)


def build_default_profile() -> ClickProfile:
    return ClickProfile(name="Focus Tap", interval_ms=120, burst_count=5)


def validate_profile(profile: ClickProfile) -> list[str]:
    issues: list[str] = []
    if profile.interval_ms < 40:
        issues.append("interval_ms must be at least 40 for safety")
    if profile.burst_count < 1 or profile.burst_count > 50:
        issues.append("burst_count must be between 1 and 50")
    if profile.start_hotkey == profile.stop_hotkey:
        issues.append("start and stop hotkeys must differ")
    return issues


def build_click_schedule(profile: ClickProfile) -> tuple[int, ...]:
    issues = validate_profile(profile)
    if issues:
        raise ValueError("; ".join(issues))
    return tuple(index * profile.interval_ms for index in range(profile.burst_count))
'''
            patches.append(self._patch_from_strings(old, new, "src/clicker_core.py"))
        if "src/clicker_ui.py" in allowed_files:
            old = '"""Presentation helpers for the mouse clicker demo."""\n\n'
            new = '''"""Presentation helpers for the mouse clicker demo."""

from __future__ import annotations

from .clicker_core import ClickProfile

THEME = {
    "surface": "graphite",
    "accent": "signal-lime",
    "warning": "ember",
    "shape": "rounded-control-deck",
}


def render_safety_banner() -> str:
    return "SAFE MODE: preview schedules only; no real mouse events are fired."


def render_control_card(profile: ClickProfile) -> str:
    lines = [
        f"[{THEME['accent']}] {profile.name}",
        f"speed: {profile.clicks_per_second()} clicks/sec",
        f"burst: {profile.burst_count} planned clicks",
        f"hotkeys: start {profile.start_hotkey} / stop {profile.stop_hotkey}",
        render_safety_banner(),
    ]
    return "\\n".join(lines)
'''
            patches.append(self._patch_from_strings(old, new, "src/clicker_ui.py"))
        if "tests/test_clicker_design.py" in allowed_files:
            old = '"""Tests generated by file-swarm in the collaboration demo."""\n\n'
            new = '''"""Tests generated by file-swarm in the collaboration demo."""

import pytest

from src.clicker_core import ClickProfile, build_click_schedule, build_default_profile, validate_profile
from src.clicker_ui import THEME, render_control_card, render_safety_banner


def test_default_profile_schedule_is_predictable():
    profile = build_default_profile()

    assert profile.name == "Focus Tap"
    assert build_click_schedule(profile) == (0, 120, 240, 360, 480)


def test_profile_validation_blocks_risky_click_settings():
    profile = ClickProfile(name="Too Fast", interval_ms=10, burst_count=100)

    assert validate_profile(profile) == [
        "interval_ms must be at least 40 for safety",
        "burst_count must be between 1 and 50",
    ]
    with pytest.raises(ValueError):
        build_click_schedule(profile)


def test_control_card_has_designed_copy_and_safety_banner():
    profile = ClickProfile(name="Boss Button", interval_ms=250, burst_count=3)
    card = render_control_card(profile)

    assert THEME["shape"] == "rounded-control-deck"
    assert "Boss Button" in card
    assert "4.0 clicks/sec" in card
    assert render_safety_banner() in card
    assert "no real mouse events" in card
'''
            patches.append(self._patch_from_strings(old, new, "tests/test_clicker_design.py"))
        return "\n".join(patches)

    async def chat(self, model: str, messages: list[dict], **kwargs) -> ProviderResult:
        user_text = "\n".join(str(message.get("content", "")) for message in messages)
        allowed_files = self._extract_allowed_files(user_text)

        if "Reply with OK." in user_text:
            return ProviderResult(ok=True, text="OK", model=model, provider="mock")

        if "subtract" in user_text and (
            "src/demo_math.py" in allowed_files or "tests/test_demo_math.py" in allowed_files
        ):
            patch = self._demo_math_patch(allowed_files)
        elif ("mouse clicker" in user_text.lower() or "auto clicker" in user_text.lower() or "连点器" in user_text) and (
            "src/clicker_core.py" in allowed_files
            or "src/clicker_ui.py" in allowed_files
            or "tests/test_clicker_design.py" in allowed_files
        ):
            patch = self._mouse_clicker_patch(allowed_files)
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

        text = (
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
        return ProviderResult(ok=True, text=text, model=model, provider="mock")
