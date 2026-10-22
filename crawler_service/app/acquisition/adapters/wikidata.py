"""Wikidata entity JSON adapter.

Supports the ``wbgetentities`` shape (``{"entities": {...}}``), a list of
entity objects or a single entity object. P625 coordinates are parsed only when
the snak is a value, the datavalue is a ``globecoordinate`` and the globe is
Earth (Wikidata ``Q2``). Deprecated and non-Earth claims are informational
notes; they do not block acceptance when a unique valid live Earth coordinate
exists. Multiple non-identical live coordinates are ambiguous and require
review. JSON Pointers address the actual document, including the
``entities/<QID>`` prefix.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from ..contracts import GeometryKind, InfoCode, POICandidate, ReasonCode, is_finite_in_range
from ..jsonptr import build_pointer
from .base import SourceAdapter, SourceFormatError

_EARTH_GLOBES = {
    "Q2",
    "http://www.wikidata.org/entity/Q2",
    "https://www.wikidata.org/entity/Q2",
}
_QID_RE = re.compile(r"^Q[1-9][0-9]*$")


def _entity_entries(payload: Any) -> List[Tuple[Tuple[Any, ...], Dict[str, Any]]]:
    if isinstance(payload, dict):
        if "error" in payload:
            raise SourceFormatError("Wikidata payload reports a collection error")
        entities = payload.get("entities")
        if isinstance(entities, dict):
            return [
                (("entities", key), value)
                for key, value in entities.items()
                if isinstance(value, dict)
            ]
        if isinstance(entities, list):
            return [
                (("entities", index), value)
                for index, value in enumerate(entities)
                if isinstance(value, dict)
            ]
        if "id" in payload and "claims" in payload:
            return [((), payload)]
        raise SourceFormatError("unrecognized Wikidata payload shape")
    if isinstance(payload, list):
        return [
            ((index,), value)
            for index, value in enumerate(payload)
            if isinstance(value, dict)
        ]
    raise SourceFormatError(f"unsupported Wikidata payload type: {type(payload).__name__}")


class WikidataAdapter(SourceAdapter):
    source_type = "wikidata"

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
        candidates: List[POICandidate] = []
        for base_tokens, entity in _entity_entries(payload):
            candidates.append(
                self._parse_entity(
                    entity,
                    base_tokens=base_tokens,
                    source_url=source_url,
                    license=license,
                    retrieved_at=retrieved_at,
                    raw_content_reference=raw_content_reference,
                    raw_sha256=raw_sha256,
                )
            )
        return candidates

    def _parse_entity(
        self,
        entity: Dict[str, Any],
        *,
        base_tokens: Tuple[Any, ...],
        source_url: str,
        license: str,
        retrieved_at: str,
        raw_content_reference: str,
        raw_sha256: str,
    ) -> POICandidate:
        entity_id = entity.get("id")
        claims = entity.get("claims") if isinstance(entity.get("claims"), dict) else {}
        field_paths: Dict[str, str] = {"identity": build_pointer(*base_tokens, "id")}
        identity_reasons: List[str] = []

        if isinstance(entity_id, str) and _QID_RE.match(entity_id.strip()):
            normalized_id = entity_id.strip()
        else:
            normalized_id = ""
            identity_reasons.append(
                ReasonCode.MISSING_SOURCE_IDENTITY
                if entity_id is None
                else ReasonCode.INVALID_SOURCE_IDENTITY
            )

        name, name_path = self._label(entity, base_tokens)
        if name_path:
            field_paths["name"] = name_path

        aliases = self._aliases(entity)

        category_tags: List[str] = []
        p31 = claims.get("P31")
        if isinstance(p31, list):
            for i, statement in enumerate(p31):
                qid = self._statement_entity_id(statement)
                if qid:
                    category_tags.append(f"P31={qid}")
                    field_paths.setdefault(
                        "category", build_pointer(*base_tokens, "claims", "P31", i)
                    )

        coordinates, coord_paths, uncertainty, info = self._coordinates(claims, base_tokens)
        field_paths.update(coord_paths)

        geometry = (
            GeometryKind.POINT.value if coordinates is not None else GeometryKind.UNKNOWN.value
        )

        revision = entity.get("lastrevid")
        source_revision = (
            str(revision)
            if isinstance(revision, int) and not isinstance(revision, bool)
            else (entity.get("modified") if isinstance(entity.get("modified"), str) else None)
        )

        return POICandidate(
            source_type=self.source_type,
            source_entity_id=normalized_id,
            geometry_kind=geometry,
            name=name,
            aliases=aliases,
            coordinates=coordinates,
            address_hints={},
            category_tags=category_tags,
            opening_hours_raw=None,
            raw_content_reference=raw_content_reference,
            raw_sha256=raw_sha256,
            source_url=source_url,
            license=license,
            retrieved_at=retrieved_at,
            field_paths=field_paths,
            uncertainty_codes=identity_reasons + uncertainty,
            info_codes=info,
            source_revision=source_revision,
        )

    @staticmethod
    def _label(
        entity: Dict[str, Any], base_tokens: Tuple[Any, ...]
    ) -> Tuple[Optional[str], Optional[str]]:
        labels = entity.get("labels")
        if not isinstance(labels, dict):
            return None, None
        for lang in ("vi", "en"):
            entry = labels.get(lang)
            if isinstance(entry, dict):
                value = entry.get("value")
                if isinstance(value, str) and value.strip():
                    return value.strip(), build_pointer(*base_tokens, "labels", lang, "value")
        return None, None

    @staticmethod
    def _aliases(entity: Dict[str, Any]) -> List[str]:
        aliases = entity.get("aliases")
        if not isinstance(aliases, dict):
            return []
        collected: List[str] = []
        for lang in ("vi", "en"):
            entries = aliases.get(lang)
            if isinstance(entries, list):
                for entry in entries:
                    if isinstance(entry, dict):
                        value = entry.get("value")
                        if isinstance(value, str) and value.strip():
                            collected.append(value.strip())
        return collected

    @staticmethod
    def _statement_entity_id(statement: Any) -> Optional[str]:
        if not isinstance(statement, dict):
            return None
        if statement.get("rank") == "deprecated":
            return None
        snak = statement.get("mainsnak")
        if not isinstance(snak, dict) or snak.get("snaktype") != "value":
            return None
        datavalue = snak.get("datavalue")
        if not isinstance(datavalue, dict) or datavalue.get("type") != "wikibase-entityid":
            return None
        value = datavalue.get("value")
        if isinstance(value, dict):
            qid = value.get("id")
            if isinstance(qid, str) and qid.strip():
                return qid.strip()
        return None

    @staticmethod
    def _is_earth(globe: Any) -> bool:
        return isinstance(globe, str) and globe.strip() in _EARTH_GLOBES

    def _coordinates(
        self, claims: Dict[str, Any], base_tokens: Tuple[Any, ...]
    ) -> Tuple[Optional[Tuple[Any, Any]], Dict[str, str], List[str], List[str]]:
        p625 = claims.get("P625")
        if not isinstance(p625, list) or not p625:
            return None, {}, [ReasonCode.MISSING_COORDINATES], []

        valid_live: List[Tuple[Any, Any, str, Tuple[Any, ...]]] = []
        saw_invalid = False
        saw_deprecated = False
        saw_non_earth = False

        for i, statement in enumerate(p625):
            if not isinstance(statement, dict):
                continue
            rank = statement.get("rank") or "normal"
            snak = statement.get("mainsnak")
            if not isinstance(snak, dict) or snak.get("snaktype") != "value":
                continue
            datavalue = snak.get("datavalue")
            if not isinstance(datavalue, dict) or datavalue.get("type") != "globecoordinate":
                continue
            value = datavalue.get("value")
            if not isinstance(value, dict):
                continue
            value_tokens = base_tokens + ("claims", "P625", i, "mainsnak", "datavalue", "value")
            if rank == "deprecated":
                saw_deprecated = True
                continue
            if not self._is_earth(value.get("globe")):
                saw_non_earth = True
                continue
            lat = value.get("latitude")
            lon = value.get("longitude")
            if not is_finite_in_range(lat, -90.0, 90.0) or not is_finite_in_range(lon, -180.0, 180.0):
                saw_invalid = True
                continue
            valid_live.append((lat, lon, rank, value_tokens))

        uncertainty: List[str] = []
        info: List[str] = []
        if saw_deprecated:
            info.append(InfoCode.DEPRECATED_COORDINATE_IGNORED)
        if saw_non_earth:
            info.append(InfoCode.NON_EARTH_GLOBE_IGNORED)

        if not valid_live:
            if saw_invalid:
                uncertainty.append(ReasonCode.INVALID_COORDINATES)
            elif saw_deprecated or saw_non_earth:
                uncertainty.append(ReasonCode.NO_LIVE_COORDINATES)
            else:
                uncertainty.append(ReasonCode.MISSING_COORDINATES)
            return None, {}, uncertainty, info

        preferred = [item for item in valid_live if item[2] == "preferred"]
        pool = preferred if preferred else valid_live
        distinct = {(type(item[0]).__name__, repr(item[0]), type(item[1]).__name__, repr(item[1])) for item in pool}
        if len(distinct) != 1:
            uncertainty.append(ReasonCode.AMBIGUOUS_COORDINATES)
            return None, {}, uncertainty, info

        chosen = pool[0]
        value_tokens = chosen[3]
        return (
            (chosen[0], chosen[1]),
            {
                "coordinates": build_pointer(*value_tokens),
                "latitude": build_pointer(*value_tokens, "latitude"),
                "longitude": build_pointer(*value_tokens, "longitude"),
            },
            uncertainty,
            info,
        )
