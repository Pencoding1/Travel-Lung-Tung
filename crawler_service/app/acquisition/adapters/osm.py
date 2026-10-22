"""OpenStreetMap JSON adapter (Overpass ``elements`` shape).

Real-format support: a document with a top-level ``elements`` array (Overpass
API JSON), a single element object, or a bare list of elements. Element
identity always carries the OSM primitive (``node``/``way``/``relation``) and a
positive integer id. JSON Pointers address the actual parsed document and keep
the original element indices even when non-object entries are skipped.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ..contracts import GeometryKind, POICandidate, ReasonCode
from ..jsonptr import build_pointer
from .base import SourceAdapter, SourceFormatError

_CATEGORY_KEYS = (
    "amenity", "tourism", "shop", "leisure", "historic", "healthcare", "office", "craft",
)
_NAME_KEYS = ("name", "name:vi", "name:en")
_ADDRESS_KEYS = (
    "addr:city", "addr:district", "addr:suburb", "addr:street", "addr:housenumber", "addr:province",
)


def _element_entries(payload: Any) -> Tuple[Tuple[Any, ...], bool, List[Tuple[int, Any]]]:
    """Return (prefix_tokens, single, entries) where entries keep indices."""

    if isinstance(payload, dict):
        if "error" in payload:
            raise SourceFormatError("OSM payload reports a collection error")
        elements = payload.get("elements")
        if isinstance(elements, list):
            return ("elements",), False, list(enumerate(elements))
        if "type" in payload and "id" in payload:
            return (), True, [(0, payload)]
        raise SourceFormatError("unrecognized OSM payload shape")
    if isinstance(payload, list):
        return (), False, list(enumerate(payload))
    raise SourceFormatError(f"unsupported OSM payload type: {type(payload).__name__}")


def _valid_identity(primitive: Any, raw_id: Any) -> bool:
    return (
        primitive in ("node", "way", "relation")
        and isinstance(raw_id, int)
        and not isinstance(raw_id, bool)
        and raw_id > 0
    )


class OSMAdapter(SourceAdapter):
    source_type = "osm"

    def parse(
        self,
        payload: Any,
        *,
        source_id: str,
        source_url: str,
        license: str,
        retrieved_at: str,
        raw_content_reference: str,
        raw_sha256: str,
    ) -> List[POICandidate]:
        prefix_tokens, single, entries = _element_entries(payload)
        candidates: List[POICandidate] = []
        for index, element in entries:
            base_tokens: Tuple[Any, ...] = () if single else prefix_tokens + (index,)
            candidates.append(
                self._parse_element(
                    element if isinstance(element, dict) else {},
                    base_tokens=base_tokens,
                    source_url=source_url,
                    license=license,
                    retrieved_at=retrieved_at,
                    raw_content_reference=raw_content_reference,
                    raw_sha256=raw_sha256,
                )
            )
        return candidates

    def _parse_element(
        self,
        element: Dict[str, Any],
        *,
        base_tokens: Tuple[Any, ...],
        source_url: str,
        license: str,
        retrieved_at: str,
        raw_content_reference: str,
        raw_sha256: str,
    ) -> POICandidate:
        primitive = element.get("type")
        raw_id = element.get("id")
        identity_reasons: List[str] = []

        if _valid_identity(primitive, raw_id):
            source_entity_id = f"{primitive}/{raw_id}"
        else:
            source_entity_id = ""
            if primitive is None and raw_id is None:
                identity_reasons.append(ReasonCode.MISSING_SOURCE_IDENTITY)
            else:
                identity_reasons.append(ReasonCode.INVALID_SOURCE_IDENTITY)

        tags = element.get("tags") if isinstance(element.get("tags"), dict) else {}

        field_paths: Dict[str, str] = {
            "identity": build_pointer(*base_tokens, "id"),
            "tags": build_pointer(*base_tokens, "tags"),
        }

        geometry, coordinates, coord_paths = self._geometry(element, primitive, base_tokens)
        field_paths.update(coord_paths)
        if geometry != GeometryKind.POINT.value:
            field_paths["geometry"] = build_pointer(*base_tokens, "geometry")

        name = self.first_nonblank(*[tags.get(k) for k in _NAME_KEYS])
        if name is not None:
            for key in _NAME_KEYS:
                if isinstance(tags.get(key), str) and tags[key].strip() == name:
                    field_paths["name"] = build_pointer(*base_tokens, "tags", key)
                    break

        aliases: List[str] = []
        for key in ("alt_name", "official_name", "name:en", "name:vi"):
            value = tags.get(key)
            if isinstance(value, str) and value.strip() and value.strip() != name:
                aliases.append(value.strip())

        address_hints: Dict[str, str] = {}
        for key in _ADDRESS_KEYS:
            value = tags.get(key)
            if isinstance(value, str) and value.strip():
                address_hints[key] = value.strip()

        category_tags: List[str] = []
        for key in _CATEGORY_KEYS:
            value = tags.get(key)
            if isinstance(value, str) and value.strip():
                category_tags.append(f"{key}={value.strip()}")
                field_paths.setdefault("category", build_pointer(*base_tokens, "tags", key))

        opening_hours = tags.get("opening_hours")
        opening_hours_raw = (
            opening_hours.strip() if isinstance(opening_hours, str) and opening_hours.strip() else None
        )
        if opening_hours_raw is not None:
            field_paths["opening_hours"] = build_pointer(*base_tokens, "tags", "opening_hours")

        revision = element.get("version")
        source_revision = (
            str(revision)
            if isinstance(revision, int) and not isinstance(revision, bool)
            else (element.get("timestamp") if isinstance(element.get("timestamp"), str) else None)
        )

        return POICandidate(
            source_type=self.source_type,
            source_entity_id=source_entity_id,
            geometry_kind=geometry,
            name=name,
            aliases=aliases,
            coordinates=coordinates,
            address_hints=address_hints,
            category_tags=category_tags,
            opening_hours_raw=opening_hours_raw,
            raw_content_reference=raw_content_reference,
            raw_sha256=raw_sha256,
            source_url=source_url,
            license=license,
            retrieved_at=retrieved_at,
            field_paths=field_paths,
            uncertainty_codes=identity_reasons,
            source_revision=source_revision,
        )

    @staticmethod
    def _geometry(
        element: Dict[str, Any], primitive: Any, base_tokens: Tuple[Any, ...]
    ) -> Tuple[str, Optional[Tuple[Any, Any]], Dict[str, str]]:
        if primitive == "node":
            return (
                GeometryKind.POINT.value,
                (element.get("lat"), element.get("lon")),
                {
                    "coordinates": build_pointer(*base_tokens, "lat"),
                    "latitude": build_pointer(*base_tokens, "lat"),
                    "longitude": build_pointer(*base_tokens, "lon"),
                },
            )
        center = element.get("center")
        if isinstance(center, dict) and "lat" in center and "lon" in center:
            return (
                GeometryKind.CENTER.value,
                (center.get("lat"), center.get("lon")),
                {
                    "coordinates": build_pointer(*base_tokens, "center", "lat"),
                    "latitude": build_pointer(*base_tokens, "center", "lat"),
                    "longitude": build_pointer(*base_tokens, "center", "lon"),
                },
            )
        return GeometryKind.AREA.value, None, {}
