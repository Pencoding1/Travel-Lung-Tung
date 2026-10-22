"""Strict request contract: source tuple + car/foot before any model or MCP.

The Pydantic models are exercised directly and through the real ASGI routes.
Fake collaborators raise if they are reached, so a rejection is proven to
happen before Jev, the model or MCP.
"""

import json

import httpx
import pytest
from domains import grounding
from domains.payloads import ChatRequest, ItineraryRequest
from helpers_core_flow import (
    SELECTION_A,
    chat_body,
    http_call,
    itinerary_body,
)

import main


def _valid_chat(**overrides):
    values = {
        "session_id": "s1",
        "message": "xin chào",
        "source_scope": dict(SELECTION_A),
        "transport_mode": "foot",
    }
    values.update(overrides)
    return ChatRequest(**values)


def test_chat_accepts_exact_tuple_and_foot():
    request = _valid_chat()
    assert request.transport_mode == "foot"
    assert request.source_scope.model_dump() == SELECTION_A


def test_chat_defaults_legacy_context():
    request = ChatRequest(session_id="s1", message="xin chào")
    assert request.transport_mode == "car"
    assert request.source_scope is None


@pytest.mark.parametrize("mode", ["Foot", "FOOT", " car", "car ", "", "walk", 1, True])
def test_chat_rejects_nonliteral_modes(mode):
    with pytest.raises(ValueError):
        _valid_chat(transport_mode=mode)


@pytest.mark.parametrize("scope", [
    {**SELECTION_A, "extra": "x"},
    {"dataset_namespace": SELECTION_A["dataset_namespace"],
     "input_sha256": SELECTION_A["input_sha256"]},
    {**SELECTION_A, "input_sha256": "A" * 64},
    {**SELECTION_A, "input_sha256": "a" * 63},
    {**SELECTION_A, "dataset_namespace": " hcm_primary_geojson"},
    {**SELECTION_A, "dataset_namespace": "hcm_primary_geojson "},
    {**SELECTION_A, "source_area_id": "quan_1"},
    {**SELECTION_A, "source_area_id": "source_area_v1:" + "B" * 64},
    {**SELECTION_A, "dataset_namespace": None},
    {**SELECTION_A, "source_area_id": ""},
])
def test_chat_rejects_malformed_source_scope(scope):
    with pytest.raises(ValueError):
        _valid_chat(source_scope=scope)


def test_itinerary_shares_the_same_strict_contract():
    base = dict(itinerary_body())
    request = ItineraryRequest(**base)
    assert request.transport_mode == "car"
    assert request.source_scope.model_dump() == SELECTION_A

    with pytest.raises(ValueError):
        ItineraryRequest(**{**base, "transport_mode": "Foot"})
    with pytest.raises(ValueError):
        ItineraryRequest(**{**base, "source_scope": {**SELECTION_A,
                                                    "input_sha256": "a" * 63}})


def _forbid_collaborators(monkeypatch):
    calls = {"jev": 0, "model": 0, "mcp": 0}

    async def _model(_payload):
        calls["model"] += 1
        raise AssertionError("model must not be called")

    def _session():
        calls["mcp"] += 1
        raise AssertionError("MCP must not be called")

    monkeypatch.setattr(main, "gemini_chat_completion", _model)
    monkeypatch.setattr(main, "open_mcp_session", _session)
    monkeypatch.setattr(main, "route_intent", _model)
    return calls


def test_chat_invalid_mode_is_422_before_any_collaborator(monkeypatch):
    calls = _forbid_collaborators(monkeypatch)
    response = http_call("POST", "/chat",
                         body={**chat_body(), "transport_mode": "Foot"})
    assert response.status_code == 422
    assert calls == {"jev": 0, "model": 0, "mcp": 0}


def test_chat_invalid_selection_is_422_before_any_collaborator(monkeypatch):
    calls = _forbid_collaborators(monkeypatch)
    response = http_call("POST", "/chat",
                         body={**chat_body(),
                               "source_scope": {**SELECTION_A,
                                                "source_area_id": "quan_1"}})
    assert response.status_code == 422
    detail = response.json()["detail"]
    # FastAPI's typed-request rejection is structured JSON before the endpoint
    # runs; the exact pydantic message is not a contract, only the field path.
    assert "source_area_id" in json.dumps(detail)
    assert calls == {"jev": 0, "model": 0, "mcp": 0}


def test_itinerary_invalid_selection_is_structured_without_model(monkeypatch):
    calls = _forbid_collaborators(monkeypatch)
    response = http_call("POST", "/generate_itinerary",
                         body={**itinerary_body(),
                               "source_scope": {**SELECTION_A,
                                                "input_sha256": "a" * 63}})
    assert response.status_code == 422
    assert calls == {"jev": 0, "model": 0, "mcp": 0}


def test_legacy_chat_without_selection_still_works(monkeypatch):
    install_calls = []

    def _handler(_request):
        import httpx

        return httpx.Response(200, json={
            "model": "jev-test-1",
            "answers": {"intent": {
                "type": "choice", "choice": "CHITCHAT",
                "probabilities": {"CHITCHAT": 0.9, "TRAVEL": 0.05,
                                  "UNCERTAIN": 0.05},
                "confidence": 0.9}},
            "usage": {"input_tokens": 1, "output_tokens": 1},
        })

    from domains import jev_intent

    jev_intent.configure_intent_router(
        {"TYPESAFE_API_KEY": "dummy-test-key", "JEV_MIN_CONFIDENCE": "0.5"},
        transport=httpx.MockTransport(_handler))

    async def _mcp():
        raise AssertionError("chitchat must not open MCP")

    async def _model(payload):
        install_calls.append(payload)
        return {"choices": [{"message": {"content": "Chào bạn!"}}]}

    monkeypatch.setattr(main, "open_mcp_session", _mcp)
    monkeypatch.setattr(main, "gemini_chat_completion", _model)

    response = http_call("POST", "/chat",
                         body={"session_id": "legacy-1",
                               "message": "xin chào"})
    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "CHITCHAT"
    assert body["transport_mode"] == "car"
    assert body["source_scope"] is None
    assert body["scope_mode"] == grounding.SCOPE_MODE_CURRENT
    assert body["tool_chain"] == []
    assert len(install_calls) == 1
