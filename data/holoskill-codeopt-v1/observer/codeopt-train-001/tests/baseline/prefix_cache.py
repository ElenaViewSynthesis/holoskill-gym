from __future__ import annotations


def _encode_token(token: str) -> int:
    total = 0
    for index, char in enumerate(token):
        total = (total * 31 + ord(char) + index) % 1_000_003
    return total


def encode_batch(prompts: list[str], prefix: str) -> list[list[int]]:
    """Encode each prompt as prefix tokens followed by prompt tokens."""

    encoded: list[list[int]] = []
    for prompt in prompts:
        row: list[int] = []
        for token in prefix.split():
            row.append(_encode_token(token))
        for token in prompt.split():
            row.append(_encode_token(token))
        encoded.append(row)
    return encoded
