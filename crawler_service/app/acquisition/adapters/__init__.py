"""Adapter registry keyed by declared source type."""

from __future__ import annotations

from typing import Dict, Type

from .base import SourceAdapter
from .osm import OSMAdapter
from .web_poi import WebPOIAdapter
from .wikidata import WikidataAdapter


_ADAPTERS: Dict[str, Type[SourceAdapter]] = {
    OSMAdapter.source_type: OSMAdapter,
    WikidataAdapter.source_type: WikidataAdapter,
    WebPOIAdapter.source_type: WebPOIAdapter,
}


def get_adapter(source_type: str) -> SourceAdapter:
    try:
        adapter_cls = _ADAPTERS[source_type]
    except KeyError as exc:  # pragma: no cover - defensive
        raise KeyError(f"unsupported source type: {source_type!r}") from exc
    return adapter_cls()


def supported_source_types() -> Dict[str, Type[SourceAdapter]]:
    return dict(_ADAPTERS)
