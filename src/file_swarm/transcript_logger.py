from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import re

from .slot_registry import SlotRegistry

REDACT_PATTERNS = [
    re.compile(r"Authorization:\s*Bearer\s+[^\s]+", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]+", re.IGNORECASE),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{12,}\b", re.IGNORECASE),
    re.compile(r"\bnvapi-[A-Za-z0-9_\-]{12,}\b", re.IGNORECASE),
    re.compile(r"\btp-[A-Za-z0-9_\-]{12,}\b", re.IGNORECASE),
    re.compile(r"api_key\s*=\s*[^\s]+", re.IGNORECASE),
    re.compile(r'"api_key"\s*:\s*"[^"]+"', re.IGNORECASE),
    re.compile(r"\b[A-Z0-9_]*(?:API_KEY|TOKEN|SECRET|KEY)\s*=\s*[^\s]+", re.IGNORECASE),
    re.compile(r"Cookie:\s*[^\s]+", re.IGNORECASE),
]


def redact_text(text: str) -> str:
    redacted = text
    for pattern in REDACT_PATTERNS:
        redacted = pattern.sub("[REDACTED_SECRET]", redacted)
    return redacted


def append_timeline_event(run_dir: Path, event_type: str, payload: dict[str, Any]) -> None:
    event = {
        "event": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **payload,
    }
    timeline_path = run_dir / "timeline.jsonl"
    timeline_path.parent.mkdir(parents=True, exist_ok=True)
    with timeline_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def log_worker_call(
    run_dir: Path,
    task_id: str,
    input_prompt: str,
    output_text: str,
    slot_id: str,
    provider: str,
    model: str,
    api_key: str | None,
    status: str,
    assigned_files: list[str],
    allowed_files: list[str],
    modified_files: list[str],
    provider_ok: bool | None = None,
    provider_error: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
) -> None:
    transcript_dir = run_dir / "transcripts"
    write_text(transcript_dir / f"{task_id}.input.md", redact_text(input_prompt))
    write_text(transcript_dir / f"{task_id}.output.md", redact_text(output_text))
    meta = {
        "task_id": task_id,
        "slot_id": slot_id,
        "provider": provider,
        "model": model,
        "key_fingerprint": SlotRegistry.key_fingerprint(api_key),
        "start_time": datetime.now(timezone.utc).isoformat(),
        "end_time": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "assigned_files": assigned_files,
        "allowed_files": allowed_files,
        "modified_files": modified_files,
        "provider_ok": provider_ok,
        "provider_error": redact_text(provider_error or "") or None,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }
    write_json(transcript_dir / f"{task_id}.meta.json", meta)
    append_timeline_event(run_dir, "worker_transcript_saved", meta)
