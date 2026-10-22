"""Lossless, fail-closed run-state persistence for the live-model collector.

Design guarantees:

* ``calls.jsonl`` is parsed **strictly** on resume. A malformed line, a
  non-object record or a duplicate ``(scenario_id, condition, repetition)`` key
  raises :class:`LedgerError` and the caller aborts *before any write*.
* Existing ``calls.jsonl`` bytes are preserved as an immutable prefix. New
  observations are appended after that prefix and re-materialised with an atomic
  temp-file + ``os.replace`` after **every** observation, so an interruption
  keeps every committed observation durable.
* A no-op resume (no new observations) performs **no** write at all, leaving the
  ledger and every raw capture byte-for-byte unchanged.
* A single-writer lock file is created with ``O_CREAT|O_EXCL`` so concurrent
  writers fail closed instead of interleaving.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .util import canonical_json, write_bytes_atomic

Key = Tuple[str, str, int]

LOCK_NAME = "collector.lock"


class LedgerError(RuntimeError):
    """A fail-closed run-state rejection (no output is mutated)."""

    __slots__ = ("code", "detail")

    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def key_of(record: Any) -> Key:
    if not isinstance(record, dict):
        raise LedgerError("malformed_ledger_record", f"not an object: {record!r}")
    scenario_id = record.get("scenario_id")
    condition = record.get("condition")
    repetition = record.get("repetition")
    if not isinstance(scenario_id, str) or not scenario_id.strip():
        raise LedgerError("malformed_ledger_record", "missing scenario_id")
    if not isinstance(condition, str) or not condition.strip():
        raise LedgerError("malformed_ledger_record", "missing condition")
    if isinstance(repetition, bool) or not isinstance(repetition, int):
        raise LedgerError("malformed_ledger_record", "repetition must be an integer")
    return (scenario_id, condition, repetition)


def load_ledger(path: Path) -> Dict[Key, Dict[str, Any]]:
    """Strictly parse an existing ledger file. Empty/absent -> ``{}``."""
    path = Path(path)
    if not path.exists():
        return {}
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise LedgerError("unreadable_ledger", f"cannot read {path}: {exc}")
    records: Dict[Key, Dict[str, Any]] = {}
    for lineno, line in enumerate(raw.splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise LedgerError("malformed_ledger_line", f"line {lineno}: {exc}")
        key = key_of(record)
        if key in records:
            raise LedgerError("duplicate_ledger_key", f"line {lineno}: {key}")
        records[key] = record
    return records


def validate_ledger_records(records: Dict[Key, Dict[str, Any]], scenario_ids: Sequence[str],
                            conditions: Sequence[str], repetitions: int) -> None:
    """Reject any historical key that is not part of the frozen run plan.

    Keys must reference a declared scenario, a declared condition, and a
    repetition in ``0..repetitions-1``. Duplicate keys are already rejected by
    :func:`load_ledger`.
    """
    known_scenarios = set(scenario_ids)
    known_conditions = set(conditions)
    for key in records:
        scenario_id, condition, repetition = key
        if scenario_id not in known_scenarios:
            raise LedgerError("ledger_key_out_of_plan", f"unknown scenario_id: {scenario_id}")
        if condition not in known_conditions:
            raise LedgerError("ledger_key_out_of_plan", f"undeclared condition: {condition}")
        if repetition < 0 or repetition >= repetitions:
            raise LedgerError("ledger_repetition_out_of_range",
                              f"{key} not in 0..{repetitions - 1}")


class RunLedger:
    """Append-only, atomically persisted ledger over one output directory."""

    def __init__(self, path: Path, prefix: bytes,
                 records: Dict[Key, Dict[str, Any]]):
        self.path = Path(path)
        self._prefix = prefix
        self.records = records
        self._new_logs: List[Dict[str, Any]] = []

    @classmethod
    def open(cls, path: Path) -> "RunLedger":
        path = Path(path)
        if path.exists():
            prefix = path.read_bytes()
        else:
            prefix = b""
        return cls(path, prefix, load_ledger(path))

    @property
    def new_count(self) -> int:
        return len(self._new_logs)

    def has(self, key: Key) -> bool:
        return key in self.records

    def append(self, log: Dict[str, Any]) -> Key:
        key = key_of(log)
        if key in self.records:
            raise LedgerError("duplicate_ledger_key", f"already present: {key}")
        self.records[key] = log
        self._new_logs.append(log)
        self._flush()
        return key

    def _flush(self) -> None:
        payload = self._prefix
        if payload and not payload.endswith(b"\n"):
            payload += b"\n"
        for log in self._new_logs:
            payload += (canonical_json(log) + "\n").encode("utf-8")
        write_bytes_atomic(self.path, payload)

    def merged_logs(self) -> List[Dict[str, Any]]:
        """All records in insertion order (existing first, then new)."""
        return list(self.records.values())


class RunLock:
    """Explicit single-writer exclusion via ``O_CREAT|O_EXCL``."""

    def __init__(self, out_dir: Path, name: str = LOCK_NAME):
        self.path = Path(out_dir) / name
        self._fd: Optional[int] = None

    def acquire(self) -> None:
        try:
            self._fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise LedgerError("concurrent_writer",
                              f"another collector holds {self.path}")

    def release(self) -> None:
        if self._fd is None:
            # Never delete a lock file we did not create (e.g. failed acquire).
            return
        try:
            os.close(self._fd)
        except OSError:
            pass
        self._fd = None
        try:
            os.remove(str(self.path))
        except OSError:
            pass

    def __enter__(self) -> "RunLock":
        self.acquire()
        return self

    def __exit__(self, *exc) -> None:
        self.release()
