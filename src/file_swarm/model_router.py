from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(slots=True)
class ModelRouter:
    routing: dict[str, list[str]]

    @classmethod
    def from_yaml(cls, path: Path) -> "ModelRouter":
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        routing = {
            name: list(block.get("preferred_models", []))
            for name, block in (data.get("model_routing") or {}).items()
        }
        return cls(routing=routing)

    def preferred_model(self, worker_type: str, fallback: str) -> str:
        options = self.routing.get(worker_type, [])
        return options[0] if options else fallback
