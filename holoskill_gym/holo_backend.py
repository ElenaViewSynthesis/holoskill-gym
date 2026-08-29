"""Structured-output Holo optimizer built on SkillOpt's configured client."""

from __future__ import annotations

import json
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from .schemas import (
    OptimizerCallRecord,
    OptimizerUsage,
    ProposalResponse,
    SkillUpdateProposal,
)

DEFAULT_HOLO_BASE_URL = "https://api.hcompany.ai/v1"
DEFAULT_HOLO_MODEL = "holo3-1-35b-a3b"
HOLO_35B_MAX_OUTPUT_TOKENS = 4_096
DEFAULT_PROPOSAL_MAX_TOKENS = 3_000
DEFAULT_MAX_ATTEMPTS = 6
DEFAULT_INITIAL_BACKOFF_SECONDS = 6.0
DEFAULT_MAX_BACKOFF_SECONDS = 30.0


@dataclass(frozen=True)
class HoloBackendConfig:
    """Connection and retry settings for the Holo optimizer role."""

    api_key: str = field(repr=False)
    base_url: str = DEFAULT_HOLO_BASE_URL
    model: str = DEFAULT_HOLO_MODEL
    max_completion_tokens: int = DEFAULT_PROPOSAL_MAX_TOKENS
    timeout_seconds: float = 120.0
    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    initial_backoff_seconds: float = DEFAULT_INITIAL_BACKOFF_SECONDS
    max_backoff_seconds: float = DEFAULT_MAX_BACKOFF_SECONDS

    def __post_init__(self) -> None:
        if not self.api_key.strip():
            raise ValueError("Holo api_key must not be empty")
        if not self.base_url.strip():
            raise ValueError("Holo base_url must not be empty")
        if self.model != DEFAULT_HOLO_MODEL:
            raise ValueError(
                f"Holo model must be {DEFAULT_HOLO_MODEL!r}; this integration is 35B-only"
            )
        if self.max_completion_tokens <= 0:
            raise ValueError("max_completion_tokens must be positive")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.max_attempts <= 0:
            raise ValueError("max_attempts must be positive")
        if self.initial_backoff_seconds < 0 or self.max_backoff_seconds < 0:
            raise ValueError("retry backoff values must be non-negative")

    @classmethod
    def from_env(
        cls,
        *,
        model: str | None = None,
        max_completion_tokens: int = DEFAULT_PROPOSAL_MAX_TOKENS,
        timeout_seconds: float = 120.0,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        initial_backoff_seconds: float = DEFAULT_INITIAL_BACKOFF_SECONDS,
        max_backoff_seconds: float = DEFAULT_MAX_BACKOFF_SECONDS,
    ) -> HoloBackendConfig:
        api_key = (os.environ.get("HAI_API_KEY") or "").strip()
        if not api_key:
            raise HoloAuthenticationError(
                "HAI_API_KEY is not set",
                attempts=0,
                latency_ms=0,
            )
        return cls(
            api_key=api_key,
            base_url=(os.environ.get("HOLO_BASE_URL") or DEFAULT_HOLO_BASE_URL).rstrip("/"),
            model=model or os.environ.get("HOLO_OPTIMIZER_MODEL") or DEFAULT_HOLO_MODEL,
            max_completion_tokens=max_completion_tokens,
            timeout_seconds=timeout_seconds,
            max_attempts=max_attempts,
            initial_backoff_seconds=initial_backoff_seconds,
            max_backoff_seconds=max_backoff_seconds,
        )


class HoloBackendError(RuntimeError):
    """Base provider error with safe, serializable metadata."""

    code = "provider_error"

    def __init__(
        self,
        message: str,
        *,
        attempts: int,
        latency_ms: float,
        status_code: int | None = None,
        retryable: bool = False,
        call: OptimizerCallRecord | None = None,
    ) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.latency_ms = latency_ms
        self.status_code = status_code
        self.retryable = retryable
        self.call = call

    def to_safe_dict(self) -> dict[str, object]:
        return {
            "type": self.code,
            "attempts": self.attempts,
            "latency_ms": self.latency_ms,
            "status_code": self.status_code,
            "retryable": self.retryable,
        }


class HoloAuthenticationError(HoloBackendError):
    code = "authentication_error"


class HoloModelAccessError(HoloBackendError):
    code = "model_access_error"


class HoloRateLimitError(HoloBackendError):
    code = "rate_limit_error"


class HoloTimeoutError(HoloBackendError):
    code = "timeout_error"


class HoloMalformedOutputError(HoloBackendError):
    code = "malformed_output"


class HoloTruncatedOutputError(HoloMalformedOutputError):
    code = "truncated_output"


class HoloProviderError(HoloBackendError):
    code = "provider_error"


class HoloBackend:
    """Issue strict schema requests through SkillOpt's optimizer client."""

    def __init__(
        self,
        config: HoloBackendConfig,
        *,
        client: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self.config = config
        self._client = client
        self._sleep = sleep
        self._clock = clock
        self._records: list[OptimizerCallRecord] = []
        self._records_lock = threading.Lock()

    @classmethod
    def from_env(
        cls,
        *,
        model: str | None = None,
        max_completion_tokens: int = DEFAULT_PROPOSAL_MAX_TOKENS,
        timeout_seconds: float = 120.0,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        initial_backoff_seconds: float = DEFAULT_INITIAL_BACKOFF_SECONDS,
        max_backoff_seconds: float = DEFAULT_MAX_BACKOFF_SECONDS,
    ) -> HoloBackend:
        config = HoloBackendConfig.from_env(
            model=model,
            max_completion_tokens=max_completion_tokens,
            timeout_seconds=timeout_seconds,
            max_attempts=max_attempts,
            initial_backoff_seconds=initial_backoff_seconds,
            max_backoff_seconds=max_backoff_seconds,
        )
        configure_skillopt_holo(config)
        return cls(config)

    @property
    def records(self) -> tuple[OptimizerCallRecord, ...]:
        with self._records_lock:
            return tuple(self._records)

    def propose(
        self, *, system: str, user: str, schema: dict[str, Any] | None = None
    ) -> ProposalResponse:
        """Request and parse one bounded update proposal."""

        started = self._clock()
        max_tokens = min(self.config.max_completion_tokens, HOLO_35B_MAX_OUTPUT_TOKENS)

        for attempt in range(1, self.config.max_attempts + 1):
            try:
                response = self.client.chat.completions.create(
                    model=self.config.model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    max_completion_tokens=max_tokens,
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": "skill_update_proposal",
                            "strict": True,
                            "schema": schema or SkillUpdateProposal.model_json_schema(),
                        },
                    },
                    timeout=self.config.timeout_seconds,
                )
            except Exception as exc:  # provider SDK exceptions are normalized below
                latency_ms = (self._clock() - started) * 1_000
                normalized = _normalize_provider_error(
                    exc,
                    attempts=attempt,
                    latency_ms=latency_ms,
                )
                if normalized.retryable and attempt < self.config.max_attempts:
                    self._sleep(self._retry_delay(attempt))
                    continue
                raise normalized from exc

            latency_ms = (self._clock() - started) * 1_000
            try:
                result = _parse_response(
                    response,
                    model=self.config.model,
                    attempts=attempt,
                    latency_ms=latency_ms,
                )
            except HoloBackendError as exc:
                if exc.call is not None:
                    with self._records_lock:
                        self._records.append(exc.call)
                raise
            with self._records_lock:
                self._records.append(result.call)
            return result

        raise AssertionError("unreachable retry state")

    @property
    def client(self) -> Any:
        if self._client is None:
            from skillopt.model.azure_openai import get_optimizer_client

            self._client = get_optimizer_client()
        return self._client

    def _retry_delay(self, failed_attempt: int) -> float:
        return min(
            self.config.max_backoff_seconds,
            self.config.initial_backoff_seconds * (2 ** (failed_attempt - 1)),
        )


def configure_skillopt_holo(config: HoloBackendConfig) -> None:
    """Configure SkillOpt's shared optimizer client for Holo safely."""

    from skillopt.model.azure_openai import (
        configure_azure_openai,
        set_optimizer_deployment,
        set_reasoning_effort,
    )

    configure_azure_openai(
        optimizer_endpoint=config.base_url.rstrip("/"),
        optimizer_api_key=config.api_key,
        optimizer_auth_mode="openai_compatible",
    )
    set_optimizer_deployment(config.model)
    set_reasoning_effort(None)


def _parse_response(
    response: Any,
    *,
    model: str,
    attempts: int,
    latency_ms: float,
) -> ProposalResponse:
    call = _call_record(
        response,
        model=model,
        attempts=attempts,
        latency_ms=latency_ms,
        finish_reason=None,
    )
    try:
        choice = response.choices[0]
        message = choice.message
    except (AttributeError, IndexError, TypeError) as exc:
        raise HoloMalformedOutputError(
            "Holo returned a response without a completion choice",
            attempts=attempts,
            latency_ms=latency_ms,
            call=call,
        ) from exc

    finish_reason = getattr(choice, "finish_reason", None)
    call = _call_record(
        response,
        model=model,
        attempts=attempts,
        latency_ms=latency_ms,
        finish_reason=finish_reason,
    )
    content = getattr(message, "content", None)
    if not isinstance(content, str) or not content.strip():
        error_class = (
            HoloTruncatedOutputError if finish_reason == "length" else HoloMalformedOutputError
        )
        raise error_class(
            "Holo returned no structured proposal content",
            attempts=attempts,
            latency_ms=latency_ms,
            call=call,
        )

    try:
        payload = json.loads(content)
        proposal = SkillUpdateProposal.model_validate(payload)
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        raise HoloMalformedOutputError(
            "Holo returned content that does not satisfy SkillUpdateProposal",
            attempts=attempts,
            latency_ms=latency_ms,
            call=call,
        ) from exc

    return ProposalResponse(proposal=proposal, call=call)


def _call_record(
    response: Any,
    *,
    model: str,
    attempts: int,
    latency_ms: float,
    finish_reason: Any,
) -> OptimizerCallRecord:
    return OptimizerCallRecord(
        provider="hcompany",
        model=str(getattr(response, "model", None) or model),
        latency_ms=latency_ms,
        attempts=attempts,
        response_id=_optional_string(getattr(response, "id", None)),
        finish_reason=_optional_string(finish_reason),
        usage=_extract_usage(getattr(response, "usage", None)),
    )


def _extract_usage(usage: Any) -> OptimizerUsage:
    if usage is None:
        return OptimizerUsage()
    prompt = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion = int(getattr(usage, "completion_tokens", 0) or 0)
    total = int(getattr(usage, "total_tokens", 0) or prompt + completion)
    return OptimizerUsage(
        prompt_tokens=max(0, prompt),
        completion_tokens=max(0, completion),
        total_tokens=max(0, total),
    )


def _normalize_provider_error(
    exc: Exception,
    *,
    attempts: int,
    latency_ms: float,
) -> HoloBackendError:
    status = getattr(exc, "status_code", None)
    if not isinstance(status, int):
        status = None
    name = type(exc).__name__.lower()
    common = {"attempts": attempts, "latency_ms": latency_ms, "status_code": status}

    if status in {401, 403} or "authentication" in name or "permissiondenied" in name:
        return HoloAuthenticationError("Holo authentication was rejected", **common)
    if status in {402, 404} or "notfound" in name:
        return HoloModelAccessError("Holo model is unavailable for this account", **common)
    if status == 429 or "ratelimit" in name:
        return HoloRateLimitError("Holo request was rate limited", retryable=True, **common)
    if isinstance(exc, TimeoutError) or "timeout" in name:
        return HoloTimeoutError("Holo request timed out", retryable=True, **common)
    retryable = status in {408, 409, 425} or (status is not None and status >= 500)
    return HoloProviderError(
        "Holo provider request failed",
        retryable=retryable,
        **common,
    )


def _optional_string(value: Any) -> str | None:
    return None if value in (None, "") else str(value)
