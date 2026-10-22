"""Dry-run ingestion planning for accepted web POIs.

The existing acquisition pipeline decides acceptance; this module only prepares
the payload, evidence sidecar and manifest, validates the payload shape, and can
hand it to an *injected* transport. The default is always a dry run. Nothing in
this repository calls a real ingestion endpoint, and ``imported`` is 0 unless a
fake/real transport explicitly reports a fully successful batch.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..acquisition.contracts import is_finite_in_range
from ..acquisition.identity import sha256_bytes, stable_source_id
from ..acquisition.storage import atomic_write_json, atomic_write_jsonl

Transport = Callable[[List[Dict[str, Any]]], Tuple[int, bytes]]


class IngestError(RuntimeError):
    def __init__(self, reason: str, detail: str = "") -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}" if detail else reason)


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            value = json.loads(line)
            if not isinstance(value, dict):
                raise IngestError("invalid_jsonl_row", str(path))
            rows.append(value)
    return rows


def validate_payload(payload: Dict[str, Any]) -> List[str]:
    problems: List[str] = []
    for key in ("id", "name", "latitude", "longitude", "address", "poi_categories"):
        if key not in payload:
            problems.append(f"missing_{key}")
    if not isinstance(payload.get("id"), str) or not payload.get("id", "").strip():
        problems.append("invalid_id")
    if not is_finite_in_range(payload.get("latitude"), -90.0, 90.0):
        problems.append("invalid_latitude")
    if not is_finite_in_range(payload.get("longitude"), -180.0, 180.0):
        problems.append("invalid_longitude")
    address = payload.get("address")
    if not isinstance(address, dict) or not address.get("city") or not address.get("district"):
        problems.append("incomplete_admin")
    categories = payload.get("poi_categories")
    if not isinstance(categories, list) or not categories:
        problems.append("missing_categories")
    return problems


def build_ingest_plan(
    accepted_path: Path,
    candidates_path: Path,
    out_dir: Path,
    *,
    dataset: str,
    synthetic: bool,
    transport: Optional[Transport] = None,
    dry_run: bool = True,
    opt_in: bool = False,
) -> Dict[str, Any]:
    accepted = _read_jsonl(Path(accepted_path))
    candidates = _read_jsonl(Path(candidates_path))
    evidence_by_id: Dict[str, Dict[str, Any]] = {}
    for row in candidates:
        entity_id = row.get("source_entity_id")
        source_type = row.get("source_type")
        if not isinstance(entity_id, str) or not entity_id or not isinstance(source_type, str):
            continue
        evidence_by_id[stable_source_id(source_type, entity_id)] = {
            "source_type": source_type,
            "source_entity_id": entity_id,
            "description": row.get("description"),
            "review_text": row.get("review_text"),
            "field_evidence": row.get("field_evidence"),
            "raw_content_reference": row.get("raw_content_reference"),
            "raw_sha256": row.get("raw_sha256"),
            "source_url": row.get("source_url"),
            "retrieved_at": row.get("retrieved_at"),
        }

    payloads: List[Dict[str, Any]] = []
    sidecar: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    for row in accepted:
        problems = validate_payload(row)
        if problems:
            rejected.append({"id": row.get("id"), "problems": problems})
            continue
        payloads.append(row)
        sidecar.append(
            {
                "poi_id": row["id"],
                "source_id": row.get("source_id"),
                "evidence": evidence_by_id.get(row["id"]),
            }
        )

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload_path = out_dir / "ingestion_payload.jsonl"
    evidence_path = out_dir / "ingestion_evidence.jsonl"
    atomic_write_jsonl(payload_path, payloads)
    atomic_write_jsonl(evidence_path, sidecar)
    plan = {
        "schema_version": 1,
        "dataset": dataset,
        "synthetic": bool(synthetic),
        "dry_run": bool(dry_run),
        "opt_in": bool(opt_in),
        "counts": {
            "accepted_rows": len(accepted),
            "payload_rows": len(payloads),
            "payload_rejected": len(rejected),
            "imported": 0,
        },
        "rejected": rejected,
        "payload_path": payload_path.name,
        "evidence_path": evidence_path.name,
        "note": "Evidence sidecar preserves description/review/raw lineage; the POI payload itself is unchanged.",
    }
    atomic_write_json(out_dir / "ingestion_plan.json", plan)

    if not dry_run:
        plan["transport_result"] = _submit(payloads, transport=transport, opt_in=opt_in)
    return plan


def _submit(
    payloads: List[Dict[str, Any]],
    *,
    transport: Optional[Transport],
    opt_in: bool,
) -> Dict[str, Any]:
    if not opt_in:
        raise IngestError("opt_in_required", "live submit requires explicit opt_in=True")
    if transport is None:
        raise IngestError("transport_not_configured", "no default live ingestion client exists")
    try:
        status, body = transport(payloads[:10])
    except OSError:
        # Exception text can embed the endpoint URL, credentials or local
        # paths; the status contract only needs a stable classification.
        return {"status": "failed", "reason": "network_error", "imported": 0}
    try:
        decoded = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        decoded = None
    if status == 422:
        return {
            "status": "failed",
            "reason": "canary_rejected_422",
            "imported": 0,
            "response_sha256": sha256_bytes(body),
        }
    if status < 200 or status >= 300:
        return {
            "status": "failed",
            "reason": f"http_{status}",
            "imported": 0,
            "response_sha256": sha256_bytes(body),
        }
    imported = decoded.get("imported") if isinstance(decoded, dict) else None
    if not isinstance(imported, int) or isinstance(imported, bool) or imported < 0:
        return {
            "status": "unverified",
            "reason": "response_did_not_report_imported_count",
            "imported": 0,
            "response_sha256": sha256_bytes(body),
        }
    return {
        "status": "ok",
        "imported": imported,
        "response_sha256": sha256_bytes(body),
    }


@dataclass
class IngestPlan:
    payloads: List[Dict[str, Any]] = field(default_factory=list)
    plan: Dict[str, Any] = field(default_factory=dict)
