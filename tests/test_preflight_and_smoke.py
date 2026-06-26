from pathlib import Path

from file_swarm.preflight_checker import run_preflight, run_smoke_test


def _write_slots(repo: Path, text: str) -> Path:
    config_dir = repo / ".swarm" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    slots_path = config_dir / "model_slots.yaml"
    slots_path.write_text(text, encoding="utf-8")
    return slots_path


def test_preflight_missing_key_does_not_crash(tmp_path: Path) -> None:
    slots_path = _write_slots(
        tmp_path,
        "model_slots:\n  - id: live1\n    provider: openai_compatible\n    base_url: https://example.com/v1\n    api_key_env: LIVE_API_KEY\n    enabled: true\n    allowed_models: [demo-model]\n    default_model: demo-model\n",
    )

    report = run_preflight(tmp_path, slots_path, live=False)

    assert "live1" in report
    assert "mock_ready" in report or "ready" in report or "missing_key" in report


def test_mock_preflight_passes(tmp_path: Path) -> None:
    slots_path = _write_slots(
        tmp_path,
        "model_slots:\n  - id: mock1\n    provider: mock\n    api_key_env: MOCK_API_KEY\n    enabled: true\n    allowed_models: [mock-model]\n    default_model: mock-model\n",
    )

    report = run_preflight(tmp_path, slots_path, live=False)

    assert "mock_ready" in report


def test_live_preflight_without_key_is_skipped(tmp_path: Path) -> None:
    slots_path = _write_slots(
        tmp_path,
        "model_slots:\n  - id: live1\n    provider: openai_compatible\n    base_url: https://example.com/v1\n    api_key_env: LIVE_API_KEY\n    enabled: true\n    allowed_models: [demo-model]\n    default_model: demo-model\n",
    )

    report = run_preflight(tmp_path, slots_path, live=True)

    assert "skipped" in report


def test_smoke_test_live_produces_report_and_patch(tmp_path: Path) -> None:
    slots_path = _write_slots(
        tmp_path,
        "model_slots:\n  - id: mock1\n    provider: mock\n    api_key_env: MOCK_API_KEY\n    enabled: true\n    allowed_models: [mock-model]\n    default_model: mock-model\n",
    )

    result = run_smoke_test(tmp_path, slots_path, live=True)

    assert result.status == "passed"
    assert "hello.py" in result.report_text
    assert "hello.py" in result.patch_text
