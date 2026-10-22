"""Closed source-category catalog for the primary GeoJSON.

The catalog is derived *only* from the 14 ``poi_category`` labels observed in
the supplied source vocabulary (OC-032 audit §5). Each entry is a stable,
namespace-prefixed id plus a short context that describes the meaning of the
*source label* -- never a reviewed graph taxonomy, rating, price or finer
category that the source does not contain. An unobserved label is a review
item; it is never silently mapped or invented.
"""

from __future__ import annotations

import hashlib
import json
from typing import Dict, List, Optional

from . import PRIMARY_NAMESPACE

_SOURCE_LABELS: Dict[str, str] = {
    "coffee": "Coffee shops and cafes as labelled by the primary GeoJSON source.",
    "convenience": "Convenience stores and small daily-goods shops in the source vocabulary.",
    "restaurant": "Restaurants and eating places labelled as restaurant in the source data.",
    "finance": "Banks, ATMs and financial-service points as labelled by the source.",
    "lodging": "Places to stay (hotels, guesthouses) as labelled by the source.",
    "specialty_food": "Specialty food shops and food producers as labelled by the source.",
    "apparel_and_gifts": "Clothing, apparel and gift shops as labelled by the source.",
    "health_and_beauty": "Health-care and beauty establishments as labelled by the source.",
    "retail_center": "Shopping centres and retail complexes as labelled by the source.",
    "attractions": "Visitor attractions as labelled by the primary GeoJSON source.",
    "entertainment": "Entertainment venues as labelled by the primary GeoJSON source.",
    "fuel": "Fuel / petrol stations as labelled by the primary GeoJSON source.",
    "transport": "Transport stops and terminals as labelled by the primary GeoJSON source.",
    "public_services": "Public-service facilities as labelled by the primary GeoJSON source.",
}


def _display_name(label: str) -> str:
    return label.replace("_", " ").title()


def _category_id(label: str) -> str:
    return f"{PRIMARY_NAMESPACE}:source-category:{label}"


def _build() -> List[Dict[str, str]]:
    return [
        {
            "id": _category_id(label),
            "name": _display_name(label),
            "context": context,
            "source_label": label,
        }
        for label, context in sorted(_SOURCE_LABELS.items())
    ]


CATALOG: List[Dict[str, str]] = _build()
CATALOG_BY_LABEL: Dict[str, Dict[str, str]] = {row["source_label"]: row for row in CATALOG}


def catalog_version() -> str:
    """Stable content hash of the closed catalog (binds lineage to a revision)."""

    material = json.dumps(
        [
            {"id": row["id"], "name": row["name"], "context": row["context"]}
            for row in CATALOG
        ],
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


CATALOG_VERSION = catalog_version()


def catalog_payload(label: object) -> Optional[Dict[str, str]]:
    """Return the POI ``Category`` payload for an observed source label, or None."""

    if not isinstance(label, str):
        return None
    row = CATALOG_BY_LABEL.get(label.strip())
    if row is None:
        return None
    return {"id": row["id"], "name": row["name"], "context": row["context"]}
