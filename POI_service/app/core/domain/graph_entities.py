import difflib
import hashlib
import json
import math
import re

from datetime import date
from typing import Any, Dict, List, Literal, Optional, Tuple
import phonenumbers
from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from app.core.domain.enum import BudgetLevel, TravelPace


# Provenance is persisted as scalar node properties only (Memgraph does not
# support nested map/list-of-map property values). The canonical raw lineage
# (geometry + raw source properties) is bounded so a single record cannot
# produce an unbounded node property.
MAX_RAW_LINEAGE_BYTES = 64 * 1024
MAX_SOURCE_METADATA_BYTES = MAX_RAW_LINEAGE_BYTES + 8 * 1024
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _looks_like_misspelled_metadata_field(key: str) -> bool:
    """Catch provenance typos without rejecting unrelated legacy fields.

    A real ingestion payload may legitimately carry fields such as ``source_id``
    or ``extraction_metadata``. Only near-misses of ``source_metadata`` and the
    explicit alternative block names are treated as a misplaced provenance
    block.
    """
    lowered = key.lower()
    if lowered in {"provenance", "source_provenance", "administrative_scope"}:
        return True
    if lowered == "source_metadata":
        return False
    return (
        difflib.SequenceMatcher(None, lowered, "source_metadata").ratio() >= 0.8
    )


def canonical_json(value: Any) -> str:
    """Deterministic JSON used for both hashing and graph scalar storage.

    ``ensure_ascii=False`` keeps Vietnamese source text byte-faithful instead of
    escaping it into a different representation.
    """
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _is_nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _unknown_or_value(value: Any) -> Optional[Any]:
    if value is None or value == "UNKNOWN":
        return None
    return value


class SourceMetadata(BaseModel):
    """Optional, typed provenance for an externally supplied POI.

    This is deliberately additive: records without it remain legacy/unspecified
    and are never implicitly treated as verified. The only currently accepted
    scope is a source-snapshot area claim whose administrative labels are NOT
    present-day containment.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_namespace: str
    identity_scope: Literal["internal_local_only"]
    cross_export_matching: Literal["not_guaranteed"]
    administrative_scope: Literal["source_snapshot_area_only"]

    input_sha256: str
    feature_sha256: str
    canonical_source_index: int
    duplicate_source_indices: List[int] = Field(default_factory=list)
    internal_record_id: str
    provided_at: date

    # Unknown upstream facts stay null (or the explicit literal "UNKNOWN").
    collection_time: Optional[str] = None
    source_url: Optional[str] = None
    license: Optional[str] = None
    freshness: Optional[str] = None

    # Full bounded raw lineage (the canonical lineage row) and its binding hash.
    raw_lineage_json: str
    raw_lineage_sha256: str

    @field_validator("dataset_namespace", "internal_record_id")
    @classmethod
    def _nonblank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Field cannot be blank.")
        return cleaned

    @field_validator("input_sha256", "feature_sha256", "raw_lineage_sha256")
    @classmethod
    def _malformed_hash(cls, value: str) -> str:
        if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
            raise ValueError("Expected a lowercase 64-character SHA256 hex digest.")
        return value

    @field_validator("canonical_source_index", mode="before")
    @classmethod
    def _reject_bad_index(cls, value: Any) -> int:
        if not _is_nonnegative_int(value):
            raise ValueError(
                "canonical_source_index must be a nonnegative integer (bools rejected)."
            )
        return value

    @field_validator("duplicate_source_indices", mode="before")
    @classmethod
    def _reject_bad_duplicate_indices(cls, value: Any) -> List[int]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("duplicate_source_indices must be a list of integers.")
        seen = set()
        cleaned: List[int] = []
        for item in value:
            if not _is_nonnegative_int(item):
                raise ValueError(
                    "Every duplicate source index must be a nonnegative integer "
                    "(bools rejected)."
                )
            if item in seen:
                raise ValueError("Duplicate source indices must be unique.")
            seen.add(item)
            cleaned.append(item)
        return cleaned

    @field_validator("collection_time", "source_url", "license", "freshness")
    @classmethod
    def _optional_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Optional provenance text must be null or nonblank.")
        return value

    @field_validator("raw_lineage_json")
    @classmethod
    def _bounded_raw_lineage(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("raw_lineage_json must be a nonblank JSON string.")
        if len(value.encode("utf-8")) > MAX_RAW_LINEAGE_BYTES:
            raise ValueError(
                f"raw_lineage_json exceeds the {MAX_RAW_LINEAGE_BYTES}-byte limit."
            )
        return value

    def parsed_lineage(self) -> Dict[str, Any]:
        """Return the raw lineage object, validating canonical form and hash."""
        try:
            row = json.loads(self.raw_lineage_json)
        except (TypeError, ValueError) as exc:
            raise ValueError("raw_lineage_json is not valid JSON.") from exc
        if not isinstance(row, dict):
            raise ValueError("raw_lineage_json must encode a JSON object.")
        if canonical_json(row) != self.raw_lineage_json:
            raise ValueError("raw_lineage_json is not canonical (sorted/compact).")
        if _sha256_text(self.raw_lineage_json) != self.raw_lineage_sha256:
            raise ValueError("raw_lineage_sha256 does not match raw_lineage_json.")
        return row

    def _validate_source_feature(self, source: Dict[str, Any]) -> None:
        """Require the actual full source feature body and its own hash recipe.

        ``feature_sha256`` is NOT the compact raw-lineage JSON hash. It follows
        the frozen preparation recipe:
        ``sha256(json.dumps(feature, sort_keys=True, ensure_ascii=False))`` with
        default (spaced) separators over ``type``/``properties``/``geometry``.
        """
        geometry = source.get("geometry")
        properties = source.get("raw_properties")
        if not isinstance(geometry, dict) or not geometry:
            raise ValueError(
                "raw lineage must include the full source geometry object."
            )
        if not isinstance(properties, dict) or not properties:
            raise ValueError(
                "raw lineage must include the full source raw_properties object."
            )
        if geometry.get("type") != "Point":
            raise ValueError("source geometry must be a finite Point.")

        coordinates = geometry.get("coordinates")
        if not (isinstance(coordinates, list) and len(coordinates) == 2):
            raise ValueError(
                "source geometry coordinates must be [longitude, latitude]."
            )
        longitude, latitude = coordinates
        if not (_is_finite_number(longitude) and _is_finite_number(latitude)):
            raise ValueError(
                "source geometry coordinates must be finite numbers (bools rejected)."
            )
        if not (-180.0 <= longitude <= 180.0 and -90.0 <= latitude <= 90.0):
            raise ValueError("source geometry coordinates are out of range.")

        # Where source properties repeat coordinates, they must agree.
        for key, expected, low, high in (
            ("lon", longitude, -180.0, 180.0),
            ("lat", latitude, -90.0, 90.0),
        ):
            if key not in properties:
                continue
            value = properties[key]
            if not _is_finite_number(value) or not (low <= value <= high):
                raise ValueError(
                    f"source raw_properties.{key} is not a finite in-range number."
                )
            if not math.isclose(
                float(value), float(expected), rel_tol=0.0, abs_tol=1e-9
            ):
                raise ValueError(
                    f"source raw_properties.{key} contradicts the geometry coordinate."
                )

        feature = {
            "type": "Feature",
            "properties": properties,
            "geometry": geometry,
        }
        material = json.dumps(feature, sort_keys=True, ensure_ascii=False)
        actual = hashlib.sha256(material.encode("utf-8")).hexdigest()
        if actual != self.feature_sha256:
            raise ValueError(
                "feature_sha256 does not match the actual source feature body."
            )

    @model_validator(mode="after")
    def _validate_bindings(self) -> "SourceMetadata":
        row = self.parsed_lineage()
        identity = row.get("identity")
        source = row.get("source")
        address = row.get("address")
        provenance = row.get("provenance")
        if not isinstance(identity, dict):
            raise ValueError("raw lineage has no identity object.")
        if not isinstance(source, dict):
            raise ValueError("raw lineage has no source object.")
        if not isinstance(address, dict):
            raise ValueError("raw lineage has no address object.")
        if not isinstance(provenance, dict):
            raise ValueError("raw lineage has no provenance object.")

        self._validate_source_feature(source)
        if not _is_nonnegative_int(source.get("canonical_source_index")):
            raise ValueError(
                "raw lineage source.canonical_source_index must be a nonnegative "
                "integer (bools rejected)."
            )

        expected = {
            "identity.namespace": (identity.get("namespace"), self.dataset_namespace),
            "identity.identity_scope": (
                identity.get("identity_scope"),
                self.identity_scope,
            ),
            "identity.cross_export_matching": (
                identity.get("cross_export_matching"),
                self.cross_export_matching,
            ),
            "source.input_sha256": (source.get("input_sha256"), self.input_sha256),
            "source.exact_feature_hash": (
                source.get("exact_feature_hash"),
                self.feature_sha256,
            ),
            "source.canonical_source_index": (
                source.get("canonical_source_index"),
                self.canonical_source_index,
            ),
            "internal_record_id": (
                row.get("internal_record_id"),
                self.internal_record_id,
            ),
            "address.scope": (address.get("scope"), self.administrative_scope),
            "address.current_admin_claim": (address.get("current_admin_claim"), "none"),
            "provenance.provided_at": (
                provenance.get("provided_at"),
                self.provided_at.isoformat(),
            ),
        }
        for label, (actual, wanted) in expected.items():
            if actual != wanted:
                raise ValueError(
                    f"source_metadata binding mismatch for {label}: "
                    f"raw lineage has {actual!r}, metadata has {wanted!r}."
                )

        for field in ("collection_time", "source_url", "license", "freshness"):
            if _unknown_or_value(provenance.get(field)) != _unknown_or_value(
                getattr(self, field)
            ):
                raise ValueError(
                    f"source_metadata binding mismatch for provenance.{field}."
                )

        if self.canonical_source_index in self.duplicate_source_indices:
            raise ValueError(
                "canonical_source_index cannot also be listed as a duplicate index."
            )

        canonical_metadata = canonical_json(self.model_dump(mode="json"))
        if len(canonical_metadata.encode("utf-8")) > MAX_SOURCE_METADATA_BYTES:
            raise ValueError(
                "Canonical source metadata exceeds the "
                f"{MAX_SOURCE_METADATA_BYTES}-byte storage limit."
            )
        return self

    def assert_bound_to_poi(self, poi_id: str) -> None:
        """Reject metadata copied from a different record."""
        row = self.parsed_lineage()
        if row.get("id") != poi_id:
            raise ValueError(
                "source_metadata raw lineage id does not match the POI id "
                f"({row.get('id')!r} != {poi_id!r})."
            )


def canonical_source_metadata_json(metadata: SourceMetadata) -> str:
    """Canonical scalar representation persisted on the POI node."""
    return canonical_json(metadata.model_dump(mode="json"))


def decode_source_metadata(
    raw: Any, expected_sha256: Optional[str] = None
) -> Tuple[Optional[SourceMetadata], str]:
    """Decode stored provenance without ever silently promoting corruption.

    Returns ``(metadata, status)`` where ``status`` is ``valid``, ``missing`` or
    ``corrupt``. A corrupt value is explicitly reported and never returned as a
    trusted typed model.
    """
    if raw is None:
        return None, "missing"
    if isinstance(raw, str) and not raw.strip():
        return None, "missing"
    try:
        if isinstance(raw, str):
            payload = json.loads(raw)
        elif isinstance(raw, dict):
            payload = raw
        else:
            return None, "corrupt"
        metadata = SourceMetadata.model_validate(payload)
        if expected_sha256 is not None:
            if not isinstance(expected_sha256, str):
                return None, "corrupt"
            actual = _sha256_text(canonical_source_metadata_json(metadata))
            if actual != expected_sha256:
                return None, "corrupt"
    except Exception:
        return None, "corrupt"
    return metadata, "valid"


class Category(BaseModel):
    id: str = Field(..., min_length=1, description="Unique identifier for the category")
    name: str = Field(..., min_length=1, description="Display name of the category")
    context: str = Field(..., description="Semantic context for the AI agent")

    @field_validator('id', 'name')
    @classmethod
    def sanitize_basic_strings(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Field cannot consist only of whitespace.")
        return cleaned

    @field_validator('context')
    @classmethod
    def validate_context(cls, v: str) -> str:
        cleaned_context = re.sub(r'\s+', ' ', v).strip()
        if not cleaned_context:
            raise ValueError("Category context cannot be empty.")
            
        word_count = len(cleaned_context.split())
        if word_count >= 400:
            raise ValueError(f"Category context must be under 400 words. Current count: {word_count}.")
            
        return cleaned_context


class Tag(BaseModel):
    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)

    @field_validator('id', 'name')
    @classmethod
    def sanitize_tag_strings(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Tag fields cannot be empty or just whitespace.")
        return cleaned


class UserPreference(BaseModel):
    user_id: str
    category_weights: Dict[str, float] = Field(default_factory=dict)
    tag_weights: Dict[str, float] = Field(default_factory=dict)
    daily_budget: Optional[float] = Field(None, description="Exact target spending per day")
    budget_level: BudgetLevel = Field(
        default=BudgetLevel.STANDARD,
        description="The classified budget tier that dictates price filtering."
    )
    travel_pace: TravelPace = Field(
        default=TravelPace.MODERATE,
        description="The preferred speed of travel, dictating how long the user stays at each POI."
    )
    dietary_restrictions: List[str] = Field(default_factory=list)
    requires_accessibility: bool = False
    personal_vibe: Optional[str] = Field(None)

    @model_validator(mode='after')
    def assign_budget_bin(self) -> 'UserPreference':
        if self.daily_budget is not None:
            if self.daily_budget < 50.0:
                self.budget_level = BudgetLevel.BUDGET
            elif self.daily_budget <= 150.0:
                self.budget_level = BudgetLevel.STANDARD
            else:
                self.budget_level = BudgetLevel.LUXURY
        return self


class Address(BaseModel):
    street_name: Optional[str] = None
    district: str = Field(..., min_length=1)
    ward: Optional[str] = None
    city: str = Field(..., min_length=1)
    nation: str = Field(default="Vietnam", min_length=1)

    @field_validator('street_name', 'district', 'ward', 'city', 'nation')
    @classmethod
    def sanitize_address_fields(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return v
        cleaned = re.sub(r'\s+', ' ', v).strip()
        if not cleaned:
            raise ValueError("Address fields cannot consist only of whitespace.")
        return cleaned.title()


class Product(BaseModel):
    id: str = Field(..., min_length=1)
    product_name: str = Field(..., min_length=1, max_length=200)
    price: float = Field(..., ge=0.0)

    @field_validator('product_name')
    @classmethod
    def sanitize_product_name(cls, v: str) -> str:
        cleaned_name = re.sub(r'\s+', ' ', v).strip()
        if not cleaned_name:
            raise ValueError("Product name cannot consist only of whitespace.")
        return cleaned_name
        
    @field_validator('id')
    @classmethod
    def sanitize_id(cls, v: str) -> str:
        cleaned_id = v.strip()
        if not cleaned_id:
             raise ValueError("Product ID cannot be empty.")
        return cleaned_id


class ContactInfo(BaseModel):
    email: EmailStr | None = None
    phone_number: Optional[str] = None
    
    # FIX: Changed from HttpUrl to str to prevent crashes on bad data like "Imported from GIS"
    fanpage: Optional[str] = None
    website: Optional[str] = None

    # FIX: Added mode="before" to intercept None before phonenumbers tries to parse it
    @field_validator('phone_number', mode='before')
    @classmethod
    def validate_and_format_phone(cls, v: Optional[str]) -> Optional[str]:
        if not v or str(v).lower() == "none": 
            return None
            
        try:
            parsed_number = phonenumbers.parse(v, "VN")
            if not phonenumbers.is_valid_number(parsed_number):
                return None # Fail gracefully, keep the POI alive
            
            return phonenumbers.format_number(
                parsed_number, 
                phonenumbers.PhoneNumberFormat.E164
            )
        except Exception:
            # If it's a completely garbled string, just ignore it
            return None
            
    # FIX: Removed the ensure_data_exists model_validator! 
    # Sparse GIS data is fine, an empty ContactInfo object shouldn't crash the API.


class POI(BaseModel):
    id: str
    name: str
    poi_categories: List[Category] = Field(default_factory=list)
    tag: Optional[Tag] = None
    longitude: float
    latitude: float
    
    # FIX: Address is now entirely optional
    address: Optional[Address] = None
    contact_info: Optional[ContactInfo] = None
    
    # FIX: Operation time can be missing
    operation_time: Optional[str] = None
    rating: Optional[Dict] = None
    
    # FIX: Default factory for list
    menu: List[Product] = Field(default_factory=list)

    # Optional typed provenance. ``None`` means legacy/unspecified, never
    # "verified": absence must not be read as a trust upgrade.
    source_metadata: Optional[SourceMetadata] = None

    @model_validator(mode="before")
    @classmethod
    def reject_unrecognized_metadata_fields(cls, data: Any) -> Any:
        """Refuse a misspelled provenance block instead of silently ignoring it."""
        if isinstance(data, dict):
            for key in data:
                if not isinstance(key, str) or key in cls.model_fields:
                    continue
                if _looks_like_misspelled_metadata_field(key):
                    raise ValueError(
                        f"Unrecognized provenance/metadata field {key!r}; "
                        "use the explicit 'source_metadata' object."
                    )
        return data

    @field_validator("source_metadata", mode="before")
    @classmethod
    def decode_stored_source_metadata(cls, value: Any) -> Any:
        """Accept the scalar JSON stored on a graph node while validating it."""
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (TypeError, ValueError) as exc:
                raise ValueError("Stored source_metadata is not valid JSON.") from exc
        return value

    @model_validator(mode="after")
    def bind_source_metadata_to_identity(self) -> "POI":
        if self.source_metadata is not None:
            self.source_metadata.assert_bound_to_poi(self.id)
        return self

    # FIX: An explicit identifier is immutable. Blank identifiers are rejected at
    # this trusted boundary instead of being replaced by an uncertain generated
    # key; acquisition must supply stable source-derived identifiers.
    @field_validator("id")
    @classmethod
    def validate_explicit_identifier(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError(
                "POI id must be supplied and cannot be blank; a stable "
                "source-derived identifier is required."
            )
        return v

    # FIX: Names are trimmed safely and may never be blank.
    @field_validator("name")
    @classmethod
    def sanitize_poi_name(cls, v: str) -> str:
        cleaned_name = v.strip()
        if not cleaned_name:
            raise ValueError("POI name cannot be blank.")
        return cleaned_name

    @field_validator("latitude")
    @classmethod
    def validate_latitude(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("POI latitude must be a finite number.")
        if not -90.0 <= v <= 90.0:
            raise ValueError("POI latitude must be within [-90, 90].")
        return v

    @field_validator("longitude")
    @classmethod
    def validate_longitude(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("POI longitude must be a finite number.")
        if not -180.0 <= v <= 180.0:
            raise ValueError("POI longitude must be within [-180, 180].")
        return v

    # FIX: Catches explicit `null` from JSON and turns it into []
    @field_validator("menu", mode="before")
    @classmethod
    def ensure_menu_is_list(cls, v):
        if v is None:
            return []
        return v


class Description(BaseModel):
    poi_id: str
    review_id: str 
    summary_id: str
    seo_doc_id: str
    faq: Dict

class POILite(BaseModel):
    id: str
    name: str
    full_address: Optional[str] = "Address not specified"
    categories: List[str] = []
    operation_time: Optional[str] = "Hours not specified"