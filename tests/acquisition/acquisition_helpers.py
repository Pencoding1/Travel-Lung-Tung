"""Shared builders for acquisition tests. All fixtures are SYNTHETIC."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from crawler_service.app.acquisition.pipeline import run_pipeline

NOW = "2026-10-15T00:00:00Z"

DEFAULT_CATEGORY_MAP = {"amenity=cafe": "cafe", "tourism=attraction": "attraction"}


def osm_node(entity_id: Any, lat: Any, lon: Any, **tags: Any) -> Dict[str, Any]:
    node: Dict[str, Any] = {"type": "node", "id": entity_id, "tags": dict(tags)}
    if lat is not None:
        node["lat"] = lat
    if lon is not None:
        node["lon"] = lon
    return node


def osm_way(entity_id: Any, center: Any = None, **tags: Any) -> Dict[str, Any]:
    way: Dict[str, Any] = {"type": "way", "id": entity_id, "tags": dict(tags)}
    if center is not None:
        way["center"] = {"lat": center[0], "lon": center[1]}
    else:
        way["geometry"] = [{"lat": 1.0, "lon": 1.0}]
    return way


def osm_relation(entity_id: Any, **tags: Any) -> Dict[str, Any]:
    return {
        "type": "relation",
        "id": entity_id,
        "bounds": {"minlat": 1.0, "minlon": 1.0, "maxlat": 2.0, "maxlon": 2.0},
        "tags": dict(tags),
    }


def write_json(path: Path, value: Any) -> Path:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


def write_osm_export(path: Path, elements: List[Dict[str, Any]], synthetic: bool = True) -> Path:
    return write_json(path, {"synthetic": synthetic, "version": 0.6, "elements": elements})


def wikidata_entity(
    entity_id: str,
    labels: Optional[Dict[str, str]] = None,
    p31: Optional[List[str]] = None,
    coordinates: Optional[List[Dict[str, Any]]] = None,
    aliases: Optional[Dict[str, List[str]]] = None,
) -> Dict[str, Any]:
    claims: Dict[str, Any] = {}
    if p31:
        claims["P31"] = [
            {
                "mainsnak": {
                    "snaktype": "value",
                    "datavalue": {"value": {"id": qid}, "type": "wikibase-entityid"},
                },
                "rank": "normal",
            }
            for qid in p31
        ]
    if coordinates is not None:
        claims["P625"] = coordinates
    entity: Dict[str, Any] = {"id": entity_id, "claims": claims}
    if labels is not None:
        entity["labels"] = {
            lang: {"language": lang, "value": value} for lang, value in labels.items()
        }
    if aliases is not None:
        entity["aliases"] = {
            lang: [{"language": lang, "value": v} for v in values]
            for lang, values in aliases.items()
        }
    return entity


def coord_claim(lat: Any, lon: Any, rank: str = "normal", globe: Any = "Q2") -> Dict[str, Any]:
    return {
        "mainsnak": {
            "snaktype": "value",
            "datavalue": {
                "value": {"latitude": lat, "longitude": lon, "globe": globe},
                "type": "globecoordinate",
            },
        },
        "rank": rank,
    }


def write_wikidata_export(path: Path, entities: List[Dict[str, Any]], synthetic: bool = True) -> Path:
    return write_json(
        path,
        {"synthetic": synthetic, "entities": {e["id"]: e for e in entities}},
    )


def write_manifest(path: Path, sources: List[Dict[str, Any]], synthetic: bool = True) -> Path:
    return write_json(
        path, {"manifest_version": 1, "synthetic": synthetic, "sources": sources}
    )


def write_mapping(
    path: Path,
    categories: List[Dict[str, str]],
    sources: Dict[str, Dict[str, Any]],
) -> Path:
    return write_json(
        path, {"mapping_version": 1, "categories": categories, "sources": sources}
    )


def default_categories() -> List[Dict[str, str]]:
    return [
        {"id": "cafe", "name": "Cafe", "context": "Coffee shops and cafes"},
        {"id": "attraction", "name": "Attraction", "context": "Tourist attractions"},
        {"id": "museum", "name": "Museum", "context": "Museums"},
    ]


def entity_review(
    city: str = "Ho Chi Minh City",
    district: str = "District 1",
    nation: str = "Vietnam",
    reviewer: str = "test-reviewer",
    evidence_reference: str = "docs/research/DATA_SOURCE_SURVEY.md",
) -> Dict[str, Any]:
    return {
        "reviewer": reviewer,
        "evidence_reference": evidence_reference,
        "city": city,
        "district": district,
        "nation": nation,
    }


def entities_for(*keys: str, **kwargs: Any) -> Dict[str, Dict[str, Any]]:
    return {key: entity_review(**kwargs) for key in keys}


def reviewed_source(
    entities: Optional[Dict[str, Dict[str, Any]]] = None,
    category_map: Optional[Dict[str, str]] = None,
    districts: Optional[Dict[str, str]] = None,
    synthetic: bool = False,
    **overrides: Any,
) -> Dict[str, Any]:
    block: Dict[str, Any] = {
        "synthetic": synthetic,
        "districts": {"Quan 1": "District 1"} if districts is None else districts,
        "category_map": dict(category_map) if category_map is not None else dict(DEFAULT_CATEGORY_MAP),
        "entities": entities if entities is not None else {},
    }
    block.update(overrides)
    return block


def run(manifest: Path, mapping: Path, out: Path, now: str = NOW):
    return run_pipeline(manifest, mapping, out, now=now, dry_run=True)
