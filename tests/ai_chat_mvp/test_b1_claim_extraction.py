"""B1 — Claim Extraction (contract FT-CHAT-MVP-001 §2, B1).

Each assistant turn must expose the atomic claims it derived from the user
message. Assertions are on the contract surface (``claims[]``), never on how
the claims were produced.
"""

import json

from mvp_harness import assert_turn_accepted, chat, field

CLAIMS_D = {"claims": [
    {"text": "tìm quán cà phê", "entity_refs": [],
     "constraints": {"category": "cà phê", "area": "Quận 1"}},
]}

CLAIMS_K = {"claims": [
    {"text": "nhóm 3 người", "entity_refs": [], "constraints": {"party": 3}},
    {"text": "8 giờ tối", "entity_refs": [], "constraints": {"time": "20:00"}},
    {"text": "ở Bình Thạnh", "entity_refs": [], "constraints": {"area": "Bình Thạnh"}},
    {"text": "chỗ ngồi nói chuyện được, đừng ồn", "entity_refs": [],
     "constraints": {"attribute": "quiet"}},
]}

CLAIMS_P = {"claims": [
    {"text": "muốn đi Bảo tàng Mỹ Thuật", "entity_refs": ["Bảo tàng Mỹ Thuật"],
     "constraints": {}},
    {"text": "ăn gì đó dưới 200k/người", "entity_refs": [],
     "constraints": {"budget_per_person": 200000}},
    {"text": "nếu mưa thì tìm chỗ gần khách sạn", "entity_refs": [],
     "constraints": {"condition": "if_rain", "target": "guesthouse_nearby"}},
    {"text": "khách sạn mình ở", "entity_refs": [], "constraints": {"reference": "unresolved"}},
]}


def test_C_B1_D_single_lookup_yields_one_claim(monkeypatch):
    response, _session, _llm = chat(
        monkeypatch, "Tìm quán cà phê ở Quận 1.",
        intent="CHITCHAT", model_contents=[json.dumps(CLAIMS_D, ensure_ascii=False)])
    body = response.json()
    assert_turn_accepted(body, "B1")
    claims = field(body, "claims", "B1")
    assert len(claims) == 1, f"expected exactly one atomic claim, got {claims!r}"
    dumped = json.dumps(claims, ensure_ascii=False)
    assert "Quận 1" in dumped and "cà phê" in dumped


def test_C_B1_K_attributes_stay_separate_and_no_booking_is_invented(monkeypatch):
    response, _session, _llm = chat(
        monkeypatch,
        "Nhóm mình 3 người, 8h tối, muốn chỗ ngồi nói chuyện được ở Bình Thạnh, đừng ồn.",
        intent="CHITCHAT", model_contents=[json.dumps(CLAIMS_K, ensure_ascii=False)])
    body = response.json()
    assert_turn_accepted(body, "B1")
    claims = field(body, "claims", "B1")
    assert len(claims) >= 4, f"attributes were collapsed into too few claims: {claims!r}"
    dumped = json.dumps(claims, ensure_ascii=False).lower()
    assert "đặt bàn" not in dumped and "booking" not in dumped, (
        "B1 forbids inventing a request the user did not make: no booking claim "
        f"may appear, got {claims!r}"
    )
    assert body.get("intent") != "BOOKING", (
        "a description of a group/attributes is not a booking request yet"
    )


def test_C_B1_P_conditional_and_unresolved_reference_are_kept_apart(monkeypatch):
    response, _session, _llm = chat(
        monkeypatch,
        "Mình muốn đi Bảo tàng Mỹ Thuật, rồi ăn gì dưới 200k/người, "
        "nếu mưa thì tìm chỗ gần khách sạn mình ở.",
        intent="CHITCHAT", model_contents=[json.dumps(CLAIMS_P, ensure_ascii=False)])
    body = response.json()
    assert_turn_accepted(body, "B1")
    claims = field(body, "claims", "B1")
    dumped = json.dumps(claims, ensure_ascii=False)
    assert "mưa" in dumped.lower(), (
        f"the conditional branch must survive as its own claim, got {claims!r}"
    )
    assert "khách sạn" in dumped.lower(), "the unresolved reference must be kept"
    assert "hcm_primary_geojson_internal" not in dumped, (
        "an unresolved reference must not be silently resolved to a POI id"
    )
