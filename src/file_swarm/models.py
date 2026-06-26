from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ModelSlot:
    id: str
    provider: str
    base_url: str | None
    base_url_env: str | None
    api_key_env: str
    enabled: bool
    allowed_models: list[str]
    default_model: str
    max_concurrent_tasks: int = 1


@dataclass(slots=True)
class ModelWorker:
    worker_id: str
    task_id: str
    slot_id: str
    model: str
    worker_type: str = "stateless_patch_worker"
    assigned_files: list[str] = field(default_factory=list)
    allowed_files: list[str] = field(default_factory=list)


@dataclass(slots=True)
class HardConstraints:
    pass


@dataclass(slots=True)
class InterfaceContract:
    pass
