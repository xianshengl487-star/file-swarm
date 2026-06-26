from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .slot_registry import SlotRegistry


def _line(slot_id: str, provider: str, base_url: str, key_fingerprint: str, model: str, status: str, reason: str) -> str:
    return " | ".join([slot_id, provider, base_url, key_fingerprint, model, status, reason])


def run_preflight(repo_root: Path, model_slots_path: Path | None = None) -> str:
    if model_slots_path is None or not model_slots_path.exists():
        return "slot_id | provider | base_url | key_fingerprint | model | status | reason\n(no model_slots.yaml found)\n"

    registry = SlotRegistry.from_yaml(model_slots_path)
    lines = ["slot_id | provider | base_url | key_fingerprint | model | status | reason"]
    for slot in registry.slots.values():
        base_url = slot.base_url or (slot.base_url_env or "")
        api_key = registry.env_value(slot.api_key_env)
        key_fingerprint = SlotRegistry.key_fingerprint(api_key)
        if not slot.enabled:
            status = "disabled"
            reason = "slot disabled"
        elif not api_key:
            status = "missing_key"
            reason = f"env {slot.api_key_env} missing"
        elif slot.default_model not in slot.allowed_models:
            status = "invalid_default_model"
            reason = "default_model not allowed"
        else:
            status = "mock_ready" if slot.provider == "mock" else "ready"
            reason = "ok"
        lines.append(_line(slot.id, slot.provider, base_url, key_fingerprint, slot.default_model, status, reason))
    return "\n".join(lines) + "\n"
