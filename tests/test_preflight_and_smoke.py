from pathlib import Path

from file_swarm.providers.base import ProviderResult
from file_swarm.providers.openai_compatible_provider import OpenAICompatibleProvider
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


def test_mock_smoke_test_can_fallback_and_pass(tmp_path: Path, monkeypatch) -> None:
    slots_path = _write_slots(
        tmp_path,
        "model_slots:\n  - id: mock1\n    provider: mock\n    api_key_env: MOCK_API_KEY\n    enabled: true\n    allowed_models: [mock-model]\n    default_model: mock-model\n",
    )

    result = run_smoke_test(tmp_path, slots_path, live=False)

    assert result.status == "passed"
    assert "--- a/hello.py" in result.patch_text


def test_live_smoke_test_cannot_fallback_on_non_diff(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LIVE_API_KEY", "test-key-not-real")
    slots_path = _write_slots(
        tmp_path,
        "model_slots:\n  - id: live1\n    provider: openai_compatible\n    base_url: https://example.com/v1\n    api_key_env: LIVE_API_KEY\n    enabled: true\n    allowed_models: [demo-model]\n    default_model: demo-model\n",
    )

    async def fake_chat(self, model: str, messages: list[dict], **kwargs):
        prompt = messages[0]["content"]
        if prompt == "Reply with OK.":
            return ProviderResult(ok=True, text="OK", model=model, provider="openai_compatible")
        return ProviderResult(ok=True, text="not a diff", model=model, provider="openai_compatible")

    monkeypatch.setattr(OpenAICompatibleProvider, "chat", fake_chat)

    result = run_smoke_test(tmp_path, slots_path, live=True)

    assert result.status == "failed"
    assert "model did not return unified diff patch" in result.report_text
    assert result.patch_text == ""


def test_live_smoke_test_passes_with_real_diff_shape(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LIVE_API_KEY", "test-key-not-real")
    slots_path = _write_slots(
        tmp_path,
        "model_slots:\n  - id: live1\n    provider: openai_compatible\n    base_url: https://example.com/v1\n    api_key_env: LIVE_API_KEY\n    enabled: true\n    allowed_models: [demo-model]\n    default_model: demo-model\n",
    )
    diff = "--- a/hello.py\n+++ b/hello.py\n@@ -1,2 +1,2 @@\n def hello():\n-    return \"hello\"\n+    return \"hello world\"\n"

    async def fake_chat(self, model: str, messages: list[dict], **kwargs):
        prompt = messages[0]["content"]
        if prompt == "Reply with OK.":
            return ProviderResult(ok=True, text="OK", model=model, provider="openai_compatible")
        return ProviderResult(ok=True, text=diff, model=model, provider="openai_compatible")

    monkeypatch.setattr(OpenAICompatibleProvider, "chat", fake_chat)

    result = run_smoke_test(tmp_path, slots_path, live=True)

    assert result.status == "passed"
    assert result.patch_text == diff
