import asyncio
from pathlib import Path

from file_swarm.dispatcher import dispatch_run_async
from file_swarm.lease_manager import LeaseManager
from file_swarm.models import ModelSlot
from file_swarm.run_state import RunState
from file_swarm.slot_registry import SlotRegistry
from file_swarm.task_planner import PlannedTask
from file_swarm.providers.mock_provider import MockProvider


def test_async_dispatch_keeps_slot_exclusive(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path
    (repo / "src").mkdir()
    (repo / "tests").mkdir()
    state = RunState(run_id="20260101010101000000", root=repo, user_request="demo", repo_root=str(repo))
    state.ensure_dirs()
    state.save()
    (state.run_dir / "hard_constraints.yaml").write_text("hard_constraints: {}\n", encoding="utf-8")
    (state.run_dir / "interface_contract.yaml").write_text("interface_contract: {}\n", encoding="utf-8")

    registry = SlotRegistry(
        slots={
            "mock1": ModelSlot(
                id="mock1",
                provider="mock",
                base_url=None,
                base_url_env=None,
                api_key_env="MOCK_API_KEY",
                enabled=True,
                allowed_models=["mock-model"],
                default_model="mock-model",
                max_concurrent_tasks=1,
            )
        }
    )

    tasks = [
        PlannedTask(
            task_id="task_001",
            task_type="patch_worker",
            assigned_files=["src/task_a.py"],
            allowed_files=["src/task_a.py"],
            readonly_context_files=[],
            goal="Create task_a",
            requirements=[],
            forbidden=[],
        ),
        PlannedTask(
            task_id="task_002",
            task_type="patch_worker",
            assigned_files=["src/task_b.py"],
            allowed_files=["src/task_b.py"],
            readonly_context_files=[],
            goal="Create task_b",
            requirements=[],
            forbidden=[],
        ),
    ]

    active = 0
    max_active = 0
    original_chat = MockProvider.chat

    async def tracked_chat(self, model: str, messages: list[dict], **kwargs):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        try:
            await asyncio.sleep(0.05)
            return await original_chat(self, model, messages, **kwargs)
        finally:
            active -= 1

    monkeypatch.setattr(MockProvider, "chat", tracked_chat)

    results = asyncio.run(dispatch_run_async(state, tasks=tasks, registry=registry, parallel=2))

    assert max_active == 1
    assert all(result.status == "passed" for result in results)
    assert (state.run_dir / "patches" / "task_001.patch").exists()
    assert (state.run_dir / "patches" / "task_002.patch").exists()
