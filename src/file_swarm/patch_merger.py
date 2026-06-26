from __future__ import annotations

from pathlib import Path


def merge_patches(patch_paths: list[Path], final_patch_path: Path) -> str:
    parts: list[str] = []
    for patch_path in patch_paths:
        parts.append(patch_path.read_text(encoding="utf-8"))
    final_patch_path.parent.mkdir(parents=True, exist_ok=True)
    merged = "\n".join(part.strip() for part in parts if part.strip()) + ("\n" if parts else "")
    final_patch_path.write_text(merged, encoding="utf-8")
    return merged
