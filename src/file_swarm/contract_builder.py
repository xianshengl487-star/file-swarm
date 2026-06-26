from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


DEFAULT_HARD_CONSTRAINTS = {
    "hard_constraints": {
        "scope": {
            "allowed_root_dirs": ["src", "tests"],
            "forbidden_root_dirs": [".git", "node_modules", "dist", "build", "vendor", ".env", ".github/secrets"],
        },
        "file_modification": {
            "worker_can_modify_only_assigned_files": True,
            "reject_out_of_scope_patch": True,
            "reject_unlisted_file_creation": True,
            "reject_file_deletion_by_default": True,
            "require_patch_format": "unified_diff",
        },
        "dependencies": {
            "allow_new_dependencies": False,
            "allow_lockfile_changes": False,
        },
        "security": {
            "redact_secrets": True,
            "reject_raw_secret_output": True,
        },
        "execution": {
            "worker_can_run_shell": False,
            "worker_can_install_dependencies": False,
            "worker_can_directly_write_files": False,
            "worker_must_return_patch_only": True,
        },
        "validation": {
            "require_patch_guard": True,
            "require_final_summary": True,
            "require_validation_report": True,
        },
    }
}

DEFAULT_INTERFACE_CONTRACT = {
    "interface_contract": {
        "project_style": {
            "language": "auto_detect",
            "framework": "auto_detect",
            "follow_existing_style": True,
        },
        "naming": {"functions": "follow_existing", "classes": "follow_existing"},
        "testing": {"add_or_update_tests_when_behavior_changes": True},
    }
}


def write_contracts(run_dir: Path) -> tuple[Path, Path]:
    hard_path = run_dir / "hard_constraints.yaml"
    interface_path = run_dir / "interface_contract.yaml"
    hard_path.write_text(yaml.safe_dump(DEFAULT_HARD_CONSTRAINTS, sort_keys=False, allow_unicode=True), encoding="utf-8")
    interface_path.write_text(yaml.safe_dump(DEFAULT_INTERFACE_CONTRACT, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return hard_path, interface_path


def ensure_contracts(run_dir: Path) -> tuple[Path, Path]:
    hard_path = run_dir / "hard_constraints.yaml"
    interface_path = run_dir / "interface_contract.yaml"
    if not hard_path.exists() or not interface_path.exists():
        return write_contracts(run_dir)
    return hard_path, interface_path


def load_contract_texts(run_dir: Path) -> tuple[str, str]:
    hard_path, interface_path = ensure_contracts(run_dir)
    return hard_path.read_text(encoding="utf-8"), interface_path.read_text(encoding="utf-8")


def load_contract_dicts(run_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    hard_text, interface_text = load_contract_texts(run_dir)
    hard = yaml.safe_load(hard_text) or {}
    interface = yaml.safe_load(interface_text) or {}
    return hard, interface
