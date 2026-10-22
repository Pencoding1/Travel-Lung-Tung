"""EVALUATE SET (agent-visible) — B3 Grounded Answer with the existence pair.

The pair is the specification: an existing POI must be confirmed, an absent POI
must be refused. B3-N counts as the G2 clause (no unsupported data).
"""

import re

from mvp_harness import (
    POI_CAFE_BETTA,
    POI_GALLERY_ANH_TUONG,
    assert_turn_accepted,
    chat,
    explore_empty,
    explore_results,
    field,
    not_found_envelope,
    ok_json,
    poi_compound,
    poi_result_known_hours,
    poi_result_missing_hours,
)

TIME = re.compile(r"(?<!\d)(0[0-9]|1[0-9]|2[0-3]):[0-5][0-9]")
NOT_FOUND_MARKERS = ("không tìm thấy", "không có thông tin", "không tồn tại")


def _cafe_handlers():
    return {
        "explore_pois": lambda args: ok_json(explore_results(
            poi_compound(POI_CAFE_BETTA, "ca phe betta fish", "06:00-22:00"))),
        "get_poi_details": lambda args: ok_json(poi_result_known_hours()),
    }


def _gallery_handlers():
    return {
        "explore_pois": lambda args: ok_json(explore_results(
            poi_compound(POI_GALLERY_ANH_TUONG, "anh tuong my thuat"))),
        "get_poi_details": lambda args: ok_json(poi_result_missing_hours()),
    }


def _absent_handlers():
    return {
        "explore_pois": lambda args: ok_json(explore_empty()),
        "get_poi_details": lambda args: ok_json(not_found_envelope()),
    }


def test_C_B3_D_known_hours_are_answered_from_the_record(monkeypatch):
    response, _session, _llm = chat(
        monkeypatch, "Cà phê Betta Fish ở Võ Văn Kiệt mở cửa mấy giờ?",
        intent="CHITCHAT", handlers=_cafe_handlers(),
        model_contents=["Quán mở cửa 08:00-23:00 và có wifi miễn phí."])
    body = response.json()
    assert_turn_accepted(body, "B3")
    evidence = field(body, "source_evidence_ids", "B3")
    assert POI_CAFE_BETTA in evidence, (
        "an answer about a POI must be backed by a retrieved record, "
        f"got evidence={evidence!r}"
    )
    reply = body.get("reply") or ""
    assert "06:00" in reply and "22:00" in reply, (
        f"the answer must use the stored hours, got reply={reply!r}"
    )
    scrubbed = reply.replace("06:00", "").replace("22:00", "")
    assert not TIME.search(scrubbed), (
        f"the answer contains an hour that is not in the record: reply={reply!r}"
    )


def test_C_B3_E1_existing_poi_is_confirmed(monkeypatch):
    """Positive control: the record exists — never answer 'not found'."""
    response, _session, _llm = chat(
        monkeypatch, "Anh Tường Mỹ Thuật ở Tân Phú có mở cửa không?",
        intent="CHITCHAT", handlers=_gallery_handlers(),
        model_contents=["Không tìm thấy địa điểm này trong dữ liệu."])
    body = response.json()
    assert_turn_accepted(body, "B3")
    evidence = field(body, "source_evidence_ids", "B3")
    assert POI_GALLERY_ANH_TUONG in evidence, (
        "an existing POI must be retrieved and cited, "
        f"got evidence={evidence!r} — a false negative is a contract violation"
    )
    reply = (body.get("reply") or "").lower()
    assert "không tìm thấy" not in reply, (
        f"the record exists but the answer denied it: reply={reply!r}"
    )


def test_C_B3_E2_absent_poi_is_refused(monkeypatch):
    """Negative control: nothing exists — never answer as if it did (G2)."""
    response, _session, _llm = chat(
        monkeypatch, "Quán Cà Phê Bóng Đêm ở Quận 1 mở mấy giờ?",
        intent="CHITCHAT", handlers=_absent_handlers(),
        model_contents=["Quán Cà Phê Bóng Đêm mở cửa 08:00-23:00."])
    body = response.json()
    assert_turn_accepted(body, "B3")
    evidence = field(body, "source_evidence_ids", "B3")
    assert evidence == [], (
        f"no record exists, so no evidence id may be cited, got {evidence!r}"
    )
    reply = (body.get("reply") or "").lower()
    assert any(m in reply for m in NOT_FOUND_MARKERS), (
        f"an absent POI must be refused explicitly, got reply={reply!r}"
    )
    assert not TIME.search(reply), (
        f"an absent POI cannot have opening hours, got reply={reply!r}"
    )
