"""Explicit, typed source-snapshot area selection.

A source area is *not* a current administrative district. The selector is
derived from the exact tuple ``(dataset_namespace, input_sha256, raw_city,
raw_area)`` so equal display labels from different snapshots or cities cannot
collide. Raw labels are preserved exactly; a missing label yields an explicitly
unassigned source area instead of an invented current name.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional, Tuple

from pydantic import (
    BaseModel,
    ConfigDict,
    ValidationError,
    field_validator,
    model_serializer,
    model_validator,
)

from app.core.domain.graph_entities import SourceMetadata


SOURCE_AREA_SCHEMA = "source_area_scope_v1"
SOURCE_AREA_ID_PREFIX = "source_area_v1:"
SOURCE_AREA_ID_RE = re.compile(r"^source_area_v1:[0-9a-f]{64}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

CURRENT_BOUNDARY_UNCERTAINTY = (
    "Source-snapshot area labels are not a verified mapping to current "
    "administrative boundaries; current city/district status is unverified."
)

SOURCE_AREA_LABEL_UNASSIGNED = "Unassigned source area"

# Multi-area selection is an alternate selector, never an additional one. The
# bound keeps a request/cache key finite and mirrors the AI payload contract.
SOURCE_AREA_IDS_MAX = 64


class SourceScopeError(ValueError):
    """Base class for rejected source-scope input or stored qualification."""


class SourceScopeMismatch(SourceScopeError):
    """The record does not match the explicitly requested source scope."""


class SourceScopeCorruption(SourceScopeError):
    """Stored qualification is missing, inconsistent or copied."""


class SourceSnapshotRef(BaseModel):
    """Identifies one dataset snapshot for source-area discovery."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_namespace: str
    input_sha256: str

    @field_validator("dataset_namespace")
    @classmethod
    def _nonblank_namespace(cls, value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("dataset_namespace must be a nonblank string.")
        return value.strip()

    @field_validator("input_sha256")
    @classmethod
    def _input_hash(cls, value: Any) -> str:
        if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
            raise ValueError(
                "input_sha256 must be a lowercase 64-character SHA256 hex digest."
            )
        return value


class SourceSnapshotSelection(BaseModel):
    """Strict explicit selection; its presence is the only source mode switch.

    Exactly one selector is supplied: the legacy ``source_area_id`` or the
    multi-area ``source_area_ids`` list. Multi ids are canonicalised (sorted)
    for stable equality, but duplicates are rejected rather than silently
    collapsed. Optional selector fields are omitted from ``model_dump`` so a
    one-area selection keeps its legacy three-key byte shape.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    dataset_namespace: str
    input_sha256: str
    source_area_id: Optional[str] = None
    source_area_ids: Optional[List[str]] = None

    @model_validator(mode="before")
    @classmethod
    def _exactly_one_selector(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        has_single = "source_area_id" in data
        has_multi = "source_area_ids" in data
        if has_single == has_multi:
            raise ValueError(
                "exactly one of source_area_id or source_area_ids is required."
            )
        key = "source_area_id" if has_single else "source_area_ids"
        if data.get(key) is None:
            raise ValueError(f"{key} must not be null.")
        return data

    @field_validator("dataset_namespace")
    @classmethod
    def _nonblank_namespace(cls, value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("dataset_namespace must be a nonblank string.")
        if value != value.strip():
            raise ValueError(
                "dataset_namespace must not have leading/trailing whitespace."
            )
        return value

    @field_validator("input_sha256")
    @classmethod
    def _input_hash(cls, value: Any) -> str:
        if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
            raise ValueError(
                "input_sha256 must be a lowercase 64-character SHA256 hex digest."
            )
        return value

    @field_validator("source_area_id")
    @classmethod
    def _area_id(cls, value: Any) -> str:
        if not isinstance(value, str) or not SOURCE_AREA_ID_RE.fullmatch(value):
            raise ValueError(
                "source_area_id must use the source_area_v1:<64 lowercase hex> "
                "form; current administrative ids are not source selectors."
            )
        return value

    @field_validator("source_area_ids")
    @classmethod
    def _area_ids(cls, value: Any) -> List[str]:
        if not isinstance(value, list):
            raise ValueError("source_area_ids must be a list of source area ids.")
        if not (1 <= len(value) <= SOURCE_AREA_IDS_MAX):
            raise ValueError(
                f"source_area_ids must contain 1..{SOURCE_AREA_IDS_MAX} ids."
            )
        for item in value:
            if not isinstance(item, str) or not SOURCE_AREA_ID_RE.fullmatch(item):
                raise ValueError(
                    "every source_area_ids entry must use the "
                    "source_area_v1:<64 lowercase hex> form."
                )
        if len(set(value)) != len(value):
            raise ValueError("source_area_ids must not contain duplicates.")
        return sorted(value)

    @model_serializer(mode="wrap")
    def _omit_unused_selector(self, handler: Any) -> Any:
        """Drop the unused selector on every serialisation path.

        A ``model_dump`` method override only ran for a direct call; Pydantic
        nested serialisation (for example a request wrapper) bypassed it and
        emitted the unset selector as ``null``. A wrap serializer runs for
        direct, nested, Python and JSON dumps alike, while leaving the caller's
        ``include``/``exclude``/``by_alias`` semantics intact.
        """
        data = handler(self)
        if not isinstance(data, dict):
            return data
        unused = ("source_area_ids" if self.source_area_id is not None
                  else "source_area_id")
        data.pop(unused, None)
        return data

    @property
    def area_ids(self) -> Tuple[str, ...]:
        """The selected concrete ids, never a global sentinel."""
        if self.source_area_ids is not None:
            return tuple(self.source_area_ids)
        return (self.source_area_id,) if self.source_area_id else ()


class SourceContext(BaseModel):
    """Compact, model-facing source evidence.

    This is deliberately distinct from ``AdministrativeContext``: it carries no
    current City/District ids and no raw lineage blob. The lineage reference is a
    stable pointer to the server-side audit representation.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_namespace: str
    input_sha256: str
    source_area_id: str
    raw_city: Optional[str] = None
    raw_area: Optional[str] = None
    source_area_label: str
    area_assignment: Literal["qualified", "unassigned"]
    current_admin_status: Literal["unverified_source_area"] = (
        "unverified_source_area"
    )
    current_boundary_uncertainty: str = CURRENT_BOUNDARY_UNCERTAINTY
    lineage_reference: str
    qualification: Literal["exact_source_snapshot_tuple"] = (
        "exact_source_snapshot_tuple"
    )


@dataclass(frozen=True)
class SourceAreaIdentity:
    dataset_namespace: str
    input_sha256: str
    source_area_id: str
    raw_city: Optional[str]
    raw_area: Optional[str]

    @property
    def area_assignment(self) -> Literal["qualified", "unassigned"]:
        return "qualified" if (self.raw_city and self.raw_area) else "unassigned"

    @property
    def source_area_label(self) -> str:
        if self.raw_city and self.raw_area:
            return f"{self.raw_area}, {self.raw_city}"
        if self.raw_area:
            return self.raw_area
        if self.raw_city:
            return self.raw_city
        return SOURCE_AREA_LABEL_UNASSIGNED


def canonical_source_area_json(
    dataset_namespace: str,
    input_sha256: str,
    raw_city: Optional[str],
    raw_area: Optional[str],
) -> str:
    """Documented canonical material hashed into ``source_area_id``."""
    material = {
        "dataset_namespace": dataset_namespace,
        "input_sha256": input_sha256,
        "raw_area": raw_area,
        "raw_city": raw_city,
        "schema": SOURCE_AREA_SCHEMA,
    }
    return json.dumps(
        material, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def derive_source_area_id(
    dataset_namespace: str,
    input_sha256: str,
    raw_city: Optional[str],
    raw_area: Optional[str],
) -> str:
    material = canonical_source_area_json(
        dataset_namespace, input_sha256, raw_city, raw_area
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return f"{SOURCE_AREA_ID_PREFIX}{digest}"


def _raw_label(address: Dict[str, Any], key: str) -> Optional[str]:
    if key not in address:
        return None
    value = address.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise SourceScopeCorruption(
            f"stored source address {key} is not a string or null."
        )
    if not value.strip():
        return None
    return value


def read_raw_source_labels(
    metadata: SourceMetadata,
) -> Tuple[Optional[str], Optional[str]]:
    """Return the exact stored raw city/area labels, or ``None`` when absent."""
    row = metadata.parsed_lineage()
    address = row.get("address")
    if not isinstance(address, dict):
        raise SourceScopeCorruption("stored source lineage has no address object.")
    return _raw_label(address, "raw_city"), _raw_label(address, "raw_district")


def derive_source_area(metadata: SourceMetadata) -> SourceAreaIdentity:
    raw_city, raw_area = read_raw_source_labels(metadata)
    source_area_id = derive_source_area_id(
        metadata.dataset_namespace,
        metadata.input_sha256,
        raw_city,
        raw_area,
    )
    return SourceAreaIdentity(
        dataset_namespace=metadata.dataset_namespace,
        input_sha256=metadata.input_sha256,
        source_area_id=source_area_id,
        raw_city=raw_city,
        raw_area=raw_area,
    )


def _validate_cached_selector(
    identity: SourceAreaIdentity,
    cached_area_id: Any,
    cached_namespace: Any,
    cached_snapshot: Any,
) -> None:
    cached = (cached_area_id, cached_namespace, cached_snapshot)
    if all(value is None for value in cached):
        return
    if any(value is None for value in cached):
        raise SourceScopeCorruption(
            "stored source selector is incomplete; it cannot be trusted."
        )
    if (
        cached_namespace != identity.dataset_namespace
        or cached_snapshot != identity.input_sha256
        or cached_area_id != identity.source_area_id
    ):
        raise SourceScopeCorruption(
            "stored source selector contradicts the validated source lineage."
        )


def qualify_source_record(
    poi_id: str,
    metadata: SourceMetadata,
    selection: SourceSnapshotSelection,
    *,
    cached_area_id: Any = None,
    cached_namespace: Any = None,
    cached_snapshot: Any = None,
) -> SourceAreaIdentity:
    """Fail-closed qualification of an actual stored record.

    Raises ``SourceScopeCorruption`` for copied/inconsistent evidence and
    ``SourceScopeMismatch`` when the record is valid but belongs to another
    source snapshot/area.
    """
    if not isinstance(poi_id, str) or not poi_id.strip():
        raise SourceScopeCorruption("record has no usable POI id.")
    try:
        metadata.assert_bound_to_poi(poi_id)
    except ValueError as exc:
        raise SourceScopeCorruption(str(exc)) from exc

    try:
        identity = derive_source_area(metadata)
    except SourceScopeError:
        raise
    except ValueError as exc:
        raise SourceScopeCorruption(str(exc)) from exc

    _validate_cached_selector(
        identity, cached_area_id, cached_namespace, cached_snapshot
    )

    if (
        identity.dataset_namespace != selection.dataset_namespace
        or identity.input_sha256 != selection.input_sha256
        or identity.source_area_id not in set(selection.area_ids)
    ):
        raise SourceScopeMismatch(
            "record does not match the explicitly selected source snapshot/area."
        )
    return identity


def build_source_context(
    identity: SourceAreaIdentity, metadata: SourceMetadata
) -> SourceContext:
    return SourceContext(
        dataset_namespace=identity.dataset_namespace,
        input_sha256=identity.input_sha256,
        source_area_id=identity.source_area_id,
        raw_city=identity.raw_city,
        raw_area=identity.raw_area,
        source_area_label=identity.source_area_label,
        area_assignment=identity.area_assignment,
        lineage_reference=(
            "graph:POI.source_metadata_json#"
            f"{metadata.raw_lineage_sha256}"
        ),
    )


def parse_source_snapshot_selection(value: Any) -> SourceSnapshotSelection:
    if isinstance(value, SourceSnapshotSelection):
        return value
    if isinstance(value, dict):
        try:
            return SourceSnapshotSelection.model_validate(value)
        except ValidationError as exc:
            raise SourceScopeError(
                "source_scope is not a valid typed source selection."
            ) from exc
    raise SourceScopeError("source_scope must be a typed selection object.")


def parse_source_snapshot_ref(value: Any) -> SourceSnapshotRef:
    if isinstance(value, SourceSnapshotRef):
        return value
    if isinstance(value, dict):
        try:
            return SourceSnapshotRef.model_validate(value)
        except ValidationError as exc:
            raise SourceScopeError(
                "source_snapshot is not a valid typed snapshot reference."
            ) from exc
    raise SourceScopeError("source_snapshot must be a typed snapshot object.")
