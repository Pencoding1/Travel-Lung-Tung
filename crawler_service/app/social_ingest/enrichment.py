"""Injectable enrichment clients (no paid calls in this task).

Both transports are injected. There is deliberately no default HTTP
implementation for a paid API, so importing/running this module cannot call
SerpApi/Tavily. A missing key raises before any transport is touched, and no
secret is ever placed in an exception, provenance or repr.

Conservative matching
---------------------
A lookup never assigns a candidate from a name alone. A place is only eligible
when (a) its name matches exactly after whitespace/case normalisation, (b) it
carries a non-empty address that agrees with the expected address whenever the
caller supplied one, and (c) its coordinates are finite and inside
``[-90, 90]`` / ``[-180, 180]``. Otherwise the outcome is ``not_found`` (no
usable candidate exists) or ``review_required`` (a same-name place exists but
its address is missing or contradicts the request, i.e. a human must decide);
nothing is auto-assigned.

Error sanitisation
------------------
Transport exceptions can embed the failing URL, and that URL carries the API
key, so only the exception class name becomes a reason. The original message,
URL, query string and key are never copied into the outcome.

Provenance
----------
Every provenance row names its source, source URL, retrieval time and raw
reference. Where a value genuinely does not exist it is written as
``unknown:not_available`` (see :data:`UNKNOWN_PROVENANCE`) instead of being
left blank, so gaps stay visible to reviewers.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..acquisition.contracts import is_finite_in_range

Transport = Callable[[Dict[str, str]], Tuple[int, bytes]]
Clock = Callable[[], datetime]

_WHITESPACE_RE = re.compile(r"\s+")
_EXCEPTION_NAME_RE = re.compile(r"[^A-Za-z0-9_]+")

#: Explicit placeholder for provenance aspects that genuinely have no value.
#: Never silently blank: readers must be able to tell "absent" from "unknown".
UNKNOWN_PROVENANCE = "unknown:not_available"

STATUS_MATCHED = "matched"
STATUS_AMBIGUOUS = "ambiguous"
STATUS_NOT_FOUND = "not_found"
STATUS_REVIEW_REQUIRED = "review_required"
STATUS_ERROR = "error"

#: Provenance keys every row is guaranteed to carry.
PROVENANCE_KEYS = (
    "source",
    "source_url",
    "retrieved_at",
    "raw_reference",
    "response_sha256",
    "selected",
    "match_decision",
)


class EnrichmentError(RuntimeError):
    def __init__(self, reason: str, detail: str = "") -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}" if detail else reason)


class MissingApiKeyError(EnrichmentError):
    def __init__(self) -> None:
        super().__init__("missing_api_key", "no API key supplied; no call attempted")


class TransportNotConfigured(EnrichmentError):
    def __init__(self) -> None:
        super().__init__(
            "transport_not_configured",
            "paid enrich transports must be injected explicitly; no default network client exists",
        )


def _normalize(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", value or "").strip().casefold()


def _iso_utc(moment: datetime) -> str:
    if not isinstance(moment, datetime):
        raise EnrichmentError("invalid_clock_value", "clock must return a datetime")
    if moment.tzinfo is None or moment.utcoffset() is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds")


def _json_number(value: Any) -> Optional[float]:
    """Float for JSON-safe output; NaN/inf/non-numbers become ``None``."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _sanitized_transport_reason(exc: BaseException) -> str:
    """Reason built from the exception *class* only.

    ``OSError``/``URLError`` messages routinely contain the failing URL, and the
    URL contains the API key, so the message is never copied.
    """

    name = _EXCEPTION_NAME_RE.sub("", type(exc).__name__)[:64] or "Exception"
    prefix = "network_error" if isinstance(exc, OSError) else "transport_error"
    return f"{prefix}:{name}"


def _provenance_row(
    *,
    source: str,
    source_url: str,
    retrieved_at: str,
    raw_reference: str,
    raw_sha256: str,
    name: str,
    address: str,
    latitude: Optional[float],
    longitude: Optional[float],
    selected: bool,
    match_decision: str,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "source": source,
        "source_url": source_url or UNKNOWN_PROVENANCE,
        "retrieved_at": retrieved_at or UNKNOWN_PROVENANCE,
        "raw_reference": raw_reference or UNKNOWN_PROVENANCE,
        "response_sha256": raw_sha256,
        "name": name,
        "address": address,
        "latitude": latitude,
        "longitude": longitude,
        "selected": bool(selected),
        "match_decision": match_decision,
    }
    if extra:
        row.update(extra)
    return row


@dataclass
class EnrichmentCandidate:
    name: str
    address: str
    latitude: float
    longitude: float
    source: str
    raw_sha256: str
    source_url: str = UNKNOWN_PROVENANCE
    retrieved_at: str = UNKNOWN_PROVENANCE
    raw_reference: str = UNKNOWN_PROVENANCE
    evidence_reference: str = ""

    def provenance(self) -> Dict[str, Any]:
        extra = {"evidence_reference": self.evidence_reference} if self.evidence_reference else None
        return _provenance_row(
            source=self.source,
            source_url=self.source_url,
            retrieved_at=self.retrieved_at,
            raw_reference=self.raw_reference,
            raw_sha256=self.raw_sha256,
            name=self.name,
            address=self.address,
            latitude=_json_number(self.latitude),
            longitude=_json_number(self.longitude),
            selected=True,
            match_decision="selected",
            extra=extra,
        )


@dataclass
class EnrichmentOutcome:
    status: str
    reason: Optional[str] = None
    candidate: Optional[EnrichmentCandidate] = None
    provenance: List[Dict[str, Any]] = field(default_factory=list)


class SerpApiMapsEnricher:
    """Look up one POI by name; ambiguous or unconfirmed results are never picked."""

    endpoint = "https://serpapi.com/search.json"

    def __init__(
        self,
        api_key: Optional[str],
        transport: Optional[Transport] = None,
        *,
        clock: Optional[Clock] = None,
    ) -> None:
        if not api_key or not str(api_key).strip():
            raise MissingApiKeyError()
        self._api_key = str(api_key).strip()
        self._transport = transport
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def __repr__(self) -> str:  # never leak the key
        return f"SerpApiMapsEnricher(endpoint={self.endpoint!r}, configured=True)"

    def lookup(
        self,
        name: str,
        address: Optional[str] = None,
        *,
        raw_reference: Optional[str] = None,
        retrieved_at: Optional[str] = None,
    ) -> EnrichmentOutcome:
        wanted = _normalize(name) if isinstance(name, str) else ""
        if not wanted:
            return EnrichmentOutcome(STATUS_NOT_FOUND, reason="empty_name")
        if self._transport is None:
            raise TransportNotConfigured()
        expected_address = _normalize(address) if address else ""
        stamp = (
            retrieved_at.strip()
            if isinstance(retrieved_at, str) and retrieved_at.strip()
            else _iso_utc(self._clock())
        )
        reference = (
            raw_reference.strip()
            if isinstance(raw_reference, str) and raw_reference.strip()
            else UNKNOWN_PROVENANCE
        )
        params = {"engine": "google_maps", "q": name, "api_key": self._api_key}
        if address:
            params["address"] = address
        try:
            status, body = self._transport(params)
        except Exception as exc:  # message may carry the URL and therefore the key
            return EnrichmentOutcome(STATUS_ERROR, reason=_sanitized_transport_reason(exc))
        if isinstance(status, bool) or not isinstance(status, int):
            return EnrichmentOutcome(
                STATUS_ERROR, reason="transport_contract_violation:status_not_int"
            )
        if not isinstance(body, (bytes, bytearray)):
            return EnrichmentOutcome(
                STATUS_ERROR, reason="transport_contract_violation:body_not_bytes"
            )
        body = bytes(body)
        digest = hashlib.sha256(body).hexdigest()
        if status in (401, 403):
            return EnrichmentOutcome(STATUS_ERROR, reason=f"auth_failed_{status}")
        if status == 429:
            return EnrichmentOutcome(STATUS_ERROR, reason="rate_limited_429")
        if status < 200 or status >= 300:
            return EnrichmentOutcome(STATUS_ERROR, reason=f"http_{status}")
        try:
            document = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return EnrichmentOutcome(STATUS_ERROR, reason="invalid_json")
        places = document.get("local_results") if isinstance(document, dict) else None
        if not isinstance(places, list) or not places:
            return EnrichmentOutcome(STATUS_NOT_FOUND, reason="no_local_results")

        def row(place: Dict[str, Any], *, decision: str) -> Dict[str, Any]:
            coordinates = place.get("gps_coordinates")
            coordinates = coordinates if isinstance(coordinates, dict) else {}
            candidate_address = place.get("address")
            return _provenance_row(
                source="serpapi_google_maps",
                source_url=self.endpoint,
                retrieved_at=stamp,
                raw_reference=reference,
                raw_sha256=digest,
                name=str(place.get("title") or "").strip(),
                address=candidate_address.strip() if isinstance(candidate_address, str) else "",
                latitude=_json_number(coordinates.get("latitude")),
                longitude=_json_number(coordinates.get("longitude")),
                selected=False,
                match_decision=decision,
            )

        confirmed: List[EnrichmentCandidate] = []
        address_rejections: List[Dict[str, Any]] = []
        coordinate_rejections: List[Dict[str, Any]] = []
        for place in places:
            if not isinstance(place, dict):
                continue
            title = place.get("title")
            if not isinstance(title, str) or _normalize(title) != wanted:
                continue
            raw_address = place.get("address")
            candidate_address = raw_address.strip() if isinstance(raw_address, str) else ""
            if not candidate_address:
                address_rejections.append(row(place, decision="rejected_missing_address"))
                continue
            if expected_address and _normalize(candidate_address) != expected_address:
                address_rejections.append(row(place, decision="rejected_address_mismatch"))
                continue
            coordinates = place.get("gps_coordinates")
            coordinates = coordinates if isinstance(coordinates, dict) else {}
            latitude = coordinates.get("latitude")
            longitude = coordinates.get("longitude")
            if not is_finite_in_range(latitude, -90.0, 90.0) or not is_finite_in_range(
                longitude, -180.0, 180.0
            ):
                coordinate_rejections.append(row(place, decision="rejected_invalid_coordinates"))
                continue
            confirmed.append(
                EnrichmentCandidate(
                    name=title.strip(),
                    address=candidate_address,
                    latitude=float(latitude),
                    longitude=float(longitude),
                    source="serpapi_google_maps",
                    raw_sha256=digest,
                    source_url=self.endpoint,
                    retrieved_at=stamp,
                    raw_reference=reference,
                )
            )

        rejected_rows = address_rejections + coordinate_rejections
        if not confirmed:
            if address_rejections:
                return EnrichmentOutcome(
                    STATUS_REVIEW_REQUIRED,
                    reason="address_not_confirmed",
                    provenance=rejected_rows,
                )
            if coordinate_rejections:
                return EnrichmentOutcome(
                    STATUS_NOT_FOUND,
                    reason="no_candidate_with_finite_coordinates",
                    provenance=rejected_rows,
                )
            return EnrichmentOutcome(STATUS_NOT_FOUND, reason="no_exact_name_match")

        distinct_coordinates = {(item.latitude, item.longitude) for item in confirmed}
        distinct_addresses = {_normalize(item.address) for item in confirmed}
        if len(distinct_coordinates) > 1 or len(distinct_addresses) > 1:
            return EnrichmentOutcome(
                STATUS_AMBIGUOUS,
                reason="multiple_exact_matches",
                provenance=[
                    item.provenance() | {"selected": False, "match_decision": "not_selected"}
                    for item in confirmed
                ]
                + rejected_rows,
            )
        chosen = confirmed[0]
        provenance: List[Dict[str, Any]] = []
        for item in confirmed:
            if item is chosen:
                provenance.append(item.provenance())
            else:
                provenance.append(
                    item.provenance()
                    | {"selected": False, "match_decision": "duplicate_not_selected"}
                )
        return EnrichmentOutcome(
            STATUS_MATCHED,
            candidate=chosen,
            provenance=provenance + rejected_rows,
        )


@dataclass
class ReviewedEvidence:
    name: str
    address: str
    latitude: float
    longitude: float
    reviewer: str
    evidence_reference: str
    source_url: str = UNKNOWN_PROVENANCE
    retrieved_at: str = UNKNOWN_PROVENANCE


class ReviewedEvidenceEnricher:
    """Deterministic reviewed evidence injection (synthetic tests / manual review).

    The reviewed set is closed: a name match whose address disagrees with the
    request is ``not_found`` (this fixture does not cover that place), while a
    reviewed row published without an address cannot be confirmed at all and is
    reported as ``review_required``.
    """

    def __init__(self, reviews: List[ReviewedEvidence]) -> None:
        if not reviews:
            raise EnrichmentError("no_reviewed_evidence")
        self._reviews = list(reviews)

    def lookup(self, name: str, address: Optional[str] = None) -> EnrichmentOutcome:
        wanted = _normalize(name) if isinstance(name, str) else ""
        if not wanted:
            return EnrichmentOutcome(STATUS_NOT_FOUND, reason="empty_name")
        expected_address = _normalize(address) if address else ""
        name_matches = [review for review in self._reviews if _normalize(review.name) == wanted]
        if not name_matches:
            return EnrichmentOutcome(STATUS_NOT_FOUND, reason="no_reviewed_match")

        confirmed: List[ReviewedEvidence] = []
        rejected: List[Dict[str, Any]] = []
        missing_address = False
        invalid_coordinates = False
        for review in name_matches:
            review_address = review.address.strip() if isinstance(review.address, str) else ""
            if not review_address:
                missing_address = True
                rejected.append(_reviewed_row(review, decision="rejected_missing_address"))
                continue
            if expected_address and _normalize(review_address) != expected_address:
                rejected.append(_reviewed_row(review, decision="rejected_address_mismatch"))
                continue
            if not is_finite_in_range(review.latitude, -90.0, 90.0) or not is_finite_in_range(
                review.longitude, -180.0, 180.0
            ):
                invalid_coordinates = True
                rejected.append(_reviewed_row(review, decision="rejected_invalid_coordinates"))
                continue
            confirmed.append(review)

        if not confirmed:
            if missing_address:
                return EnrichmentOutcome(
                    STATUS_REVIEW_REQUIRED, reason="address_not_confirmed", provenance=rejected
                )
            if invalid_coordinates:
                return EnrichmentOutcome(
                    STATUS_NOT_FOUND, reason="invalid_reviewed_coordinates", provenance=rejected
                )
            return EnrichmentOutcome(
                STATUS_NOT_FOUND, reason="no_reviewed_match", provenance=rejected
            )

        coordinates = {(review.latitude, review.longitude) for review in confirmed}
        addresses = {_normalize(review.address) for review in confirmed}
        if len(coordinates) > 1 or len(addresses) > 1:
            return EnrichmentOutcome(
                STATUS_AMBIGUOUS,
                reason="conflicting_reviewed_coordinates",
                provenance=rejected
                + [_reviewed_row(review, decision="not_selected") for review in confirmed],
            )
        review = confirmed[0]
        return EnrichmentOutcome(
            STATUS_MATCHED,
            candidate=EnrichmentCandidate(
                name=review.name,
                address=review.address.strip(),
                latitude=float(review.latitude),
                longitude=float(review.longitude),
                source="reviewed_evidence_fixture",
                raw_sha256=hashlib.sha256(
                    f"{review.reviewer}\x1f{review.evidence_reference}".encode("utf-8")
                ).hexdigest(),
                source_url=review.source_url or UNKNOWN_PROVENANCE,
                retrieved_at=review.retrieved_at or UNKNOWN_PROVENANCE,
                raw_reference=review.evidence_reference.strip() or UNKNOWN_PROVENANCE,
                evidence_reference=review.evidence_reference.strip(),
            ),
            provenance=rejected + [_reviewed_row(review, selected=True, decision="selected")],
        )


def _reviewed_row(
    review: ReviewedEvidence,
    *,
    selected: bool = False,
    decision: str,
) -> Dict[str, Any]:
    reference = (
        review.evidence_reference.strip() if isinstance(review.evidence_reference, str) else ""
    )
    return _provenance_row(
        source="reviewed_evidence_fixture",
        source_url=review.source_url,
        retrieved_at=review.retrieved_at,
        raw_reference=reference or UNKNOWN_PROVENANCE,
        raw_sha256=hashlib.sha256(
            f"{review.reviewer}\x1f{review.evidence_reference}".encode("utf-8")
        ).hexdigest(),
        name=review.name,
        address=review.address.strip() if isinstance(review.address, str) else "",
        latitude=_json_number(review.latitude),
        longitude=_json_number(review.longitude),
        selected=selected,
        match_decision=decision,
        extra={
            "reviewer": review.reviewer,
            "evidence_reference": reference or UNKNOWN_PROVENANCE,
        },
    )
