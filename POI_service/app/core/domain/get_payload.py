import math
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field, field_validator, model_serializer

from app.core.domain.graph_entities import SourceMetadata
from app.core.domain.source_scope import SourceContext


def _omit_absent_source_evidence(data: Dict[str, Any]) -> Dict[str, Any]:
    """Keep the provenance-free read shape byte-compatible.

    Optional evidence keys are only emitted when there is something truthful to
    say. A provenance-free record must not gain null fields in the MCP payload.
    """
    if data.get("source_metadata") is None:
        data.pop("source_metadata", None)
    if data.get("administrative_scope") is None:
        data.pop("administrative_scope", None)
    if data.get("source_metadata_status") == "missing":
        data.pop("source_metadata_status", None)
    if data.get("source_context") is None:
        data.pop("source_context", None)
    return data


def _strict_nonnegative(value: Any) -> Optional[float]:
    """Accept only real finite nonnegative numbers (reject bools/strings/NaN)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or value < 0:
        return None
    return float(value)


def _nonblank(value: Any) -> Optional[str]:
    """Return a stripped nonblank ``str`` or ``None`` (rejects bools/ints/lists)."""
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


class ReviewDetail(BaseModel):
    # A rating is only surfaced when it is a real finite nonnegative number.
    # The Document-RAG fallback ``0.0`` must not be presented as a rating, so
    # ``None`` is the truthful representation of "no rating available".
    rating: Optional[float] = Field(
        default=None, description="Average rating of the POI, null when unavailable"
    )
    review: str = Field(default="", description="A summarized review text")

    @field_validator("rating", mode="before")
    @classmethod
    def validate_rating(cls, v: Optional[float]) -> Optional[float]:
        return _strict_nonnegative(v)


class POIDescription(BaseModel):
    insight: str = Field(default="", description="Key insights or vibe of the POI")
    seo_article: str = Field(default="", description="SEO optimized descriptive text")
    review: ReviewDetail = Field(default_factory=ReviewDetail)
    # Explicit provenance for the description block. When the Document RAG is
    # missing or fails, ``status`` is ``"unavailable"`` and ``review.rating`` is
    # ``None`` -- never an invented ``0``.
    status: str = Field(
        default="available", description="available | unavailable"
    )


class POIContactInfo(BaseModel):
    website: Optional[str] = ""
    fanpage: Optional[str] = ""
    phonenumber: Optional[str] = ""


class POILite(BaseModel):
    id: str
    name: str
    full_address: Optional[str] = "Address not specified"
    categories: List[str] = []
    operation_time: Optional[str] = "Hours not specified"
    offers: List[str] = []  # Example format: ["Iced Latte (2.5)", "Croissant (1.5)"]


class CategoryRef(BaseModel):
    """A category reference that keeps its explicit graph ``id``."""

    id: Optional[str] = None
    name: Optional[str] = None
    context: Optional[str] = None


class SourceEvidenceSummary(BaseModel):
    """Compact, AI-facing provenance evidence.

    The full typed ``SourceMetadata`` (including the raw lineage blob) remains
    the graph/CRUD representation. MCP details and compound output use this
    smaller projection so the raw feature body is not repeated into model
    context; traceability is retained through the hashes and the stored-property
    reference.
    """

    dataset_namespace: str
    identity_scope: str
    cross_export_matching: str
    administrative_scope: str
    input_sha256: str
    feature_sha256: str
    canonical_source_index: int
    duplicate_source_indices: List[int] = []
    internal_record_id: str
    provided_at: date
    collection_time: Optional[str] = None
    source_url: Optional[str] = None
    license: Optional[str] = None
    freshness: Optional[str] = None
    raw_lineage_sha256: str
    raw_lineage_reference: str

    @classmethod
    def from_metadata(cls, metadata: SourceMetadata) -> "SourceEvidenceSummary":
        return cls(
            dataset_namespace=metadata.dataset_namespace,
            identity_scope=metadata.identity_scope,
            cross_export_matching=metadata.cross_export_matching,
            administrative_scope=metadata.administrative_scope,
            input_sha256=metadata.input_sha256,
            feature_sha256=metadata.feature_sha256,
            canonical_source_index=metadata.canonical_source_index,
            duplicate_source_indices=list(metadata.duplicate_source_indices),
            internal_record_id=metadata.internal_record_id,
            provided_at=metadata.provided_at,
            collection_time=metadata.collection_time,
            source_url=metadata.source_url,
            license=metadata.license,
            freshness=metadata.freshness,
            raw_lineage_sha256=metadata.raw_lineage_sha256,
            raw_lineage_reference=(
                "graph:POI.source_metadata_json#"
                f"{metadata.raw_lineage_sha256}"
            ),
        )


class AdministrativeContext(BaseModel):
    """Structured parent geography of a POI, taken from graph relationships.

    Every field is nullable so a missing or ambiguous parent chain is reported
    truthfully instead of being inferred from free-form address text or from the
    ids the caller requested.
    """

    city_id: Optional[str] = None
    district_id: Optional[str] = None
    city_name: Optional[str] = None
    district_name: Optional[str] = None


class NearbyPOI(BaseModel):
    poi: POILite
    # Distance is optional: a missing distance is ``None`` (omitted), never a
    # fabricated ``0``.
    distance: Optional[float] = Field(
        default=None, description="Spatial distance in kilometers or meters"
    )

    @field_validator("distance", mode="before")
    @classmethod
    def validate_distance(cls, v: Optional[float]) -> Optional[float]:
        return _strict_nonnegative(v)


class OfferLite(BaseModel):
    # Missing name/price stays ``None``. No "Unnamed Product" placeholder and no
    # fabricated free (``0.0``) price is ever emitted.
    name: Optional[str] = Field(default=None)
    price: Optional[float] = Field(default=None)

    @field_validator("price", mode="before")
    @classmethod
    def validate_price(cls, v: Optional[float]) -> Optional[float]:
        return _strict_nonnegative(v)


class POICompoundLite(BaseModel):
    """Token-optimised exploration item with structured ids and parent context."""

    id: str
    name: Optional[str] = None
    full_address: Optional[str] = None
    operation_time: Optional[str] = None
    categories: List[CategoryRef] = []
    offers: List[OfferLite] = []
    administrative_context: Optional[AdministrativeContext] = None
    administrative_context_status: str = "missing"

    # Optional source evidence. When absent these keys are omitted from the
    # emitted payload rather than rendered as null.
    source_metadata: Optional[SourceEvidenceSummary] = None
    source_metadata_status: str = "missing"
    source_context: Optional[SourceContext] = None
    administrative_scope: Optional[str] = None

    @model_serializer(mode="wrap")
    def _serialize_source_evidence(self, handler):
        return _omit_absent_source_evidence(handler(self))


class POIResult(BaseModel):
    POI_ID: str
    POI_Name: str
    POI_Address: Optional[str] = None
    POI_Category: Optional[str] = None

    # Coordinates are exposed to the AI but may be genuinely absent.
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    operation_time: Optional[str] = None

    POI_Description: "POIDescription"
    POI_Contact_Info: "POIContactInfo"

    # The unrolled graph edges
    Offers: List["OfferLite"] = []
    NEAR_BY: List["NearbyPOI"] = []

    # Structured parent geography (see grounding.poi_scope_status).
    administrative_context: Optional["AdministrativeContext"] = None
    administrative_context_status: str = "missing"

    # Optional source evidence. For ``source_snapshot_area_only`` records the
    # address is a source display claim and the context status is explicitly
    # unverified, never a present-day jurisdiction resolution.
    source_metadata: Optional[SourceEvidenceSummary] = None
    source_metadata_status: str = "missing"
    source_context: Optional[SourceContext] = None
    administrative_scope: Optional[str] = None

    # Explicit category ids kept alongside the legacy display name.
    POI_Categories: List["CategoryRef"] = []

    # Names of fields that could not be backed by graph data.
    missing_data: List[str] = []

    @model_serializer(mode="wrap")
    def _serialize_source_evidence(self, handler):
        return _omit_absent_source_evidence(handler(self))


class POIGetResponse(BaseModel):
    success: bool = Field(default=True)
    result: "POIResult"


def resolve_administrative_context(
    chains: Any,
) -> Tuple[Optional[Dict[str, str]], str]:
    """Resolve a POI's parent city/district from raw graph relationship chains.

    ``chains`` is a list of candidate ``{city_id, district_id, city_name,
    district_name}`` maps gathered from *both* supported graph shapes:

    * ``(p)-[:LOCATE_AT]->(district)-[:IN_CITY]->(city)``
    * ``(p)-[:LOCATE_AT]->(street)-[:IN_DISTRICT]->(district)-[:IN_CITY]->(city)``

    A chain only counts when all four values are nonblank strings. The result is
    ``(context, "resolved")`` when exactly one distinct, complete chain exists;
    otherwise ``(None, status)`` with ``missing``/``incomplete``/``ambiguous``.
    Contradictory parent chains are never collapsed to the first arbitrary one.
    """
    if not isinstance(chains, list):
        return None, "missing"

    usable: List[Tuple[str, str, str, str]] = []
    for chain in chains:
        if not isinstance(chain, dict):
            continue
        city_id = _nonblank(chain.get("city_id"))
        district_id = _nonblank(chain.get("district_id"))
        city_name = _nonblank(chain.get("city_name"))
        district_name = _nonblank(chain.get("district_name"))
        if city_id and district_id and city_name and district_name:
            usable.append((city_id, district_id, city_name, district_name))

    distinct: List[Tuple[str, str, str, str]] = []
    for item in usable:
        if item not in distinct:
            distinct.append(item)

    if len(distinct) == 1:
        city_id, district_id, city_name, district_name = distinct[0]
        return (
            {
                "city_id": city_id,
                "district_id": district_id,
                "city_name": city_name,
                "district_name": district_name,
            },
            "resolved",
        )
    if not distinct:
        if usable or chains:
            return None, "incomplete"
        return None, "missing"
    return None, "ambiguous"
