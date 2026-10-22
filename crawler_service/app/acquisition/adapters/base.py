"""Source adapter interface."""

from __future__ import annotations

from typing import Any, List

from ..contracts import POICandidate


class SourceFormatError(ValueError):
    """Raised when a payload is not a valid document for this source type."""


class SourceAdapter:
    """Base class for deterministic raw-format adapters."""

    source_type: str = ""

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
    ) -> List[POICandidate]:  # pragma: no cover - interface
        raise NotImplementedError

    @staticmethod
    def first_nonblank(*values: Any) -> Any:
        for value in values:
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None
