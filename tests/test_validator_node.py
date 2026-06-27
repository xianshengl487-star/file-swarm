from pathlib import Path
from types import SimpleNamespace

from file_swarm import validators


def test_npm_validation_uses_resolved_executable(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "package.json").write_text('{"scripts":{"test":"node tests/validate.mjs"}}', encoding="utf-8")
    calls: list[list[str]] = []

    def fake_which(name: str) -> str | None:
        if name == "npm":
            return "C:/Program Files/nodejs/npm.cmd"
        return None

    def fake_run(args, **kwargs):
        calls.append(list(args))
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(validators.shutil, "which", fake_which)
    monkeypatch.setattr(validators.subprocess, "run", fake_run)

    result = validators.run_validation(tmp_path, apply_mode=True)

    assert result.status == "passed"
    assert calls == [["C:/Program Files/nodejs/npm.cmd", "test"]]
