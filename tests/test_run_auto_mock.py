from pathlib import Path

from file_swarm.cli import auto


def test_auto_creates_run_outputs(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path
    (repo / "src").mkdir()
    (repo / "tests").mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    (repo / "configs").mkdir()
    (repo / "configs" / "hard_constraints.example.yaml").write_text("hard_constraints: {}\n", encoding="utf-8")
    (repo / "configs" / "interface_contract.example.yaml").write_text("interface_contract: {}\n", encoding="utf-8")
    (repo / "configs" / "policy.example.yaml").write_text("policy: {}\n", encoding="utf-8")
    (repo / ".swarm").mkdir()
    (repo / ".swarm" / "config").mkdir(parents=True)
    (repo / ".swarm" / "config" / "model_slots.yaml").write_text(
        "model_slots:\n  - id: mock1\n    provider: mock\n    api_key_env: NO_KEY\n    enabled: true\n    allowed_models: [mock-model]\n    default_model: mock-model\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(repo)

    auto(task="demo task", repo=".", parallel=1, dry_merge=True)

    runs = list((repo / ".swarm" / "runs").iterdir())
    assert runs
    run_dir = runs[0]
    assert (run_dir / "codex_summary.md").exists()
    assert (run_dir / "final.patch").exists()
