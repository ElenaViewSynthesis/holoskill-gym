from src.batching import score_all


def test_preserves_order_and_length() -> None:
    out = score_all(["a", "bb", "ccc"])
    assert len(out) == 3
    assert out[0] < out[1] < out[2]


def test_empty_input() -> None:
    assert score_all([]) == []


def test_matches_single_item_scoring() -> None:
    items = ["alpha", "beta", "gamma"]
    assert score_all(items) == [score_all([item])[0] for item in items]


def test_large_input_length() -> None:
    assert len(score_all([f"x{i}" for i in range(500)])) == 500
