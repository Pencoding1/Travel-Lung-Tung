"""Stdlib-only JSON / JSONL readers for the evaluator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .errors import SchemaError


def read_json(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SchemaError(f"manifest not found: {path}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise SchemaError(f"manifest is not valid JSON ({path}): {exc}") from exc


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    """Read a JSONL file into a list of objects, preserving line provenance.

    Blank lines are ignored. Any non-object line fails closed with the line
    number so a malformed raw record can never be silently dropped.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SchemaError(f"records file not found: {path}") from exc

    records: List[Dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            value = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise SchemaError(f"{path}:{line_number}: not valid JSON: {exc}") from exc
        if not isinstance(value, dict):
            raise SchemaError(f"{path}:{line_number}: record must be a JSON object")
        value["_source_line"] = line_number
        records.append(value)
    return records
