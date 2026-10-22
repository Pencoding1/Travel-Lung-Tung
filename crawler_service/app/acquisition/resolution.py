"""Reviewed mapping manifest loading, validation and resolution policy.

Administrative acceptance is per **source entity**, never per export file. The
mapping manifest must whitelist each reviewed entity with its own reviewer,
evidence reference and city/district (and nation). File-level category mapping
may remain, but a file-level default district alone is never sufficient.
Category and administrative decisions are recorded in fact provenance with the
mapping-manifest SHA-256 and JSON Pointers into the manifest.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .contracts import (
    GeometryKind,
    POICandidate,
    ReasonCode,
    ResolutionStatus,
    ResolvedPOI,
    is_finite_in_range,
)
from .identity import sha256_bytes, stable_source_id
from .jsonptr import build_pointer


class ConfigError(ValueError):
    """Raised when a manifest or mapping manifest is invalid."""


_UNSUPPORTED_MANIFEST_KEYS = ("equivalence", "equivalences", "merge", "merges")


def _reject_duplicate_keys(pairs):
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise ConfigError(f"duplicate key in JSON object: {key!r}")
        seen[key] = value
    return seen


def _load_document_with_bytes(path: Path) -> tuple[Dict[str, Any], bytes]:
    try:
        payload = Path(path).read_bytes()
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    try:
        data = json.loads(payload.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except UnicodeDecodeError as exc:
        raise ConfigError(f"{path} is not valid UTF-8: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain a JSON object")
    return data, payload


def load_json_object(path: Path) -> Dict[str, Any]:
    return _load_document_with_bytes(Path(path))[0]


def _require_bool(value: Any, label: str, *, default: bool = False) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ConfigError(f"{label} must be a boolean, got {type(value).__name__}")
    return value


def _require_nonblank_str(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{label} must be a non-empty string")
    return value.strip()


@dataclass(frozen=True)
class CategoryDefinition:
    id: str
    name: str
    context: str


@dataclass
class EntityReview:
    key: str
    reviewer: str
    evidence_reference: str
    city: str
    district: str
    nation: str


@dataclass
class SourceReview:
    source_id: str
    synthetic: bool = False
    districts: Dict[str, str] = field(default_factory=dict)
    category_map: Dict[str, str] = field(default_factory=dict)
    entities: Dict[str, EntityReview] = field(default_factory=dict)

    def lookup_entity(self, source_type: str, entity_id: str) -> Optional[EntityReview]:
        for key in (f"{source_type}/{entity_id}", entity_id):
            review = self.entities.get(key)
            if review is not None:
                return review
        return None


@dataclass
class MappingManifest:
    categories: Dict[str, CategoryDefinition]
    category_order: List[str]
    sources: Dict[str, SourceReview]
    sha256: str

    def catalog_payload(self, category_id: str) -> Optional[Dict[str, str]]:
        category = self.categories.get(category_id)
        if category is None:
            return None
        return {"id": category.id, "name": category.name, "context": category.context}

    def catalog_pointer(self, category_id: str) -> Optional[str]:
        try:
            index = self.category_order.index(category_id)
        except ValueError:
            return None
        return build_pointer("categories", index)


def load_mapping_manifest(path: Path) -> MappingManifest:
    document, payload = _load_document_with_bytes(Path(path))

    for unsupported in _UNSUPPORTED_MANIFEST_KEYS:
        if unsupported in document:
            raise ConfigError(
                f"manifest key {unsupported!r} is unsupported: cross-source "
                "equivalence/merge is not implemented"
            )

    raw_categories = document.get("categories")
    if not isinstance(raw_categories, list) or not raw_categories:
        raise ConfigError("mapping manifest requires a non-empty 'categories' list")
    categories: Dict[str, CategoryDefinition] = {}
    category_order: List[str] = []
    for index, entry in enumerate(raw_categories):
        if not isinstance(entry, dict):
            raise ConfigError(f"categories[{index}] must be an object")
        cid = _require_nonblank_str(entry.get("id"), f"categories[{index}].id")
        name = _require_nonblank_str(entry.get("name"), f"categories[{index}].name")
        context = _require_nonblank_str(
            entry.get("context"), f"categories[{index}].context"
        )
        definition = CategoryDefinition(cid, name, context)
        existing = categories.get(definition.id)
        if existing is not None and existing != definition:
            raise ConfigError(
                f"conflicting definitions for category id {definition.id!r}"
            )
        if existing is None:
            category_order.append(definition.id)
        categories[definition.id] = definition

    raw_sources = document.get("sources")
    if not isinstance(raw_sources, dict) or not raw_sources:
        raise ConfigError("mapping manifest requires a non-empty 'sources' object")

    sources: Dict[str, SourceReview] = {}
    for source_id, entry in raw_sources.items():
        if not isinstance(entry, dict):
            raise ConfigError(f"sources[{source_id!r}] must be an object")
        synthetic = _require_bool(
            entry.get("synthetic"), f"sources[{source_id!r}].synthetic"
        )

        raw_map = entry.get("category_map") or {}
        if not isinstance(raw_map, dict):
            raise ConfigError(f"sources[{source_id!r}].category_map must be an object")
        category_map: Dict[str, str] = {}
        for tag, category_id in raw_map.items():
            if not isinstance(category_id, str) or category_id not in categories:
                raise ConfigError(
                    f"sources[{source_id!r}] maps {tag!r} to unknown category "
                    f"{category_id!r}"
                )
            category_map[tag] = category_id

        raw_districts = entry.get("districts") or {}
        if not isinstance(raw_districts, dict):
            raise ConfigError(f"sources[{source_id!r}].districts must be an object")
        districts: Dict[str, str] = {}
        for raw_value, canonical in raw_districts.items():
            districts[raw_value] = _require_nonblank_str(
                canonical, f"sources[{source_id!r}].districts[{raw_value!r}]"
            )

        raw_entities = entry.get("entities") or {}
        if not isinstance(raw_entities, dict):
            raise ConfigError(f"sources[{source_id!r}].entities must be an object")
        entities: Dict[str, EntityReview] = {}
        for entity_key, entity_entry in raw_entities.items():
            if not isinstance(entity_key, str) or not entity_key.strip():
                raise ConfigError(f"sources[{source_id!r}].entities keys must be strings")
            if not isinstance(entity_entry, dict):
                raise ConfigError(
                    f"sources[{source_id!r}].entities[{entity_key!r}] must be an object"
                )
            reviewer = _require_nonblank_str(
                entity_entry.get("reviewer"),
                f"sources[{source_id!r}].entities[{entity_key!r}].reviewer",
            )
            evidence = _require_nonblank_str(
                entity_entry.get("evidence_reference"),
                f"sources[{source_id!r}].entities[{entity_key!r}].evidence_reference",
            )
            city = _require_nonblank_str(
                entity_entry.get("city"),
                f"sources[{source_id!r}].entities[{entity_key!r}].city",
            )
            district = _require_nonblank_str(
                entity_entry.get("district"),
                f"sources[{source_id!r}].entities[{entity_key!r}].district",
            )
            nation = entity_entry.get("nation") or "Vietnam"
            nation = _require_nonblank_str(
                nation, f"sources[{source_id!r}].entities[{entity_key!r}].nation"
            )
            entities[entity_key] = EntityReview(
                key=entity_key,
                reviewer=reviewer,
                evidence_reference=evidence,
                city=city,
                district=district,
                nation=nation,
            )

        sources[source_id] = SourceReview(
            source_id=source_id,
            synthetic=synthetic,
            districts=districts,
            category_map=category_map,
            entities=entities,
        )

    return MappingManifest(
        categories=categories,
        category_order=category_order,
        sources=sources,
        sha256=sha256_bytes(payload),
    )


@dataclass
class Resolution:
    resolved: Optional[ResolvedPOI]
    resolution_status: str
    reasons: List[str]
    evidence_references: List[str]
    info_codes: List[str]


def _normalize(value: str) -> str:
    return " ".join(value.split()).casefold()


def _admin_conflicts(
    candidate: POICandidate, source_review: SourceReview, entity: EntityReview
) -> bool:
    hints = candidate.address_hints
    hint_city = hints.get("addr:city") or hints.get("addr:province")
    if hint_city and _normalize(hint_city) != _normalize(entity.city):
        return True
    raw_district = hints.get("addr:district") or hints.get("addr:suburb")
    if raw_district:
        canonical = source_review.districts.get(raw_district)
        if canonical is None or _normalize(canonical) != _normalize(entity.district):
            return True
    return False


def resolve_candidate(
    candidate: POICandidate,
    source_review: Optional[SourceReview],
    manifest: MappingManifest,
) -> Resolution:
    """Resolve a candidate and record administative/category provenance."""

    info_codes = list(candidate.info_codes)
    reasons: List[str] = [
        code
        for code in candidate.uncertainty_codes
        if code
        not in (
            ReasonCode.MISSING_NAME,
            ReasonCode.MISSING_COORDINATES,
            ReasonCode.UNKNOWN_CATEGORY,
            ReasonCode.UNKNOWN_ADMIN,
            ReasonCode.ENTITY_UNREVIEWED,
            ReasonCode.UNREVIEWED_SOURCE,
            ReasonCode.ADMIN_CONFLICT,
        )
    ]

    if not candidate.source_entity_id:
        identity_reason = (
            ReasonCode.INVALID_SOURCE_IDENTITY
            if ReasonCode.INVALID_SOURCE_IDENTITY in candidate.uncertainty_codes
            else ReasonCode.MISSING_SOURCE_IDENTITY
        )
        return Resolution(
            None, ResolutionStatus.UNRESOLVED.value, [identity_reason], [], info_codes
        )

    evidence_refs: List[str] = []

    if source_review is None:
        reasons.append(ReasonCode.UNREVIEWED_SOURCE)
    entity = (
        source_review.lookup_entity(candidate.source_type, candidate.source_entity_id)
        if source_review is not None
        else None
    )
    if entity is None:
        reasons.append(ReasonCode.ENTITY_UNREVIEWED)

    category_ids: List[str] = []
    category_provenance: List[Dict[str, str]] = []
    if source_review is not None:
        for tag in candidate.category_tags:
            category_id = source_review.category_map.get(tag)
            if category_id and category_id not in category_ids:
                category_ids.append(category_id)
                category_provenance.append(
                    {
                        "tag": tag,
                        "category_id": category_id,
                        "map_pointer": build_pointer(
                            "sources", source_review.source_id, "category_map", tag
                        ),
                        "catalog_pointer": manifest.catalog_pointer(category_id) or "",
                    }
                )
    if not category_ids:
        reasons.append(ReasonCode.UNKNOWN_CATEGORY)

    city = entity.city if entity else None
    district = entity.district if entity else None
    nation = entity.nation if entity else "Vietnam"
    if entity is None:
        reasons.append(ReasonCode.UNKNOWN_ADMIN)
    elif source_review is not None and _admin_conflicts(candidate, source_review, entity):
        reasons.append(ReasonCode.ADMIN_CONFLICT)
    if entity is not None:
        evidence_refs.append(entity.evidence_reference)

    if candidate.name is None or not candidate.name.strip():
        reasons.append(ReasonCode.MISSING_NAME)

    lat, lon = (None, None)
    invalid_coordinates = False
    if candidate.coordinates is None:
        reasons.append(ReasonCode.MISSING_COORDINATES)
    else:
        lat, lon = candidate.coordinates
        if not is_finite_in_range(lat, -90.0, 90.0) or not is_finite_in_range(
            lon, -180.0, 180.0
        ):
            reasons.append(ReasonCode.INVALID_COORDINATES)
            invalid_coordinates = True

    if candidate.geometry_kind == GeometryKind.AREA.value:
        reasons.append(ReasonCode.AREA_GEOMETRY_REVIEW)
    elif candidate.geometry_kind == GeometryKind.CENTER.value:
        reasons.append(ReasonCode.CENTER_COORDINATE_REVIEW)

    if invalid_coordinates:
        return Resolution(
            None,
            ResolutionStatus.UNRESOLVED.value,
            _dedupe(reasons),
            evidence_refs,
            info_codes,
        )

    if reasons:
        return Resolution(
            None,
            ResolutionStatus.AMBIGUOUS.value,
            _dedupe(reasons),
            evidence_refs,
            info_codes,
        )

    categories = [manifest.catalog_payload(cid) for cid in category_ids]
    admin_pointer = build_pointer(
        "sources", source_review.source_id, "entities", entity.key
    )
    provenance: Dict[str, Any] = {
        "source_type": candidate.source_type,
        "source_entity_id": candidate.source_entity_id,
        "source_url": candidate.source_url,
        "license": candidate.license,
        "retrieved_at": candidate.retrieved_at,
        "source_revision": candidate.source_revision,
        "raw_content_reference": candidate.raw_content_reference,
        "raw_sha256": candidate.raw_sha256,
        "field_paths": dict(candidate.field_paths),
        "info_codes": info_codes,
        "mapping": {
            "manifest_sha256": manifest.sha256,
            "admin": {
                "pointer": admin_pointer,
                "city": city,
                "district": district,
                "nation": nation,
                "reviewer": entity.reviewer,
                "evidence_reference": entity.evidence_reference,
            },
            "categories": category_provenance,
        },
    }
    if candidate.opening_hours_raw is not None:
        provenance["operation_time"] = {
            "value": candidate.opening_hours_raw,
            "parse_status": "unparsed_source_text",
            "pointer": candidate.field_paths.get("opening_hours"),
        }

    resolved = ResolvedPOI(
        stable_id=stable_source_id(candidate.source_type, candidate.source_entity_id),
        canonical_name=candidate.name.strip(),
        latitude=float(lat),
        longitude=float(lon),
        city=city,
        district=district,
        nation=nation,
        category_ids=category_ids,
        categories=[dict(cat) for cat in categories],
        resolution_status=ResolutionStatus.EXACT.value,
        geometry_kind=candidate.geometry_kind,
        provenance=provenance,
        operation_time=candidate.opening_hours_raw,
    )
    return Resolution(
        resolved,
        ResolutionStatus.EXACT.value,
        _dedupe(reasons),
        evidence_refs,
        info_codes,
    )


def _dedupe(values: List[str]) -> List[str]:
    seen: List[str] = []
    for value in values:
        if value not in seen:
            seen.append(value)
    return seen
