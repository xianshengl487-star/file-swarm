from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from .patch_merger import _extract_diff_block


_HUNK_HEADER = re.compile(r"^@@ -(\d+),?(\d*) \+(\d+),?(\d*) @@")


def _parse_hunks(patch_text: str) -> list[tuple[str, str, list[str]]]:
    files: list[tuple[str, str, list[str]]] = []
    lines = patch_text.splitlines()
    i = 0
    current_old: str | None = None
    current_new: str | None = None
    current_hunks: list[str] = []
    while i < len(lines):
        line = lines[i]
        if line.startswith("--- "):
            current_old = line[4:].strip()
            if current_old.startswith("a/"):
                current_old = current_old[2:]
            i += 1
            continue
        if line.startswith("+++ "):
            current_new = line[4:].strip()
            if current_new.startswith("b/"):
                current_new = current_new[2:]
            i += 1
            continue
        if line.startswith("@@ "):
            current_hunks.append(line)
            i += 1
            while i < len(lines) and not lines[i].startswith(("--- ", "+++ ", "@@ ")):
                current_hunks.append(lines[i])
                i += 1
            if current_old is not None and current_new is not None and current_hunks:
                files.append((current_old, current_new, current_hunks))
                current_old = None
                current_new = None
                current_hunks = []
            continue
        i += 1
    return files


def _apply_file_patch(repo_root: Path, old_path: str, new_path: str, hunks: list[str]) -> None:
    target_rel = new_path if new_path != "/dev/null" else old_path
    if target_rel == "/dev/null":
        raise ValueError("cannot apply patch with both paths as /dev/null")
    target = repo_root / target_rel
    original_lines = target.read_text(encoding="utf-8").splitlines() if target.exists() else []
    result_lines: list[str] = []
    source_index = 0
    hunk_index = 0
    while hunk_index < len(hunks):
        header = hunks[hunk_index]
        if not header.startswith("@@ "):
            hunk_index += 1
            continue
        match = _HUNK_HEADER.match(header)
        if not match:
            raise ValueError(f"invalid hunk header for {target_rel}")
        hunk_start = max(int(match.group(1)) - 1, 0)
        if hunk_start < source_index:
            raise ValueError(f"overlapping hunk for {target_rel}")
        result_lines.extend(original_lines[source_index:hunk_start])
        source_index = hunk_start
        hunk_index += 1
        while hunk_index < len(hunks) and not hunks[hunk_index].startswith("@@ "):
            diff_line = hunks[hunk_index]
            if diff_line.startswith(" "):
                expected = diff_line[1:]
                if source_index >= len(original_lines) or original_lines[source_index] != expected:
                    raise ValueError(f"patch context mismatch for {target_rel}")
                result_lines.append(expected)
                source_index += 1
            elif diff_line.startswith("-"):
                expected = diff_line[1:]
                if source_index >= len(original_lines) or original_lines[source_index] != expected:
                    raise ValueError(f"patch deletion mismatch for {target_rel}")
                source_index += 1
            elif diff_line.startswith("+"):
                result_lines.append(diff_line[1:])
            elif diff_line == "":
                result_lines.append("")
            hunk_index += 1
    result_lines.extend(original_lines[source_index:])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(result_lines) + "\n", encoding="utf-8")


def apply_patch_text(repo_root: Path, patch_path: Path) -> None:
    patch_text = _extract_diff_block(patch_path.read_text(encoding="utf-8"))
    for old_path, new_path, hunks in _parse_hunks(patch_text):
        _apply_file_patch(repo_root, old_path, new_path, hunks)
