from pathlib import Path

from file_swarm.transcript_logger import redact_text


def test_redact_text_masks_secrets() -> None:
    text = "Authorization: Bearer abc123\nAPI_KEY=secret\nCookie: x=y"
    redacted = redact_text(text)

    assert "abc123" not in redacted
    assert "secret" not in redacted
    assert "[REDACTED_SECRET]" in redacted
