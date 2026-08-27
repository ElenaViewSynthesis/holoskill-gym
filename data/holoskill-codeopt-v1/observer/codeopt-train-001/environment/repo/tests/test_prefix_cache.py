from src.prefix_cache import encode_batch


def test_encodes_prefix_then_prompt() -> None:
    out = encode_batch(["alpha beta"], "shared prefix")
    assert len(out) == 1
    assert len(out[0]) == 4


def test_prefix_rows_are_identical_across_prompts() -> None:
    out = encode_batch(["one", "two", "three"], "a b c")
    assert out[0][:3] == out[1][:3] == out[2][:3]


def test_empty_prompt_list() -> None:
    assert encode_batch([], "x") == []


def test_distinct_prompts_differ() -> None:
    out = encode_batch(["alpha", "omega"], "p")
    assert out[0][1:] != out[1][1:]
