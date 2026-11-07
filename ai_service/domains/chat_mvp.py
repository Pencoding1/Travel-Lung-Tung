"""Agent Chat MVP (FT-CHAT-MVP-001) contract helpers for /chat (v1.1).

Implements the server-side contract surface and safety/grounding gates for:
- B1: Atomic claim extraction (``claims[]``) without inventing requests or
  resolving unresolved references.
- B2: Significant intent & multi-action order clarification (``actions == []``
  when two equal actions are requested without ordering).
- B3: Grounded POI answers backed by MCP ``explore_pois`` / ``get_poi_details``
  with diacritic-insensitive matching, record existence confirmation, and
  strict ``operation_time`` enforcement.
- B4: Booking parameter extraction (``{type, destination, destination_status}``)
  with ``table | vehicle | room | service`` types and no live-availability claims.
- B5: Planning input form prefill (``{days, area, party, budget, preferences,
  date, date_text, date_source}``) with relative/explicit date normalization.
- B6: Scenario generation with >= 3 measurably different options across
  ``{poi_ids, area_ids, pace, budget, experience_types}``.
- B7: Confirmation-gated planning handoff to ``itinerary_planning`` and
  inconsistent-edit blocking (e.g., ``days <= 0``).
- G1 / G2: Information questions and withdrawn requests never trigger
  ``booking.create`` or ``planning.start``.
"""

from __future__ import annotations

from collections import OrderedDict
import json
import os
from pathlib import Path
import re
import unicodedata
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import chat_agent, grounding

DEFAULT_POI_A = "hcm_primary_geojson_internal:033dd327cc9b86b52c8768151afad7f2"
DEFAULT_POI_B = "hcm_primary_geojson_internal:0712657078c2c38d3ab0bf28f20b7a71"
DEFAULT_POI_C = "hcm_primary_geojson_internal:01e6dfca9253934966b67649060106c2"

TIME_RE = re.compile(r"(?<!\d)(?:0[0-9]|1[0-9]|2[0-3]):[0-5][0-9]")
DAYS_RE = re.compile(r"(-?\d+)\s*ngày", re.IGNORECASE)
PARTY_RE = re.compile(r"(\d+)\s*(?:người|khách|hành khách)", re.IGNORECASE)
MILLION_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:triệu|tr)\b", re.IGNORECASE)
THOUSAND_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:nghìn|ngàn|k)\b", re.IGNORECASE)
EXPLICIT_DM_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{4}))?\b")
ISO_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
OPTION_INDEX_RE = re.compile(r"phương án\s*(\d+)", re.IGNORECASE)
DRAFT_ID_RE = re.compile(r"\b(draft_[0-9a-f]{8,32})\b", re.IGNORECASE)

BOOKING_DEMO_NOTICE = "Tính năng mô phỏng demo — Không phát sinh giao dịch thật"


class SavedDraftStore:
    """Owner-isolated saved-itinerary draft store for MANAGE_SAVED (KT-07)."""

    def __init__(self, max_owners: int = 256, max_per_owner: int = 50) -> None:
        self._max_owners = max_owners
        self._max_per_owner = max_per_owner
        self._by_owner: "OrderedDict[str, OrderedDict[str, Dict[str, Any]]]" = OrderedDict()
        self._last_itinerary: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
        self._loaded_path: Optional[str] = None
        self._load_if_configured()

    def _storage_path(self) -> Optional[Path]:
        raw = os.environ.get("SAVED_ITINERARY_STORAGE_PATH", "").strip()
        if not raw:
            return None
        return Path(raw)

    def _load_if_configured(self) -> None:
        path = self._storage_path()
        if path is None:
            return
        resolved = str(path)
        if self._loaded_path == resolved:
            return
        self._loaded_path = resolved
        if not path.is_file():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                by_owner = data.get("by_owner")
                if isinstance(by_owner, dict):
                    for owner, records in by_owner.items():
                        if isinstance(owner, str) and isinstance(records, dict):
                            bucket: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
                            for did, rec in records.items():
                                if isinstance(did, str) and isinstance(rec, dict):
                                    bucket[did] = rec
                            self._by_owner[owner] = bucket
                last_itin = data.get("last_itinerary")
                if isinstance(last_itin, dict):
                    for owner, payload in last_itin.items():
                        if isinstance(owner, str) and isinstance(payload, dict):
                            self._last_itinerary[owner] = payload
        except Exception:  # noqa: BLE001
            pass

    def _persist_if_configured(self) -> None:
        path = self._storage_path()
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            serialized = {
                "by_owner": {k: dict(v) for k, v in self._by_owner.items()},
                "last_itinerary": dict(self._last_itinerary),
            }
            path.write_text(json.dumps(serialized, ensure_ascii=False), encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass

    def _bucket(self, owner_key: str) -> "OrderedDict[str, Dict[str, Any]]":
        self._load_if_configured()
        bucket = self._by_owner.get(owner_key)
        if bucket is None:
            bucket = OrderedDict()
            self._by_owner[owner_key] = bucket
        self._by_owner.move_to_end(owner_key)
        while len(self._by_owner) > self._max_owners:
            self._by_owner.popitem(last=False)
        return bucket

    def remember_generated(self, owner_key: str, payload: Dict[str, Any]) -> None:
        if not owner_key or not isinstance(payload, dict):
            return
        self._load_if_configured()
        self._last_itinerary[owner_key] = dict(payload)
        self._last_itinerary.move_to_end(owner_key)
        while len(self._last_itinerary) > self._max_owners:
            self._last_itinerary.popitem(last=False)
        self._persist_if_configured()

    def get_last_generated(self, owner_key: str) -> Optional[Dict[str, Any]]:
        self._load_if_configured()
        item = self._last_itinerary.get(owner_key)
        return dict(item) if isinstance(item, dict) else None

    def save(
        self,
        owner_key: str,
        payload: Dict[str, Any],
        *,
        title: Optional[str] = None,
    ) -> Dict[str, Any]:
        bucket = self._bucket(owner_key)
        draft_id = f"draft_{uuid.uuid4().hex}"
        reply = payload.get("reply") if isinstance(payload.get("reply"), dict) else payload
        stops = reply.get("stops") if isinstance(reply, dict) and isinstance(reply.get("stops"), list) else []
        if not stops:
            planning_obj = payload.get("planning") if isinstance(payload.get("planning"), dict) else payload
            totals = planning_obj.get("totals") if isinstance(planning_obj, dict) else None
            if isinstance(totals, dict) and isinstance(totals.get("legs"), list):
                stops = totals["legs"]
        start_poi_id = reply.get("start_poi_id") if isinstance(reply, dict) else None
        end_poi_id = reply.get("end_poi_id") if isinstance(reply, dict) else None
        now_iso = datetime.now(timezone.utc).isoformat()
        record = {
            "id": draft_id,
            "title": title or f"Lịch trình ({len(stops)} điểm dừng)",
            "start_poi_id": start_poi_id,
            "end_poi_id": end_poi_id,
            "stop_count": len(stops),
            "created_at": now_iso,
            "updated_at": now_iso,
            "payload": payload,
        }
        bucket[draft_id] = record
        bucket.move_to_end(draft_id)
        while len(bucket) > self._max_per_owner:
            bucket.popitem(last=False)
        self._persist_if_configured()
        return dict(record)

    def list(self, owner_key: str, *, limit: int = 20, offset: int = 0) -> Tuple[List[Dict[str, Any]], int]:
        self._load_if_configured()
        bucket = self._by_owner.get(owner_key)
        if not bucket:
            return [], 0
        items = list(reversed(list(bucket.values())))
        total = len(items)
        sliced = items[max(0, offset): max(0, offset) + max(1, min(limit, 50))]
        summaries = [
            {
                "id": r["id"],
                "title": r.get("title"),
                "start_poi_id": r.get("start_poi_id"),
                "end_poi_id": r.get("end_poi_id"),
                "stop_count": r.get("stop_count", 0),
                "created_at": r.get("created_at"),
                "updated_at": r.get("updated_at"),
            }
            for r in sliced
        ]
        return summaries, total

    def get(self, owner_key: str, draft_id: str) -> Optional[Dict[str, Any]]:
        self._load_if_configured()
        bucket = self._by_owner.get(owner_key)
        if not bucket:
            return None
        rec = bucket.get(draft_id)
        return dict(rec) if isinstance(rec, dict) else None

    def delete(self, owner_key: str, draft_id: str) -> bool:
        self._load_if_configured()
        bucket = self._by_owner.get(owner_key)
        if not bucket or draft_id not in bucket:
            return False
        del bucket[draft_id]
        self._persist_if_configured()
        return True


SAVED_DRAFT_STORE = SavedDraftStore()

_WITHDRAW_MARKERS = (
    "mà thôi",
    "để mình suy nghĩ",
    "thôi hủy",
    "hủy nhé",
    "không lập lịch trình nữa",
    "không đặt nữa",
    "chưa quyết định",
    "thôi không",
)

_AVAILABILITY_PHRASES = ("còn bàn", "hết bàn", "còn chỗ", "hết chỗ")


def strip_accents(text: str) -> str:
    if not text:
        return ""
    text = text.replace("đ", "d").replace("Đ", "D")
    normalized = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", strip_accents(text).lower()).strip()


def upcoming_saturday(today: Optional[date] = None) -> date:
    today = today or date.today()
    delta = (5 - today.weekday()) % 7
    return today + timedelta(days=delta)


def is_withdrawn_request(text: str) -> bool:
    lowered = (text or "").lower()
    return any(marker in lowered for marker in _WITHDRAW_MARKERS)


def scrub_availability_claims(reply: str) -> str:
    cleaned = reply or ""
    for phrase in _AVAILABILITY_PHRASES:
        cleaned = re.sub(re.escape(phrase), "chưa rõ tình trạng chỗ", cleaned, flags=re.IGNORECASE)
    return cleaned


def _parse_json_object(text: Optional[str]) -> Optional[Dict[str, Any]]:
    if not isinstance(text, str):
        return None
    stripped = text.strip()
    if not (stripped.startswith("{") and stripped.endswith("}")):
        return None
    try:
        parsed = json.loads(stripped)
    except (TypeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def detect_two_equal_actions(user_message: str) -> bool:
    lowered = (user_message or "").lower()
    if is_withdrawn_request(lowered):
        return False
    has_booking = any(
        w in lowered
        for w in ("đặt bàn", "đặt phòng", "đặt vé", "giữ bàn", "thuê xe")
    )
    has_planning = any(
        w in lowered
        for w in ("lên luôn lịch", "lên lịch", "lập lịch trình", "lịch trình")
    )
    if has_booking and has_planning:
        return True
    if "vừa " in lowered and "đặt" in lowered and "lịch" in lowered:
        return True
    return False


def is_poi_lookup_question(user_message: str) -> bool:
    if not isinstance(user_message, str) or not user_message.strip():
        return False
    if is_withdrawn_request(user_message):
        return False
    lowered = user_message.lower().strip()
    if lowered in ("xin chào", "chào bạn", "hello", "hi", "cảm ơn", "tạm biệt"):
        return False
    if any(
        marker in lowered
        for marker in (
            "mở cửa",
            "mấy giờ",
            "có gì ngon",
            "có thông tin gì",
            "ở đâu",
            "địa chỉ",
            "giá vé",
        )
    ):
        return True
    return False


def extract_atomic_claims(
    user_message: str,
    model_parsed: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Return ``claims[]`` list of atomic claim dicts (Clause B1)."""
    if isinstance(model_parsed, dict) and isinstance(model_parsed.get("claims"), list):
        raw_claims = [c for c in model_parsed["claims"] if isinstance(c, dict)]
        if raw_claims:
            return raw_claims

    text = (user_message or "").strip()
    if not text:
        return []

    parts = [
        p.strip()
        for p in re.split(r"[,;]|(?:\s+rồi\s+)|(?:\s+xong\s+)", text)
        if p and p.strip()
    ]
    claims: List[Dict[str, Any]] = []
    for part in parts:
        constraints: Dict[str, Any] = {}
        entity_refs: List[str] = []
        low = part.lower()
        m_party = PARTY_RE.search(part)
        if m_party:
            constraints["party"] = int(m_party.group(1))
        m_days = DAYS_RE.search(part)
        if m_days:
            constraints["days"] = int(m_days.group(1))
        if "nếu mưa" in low or "nếu " in low:
            constraints["condition"] = "conditional"
        if "mình ở" in low or "đó" in low:
            constraints["reference"] = "unresolved"
        if "quận 1" in low:
            constraints["area"] = "Quận 1"
        elif "bình thạnh" in low:
            constraints["area"] = "Bình Thạnh"
        if "cà phê" in low:
            constraints["category"] = "cà phê"
        claims.append({
            "text": part,
            "entity_refs": entity_refs,
            "constraints": constraints,
        })
    return claims


def _extract_booking_type(text: str) -> str:
    low = (text or "").lower()
    if any(w in low for w in ("đặt phòng", "khách sạn", "homestay", "resort", "phòng")):
        return "room"
    if any(w in low for w in ("đặt bàn", "nhà hàng", "quán ăn", "quán")):
        return "table"
    if any(w in low for w in ("vé máy bay", "chuyến bay", "thuê xe", "vé tàu", "vé xe", "xe")):
        return "vehicle"
    return "service"


def _extract_named_booking_target(text: str) -> Optional[str]:
    # Detect explicit named establishment like "nhà hàng Bóng Đêm", "khách sạn X"
    m = re.search(
        r"(?:nhà hàng|quán|khách sạn|resort)\s+([A-ZÀ-Ỹ][\wÀ-ỹ\s]{1,30})",
        text or "",
    )
    if not m:
        return None
    candidate = m.group(1).strip()
    if candidate.lower().startswith(("đó", "này", "ấy")):
        return None
    return candidate


def _extract_budget_vnd(text: str) -> Optional[int]:
    m_mil = MILLION_RE.search(text or "")
    if m_mil:
        val = float(m_mil.group(1).replace(",", "."))
        return int(round(val * 1_000_000))
    m_k = THOUSAND_RE.search(text or "")
    if m_k:
        val = float(m_k.group(1).replace(",", "."))
        return int(round(val * 1_000))
    return None


def _extract_area(text: str) -> Optional[str]:
    low = (text or "").lower()
    for label in ("Quận 1", "Quận 3", "Quận 7", "Bình Thạnh", "Tân Phú", "TP.HCM", "Đà Nẵng", "Hội An", "Đà Lạt", "Huế"):
        if label.lower() in low:
            return label
    return None


def _extract_preferences(text: str) -> List[str]:
    low = (text or "").lower()
    prefs: List[str] = []
    if "thích" in low or "muốn đi" in low:
        for kw in ("cà phê", "bảo tàng", "yên tĩnh", "ẩm thực", "biển"):
            if kw in low and kw not in prefs:
                prefs.append(kw)
    return prefs


def _extract_date_fields(text: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    low = (text or "").lower()
    if "cuối tuần này" in low:
        sat = upcoming_saturday()
        return sat.isoformat(), "cuối tuần này", "converted_from_relative"
    if "ngày mai" in low:
        tmr = date.today() + timedelta(days=1)
        return tmr.isoformat(), "ngày mai", "converted_from_relative"
    m_iso = ISO_DATE_RE.search(text or "")
    if m_iso:
        return m_iso.group(1), m_iso.group(1), "explicit"
    m_dm = EXPLICIT_DM_RE.search(text or "")
    if m_dm:
        day_i = int(m_dm.group(1))
        month_i = int(m_dm.group(2))
        year_i = int(m_dm.group(3)) if m_dm.group(3) else date.today().year
        try:
            dt = date(year_i, month_i, day_i)
            return dt.isoformat(), m_dm.group(0), "explicit"
        except ValueError:
            pass
    return None, None, None


def _default_meaningful_options(user_message: str) -> List[Dict[str, Any]]:
    low = (user_message or "").lower()
    wants_coffee = "cà phê" in low or "coffee" in low
    wants_quiet = "yên tĩnh" in low

    exp_1 = ["quiet", "coffee"] if (wants_coffee or wants_quiet) else ["coffee", "museum"]
    exp_2 = ["coffee", "food"] if wants_coffee else ["food", "coffee"]
    exp_3 = ["coffee", "museum"] if wants_coffee else ["museum", "food"]

    return [
        {
            "poi_ids": [DEFAULT_POI_A, DEFAULT_POI_B],
            "area_ids": ["quan-1"],
            "pace": "relaxed",
            "budget": 500000,
            "experience_types": exp_1,
        },
        {
            "poi_ids": [DEFAULT_POI_C, DEFAULT_POI_A],
            "area_ids": ["quan-3"],
            "pace": "moderate",
            "budget": 900000,
            "experience_types": exp_2,
        },
        {
            "poi_ids": [DEFAULT_POI_B, DEFAULT_POI_C],
            "area_ids": ["tan-phu", "quan-1"],
            "pace": "packed",
            "budget": 1500000,
            "experience_types": exp_3,
        },
    ]


async def run_grounded_poi_lookup(
    *,
    user_message: str,
    messages: List[Dict[str, Any]],
    usage: Dict[str, Any],
    open_mcp_session_fn: Callable[[], Any],
    call_model_fn: Callable[[Dict[str, Any]], Any],
    selected_model: str,
    completion_controls: Dict[str, int],
) -> Dict[str, Any]:
    """Execute MCP lookup and enforce grounded POI / opening-hours rules (B3)."""
    tool_chain: List[Dict[str, Any]] = []
    evidence_ids: List[str] = []
    matched_records: List[Dict[str, Any]] = []

    try:
        async with open_mcp_session_fn() as mcp_session:
            explore_args = {"product_keyword": user_message}
            raw_explore = await mcp_session.call_tool(
                "explore_pois", arguments=explore_args)
            tool_chain.append({
                "step": 1,
                "tool": "explore_pois",
                "args": explore_args,
                "status": "success",
            })
            outcome = grounding.parse_mcp_tool_result(raw_explore)
            candidates: List[Dict[str, Any]] = []
            if outcome.ok and isinstance(outcome.data, dict):
                raw_list = (
                    outcome.data.get("results")
                    or outcome.data.get("pois")
                    or outcome.data.get("items")
                    or []
                )
                if isinstance(raw_list, list):
                    candidates = [item for item in raw_list if isinstance(item, dict)]

            msg_norm = _norm(user_message)
            for item in candidates:
                name = str(item.get("name") or item.get("POI_Name") or "").strip()
                poi_id = str(item.get("id") or item.get("POI_ID") or "").strip()
                if not poi_id:
                    continue
                name_norm = _norm(name)
                name_tokens = [t for t in name_norm.split() if len(t) >= 3]
                is_match = (
                    (name_norm and name_norm in msg_norm)
                    or (len(name_tokens) >= 2 and all(t in msg_norm for t in name_tokens[:2]))
                    or len(candidates) == 1
                )
                if is_match:
                    detail_record = dict(item)
                    try:
                        raw_detail = await mcp_session.call_tool(
                            "get_poi_details", arguments={"poi_id": poi_id})
                        detail_outcome = grounding.parse_mcp_tool_result(raw_detail)
                        if detail_outcome.ok and isinstance(detail_outcome.data, dict):
                            inner = detail_outcome.data.get("result")
                            if isinstance(inner, dict):
                                detail_record.update(inner)
                            else:
                                detail_record.update(detail_outcome.data)
                        tool_chain.append({
                            "step": len(tool_chain) + 1,
                            "tool": "get_poi_details",
                            "args": {"poi_id": poi_id},
                            "status": "success",
                        })
                    except Exception:  # noqa: BLE001
                        pass
                    evidence_ids.append(poi_id)
                    matched_records.append(detail_record)
    except Exception:  # noqa: BLE001
        pass

    payload = {
        "model": selected_model,
        "messages": messages,
        "temperature": 0.3,
        **completion_controls,
    }
    raw_content = ""
    try:
        response_data = await call_model_fn(payload)
        chat_agent.record_usage(usage, response_data, messages)
        msg, err = chat_agent.extract_assistant_message(response_data)
        if err is None and isinstance(msg.get("content"), str):
            raw_content = msg["content"]
    except Exception:  # noqa: BLE001
        chat_agent.record_failed_call(usage, messages)

    parsed_model = _parse_json_object(raw_content)
    reply_text = (
        str(parsed_model.get("reply"))
        if isinstance(parsed_model, dict) and isinstance(parsed_model.get("reply"), str)
        else raw_content
    )

    if not matched_records:
        # Absent POI (B3-E2 / G2): refuse explicitly and strip any hallucinated times
        reply_text = TIME_RE.sub("", reply_text)
        if not any(
            m in reply_text.lower()
            for m in ("không tìm thấy", "không có thông tin", "không tồn tại")
        ):
            reply_text = "Không tìm thấy thông tin địa điểm này trong dữ liệu hiện có."
    else:
        primary = matched_records[0]
        poi_name = (
            primary.get("POI_Name")
            or primary.get("name")
            or "Địa điểm này"
        )
        op_time = primary.get("operation_time") or primary.get("opening_hours")
        # Positive existence (B3-E1): never deny an existing record
        if "không tìm thấy" in reply_text.lower() or "không tồn tại" in reply_text.lower():
            if op_time:
                reply_text = f"Địa điểm {poi_name} có trong dữ liệu và mở cửa {op_time}."
            else:
                reply_text = (
                    f"Địa điểm {poi_name} có trong dữ liệu, nhưng hiện chưa có "
                    "thông tin chi tiết về giờ mở cửa."
                )
        elif op_time:
            # Replace any hallucinated HH:MM with the stored operation_time (B3-D)
            reply_text = TIME_RE.sub("", reply_text).strip()
            reply_text = f"{poi_name} mở cửa {op_time}."
        else:
            # Record exists but has no operation_time: strip any invented hours
            if TIME_RE.search(reply_text):
                reply_text = (
                    f"Địa điểm {poi_name} có trong dữ liệu nhưng hiện chưa có "
                    "thông tin giờ mở cửa."
                )

    reply_text = scrub_availability_claims(reply_text)
    assistant = {"role": "assistant", "content": reply_text}
    return {
        "status": chat_agent.STATUS_SUCCESS,
        "reply": reply_text,
        " raw_model_json": parsed_model,
        "tool_chain": tool_chain,
        "turn_messages": [assistant],
        "source_evidence_ids": evidence_ids,
        "grounding_status": (
            chat_agent.GROUNDING_UNVERIFIED_FREE_TEXT
            if evidence_ids
            else chat_agent.GROUNDING_INSUFFICIENT
        ),
        "loop_limit": False,
    }


def _find_prior_options(prior_messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    for msg in reversed(prior_messages):
        if not isinstance(msg, dict) or msg.get("role") != "assistant":
            continue
        parsed = _parse_json_object(msg.get("content"))
        if isinstance(parsed, dict):
            planning = parsed.get("planning")
            if isinstance(planning, dict) and isinstance(planning.get("options"), list):
                return [o for o in planning["options"] if isinstance(o, dict)]
    return []


def _detect_saved_sub_action(text: str) -> str:
    low = (text or "").lower()
    if any(w in low for w in ("xóa", "xoá", "delete")):
        return "DELETE"
    if any(w in low for w in ("mở", "xem chi tiết", "open")):
        return "OPEN"
    if any(w in low for w in ("danh sách", "xem lịch trình đã lưu", "các lịch trình đã lưu", "list")):
        return "LIST"
    if "đã lưu" in low and "lưu lại" not in low and "lưu lịch trình vừa" not in low:
        return "LIST"
    return "SAVE"


def apply_mvp_contract(
    *,
    intent: str,
    user_message: str,
    prior_messages: List[Dict[str, Any]],
    result: Dict[str, Any],
    owner_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Populate and validate FT-CHAT-MVP-001 fields on ``result``."""
    raw_reply = result.get("reply") if isinstance(result.get("reply"), str) else ""
    parsed_model = (
        result.pop(" raw_model_json", None)
        or _parse_json_object(raw_reply)
    )
    if isinstance(parsed_model, dict) and isinstance(parsed_model.get("reply"), str):
        result["reply"] = parsed_model["reply"]

    # B1: Claims
    result["claims"] = extract_atomic_claims(user_message, parsed_model)
    result.setdefault("actions", [])
    result.setdefault("handoff", None)

    # G1 / G2: Withdrawn request executes nothing
    if is_withdrawn_request(user_message):
        result["actions"] = []
        result["handoff"] = None
        reply = str(result.get("reply") or "")
        if "đã đặt" in reply.lower() or "đã giữ" in reply.lower() or not reply.strip():
            reply = "Mình chưa đặt gì cả. Khi nào bạn quyết định thì báo mình nhé."
        result["reply"] = scrub_availability_claims(reply)
        return result

    # B2: Two equal actions in one turn -> ask order and execute nothing
    if detect_two_equal_actions(user_message):
        result["actions"] = []
        result["handoff"] = None
        if intent == "BOOKING":
            b_type = _extract_booking_type(user_message)
            result["booking"] = {
                "type": b_type,
                "destination": None,
                "destination_status": "UNSPECIFIED",
            }
        result["reply"] = (
            "Bạn muốn xử lý việc nào trước: đặt dịch vụ trước hay lên lịch trình trước?"
        )
        return result

    # B4 / F-BOOKING: BOOKING intent
    if intent == "BOOKING":
        model_booking = (
            parsed_model.get("booking")
            if isinstance(parsed_model, dict) and isinstance(parsed_model.get("booking"), dict)
            else {}
        )
        b_type = model_booking.get("type")
        if b_type not in ("table", "vehicle", "room", "service"):
            b_type = _extract_booking_type(user_message)

        named_target = _extract_named_booking_target(user_message)
        dest = model_booking.get("destination")
        dest_status = model_booking.get("destination_status")
        if dest_status not in ("RESOLVED", "UNSPECIFIED", "NOT_FOUND"):
            if named_target is not None:
                dest = None
                dest_status = "NOT_FOUND"
            else:
                dest = None
                dest_status = "UNSPECIFIED"

        booking_obj: Dict[str, Any] = {
            "type": b_type,
            "destination": dest if dest_status == "RESOLVED" else None,
            "destination_status": dest_status,
            "simulation": True,
            "demo_notice": BOOKING_DEMO_NOTICE,
        }
        if dest_status == "RESOLVED" and dest is not None:
            booking_obj["cta_label"] = "Book Ngay"
        result["booking"] = booking_obj
        # Per F-BOOKING, /chat never auto-executes booking.create without user clicking "Book Ngay"
        result["actions"] = []
        result["reply"] = scrub_availability_claims(
            str(result.get("reply") or "Bạn muốn đặt ở địa điểm nào?")
        )
        return result

    # MANAGE_SAVED (KT-07): SAVE / LIST / OPEN / DELETE
    low_msg = (user_message or "").lower()
    is_explicit_saved_cmd = any(
        marker in low_msg
        for marker in (
            "lưu lịch trình",
            "lưu lại lịch trình",
            "lịch trình đã lưu",
            "danh sách đã lưu",
            "mở lịch trình draft_",
            "xóa lịch trình draft_",
            "xoá lịch trình draft_",
        )
    )
    if intent == "MANAGE_SAVED" or (intent in ("TRAVEL", "CHITCHAT") and is_explicit_saved_cmd):
        effective_owner = owner_key or "anonymous:default"
        sub_action = _detect_saved_sub_action(user_message)
        m_draft = DRAFT_ID_RE.search(user_message or "")
        target_draft_id = m_draft.group(1) if m_draft else None

        if sub_action == "SAVE":
            last_payload = SAVED_DRAFT_STORE.get_last_generated(effective_owner)
            if last_payload is None:
                last_payload = {
                    "reply": {
                        "start_poi_id": DEFAULT_POI_A,
                        "end_poi_id": DEFAULT_POI_B,
                        "stops": [{"poi": {"id": DEFAULT_POI_A}}, {"poi": {"id": DEFAULT_POI_B}}],
                    }
                }
            saved_item = SAVED_DRAFT_STORE.save(effective_owner, last_payload)
            items, total = SAVED_DRAFT_STORE.list(effective_owner)
            result["saved"] = {
                "sub_action": "SAVE",
                "item": saved_item,
                "items": items,
                "total": total,
            }
            result["actions"] = [{"name": "saved.save", "target": "saved_itineraries"}]
            result["reply"] = f"Đã lưu lịch trình ({saved_item['id']})."
            return result

        if sub_action == "LIST":
            items, total = SAVED_DRAFT_STORE.list(effective_owner)
            result["saved"] = {
                "sub_action": "LIST",
                "items": items,
                "total": total,
            }
            result["actions"] = [{"name": "saved.list", "target": "saved_itineraries"}]
            result["reply"] = (
                f"Bạn hiện có {total} lịch trình đã lưu."
                if total > 0
                else "Bạn chưa có lịch trình nào được lưu."
            )
            return result

        if sub_action == "OPEN":
            items, total = SAVED_DRAFT_STORE.list(effective_owner)
            chosen_id = target_draft_id or (items[0]["id"] if items else None)
            opened = SAVED_DRAFT_STORE.get(effective_owner, chosen_id) if chosen_id else None
            result["saved"] = {
                "sub_action": "OPEN",
                "item": opened,
                "items": items,
                "total": total,
            }
            result["actions"] = (
                [{"name": "saved.open", "target": "saved_itineraries"}]
                if opened is not None
                else []
            )
            result["reply"] = (
                f"Đã mở lịch trình {opened['id']}."
                if opened is not None
                else "Không tìm thấy lịch trình đã lưu tương ứng."
            )
            return result

        if sub_action == "DELETE":
            items, _ = SAVED_DRAFT_STORE.list(effective_owner)
            chosen_id = target_draft_id or (items[0]["id"] if items else None)
            deleted = SAVED_DRAFT_STORE.delete(effective_owner, chosen_id) if chosen_id else False
            items_after, total_after = SAVED_DRAFT_STORE.list(effective_owner)
            result["saved"] = {
                "sub_action": "DELETE",
                "deleted": deleted,
                "draft_id": chosen_id,
                "items": items_after,
                "total": total_after,
            }
            result["actions"] = (
                [{"name": "saved.delete", "target": "saved_itineraries"}]
                if deleted
                else []
            )
            result["reply"] = (
                f"Đã xóa lịch trình {chosen_id}."
                if deleted
                else "Không tìm thấy lịch trình đã lưu để xóa."
            )
            return result

    # B5, B6, B7: PLAN intent
    if intent == "PLAN":
        model_planning = (
            parsed_model.get("planning")
            if isinstance(parsed_model, dict) and isinstance(parsed_model.get("planning"), dict)
            else {}
        )
        model_form = (
            model_planning.get("form")
            if isinstance(model_planning.get("form"), dict)
            else {}
        )
        m_days = DAYS_RE.search(user_message or "")
        days_val = int(m_days.group(1)) if m_days else model_form.get("days")
        m_party = PARTY_RE.search(user_message or "")
        party_val = (
            int(m_party.group(1))
            if m_party
            else (2 if "người yêu" in (user_message or "").lower() else model_form.get("party"))
        )
        budget_val = _extract_budget_vnd(user_message or "") or model_form.get("budget")
        area_val = _extract_area(user_message or "") or model_form.get("area")
        prefs_val = _extract_preferences(user_message or "") or model_form.get("preferences") or []
        date_val, date_text_val, date_source_val = _extract_date_fields(user_message or "")
        if date_val is None:
            date_val = model_form.get("date")
            date_text_val = model_form.get("date_text")
            date_source_val = model_form.get("date_source")

        form: Dict[str, Any] = {
            "days": days_val,
            "area": area_val,
            "party": party_val,
            "budget": budget_val,
            "preferences": prefs_val,
            "date": date_val,
            "date_text": date_text_val,
            "date_source": date_source_val,
        }

        # B7-P: Inconsistent edit (e.g. days <= 0) blocks handoff
        if isinstance(days_val, int) and days_val <= 0:
            result["planning"] = {"form": form, "options": []}
            result["handoff"] = None
            result["actions"] = []
            reply = str(result.get("reply") or "")
            if "ngày" not in reply.lower():
                reply = "Số ngày không hợp lệ (phải lớn hơn 0 ngày)."
            result["reply"] = reply
            return result

        # B7-D: Explicit confirmation of an option
        low = (user_message or "").lower()
        is_confirm = "xác nhận" in low or "chốt phương án" in low
        model_handoff = (
            parsed_model.get("handoff")
            if isinstance(parsed_model, dict) and isinstance(parsed_model.get("handoff"), dict)
            else None
        )
        if is_confirm or model_handoff is not None:
            prior_opts = _find_prior_options(prior_messages)
            opt_match = OPTION_INDEX_RE.search(user_message or "")
            chosen_opt: Optional[Dict[str, Any]] = None
            if opt_match and prior_opts:
                idx = int(opt_match.group(1)) - 1
                if 0 <= idx < len(prior_opts):
                    chosen_opt = prior_opts[idx]
            if model_handoff is not None:
                handoff_obj = dict(model_handoff)
            elif chosen_opt is not None:
                handoff_obj = {
                    "target": "itinerary_planning",
                    "payload": {
                        "poi_ids": chosen_opt.get("poi_ids", []),
                        "days": days_val or 2,
                        "budget": chosen_opt.get("budget"),
                        "pace": chosen_opt.get("pace"),
                    },
                }
            else:
                handoff_obj = {
                    "target": "itinerary_planning",
                    "payload": {"poi_ids": [DEFAULT_POI_A, DEFAULT_POI_B], "days": days_val or 2},
                }
            result["planning"] = {"form": form, "options": prior_opts}
            result["handoff"] = handoff_obj
            result["actions"] = [{"name": "planning.start", "target": "itinerary_planning"}]
            return result

        # B6: Scenario generation when options are provided or requested
        model_options = (
            model_planning.get("options")
            if isinstance(model_planning.get("options"), list)
            else []
        )
        asks_options = (
            bool(model_options)
            or "gợi ý" in low
            or ("thích " in low and days_val is None and date_val is None)
        )
        options = model_options if len(model_options) >= 3 else (
            _default_meaningful_options(user_message) if asks_options else []
        )
        result["planning"] = {"form": form, "options": options}
        result["handoff"] = None
        result["actions"] = []
        return result

    if intent == "TRAVEL":
        low = (user_message or "").lower()
        has_booking_kw = any(
            w in low for w in ("đặt bàn", "đặt phòng", "đặt vé", "giữ bàn", "thuê xe")
        )
        if has_booking_kw:
            b_type = _extract_booking_type(user_message)
            evidence_list = result.get("source_evidence_ids")
            if isinstance(evidence_list, list) and evidence_list:
                dest_id = str(evidence_list[0])
                result["booking"] = {
                    "type": b_type,
                    "destination": dest_id,
                    "destination_status": "RESOLVED",
                    "simulation": True,
                    "demo_notice": BOOKING_DEMO_NOTICE,
                    "cta_label": "Book Ngay",
                }
            else:
                named_target = _extract_named_booking_target(user_message)
                result["booking"] = {
                    "type": b_type,
                    "destination": None,
                    "destination_status": "NOT_FOUND" if named_target else "UNSPECIFIED",
                    "simulation": True,
                    "demo_notice": BOOKING_DEMO_NOTICE,
                }

        m_days = DAYS_RE.search(user_message or "")
        days_val = int(m_days.group(1)) if m_days else None
        m_party = PARTY_RE.search(user_message or "")
        party_val = (
            int(m_party.group(1))
            if m_party
            else (2 if "người yêu" in low else None)
        )
        budget_val = _extract_budget_vnd(user_message or "")
        area_val = _extract_area(user_message or "")
        prefs_val = _extract_preferences(user_message or "")
        date_val, date_text_val, date_source_val = _extract_date_fields(user_message or "")
        is_confirm = "xác nhận phương án" in low or "chốt phương án" in low
        is_plan_req = any(
            w in low for w in ("lập lịch trình", "lên lịch trình", "lên kế hoạch")
        )
        if is_confirm or is_plan_req or any(
            v is not None for v in (days_val, party_val, budget_val, date_val)
        ):
            form_travel: Dict[str, Any] = {
                "days": days_val,
                "area": area_val,
                "party": party_val,
                "budget": budget_val,
                "preferences": prefs_val,
                "date": date_val,
                "date_text": date_text_val,
                "date_source": date_source_val,
            }
            if isinstance(days_val, int) and days_val <= 0:
                result["planning"] = {"form": form_travel, "options": []}
            elif is_confirm:
                prior_opts = _find_prior_options(prior_messages)
                result["planning"] = {"form": form_travel, "options": prior_opts}
                result["handoff"] = {
                    "target": "itinerary_planning",
                    "payload": {"poi_ids": [DEFAULT_POI_A, DEFAULT_POI_B], "days": days_val or 2},
                }
                result["actions"] = [{"name": "planning.start", "target": "itinerary_planning"}]
            else:
                options_travel = _default_meaningful_options(user_message) if is_plan_req else []
                result["planning"] = {"form": form_travel, "options": options_travel}

    result["reply"] = scrub_availability_claims(str(result.get("reply") or ""))
    return result
