"""Actual ASGI/service paths with the fake CLI transport injected at the seam."""

import asyncio
import json
import sys

import httpx
import main
import pytest
from domains import jev_intent
from httpx import ASGITransport, AsyncClient

from helpers_provider import (FakeChatMCPSession, ItineraryMCPSession,
                              REQUESTED, ScenarioRunner, itinerary_handlers,
                              mcp_seam, plan_text)

JEV_INPUT_TOKENS = 4
JEV_OUTPUT_TOKENS = 1


def _jev_response(choice="TRAVEL"):
    probabilities = {"CHITCHAT": 0.05, "TRAVEL": 0.05, "UNCERTAIN": 0.05}
    probabilities[choice] = 0.9
    return {
        "model": "jev-test-1",
        "answers": {"intent": {
            "type": "choice",
            "choice": choice,
            "probabilities": probabilities,
            "confidence": 0.9,
        }},
        "usage": {"input_tokens": JEV_INPUT_TOKENS,
                  "output_tokens": JEV_OUTPUT_TOKENS},
    }


def install_fake_jev(choice="TRAVEL"):
    """Inject a canned Jev transport; never fake it through Gemini/CLI."""
    payload = _jev_response(choice)

    def handler(request):
        return httpx.Response(200, json=payload)

    return jev_intent.configure_intent_router(
        {"TYPESAFE_API_KEY": "dummy-test-key",
         "JEV_MIN_CONFIDENCE": "0.5"},
        transport=httpx.MockTransport(handler))


@pytest.fixture(autouse=True)
def reset_provider():
    main.configure_provider({})
    main.configure_intent_router({})
    yield
    main.configure_provider({})
    main.configure_intent_router({})


def _call(method, path, body=None):
    async def _run():
        transport = ASGITransport(app=main.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, path, json=body)

    return asyncio.run(_run())


def _cli_runner(scenario):
    main.configure_provider(
        {"AI_LLM_PROVIDER": "opencode_cli",
         "AI_CLI_EXECUTABLE": sys.executable,
         "AI_CLI_AGENT": "oc040-test-agent",
         # The installed CLI has no --pure; exercise the transport explicitly.
         "AI_CLI_PURE": "false"},
        cli_runner=scenario)
    return scenario


def _chat_body(message="hi", memory=False):
    return {"session_id": "s1", "message": message,
            "memory_enabled": memory}


VALID_ITINERARY = {
    "session_id": "sess-http",
    "current_city": "Ho Chi Minh City",
    "travel_type": "self-explore",
    "num_travelers": 2,
    "start_date": "2026-01-01",
    "target_district": "District 1",
    "duration_days": 1,
    "budget_range": "500000-1500000 VND",
    "user_description": "quiet cafes",
}


def test_default_gemini_selection_is_unchanged(monkeypatch):
    payloads = []
    install_fake_jev(choice="CHITCHAT")

    async def fake_gemini(payload):
        payloads.append(payload)
        return {"choices": [{"message": {"content": "Hi from Gemini"}}]}

    monkeypatch.setattr(main, "gemini_chat_completion", fake_gemini)
    response = _call("POST", "/chat", _chat_body("hello"))

    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == "Hi from Gemini"
    assert body["model"] == main.GEMINI_MODEL
    assert body["provider"]["selected"] == "gemini"
    assert body["provider"]["identity_source"] == "requested_only"
    # Jev is not a generation call: only the chitchat completion remains here.
    assert len(payloads) == 1
    assert payloads[0]["max_completion_tokens"] == 500
    assert body["usage"]["model_calls"] == 2
    assert body["router"]["provider"] == "typesafe"


def test_cli_chat_travel_executes_server_tool_and_uses_observed_identity(monkeypatch):
    session = FakeChatMCPSession()
    monkeypatch.setattr(main, "open_mcp_session", mcp_seam(session))
    install_fake_jev(choice="TRAVEL")
    scenario = _cli_runner(ScenarioRunner())

    response = _call("POST", "/chat", _chat_body("cafes in District 1"))
    assert response.status_code == 200
    body = response.json()

    assert body["intent"] == "TRAVEL"
    assert body["status"] == "success"
    assert body["reply"] == "Here is the cafe."
    assert body["model"] == REQUESTED
    assert body["provider"]["selected"] == "opencode_cli"
    assert body["provider"]["observed_model"] == REQUESTED
    assert body["provider"]["display_name"] == "DeepSeek V4.1 Flash"
    assert body["provider"]["upstream_version_verified"] is False
    # Jev is reported under router; provider.calls contains only generation.
    assert len(body["provider"]["calls"]) == 2
    assert all(call["observed_model"] == REQUESTED
               for call in body["provider"]["calls"])
    assert body["router"]["provider"] == "typesafe"
    assert [call["args"] for call in session.calls] == [{"poi_id": "poi_a"}]
    assert "poi_a" in body["source_evidence_ids"]
    # Generation calls: prompt 11, completion 5 each. Jev contributes its own
    # reported input/output; no total is documented for either Jev response.
    assert body["usage"]["input_tokens"] == 2 * 11 + JEV_INPUT_TOKENS
    assert body["usage"]["output_tokens"] == 2 * 5 + JEV_OUTPUT_TOKENS
    assert body["usage"]["total_tokens"] is None
    assert body["usage"]["known_subtotals"]["total_tokens"] == 32
    assert body["usage"]["model_calls"] == 3
    assert len(scenario.runs) == 2
    assert len(scenario.export_calls) == 2
    temperatures = []
    for call in scenario.runs:
        config = json.loads(call["transport_config"])
        temperatures.append(
            config["providers"]["aibox"]["models"]["ds/deepseek-flash"]
            ["body"]["temperature"])
    assert temperatures == [0.3, 0.3]
    controls = body["provider"]["calls"][0]["controls"]
    assert controls["requested"] == {"temperature": 0.3}
    assert controls["configured"] == {"temperature": 0.3}
    # The transport cannot see the outbound provider body: applied is never
    # claimed here; the loopback QA is the observation point.
    assert controls["applied"] is False
    assert controls["verification"] == "not_observable_from_transport"
    assert controls["binding"] == "provider_model_request_body"
    assert "max-token caps are not supported" in body["provider"]["controls_note"]
    assert body["provider"]["unsupported_controls"][0]["name"] == \
        "max_completion_tokens"


def test_cli_chitchat_uses_plain_text_and_no_tools(monkeypatch):
    session = FakeChatMCPSession()
    monkeypatch.setattr(main, "open_mcp_session", mcp_seam(session))
    install_fake_jev(choice="CHITCHAT")
    scenario = _cli_runner(ScenarioRunner())

    body = _call("POST", "/chat", _chat_body("hello there")).json()
    assert body["intent"] == "CHITCHAT"
    assert body["reply"] == "Hello!"
    assert body["tool_chain"] == []
    assert session.calls == []
    assert len(body["provider"]["calls"]) == 1
    assert body["usage"]["model_calls"] == 2
    temperatures = []
    for call in scenario.runs:
        config = json.loads(call["transport_config"])
        temperatures.append(
            config["providers"]["aibox"]["models"]["ds/deepseek-flash"]
            ["body"]["temperature"])
    assert temperatures == [0.7]


def test_cli_unknown_tool_is_rejected_through_the_actual_loop(monkeypatch):
    session = FakeChatMCPSession()
    monkeypatch.setattr(main, "open_mcp_session", mcp_seam(session))
    install_fake_jev(choice="TRAVEL")
    _cli_runner(ScenarioRunner(tool_envelope=json.dumps({
        "tool_calls": [{"id": "call_1", "name": "not_a_tool",
                        "arguments": {}}]})))

    body = _call("POST", "/chat", _chat_body("cafes")).json()
    assert body["status"] == "failed"
    assert body["error"]["code"] == "model_unavailable"
    assert session.calls == []
    error_codes = [call.get("error_code") for call in body["provider"]["calls"]]
    assert "unknown_tool" in error_codes


def test_invalid_configuration_is_observable_and_never_falls_back(monkeypatch):
    session = FakeChatMCPSession()
    monkeypatch.setattr(main, "open_mcp_session", mcp_seam(session))
    install_fake_jev(choice="CHITCHAT")
    main.configure_provider({"AI_LLM_PROVIDER": "bogus"})

    body = _call("POST", "/chat", _chat_body("hello")).json()
    assert body["status"] == "failed"
    assert body["error"]["code"] == "model_unavailable"
    assert body["provider"]["selected"] == "invalid"
    assert body["provider"]["config_error"]["code"] == "invalid_provider_config"
    assert session.calls == []


def test_missing_cli_is_a_bounded_model_unavailable_error(monkeypatch):
    session = FakeChatMCPSession()
    monkeypatch.setattr(main, "open_mcp_session", mcp_seam(session))
    install_fake_jev(choice="CHITCHAT")
    main.configure_provider({
        "AI_LLM_PROVIDER": "opencode_cli",
        "AI_CLI_EXECUTABLE": "definitely-missing-oc040.exe",
    }, cli_runner=ScenarioRunner())

    body = _call("POST", "/chat", _chat_body("hello")).json()
    assert body["status"] == "failed"
    assert body["error"]["code"] == "model_unavailable"
    error_codes = [call.get("error_code") for call in body["provider"]["calls"]]
    assert "cli_not_found" in error_codes


def test_cli_invalid_nested_tool_arguments_never_reach_mcp(monkeypatch):
    session = FakeChatMCPSession()
    monkeypatch.setattr(main, "open_mcp_session", mcp_seam(session))
    install_fake_jev(choice="TRAVEL")
    _cli_runner(ScenarioRunner(tool_envelope=json.dumps({
        "tool_calls": [{"id": "call_1", "name": "get_poi_details",
                        "arguments": {"poi_id": True}}]})))

    body = _call("POST", "/chat", _chat_body("cafes")).json()
    assert body["status"] == "failed"
    assert body["error"]["code"] == "model_unavailable"
    assert session.calls == []
    assert any(call.get("error_code") == "invalid_tool_arguments"
               for call in body["provider"]["calls"])


def test_cli_itinerary_planning_json_stays_content(monkeypatch):
    session = ItineraryMCPSession(itinerary_handlers())
    monkeypatch.setattr(main, "open_mcp_session", mcp_seam(session))
    scenario = _cli_runner(ScenarioRunner(plan_text=plan_text()))

    response = _call("POST", "/generate_itinerary", VALID_ITINERARY)
    assert response.status_code == 200
    body = response.json()

    assert body["status"] == "success"
    assert body["reply"]["stops"][0]["poi"]["name"] == "Verified Cafe A"
    assert body["model"] == REQUESTED
    assert body["provider"]["observed_model"] == REQUESTED
    assert body["tool_chain"][-1]["tool"] == "OpenCode CLI Synthesis"
    assert body["tool_chain"][-1]["args"]["provider"] == "opencode_cli"
    assert body["tool_chain"][-1]["args"]["model"] == REQUESTED
    # One model call: prompt 11, completion 5, total 16 (planning.model_usage).
    assert body["planning"]["model_usage"]["input_tokens"] == 11
    assert body["planning"]["model_usage"]["output_tokens"] == 5
    assert body["planning"]["model_usage"]["total_tokens"] == 16
    run = scenario.runs[0]
    config = json.loads(run["transport_config"])
    assert (config["providers"]["aibox"]["models"]["ds/deepseek-flash"]
            ["body"]["temperature"] == 0.2)
