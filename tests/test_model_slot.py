from file_swarm.models import ModelSlot


def test_model_slot_dataclass_fields() -> None:
    slot = ModelSlot(
        id="slot-1",
        provider="openai_compatible",
        base_url="https://example.com/v1",
        base_url_env=None,
        api_key_env="API_KEY",
        enabled=True,
        allowed_models=["model-a"],
        default_model="model-a",
    )

    assert slot.id == "slot-1"
    assert slot.default_model == "model-a"
