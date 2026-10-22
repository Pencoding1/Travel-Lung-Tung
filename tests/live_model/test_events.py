from __future__ import annotations

import json

from live_model.events import parse_event_lines

import fake_events as fe


def test_session_and_model_extraction():
    parsed = parse_event_lines([fe.step_start(), fe.model_event(), fe.text(value="{}"),
                                fe.step_finish()])
    assert parsed.session_id == fe.SESSION
    assert parsed.observed_model_ids == (fe.MODEL,)
    assert parsed.observed_provider_ids == (fe.PROVIDER,)
    assert parsed.terminal_present is True


def test_usage_preserved_separately():
    parsed = parse_event_lines([fe.step_finish(
        tokens={"total": 200, "input": 120, "output": 50, "reasoning": 7,
                "cache": {"write": 3, "read": 20}})])
    usage = parsed.usage
    assert usage is not None
    assert (usage.input_tokens, usage.output_tokens, usage.reasoning_tokens) == (120, 50, 7)
    assert (usage.cache_read_tokens, usage.cache_write_tokens) == (20, 3)
    assert usage.total_tokens == 200
    assert usage.partial is False


def test_missing_usage_stays_unknown():
    parsed = parse_event_lines([fe.step_finish(tokens=None)])
    assert parsed.usage is None


def test_partial_usage_flagged():
    with_tokens = json.dumps({"type": "step_finish", "sessionID": fe.SESSION,
                              "part": {"reason": "stop", "tokens": {"input": 1, "output": 2}}})
    without = json.dumps({"type": "step_finish", "sessionID": fe.SESSION,
                          "part": {"reason": "tool-calls"}})
    parsed = parse_event_lines([with_tokens, without])
    assert parsed.usage is not None and parsed.usage.partial is True


def test_malformed_and_truncated_lines_recorded():
    truncated = fe.step_finish()[:-5]
    parsed = parse_event_lines([fe.step_start(), truncated, "", "not json"])
    assert parsed.malformed_lines == (2, 4)
    assert parsed.line_count == 4


def test_tool_and_error_counts():
    parsed = parse_event_lines([fe.step_start(), fe.tool_use(name="bash"),
                                fe.error("boom"), fe.step_finish()])
    assert parsed.tool_use_count == 1
    assert parsed.tool_names == ("bash",)
    assert parsed.error_count == 1
    assert "boom" in parsed.error_messages


def test_missing_reason_is_not_success():
    parsed = parse_event_lines([fe.step_start(), fe.text(value="{}"),
                                fe.step_finish(reason="")])
    assert parsed.terminal_present is False
    assert "missing" in parsed.terminal_note


def test_absent_terminal_is_not_success():
    parsed = parse_event_lines([fe.step_start(), fe.text(value="{}")])
    assert parsed.terminal_present is False


def test_empty_token_block_is_unknown_not_zero():
    parsed = parse_event_lines([fe.step_finish(tokens={})])
    usage = parsed.usage
    assert usage is not None
    assert usage.input_tokens is None and usage.output_tokens is None
    assert usage.reasoning_tokens is None
    assert usage.cache_read_tokens is None and usage.cache_write_tokens is None
    assert usage.total_tokens is None
    assert usage.complete is False and usage.partial is True


def test_partial_token_block_does_not_fabricate_zeros():
    parsed = parse_event_lines([fe.step_finish(tokens={"input": 7})])
    usage = parsed.usage
    assert usage.input_tokens == 7
    assert usage.output_tokens is None and usage.reasoning_tokens is None
    assert usage.cache_read_tokens is None and usage.cache_write_tokens is None
    assert usage.total_tokens is None
    assert usage.partial is True


def test_explicit_zero_is_preserved():
    parsed = parse_event_lines([fe.step_finish(tokens={
        "input": 0, "output": 0, "reasoning": 0,
        "cache": {"read": 0, "write": 0}, "total": 0})])
    usage = parsed.usage
    assert usage.complete is True and usage.partial is False
    assert usage.input_tokens == 0 and usage.reasoning_tokens == 0
    assert usage.total_tokens == 0


def test_negative_and_bool_counts_are_rejected():
    parsed = parse_event_lines([fe.step_finish(tokens={"input": -5, "output": True, "total": 10})])
    usage = parsed.usage
    assert usage.input_tokens is None and usage.output_tokens is None
    assert usage.total_tokens == 10
    assert "input" in usage.invalid_fields and "output" in usage.invalid_fields


def test_multistep_aggregates_only_complete_components():
    parsed = parse_event_lines([
        fe.step_finish(reason="tool-calls", tokens={
            "input": 5, "output": 5, "reasoning": 0,
            "cache": {"read": 0, "write": 0}, "total": 10}),
        fe.step_finish(reason="stop", tokens={"input": 3}),
    ])
    usage = parsed.usage
    assert usage.input_tokens == 8          # complete across both steps
    assert usage.output_tokens is None      # missing in the second step -> unknown
    assert usage.reasoning_tokens is None
    assert usage.total_tokens is None
    assert usage.complete is False and usage.partial is True
    assert usage.lower_bounds["input"] == 8


def test_missing_token_block_makes_aggregate_unknown():
    parsed = parse_event_lines([
        fe.step_finish(tokens={"input": 5, "output": 5, "reasoning": 0,
                               "cache": {"read": 0, "write": 0}, "total": 10}),
        fe.step_finish(reason="stop", tokens=None),
    ])
    usage = parsed.usage
    assert usage.input_tokens is None and usage.partial is True
    assert usage.lower_bounds["input"] == 5


def test_provider_total_is_not_recomputed():
    parsed = parse_event_lines([fe.step_finish(tokens={
        "input": 10, "output": 5, "reasoning": 2,
        "cache": {"read": 3, "write": 0}, "total": 15})])
    assert parsed.usage.total_tokens == 15


def test_length_reason_is_not_terminal():
    parsed = parse_event_lines([fe.text(value="{}"), fe.step_finish(reason="length")])
    assert parsed.terminal_present is False
    assert "length" in parsed.terminal_note


def test_stop_then_incomplete_step_is_not_terminal():
    parsed = parse_event_lines([fe.text(value="{}"), fe.step_finish(reason="stop"),
                                fe.step_start(), fe.text(value="more")])
    assert parsed.terminal_present is False


def test_finish_before_text_is_not_terminal():
    parsed = parse_event_lines([fe.step_finish(reason="stop"), fe.text(value="{}")])
    assert parsed.terminal_present is False
    assert "text_after_terminal_finish" in parsed.terminal_note


def test_stop_after_text_is_terminal():
    parsed = parse_event_lines([fe.step_start(), fe.text(value="{}"),
                                fe.step_finish(reason="stop")])
    assert parsed.terminal_present is True
