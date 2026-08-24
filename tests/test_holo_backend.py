from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from holoskill_gym.holo_backend import (
    HoloAuthenticationError,
    HoloBackend,
    HoloBackendConfig,
    HoloMalformedOutputError,
    HoloModelAccessError,
    HoloProviderError,
    HoloRateLimitError,
    HoloTruncatedOutputError,
)

VALID_PROPOSAL = {
    "diagnosis": ["Measurements are noisy."],
    "edits": [
        {
            "operation": "replace",
            "section": "Measure",
            "old_text": "Run once.",
            "new_text": "Run three times.",
            "rationale": "Use a robust aggregate.",
            "evidence_ids": ["train-1"],
        }
    ],
    "expected_effects": ["Less measurement noise."],
    "risks": ["Longer runtime."],
}


class FakeCompletions:
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeClient:
    def __init__(self, outcomes: list[object]) -> None:
        self.completions = FakeCompletions(outcomes)
        self.chat = SimpleNamespace(completions=self.completions)


class FakeProviderError(Exception):
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__("provider details that must not be persisted")


def response(
    *,
    content: str | None = None,
    finish_reason: str = "stop",
    prompt_tokens: int = 100,
    completion_tokens: int = 200,
) -> SimpleNamespace:
    return SimpleNamespace(
        id="resp-safe-id",
        model="holo3-1-35b-a3b",
        choices=[
            SimpleNamespace(
                finish_reason=finish_reason,
                message=SimpleNamespace(content=content),
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
    )


def config(**overrides: object) -> HoloBackendConfig:
    values: dict[str, object] = {
        "api_key": "not-a-real-secret",
        "initial_backoff_seconds": 0,
        "max_backoff_seconds": 0,
    }
    values.update(overrides)
    return HoloBackendConfig(**values)  # type: ignore[arg-type]


def test_propose_uses_strict_schema_without_tools_or_reasoning_effort() -> None:
    client = FakeClient([response(content=json.dumps(VALID_PROPOSAL))])
    backend = HoloBackend(config(max_completion_tokens=9_999), client=client)

    result = backend.propose(system="system", user="user")

    call = client.completions.calls[0]
    assert call["max_completion_tokens"] == 4_096
    assert call["response_format"]["type"] == "json_schema"  # type: ignore[index]
    assert call["response_format"]["json_schema"]["strict"] is True  # type: ignore[index]
    assert "tools" not in call
    assert "reasoning_effort" not in call
    assert result.proposal.edits[0].operation == "replace"
    assert result.call.usage.total_tokens == 300
    assert backend.records == (result.call,)


def test_malformed_json_fails_safely() -> None:
    backend = HoloBackend(config(), client=FakeClient([response(content="not json")]))

    with pytest.raises(HoloMalformedOutputError) as exc_info:
        backend.propose(system="system", user="user")

    assert exc_info.value.to_safe_dict()["type"] == "malformed_output"
    assert backend.records == ()


def test_empty_length_limited_response_is_truncation() -> None:
    backend = HoloBackend(
        config(),
        client=FakeClient([response(content=None, finish_reason="length")]),
    )

    with pytest.raises(HoloTruncatedOutputError):
        backend.propose(system="system", user="user")


def test_retryable_failure_retries_then_records_attempt_count() -> None:
    sleeps: list[float] = []
    client = FakeClient(
        [
            FakeProviderError(500),
            response(content=json.dumps(VALID_PROPOSAL)),
        ]
    )
    backend = HoloBackend(config(), client=client, sleep=sleeps.append)

    result = backend.propose(system="system", user="user")

    assert len(client.completions.calls) == 2
    assert sleeps == [0]
    assert result.call.attempts == 2


@pytest.mark.parametrize(
    ("status", "error_type"),
    [
        (401, HoloAuthenticationError),
        (402, HoloModelAccessError),
        (429, HoloRateLimitError),
    ],
)
def test_provider_errors_are_classified(status: int, error_type: type[Exception]) -> None:
    backend = HoloBackend(
        config(max_attempts=1),
        client=FakeClient([FakeProviderError(status)]),
    )

    with pytest.raises(error_type):
        backend.propose(system="system", user="user")


def test_error_metadata_does_not_include_provider_message() -> None:
    backend = HoloBackend(
        config(max_attempts=1),
        client=FakeClient([FakeProviderError(500)]),
    )

    with pytest.raises(HoloProviderError) as exc_info:
        backend.propose(system="system", user="user")

    assert "provider details" not in str(exc_info.value)
    assert exc_info.value.to_safe_dict()["status_code"] == 500
