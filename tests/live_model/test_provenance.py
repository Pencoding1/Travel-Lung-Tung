from __future__ import annotations

import json

import pytest

from live_model import events, provenance

import fake_session_export as fx


def _parsed(lines):
    return events.parse_event_lines(list(lines))


def _verdict(export: dict, parsed=None, requested: str = fx.REQUESTED):
    parsed = parsed if parsed is not None else _parsed(fx.raw_events())
    return provenance.validate_observation_export(
        parsed, provenance.parse_session_export(export), requested)


# ---------------------------------------------------------------------------
# Real diagnostic fixture (non-scientific, read-only)
# ---------------------------------------------------------------------------
def test_ds004_real_fixture_binds_exact_qualified_model():
    events_path, export_path = fx.ds004_paths()
    parsed = events.parse_event_lines(
        events_path.read_text(encoding="utf-8").splitlines())
    assert parsed.session_id == "ses_ebbd4944cffem7aZnZIUJ1Jrb0"
    assert parsed.observed_model_ids == ()
    assert parsed.assistant_message_ids == ("msg_1442b70cc001vJYSnX893U6Ghy",)

    exported = provenance.parse_session_export_bytes(export_path.read_bytes())
    verdict = provenance.validate_observation_export(
        parsed, exported, "aibox/ds/deepseek-flash")
    assert verdict.ok, verdict.reason
    assert verdict.qualified_model_id == "aibox/ds/deepseek-flash"
    assert verdict.assistant_message_id == "msg_1442b70cc001vJYSnX893U6Ghy"
    # The observed alias is not treated as proof of an upstream checkpoint.
    assert verdict.observed_model_id == "ds/deepseek-flash"


def test_synthetic_fixture_binds():
    verdict = _verdict(fx.build_export())
    assert verdict.ok, verdict.reason
    assert verdict.qualified_model_id == fx.REQUESTED


# ---------------------------------------------------------------------------
# Strict binding / fail-closed
# ---------------------------------------------------------------------------
def test_forged_session_is_gap():
    verdict = _verdict(fx.build_export(session="ses_other"))
    assert verdict.reason == "export_session_mismatch"


def test_missing_export_session_is_gap():
    export = fx.build_export()
    export["info"]["id"] = None
    assert _verdict(export).reason == "export_missing_session"


def test_forged_message_id_is_gap():
    verdict = _verdict(fx.build_export(message="msg_forged"))
    assert verdict.reason == "export_message_unbound"


def test_forged_model_has_no_blind_suffix_match():
    assert _verdict(fx.build_export(model="deepseek-flash")).reason == "model_mismatch"
    assert _verdict(fx.build_export(model="ds/deepseek-flash-4.1")).reason == "model_mismatch"


def test_forged_provider_is_gap():
    assert _verdict(fx.build_export(provider="other")).reason == "model_mismatch"


def test_user_role_only_is_ambiguous():
    verdict = _verdict(fx.build_export(role="user"))
    assert verdict.reason == "ambiguous_assistant_identity"


def test_extra_assistant_message_is_ambiguous():
    export = fx.build_export()
    export["messages"].append(fx.build_export(message="msg_second")["messages"][1])
    assert _verdict(export).reason == "ambiguous_assistant_identity"


def test_text_conflict_is_gap():
    assert _verdict(fx.build_export(text='{"ok":false}')).reason == "text_conflict"


def test_completion_conflict_is_gap():
    assert _verdict(fx.build_export(finish="length")).reason == "completion_conflict"


def test_usage_conflict_is_gap():
    bad = {"total": 999, "input": 194, "output": 6, "reasoning": 13,
           "cache": {"write": 0, "read": 0}}
    assert _verdict(fx.build_export(tokens=bad)).reason == "usage_conflict"


def test_missing_model_metadata_is_gap():
    export = fx.build_export()
    export["messages"][1]["info"].pop("modelID")
    export["messages"][1]["info"].pop("providerID")
    assert _verdict(export).reason == "export_missing_model_metadata"


def test_part_binding_failure_is_gap():
    export = fx.build_export()
    export["messages"][1]["parts"] = [
        part for part in export["messages"][1]["parts"]
        if part.get("id") != fx.PART_TEXT]
    assert _verdict(export).reason == "export_part_binding_failed"


def test_ambiguous_raw_messages_is_gap():
    lines = [
        fx.raw_events()[0],
        json.dumps({"type": "text", "sessionID": fx.SESSION,
                    "part": {"id": "prt_a", "messageID": "msg_a", "type": "text",
                             "text": '{"ok":true}'}}),
        json.dumps({"type": "text", "sessionID": fx.SESSION,
                    "part": {"id": "prt_b", "messageID": "msg_b", "type": "text",
                             "text": ""}}),
        fx.raw_events()[2],
    ]
    parsed = _parsed(lines)
    assert _verdict(fx.build_export(), parsed=parsed, requested=fx.REQUESTED).reason \
        == "ambiguous_assistant_identity"


# ---------------------------------------------------------------------------
# R1: assistant session id and per-part session/message binding
# ---------------------------------------------------------------------------
def test_assistant_session_missing_is_gap():
    export = fx.build_export()
    export["messages"][1]["info"]["sessionID"] = None
    assert _verdict(export).reason == "export_missing_assistant_session"


def test_assistant_session_wrong_is_gap():
    export = fx.build_export()
    export["messages"][1]["info"]["sessionID"] = "ses_wrong"
    assert _verdict(export).reason == "export_assistant_session_mismatch"


def test_part_message_wrong_is_gap():
    export = fx.build_export()
    export["messages"][1]["parts"][2]["messageID"] = "msg_wrong"
    assert _verdict(export).reason == "export_part_message_mismatch"


def test_part_session_wrong_is_gap():
    export = fx.build_export()
    export["messages"][1]["parts"][0]["sessionID"] = "ses_wrong"
    assert _verdict(export).reason == "export_part_session_mismatch"


def test_part_message_missing_is_gap():
    export = fx.build_export()
    export["messages"][1]["parts"][1].pop("messageID")
    assert _verdict(export).reason == "export_part_unbound"


def test_duplicate_part_id_is_gap():
    export = fx.build_export()
    duplicate = dict(export["messages"][1]["parts"][2])
    export["messages"][1]["parts"].append(duplicate)
    assert _verdict(export).reason == "duplicate_part_id"


# ---------------------------------------------------------------------------
# R1: explicitly invalid token components are rejected before comparison
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("tokens", [
    {"input": -1, "output": 6, "reasoning": 13, "total": 213},
    {"input": True, "output": 6, "reasoning": 13, "total": 213},
    {"input": 1.5, "output": 6, "reasoning": 13, "total": 213},
    {"input": "5", "output": 6, "reasoning": 13, "total": 213},
    {"input": 194, "output": 6, "reasoning": 13, "total": -5},
    {"input": 194, "output": 6, "reasoning": 13, "total": 213,
     "cache": {"read": -1, "write": 0}},
    {"input": 194, "output": 6, "reasoning": 13, "total": 213, "cache": -1},
])
def test_invalid_export_token_is_gap(tokens):
    assert _verdict(fx.build_export(tokens=tokens)).reason == "invalid_export_usage"


def test_invalid_export_token_never_silently_accepted():
    # A negative component must not be dropped into "unknown" and pass.
    export = fx.build_export(tokens={"input": -1, "total": 213})
    assert provenance.invalid_token_components(export["messages"][1]["info"]["tokens"]) \
        == ("input",)


def test_missing_raw_session_is_gap():
    lines = [
        json.dumps({"type": "text",
                    "part": {"id": fx.PART_TEXT, "messageID": fx.MESSAGE,
                             "type": "text", "text": '{"ok":true}'}}),
        json.dumps({"type": "step_finish",
                    "part": {"id": fx.PART_FINISH, "reason": "stop",
                             "messageID": fx.MESSAGE, "type": "step-finish",
                             "tokens": dict(fx.DEFAULT_TOKENS)}}),
    ]
    parsed = _parsed(lines)
    assert parsed.session_id is None
    assert _verdict(fx.build_export(), parsed=parsed).reason == "unknown_session_provenance"


# ---------------------------------------------------------------------------
# Tokens: missing components stay unknown; explicit zeros are kept
# ---------------------------------------------------------------------------
def test_missing_export_component_does_not_conflict():
    export = fx.build_export(tokens={"total": 213})
    assert _verdict(export).ok


def test_explicit_zero_on_both_sides_is_kept():
    tokens = {"input": 0, "output": 0, "reasoning": 0,
              "cache": {"read": 0, "write": 0}, "total": 0}
    parsed = _parsed(fx.raw_events(tokens=tokens))
    assert _verdict(fx.build_export(tokens=tokens), parsed=parsed).ok


def test_malformed_export_bytes_raise():
    with pytest.raises(provenance.ProvenanceError):
        provenance.parse_session_export_bytes(b"not json")
    with pytest.raises(provenance.ProvenanceError):
        provenance.parse_session_export_bytes(json.dumps([1, 2, 3]).encode())


def test_qualified_model_id_is_provider_slash_model():
    assert provenance.qualified_model_id("aibox", "ds/deepseek-flash") == fx.REQUESTED


def test_sidecar_metadata_source_label():
    export = provenance.parse_session_export(fx.build_export())
    verdict = provenance.validate_observation_export(
        _parsed(fx.raw_events()), export, fx.REQUESTED)
    meta = provenance.build_sidecar_metadata(
        export=export, verdict=verdict, requested_model_id=fx.REQUESTED,
        export_path="e.json", export_sha256="deadbeef", captured=True)
    assert meta["source"] == "OpenCode session metadata"
    assert meta["qualified_model_id"] == fx.REQUESTED
    assert meta["assistant_tokens"]["total"] == 213
    assert meta["captured"] is True
