"""EXP092 durable, append-only local JSONL evidence journal (stdlib only).

The journal is *evidence*, not a scientific result and not a resume log.  It
records only public, sanitized units that have finished.  Opening a journal is
exclusive: an existing path is never truncated or reused.  Every canonical
record is written with a single file write, flushed and ``fsync``-ed before the
caller is allowed to move on to the next unit.

Records form a SHA256 hash chain::

    body      = {seq, kind, prev_sha256, utc, payload}
    body_sha  = sha256(canonical_json(body))
    record    = body + {body_sha256: body_sha}

``prev_sha256`` of the first record is 64 zeroes; later records point at the
previous record's ``body_sha256``.  The offline reader rejects duplicate,
out-of-order, interior-corrupt and foreign-binding records.  A final line that
does not end in a newline is reported as an explicit incomplete tail and is
never admitted as a valid event.  The reader never repairs or truncates.

``fsync`` reduces, but cannot prove survival of, every hardware/storage failure.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

PROTOCOL = "exp092.durable.v1"
JOURNAL_SCHEMA = "exp092.journal.v1"
GENESIS_SHA256 = "0" * 64

_BODY_KEYS = ("seq", "kind", "prev_sha256", "utc", "payload")


class JournalError(Exception):
    """A closed, sanitized journal failure (no arbitrary payload text)."""

    def __init__(self, code: str, *, detail: Mapping[str, Any] | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.detail = dict(detail or {})

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code}
        if self.detail:
            payload["detail"] = dict(self.detail)
        return payload


def canonical_json(value: Any) -> str:
    """Canonical JSON used for the hash chain."""
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def journal_path_for(output_path: Path | str) -> Path:
    """Deterministic journal path for a collector output path."""
    output = Path(output_path)
    return output.with_name(output.name + ".journal.jsonl")


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise JournalError("journal_write_failed")
        view = view[written:]


class DurableJournal:
    """Append-only writer.  One instance owns one exclusively created path."""

    def __init__(self, path: Path | str, fd: int, *, fsync: bool = True) -> None:
        self.path = Path(path)
        self._fd: int | None = fd
        self._fsync = fsync
        self._seq = 0
        self._prev_sha256 = GENESIS_SHA256
        self.records_written = 0

    @classmethod
    def open_new(
        cls,
        path: Path | str,
        *,
        binding: Mapping[str, Any],
        planned: Mapping[str, Any],
        created_utc: datetime | None = None,
        fsync: bool = True,
    ) -> "DurableJournal":
        """Create a new journal exclusively; refuse any existing path."""
        journal_path = Path(path)
        journal_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(
                str(journal_path),
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
        except FileExistsError:
            raise JournalError("journal_exists") from None
        except OSError:
            raise JournalError("journal_open_failed") from None
        journal = cls(journal_path, fd, fsync=fsync)
        try:
            journal.append(
                "header",
                {
                    "schema": JOURNAL_SCHEMA,
                    "protocol": PROTOCOL,
                    "binding": dict(binding),
                    "planned": dict(planned),
                },
                utc=created_utc,
            )
        except Exception:
            journal.close()
            raise
        return journal

    def append(
        self,
        kind: str,
        payload: Mapping[str, Any],
        *,
        utc: datetime | None = None,
    ) -> dict[str, Any]:
        """Append one canonical record, flush and fsync it before returning."""
        if self._fd is None:
            raise JournalError("journal_closed")
        if not isinstance(kind, str) or not kind:
            raise JournalError("journal_kind_invalid")
        body = {
            "seq": self._seq,
            "kind": kind,
            "prev_sha256": self._prev_sha256,
            "utc": _utc_iso(utc or datetime.now(timezone.utc)),
            "payload": dict(payload),
        }
        body_sha = sha256_text(canonical_json(body))
        record = dict(body)
        record["body_sha256"] = body_sha
        line = canonical_json(record) + "\n"
        try:
            _write_all(self._fd, line.encode("utf-8"))
            os.fsync(self._fd)
        except OSError:
            raise JournalError("journal_write_failed") from None
        self._seq += 1
        self._prev_sha256 = body_sha
        self.records_written += 1
        return record

    def close(self) -> None:
        fd, self._fd = self._fd, None
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass

    def __enter__(self) -> "DurableJournal":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()


@dataclass
class JournalRead:
    """Offline, read-only view of a journal.  Never resumes execution."""

    path: Path
    header: Mapping[str, Any] | None = None
    binding: Mapping[str, Any] | None = None
    planned: Mapping[str, Any] | None = None
    records: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    incomplete_tail: bool = False
    incomplete_tail_reason: str | None = None
    last_seq: int | None = None


def _parse_record(raw_line: bytes, index: int) -> dict[str, Any]:
    try:
        record = json.loads(raw_line.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise JournalError(
            "journal_record_invalid", detail={"record_index": index}
        ) from None
    if not isinstance(record, dict):
        raise JournalError("journal_record_invalid", detail={"record_index": index})
    if set(record) != set(_BODY_KEYS) | {"body_sha256"}:
        raise JournalError("journal_record_invalid", detail={"record_index": index})
    body = {key: record[key] for key in _BODY_KEYS}
    expected = sha256_text(canonical_json(body))
    if record.get("body_sha256") != expected:
        raise JournalError(
            "journal_checksum_invalid", detail={"record_index": index}
        )
    return record


def read_journal(
    path: Path | str,
    *,
    expected_binding: Mapping[str, Any] | None = None,
) -> JournalRead:
    """Verify the chain and return committed records.

    A final fragment without a terminating newline is an incomplete tail: its
    bytes are left untouched and it is not returned as an event.  Interior
    corruption, binding mismatch, duplicate or out-of-order sequence fails
    closed with :class:`JournalError`.
    """
    journal_path = Path(path)
    try:
        raw = journal_path.read_bytes()
    except OSError:
        raise JournalError("journal_unreadable") from None

    read = JournalRead(path=journal_path)
    if raw and not raw.endswith(b"\n"):
        read.incomplete_tail = True
        read.incomplete_tail_reason = "unterminated_final_record"
        last_newline = raw.rfind(b"\n")
        committed = raw[: last_newline + 1] if last_newline >= 0 else b""
    else:
        committed = raw

    lines = committed.split(b"\n")
    # ``committed`` always ends with exactly one record terminator; drop that
    # single trailing empty element.  Every remaining element is a complete
    # record and must be non-empty/non-whitespace JSON -- blank records are
    # corruption, never silently filtered.
    if lines and lines[-1] == b"":
        lines = lines[:-1]
    if not lines:
        raise JournalError("journal_empty")
    for index, line in enumerate(lines):
        if not line.strip():
            raise JournalError(
                "journal_empty_record", detail={"record_index": index}
            )

    prev_sha = GENESIS_SHA256
    for index, line in enumerate(lines):
        record = _parse_record(line, index)
        if record.get("seq") != index:
            raise JournalError(
                "journal_sequence_invalid", detail={"record_index": index}
            )
        if record.get("prev_sha256") != prev_sha:
            raise JournalError(
                "journal_chain_invalid", detail={"record_index": index}
            )
        prev_sha = str(record["body_sha256"])
        read.records.append(record)
        read.last_seq = index

    header = read.records[0]
    if header.get("kind") != "header" or header.get("seq") != 0:
        raise JournalError("journal_header_invalid")
    payload = header.get("payload")
    if not isinstance(payload, Mapping):
        raise JournalError("journal_header_invalid")
    if payload.get("schema") != JOURNAL_SCHEMA or payload.get("protocol") != PROTOCOL:
        raise JournalError("journal_header_invalid")
    read.header = header
    read.binding = payload.get("binding") if isinstance(payload.get("binding"), Mapping) else None
    read.planned = payload.get("planned") if isinstance(payload.get("planned"), Mapping) else None
    if read.binding is None:
        raise JournalError("journal_header_invalid")
    if expected_binding is not None and dict(read.binding) != dict(expected_binding):
        raise JournalError("journal_foreign_binding")
    read.events = read.records[1:]
    return read


def completed_unit_keys(
    read: JournalRead,
    *,
    kinds: Sequence[str] = ("correctness_radius", "timing_cell"),
) -> list[tuple[str, str]]:
    """Public completed-unit identifiers from events; never invents units."""
    units: list[tuple[str, str]] = []
    wanted = set(kinds)
    for record in read.events:
        if record.get("kind") not in wanted:
            continue
        payload = record.get("payload")
        if not isinstance(payload, Mapping):
            continue
        units.append((str(record.get("kind")), canonical_json(payload)))
    return units
