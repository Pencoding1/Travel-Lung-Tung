"""EVALUATE SET (agent-visible) — B2 Significant Intent.

The agent may read and use this file to align. It states the required behaviour
and format only; the hidden suite checks whether the behaviour is real.
"""

import json

from mvp_harness import assert_turn_accepted, chat, field

BOOKING_D = {"intent": "BOOKING",
             "booking": {"type": "table", "destination": None,
                         "destination_status": "UNSPECIFIED"},
             "reply": "Bạn cho mình biết quán nào để giữ bàn 4 người lúc 19h nhé."}


def test_C_B2_D_explicit_booking_is_the_significant_intent(monkeypatch):
    response, _session, _llm = chat(
        monkeypatch, "Đặt bàn 4 người 19h tối nay.",
        intent="BOOKING", model_contents=[json.dumps(BOOKING_D, ensure_ascii=False)])
    body = response.json()
    assert_turn_accepted(body, "B2")
    assert field(body, "intent", "B2") == "BOOKING"
    booking = field(body, "booking", "B4")
    assert booking.get("type") == "table"
    assert "muốn làm gì trước" not in (body.get("reply") or ""), (
        "a single explicit action must not trigger an order question"
    )


def test_C_B2_P_two_actions_ask_order_and_do_nothing(monkeypatch):
    response, _session, _llm = chat(
        monkeypatch,
        "Đặt bàn nhà hàng X cho 4 người tối nay, xong lên luôn lịch 2 ngày "
        "quanh đó, ngân sách 2 triệu.",
        intent="BOOKING", model_contents=[json.dumps(BOOKING_D, ensure_ascii=False)])
    body = response.json()
    assert_turn_accepted(body, "B2")
    actions = field(body, "actions", "B2")
    assert actions == [], (
        "two equal actions may not run in the same turn without confirmation, "
        f"got actions={actions!r}"
    )
    reply = (body.get("reply") or "").lower()
    assert "trước" in reply, (
        "the system must ask which request to handle first, "
        f"got reply={body.get('reply')!r}"
    )
