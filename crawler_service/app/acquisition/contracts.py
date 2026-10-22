"""Stdlib-only typed contracts for the acquisition pipeline.

These mirror the four contracts in ``docs/architecture/DATA_CONTRACTS.md``:
``RawSourceRecord``, ``POICandidate``, ``ResolvedPOI`` and
``IngestionDecision``. Only the standard library is used so the package can be
imported with the validation interpreter without third-party dependencies.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class CollectionStatus(str, Enum):
    OBTAINED = "obtained"
    REJECTED = "rejected"


class GeometryKind(str, Enum):
    POINT = "point"
    CENTER = "center"
    AREA = "area"
    UNKNOWN = "unknown"


class ResolutionStatus(str, Enum):
    EXACT = "exact"
    PROBABLE = "probable"
    AMBIGUOUS = "ambiguous"
    UNRESOLVED = "unresolved"


class DecisionOutcome(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DUPLICATE = "duplicate"
    REQUIRES_REVIEW = "requires_review"


class ReasonCode:
    """Closed set of machine-readable decision/uncertainty reason codes."""

    MISSING_SOURCE_IDENTITY = "missing_source_identity"
    INVALID_SOURCE_IDENTITY = "invalid_source_identity"
    UNSUPPORTED_SOURCE_TYPE = "unsupported_source_type"
    UNSUPPORTED_PAYLOAD = "unsupported_payload"
    FAILED_COLLECTION = "failed_collection"
    MISSING_NAME = "missing_name"
    MISSING_ADDRESS = "missing_address"
    MISSING_DESCRIPTION = "missing_description"
    POLICY_UNVERIFIED = "policy_unverified"
    MISSING_COORDINATES = "missing_coordinates"
    INVALID_COORDINATES = "invalid_coordinates"
    NO_LIVE_COORDINATES = "no_live_coordinates"
    AMBIGUOUS_COORDINATES = "ambiguous_coordinates"
    UNKNOWN_CATEGORY = "unknown_category"
    UNKNOWN_ADMIN = "unknown_admin"
    ENTITY_UNREVIEWED = "entity_unreviewed"
    UNREVIEWED_SOURCE = "unreviewed_source"
    ADMIN_CONFLICT = "admin_conflict"
    AREA_GEOMETRY_REVIEW = "area_geometry_review"
    CENTER_COORDINATE_REVIEW = "center_coordinate_review"
    CONFLICTING_UPDATE = "conflicting_update"
    POLICY_RE_EVALUATED = "policy_re_evaluated"
    SYNTHETIC_REAL_COLLISION = "synthetic_real_collision"


class InfoCode:
    """Informational notes that never block acceptance on their own."""

    DEPRECATED_COORDINATE_IGNORED = "deprecated_coordinate_ignored"
    NON_EARTH_GLOBE_IGNORED = "non_earth_globe_ignored"


def is_number(value: Any) -> bool:
    """True only for real finite/infinite numbers; ``bool`` is not numeric."""

    return isinstance(value, (int, float)) and not isinstance(value, bool)


def is_finite_in_range(value: Any, low: float, high: float) -> bool:
    """Finite numeric check that also rejects ``bool`` and non-numbers."""

    return is_number(value) and math.isfinite(value) and low <= value <= high


def parse_utc(value: Any) -> datetime:
    """Parse an ISO-8601 timestamp and require an explicit UTC offset.

    Raises ``ValueError`` for missing, naive or unparseable values so callers
    can surface a configuration error without writing partial output.
    """

    if not isinstance(value, str) or not value.strip():
        raise ValueError("retrieved_at must be a non-empty ISO-8601 string")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware (UTC)")
    return parsed


def to_utc_iso(value: datetime) -> str:
    """Render a datetime as an explicit UTC ISO-8601 string with ``Z``."""

    from datetime import timezone

    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class RawSourceRecord:
    """Immutable reference to the exact saved source bytes for one element."""

    source_type: str
    source_id: str
    source_url: str
    retrieved_at: str
    license: str
    raw_content_reference: str
    sha256: str
    collection_status: str
    extraction_metadata: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "source_type": self.source_type,
            "source_id": self.source_id,
            "source_url": self.source_url,
            "retrieved_at": self.retrieved_at,
            "license": self.license,
            "raw_content_reference": self.raw_content_reference,
            "sha256": self.sha256,
            "collection_status": self.collection_status,
            "extraction_metadata": dict(self.extraction_metadata),
        }


@dataclass
class POICandidate:
    """A single source-derived candidate with original field evidence."""

    source_type: str
    source_entity_id: str
    geometry_kind: str
    name: Optional[str]
    aliases: List[str]
    coordinates: Optional[Tuple[Any, Any]]
    address_hints: Dict[str, str]
    category_tags: List[str]
    opening_hours_raw: Optional[str]
    raw_content_reference: str
    raw_sha256: str
    source_url: str
    license: str
    retrieved_at: str
    field_paths: Dict[str, str] = field(default_factory=dict)
    uncertainty_codes: List[str] = field(default_factory=list)
    info_codes: List[str] = field(default_factory=list)
    source_revision: Optional[str] = None
    # Additive web-source evidence. These never participate in the stable id or
    # the fact fingerprint; the acquisition mapping/quality gate is unchanged.
    description: Optional[str] = None
    review_text: Optional[str] = None
    field_evidence: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def source_identity(self) -> Optional[str]:
        if self.source_type and self.source_entity_id:
            return f"{self.source_type}/{self.source_entity_id}"
        return None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "source_type": self.source_type,
            "source_entity_id": self.source_entity_id,
            "geometry_kind": self.geometry_kind,
            "name": self.name,
            "aliases": list(self.aliases),
            "coordinates": list(self.coordinates) if self.coordinates else None,
            "address_hints": dict(self.address_hints),
            "category_tags": list(self.category_tags),
            "opening_hours_raw": self.opening_hours_raw,
            "raw_content_reference": self.raw_content_reference,
            "raw_sha256": self.raw_sha256,
            "source_url": self.source_url,
            "license": self.license,
            "retrieved_at": self.retrieved_at,
            "source_revision": self.source_revision,
            "field_paths": dict(self.field_paths),
            "uncertainty_codes": list(self.uncertainty_codes),
            "info_codes": list(self.info_codes),
            "description": self.description,
            "review_text": self.review_text,
            "field_evidence": [dict(item) for item in self.field_evidence],
        }


@dataclass
class ResolvedPOI:
    """A candidate mapped to the closed category catalog and reviewed admin."""

    stable_id: str
    canonical_name: str
    latitude: float
    longitude: float
    city: str
    district: str
    nation: str
    category_ids: List[str]
    categories: List[Dict[str, str]]
    resolution_status: str
    geometry_kind: str
    provenance: Dict[str, Any] = field(default_factory=dict)
    operation_time: Optional[str] = None

    def as_payload(self) -> Dict[str, Any]:
        """Return a payload compatible with the POI domain model.

        ``poi_categories`` carries full ``id``/``name``/``context`` objects from
        the closed catalog. ``operation_time``, when present, is the original
        source text only; provenance records that it is unparsed.
        """

        payload: Dict[str, Any] = {
            "id": self.stable_id,
            "name": self.canonical_name,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "address": {
                "city": self.city,
                "district": self.district,
                "nation": self.nation,
            },
            "poi_categories": [dict(category) for category in self.categories],
        }
        if self.operation_time:
            payload["operation_time"] = self.operation_time
        return payload

    def as_dict(self) -> Dict[str, Any]:
        return {
            "stable_id": self.stable_id,
            "canonical_name": self.canonical_name,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "city": self.city,
            "district": self.district,
            "nation": self.nation,
            "category_ids": list(self.category_ids),
            "categories": [dict(category) for category in self.categories],
            "resolution_status": self.resolution_status,
            "geometry_kind": self.geometry_kind,
            "operation_time": self.operation_time,
            "provenance": dict(self.provenance),
        }


@dataclass
class IngestionDecision:
    """The deterministic outcome for one candidate on one run."""

    candidate_id: str
    outcome: str
    reason_codes: List[str]
    resolved_id: Optional[str]
    decided_at: str
    evidence_references: List[str] = field(default_factory=list)
    prior_outcome: Optional[str] = None
    info_codes: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "outcome": self.outcome,
            "reason_codes": list(self.reason_codes),
            "resolved_id": self.resolved_id,
            "decided_at": self.decided_at,
            "evidence_references": list(self.evidence_references),
            "prior_outcome": self.prior_outcome,
            "info_codes": list(self.info_codes),
        }
