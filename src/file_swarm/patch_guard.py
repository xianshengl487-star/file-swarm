from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
import re


SECRET_PATTERNS = [
    re.compile(r"api[_-]?key", re.IGNORECASE),
    re.compile(r"authorization:", re.IGNORECASE),
    re.compile(r"bearer\s+[A-Za-z0-9._-]+", re.IGNORECASE),
    re.compile(r"cookie:", re.IGNORECASE),
]


@dataclass(slots=True)
class GuardResult:
    passed: bool
    reason: str
    modified_files: list[str]


def _extract_paths(patch_text: str) -> list[str]:
    paths: list[str] = []
    for line in patch_text.splitlines():
        if line.startswith("+++ b/") or line.startswith("--- a/"):
            raw = line[6:]
            if raw != "/dev/null":
                paths.append(raw.strip())
    return paths


def _has_secret(patch_text: str) -> bool:
    return any(pattern.search(patch_text) for pattern in SECRET_PATTERNS)


def guard_patch(patch_text: str, allowed_files: list[str]) -> GuardResult:
    if "```diff" in patch_text:
        patch_text = patch_text.split("```diff", 1)[1]
        if "```" in patch_text:
            patch_text = patch_text.rsplit("```", 1)[0]
    modified_files = sorted({path for path in _extract_paths(patch_text) if path})
    if not modified_files:
        return GuardResult(False, "no_file_changes_found", [])
    allowed_set = {str(PurePosixPath(path)) for path in allowed_files}
    for path in modified_files:
        if str(PurePosixPath(path)) not in allowed_set:
            return GuardResult(False, f"out_of_scope_file:{path}", modified_files)
    if _has_secret(patch_text):
        return GuardResult(False, "secret_like_content_detected", modified_files)
    return GuardResult(True, "passed", modified_files)
