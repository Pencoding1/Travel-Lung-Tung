"""Acquisition adapter for normalized public-web POI exports.

The input is the normalized JSON produced by
``crawler_service.app.social_ingest``. It is intentionally *not* OSM/Wikidata
shaped and never claims their source identity.

Identity rule: source-namespaced, stable, order-independent
-----------------------------------------------------------
A record's native anchor is ``record_id`` (the JSON-LD ``@id``, the HTML chapter
``<page-slug>#<section-id>``, the CSV ``id``/``url`` column). It is never an
array index and never a hash of the mutable name/address/review, so renaming a
POI or editing its review keeps the same entity, and reordering/adding/removing
records never renames a surviving one.

That anchor is only unique *inside the page it came from*, so the exported
identity is namespaced by the canonical URL of that page:

* an anchor that is already an absolute URL (scheme + host) is used as-is. This
  is the single documented exception: an absolute URL is globally unique by
  construction, and keeping it verbatim is what makes namespacing idempotent --
  re-parsing an already namespaced id reproduces it byte for byte.
* every other anchor (``node/137#chapter-1``, ``#poi-1``, ``csv-1``) becomes
  ``<canonical page URL>#<anchor>`` (a fragment-only anchor such as ``#poi-1``
  is appended directly, i.e. ``<page>#poi-1``). A relative ``@id`` therefore
  never becomes a bare global id, and two sources that both use native id ``1``
  can never collide.
* when no absolute page URL is available (neither the record's ``page_url`` nor
  the source's ``source_url``) the identity is left empty and the record is
  flagged ``invalid_source_identity``. Fail closed: a bare, un-namespaced anchor
  is never emitted.

``source_url`` never acts as an entity identity on its own: it only supplies the
namespace for native anchors, and records whose derived identities collide (e.g.
a JSON-LD block whose ``@id`` is the listing page itself) are all flagged
``invalid_source_identity`` instead of being silently merged into one entity.
The canonical page URL keeps its path and query -- paginated listing pages are
different pages -- and drops the fragment, because an in-page anchor is part of
the native id, not of the namespace.

Address is mandatory
--------------------
P0 requires name + address + (description or review). Coordinates never
substitute for the address, so a record without ``address_raw`` carries
``missing_address`` even when it has coordinates; neither this adapter nor the
acquisition CLI can then accept it.

Description/review text and per-field evidence are carried through the candidate
envelope and raw index without changing the existing mapping/quality gate.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

from ..contracts import GeometryKind, POICandidate, ReasonCode
from ..jsonptr import build_pointer
from .base import SourceAdapter, SourceFormatError

_ISSUE_TO_REASON = {
    "missing_name": ReasonCode.MISSING_NAME,
    "missing_address": ReasonCode.MISSING_ADDRESS,
    "missing_description": ReasonCode.MISSING_DESCRIPTION,
    "unstable_record_anchor": ReasonCode.INVALID_SOURCE_IDENTITY,
}

_EVIDENCE_KEYS = (
    "field",
    "value",
    "source_url",
    "fetched_at",
    "raw_capture_path",
    "raw_sha256",
    "locator",
)

_DEFAULT_PORTS = {"http": 80, "https": 443}


def _nonblank(value: Any) -> Optional[str]:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _canonical_absolute_url(value: Any, *, keep_fragment: bool) -> Optional[str]:
    """Canonicalise an absolute URL, or return ``None`` when it is not one.

    Only ``scheme://host`` values qualify, so a relative anchor such as
    ``node/137#chapter-1`` or a bare id such as ``csv-1`` (which ``urlsplit``
    reports with an empty authority) is never mistaken for a global identity.
    Scheme/host are lowercased and a default port is dropped; path and query are
    preserved because different paths/queries are different pages. The fragment
    is kept only when the fragment *is* the anchor (an absolute ``@id``).
    """

    text = _nonblank(value)
    if text is None:
        return None
    parts = urlsplit(text)
    scheme = parts.scheme.lower()
    if not scheme or not parts.netloc:
        return None
    host = parts.hostname
    if not host:
        return None
    netloc = f"[{host}]" if ":" in host and not host.startswith("[") else host
    try:
        port = parts.port
    except ValueError:
        return None
    if port is not None and port != _DEFAULT_PORTS.get(scheme):
        netloc = f"{netloc}:{port}"
    path = parts.path or "/"
    query = f"?{parts.query}" if parts.query else ""
    fragment = f"#{parts.fragment}" if keep_fragment and parts.fragment else ""
    return f"{scheme}://{netloc}{path}{query}{fragment}"


def canonical_page_namespace(url: Any) -> Optional[str]:
    """Canonical absolute page URL used as the namespace for native anchors.

    The fragment is dropped here: an in-page anchor belongs to the native id,
    never to the page namespace.
    """

    return _canonical_absolute_url(url, keep_fragment=False)


def namespaced_entity_id(
    native_id: Any, *, page_url: Any = "", source_url: Any = ""
) -> str:
    """Derive the exported entity identity for one native anchor.

    Returns ``""`` (never a bare global id) when the anchor is blank or no
    absolute page URL is available; callers must treat that as an invalid source
    identity. The function is idempotent: feeding its own output back in with a
    different page URL returns the same value, because absolute URLs are used
    as-is.
    """

    native = _nonblank(native_id)
    if native is None:
        return ""
    absolute = _canonical_absolute_url(native, keep_fragment=True)
    if absolute is not None:
        return absolute
    namespace = canonical_page_namespace(page_url) or canonical_page_namespace(
        source_url
    )
    if namespace is None:
        return ""
    # A fragment-only anchor (``#poi-1``) already starts with the separator, so
    # it is appended verbatim: the identity is then the page URL plus its
    # fragment, with no doubled ``#``.
    if native.startswith("#"):
        return f"{namespace}{native}"
    return f"{namespace}#{native}"


class WebPOIAdapter(SourceAdapter):
    source_type = "web_poi"

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
        if not isinstance(payload, dict):
            raise SourceFormatError("web_poi export must be a JSON object")
        records = payload.get("records")
        if not isinstance(records, list):
            raise SourceFormatError("web_poi export requires a 'records' array")
        source_block = payload.get("source")
        if not isinstance(source_block, dict):
            raise SourceFormatError("web_poi export requires a 'source' object")
        export_synthetic = payload.get("synthetic")
        if type(export_synthetic) is not bool:
            raise SourceFormatError("web_poi export requires an explicit boolean 'synthetic'")
        reuse_status = _nonblank(source_block.get("reuse_status")) or "unknown"
        declared_license = _nonblank(source_block.get("license")) or "UNKNOWN"
        policy_unverified = (not export_synthetic) and (
            reuse_status != "permitted"
            or declared_license.upper() in ("UNKNOWN", "UNLICENSED", "NONE")
        )

        candidates: List[POICandidate] = []
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                raise SourceFormatError(f"records[{index}] must be an object")
            candidates.append(
                self._parse_record(
                    record,
                    index=index,
                    source_url=source_url,
                    declared_license=declared_license,
                    policy_unverified=policy_unverified,
                    retrieved_at=retrieved_at,
                    raw_content_reference=raw_content_reference,
                    raw_sha256=raw_sha256,
                )
            )
        self._flag_colliding_identities(candidates)
        return candidates

    @staticmethod
    def _flag_colliding_identities(candidates: List[POICandidate]) -> None:
        """Flag every record that claims an identity another record also claims.

        Two records that resolve to the same namespaced identity cannot both be
        that entity (typically a listing page reusing the page URL as ``@id``,
        or a duplicated in-page anchor). Merging them would silently collapse
        separate listings, so all of them are marked invalid source identity and
        left for review.
        """

        counts: Dict[str, int] = {}
        for candidate in candidates:
            if candidate.source_entity_id:
                counts[candidate.source_entity_id] = (
                    counts.get(candidate.source_entity_id, 0) + 1
                )
        for candidate in candidates:
            entity_id = candidate.source_entity_id
            if (
                entity_id
                and counts[entity_id] > 1
                and ReasonCode.INVALID_SOURCE_IDENTITY
                not in candidate.uncertainty_codes
            ):
                candidate.uncertainty_codes.append(
                    ReasonCode.INVALID_SOURCE_IDENTITY
                )

    def _parse_record(
        self,
        record: Dict[str, Any],
        *,
        index: int,
        source_url: str,
        declared_license: str,
        policy_unverified: bool,
        retrieved_at: str,
        raw_content_reference: str,
        raw_sha256: str,
    ) -> POICandidate:
        native_id = _nonblank(record.get("record_id")) or ""
        name = _nonblank(record.get("name"))
        address_raw = _nonblank(record.get("address_raw"))
        description = _nonblank(record.get("description"))
        review_text = _nonblank(record.get("review_text"))
        page_url = _nonblank(record.get("page_url")) or ""
        page_capture_sha = _nonblank(record.get("page_capture_sha256"))

        # Source-namespaced identity; see the module docstring for the rule.
        record_id = namespaced_entity_id(
            native_id, page_url=page_url, source_url=source_url
        )

        evidence = record.get("field_evidence") or []
        if not isinstance(evidence, list) or any(
            not isinstance(item, dict) for item in evidence
        ):
            raise SourceFormatError(
                f"records[{index}].field_evidence must be a list of objects"
            )
        cleaned_evidence: List[Dict[str, Any]] = []
        for item in evidence:
            missing = [key for key in _EVIDENCE_KEYS if key not in item]
            if missing:
                raise SourceFormatError(
                    f"records[{index}].field_evidence item missing {missing}"
                )
            cleaned_evidence.append({key: item[key] for key in _EVIDENCE_KEYS})

        hints = record.get("address_hints")
        address_hints: Dict[str, str] = {}
        if isinstance(hints, dict):
            for key, value in hints.items():
                if isinstance(key, str) and isinstance(value, str) and value.strip():
                    address_hints[key] = value.strip()
        if address_raw and "addr:full" not in address_hints:
            address_hints["addr:full"] = address_raw

        coordinates = record.get("coordinates")
        coord_tuple = None
        geometry = GeometryKind.UNKNOWN.value
        if coordinates is not None:
            if (
                not isinstance(coordinates, list)
                or len(coordinates) != 2
            ):
                raise SourceFormatError(
                    f"records[{index}].coordinates must be null or [lat, lon]"
                )
            coord_tuple = (coordinates[0], coordinates[1])
            geometry = GeometryKind.POINT.value

        issues = record.get("issues") or []
        if not isinstance(issues, list) or any(not isinstance(item, str) for item in issues):
            raise SourceFormatError(f"records[{index}].issues must be a list of strings")
        reasons: List[str] = []
        for issue in issues:
            reason = _ISSUE_TO_REASON.get(issue)
            if reason and reason not in reasons:
                reasons.append(reason)
        if not record_id and ReasonCode.INVALID_SOURCE_IDENTITY not in reasons:
            reasons.append(ReasonCode.INVALID_SOURCE_IDENTITY)
        if policy_unverified and ReasonCode.POLICY_UNVERIFIED not in reasons:
            reasons.append(ReasonCode.POLICY_UNVERIFIED)
        if name is None and ReasonCode.MISSING_NAME not in reasons:
            reasons.append(ReasonCode.MISSING_NAME)
        # Coordinates are never an address: P0 requires address evidence, so
        # this gate ignores coordinates completely.
        if address_raw is None and ReasonCode.MISSING_ADDRESS not in reasons:
            reasons.append(ReasonCode.MISSING_ADDRESS)
        if description is None and review_text is None and ReasonCode.MISSING_DESCRIPTION not in reasons:
            reasons.append(ReasonCode.MISSING_DESCRIPTION)

        field_paths: Dict[str, str] = {
            "identity": build_pointer("records", index, "record_id"),
            "identity_namespace": build_pointer("records", index, "page_url"),
            "name": build_pointer("records", index, "name"),
            "address": build_pointer("records", index, "address_raw"),
            "description": build_pointer("records", index, "description"),
            "review": build_pointer("records", index, "review_text"),
            "category": build_pointer("records", index, "category_tags"),
            "coordinates": build_pointer("records", index, "coordinates"),
            "opening_hours": build_pointer("records", index, "opening_hours_raw"),
            "field_evidence": build_pointer("records", index, "field_evidence"),
        }

        category_tags = record.get("category_tags") or []
        if not isinstance(category_tags, list) or any(
            not isinstance(item, str) for item in category_tags
        ):
            raise SourceFormatError(
                f"records[{index}].category_tags must be a list of strings"
            )

        return POICandidate(
            source_type=self.source_type,
            source_entity_id=record_id,
            geometry_kind=geometry,
            name=name,
            aliases=[],
            coordinates=coord_tuple,
            address_hints=address_hints,
            category_tags=list(category_tags),
            opening_hours_raw=_nonblank(record.get("opening_hours_raw")),
            raw_content_reference=raw_content_reference,
            raw_sha256=raw_sha256,
            source_url=page_url,
            license=declared_license,
            retrieved_at=retrieved_at,
            source_revision=page_capture_sha,
            field_paths=field_paths,
            uncertainty_codes=reasons,
            description=description,
            review_text=review_text,
            field_evidence=cleaned_evidence,
        )
