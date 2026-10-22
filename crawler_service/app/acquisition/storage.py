"""Atomic, collision-safe file writes and JSONL helpers.

Raw source bytes are written with an existence check so repeated runs never
overwrite an immutable raw capture. Structured outputs are written to a
temporary sibling and atomically moved into place. The ledger is append-only.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable, Mapping


class OutputCollisionError(RuntimeError):
    """Raised when a write would overwrite immutable or conflicting content."""


def atomic_write_bytes(path: Path, payload: bytes, *, overwrite: bool = False) -> None:
    """Write ``payload`` to ``path`` atomically.

    When ``overwrite`` is false and the destination already exists, the bytes
    must match exactly; otherwise an ``OutputCollisionError`` is raised.
    """

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = path.read_bytes()
        if existing == payload:
            return
        if not overwrite:
            raise OutputCollisionError(
                f"refusing to overwrite existing file with different bytes: {path}"
            )
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def atomic_write_text(path: Path, text: str, *, overwrite: bool = True) -> None:
    atomic_write_bytes(Path(path), text.encode("utf-8"), overwrite=overwrite)


def atomic_write_json(path: Path, value: Any, *, overwrite: bool = True) -> None:
    text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    atomic_write_text(path, text, overwrite=overwrite)


def atomic_write_jsonl(path: Path, rows: Iterable[Mapping], *, overwrite: bool = True) -> None:
    lines = [json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows]
    body = "\n".join(lines)
    if body:
        body += "\n"
    atomic_write_text(path, body, overwrite=overwrite)


def append_jsonl(path: Path, row: Mapping) -> None:
    """Append a single row to an append-only JSONL ledger."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
