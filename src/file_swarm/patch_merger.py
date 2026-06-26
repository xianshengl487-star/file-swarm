from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .patch_normalizer import normalize_patch


@dataclass(slots=True)
class MergeResult:
    merged: bool
    conflict: bool
    final_patch_path: Path | None
    merge_report_path: Path
    modified_files: list[str]
    reason: str


def _load_guarded_patch_paths(run_dir: Path) -> list[Path]:
    patch_dir = run_dir / "patches"
    guard_dir = run_dir / "guard_reports"
    selected: list[Path] = []
    for patch_path in sorted(patch_dir.glob("*.patch")):
        guard_path = guard_dir / f"{patch_path.stem}.guard.json"
        if not guard_path.exists():
            continue
        try:
            payload = json.loads(guard_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if payload.get("passed") is True:
            selected.append(patch_path)
    return selected


def _extract_diff_block(text: str) -> str:
    """Extract a unified-diff block from provider output.

    Handles three common LLM output styles:
    1.  Fenced:   ``diff ... ``  (OpenAI-compatible models)
    2.  Bare:     ``` without language tag, then diff lines, then ```
    3.  Unfenced: plain diff lines mixed with markdown (Mimo, some GLMs)
    """
    if "```diff" in text:
        # Style 1 – explicit diff fence
        block = text.split("```diff", 1)[1]
        if "```" in block:
            block = block.split("```", 1)[0]
        return block.strip() + "\n"

    # Style 2 – some models use plain ``` without language tag
    if "```" in text:
        _, _, after = text.partition("```")
        if "--- " in after:
            block = after
            if "```" in block:
                block = block.split("```", 1)[0]
            return block.strip() + "\n"

    # Style 3 – unfenced: scan for the first --- a/ or diff --git line,
    # take everything until the next markdown heading or fence.
    for prefix in ("\n--- a/", "\n--- b/", "\ndiff --git ", "\n--- "):
        if prefix in text:
            idx = text.index(prefix)
            block = text[idx + 1:]  # skip the leading newline, keep ---
            cutoff = len(block)
            for marker in ("\n## ", "\n```"):
                pos = block.find(marker)
                if pos != -1 and pos < cutoff:
                    cutoff = pos
            return block[:cutoff].strip() + "\n"

    return text.strip() + "\n"


def _modified_files_from_patch(patch_text: str) -> list[str]:
    files: list[str] = []
    for line in patch_text.splitlines():
        if line.startswith("+++ ") and not line.startswith("+++ /dev/null"):
            raw = line[4:].strip()
            if raw.startswith("b/"):
                raw = raw[2:]
            files.append(raw)
    return files


def _normalize_patch_paths(patch_text: str) -> str:
    """Ensure ---/+++ lines carry a/ and b/ prefixes (some LLMs omit them)."""
    lines = patch_text.splitlines()
    out: list[str] = []
    for line in lines:
        if line.startswith("--- ") and not line.startswith("--- a/") and not line.startswith("--- /dev/null"):
            path = line[4:].strip()
            out.append(f"--- a/{path}")
        elif line.startswith("+++ ") and not line.startswith("+++ b/") and not line.startswith("+++ /dev/null"):
            path = line[4:].strip()
            out.append(f"+++ b/{path}")
        else:
            out.append(line)
    return "\n".join(out) + "\n"


def merge_patches(run_dir: Path) -> MergeResult:
    patch_paths = _load_guarded_patch_paths(run_dir)
    merge_report_path = run_dir / "merge_report.md"
    final_patch_path = run_dir / "final.patch"

    if not patch_paths:
        merge_report_path.write_text("status: skipped\nreason: no guard-passed patches\n", encoding="utf-8", newline="\n")
        return MergeResult(False, False, None, merge_report_path, [], "no guard-passed patches")

    merged_parts: list[str] = []
    seen_files: set[str] = set()
    modified_files: list[str] = []

    for patch_path in patch_paths:
        raw = patch_path.read_text(encoding="utf-8")
        norm = normalize_patch(raw)
        if not norm.ok:
            continue  # skip patches that can't be normalized
        patch_text = norm.patch_text
        files = norm.files
        overlap = seen_files.intersection(files)
        if overlap:
            merge_report_path.write_text(
                "\n".join(
                    [
                        "status: conflict",
                        f"reason: conflicting modifications for {', '.join(sorted(overlap))}",
                    ]
                )
                + "\n",
                encoding="utf-8",
                newline="\n",
            )
            if final_patch_path.exists():
                final_patch_path.unlink()
            return MergeResult(False, True, None, merge_report_path, modified_files + files, "conflict")
        seen_files.update(files)
        modified_files.extend(files)
        merged_parts.append(patch_text.rstrip())

    merged_text = "\n".join(merged_parts).strip() + "\n"
    final_patch_path.write_text(merged_text, encoding="utf-8", newline="\n")
    merge_report_path.write_text(
        "\n".join(
            [
                "status: merged",
                f"patch_count: {len(patch_paths)}",
                f"modified_files: {', '.join(modified_files) if modified_files else 'none'}",
            ]
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return MergeResult(True, False, final_patch_path, merge_report_path, modified_files, "merged")
