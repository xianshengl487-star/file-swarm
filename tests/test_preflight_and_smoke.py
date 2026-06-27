import asyncio
from types import SimpleNamespace
from pathlib import Path

from file_swarm.providers.anthropic_provider import AnthropicProvider
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


def test_anthropic_mimo_live_preflight_passes_with_ok_period(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MIMO_TEST_API_KEY", "test-key-not-real")
    slots_path = _write_slots(
        tmp_path,
        "model_slots:\n"
        "  - id: mimo_anthropic_pro\n"
        "    provider: anthropic\n"
        "    base_url: https://token-plan-cn.xiaomimimo.com/anthropic\n"
        "    api_key_env: MIMO_TEST_API_KEY\n"
        "    enabled: true\n"
        "    allowed_models: [mimo-v2.5-pro]\n"
        "    default_model: mimo-v2.5-pro\n",
    )

    async def fake_chat(self, model: str, messages: list[dict], **kwargs):
        return ProviderResult(ok=True, text="OK.", model=model, provider="anthropic")

    monkeypatch.setattr(AnthropicProvider, "chat", fake_chat)

    report = run_preflight(tmp_path, slots_path, live=True)

    assert "mimo_anthropic_pro" in report
    assert "live_ok" in report


def test_anthropic_mimo_live_smoke_test_requires_real_diff(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MIMO_TEST_API_KEY", "test-key-not-real")
    slots_path = _write_slots(
        tmp_path,
        "model_slots:\n"
        "  - id: mimo_anthropic_mm\n"
        "    provider: anthropic\n"
        "    base_url: https://token-plan-cn.xiaomimimo.com/anthropic\n"
        "    api_key_env: MIMO_TEST_API_KEY\n"
        "    enabled: true\n"
        "    allowed_models: [mimo-v2.5]\n"
        "    default_model: mimo-v2.5\n",
    )
    diff = "--- a/hello.py\n+++ b/hello.py\n@@ -1,2 +1,2 @@\n def hello():\n-    return \"hello\"\n+    return \"hello world\"\n"

    async def fake_chat(self, model: str, messages: list[dict], **kwargs):
        prompt = messages[0]["content"]
        if prompt == "Reply with OK.":
            return ProviderResult(ok=True, text="OK.", model=model, provider="anthropic")
        return ProviderResult(ok=True, text=diff, model=model, provider="anthropic")

    monkeypatch.setattr(AnthropicProvider, "chat", fake_chat)

    result = run_smoke_test(tmp_path, slots_path, live=True)

    assert result.status == "passed"
    assert result.patch_text == diff


def test_live_smoke_test_uses_next_keyed_slot_when_first_slot_has_no_key(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("NVIDIA_MISSING_KEY", raising=False)
    monkeypatch.setenv("MIMO_TEST_API_KEY", "test-key-not-real")
    slots_path = _write_slots(
        tmp_path,
        "model_slots:\n"
        "  - id: nvidia_without_key\n"
        "    provider: openai_compatible\n"
        "    base_url: https://integrate.api.nvidia.com/v1\n"
        "    api_key_env: NVIDIA_MISSING_KEY\n"
        "    enabled: true\n"
        "    allowed_models: [z-ai/glm-5.1]\n"
        "    default_model: z-ai/glm-5.1\n"
        "  - id: mimo_anthropic_pro\n"
        "    provider: anthropic\n"
        "    base_url: https://token-plan-cn.xiaomimimo.com/anthropic\n"
        "    api_key_env: MIMO_TEST_API_KEY\n"
        "    enabled: true\n"
        "    allowed_models: [mimo-v2.5-pro]\n"
        "    default_model: mimo-v2.5-pro\n",
    )
    diff = "--- a/hello.py\n+++ b/hello.py\n@@ -1,2 +1,2 @@\n def hello():\n-    return \"hello\"\n+    return \"hello world\"\n"
    seen_models: list[str] = []

    async def fake_chat(self, model: str, messages: list[dict], **kwargs):
        seen_models.append(model)
        prompt = messages[0]["content"]
        if prompt == "Reply with OK.":
            return ProviderResult(ok=True, text="OK", model=model, provider="anthropic")
        return ProviderResult(ok=True, text=diff, model=model, provider="anthropic")

    monkeypatch.setattr(AnthropicProvider, "chat", fake_chat)

    result = run_smoke_test(tmp_path, slots_path, live=True)

    assert result.status == "passed"
    assert "slot_id: mimo_anthropic_pro" in result.report_text
    assert seen_models == ["mimo-v2.5-pro", "mimo-v2.5-pro"]


def test_openai_compatible_empty_response_is_provider_failure(monkeypatch) -> None:
    class FakeCompletions:
        async def create(self, **kwargs):
            usage = SimpleNamespace(prompt_tokens=5, completion_tokens=0)
            message = SimpleNamespace(content="")
            return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)

    class FakeClient:
        def __init__(self):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(OpenAICompatibleProvider, "_client", lambda self: FakeClient())
    provider = OpenAICompatibleProvider(base_url="https://token-plan-cn.xiaomimimo.com/v1", api_key="test-key")

    result = asyncio.run(provider.chat(model="mimo-v2.5-pro", messages=[{"role": "user", "content": "Reply with OK."}]))

    assert result.ok is False
    assert result.error == "empty_response"
    assert result.input_tokens == 5
    assert result.output_tokens == 0
