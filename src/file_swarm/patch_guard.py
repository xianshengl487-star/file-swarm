from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re
from typing import Any

import yaml


SECRET_PATTERNS = [
    re.compile(r"api[_-]?key", re.IGNORECASE),
    re.compile(r"authorization:", re.IGNORECASE),
    re.compile(r"bearer\s+[A-Za-z0-9._-]+", re.IGNORECASE),
    re.compile(r"cookie:", re.IGNORECASE),
    re.compile(r"\b(?:sk|tp|nvapi)-[A-Za-z0-9_\-]{16,}\b", re.IGNORECASE),
]

FORBIDDEN_BASENAMES = {
    ".env",
    ".env.local",
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
}


@dataclass(slots=True)
class GuardResult:
    passed: bool
    reason: str
    modified_files: list[str]


def load_hard_constraints(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _extract_paths(patch_text: str) -> tuple[list[str], list[str]]:
    modified: list[str] = []
    original: list[str] = []
    for line in patch_text.splitlines():
        if line.startswith("+++ ") or line.startswith("--- "):
            raw = line[4:].strip()
            if raw.startswith("a/") or raw.startswith("b/"):
                raw = raw[2:]
            if raw != "/dev/null":
                if line.startswith("+++ "):
                    modified.append(raw)
                else:
                    original.append(raw)
    return modified, original


def _has_secret(patch_text: str) -> bool:
    return any(pattern.search(patch_text) for pattern in SECRET_PATTERNS)


def _is_absolute_path(path: str) -> bool:
    return bool(re.match(r"^(?:[A-Za-z]:[\\/]|/)", path))


def guard_patch(
    patch_text: str,
    allowed_files: list[str],
    hard_constraints: dict[str, Any] | None = None,
    hard_constraints_path: Path | None = None,
) -> GuardResult:
    constraints = hard_constraints or load_hard_constraints(hard_constraints_path)
    hard = (constraints.get("hard_constraints") or {}) if constraints else {}
    file_modification = hard.get("file_modification", {})
    dependencies = hard.get("dependencies", {})
    reject_deletions = bool(file_modification.get("reject_file_deletion_by_default", True))
    reject_out_of_scope = bool(file_modification.get("reject_out_of_scope_patch", True))
    forbidden_files = {str(PurePosixPath(path)) for path in dependencies.get("forbidden_files", [])}

    # ── Extract the actual diff from LLM output (same 3-style logic as
    # patch_merger._extract_diff_block).
    if "```diff" in patch_text:
        # Style 1 – explicit diff fence
        patch_text = patch_text.split("```diff", 1)[1]
        if "```" in patch_text:
            patch_text = patch_text.split("```", 1)[0]
    elif "```" in patch_text:
        # Style 2 – bare ``` fence
        _, _, after = patch_text.partition("```")
        if "--- " in after:
            patch_text = after
            if "```" in patch_text:
                patch_text = patch_text.split("```", 1)[0]
    else:
        # Style 3 – unfenced: grab from first --- line to next heading/fence
        for prefix in ("\n--- a/", "\n--- "):
            if prefix in patch_text:
                idx = patch_text.index(prefix)
                block = patch_text[idx + 1:]
                cutoff = len(block)
                for marker in ("\n## ", "\n```"):
                    pos = block.find(marker)
                    if pos != -1 and pos < cutoff:
                        cutoff = pos
                patch_text = block[:cutoff]
                break

    stripped = patch_text.strip()
    if not stripped:
        return GuardResult(False, "empty_patch", [])
    if _has_secret(patch_text):
        return GuardResult(False, "secret_like_content_detected", [])

    modified_files, original_files = _extract_paths(patch_text)
    modified_files = sorted({path for path in modified_files if path})
    original_files = sorted({path for path in original_files if path})
    if not modified_files:
        return GuardResult(False, "no_file_changes_found", [])

    allowed_set = {str(PurePosixPath(path)) for path in allowed_files}
    all_paths = modified_files + original_files
    if any(_is_absolute_path(path) for path in all_paths):
        return GuardResult(False, "absolute_path_detected", modified_files)

    if reject_deletions and any(line.startswith("+++ /dev/null") for line in patch_text.splitlines()):
        return GuardResult(False, "file_deletion_rejected", modified_files)

    for path in all_paths:
        pure = PurePosixPath(path)
        if pure.name in FORBIDDEN_BASENAMES or str(pure) in forbidden_files:
            return GuardResult(False, f"forbidden_file:{path}", modified_files)
        if reject_out_of_scope and str(pure) not in allowed_set:
            return GuardResult(False, f"out_of_scope_file:{path}", modified_files)

    return GuardResult(True, "passed", modified_files)
