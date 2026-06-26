from file_swarm.transcript_logger import redact_text


def test_redacts_sk_key() -> None:
    assert "sk-secretsecretsecret" not in redact_text("key sk-secretsecretsecret")


def test_redacts_nvapi_key() -> None:
    assert "nvapi-secretsecretsecret" not in redact_text("key nvapi-secretsecretsecret")


def test_redacts_bearer_token() -> None:
    assert "Bearer abc.def-ghi" not in redact_text("Authorization: Bearer abc.def-ghi")


def test_redacts_json_api_key() -> None:
    text = redact_text('{"api_key": "abc123secret456"}')
    assert "abc123secret456" not in text


def test_redacts_env_style_key() -> None:
    text = redact_text("OPENAI_API_KEY=abc123secret456")
    assert "abc123secret456" not in text
