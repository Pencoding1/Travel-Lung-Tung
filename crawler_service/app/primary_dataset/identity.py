"""Deterministic feature identity for the primary dataset.

The supplied GeoJSON carries no genuine upstream identifier, so no
source-derived stable id can be computed. This module builds a strict *local*
identity key from fields that describe the same venue across a re-export:

* a normalized name (accent-folded, lowercase, alphanumerics only);
* the exact coordinates (full precision, no rounding);
* a normalized source address anchor (house + street text).

The key is used only to look up a persisted *internal* record id and to fail
closed when identity fields change. It is explicitly NOT a cross-export stable
identity and must never be presented as an OSM/Wikidata id.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any, Dict, Mapping, Optional

from . import PRIMARY_NAMESPACE


def normalize_text(value: Any) -> str:
    """NFKD accent fold -> ASCII -> lowercase -> alphanumerics only."""

    if not isinstance(value, str):
        return ""
    folded = unicodedata.normalize("NFKD", value)
    ascii_only = folded.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", ascii_only.lower())


def coord_token(latitude: Any, longitude: Any) -> str:
    """Exact coordinate token; ``None`` when either value is not finite numeric."""

    if isinstance(latitude, bool) or isinstance(longitude, bool):
        return ""
    if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
        return ""
    lat = float(latitude)
    lon = float(longitude)
    if lat != lat or lon != lon or lat in (float("inf"), float("-inf")) or lon in (
        float("inf"),
        float("-inf"),
    ):
        return ""
    return f"{lon!r},{lat!r}"


def address_anchor(properties: Mapping[str, Any]) -> str:
    """Normalized source address anchor derived from house + street text only."""

    house = normalize_text(properties.get("addr_house"))
    street = normalize_text(properties.get("addr_stree"))
    return f"{house}|{street}"


def identity_key(
    name_key: str, coordinates: str, anchor: str
) -> str:
    """Readable, collision-checkable local identity key (not a hash)."""

    return f"{PRIMARY_NAMESPACE}|{name_key}|{coordinates}|{anchor}"


def canonical_name(properties: Mapping[str, Any]) -> tuple[str, Optional[str], str]:
    """Return ``(display_name, raw_name_or_None, name_source)``.

    ``processed_name`` is preferred when nonblank; otherwise the raw ``name`` is
    used verbatim. No venue fact is invented and the raw source field is kept for
    lineage by the caller.
    """

    processed = properties.get("processed_name")
    raw = properties.get("name")
    if isinstance(processed, str) and processed.strip():
        return processed.strip(), raw if isinstance(raw, str) else None, "processed_name"
    if isinstance(raw, str) and raw.strip():
        return raw.strip(), raw, "raw_name_fallback"
    return "", raw if isinstance(raw, str) else None, "missing"


def name_key_for(properties: Mapping[str, Any]) -> str:
    """Normalized comparison key for the canonical display name."""

    display, _raw, _source = canonical_name(properties)
    return normalize_text(display)


def exact_feature_hash(feature: Mapping[str, Any]) -> str:
    """Byte-equivalent canonical feature hash (mirrors the OC-032 audit key)."""

    material = json.dumps(feature, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def identity_components(properties: Mapping[str, Any]) -> Dict[str, Any]:
    """The exact, comparable identity fields persisted in the registry."""

    display, raw_name, _source = canonical_name(properties)
    lat = properties.get("lat")
    lon = properties.get("lon")
    return {
        "name_key": normalize_text(display),
        "coordinates": coord_token(lat, lon),
        "address_anchor": address_anchor(properties),
        "raw_name": raw_name,
        "processed_name": properties.get("processed_name"),
    }
