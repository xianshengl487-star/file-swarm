from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


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
    scope: dict[str, Any] = field(default_factory=dict)
    file_modification: dict[str, Any] = field(default_factory=dict)
    dependencies: dict[str, Any] = field(default_factory=dict)
    public_api: dict[str, Any] = field(default_factory=dict)
    security: dict[str, Any] = field(default_factory=dict)
    execution: dict[str, Any] = field(default_factory=dict)
    validation: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class InterfaceContract:
    project_style: dict[str, Any] = field(default_factory=dict)
    naming: dict[str, Any] = field(default_factory=dict)
    error_handling: dict[str, Any] = field(default_factory=dict)
    return_values: dict[str, Any] = field(default_factory=dict)
    imports: dict[str, Any] = field(default_factory=dict)
    testing: dict[str, Any] = field(default_factory=dict)
    documentation: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RepoScanResult:
    root: Path
    directories: list[str]
    files: list[str]
    source_dirs: list[str]
    test_dirs: list[str]
    config_files: list[str]
    test_command: str | None
    project_type: str


@dataclass(slots=True)
class WorkerInput:
    task_id: str
    task_type: str
    user_request: str
    assigned_files: list[str]
    allowed_files: list[str]
    readonly_context_files: list[str]
    hard_constraints_yaml: str
    interface_contract_yaml: str
    repo_map: str


@dataclass(slots=True)
class TaskResult:
    task_id: str
    slot_id: str
    model: str
    provider: str
    status: str
    patch_path: str
    modified_files: list[str] = field(default_factory=list)
    error: str | None = None
