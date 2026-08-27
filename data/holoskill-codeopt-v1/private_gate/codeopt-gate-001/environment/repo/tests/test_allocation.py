from src.allocation import build_buffer


def test_concatenates_in_order() -> None:
    assert build_buffer(["a", "b", "c"]) == "abc"


def test_empty_input() -> None:
    assert build_buffer([]) == ""


def test_single_chunk() -> None:
    assert build_buffer(["only"]) == "only"


def test_preserves_whitespace() -> None:
    assert build_buffer([" a ", "b "]) == " a b "
