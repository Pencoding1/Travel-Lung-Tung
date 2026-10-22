"""Deterministic identity and fact-fingerprint helpers.

Stable source identifiers are a namespaced SHA-256 of the source type and the
source entity id. They are deliberately independent of taxonomy, mutable
address, retrieval date and time, per ``docs/architecture/DATA_CONTRACTS.md``.

The fact fingerprint is a deterministic digest of an entity's *normative
facts* only. It excludes fetch time, source URL, license and other container
metadata so that adding an unrelated record or refreshing a response does not
falsely conflict an unchanged entity.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


def sha256_bytes(payload: bytes) -> str:
    """Return the lowercase hex SHA-256 of the exact saved bytes."""

    return hashlib.sha256(payload).hexdigest()


def namespaced_source_hash(source_type: str, source_entity_id: str) -> str:
    """Namespaced, stable hash of the source identity only."""

    material = f"{source_type}\x1f{source_entity_id}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def stable_source_id(source_type: str, source_entity_id: str) -> str:
    """Source-derived POI id, prefixed by the source namespace.

    The namespace keeps two source families from colliding and makes the origin
    of an id obvious, while the hash keeps it independent of any mutable field.
    """

    digest = namespaced_source_hash(source_type, source_entity_id)
    return f"{source_type}:{digest[:32]}"


def fact_fingerprint(candidate: Any) -> str:
    """Deterministic digest of a candidate's normative facts.

    Deliberately excludes ``raw_sha256``, ``source_url``, ``license``,
    ``retrieved_at``, ``source_revision`` and all container/fetch metadata.
    """

    coordinates = candidate.coordinates
    payload: Mapping[str, Any] = {
        "source_type": candidate.source_type,
        "source_entity_id": candidate.source_entity_id,
        "geometry_kind": candidate.geometry_kind,
        "name": candidate.name,
        "aliases": sorted(candidate.aliases),
        "coordinates": list(coordinates) if coordinates is not None else None,
        "address_hints": sorted(candidate.address_hints.items()),
        "category_tags": sorted(candidate.category_tags),
        "opening_hours_raw": candidate.opening_hours_raw,
    }
    material = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=repr)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()
