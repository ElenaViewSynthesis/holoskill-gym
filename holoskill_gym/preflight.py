"""Minimal credentialed preflight against the H Models API.

Sends exactly ONE chat-completion request to confirm that HAI_API_KEY, the
base URL, and the model are all reachable. Per spec section 8, provider error
classes are surfaced distinctly and never collapsed into a silent zero score,
and the API key is never printed.

Usage:
    python -m holoskill_gym.preflight
    python -m holoskill_gym.preflight --optimizer --structured
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_BASE_URL = "https://api.hcompany.ai/v1/"
DEFAULT_MODEL = "holo3-1-35b-a3b"
DEFAULT_OPTIMIZER_MODEL = "holo3-1-35b-a3b"
PROMPT = "In one sentence, what is a computer-use agent?"


def load_key(env_path: Path) -> str:
    """Load HAI_API_KEY from the environment, falling back to a local .env."""
    if env_path.is_file():
        load_dotenv(env_path, override=False)
    key = (os.environ.get("HAI_API_KEY") or "").strip().strip('"').strip("'")
    if not key:
        raise SystemExit(f"HAI_API_KEY is not set. Add it to {env_path} or export it in the shell.")
    if key == "your-api-key-here":
        raise SystemExit(f"HAI_API_KEY is still the placeholder value in {env_path}.")
    return key


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="One-shot H Models API preflight.")
    parser.add_argument(
        "--optimizer", action="store_true", help="Use the configured HOLO_OPTIMIZER_MODEL."
    )
    parser.add_argument(
        "--structured",
        action="store_true",
        help="Exercise the exact strict SkillUpdateProposal path used by the optimizer.",
    )
    parser.add_argument("--prompt", default=PROMPT)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--env-file", default=".env")
    parser.add_argument(
        "--inkling",
        action="store_true",
        help="Preflight the Inkling optimizer through OpenRouter instead of Holo.",
    )
    from .inkling_backend import add_sampling_arguments

    add_sampling_arguments(parser)
    args = parser.parse_args(argv)

    if args.inkling:
        return _inkling_preflight(args)

    # Load .env first so that HOLO_* settings from the file are visible below.
    env_path = Path(args.env_file).resolve()
    key = load_key(env_path)

    base_url = os.environ.get("HOLO_BASE_URL", DEFAULT_BASE_URL)
    optimizer_model = os.environ.get("HOLO_OPTIMIZER_MODEL", DEFAULT_OPTIMIZER_MODEL)
    model = optimizer_model if args.optimizer else DEFAULT_MODEL
    if model != DEFAULT_MODEL:
        print(
            f"FAIL  this integration is 35B-only; configure model={DEFAULT_MODEL}",
            file=sys.stderr,
        )
        return 2

    # Import late so that a missing dependency is reported clearly.
    try:
        from openai import (
            APIConnectionError,
            APIStatusError,
            APITimeoutError,
            AuthenticationError,
            NotFoundError,
            OpenAI,
            RateLimitError,
        )
    except ImportError as exc:  # pragma: no cover - environment problem
        print(f"FAIL  openai package not importable: {exc}", file=sys.stderr)
        return 3

    print("H Models API preflight")
    print(f"  base_url : {base_url}")
    print(f"  model    : {model}")
    print("  api_key  : configured (value intentionally not displayed)")
    print(f"  env_file : {env_path}")
    print()

    if args.structured:
        return _structured_preflight(model=model, timeout=args.timeout)

    client = OpenAI(base_url=base_url, api_key=key, timeout=args.timeout, max_retries=0)

    started = time.perf_counter()
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": args.prompt}],
        )
    except AuthenticationError as exc:
        print(
            f"FAIL  authentication rejected (check HAI_API_KEY): {exc.status_code}", file=sys.stderr
        )
        return 4
    except NotFoundError as exc:
        print(
            f"FAIL  model '{model}' not found or not enabled for this key: {exc.status_code}",
            file=sys.stderr,
        )
        return 5
    except RateLimitError as exc:
        print(f"FAIL  rate limited (retryable): {exc.status_code}", file=sys.stderr)
        return 6
    except APITimeoutError:
        print(f"FAIL  request timed out after {args.timeout}s (retryable)", file=sys.stderr)
        return 7
    except APIConnectionError as exc:
        print(f"FAIL  could not reach {base_url}: {exc.__class__.__name__}", file=sys.stderr)
        return 8
    except APIStatusError as exc:
        print(f"FAIL  provider error status={exc.status_code}", file=sys.stderr)
        return 9

    latency_ms = (time.perf_counter() - started) * 1000.0
    content = (response.choices[0].message.content or "").strip()
    usage = response.usage

    print("OK    request succeeded")
    print(f"  latency      : {latency_ms:.0f} ms")
    print(f"  response_id  : {response.id}")
    print(f"  model_served : {response.model}")
    print(f"  finish       : {response.choices[0].finish_reason}")
    if usage is not None:
        print(
            f"  tokens       : prompt={usage.prompt_tokens} "
            f"completion={usage.completion_tokens} total={usage.total_tokens}"
        )
    print(f"  content_chars: {len(content)}")
    return 0


def _structured_preflight(*, model: str, timeout: float) -> int:
    from .holo_backend import HoloBackend, HoloBackendError

    try:
        backend = HoloBackend.from_env(
            model=model,
            max_completion_tokens=3_000,
            timeout_seconds=timeout,
            max_attempts=1,
        )
        response = backend.propose(
            system=(
                "Return a strict SkillUpdateProposal. This is a connectivity check; emit no "
                "edits and do not include reasoning outside the schema."
            ),
            user="The current skill is '# Skill'. No training evidence is available.",
        )
    except HoloBackendError as exc:
        details = exc.to_safe_dict()
        print(
            f"FAIL  structured optimizer preflight: {details['type']} "
            f"status={details['status_code']}",
            file=sys.stderr,
        )
        return 10
    print("OK    strict json_schema request succeeded")
    print(f"  response_id  : {response.call.response_id}")
    print(f"  model_served : {response.call.model}")
    print(f"  finish       : {response.call.finish_reason}")
    print(f"  edits        : {len(response.proposal.edits)}")
    print(f"  tokens       : total={response.call.usage.total_tokens}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _inkling_preflight(args) -> int:
    """One structured request to Inkling with the parameters given on the CLI."""

    from .holo_backend import HoloBackendError
    from .inkling_backend import InklingBackend, InklingBackendConfig, sampling_from_args

    sampling = sampling_from_args(args)
    print("OpenRouter Inkling preflight")
    print(f"  base_url    : {os.environ.get('OPENROUTER_BASE_URL', '(default)')}")
    print(f"  model       : {os.environ.get('INKLING_MODEL', '(default)')}")
    print("  api_key     : configured (value intentionally not displayed)")
    print(f"  temperature : {sampling.temperature}")
    print(f"  top_p       : {sampling.top_p}")
    print(f"  max_tokens  : {sampling.max_tokens}")
    print(f"  seed        : {sampling.seed}")
    print(f"  reasoning   : {sampling.reasoning_payload()}")
    print()

    try:
        backend = InklingBackend(
            InklingBackendConfig.from_env(
                sampling=sampling,
                timeout_seconds=args.timeout,
                max_attempts=1,
            )
        )
        response = backend.propose(
            system=(
                "Return a strict SkillUpdateProposal. This is a connectivity check; emit no edits."
            ),
            user="The current skill is '# Skill'. No training evidence is available.",
        )
    except HoloBackendError as exc:
        details = exc.to_safe_dict()
        print(
            f"FAIL  inkling preflight: {details['type']} status={details['status_code']}",
            file=sys.stderr,
        )
        if details["type"] == "model_access_denied":
            print(
                "      OpenRouter restricts some models to registered agentic "
                "harnesses; see docs/openrouter-inkling.md",
                file=sys.stderr,
            )
        return 11
    print("OK    strict json_schema request succeeded")
    print(f"  response_id  : {response.call.response_id}")
    print(f"  model_served : {response.call.model}")
    print(f"  edits        : {len(response.proposal.edits)}")
    print(f"  tokens       : total={response.call.usage.total_tokens}")
    return 0
