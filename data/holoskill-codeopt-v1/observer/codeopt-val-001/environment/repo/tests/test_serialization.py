import json

from src.serialization import serialize_records


def test_header_and_body_are_joined() -> None:
    out = serialize_records([{"a": 1}])
    header, body = out[0].split("|", 1)
    assert json.loads(header)["version"] == "v1"
    assert json.loads(body) == {"a": 1}


def test_every_record_carries_the_header() -> None:
    out = serialize_records([{"a": 1}, {"b": 2}])
    assert out[0].split("|", 1)[0] == out[1].split("|", 1)[0]


def test_empty_input() -> None:
    assert serialize_records([]) == []


def test_keys_are_sorted() -> None:
    out = serialize_records([{"b": 2, "a": 1}])
    assert out[0].split("|", 1)[1] == '{"a": 1, "b": 2}'
