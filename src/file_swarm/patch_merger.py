from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


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
        payload = guard_path.read_text(encoding="utf-8")
        if '"passed": true' in payload:
            selected.append(patch_path)
    return selected


def _extract_diff_block(text: str) -> str:
    if "```diff" in text:
        block = text.split("```diff", 1)[1]
        if "```" in block:
            block = block.rsplit("```", 1)[0]
        return block.strip() + "\n"
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
        patch_text = _extract_diff_block(patch_path.read_text(encoding="utf-8"))
        files = _modified_files_from_patch(patch_text)
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
