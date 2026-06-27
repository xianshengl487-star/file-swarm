from pathlib import Path

from file_swarm.patch_apply import apply_patch_text
from file_swarm.patch_normalizer import normalize_patch


def test_normalizer_preserves_blank_context_line() -> None:
    raw = (
        "--- a/src/example.py\n"
        "+++ b/src/example.py\n"
        "@@ -1,4 +1,6 @@\n"
        " line_one = 1\n"
        " \n"
        " def value() -> int:\n"
        "     return 1\n"
        "+\n"
        "+extra = 2\n"
    )

    normalized = normalize_patch(raw)

    assert normalized.ok
    assert "\n \n" in normalized.patch_text


def test_fallback_apply_uses_hunk_start_line(tmp_path: Path) -> None:
    source = tmp_path / "src" / "example.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "line_one = 1\n"
        "\n"
        "def value() -> int:\n"
        "    return 1\n",
        encoding="utf-8",
    )
    patch = tmp_path / "change.patch"
    patch.write_text(
        "--- a/src/example.py\n"
        "+++ b/src/example.py\n"
        "@@ -3,2 +3,5 @@\n"
        " def value() -> int:\n"
        "     return 1\n"
        "+\n"
        "+def marker() -> str:\n"
        "+    return \"ok\"\n",
        encoding="utf-8",
    )

    apply_patch_text(tmp_path, patch)

    assert "def marker() -> str:" in source.read_text(encoding="utf-8")


def test_fallback_apply_handles_multiple_files_with_blank_context(tmp_path: Path) -> None:
    first = tmp_path / "src" / "audit.py"
    second = tmp_path / "src" / "forecast.py"
    first.parent.mkdir(parents=True)
    first.write_text(
        '"""Audit helpers."""\n\n'
        "from __future__ import annotations\n\n\n"
        "def audit_label(event: str, actor: str) -> str:\n"
        "    return f\"{actor}:{event}\".lower()\n",
        encoding="utf-8",
    )
    second.write_text(
        '"""Forecast helpers."""\n\n'
        "from __future__ import annotations\n\n\n"
        "def moving_average(values: list[float]) -> float:\n"
        "    if not values:\n"
        "        return 0.0\n"
        "    return round(sum(values) / len(values), 2)\n",
        encoding="utf-8",
    )
    patch = tmp_path / "multi.patch"
    patch.write_text(
        "--- a/src/audit.py\n"
        "+++ b/src/audit.py\n"
        "@@ -5,3 +5,6 @@\n"
        " \n"
        " def audit_label(event: str, actor: str) -> str:\n"
        "     return f\"{actor}:{event}\".lower()\n"
        "+\n"
        "+def audit_marker() -> str:\n"
        "+    return \"ok\"\n"
        "--- a/src/forecast.py\n"
        "+++ b/src/forecast.py\n"
        "@@ -7,3 +7,6 @@\n"
        "     if not values:\n"
        "         return 0.0\n"
        "     return round(sum(values) / len(values), 2)\n"
        "+\n"
        "+def forecast_marker() -> str:\n"
        "+    return \"ok\"\n",
        encoding="utf-8",
    )

    apply_patch_text(tmp_path, patch)

    assert "def audit_marker() -> str:" in first.read_text(encoding="utf-8")
    assert "def forecast_marker() -> str:" in second.read_text(encoding="utf-8")
