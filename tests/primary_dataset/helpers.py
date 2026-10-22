"""Synthetic GeoJSON fixtures for the OC-034 preparation tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_INPUT = REPO_ROOT / "data" / "primary_20261016" / "hcm_pois_final.geojson"

MISSING = object()


def feature(
    name: str = "Cafe",
    lat: Any = 10.77,
    lon: Any = 106.69,
    *,
    category: Any = "coffee",
    processed_name: Any = None,
    district: str = "Quan 1",
    city: str = "HCMC",
    ward: Any = None,
    house: Any = None,
    street: Any = None,
    opening_ho: Any = None,
    cluster: Any = 0,
    geometry: Any = None,
    properties: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    props: Dict[str, Any] = {
        "name": name,
        "processed_name": processed_name if processed_name is not None else name,
        "poi_category": category,
        "addr_city": city,
        "addr_district": district,
        "addr_ward": ward,
        "addr_full": None,
        "addr_house": house,
        "addr_stree": street,
        "opening_ho": opening_ho,
        "cluster": cluster,
        "lat": lat,
        "lon": lon,
    }
    if properties:
        props.update(properties)
    result: Dict[str, Any] = {"type": "Feature", "properties": props}
    if geometry is MISSING:
        return result
    result["geometry"] = geometry if geometry is not None else {"type": "Point", "coordinates": [lon, lat]}
    return result


def write_geojson(path: Path, features: List[Dict[str, Any]]) -> Path:
    document = {
        "type": "FeatureCollection",
        "name": "synthetic",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "features": features,
    }
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    return path


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    text = Path(path).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]
