from __future__ import annotations

from seagym.logging.redaction import redact_sensitive


def test_numeric_token_usage_survives_redaction_but_credentials_do_not() -> None:
    redacted = redact_sensitive(
        {
            "input_tokens": 12,
            "completion_tokens": 7,
            "total_tokens": 19,
            "access_token": "secret-value",
            "authorization": "Bearer secret-value",
            "nested": {"API_KEY": "secret-value"},
        }
    )

    assert redacted["input_tokens"] == 12
    assert redacted["completion_tokens"] == 7
    assert redacted["total_tokens"] == 19
    assert redacted["access_token"] == "<redacted>"
    assert redacted["authorization"] == "<redacted>"
    assert redacted["nested"]["API_KEY"] == "<redacted>"
