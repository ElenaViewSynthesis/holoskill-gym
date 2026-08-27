from __future__ import annotations

import json


def _schema() -> dict[str, str]:
    return {"version": "v1", "encoding": "utf-8", "producer": "holoskill"}


def serialize_records(records: list[dict[str, int]]) -> list[str]:
    """Serialize each record with the shared schema header."""

    header = json.dumps(_schema(), sort_keys=True)
    prefix = header + "|"
    return [prefix + json.dumps(record, sort_keys=True) for record in records]
