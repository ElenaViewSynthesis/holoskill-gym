from src.locking import Registry


def test_reads_return_stored_values() -> None:
    assert Registry({"a": 1, "b": 2}).read_many(["a", "b"]) == [1, 2]


def test_missing_key_returns_sentinel() -> None:
    assert Registry({}).read_many(["nope"]) == [-1]


def test_write_is_visible_to_later_reads() -> None:
    reg = Registry({"a": 1})
    reg.write("a", 9)
    assert reg.read_many(["a"]) == [9]


def test_order_is_preserved() -> None:
    reg = Registry({"a": 1, "b": 2, "c": 3})
    assert reg.read_many(["c", "a", "b"]) == [3, 1, 2]
