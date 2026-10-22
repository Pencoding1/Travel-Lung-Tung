"""Closed projection and validation tests for the thin production-V2 adapter.

No model, engine, provider or network call is made here; ``complete`` is only
called through an explicitly injected fake in the runner tests.
"""

from __future__ import annotations

import json

import pytest

from live_model import v2_transport
from live_model.util import sha256_text

from domains.providers.errors import ModelUnavailableError

MODEL = "opencode-go/deepseek-v4.1-flash"
ASSISTANT = json.dumps({"ordered_poi_ids": ["p_food"]})
SENTINEL = "SYNTHETIC_SENTINEL_MUST_NOT_PERSIST"


def _provider(**overrides):
    value = {
        "ok": True,
        "requested_model": MODEL,
        "observed_model": MODEL,
        "observed_provider_id": "opencode-go",
        "observed_model_id": "deepseek-v4.1-flash",
        "session_id": "ses_synthetic_test",
        "identity_source": "opencode_session_export",
        "finish": "stop",
        "attempts": 1,
        "failed_attempts": 0,
        "usage_components": {"input": 10, "output": 20, "total": 30},
        "usage_total": 30,
        "usage_consistent": True,
        "cli_capabilities": {"version": "2.0.32", "pure_supported": False,
                             "reason": "installed_cli_has_no_pure"},
        "controls": {"requested": {"temperature": 0.2},
                     "configured": {"temperature": 0.2},
                     "applied": False,
                     "verification": "not_observable_from_transport",
                     "binding": "provider_model_request_body",
                     "unsupported": []},
        "transport": {"config_filename": "opencode.json",
                      "config_sha256": "a" * 64, "scope": "child_process"},
        "agent_preflight": {"status": "ok"},
    }
    value.update(overrides)
    return value


def _completion(text=ASSISTANT, *, provider=None, model=MODEL, **overrides):
    value = {
        "id": "chatcmpl-synthetic",
        "object": "chat.completion",
        "created": 0,
        "model": model,
        "choices": [{"index": 0,
                     "message": {"role": "assistant", "content": text,
                                 "tool_calls": None},
                     "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20,
                  "total_tokens": 30},
        "_provider": _provider() if provider is None else provider,
    }
    value.update(overrides)
    return value


def test_valid_completion_returns_bounded_evidence():
    validated = v2_transport.validate_completion(
        _completion(), requested_model=MODEL, duration_seconds=1.25)
    assert validated.text == ASSISTANT
    assert validated.text_sha256 == sha256_text(ASSISTANT)
    assert validated.model == MODEL
    assert validated.session_id == "ses_synthetic_test"
    assert validated.finish == "stop"
    assert validated.usage["provider_components"]["input"] == 10
    assert validated.usage["total_tokens"] == 30


def test_controls_projection_drops_unknown_nested_fields():
    provider = _provider(controls={
        "requested": {"temperature": 0.2, "top_p": 0.9,
                      "unexpected_secret_field": SENTINEL,
                      "nested": {"secret": SENTINEL}},
        "configured": {"temperature": float("nan"), "top_p": True,
                       "unexpected_secret_field": SENTINEL},
        "applied": "yes",
        "verification": SENTINEL,
        "binding": {"nested": SENTINEL},
        "unsupported": ["temperature", "unexpected_secret_field",
                        {"nested": SENTINEL}],
        "unexpected_top": {"secret": SENTINEL},
    })
    out = v2_transport.normalise_provider(provider)
    assert out["controls"]["requested"] == {"temperature": 0.2, "top_p": 0.9}
    assert out["controls"]["configured"] == {}
    assert "applied" not in out["controls"]
    assert "verification" not in out["controls"]
    assert "binding" not in out["controls"]
    assert out["controls"]["unsupported"] == ["temperature"]
    assert SENTINEL not in json.dumps(out, sort_keys=True)


def test_usage_projection_keeps_only_nonnegative_ints_and_nulls():
    provider = _provider(
        usage_components={
            "input": 10, "output": -1, "reasoning": True,
            "cache_read": {"secret": SENTINEL}, "cache_write": 1.5,
            "total": None, "unexpected": SENTINEL},
        usage_total=True,
        usage_consistent="yes",
    )
    completion = _completion(provider=provider, usage={
        "prompt_tokens": 10, "completion_tokens": -3,
        "total_tokens": {"secret": SENTINEL},
        "prompt_tokens_details": {"secret": SENTINEL}})
    # The raw provider identity is still checked before usage is projected.
    validated = v2_transport.validate_completion(completion, requested_model=MODEL)
    assert validated.usage["provider_components"] == {
        "input": 10, "output": None, "reasoning": None,
        "cache_read": None, "cache_write": None, "total": None}
    assert validated.usage["prompt_tokens"] == 10
    assert validated.usage["completion_tokens"] is None
    assert validated.usage["total_tokens"] is None
    assert validated.usage["usage_consistent"] is None
    assert validated.provider["usage_total"] is None
    assert validated.provider["usage_consistent"] is None
    assert validated.provider["attempts"] == 1
    assert SENTINEL not in json.dumps(validated.provider, sort_keys=True)


def test_derived_receipt_excludes_blocked_fields_and_hashes_text():
    provider = _provider(
        headers={"Authorization": f"Bearer {SENTINEL}"},
        config={"OPENCODE_CONFIG_CONTENT": SENTINEL},
        error_body=SENTINEL,
        reasoning=SENTINEL,
        untrusted_debug={"secret": SENTINEL},
        unknown_subtree={"nested": SENTINEL},
    )
    validated = v2_transport.validate_completion(
        _completion(provider=provider), requested_model=MODEL,
        duration_seconds=0.5)
    evidence = v2_transport.build_evidence(validated, requested_model=MODEL)
    assert evidence["kind"] == v2_transport.EVIDENCE_KIND
    assert evidence["derived"] is True
    assert evidence["raw_cli_transcript_retained"] is False
    assert evidence["raw_session_export_retained"] is False
    assert evidence["response"]["assistant_text_sha256"] == sha256_text(ASSISTANT)
    assert evidence["response"]["assistant_text_chars"] == len(ASSISTANT)
    dumped = v2_transport.canonical_evidence_json(evidence)
    assert SENTINEL not in dumped
    for blocked in ("headers", "config", "error_body", "reasoning",
                    "untrusted_debug", "unknown_subtree"):
        assert blocked not in evidence["provider"]


@pytest.mark.parametrize("provider_overrides,completion_overrides,code", [
    ({"ok": False}, {}, "provider_not_ok"),
    ({"observed_model": "other/model"}, {}, "model_mismatch"),
    ({"observed_provider_id": "other"}, {}, "provider_mismatch"),
    ({"observed_model_id": "other"}, {}, "provider_mismatch"),
    ({"session_id": ""}, {}, "unknown_session_provenance"),
    ({"session_id": None}, {}, "unknown_session_provenance"),
    ({"identity_source": "event_stream"}, {}, "unknown_identity_source"),
    ({"finish": "length"}, {}, "unfinished_response"),
    ({"attempts": 2}, {}, "unexpected_attempts"),
    ({}, {"model": "other/model"}, "model_mismatch"),
])
def test_non_admissible_completions_are_rejected(provider_overrides,
                                                 completion_overrides, code):
    completion = _completion(provider=_provider(**provider_overrides))
    completion.update(completion_overrides)
    with pytest.raises(v2_transport.CompletionRejected) as excinfo:
        v2_transport.validate_completion(completion, requested_model=MODEL)
    assert excinfo.value.code == code


@pytest.mark.parametrize("mutate,code", [
    (lambda c: c.pop("_provider"), "provider_metadata_missing"),
    (lambda c: c.__setitem__("choices", []), "invalid_completion_shape"),
    (lambda c: c["choices"][0]["message"].__setitem__("content", ""),
     "empty_assistant_text"),
    (lambda c: c["choices"][0]["message"].__setitem__(
        "tool_calls", [{"id": "x"}]), "unexpected_tool_calls"),
])
def test_malformed_completion_shapes_are_rejected(mutate, code):
    completion = _completion()
    mutate(completion)
    with pytest.raises(v2_transport.CompletionRejected) as excinfo:
        v2_transport.validate_completion(completion, requested_model=MODEL)
    assert excinfo.value.code == code


def test_provider_failure_is_constant_and_does_not_leak_exception_text():
    exc = ModelUnavailableError("provider_timeout", f"raw {SENTINEL}",
                                retryable=True)
    exc.attempts = 1
    exc.failed_attempts = 1
    failure = v2_transport.provider_failure(exc)
    assert (failure.code, failure.attempts, failure.failed_attempts,
            failure.retryable) == ("provider_timeout", 1, 1, True)
    generic = v2_transport.provider_failure(RuntimeError(f"raw {SENTINEL}"))
    assert generic.code == "provider_transport_exception"
    assert SENTINEL not in repr(generic)


def test_settings_id_binds_the_actual_v2_system_prompt():
    from live_model import export
    from live_model.constants import AGENT_SYSTEM_PROMPT

    v2_id = v2_transport.settings_id(MODEL, "h2-live-collector")
    legacy_id = export.settings_id(MODEL, "h2-live-collector",
                                   AGENT_SYSTEM_PROMPT)
    assert v2_id != legacy_id
    assert v2_transport.transport_system_prompt() != AGENT_SYSTEM_PROMPT


def test_default_provider_factory_delegates_without_a_call():
    from domains.providers.opencode_cli import OpenCodeCliProvider

    config = v2_transport.build_provider_config(
        model=MODEL, executable="opencode", timeout=120.0,
        agent="h2-live-collector")
    provider = v2_transport.default_provider_factory(config, cwd=None)
    assert type(provider) is OpenCodeCliProvider
    assert provider.config.model == MODEL
    assert provider.config.cli_max_attempts == 1
    assert provider.config.cli_max_concurrency == 1
    assert provider.config.cli_pure is False
    payload = v2_transport.build_payload("paired prompt", MODEL)
    assert payload["model"] == MODEL
    assert payload["messages"] == [{"role": "user", "content": "paired prompt"}]
    assert payload["response_format"] == {"type": "json_object"}
