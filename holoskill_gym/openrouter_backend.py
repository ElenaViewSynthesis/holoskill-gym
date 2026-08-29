"""OpenRouter optimizer backend, an alternative to Holo.

Satisfies the same ``ProposalBackend`` contract as
:mod:`holoskill_gym.holo_backend`, so the engine is indifferent to which is
configured. The model is selected by ``OPENROUTER_MODEL``; the adapter itself
is model-agnostic.

Model selection is not free. The mutation call requires strict
``json_schema``, and advertised support does not imply the model can produce a
valid proposal. Probed against the live API rather than read from metadata:

===========================================  =========  ==============  =========
model                                        free       response_format  proposal
===========================================  =========  ==============  =========
``openai/gpt-5.6-luna``                      no         yes             **yes**
``z-ai/glm-5.2:free``                        yes        yes             rate limited
``nvidia/nemotron-3-super-120b-a12b:free``   yes        yes             schema failure
``dots-studio/dots-3-note-preview:free``     yes        yes             null content
``liquid/lfm-2.5-2.6b:free``                 yes        yes             schema failure
``thinkingmachines/inkling``                 no         yes             untested
``thinkingmachines/inkling:free``            yes        no              n/a
===========================================  =========  ==============  =========

Four models advertising ``structured_outputs`` cannot produce a valid proposal,
which is why the last column exists and why ``supported_parameters`` is not a
sufficient check. Local semantic validation runs regardless of model.

The Inkling free variants additionally answer ``403 "only available on agentic
harnesses"`` to any direct call, which :class:`OpenRouterAccessError`
classifies distinctly so it fails closed rather than looking like a malformed
proposal. See ``docs/openrouter-inkling.md``.
"""

from __future__ import annotations

import os
import threading
import time
from argparse import BooleanOptionalAction
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from .holo_backend import (
    HoloBackendError,
    _normalize_provider_error,
    _parse_response,
)
from .schemas import OptimizerCallRecord, ProposalResponse, SkillUpdateProposal

DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
LUNA_MODEL = "openai/gpt-5.6-luna"
GLM_MODEL = "z-ai/glm-5.2:free"
INKLING_PAID_MODEL = "thinkingmachines/inkling"
INKLING_FREE_MODEL = "thinkingmachines/inkling:free"

# GPT-5.6 Luna is the default: the first model probed that actually returns a
# valid SkillUpdateProposal, on the first attempt, rather than merely
# advertising structured output. Verified 2026-08-29: a valid proposal in
# 43.5s on 426 tokens, attempts=1.
#
# It is paid ($0.20/M prompt, $1.20/M completion). That is the trade: every
# free candidate either exhausted its retries on upstream saturation or failed
# schema validation. GLM_MODEL remains selectable for a zero-cost run, with the
# caveat that it has never completed a proposal.
DEFAULT_OPENROUTER_MODEL = LUNA_MODEL

# Models that cannot fill the optimizer role, with the reason each was ruled
# out. Selecting one is a configuration error, raised before any request is
# sent rather than surfacing as a malformed proposal after tokens are spent.
#
# Two distinct causes, both established by probing rather than by reading
# catalogue metadata -- `supported_parameters` proved unreliable, since three
# of these advertise structured output and still cannot produce it.
UNUSABLE_OPTIMIZER_MODELS: dict[str, str] = {
    # No response_format support at all.
    "thinkingmachines/inkling:free": "does not support response_format",
    "thinkingmachines/inkling-small:free": "does not support response_format",
    "thinkingmachines/inkling-small": "does not support response_format",
    "thinkingmachines/inkling:batch": "does not support response_format",
    # Advertises structured output; fails to produce a valid proposal.
    "nvidia/nemotron-3-super-120b-a12b:free": (
        "advertises structured_outputs but returned content failing schema "
        "validation on every probe (2026-08-28, 2026-08-29)"
    ),
    "dots-studio/dots-3-note-preview:free": (
        "advertises structured_outputs but returned null content within the "
        "token budget (probed 2026-08-28)"
    ),
    "liquid/lfm-2.5-2.6b:free": (
        "advertises structured_outputs but is too small to satisfy the "
        "SkillUpdateProposal schema (probed 2026-08-28)"
    ),
}

# Retained for callers that only need membership.
MODELS_WITHOUT_STRUCTURED_OUTPUT = frozenset(UNUSABLE_OPTIMIZER_MODELS)

# Defaults chosen for a *deterministic optimizer*, not for chat. OpenRouter's
# own defaults (temperature 1, no seed) are wrong for this role: the optimizer
# drives an accept/reject gate, so an unreproducible proposal makes the whole
# run unreproducible. This mirrors why the Holo role is pinned to one model.
DEFAULT_TEMPERATURE = 0.0
DEFAULT_TOP_P = 1.0
DEFAULT_SEED = 42
DEFAULT_MAX_TOKENS = 4_096
DEFAULT_FREQUENCY_PENALTY = 0.0
DEFAULT_PRESENCE_PENALTY = 0.0
DEFAULT_REASONING_ENABLED = True
DEFAULT_REASONING_EFFORT: ReasoningEffort = "medium"
DEFAULT_TIMEOUT_SECONDS = 120.0
DEFAULT_MAX_ATTEMPTS = 6
DEFAULT_INITIAL_BACKOFF_SECONDS = 6.0
DEFAULT_MAX_BACKOFF_SECONDS = 30.0

ReasoningEffort = Literal["low", "medium", "high"]
_VALID_EFFORTS = ("low", "medium", "high")


class OpenRouterAccessError(HoloBackendError):
    """Raised when OpenRouter refuses the model for this caller (HTTP 403)."""

    code = "model_access_denied"


@dataclass(frozen=True)
class OpenRouterSampling:
    """Generation parameters exposed by OpenRouter's chat completions API."""

    temperature: float = DEFAULT_TEMPERATURE
    top_p: float = DEFAULT_TOP_P
    max_tokens: int = DEFAULT_MAX_TOKENS
    seed: int | None = DEFAULT_SEED
    frequency_penalty: float = DEFAULT_FREQUENCY_PENALTY
    presence_penalty: float = DEFAULT_PRESENCE_PENALTY
    stop: tuple[str, ...] = ()
    reasoning_enabled: bool = DEFAULT_REASONING_ENABLED
    reasoning_effort: ReasoningEffort | None = DEFAULT_REASONING_EFFORT
    reasoning_max_tokens: int | None = None
    reasoning_exclude: bool = False

    def __post_init__(self) -> None:
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError("temperature must be between 0 and 2")
        if not 0.0 < self.top_p <= 1.0:
            raise ValueError("top_p must be within (0, 1]")
        if self.max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        if not -2.0 <= self.frequency_penalty <= 2.0:
            raise ValueError("frequency_penalty must be between -2 and 2")
        if not -2.0 <= self.presence_penalty <= 2.0:
            raise ValueError("presence_penalty must be between -2 and 2")
        if self.reasoning_effort is not None and self.reasoning_effort not in _VALID_EFFORTS:
            raise ValueError(f"reasoning_effort must be one of {_VALID_EFFORTS}")
        if self.reasoning_max_tokens is not None and self.reasoning_max_tokens <= 0:
            raise ValueError("reasoning_max_tokens must be positive when set")
        if self.reasoning_max_tokens is not None and self.reasoning_effort is not None:
            raise ValueError(
                "set reasoning_effort or reasoning_max_tokens, not both; "
                "OpenRouter treats them as alternative controls"
            )

    def reasoning_payload(self) -> dict[str, Any]:
        """Build the ``reasoning`` map, omitting keys that are not configured."""

        payload: dict[str, Any] = {"enabled": self.reasoning_enabled}
        if self.reasoning_effort is not None:
            payload["effort"] = self.reasoning_effort
        if self.reasoning_max_tokens is not None:
            payload["max_tokens"] = self.reasoning_max_tokens
        if self.reasoning_exclude:
            payload["exclude"] = True
        return payload


@dataclass(frozen=True)
class OpenRouterBackendConfig:
    """Connection, retry, and sampling settings for the OpenRouter optimizer role."""

    api_key: str = field(repr=False)
    base_url: str = DEFAULT_OPENROUTER_BASE_URL
    model: str = DEFAULT_OPENROUTER_MODEL
    sampling: OpenRouterSampling = field(default_factory=OpenRouterSampling)
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    initial_backoff_seconds: float = DEFAULT_INITIAL_BACKOFF_SECONDS
    max_backoff_seconds: float = DEFAULT_MAX_BACKOFF_SECONDS
    http_referer: str | None = None
    x_title: str | None = None

    def __post_init__(self) -> None:
        if not self.api_key.strip():
            raise ValueError("OpenRouter api_key must not be empty")
        if not self.base_url.strip():
            raise ValueError("OpenRouter base_url must not be empty")
        if not self.model.strip():
            raise ValueError("OpenRouter model must not be empty")
        if self.model in UNUSABLE_OPTIMIZER_MODELS:
            raise ValueError(
                f"{self.model} cannot serve as an optimizer: "
                f"{UNUSABLE_OPTIMIZER_MODELS[self.model]}. Choose a model that "
                f"can, for example {DEFAULT_OPENROUTER_MODEL}, or use the Holo "
                "backend, which is the supported production optimizer."
            )
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.max_attempts <= 0:
            raise ValueError("max_attempts must be positive")
        if self.initial_backoff_seconds < 0 or self.max_backoff_seconds < 0:
            raise ValueError("retry backoff values must be non-negative")

    def default_headers(self) -> dict[str, str]:
        headers = {}
        if self.http_referer:
            headers["HTTP-Referer"] = self.http_referer
        if self.x_title:
            headers["X-Title"] = self.x_title
        return headers

    @classmethod
    def from_env(cls, **overrides: Any) -> OpenRouterBackendConfig:
        """Read connection settings from OPENROUTER_* variables."""

        api_key = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
        if not api_key:
            raise OpenRouterAccessError(
                "OPENROUTER_API_KEY is not set",
                attempts=0,
                latency_ms=0,
            )
        # Sampling and reasoning knobs are command-line arguments, not
        # environment variables: they change what a run produces, so they
        # belong in the run's recorded configuration rather than in ambient
        # process state. See add_sampling_arguments().
        sampling = overrides.pop("sampling", None) or OpenRouterSampling()
        defaults: dict[str, Any] = {
            "api_key": api_key,
            "base_url": (
                os.environ.get("OPENROUTER_BASE_URL") or DEFAULT_OPENROUTER_BASE_URL
            ).rstrip("/"),
            "model": os.environ.get("OPENROUTER_MODEL") or DEFAULT_OPENROUTER_MODEL,
            "sampling": sampling,
            "http_referer": os.environ.get("OPENROUTER_HTTP_REFERER") or None,
            "x_title": os.environ.get("OPENROUTER_X_TITLE") or None,
        }
        defaults.update(overrides)
        return cls(**defaults)


class OpenRouterBackend:
    """Issue strict schema requests to a model served by OpenRouter."""

    def __init__(
        self,
        config: OpenRouterBackendConfig,
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
    def from_env(cls, **overrides: Any) -> OpenRouterBackend:
        return cls(OpenRouterBackendConfig.from_env(**overrides))

    @property
    def records(self) -> tuple[OptimizerCallRecord, ...]:
        with self._records_lock:
            return tuple(self._records)

    @property
    def client(self) -> Any:
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(
                base_url=self.config.base_url,
                api_key=self.config.api_key,
                timeout=self.config.timeout_seconds,
                max_retries=0,
                default_headers=self.config.default_headers() or None,
            )
        return self._client

    def propose(
        self, *, system: str, user: str, schema: dict[str, Any] | None = None
    ) -> ProposalResponse:
        """Request and parse one bounded update proposal."""

        started = self._clock()
        sampling = self.config.sampling
        extra_body: dict[str, Any] = {"reasoning": sampling.reasoning_payload()}

        for attempt in range(1, self.config.max_attempts + 1):
            try:
                response = self.client.chat.completions.create(
                    model=self.config.model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    max_tokens=sampling.max_tokens,
                    temperature=sampling.temperature,
                    top_p=sampling.top_p,
                    frequency_penalty=sampling.frequency_penalty,
                    presence_penalty=sampling.presence_penalty,
                    **({"seed": sampling.seed} if sampling.seed is not None else {}),
                    **({"stop": list(sampling.stop)} if sampling.stop else {}),
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": "skill_update_proposal",
                            "strict": True,
                            "schema": schema or SkillUpdateProposal.model_json_schema(),
                        },
                    },
                    extra_body=extra_body,
                    timeout=self.config.timeout_seconds,
                )
            except Exception as exc:
                latency_ms = (self._clock() - started) * 1_000
                normalized = _normalize_openrouter_error(
                    exc, attempts=attempt, latency_ms=latency_ms
                )
                if normalized.retryable and attempt < self.config.max_attempts:
                    self._sleep(self._retry_delay(attempt))
                    continue
                raise normalized from exc

            latency_ms = (self._clock() - started) * 1_000
            result = _parse_response(
                response,
                model=self.config.model,
                attempts=attempt,
                latency_ms=latency_ms,
            )
            with self._records_lock:
                self._records.append(result.call)
            return result

        raise AssertionError("unreachable retry state")

    def _retry_delay(self, failed_attempt: int) -> float:
        return min(
            self.config.max_backoff_seconds,
            self.config.initial_backoff_seconds * (2 ** (failed_attempt - 1)),
        )


def _normalize_openrouter_error(
    exc: Exception, *, attempts: int, latency_ms: float
) -> HoloBackendError:
    """Classify 403 model-gating separately; defer everything else to Holo's map."""

    status = getattr(exc, "status_code", None)
    if status == 403:
        return OpenRouterAccessError(
            "OpenRouter denied access to this model for this caller (HTTP 403). "
            "Some models are restricted to registered agentic harnesses; "
            "see docs/openrouter-inkling.md",
            attempts=attempts,
            latency_ms=latency_ms,
            status_code=403,
        )
    return _normalize_provider_error(exc, attempts=attempts, latency_ms=latency_ms)


def add_sampling_arguments(parser: Any, *, prefix: str = "openrouter") -> Any:
    """Register OpenRouter sampling and reasoning parameters on an argparse parser.

    Defaults match :class:`OpenRouterSampling` so the command line and the library
    cannot disagree. Values are tuning knobs that change what a run produces,
    which is why they are arguments rather than environment variables.
    """

    group = parser.add_argument_group(
        f"{prefix} sampling",
        "Generation parameters for the OpenRouter optimizer. Defaults are chosen "
        "for a deterministic optimizer, not for chat.",
    )
    group.add_argument(
        f"--{prefix}-temperature",
        type=float,
        default=DEFAULT_TEMPERATURE,
        help="0 keeps proposals reproducible (default: %(default)s)",
    )
    group.add_argument(
        f"--{prefix}-top-p",
        type=float,
        default=DEFAULT_TOP_P,
        help="nucleus sampling mass (default: %(default)s)",
    )
    group.add_argument(
        f"--{prefix}-max-tokens",
        type=int,
        default=DEFAULT_MAX_TOKENS,
        help="completion budget, shared with the reasoning preamble (default: %(default)s)",
    )
    group.add_argument(
        f"--{prefix}-seed",
        type=int,
        default=DEFAULT_SEED,
        help=f"deterministic sampling seed; use --no-{prefix}-seed to unset (default: %(default)s)",
    )
    group.add_argument(
        f"--no-{prefix}-seed",
        action="store_true",
        help="send no seed, letting the provider sample freely",
    )
    group.add_argument(
        f"--{prefix}-frequency-penalty",
        type=float,
        default=DEFAULT_FREQUENCY_PENALTY,
        help="(default: %(default)s)",
    )
    group.add_argument(
        f"--{prefix}-presence-penalty",
        type=float,
        default=DEFAULT_PRESENCE_PENALTY,
        help="(default: %(default)s)",
    )
    group.add_argument(
        f"--{prefix}-stop",
        action="append",
        default=None,
        metavar="TOKEN",
        help="stop sequence; repeat for several",
    )
    group.add_argument(
        f"--{prefix}-reasoning",
        dest=f"{prefix}_reasoning_enabled",
        action=BooleanOptionalAction,
        default=DEFAULT_REASONING_ENABLED,
        help="enable thinking tokens (default: enabled)",
    )
    group.add_argument(
        f"--{prefix}-reasoning-effort",
        choices=[*_VALID_EFFORTS, "none"],
        default=DEFAULT_REASONING_EFFORT,
        help=f"mutually exclusive with --{prefix}-reasoning-max-tokens (default: %(default)s)",
    )
    group.add_argument(
        f"--{prefix}-reasoning-max-tokens",
        type=int,
        default=None,
        help=f"explicit reasoning budget; unset --{prefix}-reasoning-effort to use it",
    )
    group.add_argument(
        f"--{prefix}-reasoning-exclude",
        action="store_true",
        help="omit reasoning from the response",
    )
    return parser


def sampling_from_args(args: Any, *, prefix: str = "openrouter") -> OpenRouterSampling:
    """Build an :class:`OpenRouterSampling` from parsed argparse arguments."""

    def get(name: str) -> Any:
        return getattr(args, f"{prefix}_{name}")

    effort = get("reasoning_effort")
    stop = get("stop") or []
    return OpenRouterSampling(
        temperature=get("temperature"),
        top_p=get("top_p"),
        max_tokens=get("max_tokens"),
        seed=None if getattr(args, f"no_{prefix}_seed", False) else get("seed"),
        frequency_penalty=get("frequency_penalty"),
        presence_penalty=get("presence_penalty"),
        stop=tuple(stop),
        reasoning_enabled=get("reasoning_enabled"),
        reasoning_effort=None if effort == "none" else effort,
        reasoning_max_tokens=get("reasoning_max_tokens"),
        reasoning_exclude=get("reasoning_exclude"),
    )
