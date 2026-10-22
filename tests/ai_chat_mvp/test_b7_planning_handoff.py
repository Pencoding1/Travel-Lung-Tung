"""EVALUATE SET (agent-visible) — B7 Planning Handoff.

After confirmation the confirmed payload is handed to Itinerary Planning; an
inconsistent edit blocks the hand-off.
"""

import json
import uuid

from mvp_harness import (
    POI_CAFE_BETTA,
    POI_GALLERY_ANH_TUONG,
    POI_QUAN1_RESTAURANT,
    actions_of,
    assert_turn_accepted,
    chat,
    field,
)

OPTIONS = {"planning": {"form": {"days": 2, "area": None, "party": 2,
                                 "budget": 2000000, "preferences": ["cà phê"],
                                 "date": None, "date_text": None,
                                 "date_source": None},
                        "options": [
    {"poi_ids": [POI_CAFE_BETTA, POI_GALLERY_ANH_TUONG], "area_ids": ["quan-1"],
     "pace": "relaxed", "budget": 800000, "experience_types": ["coffee"]},
    {"poi_ids": [POI_QUAN1_RESTAURANT, POI_CAFE_BETTA], "area_ids": ["quan-3"],
     "pace": "moderate", "budget": 2000000, "experience_types": ["food"]},
    {"poi_ids": [POI_GALLERY_ANH_TUONG, POI_QUAN1_RESTAURANT],
     "area_ids": ["tan-phu"], "pace": "packed", "budget": 1500000,
     "experience_types": ["museum"]},
]}}

CHOSEN = OPTIONS["planning"]["options"][1]


def _start_session(monkeypatch, session_id):
    chat(monkeypatch, "Lên lịch 2 ngày, ngân sách 2 triệu, thích cà phê.",
         intent="PLAN", model_contents=[json.dumps(OPTIONS, ensure_ascii=False)],
         session_id=session_id, memory_enabled=True)


def _planning_started(body):
    return [a for a in actions_of(body, "B7") if a.get("name") == "planning.start"]


def test_C_B7_D_confirmed_option_is_handed_off(monkeypatch):
    session_id = f"s-{uuid.uuid4().hex[:8]}"
    _start_session(monkeypatch, session_id)

    handoff = {"handoff": {"target": "itinerary_planning",
                           "payload": {"poi_ids": CHOSEN["poi_ids"], "days": 2,
                                       "budget": CHOSEN["budget"],
                                       "pace": CHOSEN["pace"]}},
               "reply": "Đã chuyển sang bước lập lịch trình."}
    body = chat(monkeypatch, "Chọn phương án 2, xác nhận.",
                intent="PLAN", model_contents=[json.dumps(handoff, ensure_ascii=False)],
                session_id=session_id, memory_enabled=True)[0].json()

    assert_turn_accepted(body, "B7")
    data = field(body, "handoff", "B7")
    assert data and data.get("target") == "itinerary_planning", (
        f"a confirmed plan must be handed to Itinerary Planning, got {data!r}"
    )
    assert data["payload"]["poi_ids"] == CHOSEN["poi_ids"], (
        "the handed-over itinerary must be the confirmed option"
    )
    started = _planning_started(body)
    assert len(started) == 1, (
        f"planning must start exactly once, got {len(started)} ({started!r})"
    )


def test_C_B7_P_inconsistent_edit_blocks_the_handoff(monkeypatch):
    session_id = f"s-{uuid.uuid4().hex[:8]}"
    _start_session(monkeypatch, session_id)

    body = chat(
        monkeypatch, "Chọn phương án 2, sửa số ngày thành 0.",
        intent="PLAN",
        model_contents=[json.dumps({"reply": "Số ngày phải lớn hơn 0."},
                                   ensure_ascii=False)],
        session_id=session_id, memory_enabled=True)[0].json()

    assert_turn_accepted(body, "B7")
    assert body.get("handoff") is None, (
        f"an inconsistent plan must not be handed over, got {body.get('handoff')!r}"
    )
    assert _planning_started(body) == [], "planning must not start on invalid input"
    reply = (body.get("reply") or "").lower()
    assert "ngày" in reply, (
        f"the answer must name the field that conflicts, got reply={reply!r}"
    )
