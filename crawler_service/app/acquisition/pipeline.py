"""Deterministic acquisition pipeline and durable dry-run output.

The pipeline validates *all* configuration and *all* source payloads before
writing anything, captures the exact raw bytes immutably, parses candidates
through the source adapters, applies the per-entity reviewed mapping, persists
decisions in a durable state file with audit history, appends an append-only
ledger, and atomically writes raw/candidate/decision/accepted/quarantine JSONL
plus a summary manifest. It never performs live ingestion or network access.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import PIPELINE_VERSION
from .adapters import get_adapter, supported_source_types
from .adapters.base import SourceFormatError
from .contracts import (
    CollectionStatus,
    DecisionOutcome,
    IngestionDecision,
    POICandidate,
    RawSourceRecord,
    ReasonCode,
    ResolutionStatus,
    parse_utc,
    to_utc_iso,
)
from .identity import fact_fingerprint, sha256_bytes, stable_source_id
from .resolution import (
    ConfigError,
    MappingManifest,
    Resolution,
    SourceReview,
    load_json_object,
    load_mapping_manifest,
    resolve_candidate,
)
from .storage import (
    append_jsonl,
    atomic_write_bytes,
    atomic_write_json,
    atomic_write_jsonl,
)

_SAFE_SOURCE_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_RESERVED_NAMES = {
    "con", "prn", "aux", "nul",
    *{f"com{i}" for i in range(1, 10)},
    *{f"lpt{i}" for i in range(1, 10)},
}


def validate_source_id(source_id: Any) -> str:
    """Reject ids that are unsafe as a filename component or path token."""

    if not isinstance(source_id, str) or not source_id.strip():
        raise ConfigError("source_id must be a non-empty string")
    canonical = source_id.strip()
    if len(canonical) > 128:
        raise ConfigError(f"source_id is too long: {canonical!r}")
    if canonical in (".", ".."):
        raise ConfigError(f"source_id is not allowed: {canonical!r}")
    if any(sep in canonical for sep in ("/", "\\", ":", "\0")):
        raise ConfigError(f"source_id contains a path separator: {canonical!r}")
    if not _SAFE_SOURCE_ID_RE.match(canonical):
        raise ConfigError(f"source_id contains unsafe characters: {canonical!r}")
    if canonical.split(".")[0].lower() in _RESERVED_NAMES:
        raise ConfigError(f"source_id is a reserved filename: {canonical!r}")
    return canonical


def validate_dataset(dataset: Any) -> str:
    """Reject an unsafe or blank dataset scope token."""

    if not isinstance(dataset, str) or not dataset.strip():
        raise ConfigError("manifest.dataset must be a non-empty string")
    canonical = dataset.strip()
    if len(canonical) > 128:
        raise ConfigError(f"manifest.dataset is too long: {canonical!r}")
    if any(sep in canonical for sep in ("/", "\\", ":", "\0")):
        raise ConfigError(f"manifest.dataset contains a path separator: {canonical!r}")
    if not _SAFE_SOURCE_ID_RE.match(canonical):
        raise ConfigError(f"manifest.dataset contains unsafe characters: {canonical!r}")
    return canonical


def scope_token(dataset: str, synthetic: bool) -> str:
    """Canonical immutable scope for one state directory.

    A scope is the explicit dataset identity plus its synthetic/real
    classification. Synthetic and real records may never share durable state, so
    a state directory is bound to exactly one scope for its whole life.
    """

    return f"{dataset}::{('synthetic' if synthetic else 'real')}"


_SCOPE_CLASSIFICATIONS: Dict[str, bool] = {"synthetic": True, "real": False}
_ALLOWED_STATE_STATUSES = {
    DecisionOutcome.ACCEPTED.value,
    DecisionOutcome.REJECTED.value,
    DecisionOutcome.REQUIRES_REVIEW.value,
}


def parse_scope(token: Any) -> Tuple[str, bool]:
    """Strictly parse ``"<dataset>::<synthetic|real>"`` into its parts.

    Any malformed token, extra separator or unknown classification is rejected,
    so a dataset/classification mismatch can never be hidden behind a loose
    string comparison. No truthiness or ``bool("false")`` coercion is used.
    """

    if not isinstance(token, str) or "::" not in token:
        raise ConfigError(
            f"malformed state scope {token!r}; expected '<dataset>::<synthetic|real>'"
        )
    dataset, _, classification = token.partition("::")
    if "::" in classification:
        raise ConfigError(f"malformed state scope {token!r}: too many separators")
    if classification not in _SCOPE_CLASSIFICATIONS:
        raise ConfigError(
            f"malformed state scope {token!r}: classification must be "
            f"{sorted(_SCOPE_CLASSIFICATIONS)}"
        )
    try:
        canonical_dataset = validate_dataset(dataset)
    except ConfigError as exc:
        raise ConfigError(f"malformed state scope {token!r}: {exc}") from exc
    if canonical_dataset != dataset:
        raise ConfigError(f"malformed state scope {token!r}: non-canonical dataset")
    return canonical_dataset, _SCOPE_CLASSIFICATIONS[classification]


def _validate_state_entry(
    key: Any, entry: Dict[str, Any], *, expected_synthetic: bool, source: Path
) -> None:
    """Fail closed on an entry that is malformed or contradicts the scope.

    Every entry must carry an explicit boolean ``synthetic`` flag matching the
    state's classification, plus the identity/status fields needed to keep the
    accepted summary honest. This runs on load, so a contradictory entry is
    rejected even when this run never touches it.
    """

    synthetic = entry.get("synthetic")
    if type(synthetic) is not bool:
        raise ConfigError(
            f"state entry {key!r} in {source} must have an explicit boolean "
            f"'synthetic' flag, got {synthetic!r}"
        )
    if synthetic != expected_synthetic:
        raise ConfigError(
            f"state entry {key!r} in {source} declares synthetic={synthetic} but "
            f"its scope is {'synthetic' if expected_synthetic else 'real'}; "
            "contradictory/mixed state is refused (fail closed)"
        )
    stable_id = entry.get("stable_id")
    if not isinstance(stable_id, str) or not stable_id.strip():
        raise ConfigError(f"state entry {key!r} in {source} has no valid stable_id")
    status = entry.get("status")
    if status not in _ALLOWED_STATE_STATUSES:
        raise ConfigError(
            f"state entry {key!r} in {source} has invalid status {status!r}"
        )
    if status == DecisionOutcome.ACCEPTED.value:
        resolved = entry.get("resolved")
        if (
            not isinstance(resolved, dict)
            or not isinstance(resolved.get("id"), str)
            or not resolved.get("id").strip()
        ):
            raise ConfigError(
                f"accepted state entry {key!r} in {source} has no valid resolved "
                "payload/id; refusing to emit a malformed accepted record"
            )



@dataclass
class SourceSpec:
    source_id: str
    source_type: str
    source_url: str
    license: str
    retrieved_at: str
    export_path: Path
    synthetic: bool = False


@dataclass
class AcquisitionManifest:
    sources: List[SourceSpec]
    synthetic: bool = False
    sha256: str = ""
    dataset: str = "default"


def _resolve_export_path(manifest_dir: Path, raw: str) -> Path:
    candidate = Path(raw)
    if candidate.is_absolute():
        return candidate
    local = manifest_dir / candidate
    if local.exists():
        return local
    return Path.cwd() / candidate


def _require_bool(value: Any, label: str, *, default: bool = False) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ConfigError(f"{label} must be a boolean, got {type(value).__name__}")
    return value


def load_acquisition_manifest(path: Path) -> AcquisitionManifest:
    path = Path(path)
    try:
        payload = path.read_bytes()
        document = json.loads(payload.decode("utf-8"))
    except OSError as exc:
        raise ConfigError(f"cannot read manifest {path}: {exc}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConfigError(f"invalid manifest JSON in {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise ConfigError(f"{path} must contain a JSON object")

    manifest_dir = path.parent
    top_synthetic = _require_bool(document.get("synthetic"), "manifest.synthetic")
    dataset = validate_dataset(document.get("dataset", "default"))

    raw_sources = document.get("sources")
    if not isinstance(raw_sources, list) or not raw_sources:
        raise ConfigError("acquisition manifest requires a non-empty 'sources' list")

    supported = supported_source_types()
    sources: List[SourceSpec] = []
    seen_ids: Dict[str, int] = {}
    for index, entry in enumerate(raw_sources):
        if not isinstance(entry, dict):
            raise ConfigError(f"sources[{index}] must be an object")
        source_id = validate_source_id(entry.get("source_id"))
        if source_id in seen_ids:
            raise ConfigError(f"duplicate source_id {source_id!r} in manifest")
        seen_ids[source_id] = index

        source_type = entry.get("source_type")
        if not isinstance(source_type, str) or source_type not in supported:
            raise ConfigError(
                f"sources[{index}].source_type must be one of {sorted(supported)}"
            )
        source_url = entry.get("source_url")
        if not isinstance(source_url, str) or not source_url.strip():
            raise ConfigError(f"sources[{index}].source_url must be non-empty")
        license_value = entry.get("license")
        if not isinstance(license_value, str) or not license_value.strip():
            raise ConfigError(f"sources[{index}].license must be non-empty")
        export_path = entry.get("export_path")
        if not isinstance(export_path, str) or not export_path.strip():
            raise ConfigError(f"sources[{index}].export_path must be non-empty")
        try:
            retrieved_utc = to_utc_iso(parse_utc(entry.get("retrieved_at")))
        except ValueError as exc:
            raise ConfigError(f"sources[{index}].retrieved_at invalid: {exc}") from exc

        resolved_export = _resolve_export_path(manifest_dir, export_path.strip())
        if not resolved_export.is_file():
            raise ConfigError(
                f"sources[{index}].export_path does not exist: {resolved_export}"
            )
        sources.append(
            SourceSpec(
                source_id=source_id,
                source_type=source_type,
                source_url=source_url.strip(),
                license=license_value.strip(),
                retrieved_at=retrieved_utc,
                export_path=resolved_export,
                synthetic=_require_bool(
                    entry.get("synthetic"), f"sources[{index}].synthetic"
                ),
            )
        )

    return AcquisitionManifest(
        sources=sources,
        synthetic=top_synthetic,
        sha256=sha256_bytes(payload),
        dataset=dataset,
    )


class StateStore:
    """Durable run state bound to one immutable dataset/synthetic scope.

    The scope is recorded when the state file is created and can never change: a
    run whose scope differs (in either direction) is rejected *before* any byte
    is written, so synthetic and real records can never share durable identity
    state, be promoted or demoted, or inherit each other's acceptance. A legacy,
    scope-less or corrupt state file fails closed rather than being reset.
    """

    def __init__(self, path: Path, *, scope: str):
        self.path = Path(path)
        self.scope = scope
        self.entries: Dict[str, Dict[str, Any]] = {}
        if not self.path.exists():
            return
        document = load_json_object(self.path)
        version = document.get("pipeline_version")
        if version != PIPELINE_VERSION:
            raise ConfigError(
                f"state file {self.path} has pipeline_version {version!r}, "
                f"expected {PIPELINE_VERSION}; legacy state is never migrated or "
                "rewritten automatically (fail closed; migrate read-only)"
            )
        stored_scope = document.get("scope")
        if not isinstance(stored_scope, str) or not stored_scope.strip():
            raise ConfigError(
                f"state file {self.path} has no explicit dataset/synthetic scope; "
                "refusing to reuse it (fail closed)"
            )
        stored_dataset, stored_synthetic = parse_scope(stored_scope)
        requested_dataset, requested_synthetic = parse_scope(scope)
        if (stored_dataset, stored_synthetic) != (requested_dataset, requested_synthetic):
            raise ConfigError(
                f"state scope mismatch: {self.path} is bound to scope "
                f"{stored_scope!r} but this run is {scope!r}; use a fresh output "
                "directory for the other dataset/synthetic scope"
            )
        entries = document.get("entries")
        if not isinstance(entries, dict):
            raise ConfigError(f"state file {self.path} has no 'entries' object")
        for key, value in entries.items():
            if not isinstance(value, dict):
                raise ConfigError(
                    f"state file {self.path} entry {key!r} is not an object"
                )
            _validate_state_entry(
                key, value, expected_synthetic=stored_synthetic, source=self.path
            )
        self.entries = entries

    def save(self) -> None:
        atomic_write_json(
            self.path,
            {
                "pipeline_version": PIPELINE_VERSION,
                "scope": self.scope,
                "entries": self.entries,
            },
        )


@dataclass
class RunResult:
    summary: Dict[str, Any]
    summary_path: Path
    outputs: Dict[str, Path] = field(default_factory=dict)


def _is_within(child: Path, parent: Path) -> bool:
    child = Path(child).resolve()
    parent = Path(parent).resolve()
    return child == parent or parent in child.parents


def _classify(resolution: Resolution) -> str:
    if resolution.resolved is not None:
        return DecisionOutcome.ACCEPTED.value
    if resolution.resolution_status == ResolutionStatus.UNRESOLVED.value:
        return DecisionOutcome.REJECTED.value
    return DecisionOutcome.REQUIRES_REVIEW.value


def _decision(
    candidate_id: str,
    outcome: str,
    reasons: List[str],
    resolved_id: Optional[str],
    decided_at: str,
    evidence_refs: List[str],
    *,
    prior_outcome: Optional[str] = None,
    info_codes: Optional[List[str]] = None,
) -> IngestionDecision:
    return IngestionDecision(
        candidate_id=candidate_id,
        outcome=outcome,
        reason_codes=reasons,
        resolved_id=resolved_id,
        decided_at=decided_at,
        evidence_references=evidence_refs,
        prior_outcome=prior_outcome,
        info_codes=list(info_codes or []),
    )


def _apply_resolution(
    entry: Dict[str, Any],
    resolution: Resolution,
    *,
    fingerprint: str,
    policy_hash: str,
    raw_sha256: str,
    at: str,
    run_id: str,
    synthetic: bool,
) -> None:
    resolved = resolution.resolved
    outcome = _classify(resolution)
    entry.update(
        {
            "fact_fingerprint": fingerprint,
            "raw_sha256": raw_sha256,
            "policy_hash": policy_hash,
            "status": outcome,
            "resolution_status": resolution.resolution_status,
            "reasons": list(resolution.reasons),
            "info_codes": list(resolution.info_codes),
            "resolved": resolved.as_payload() if resolved else None,
            "provenance": resolved.provenance if resolved else None,
            "category_ids": list(resolved.category_ids) if resolved else [],
            "synthetic": bool(synthetic),
            "last_seen": at,
        }
    )
    entry.setdefault("history", []).append(
        {
            "run_id": run_id,
            "at": at,
            "policy_hash": policy_hash,
            "outcome": outcome,
            "resolution_status": resolution.resolution_status,
            "reasons": list(resolution.reasons),
            "category_ids": list(resolved.category_ids) if resolved else [],
        }
    )


def run_pipeline(
    manifest_path: Path,
    mapping_path: Path,
    out_dir: Path,
    *,
    now: Optional[str] = None,
    dry_run: bool = True,
) -> RunResult:
    """Execute a dry-run acquisition run.

    Configuration and every source payload are validated before the first byte
    is written, so an invalid or malformed input (including a malformed *later*
    source) produces no partial output.
    """

    manifest = load_acquisition_manifest(Path(manifest_path))
    mapping: MappingManifest = load_mapping_manifest(Path(mapping_path))

    if now:
        try:
            decided_at = to_utc_iso(parse_utc(now))
        except ValueError as exc:
            raise ConfigError(f"--now is not a UTC ISO-8601 timestamp: {exc}") from exc
    else:
        decided_at = to_utc_iso(datetime.now(timezone.utc))

    out_dir = Path(out_dir)
    if out_dir.exists() and not out_dir.is_dir():
        raise ConfigError(f"output path is not a directory: {out_dir}")

    for source in manifest.sources:
        if _is_within(source.export_path, out_dir):
            raise ConfigError(
                f"source export {source.export_path} is inside the output "
                f"directory {out_dir}; refusing to overwrite inputs"
            )

    # Phase 1: validate and parse every source into memory before any write.
    parsed_sources: List[Tuple[SourceSpec, bytes, str, str, List[POICandidate], bool]] = []
    for source in manifest.sources:
        payload_bytes = source.export_path.read_bytes()
        raw_sha256 = sha256_bytes(payload_bytes)
        try:
            parsed = json.loads(payload_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ConfigError(
                f"source {source.source_id!r} is not valid UTF-8 JSON: {exc}"
            ) from exc
        adapter = get_adapter(source.source_type)
        try:
            candidates = adapter.parse(
                parsed,
                source_id=source.source_id,
                source_url=source.source_url,
                license=source.license,
                retrieved_at=source.retrieved_at,
                raw_content_reference="",  # assigned after the blob name is known
                raw_sha256=raw_sha256,
            )
        except SourceFormatError as exc:
            raise ConfigError(
                f"source {source.source_id!r} failed collection: {exc}"
            ) from exc
        review = mapping.sources.get(source.source_id)
        effective_synthetic = (
            bool(manifest.synthetic)
            or bool(source.synthetic)
            or bool(review.synthetic if review else False)
        )
        parsed_sources.append(
            (source, payload_bytes, raw_sha256, "", candidates, effective_synthetic)
        )

    # Phase 1b: derive the immutable dataset/synthetic scope from the effective
    # classification and reject a mismatched existing state *before* creating the
    # output directory or writing any byte.
    classifications = {entry[5] for entry in parsed_sources}
    if len(classifications) != 1:
        raise ConfigError(
            "manifest mixes synthetic and real sources; strict dataset/synthetic "
            "separation requires one classification per state directory (split "
            "the manifest into separate runs)"
        )
    run_synthetic = next(iter(classifications))
    scope = scope_token(manifest.dataset, run_synthetic)

    # Phase 2: all inputs valid -> validate scope, then create output and persist.
    # The existing state is validated before the output directory is even created.
    state = StateStore(out_dir / "state.json", scope=scope)
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = out_dir / "raw"

    policy_hash = mapping.sha256
    run_id = sha256_bytes(f"{decided_at}\x1f{policy_hash}\x1f{manifest.sha256}".encode())[:16]

    raw_index: List[Dict[str, Any]] = []
    candidate_rows: List[Dict[str, Any]] = []
    decision_rows: List[Dict[str, Any]] = []
    per_source_counts: Dict[str, Dict[str, int]] = {}
    source_meta: List[Dict[str, Any]] = []

    for source, payload_bytes, raw_sha256, _unused, candidates, effective_synthetic in parsed_sources:
        blob_name = f"{sha256_bytes(source.source_id.encode('utf-8'))[:16]}__{raw_sha256[:12]}.json"
        raw_blob_rel = f"raw/{blob_name}"
        atomic_write_bytes(raw_dir / blob_name, payload_bytes, overwrite=False)

        review = mapping.sources.get(source.source_id)
        counts = per_source_counts.setdefault(
            source.source_id,
            {"candidates": 0, "accepted": 0, "rejected": 0, "duplicate": 0, "requires_review": 0},
        )
        source_meta.append(
            {
                "source_id": source.source_id,
                "source_type": source.source_type,
                "source_url": source.source_url,
                "license": source.license,
                "retrieved_at": source.retrieved_at,
                "synthetic": effective_synthetic,
                "reviewed_entities": len(review.entities) if review else 0,
                "counts": counts,
            }
        )

        for candidate in candidates:
            counts["candidates"] += 1
            candidate.raw_content_reference = raw_blob_rel
            candidate_rows.append(
                {
                    "source_id": source.source_id,
                    "synthetic": effective_synthetic,
                    **candidate.as_dict(),
                }
            )
            raw_index.append(
                RawSourceRecord(
                    source_type=source.source_type,
                    source_id=source.source_id,
                    source_url=source.source_url,
                    retrieved_at=source.retrieved_at,
                    license=source.license,
                    raw_content_reference=raw_blob_rel,
                    sha256=raw_sha256,
                    collection_status=CollectionStatus.OBTAINED.value,
                    extraction_metadata={
                        "source_entity_id": candidate.source_entity_id,
                        "geometry_kind": candidate.geometry_kind,
                        "source_revision": candidate.source_revision,
                        "field_paths": candidate.field_paths,
                        **(
                            {
                                "description": candidate.description,
                                "review_text": candidate.review_text,
                                "field_evidence": [
                                    dict(item) for item in candidate.field_evidence
                                ],
                            }
                            if (
                                candidate.description is not None
                                or candidate.review_text is not None
                                or candidate.field_evidence
                            )
                            else {}
                        ),
                    },
                ).as_dict()
            )

            if not candidate.source_entity_id:
                identity_reason = (
                    ReasonCode.INVALID_SOURCE_IDENTITY
                    if ReasonCode.INVALID_SOURCE_IDENTITY in candidate.uncertainty_codes
                    else ReasonCode.MISSING_SOURCE_IDENTITY
                )
                decision = _decision(
                    candidate_id=f"{source.source_id}:(invalid identity)",
                    outcome=DecisionOutcome.REJECTED.value,
                    reasons=[identity_reason],
                    resolved_id=None,
                    decided_at=decided_at,
                    evidence_refs=[],
                )
                decision_rows.append(
                    {"source_id": source.source_id, "synthetic": effective_synthetic, **decision.as_dict()}
                )
                counts["rejected"] += 1
                continue

            stable_id = stable_source_id(candidate.source_type, candidate.source_entity_id)
            fingerprint = fact_fingerprint(candidate)
            entry = state.entries.get(stable_id)

            if entry is None:
                resolution = resolve_candidate(candidate, review, mapping)
                entry = {
                    "stable_id": stable_id,
                    "source_type": candidate.source_type,
                    "source_entity_id": candidate.source_entity_id,
                    "source_id": source.source_id,
                    "conflicted": False,
                    "first_seen": decided_at,
                    "last_seen": decided_at,
                    "history": [],
                }
                _apply_resolution(
                    entry,
                    resolution,
                    fingerprint=fingerprint,
                    policy_hash=policy_hash,
                    raw_sha256=candidate.raw_sha256,
                    at=decided_at,
                    run_id=run_id,
                    synthetic=effective_synthetic,
                )
                state.entries[stable_id] = entry
                outcome = entry["status"]
                counts[
                    {
                        "accepted": "accepted",
                        "rejected": "rejected",
                        "requires_review": "requires_review",
                    }[outcome]
                ] += 1
                decision = _decision(
                    candidate_id=stable_id,
                    outcome=outcome,
                    reasons=entry["reasons"],
                    resolved_id=stable_id if outcome == "accepted" else None,
                    decided_at=decided_at,
                    evidence_refs=[resolution.evidence_references[0]]
                    if resolution.evidence_references
                    else [],
                    info_codes=resolution.info_codes,
                )
            elif bool(entry.get("synthetic")) != effective_synthetic:
                # Symmetric scope guard: a synthetic record must never inherit a
                # real acceptance (or vice versa). The prior facts, provenance,
                # status and history are preserved untouched; the record is only
                # flagged for review and resolved_id is never handed out, so no
                # one-sided promotion or demotion can occur in either order.
                entry["last_seen"] = decided_at
                entry["conflicted"] = True
                entry["conflict_reason"] = ReasonCode.SYNTHETIC_REAL_COLLISION
                counts["requires_review"] += 1
                decision = _decision(
                    candidate_id=stable_id,
                    outcome=DecisionOutcome.REQUIRES_REVIEW.value,
                    reasons=[ReasonCode.SYNTHETIC_REAL_COLLISION],
                    resolved_id=None,
                    decided_at=decided_at,
                    evidence_refs=[],
                )

            elif fingerprint != entry.get("fact_fingerprint"):
                entry["conflicted"] = True
                entry["conflict_reason"] = ReasonCode.CONFLICTING_UPDATE
                entry["last_seen"] = decided_at
                counts["requires_review"] += 1
                decision = _decision(
                    candidate_id=stable_id,
                    outcome=DecisionOutcome.REQUIRES_REVIEW.value,
                    reasons=[ReasonCode.CONFLICTING_UPDATE],
                    resolved_id=stable_id if entry.get("status") == "accepted" else None,
                    decided_at=decided_at,
                    evidence_refs=[],
                )
            elif policy_hash != entry.get("policy_hash"):
                prior_outcome = entry.get("status")
                resolution = resolve_candidate(candidate, review, mapping)
                _apply_resolution(
                    entry,
                    resolution,
                    fingerprint=fingerprint,
                    policy_hash=policy_hash,
                    raw_sha256=candidate.raw_sha256,
                    at=decided_at,
                    run_id=run_id,
                    synthetic=effective_synthetic,
                )
                outcome = entry["status"]
                counts[
                    {
                        "accepted": "accepted",
                        "rejected": "rejected",
                        "requires_review": "requires_review",
                    }[outcome]
                ] += 1
                decision = _decision(
                    candidate_id=stable_id,
                    outcome=outcome,
                    reasons=[ReasonCode.POLICY_RE_EVALUATED] + list(entry["reasons"]),
                    resolved_id=stable_id if outcome == "accepted" else None,
                    decided_at=decided_at,
                    evidence_refs=[resolution.evidence_references[0]]
                    if resolution.evidence_references
                    else [],
                    prior_outcome=prior_outcome,
                    info_codes=resolution.info_codes,
                )
            else:
                entry["last_seen"] = decided_at
                counts["duplicate"] += 1
                decision = _decision(
                    candidate_id=stable_id,
                    outcome=DecisionOutcome.DUPLICATE.value,
                    reasons=[],
                    resolved_id=stable_id if entry.get("status") == "accepted" else None,
                    decided_at=decided_at,
                    evidence_refs=[],
                )

            decision_rows.append(
                {"source_id": source.source_id, "synthetic": effective_synthetic, **decision.as_dict()}
            )

    accepted_rows: List[Dict[str, Any]] = []
    quarantine_rows: List[Dict[str, Any]] = []
    provenance: Dict[str, Any] = {}
    for stable_id in sorted(state.entries):
        entry = state.entries[stable_id]
        conflicted = bool(entry.get("conflicted"))
        status = entry.get("status")
        if status == DecisionOutcome.ACCEPTED.value and not conflicted:
            payload = dict(entry.get("resolved") or {})
            payload["synthetic"] = bool(entry.get("synthetic"))
            payload["source_id"] = entry.get("source_id")
            accepted_rows.append(payload)
            provenance[stable_id] = entry.get("provenance")
        else:
            reason_codes = list(entry.get("reasons") or [])
            if conflicted:
                reason_codes = [
                    entry.get("conflict_reason") or ReasonCode.CONFLICTING_UPDATE
                ] + reason_codes
            quarantine_rows.append(
                {
                    "candidate_id": stable_id,
                    "source_id": entry.get("source_id"),
                    "source_type": entry.get("source_type"),
                    "source_entity_id": entry.get("source_entity_id"),
                    "synthetic": bool(entry.get("synthetic")),
                    "outcome": DecisionOutcome.REQUIRES_REVIEW.value if conflicted else status,
                    "resolution_status": entry.get("resolution_status"),
                    "reason_codes": reason_codes,
                }
            )

    raw_index.sort(key=lambda row: (row["source_id"], row["extraction_metadata"].get("source_entity_id") or ""))
    candidate_rows.sort(key=lambda row: (row["source_id"], row.get("source_entity_id") or ""))
    decision_rows.sort(key=lambda row: row["candidate_id"])
    accepted_rows.sort(key=lambda row: row["id"])
    quarantine_rows.sort(key=lambda row: row["candidate_id"])

    outputs = {
        "raw": out_dir / "raw.jsonl",
        "candidates": out_dir / "candidates.jsonl",
        "decisions": out_dir / "decisions.jsonl",
        "accepted": out_dir / "accepted.jsonl",
        "quarantine": out_dir / "quarantine.jsonl",
        "summary": out_dir / "summary.json",
    }
    atomic_write_jsonl(outputs["raw"], raw_index)
    atomic_write_jsonl(outputs["candidates"], candidate_rows)
    atomic_write_jsonl(outputs["decisions"], decision_rows)
    atomic_write_jsonl(outputs["accepted"], accepted_rows)
    atomic_write_jsonl(outputs["quarantine"], quarantine_rows)

    totals = {
        "candidates": sum(c["candidates"] for c in per_source_counts.values()),
        "accepted": sum(c["accepted"] for c in per_source_counts.values()),
        "rejected": sum(c["rejected"] for c in per_source_counts.values()),
        "duplicate": sum(c["duplicate"] for c in per_source_counts.values()),
        "requires_review": sum(c["requires_review"] for c in per_source_counts.values()),
        "accepted_durable": len(accepted_rows),
        "quarantine_durable": len(quarantine_rows),
    }
    real_totals = {"accepted": 0, "candidates": 0}
    for source, _bytes, _sha, _unused, _cands, effective_synthetic in parsed_sources:
        if effective_synthetic:
            continue
        counts = per_source_counts.get(source.source_id, {})
        real_totals["candidates"] += counts.get("candidates", 0)
        real_totals["accepted"] += counts.get("accepted", 0)

    effective_synthetic_overall = any(
        meta["synthetic"] for meta in source_meta
    ) or bool(manifest.synthetic)

    summary = {
        "pipeline_version": PIPELINE_VERSION,
        "generated_at": decided_at,
        "run_id": run_id,
        "dry_run": bool(dry_run),
        "live_ingestion": False,
        "manifest_path": str(Path(manifest_path)),
        "manifest_sha256": manifest.sha256,
        "mapping_path": str(Path(mapping_path)),
        "policy_hash": policy_hash,
        "dataset": manifest.dataset,
        "scope": scope,
        "synthetic": effective_synthetic_overall,
        "outputs": {name: str(path) for name, path in outputs.items()},
        "sources": source_meta,
        "totals": totals,
        "real_expansion_totals": real_totals,
        "provenance": provenance,
        "limitations": {
            "cross_source_equivalence": "unsupported",
            "network_acquisition": "not_implemented",
        },
    }
    atomic_write_json(outputs["summary"], summary)
    state.save()

    ledger_row = {
        "run_id": run_id,
        "generated_at": decided_at,
        "policy_hash": policy_hash,
        "manifest_sha256": manifest.sha256,
        "synthetic": effective_synthetic_overall,
        "totals": totals,
        "decisions": [
            {
                "candidate_id": row["candidate_id"],
                "outcome": row["outcome"],
                "reason_codes": row["reason_codes"],
                "prior_outcome": row.get("prior_outcome"),
            }
            for row in decision_rows
        ],
    }
    append_jsonl(out_dir / "ledger.jsonl", ledger_row)

    return RunResult(summary=summary, summary_path=outputs["summary"], outputs=outputs)
