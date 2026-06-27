"""Patch normalizer: clean, validate, and repair LLM-generated unified diffs.

Common LLM output issues handled:
  1. Hunk header line-count mismatch (LLM miscounts)
  2. Missing ``a/`` / ``b/`` path prefixes
  3. Markdown artifacts (## Patch, extra ``` fences, stray headings)
  4. Trailing whitespace, inconsistent line endings
  5. Missing final newline
  6. Non-unified-diff content wrapping

All repairs are logged so the caller can audit what changed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(slots=True)
class NormalizeReport:
    ok: bool
    patch_text: str
    repairs: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    hunk_count: int = 0
    files: list[str] = field(default_factory=list)


# ── markdown artifact stripping ────────────────────────────────────────────


def _strip_markdown_headers(text: str) -> str:
    """Strip LLM markdown wrappers around the actual diff content."""
    lines = text.splitlines()
    start_idx = 0
    for idx, line in enumerate(lines):
        s = line.strip().lower()
        if s in {"## patch", "```diff", "```"}:
            start_idx = idx + 1
            break
        if s.startswith("--- ") or s.startswith("diff "):
            start_idx = idx
            break

    end_idx = len(lines)
    for idx in range(start_idx, len(lines)):
        s = lines[idx].strip()
        if s.startswith("## ") and not s.lower().startswith("## patch"):
            end_idx = idx
            break

    return "\n".join(lines[start_idx:end_idx])


def _strip_stray_fences(text: str) -> str:
    """Remove leftover ``` markers that survived diff-block extraction."""
    out = [line for line in text.splitlines() if line.strip() not in {"```", "```diff", "```patch"}]
    return "\n".join(out)


def _normalize_patch_paths(text: str) -> tuple[str, int]:
    """Ensure --- and +++ lines carry a/ and b/ prefixes."""
    lines = text.splitlines()
    out: list[str] = []
    repairs = 0
    for line in lines:
        if line.startswith("--- ") and not line.startswith("--- a/") and not line.startswith("--- /dev/null"):
            path = line[4:].strip()
            out.append(f"--- a/{path}")
            repairs += 1
        elif line.startswith("+++ ") and not line.startswith("+++ b/") and not line.startswith("+++ /dev/null"):
            path = line[4:].strip()
            out.append(f"+++ b/{path}")
            repairs += 1
        else:
            out.append(line)
    return "\n".join(out), repairs


# ── hunk repair ────────────────────────────────────────────────────────────

_HUNK_HEADER = re.compile(r"^@@ -(\d+),?(\d*) \+(\d+),?(\d*) @@")


def _fix_hunk_counts(text: str) -> tuple[str, int]:
    """Fix LLM hunk count errors.

    LLMs sometimes miscount hunk line ranges. This repair recounts the actual
    context +/- lines in each hunk body and updates the header when the
    declared count doesn't match.

    Returns (fixed_text, number_of_fixed_hunks).
    """
    lines = text.splitlines()
    out: list[str] = []
    fixes = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        m = _HUNK_HEADER.match(line)
        if not m:
            out.append(line)
            i += 1
            continue

        old_start = int(m.group(1))
        old_count = int(m.group(2) or 1)
        new_start = int(m.group(3))
        new_count = int(m.group(4) or 1)

        # Scan hunk body lines until next hunk / file separator
        j = i + 1
        body_lines: list[str] = []
        while j < len(lines):
            nl = lines[j]
            if nl.startswith("@@") or nl.startswith("--- ") or nl.startswith("diff "):
                break
            body_lines.append(nl)
            j += 1

        # Trim trailing blank lines from the body — these are inter-file
        # separators produced during merge, not part of the diff content.
        while body_lines and not body_lines[-1].strip():
            body_lines.pop()

        actual_minus = sum(1 for l in body_lines if l.startswith("-") and not l.startswith("---"))
        actual_plus = sum(1 for l in body_lines if l.startswith("+") and not l.startswith("+++"))
        actual_context = sum(1 for l in body_lines if not l.startswith(("-", "+", "\\")))

        new_old = actual_context + actual_minus
        new_new = actual_context + actual_plus

        if new_old != old_count or new_new != new_count:
            out.append(f"@@ -{old_start},{new_old} +{new_start},{new_new} @@")
            fixes += 1
        else:
            out.append(line)

        out.extend(body_lines)
        i = j

    return "\n".join(out), fixes


# ── whitespace / ending normalization ──────────────────────────────────────


def _normalize_whitespace(text: str) -> str:
    """Strip trailing whitespace, trim leading/trailing blank lines."""
    lines: list[str] = []
    for line in text.splitlines():
        # A blank context line in unified diff is represented as a single
        # leading space. Stripping it turns a valid hunk into an invalid one.
        if line == " ":
            lines.append(line)
        else:
            lines.append(line.rstrip())
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


# ── content validation ─────────────────────────────────────────────────────


def _validate_patch_structure(text: str) -> list[str]:
    """Check that the text looks like a valid unified diff. Returns errors."""
    errors: list[str] = []
    lines = text.splitlines()
    if not any(line.startswith("--- ") for line in lines):
        errors.append("missing --- header lines")
    if not any(line.startswith("+++ ") for line in lines):
        errors.append("missing +++ header lines")
    if not any(line.startswith("@@") for line in lines):
        errors.append("missing hunk headers (@@)")
    return errors


# ── main entry ─────────────────────────────────────────────────────────────


def normalize_patch(raw_text: str) -> NormalizeReport:
    """Clean and repair an LLM-generated unified diff.

    Idempotent – safe to call on already-valid patches.
    """
    if not raw_text or not raw_text.strip():
        return NormalizeReport(ok=False, patch_text="", errors=["empty_input"])

    repairs: list[str] = []
    errors: list[str] = []
    text = raw_text

    # Phase 1 – markdown cleanup
    text = _strip_markdown_headers(text)
    text = _strip_stray_fences(text)

    # Phase 2 – path normalization
    text, path_fixes = _normalize_patch_paths(text)
    if path_fixes:
        repairs.append(f"normalized {path_fixes} path(s) (missing a/b prefix)")

    # Phase 3 – hunk count repair (the most valuable fix)
    fixed_text, hunk_fixes = _fix_hunk_counts(text)
    if hunk_fixes:
        repairs.append(f"fixed {hunk_fixes} hunk count(s)")
        text = fixed_text

    # Phase 4 – whitespace
    text = _normalize_whitespace(text)

    # Ensure exactly one trailing newline for valid output
    if text:
        text = text + "\n"

    # Phase 5 – structure validation
    errors = _validate_patch_structure(text)

    # Phase 6 – extract modified files
    files: list[str] = []
    for line in text.splitlines():
        if line.startswith("+++ ") and not line.startswith("+++ /dev/null"):
            raw = line[4:].strip()
            if raw.startswith("b/"):
                raw = raw[2:]
            files.append(raw)

    hunks = sum(1 for line in text.splitlines() if line.startswith("@@"))

    return NormalizeReport(
        ok=len(errors) == 0 and bool(text.strip()),
        patch_text=text,
        repairs=repairs,
        errors=errors,
        hunk_count=hunks,
        files=files,
    )
