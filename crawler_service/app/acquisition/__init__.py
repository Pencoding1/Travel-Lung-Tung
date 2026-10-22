"""Deterministic, source-authorized POI acquisition pipeline.

This package implements the contracts described in
``docs/architecture/DATA_ACQUISITION_DESIGN.md`` and
``docs/architecture/DATA_CONTRACTS.md``. It parses authorized local exports
(OSM JSON and Wikidata entity JSON) into candidates, applies an explicit
reviewed mapping, and writes an atomic dry-run manifest. It never performs
live ingestion and never performs network acquisition.
"""

from .contracts import (
    CollectionStatus,
    DecisionOutcome,
    GeometryKind,
    InfoCode,
    IngestionDecision,
    POICandidate,
    RawSourceRecord,
    ReasonCode,
    ResolvedPOI,
    ResolutionStatus,
)

__all__ = [
    "CollectionStatus",
    "DecisionOutcome",
    "GeometryKind",
    "InfoCode",
    "IngestionDecision",
    "POICandidate",
    "RawSourceRecord",
    "ReasonCode",
    "ResolvedPOI",
    "ResolutionStatus",
]

PIPELINE_VERSION = 3
