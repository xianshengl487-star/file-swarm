import asyncio
import json
from pathlib import Path

from file_swarm.dispatcher import dispatch_run_async
from file_swarm.models import ModelSlot
from file_swarm.providers.anthropic_provider import AnthropicProvider
from file_swarm.providers.base import ProviderResult
from file_swarm.providers.mock_provider import MockProvider
from file_swarm.providers.openai_compatible_provider import OpenAICompatibleProvider
from file_swarm.run_state import RunState
from file_swarm.slot_registry import SlotRegistry
from file_swarm.task_planner import PlannedTask


def _task(task_id: str, path: str) -> PlannedTask:
    return PlannedTask(
        task_id=task_id,
        task_type="patch_worker",
        assigned_files=[path],
        allowed_files=[path],
        readonly_context_files=[],
        goal=f"Create {path}",
        requirements=[],
        forbidden=[],
    )


def test_async_dispatch_uses_multiple_slots_without_reusing_busy_slot(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path
    (repo / "src").mkdir()
    state = RunState(run_id="20260101010101000000", root=repo, user_request="demo", repo_root=str(repo))
    state.ensure_dirs()
    state.save()
    (state.run_dir / "hard_constraints.yaml").write_text(
        "hard_constraints:\n  file_modification:\n    reject_out_of_scope_patch: true\n    reject_file_deletion_by_default: true\n",
        encoding="utf-8",
    )
    (state.run_dir / "interface_contract.yaml").write_text("interface_contract: {}\n", encoding="utf-8")

    registry = SlotRegistry(
        slots={
            slot_id: ModelSlot(
                id=slot_id,
                provider="mock",
                base_url=None,
                base_url_env=None,
                api_key_env="MOCK_API_KEY",
                enabled=True,
                allowed_models=["mock-model"],
                default_model="mock-model",
                max_concurrent_tasks=1,
            )
            for slot_id in ["mock1", "mock2"]
        }
    )
    tasks = [_task("task_001", "src/task_a.py"), _task("task_002", "src/task_b.py"), _task("task_003", "src/task_c.py")]

    active = 0
    max_active = 0
    active_by_slot: dict[str, int] = {}
    overlap_by_slot: list[str] = []
    original_chat = MockProvider.chat

    async def tracked_chat(self, model: str, messages: list[dict], **kwargs):
        nonlocal active, max_active
        task_line = str(messages[0]["content"]).splitlines()[0]
        task_id = task_line.split(": ", 1)[1]
        report = json.loads((state.run_dir / "dispatch_report.json").read_text()) if (state.run_dir / "dispatch_report.json").exists() else {}
        active += 1
        max_active = max(max_active, active)
        slot_events = [
            json.loads(line)
            for line in (state.run_dir / "timeline.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        slot_id = next(event["slot_id"] for event in reversed(slot_events) if event["event"] == "slot_acquired" and event["task_id"] == task_id)
        active_by_slot[slot_id] = active_by_slot.get(slot_id, 0) + 1
        if active_by_slot[slot_id] > 1:
            overlap_by_slot.append(slot_id)
        try:
            await asyncio.sleep(0.08)
            return await original_chat(self, model, messages, **kwargs)
        finally:
            active_by_slot[slot_id] -= 1
            active -= 1

    monkeypatch.setattr(MockProvider, "chat", tracked_chat)

    results = asyncio.run(dispatch_run_async(state, tasks=tasks, registry=registry, parallel=2))

    assert max_active == 2
    assert not overlap_by_slot
    assert {result.slot_id for result in results} == {"mock1", "mock2"}
    assert all(result.status == "passed" for result in results)
    for task in tasks:
        assert (state.run_dir / "transcripts" / f"{task.task_id}.input.md").exists()
        assert (state.run_dir / "transcripts" / f"{task.task_id}.output.md").exists()
        assert (state.run_dir / "transcripts" / f"{task.task_id}.meta.json").exists()
        assert (state.run_dir / "patches" / f"{task.task_id}.patch").exists()


def test_dispatch_failover_from_nvidia_rate_limit_and_mimo_v1_empty_response_to_mimo_anthropic(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = tmp_path
    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_text('VALUE = "old"\n', encoding="utf-8")
    config_dir = repo / ".swarm" / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "routing.yaml").write_text(
        "model_routing:\n"
        "  patch_worker:\n"
        "    preferred_models:\n"
        "      - z-ai/glm-5.1\n"
        "      - mimo-v2.5-pro\n",
        encoding="utf-8",
    )
    state = RunState(run_id="20260101010102000000", root=repo, user_request="change value", repo_root=str(repo))
    state.ensure_dirs()
    state.save()
    (state.run_dir / "hard_constraints.yaml").write_text(
        "hard_constraints:\n"
        "  file_modification:\n"
        "    reject_out_of_scope_patch: true\n"
        "    reject_file_deletion_by_default: true\n",
        encoding="utf-8",
    )
    (state.run_dir / "interface_contract.yaml").write_text("interface_contract: {}\n", encoding="utf-8")
    monkeypatch.setenv("TEST_NVIDIA_API_KEY", "test-nvidia-key")
    monkeypatch.setenv("TEST_MIMO_API_KEY", "test-mimo-key")

    registry = SlotRegistry(
        slots={
            "nvidia_glm": ModelSlot(
                id="nvidia_glm",
                provider="openai_compatible",
                base_url="https://integrate.api.nvidia.com/v1",
                base_url_env=None,
                api_key_env="TEST_NVIDIA_API_KEY",
                enabled=True,
                allowed_models=["z-ai/glm-5.1"],
                default_model="z-ai/glm-5.1",
                max_concurrent_tasks=1,
            ),
            "mimo_v1_pro": ModelSlot(
                id="mimo_v1_pro",
                provider="openai_compatible",
                base_url="https://token-plan-cn.xiaomimimo.com/v1",
                base_url_env=None,
                api_key_env="TEST_MIMO_API_KEY",
                enabled=True,
                allowed_models=["mimo-v2.5-pro"],
                default_model="mimo-v2.5-pro",
                max_concurrent_tasks=1,
            ),
            "mimo_anthropic_pro": ModelSlot(
                id="mimo_anthropic_pro",
                provider="anthropic",
                base_url="https://token-plan-cn.xiaomimimo.com/anthropic",
                base_url_env=None,
                api_key_env="TEST_MIMO_API_KEY",
                enabled=True,
                allowed_models=["mimo-v2.5-pro"],
                default_model="mimo-v2.5-pro",
                max_concurrent_tasks=1,
            ),
        }
    )
    diff = (
        "--- a/src/app.py\n"
        "+++ b/src/app.py\n"
        "@@ -1 +1 @@\n"
        "-VALUE = \"old\"\n"
        "+VALUE = \"new\"\n"
    )
    calls: list[tuple[str, str]] = []

    async def fake_openai_chat(self, model: str, messages: list[dict], **kwargs):
        calls.append((self.base_url, model))
        if "nvidia.com" in self.base_url:
            return ProviderResult(ok=False, error="rate_limit", model=model, provider="openai_compatible")
        return ProviderResult(ok=False, error="empty_response", model=model, provider="openai_compatible")

    async def fake_anthropic_chat(self, model: str, messages: list[dict], **kwargs):
        calls.append((self.base_url, model))
        return ProviderResult(ok=True, text=diff, model=model, provider="anthropic")

    monkeypatch.setattr(OpenAICompatibleProvider, "chat", fake_openai_chat)
    monkeypatch.setattr(AnthropicProvider, "chat", fake_anthropic_chat)

    results = asyncio.run(
        dispatch_run_async(
            state,
            tasks=[_task("task_001", "src/app.py")],
            registry=registry,
            parallel=1,
        )
    )

    assert results[0].status == "passed"
    assert results[0].slot_id == "mimo_anthropic_pro"
    assert results[0].model == "mimo-v2.5-pro"
    assert (state.run_dir / "patches" / "task_001.patch").read_text(encoding="utf-8") == diff
    assert calls == [
        ("https://integrate.api.nvidia.com/v1", "z-ai/glm-5.1"),
        ("https://token-plan-cn.xiaomimimo.com/v1", "mimo-v2.5-pro"),
        ("https://token-plan-cn.xiaomimimo.com/anthropic", "mimo-v2.5-pro"),
    ]
    timeline = [
        json.loads(line)
        for line in (state.run_dir / "timeline.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    failovers = [event for event in timeline if event["event"] == "slot_failover"]
    assert [event["reason"] for event in failovers] == ["rate_limit", "empty_response"]
    assert [event["from_slot_id"] for event in failovers] == ["nvidia_glm", "mimo_v1_pro"]
