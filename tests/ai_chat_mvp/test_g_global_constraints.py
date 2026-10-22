"""EVALUATE SET (agent-visible) — Global constraints (G1, G2).

An information question must never start a side effect, and a withdrawn request
must execute nothing.
"""

import json

from mvp_harness import (
    POI_QUAN1_RESTAURANT,
    actions_of,
    assert_no_availability_claim,
    assert_turn_accepted,
    chat,
    explore_results,
    field,
    ok_json,
    poi_compound,
    poi_result_missing_hours,
)

ACTIONS = ("booking.create", "planning.start")


def _restaurant_handlers():
    return {
        "explore_pois": lambda args: ok_json(explore_results(
            poi_compound(POI_QUAN1_RESTAURANT, "jumbo seafood"))),
        "get_poi_details": lambda args: ok_json(poi_result_missing_hours()),
    }


def _action_names(body):
    return [a.get("name") for a in actions_of(body, "G1")]


def test_C_G_D_information_question_never_starts_booking_or_planning(monkeypatch):
    response, _session, _llm = chat(
        monkeypatch, "Quán Jumbo Seafood có gì ngon?",
        intent="CHITCHAT", handlers=_restaurant_handlers(),
        model_contents=["Dữ liệu hiện tại không có thông tin về thực đơn."])
    body = response.json()
    assert_turn_accepted(body, "G1")
    assert field(body, "intent", "B2") == "CHITCHAT"
    assert not set(_action_names(body)) & set(ACTIONS), (
        f"an information question started a side effect: {_action_names(body)!r}"
    )


def test_C_G_P_withdrawn_request_executes_nothing(monkeypatch):
    response, _session, _llm = chat(
        monkeypatch, "Đặt bàn chỗ đó luôn đi… mà thôi để mình suy nghĩ.",
        intent="BOOKING", handlers=_restaurant_handlers(),
        model_contents=["Mình chưa đặt gì cả. Khi nào bạn quyết định thì báo mình."])
    body = response.json()
    assert_turn_accepted(body, "G1")
    assert not set(_action_names(body)) & set(ACTIONS), (
        f"a withdrawn request must not execute anything: {_action_names(body)!r}"
    )
    reply = (body.get("reply") or "").lower()
    assert "đã đặt" not in reply and "đã giữ" not in reply, (
        f"the system must not claim a booking happened, got reply={reply!r}"
    )
    assert_no_availability_claim(body.get("reply"))
