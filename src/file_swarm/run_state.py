from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class RunState:
    run_id: str
    root: Path
    user_request: str = ""
    repo_root: str = ""
    status: str = "created"
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def run_dir(self) -> Path:
        return self.root / ".swarm" / "runs" / self.run_id

    def ensure_dirs(self) -> None:
        for sub in ["transcripts", "patches", "guard_reports", "artifacts"]:
            (self.run_dir / sub).mkdir(parents=True, exist_ok=True)

    def save(self) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "run_id": self.run_id,
            "user_request": self.user_request,
            "repo_root": self.repo_root,
            "status": self.status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "data": self.data,
        }
        (self.run_dir / "run_state.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, root: Path, run_id: str) -> "RunState":
        run_dir = root / ".swarm" / "runs" / run_id
        payload = json.loads((run_dir / "run_state.json").read_text(encoding="utf-8"))
        return cls(
            run_id=run_id,
            root=root,
            user_request=payload.get("user_request", ""),
            repo_root=payload.get("repo_root", ""),
            status=payload.get("status", "created"),
            data=payload.get("data", {}),
        )
