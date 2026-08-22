"""Minimal credentialed preflight against the H Models API.

Sends exactly ONE chat-completion request to confirm that HAI_API_KEY, the
base URL, and the model are all reachable. Per spec section 8, provider error
classes are surfaced distinctly and never collapsed into a silent zero score,
and the API key is never printed.

Usage:
    python -m holoskill_gym.preflight
    python -m holoskill_gym.preflight --model holo3-122b-a10b
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
OPTIMIZER_MODEL = "holo3-122b-a10b"
PROMPT = "In one sentence, what is a computer-use agent?"


def redact(key: str) -> str:
    """Render a key as a non-recoverable fingerprint."""
    if not key:
        return "(unset)"
    if len(key) <= 8:
        return "(too short)"
    return f"{key[:4]}...{key[-2:]} (len={len(key)})"


def load_key(env_path: Path) -> str:
    """Load HAI_API_KEY from the environment, falling back to a local .env."""
    if env_path.is_file():
        load_dotenv(env_path, override=False)
    key = (os.environ.get("HAI_API_KEY") or "").strip().strip('"').strip("'")
    if not key:
        raise SystemExit(
            f"HAI_API_KEY is not set. Add it to {env_path} or export it in the shell."
        )
    if key == "your-api-key-here":
        raise SystemExit(f"HAI_API_KEY is still the placeholder value in {env_path}.")
    return key


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="One-shot H Models API preflight.")
    parser.add_argument("--model", default=os.environ.get("HOLO_PREFLIGHT_MODEL", DEFAULT_MODEL))
    parser.add_argument("--optimizer", action="store_true",
                        help=f"Use {OPTIMIZER_MODEL} instead of the default small model.")
    parser.add_argument("--prompt", default=PROMPT)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--env-file", default=".env")
    args = parser.parse_args(argv)

    model = OPTIMIZER_MODEL if args.optimizer else args.model
    base_url = os.environ.get("HOLO_BASE_URL", DEFAULT_BASE_URL)

    env_path = Path(args.env_file).resolve()
    key = load_key(env_path)
    base_url = os.environ.get("HOLO_BASE_URL", base_url)

    # Import late so that a missing dependency is reported clearly.
    try:
        from openai import (
            APIConnectionError, APIStatusError, APITimeoutError,
            AuthenticationError, NotFoundError, OpenAI, RateLimitError,
        )
    except ImportError as exc:  # pragma: no cover - environment problem
        print(f"FAIL  openai package not importable: {exc}", file=sys.stderr)
        return 3

    print("H Models API preflight")
    print(f"  base_url : {base_url}")
    print(f"  model    : {model}")
    print(f"  api_key  : {redact(key)}")
    print(f"  env_file : {env_path}")
    print()

    client = OpenAI(base_url=base_url, api_key=key, timeout=args.timeout, max_retries=0)

    started = time.perf_counter()
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": args.prompt}],
        )
    except AuthenticationError as exc:
        print(f"FAIL  authentication rejected (check HAI_API_KEY): {exc.status_code}", file=sys.stderr)
        return 4
    except NotFoundError as exc:
        print(f"FAIL  model '{model}' not found or not enabled for this key: {exc.status_code}",
              file=sys.stderr)
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
        print(f"  tokens       : prompt={usage.prompt_tokens} "
              f"completion={usage.completion_tokens} total={usage.total_tokens}")
    print()
    print(f"  prompt   : {args.prompt}")
    print(f"  content  : {content}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
