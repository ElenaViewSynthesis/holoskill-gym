from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from holoskill_gym.inkling_backend import (
    DEFAULT_INKLING_MODEL,
    InklingAccessError,
    InklingBackend,
    InklingBackendConfig,
    InklingSampling,
)

PROPOSAL = {
    "diagnosis": ["Measurements are noisy."],
    "edits": [],
    "expected_effects": ["Stabler comparisons."],
    "risks": ["None."],
}


def fake_response(content: str = json.dumps(PROPOSAL)):
    return SimpleNamespace(
        id="resp-1",
        model=DEFAULT_INKLING_MODEL,
        choices=[
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(content=content),
            )
        ],
        usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7, total_tokens=18),
    )


class RecordingClient:
    """Capture the request kwargs so parameter plumbing can be asserted."""

    def __init__(self, response=None, error: Exception | None = None) -> None:
        self.calls: list[dict] = []
        self._response = response or fake_response()
        self._error = error
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return self._response


def config(**overrides) -> InklingBackendConfig:
    return InklingBackendConfig(api_key="test-key", **overrides)


def test_defaults_are_deterministic_not_chat_defaults() -> None:
    sampling = InklingSampling()

    # OpenRouter defaults temperature to 1 and has no seed. An optimizer that
    # drives an accept/reject gate must be reproducible instead.
    assert sampling.temperature == 0.0
    assert sampling.seed == 42
    assert sampling.top_p == 1.0
    assert sampling.max_tokens == 4096
    assert sampling.reasoning_enabled is True
    assert sampling.reasoning_effort == "medium"


def test_reasoning_payload_omits_unset_controls() -> None:
    assert InklingSampling().reasoning_payload() == {"enabled": True, "effort": "medium"}
    assert InklingSampling(reasoning_effort=None, reasoning_max_tokens=512).reasoning_payload() == {
        "enabled": True,
        "max_tokens": 512,
    }
    assert InklingSampling(reasoning_effort=None).reasoning_payload() == {"enabled": True}


def test_effort_and_max_tokens_are_mutually_exclusive() -> None:
    with pytest.raises(ValueError, match="not both"):
        InklingSampling(reasoning_effort="high", reasoning_max_tokens=256)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"temperature": 2.5},
        {"top_p": 0.0},
        {"max_tokens": 0},
        {"frequency_penalty": 3.0},
        {"presence_penalty": -3.0},
        {"reasoning_effort": "extreme"},
        {"reasoning_max_tokens": 0, "reasoning_effort": None},
    ],
)
def test_out_of_range_parameters_fail_closed(kwargs) -> None:
    with pytest.raises(ValueError):
        InklingSampling(**kwargs)


def test_every_parameter_reaches_the_request() -> None:
    client = RecordingClient()
    backend = InklingBackend(
        config(
            sampling=InklingSampling(
                temperature=0.3,
                top_p=0.9,
                max_tokens=1024,
                seed=7,
                frequency_penalty=0.5,
                presence_penalty=-0.5,
                stop=("STOP",),
                reasoning_effort="high",
            )
        ),
        client=client,
    )

    backend.propose(system="sys", user="usr")

    sent = client.calls[0]
    assert sent["temperature"] == 0.3
    assert sent["top_p"] == 0.9
    assert sent["max_tokens"] == 1024
    assert sent["seed"] == 7
    assert sent["frequency_penalty"] == 0.5
    assert sent["presence_penalty"] == -0.5
    assert sent["stop"] == ["STOP"]
    assert sent["extra_body"]["reasoning"] == {"enabled": True, "effort": "high"}
    assert sent["response_format"]["json_schema"]["strict"] is True


def test_seed_and_stop_are_omitted_when_unset() -> None:
    client = RecordingClient()
    backend = InklingBackend(
        config(sampling=InklingSampling(seed=None)),
        client=client,
    )

    backend.propose(system="sys", user="usr")

    assert "seed" not in client.calls[0]
    assert "stop" not in client.calls[0]


def test_mutation_never_sends_tools() -> None:
    client = RecordingClient()
    InklingBackend(config(), client=client).propose(system="sys", user="usr")

    # Tool calling would be an alternative patch format; the mutation call is
    # strict json_schema plus local validation by policy.
    assert "tools" not in client.calls[0]


def test_forbidden_model_is_a_distinct_access_error() -> None:
    error = Exception("only available on agentic harnesses")
    error.status_code = 403  # type: ignore[attr-defined]
    backend = InklingBackend(config(max_attempts=1), client=RecordingClient(error=error))

    with pytest.raises(InklingAccessError) as excinfo:
        backend.propose(system="sys", user="usr")

    details = excinfo.value.to_safe_dict()
    assert details["type"] == "model_access_denied"
    assert details["status_code"] == 403
    # The provider message may name the caller; it must not be echoed verbatim.
    assert "agentic harnesses" not in json.dumps(details)


def test_successful_proposal_records_usage() -> None:
    backend = InklingBackend(config(), client=RecordingClient())

    result = backend.propose(system="sys", user="usr")

    assert result.proposal.edits == []
    assert result.call.usage.total_tokens == 18
    assert result.call.model == DEFAULT_INKLING_MODEL
    assert len(backend.records) == 1


def test_headers_are_sent_only_when_configured() -> None:
    assert config().default_headers() == {}
    assert config(http_referer="https://example.invalid", x_title="T").default_headers() == {
        "HTTP-Referer": "https://example.invalid",
        "X-Title": "T",
    }


def test_empty_api_key_fails_closed() -> None:
    with pytest.raises(ValueError, match="api_key"):
        InklingBackendConfig(api_key="   ")


def test_cli_defaults_match_the_dataclass_defaults() -> None:
    import argparse

    from holoskill_gym.inkling_backend import add_sampling_arguments, sampling_from_args

    parser = add_sampling_arguments(argparse.ArgumentParser())

    # The command line is the source of truth for these knobs, so its defaults
    # must not drift from the library's.
    assert sampling_from_args(parser.parse_args([])) == InklingSampling()


def test_cli_overrides_every_sampling_parameter() -> None:
    import argparse

    from holoskill_gym.inkling_backend import add_sampling_arguments, sampling_from_args

    parser = add_sampling_arguments(argparse.ArgumentParser())
    sampling = sampling_from_args(
        parser.parse_args(
            [
                "--inkling-temperature",
                "0.7",
                "--inkling-top-p",
                "0.8",
                "--inkling-max-tokens",
                "256",
                "--inkling-seed",
                "9",
                "--inkling-frequency-penalty",
                "0.25",
                "--inkling-presence-penalty",
                "-0.25",
                "--inkling-stop",
                "END",
                "--inkling-stop",
                "STOP",
                "--inkling-reasoning-effort",
                "high",
                "--inkling-reasoning-exclude",
            ]
        )
    )

    assert sampling.temperature == 0.7
    assert sampling.top_p == 0.8
    assert sampling.max_tokens == 256
    assert sampling.seed == 9
    assert sampling.frequency_penalty == 0.25
    assert sampling.presence_penalty == -0.25
    assert sampling.stop == ("END", "STOP")
    assert sampling.reasoning_effort == "high"
    assert sampling.reasoning_exclude is True


def test_cli_can_unset_seed_and_effort() -> None:
    import argparse

    from holoskill_gym.inkling_backend import add_sampling_arguments, sampling_from_args

    parser = add_sampling_arguments(argparse.ArgumentParser())

    assert sampling_from_args(parser.parse_args(["--no-inkling-seed"])).seed is None
    payload = sampling_from_args(
        parser.parse_args(
            ["--inkling-reasoning-effort", "none", "--inkling-reasoning-max-tokens", "512"]
        )
    ).reasoning_payload()
    assert payload == {"enabled": True, "max_tokens": 512}
    assert (
        sampling_from_args(parser.parse_args(["--no-inkling-reasoning"])).reasoning_enabled is False
    )


def test_sampling_parameters_are_not_read_from_the_environment(monkeypatch) -> None:
    # These knobs changed from env vars to CLI arguments: a stray environment
    # value must not silently alter what a run produces.
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    for name, value in [
        ("INKLING_TEMPERATURE", "1.9"),
        ("INKLING_TOP_P", "0.1"),
        ("INKLING_MAX_TOKENS", "17"),
        ("INKLING_SEED", "999"),
        ("INKLING_FREQUENCY_PENALTY", "1.5"),
        ("INKLING_PRESENCE_PENALTY", "1.5"),
    ]:
        monkeypatch.setenv(name, value)

    assert InklingBackendConfig.from_env().sampling == InklingSampling()
