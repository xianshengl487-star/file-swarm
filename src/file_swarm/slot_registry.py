from __future__ import annotations

import os
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any

import yaml

from .models import ModelSlot


@dataclass(slots=True)
class SlotRegistry:
    slots: dict[str, ModelSlot] = field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: Path) -> "SlotRegistry":
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        slots: dict[str, ModelSlot] = {}
        for item in data.get("model_slots", []):
            slot = ModelSlot(
                id=item["id"],
                provider=item["provider"],
                base_url=item.get("base_url"),
                base_url_env=item.get("base_url_env"),
                api_key_env=item["api_key_env"],
                enabled=bool(item.get("enabled", True)),
                allowed_models=list(item.get("allowed_models", [])),
                default_model=item["default_model"],
                max_concurrent_tasks=int(item.get("max_concurrent_tasks", 1)),
            )
            slots[slot.id] = slot
        return cls(slots=slots)

    def list_enabled(self) -> list[ModelSlot]:
        return [slot for slot in self.slots.values() if slot.enabled]

    def list_enabled_for_model(self, model: str | None = None) -> list[ModelSlot]:
        slots = self.list_enabled()
        if model is None:
            return slots
        return [slot for slot in slots if model in slot.allowed_models]

    def get(self, slot_id: str) -> ModelSlot:
        return self.slots[slot_id]

    def resolve_base_url(self, slot: ModelSlot) -> str | None:
        if slot.base_url:
            return slot.base_url
        if slot.base_url_env:
            return self.env_value(slot.base_url_env)
        return None

    def validate_slot(self, slot: ModelSlot) -> list[str]:
        issues: list[str] = []
        if not slot.enabled:
            issues.append("disabled")
        if not slot.allowed_models:
            issues.append("allowed_models empty")
        if slot.default_model not in slot.allowed_models:
            issues.append("default_model not allowed")
        if not slot.api_key_env:
            issues.append("api_key_env missing")
        if slot.provider not in {"openai_compatible", "mock", "anthropic"}:
            issues.append("unsupported provider")
        return issues

    @staticmethod
    def key_fingerprint(api_key: str | None) -> str:
        if not api_key:
            return "missing"
        digest = sha256(api_key.encode("utf-8")).hexdigest()
        return f"sha256:{digest[:12]}"

    @staticmethod
    def env_value(name: str | None) -> str | None:
        if not name:
            return None
        return os.environ.get(name)
