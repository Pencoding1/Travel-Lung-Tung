"""Regression: the ReAct loop must return the turn's messages for memory commit.

`main.py` commits ``result.get("turn_messages", [])`` into working memory. Before
this test, ``chat_agent._result`` accepted ``turn_messages`` but never put it in
the returned dict, so every turn after the first was composed from the bare user
message: the assistant reply and tool results were silently dropped from history.
"""

import asyncio

from domains import chat_agent

from helpers_chat_memory import ScriptedModel, ScriptedTools, ok_json, model_message


def test_result_carries_turn_messages_from_the_loop():
    responses = [model_message("Xin chào, đây là gợi ý.")]
    messages = [{"role": "system", "content": "sys"},
                {"role": "user", "content": "quán cà phê ở Quận 1"}]
    result = asyncio.run(chat_agent.run_agent_loop(
        messages=messages,
        tool_specs=[],
        known_tool_names=set(),
        call_model=ScriptedModel(responses),
        call_tool=ScriptedTools({}),
        max_turns=4,
        max_tool_calls=4,
    ))
    turn_messages = result.get("turn_messages")
    assert turn_messages, "turn_messages must reach the caller for commit()"
    assert any(m.get("role") == "assistant" for m in turn_messages)


def test_tool_turn_keeps_assistant_and_tool_messages():
    tool_payload = ok_json({"success": True, "matches": [
        {"id": "d1", "name": "District 1", "type": "District"}]})
    responses = [
        model_message("", tool_calls=[{
            "id": "c1", "type": "function",
            "function": {"name": "resolve_geographic_id",
                         "arguments": '{"keyword": "District 1"}'}}]),
        model_message("Đây là Quận 1."),
    ]
    messages = [{"role": "system", "content": "sys"},
                {"role": "user", "content": "POI ở Quận 1"}]
    result = asyncio.run(chat_agent.run_agent_loop(
        messages=messages,
        tool_specs=[],
        known_tool_names={"resolve_geographic_id"},
        call_model=ScriptedModel(responses),
        call_tool=ScriptedTools({"resolve_geographic_id": lambda args: tool_payload}),
        max_turns=4,
        max_tool_calls=4,
    ))
    roles = [m.get("role") for m in result.get("turn_messages") or []]
    assert "tool" in roles
    assert roles.count("assistant") >= 1


def test_public_response_never_exposes_turn_messages():
    """The HTTP payload is built field by field; turn_messages stays internal."""
    import ast
    from pathlib import Path

    source = (Path(__file__).resolve().parents[2] / "ai_service/main.py").read_text(
        encoding="utf-8")
    tree = ast.parse(source)
    response_keys = None
    for node in ast.walk(tree):
        if not isinstance(node, ast.AnnAssign):
            continue
        target = node.target
        if not (isinstance(target, ast.Name) and target.id == "response"):
            continue
        value = node.value
        if isinstance(value, ast.Dict):
            response_keys = {k.value for k in value.keys
                             if isinstance(k, ast.Constant) and isinstance(k.value, str)}
            break
    assert response_keys, "response dict literal not found in main.py"
    assert "turn_messages" not in response_keys
    assert "tool_messages" not in response_keys
