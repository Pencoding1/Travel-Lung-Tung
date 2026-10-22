import re

from collections import OrderedDict
from typing import List, Dict, Any, Literal, Optional, Union
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_serializer,
    model_validator,
)


class _BoundedChatHistory(OrderedDict):
    """Deprecated compatibility mapping.

    The previous global ``chat_history`` grew without bound. This bounded
    ``OrderedDict`` keeps the module-level name importable for existing callers
    while evicting the oldest sessions (LRU) once the cap is exceeded. New code
    should use ``domains.memory.WorkingMemory`` instead.
    """

    def __init__(self, max_entries: int = 128):
        super().__init__()
        self._max_entries = max_entries

    def __setitem__(self, key, value):
        if key in self:
            self.move_to_end(key)
        super().__setitem__(key, value)
        while len(self) > self._max_entries:
            self.popitem(last=False)


chat_history: Dict[str, List[Dict[str, Any]]] = _BoundedChatHistory()


MAX_SESSION_ID_CHARS = 200
MAX_USER_MESSAGE_CHARS = 8000


TRANSPORT_MODES = ("car", "foot")


def _strict_transport_mode(value):
    """Reject null/bool/number/object/list/whitespace/case variants exactly.

    Shared by both request types so the chat surface and the itinerary surface
    accept the same two literal values and nothing else, before any model or
    MCP call is reached.
    """
    if type(value) is not str or value not in TRANSPORT_MODES:
        raise ValueError("transport_mode must be exactly 'car' or 'foot'.")
    return value


class ClearMemoryRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=MAX_SESSION_ID_CHARS)


SOURCE_AREA_ID_RE = re.compile(r"^source_area_v1:[0-9a-f]{64}$")
SOURCE_INPUT_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SOURCE_AREA_IDS_MAX = 64


class SourceScopeSelection(BaseModel):
    """Strict explicit source-snapshot selection (T049 AI boundary).

    Its *presence* is the only source-mode switch. Values are kept byte-exact:
    the server's discovery output is canonical, so a padded namespace is
    rejected instead of being silently trimmed into a different selector.
    ``strict=True`` also rejects bool/numeric coercion for every field.

    Exactly one selector is present: legacy ``source_area_id`` or the alternate
    ``source_area_ids`` list. Multi ids are canonicalised (sorted); duplicates
    and global sentinels are rejected. Unused selector fields are omitted from
    serialisation so one-area payloads keep their legacy three-key shape.
    """

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    dataset_namespace: str
    input_sha256: str
    source_area_id: Optional[str] = None
    source_area_ids: Optional[List[str]] = None

    @model_validator(mode="before")
    @classmethod
    def _exactly_one_selector(cls, data):
        if not isinstance(data, dict):
            return data
        has_single = "source_area_id" in data
        has_multi = "source_area_ids" in data
        if has_single == has_multi:
            raise ValueError(
                "exactly one of source_area_id or source_area_ids is required."
            )
        key = "source_area_id" if has_single else "source_area_ids"
        if data.get(key) is None:
            raise ValueError(f"{key} must not be null.")
        return data

    @field_validator("dataset_namespace")
    @classmethod
    def _namespace(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("dataset_namespace must be a nonblank string.")
        if value != value.strip():
            raise ValueError(
                "dataset_namespace must not have leading/trailing whitespace."
            )
        return value

    @field_validator("input_sha256")
    @classmethod
    def _input_sha256(cls, value: str) -> str:
        if not SOURCE_INPUT_SHA256_RE.fullmatch(value):
            raise ValueError(
                "input_sha256 must be a lowercase 64-character SHA256 hex digest."
            )
        return value

    @field_validator("source_area_id")
    @classmethod
    def _source_area_id(cls, value: str) -> str:
        if not SOURCE_AREA_ID_RE.fullmatch(value):
            raise ValueError(
                "source_area_id must use source_area_v1:<64 lowercase hex>; "
                "current administrative ids are not source selectors."
            )
        return value

    @field_validator("source_area_ids")
    @classmethod
    def _source_area_ids(cls, value: List[str]) -> List[str]:
        if not isinstance(value, list):
            raise ValueError("source_area_ids must be a list of source area ids.")
        if not (1 <= len(value) <= SOURCE_AREA_IDS_MAX):
            raise ValueError(
                f"source_area_ids must contain 1..{SOURCE_AREA_IDS_MAX} ids."
            )
        for item in value:
            if not isinstance(item, str) or not SOURCE_AREA_ID_RE.fullmatch(item):
                raise ValueError(
                    "every source_area_ids entry must use the "
                    "source_area_v1:<64 lowercase hex> form."
                )
        if len(set(value)) != len(value):
            raise ValueError("source_area_ids must not contain duplicates.")
        return sorted(value)

    @model_serializer(mode="wrap")
    def _omit_unused_selector(self, handler):
        """Drop the unused selector on every serialisation path.

        A ``model_dump`` method override only ran for a direct call; Pydantic
        nested serialisation (``ChatRequest``/``ItineraryRequest``) bypassed it
        and emitted the unset selector as ``null``. A wrap serializer runs for
        direct, nested, Python and JSON dumps alike, while leaving the caller's
        ``include``/``exclude``/``by_alias`` semantics intact.
        """
        data = handler(self)
        if not isinstance(data, dict):
            return data
        unused = ("source_area_ids" if self.source_area_id is not None
                  else "source_area_id")
        data.pop(unused, None)
        return data

    @property
    def area_ids(self):
        """The selected concrete ids, never a global sentinel."""
        if self.source_area_ids is not None:
            return tuple(self.source_area_ids)
        return (self.source_area_id,) if self.source_area_id else ()


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=MAX_SESSION_ID_CHARS)
    message: str = Field(min_length=1, max_length=MAX_USER_MESSAGE_CHARS)
    # Controlled-experiment switch: when false, neither short- nor long-term
    # memory affects the prompt beyond the current turn.
    memory_enabled: bool = True

    # Explicit single-mode transport request for chat tool calls (CORE-069).
    # ``car`` is the same backward-compatibility default the itinerary surface
    # uses; the server records whether the caller was explicit.
    transport_mode: Literal["car", "foot"] = "car"

    # Explicit source-snapshot selection (CORE-069). Absent preserves the legacy
    # current-administration chat unchanged; a present, valid selection is the
    # only switch that activates source-scoped chat tools.
    source_scope: Optional[SourceScopeSelection] = None

    @field_validator("transport_mode", mode="before")
    @classmethod
    def _transport_mode_strict(cls, value):
        return _strict_transport_mode(value)


class ItineraryRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=MAX_SESSION_ID_CHARS)
    current_city: str = "Ho Chi Minh City"
    travel_type: str  # e.g., "self-explore, relaxing, sightseeing"
    num_travelers: int = Field(ge=1, le=50)
    start_date: str = Field(description="ISO date, e.g. 2026-01-01")
    target_district: Optional[str] = None
    duration_days: int = Field(ge=1, le=14)
    budget_range: str
    user_description: str
    memory_enabled: bool = True

    # Explicit single-mode transport request. ``car`` is a backward-compatibility
    # policy default, not an inferred or user-confirmed choice; the planner
    # records whether the value was explicit or defaulted. Only these two exact
    # values are accepted (never trimmed, case-folded or coerced).
    transport_mode: Literal["car", "foot"] = "car"

    # Explicit source-snapshot mode. ``None`` preserves the legacy
    # current-administration request unchanged; a present, valid selection is
    # the *only* way to activate source mode.
    source_scope: Optional[SourceScopeSelection] = None

    # --- Optional typed planning constraints (OC-016) ---------------------
    # All optional; existing free-form fields remain usable. When absent, the
    # planner records the corresponding assumption/unknown instead of guessing.
    budget_amount: Optional[Union[int, str]] = None
    budget_currency: Optional[str] = None
    budget_unit: Optional[str] = None  # per_party | per_person
    minimum_stops: Optional[int] = Field(default=None, ge=0)
    maximum_stops: Optional[int] = Field(default=None, ge=1)
    visit_minutes: Optional[int] = Field(default=None, ge=1, le=24 * 60)
    day_windows: Optional[List[Dict[str, Any]]] = None
    required_categories: Optional[List[str]] = None
    meal_windows: Optional[List[Dict[str, Any]]] = None

    @field_validator("transport_mode", mode="before")
    @classmethod
    def _transport_mode_strict(cls, value):
        # Explicit strictness on top of ``Literal``: reject null/bool/number/
        # object/list and any whitespace/case/unsupported variant before any
        # model or MCP call is reached.
        return _strict_transport_mode(value)

    @model_validator(mode="after")
    def _target_district_required_without_source_scope(self):
        if self.source_scope is None:
            if not isinstance(self.target_district, str) \
                    or not self.target_district.strip():
                raise ValueError(
                    "target_district is required unless an explicit source_scope "
                    "selection is supplied."
                )
        return self
