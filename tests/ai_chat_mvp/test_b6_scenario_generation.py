"""EVALUATE SET (agent-visible) — B6 Scenario Generation.

At least three options, measurably different (§2.2 rule), never auto-selected.
"""

import json

from mvp_harness import (
    POI_CAFE_BETTA,
    POI_GALLERY_ANH_TUONG,
    POI_QUAN1_RESTAURANT,
    assert_options_meaningful,
    assert_turn_accepted,
    chat,
    field,
)

OPTIONS_D = {"planning": {"form": {"days": 2, "area": None, "party": None,
                                   "budget": None, "preferences": [],
                                   "date": None, "date_text": None,
                                   "date_source": None},
                          "options": [
    {"poi_ids": [POI_CAFE_BETTA, POI_GALLERY_ANH_TUONG], "area_ids": ["quan-1"],
     "pace": "relaxed", "budget": 500000,
     "experience_types": ["coffee", "museum"]},
    {"poi_ids": [POI_QUAN1_RESTAURANT, POI_CAFE_BETTA], "area_ids": ["quan-3"],
     "pace": "moderate", "budget": 900000,
     "experience_types": ["food", "coffee"]},
    {"poi_ids": [POI_GALLERY_ANH_TUONG, POI_QUAN1_RESTAURANT],
     "area_ids": ["tan-phu", "quan-1"], "pace": "packed", "budget": 1500000,
     "experience_types": ["museum", "food"]},
]}}


def test_C_B6_D_suggests_three_measurably_different_options(monkeypatch):
    response, _session, _llm = chat(
        monkeypatch, "Gợi ý cho mình 2 ngày ở TP.HCM.",
        intent="PLAN", model_contents=[json.dumps(OPTIONS_D, ensure_ascii=False)])
    body = response.json()
    assert_turn_accepted(body, "B6")
    planning = field(body, "planning", "B6")
    assert_options_meaningful(planning.get("options"))
    assert body.get("handoff") is None, (
        "the system may not pick an option for the user"
    )


def test_C_B6_K_options_follow_the_stated_preferences(monkeypatch):
    payload = json.loads(json.dumps(OPTIONS_D))
    for option in payload["planning"]["options"]:
        option["experience_types"] = ["quiet", "coffee"]
    response, _session, _llm = chat(
        monkeypatch, "Mình thích yên tĩnh, thích cà phê, không thích đông.",
        intent="PLAN", model_contents=[json.dumps(payload, ensure_ascii=False)])
    body = response.json()
    assert_turn_accepted(body, "B6")
    planning = field(body, "planning", "B6")
    assert_options_meaningful(planning.get("options"))
    for option in planning["options"]:
        assert "coffee" in option.get("experience_types", []), (
            f"every option must carry the stated preference: {option!r}"
        )
    assert body.get("handoff") is None
