"""EVALUATE SET (agent-visible) — B5 Planning Input.

The form is the format: fields the user did not provide stay null, and the date
carries its original wording plus a source label.
"""

import json
from datetime import date, timedelta

from mvp_harness import assert_turn_accepted, chat, field, iso_day, upcoming_saturday

FORM_D = {"planning": {"form": {
    "days": 2, "area": "Quận 1", "party": 2, "budget": 3000000,
    "preferences": [], "date": None, "date_text": None, "date_source": None,
}, "options": []}}


def test_C_B5_D_prefills_only_what_the_user_said(monkeypatch):
    response, _session, _llm = chat(
        monkeypatch, "Lên lịch 2 ngày ở Quận 1 cho 2 người, ngân sách 3 triệu.",
        intent="PLAN", model_contents=[json.dumps(FORM_D, ensure_ascii=False)])
    body = response.json()
    assert_turn_accepted(body, "B5")
    planning = field(body, "planning", "B5")
    form = planning.get("form") or {}
    assert form.get("days") == 2
    assert form.get("area") == "Quận 1"
    assert form.get("party") == 2
    assert form.get("budget") == 3000000
    assert form.get("preferences") in ([], None), (
        f"no preference was stated, so none may be invented: {form.get('preferences')!r}"
    )


def test_C_B5_K_relative_date_is_converted_and_disclosed(monkeypatch):
    expected = iso_day(upcoming_saturday())
    payload = {"planning": {"form": {
        "days": 2, "area": None, "party": 2, "budget": 2000000,
        "preferences": ["cà phê", "bảo tàng"],
        "date": expected, "date_text": "cuối tuần này",
        "date_source": "converted_from_relative",
    }, "options": []}}
    response, _session, _llm = chat(
        monkeypatch,
        "Cuối tuần này mình rảnh 2 ngày, đi với người yêu, thích cà phê với "
        "bảo tàng, tiền tầm 2 triệu.",
        intent="PLAN", model_contents=[json.dumps(payload, ensure_ascii=False)])
    body = response.json()
    assert_turn_accepted(body, "B5")
    form = field(body, "planning", "B5").get("form") or {}
    assert form.get("date") == expected, (
        f"'cuối tuần này' must resolve to {expected}, got {form.get('date')!r}"
    )
    assert form.get("date_text") == "cuối tuần này", (
        "the original wording must be preserved so the user can check the conversion"
    )
    assert form.get("date_source") == "converted_from_relative", (
        f"a converted date must say so, got {form.get('date_source')!r}"
    )


def test_C_B5_S_sufficient_request_shows_form_without_options(monkeypatch):
    target = date.today() + timedelta(days=3)
    spoken = f"{target.day:02d}/{target.month:02d}"
    payload = {"planning": {"form": {
        "days": None, "area": None, "party": None, "budget": 2000000,
        "preferences": ["cà phê", "bảo tàng"],
        "date": iso_day(target), "date_text": spoken, "date_source": "explicit",
    }, "options": []}}
    response, _session, _llm = chat(
        monkeypatch,
        f"Ngày {spoken} mình muốn đi cà phê và bảo tàng, ngân sách 2 triệu.",
        intent="PLAN", model_contents=[json.dumps(payload, ensure_ascii=False)])
    body = response.json()
    assert_turn_accepted(body, "B5")
    planning = field(body, "planning", "B5")
    form = planning.get("form") or {}
    assert form.get("date") == iso_day(target)
    assert form.get("date_source") == "explicit", (
        f"an explicit date must not be labelled as converted, got {form.get('date_source')!r}"
    )
    assert not (planning.get("options") or []), (
        "sufficient input must not trigger scenario generation"
    )
