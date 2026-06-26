from pathlib import Path

from file_swarm.cli import auto


def _prepare_repo(repo: Path) -> None:
    (repo / "src").mkdir()
    (repo / "tests").mkdir()
    (repo / ".swarm").mkdir()
    (repo / ".swarm" / "config").mkdir(parents=True)
    (repo / ".swarm" / "config" / "model_slots.yaml").write_text(
        "model_slots:\n"
        "  - id: mock1\n"
        "    provider: mock\n"
        "    api_key_env: MOCK_API_KEY\n"
        "    enabled: true\n"
        "    allowed_models: [mock-model]\n"
        "    default_model: mock-model\n",
        encoding="utf-8",
    )


def test_auto_creates_run_outputs(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path
    _prepare_repo(repo)
    monkeypatch.chdir(repo)

    auto(task="demo task", repo=".", parallel=2, dry_merge=True)

    run_root = repo / ".swarm" / "runs"
    runs = sorted(run_root.iterdir())
    assert runs
    run_dir = runs[-1]

    assert (run_dir / "codex_summary.md").exists()
    assert (run_dir / "final.patch").exists()
    assert (run_dir / "validation_report.md").exists()
    assert list((run_dir / "transcripts").glob("*.input.md"))
    assert list((run_dir / "transcripts").glob("*.output.md"))
    assert list((run_dir / "transcripts").glob("*.meta.json"))

    summary = (run_dir / "codex_summary.md").read_text(encoding="utf-8")
    assert "hard_constraints_loaded: yes" in summary
    assert "interface_contract_loaded: yes" in summary
