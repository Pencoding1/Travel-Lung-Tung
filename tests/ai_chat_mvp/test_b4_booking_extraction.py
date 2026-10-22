"""EVALUATE SET (agent-visible) — B4 Booking Intent Extraction.

The four-field object is the format: {intent, type, destination,
destination_status}. Values must come from the message and the database, never
from a table of canned answers.
"""

import json

from mvp_harness import (
    POI_QUAN1_RESTAURANT,
    assert_no_availability_claim,
    assert_turn_accepted,
    chat,
    field,
)

TYPES = {"table", "vehicle", "room", "service"}
KNOWN_IDS = {
    POI_QUAN1_RESTAURANT,
    "hcm_primary_geojson_internal:033dd327cc9b86b52c8768151afad7f2",
}


def test_C_B4_D_table_booking_without_target_is_unspecified(monkeypatch):
    payload = json.dumps({
        "booking": {"type": "table", "destination": None,
                    "destination_status": "UNSPECIFIED"},
        "reply": "Bạn muốn đặt bàn ở quán nào?"}, ensure_ascii=False)
    response, _session, _llm = chat(
        monkeypatch, "Đặt bàn 2 người 7h tối nay.",
        intent="BOOKING", model_contents=[payload])
    body = response.json()
    assert_turn_accepted(body, "B4")
    booking = field(body, "booking", "B4")
    assert booking.get("type") in TYPES
    assert booking.get("type") == "table", f"type must be table, got {booking!r}"
    assert booking.get("destination") is None
    assert booking.get("destination_status") == "UNSPECIFIED", (
        f"no target was named, so UNSPECIFIED is required, got {booking!r}"
    )
    assert_no_availability_claim(body.get("reply"))


def test_C_B4_P_two_booking_types_do_not_execute_twice(monkeypatch):
    payload = json.dumps({
        "booking": {"type": "room", "destination": None,
                    "destination_status": "UNSPECIFIED"},
        "reply": "Bạn muốn xử lý đặt phòng trước hay đặt bàn trước?"},
        ensure_ascii=False)
    response, _session, _llm = chat(
        monkeypatch,
        "Đặt phòng khách sạn đó 2 đêm, nếu hết phòng thì đặt bàn nhà hàng luôn.",
        intent="BOOKING", model_contents=[payload])
    body = response.json()
    assert_turn_accepted(body, "B4")
    booking = field(body, "booking", "B4")
    assert booking.get("type") in TYPES
    actions = field(body, "actions", "B4")
    created = [a for a in actions if a.get("name") == "booking.create"]
    assert len(created) <= 1, (
        f"at most one booking may be created in a turn, got {created!r}"
    )
    assert_no_availability_claim(body.get("reply"))


def test_C_B4_N_named_but_missing_target_is_not_found(monkeypatch):
    payload = json.dumps({
        "booking": {"type": "table", "destination": None,
                    "destination_status": "NOT_FOUND"},
        "reply": "Mình không tìm thấy nhà hàng Bóng Đêm trong dữ liệu."},
        ensure_ascii=False)
    response, _session, _llm = chat(
        monkeypatch, "Đặt bàn ở nhà hàng Bóng Đêm Quận 7.",
        intent="BOOKING", model_contents=[payload])
    body = response.json()
    assert_turn_accepted(body, "B4")
    booking = field(body, "booking", "B4")
    assert booking.get("destination_status") == "NOT_FOUND", (
        "the user named a place that is absent, so NOT_FOUND is required, "
        f"got {booking!r}"
    )
    assert booking.get("destination") is None, (
        "no entity may be invented for a place that is not in the database"
    )
    actions = field(body, "actions", "B4")
    assert not any(a.get("name") == "booking.create" for a in actions), (
        "an unresolved booking must not be handed to the Booking feature"
    )
