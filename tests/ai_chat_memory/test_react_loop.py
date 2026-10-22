"""Bounded ReAct loop contract tests (OC-009).

Direct tests of ``domains.chat_agent.run_agent_loop`` with injected fakes.
"""

import asyncio
import json

import pytest
from domains import chat_agent

from helpers_chat_memory import (
    ScriptedModel,
    ScriptedTools,
    err_json,
    model_message,
    ok_json,
    tool_call,
)


def _poi_handler(pid="poi_a"):
    return lambda args: ok_json(
        {"success": True, "result": {"POI_ID": pid, "POI_Name": pid}})


def _run_loop(responses, handlers, tools=("resolve_geographic_id", "get_poi_details"),
              max_turns=chat_agent.MAX_TURNS,
              max_tool_calls=chat_agent.MAX_TOOL_CALLS,
              initial_tool_requests=None):
    messages = [{"role": "system", "content": "sys"},
                {"role": "user", "content": "cafes in District 1"}]
    model = ScriptedModel(responses)
    tools_obj = ScriptedTools(handlers)
    result = asyncio.run(chat_agent.run_agent_loop(
        messages=messages,
        tool_specs=[],
        known_tool_names=set(tools),
        call_model=model,
        call_tool=tools_obj,
        max_turns=max_turns,
        max_tool_calls=max_tool_calls,
        initial_tool_requests=initial_tool_requests,
    ))
    return result, messages, model, tools_obj


def test_two_tools_then_second_model_answer():
    responses = [
        model_message(tool_calls=[
            tool_call("resolve_geographic_id", {"keyword": "District 1"}, "c1"),
            tool_call("get_poi_details", {"poi_id": "poi_a"}, "c2"),
        ]),
        model_message(content="Here are the cafes.",
                      usage={"prompt_tokens": 10, "completion_tokens": 5,
                             "total_tokens": 15}),
    ]
    handlers = {
        "resolve_geographic_id": lambda args: ok_json(
            {"success": True,
             "matches": [{"id": "quan_1", "name": "District 1",
                          "type": "District"}]}),
        "get_poi_details": _poi_handler("poi_a"),
    }

    result, messages, model, tools_obj = _run_loop(responses, handlers)

    assert result["status"] == "success"
    assert result["reply"] == "Here are the cafes."
    assert len(result["tool_chain"]) == 2
    # The loop iterated after the tool results: a *second* model call happened.
    assert len(model.calls) == 2
    assert result["grounding_status"] == chat_agent.GROUNDING_UNVERIFIED_FREE_TEXT
    assert "poi_a" in result["source_evidence_ids"]
    assert result["usage"]["total_tokens"] == 15
    assert result["usage"]["model_calls"] == 2
    tool_msgs = [m for m in messages if m.get("role") == "tool"]
    assert {m["tool_call_id"] for m in tool_msgs} == {"c1", "c2"}


def test_server_bootstrap_runs_before_the_model_and_pairs_its_tool_message():
    responses = [model_message(content="Here are the cafes.")]
    handlers = {"explore_pois": lambda args: ok_json(
        {"success": True, "results": [{"id": "poi_a", "POI_Name": "A"}]})}
    result, messages, model, tools_obj = _run_loop(
        responses, handlers, tools=("explore_pois",), max_tool_calls=1,
        initial_tool_requests=[{"name": "explore_pois",
                                "arguments": {"limit": 12}}])

    assert result["status"] == chat_agent.STATUS_SUCCESS
    assert len(model.calls) == 1
    assert tools_obj.calls == [{"tool": "explore_pois",
                                "args": {"limit": 12}}]
    assert result["tool_chain"][0]["origin"] == "server_bootstrap"
    assert result["source_evidence_ids"] == ["poi_a"]
    assert result["usage"]["model_calls"] == 1
    assistant = [m for m in messages if m.get("role") == "assistant"][0]
    tool_msg = [m for m in messages if m.get("role") == "tool"][0]
    assert assistant["tool_calls"][0]["id"].startswith(
        "call_server_bootstrap_")
    assert assistant["tool_calls"][0]["id"] == tool_msg["tool_call_id"]
    # The real model turn still sees the server evidence before it answers.
    assert any(message.get("role") == "tool" and "poi_a" in message.get("content")
               for message in model.calls[0]["messages"])


def test_server_bootstrap_without_evidence_returns_before_the_model():
    handlers = {"explore_pois": lambda args: ok_json(
        {"success": True, "results": []})}
    result, messages, model, tools_obj = _run_loop(
        [], handlers, tools=("explore_pois",), max_tool_calls=1,
        initial_tool_requests=[{"name": "explore_pois",
                                "arguments": {"limit": 12}}])

    assert result["status"] == chat_agent.STATUS_INSUFFICIENT
    assert model.calls == []
    assert len(tools_obj.calls) == 1
    assert result["tool_chain"][0]["origin"] == "server_bootstrap"
    assert result["source_evidence_ids"] == []
    assistant = [m for m in messages if m.get("role") == "assistant"][0]
    tool_msg = [m for m in messages if m.get("role") == "tool"][0]
    assert assistant["tool_calls"][0]["id"] == tool_msg["tool_call_id"]


def test_server_bootstrap_consumes_the_tool_budget_truthfully():
    responses = [model_message(tool_calls=[tool_call(
        "get_poi_details", {"poi_id": "poi_a"}, "c1")])]
    handlers = {
        "explore_pois": lambda args: ok_json(
            {"success": True, "results": [{"id": "poi_a"}]}),
        "get_poi_details": _poi_handler(),
    }
    result, messages, model, tools_obj = _run_loop(
        responses, handlers, tools=("explore_pois", "get_poi_details"),
        max_tool_calls=1,
        initial_tool_requests=[{"name": "explore_pois",
                                "arguments": {"limit": 12}}])

    assert result["status"] == chat_agent.STATUS_PARTIAL
    assert result["loop_limit"] is True
    assert len(model.calls) == 1
    assert [call["tool"] for call in tools_obj.calls] == ["explore_pois"]
    assert result["tool_chain"][0]["origin"] == "server_bootstrap"


def test_missing_tool_call_ids_are_normalized_and_matched():
    responses = [
        {"choices": [{"message": {"tool_calls": [
            {"type": "function",
             "function": {"name": "get_poi_details",
                          "arguments": '{"poi_id": "poi_a"}'}}]}}]},
        model_message(content="done"),
    ]
    result, messages, model, tools_obj = _run_loop(
        responses, {"get_poi_details": _poi_handler()})

    assert result["status"] == "success"
    assistant = [m for m in messages if m.get("role") == "assistant"][0]
    tool_msg = [m for m in messages if m.get("role") == "tool"][0]
    assert assistant["tool_calls"][0]["id"] == tool_msg["tool_call_id"]
    assert tool_msg["tool_call_id"]


def test_five_turn_exhaustion_is_explicit_partial():
    responses = [
        model_message(tool_calls=[
            tool_call("get_poi_details", {"poi_id": "poi_a"}, f"c{i}")])
        for i in range(5)
    ]
    result, messages, model, tools_obj = _run_loop(
        responses, {"get_poi_details": _poi_handler()})

    assert result["status"] == chat_agent.STATUS_PARTIAL
    assert result["loop_limit"] is True
    assert result["reply"] == chat_agent.LOOP_LIMIT_MESSAGE
    assert len(model.calls) == 5


def test_tool_budget_does_not_orphan_tools():
    responses = [
        model_message(tool_calls=[
            tool_call("get_poi_details", {"poi_id": "poi_a"}, "c1"),
            tool_call("get_poi_details", {"poi_id": "poi_b"}, "c2"),
            tool_call("get_poi_details", {"poi_id": "poi_c"}, "c3"),
        ]),
    ]
    result, messages, model, tools_obj = _run_loop(
        responses, {"get_poi_details": _poi_handler()}, max_tool_calls=2)

    assert result["status"] == chat_agent.STATUS_PARTIAL
    assert len(tools_obj.calls) == 2
    assistant = [m for m in messages if m.get("role") == "assistant"][0]
    tool_msgs = [m for m in messages if m.get("role") == "tool"]
    # Every recorded tool result still maps to an emitted tool_call id.
    assistant_ids = {tc["id"] for tc in assistant["tool_calls"]}
    assert {m["tool_call_id"] for m in tool_msgs} <= assistant_ids


def test_unknown_tool_is_refused_and_never_executed():
    responses = [model_message(tool_calls=[tool_call("delete_everything", {})]),
                 model_message(content="fallback answer")]
    result, messages, model, tools_obj = _run_loop(
        responses, {}, tools=("get_poi_details",))

    assert tools_obj.calls == []
    assert result["status"] == chat_agent.STATUS_INSUFFICIENT
    assert result["tool_chain"][0]["status"] == "failed"
    assert result["tool_chain"][0]["summary"] == "unknown_tool"
    # Arbitrary model-supplied names must not appear in the trusted trace.
    assert result["tool_chain"][0]["tool"] == "rejected_tool"
    # Scoped to the trusted trace: the internal result now also carries
    # turn_messages (needed for the memory commit), which legitimately contains
    # the model's own tool call. The HTTP response is built field by field and
    # never exposes it (asserted in test_turn_messages_commit.py).
    assert "delete_everything" not in json.dumps(result["tool_chain"])


def test_budget_exhaustion_answers_every_announced_call():
    responses = [model_message(tool_calls=[
        tool_call("get_poi_details", {"poi_id": "a"}, "c1"),
        tool_call("get_poi_details", {"poi_id": "b"}, "c2"),
        tool_call("get_poi_details", {"poi_id": "c"}, "c3"),
    ])]
    result, messages, model, tools_obj = _run_loop(
        responses, {"get_poi_details": _poi_handler()}, max_tool_calls=2)

    assistant = [m for m in messages if m.get("role") == "assistant"][0]
    announced = {tc["id"] for tc in assistant["tool_calls"]}
    answered = {m["tool_call_id"] for m in messages if m.get("role") == "tool"}
    assert announced == answered
    assert len(assistant["tool_calls"]) == 2
    assert result["status"] == chat_agent.STATUS_PARTIAL


def test_duplicate_call_ids_are_made_unique_and_answered():
    responses = [
        model_message(tool_calls=[
            tool_call("get_poi_details", {"poi_id": "a"}, "dup"),
            tool_call("get_poi_details", {"poi_id": "b"}, "dup"),
        ]),
        model_message(content="done"),
    ]
    result, messages, model, tools_obj = _run_loop(
        responses, {"get_poi_details": _poi_handler()})

    assistant = [m for m in messages if m.get("role") == "assistant"][0]
    ids = [tc["id"] for tc in assistant["tool_calls"]]
    assert len(ids) == len(set(ids))
    answered = [m["tool_call_id"] for m in messages if m.get("role") == "tool"]
    assert set(ids) == set(answered)


def test_malformed_call_entries_are_dropped_not_orphaned():
    raw = {"choices": [{"message": {"content": "answer", "tool_calls": [
        "not-a-dict",
        {"id": "c1"},
        {"id": "c2", "function": "nope"},
        {"id": "c3", "function": {"name": ""}},
        {"id": "c4", "function": {"name": "get_poi_details", "arguments": "{}"}},
    ]}}]}
    responses = [raw, model_message(content="done")]
    result, messages, model, tools_obj = _run_loop(
        responses, {"get_poi_details": _poi_handler()})

    assistant = [m for m in messages if m.get("role") == "assistant"][0]
    assert len(assistant["tool_calls"]) == 1
    answered = [m["tool_call_id"] for m in messages if m.get("role") == "tool"]
    assert answered == ["c4"]


def test_metadata_only_results_are_not_usable_evidence():
    responses = [
        model_message(tool_calls=[
            tool_call("resolve_geographic_id", {"keyword": "District 1"})]),
        model_message(content="Here are the cafes I recommend!"),
    ]
    handlers = {"resolve_geographic_id": lambda a: ok_json(
        {"success": True,
         "matches": [{"id": "quan_1", "name": "District 1", "type": "District"}]})}
    result, messages, model, tools_obj = _run_loop(
        responses, handlers, tools=("resolve_geographic_id",))

    assert result["status"] == chat_agent.STATUS_INSUFFICIENT
    assert result["source_evidence_ids"] == []
    assert result["tool_chain"][0]["status"] == "success"
    assert result["tool_chain"][0]["summary"] == "no_poi_evidence"


def test_category_only_results_are_not_usable_evidence():
    responses = [
        model_message(tool_calls=[tool_call("get_available_categories", {})]),
        model_message(content="Try these categories!"),
    ]
    handlers = {"get_available_categories": lambda a: ok_json(
        {"success": True, "categories": [{"id": "cat_coffee", "name": "Cafe"}]})}
    result, messages, model, tools_obj = _run_loop(
        responses, handlers, tools=("get_available_categories",))

    assert result["status"] == chat_agent.STATUS_INSUFFICIENT
    assert result["source_evidence_ids"] == []


def test_malformed_arguments_are_refused_and_never_executed():
    responses = [model_message(tool_calls=[
        tool_call("get_poi_details", '{"poi_id": ')  # invalid JSON
    ]), model_message(content="fallback answer")]
    result, messages, model, tools_obj = _run_loop(responses, {})

    assert tools_obj.calls == []
    assert result["tool_chain"][0]["summary"] == "malformed_arguments"
    assert result["status"] == chat_agent.STATUS_INSUFFICIENT


def test_non_object_arguments_are_rejected():
    responses = [model_message(tool_calls=[
        tool_call("get_poi_details", '["poi_a"]')  # valid JSON, not an object
    ]), model_message(content="fallback")]
    result, messages, model, tools_obj = _run_loop(
        responses, {"get_poi_details": _poi_handler()})

    assert tools_obj.calls == []
    assert result["tool_chain"][0]["summary"] == "malformed_arguments"


def test_empty_model_response_fails_sanitized():
    result, messages, model, tools_obj = _run_loop(
        [model_message(content="   ")], {})

    assert result["status"] == chat_agent.STATUS_FAILED
    assert result["error"]["code"] == "invalid_model_response"
    assert "Traceback" not in str(result)


def test_model_transport_failure_is_structured():
    async def boom(messages, tools):
        raise TimeoutError("simulated timeout")

    messages = [{"role": "user", "content": "hi"}]
    result = asyncio.run(chat_agent.run_agent_loop(
        messages=messages, tool_specs=[], known_tool_names=set(),
        call_model=boom, call_tool=ScriptedTools({})))

    assert result["status"] == chat_agent.STATUS_FAILED
    assert result["error"]["code"] == "model_unavailable"
    assert "simulated timeout" not in str(result)
    assert result["usage"]["model_calls"] == 1
    assert result["usage"]["total_tokens"] is None


def test_error_envelope_success_false_is_not_usable():
    responses = [
        model_message(tool_calls=[
            tool_call("get_poi_details", {"poi_id": "poi_x"})]),
        model_message(content="Here are some places I know about!"),
    ]
    handlers = {"get_poi_details": lambda a: ok_json(
        {"success": False, "result": None, "detail": "not found"})}
    result, messages, model, tools_obj = _run_loop(responses, handlers)

    assert result["tool_chain"][0]["status"] == "failed"
    assert result["status"] == chat_agent.STATUS_INSUFFICIENT
    assert result["reply"] == chat_agent.INSUFFICIENT_DATA_MESSAGE


def test_iserror_envelope_fails_closed():
    responses = [
        model_message(tool_calls=[
            tool_call("get_poi_details", {"poi_id": "poi_a"})]),
        model_message(content="answer"),
    ]
    handlers = {"get_poi_details": lambda a: err_json(
        {"success": True, "result": {"POI_ID": "poi_a"}})}
    result, messages, model, tools_obj = _run_loop(responses, handlers)

    assert result["tool_chain"][0]["status"] == "failed"
    assert result["status"] == chat_agent.STATUS_INSUFFICIENT


def test_empty_retrieval_does_not_hallucinate():
    responses = [
        model_message(tool_calls=[tool_call("explore_pois", {"city_id": "x"})]),
        model_message(content="Here are the top cafes I recommend!"),
    ]
    handlers = {"explore_pois": lambda a: ok_json(
        {"success": True, "count": 0, "results": []})}
    result, messages, model, tools_obj = _run_loop(
        responses, handlers, tools=("explore_pois",))

    assert result["status"] == chat_agent.STATUS_INSUFFICIENT
    assert result["grounding_status"] == chat_agent.GROUNDING_INSUFFICIENT
    assert result["reply"] == chat_agent.INSUFFICIENT_DATA_MESSAGE
    assert result["source_evidence_ids"] == []


def test_usage_unknown_stays_null_not_zero():
    responses = [
        model_message(tool_calls=[tool_call("get_poi_details", {"poi_id": "a"})]),
        model_message(content="ok"),
    ]
    result, messages, model, tools_obj = _run_loop(
        responses, {"get_poi_details": _poi_handler("a")})
    assert result["usage"]["total_tokens"] is None
    assert result["usage"]["input_tokens"] is None
    assert result["usage"]["char_estimate"] >= 0
    assert "not" in result["usage"]["char_estimate_label"].lower()
