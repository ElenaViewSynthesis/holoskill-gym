from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=None)
def _encode_token(token: str) -> int:
    total = 0
    for index, char in enumerate(token):
        total = (total * 31 + ord(char) + index) % 1_000_003
    return total


def encode_batch(prompts: list[str], prefix: str) -> list[list[int]]:
    """Encode each prompt as prefix tokens followed by prompt tokens."""

    prefix_row = [_encode_token(token) for token in prefix.split()]
    return [
        prefix_row + [_encode_token(token) for token in prompt.split()]
        for prompt in prompts
    ]
