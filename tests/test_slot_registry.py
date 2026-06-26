from pathlib import Path

from file_swarm.slot_registry import SlotRegistry


def test_model_slots_example_is_readable() -> None:
    registry = SlotRegistry.from_yaml(Path("configs/model_slots.example.yaml"))

    assert registry.slots
    first = next(iter(registry.slots.values()))
    assert first.default_model in first.allowed_models
    assert registry.validate_slot(first) == []
