"""SYS100 synthetic stop/identity/cleanup policy tests (no I/O)."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from benchmarks.system_adversarial import runner as r
from benchmarks.memory_live.runner import BoundedError


def _provider_payload(model, *, code="insufficient_data", exercised=False,
                      ok_calls=1):
    return {
        "status": "failed",
        "error": {"code": code},
        "provider": {"calls": [{"ok": True, "observed_model": model,
                                "attempts": 1}]},
        "_sys098": {"case": "B_unknown_id", "real_provider_calls": 1,
                    "provider_ok_calls": ok_calls,
                    "injection_exercised": exercised},
    }


def test_wrong_observed_identity_survives_sanitization_as_closed_guard():
    receipt = r.build_case_receipt(
        case="B_unknown_id",
        response={"status": 200,
                  "payload": _provider_payload("untrusted-identity")},
        counters={})
    assert "untrusted-identity" not in json.dumps(receipt)
    assert r.stop_reason_for(receipt, generative=True, cli_attempts=1) \
        == "model_identity_mismatch_stop"


def test_mismatch_without_top_or_provider_error_still_stops():
    receipt = {"top_error_code": None, "provider_receipts": [
        {"ok": True, "observed_model": "aibox/ds/deepseek-flash",
         "model_identity_mismatch": True, "attempts": 1}]}
    assert r.stop_reason_for(receipt, generative=True, cli_attempts=1) \
        == "model_identity_mismatch_stop"
    raw = {"top_error_code": None, "provider_receipts": [
        {"ok": True, "observed_model": "aibox/ds/deepseek-flash"}]}
    assert r.stop_reason_for(raw, generative=True, cli_attempts=1) \
        == "model_identity_mismatch_stop"


def test_exact_go_and_unknown_identity_do_not_stop():
    exact = {"top_error_code": "insufficient_data", "provider_receipts": [
        {"ok": True, "observed_model": r.MODEL, "attempts": 1}]}
    assert r.stop_reason_for(exact, generative=True, cli_attempts=1) is None
    unknown = {"top_error_code": "insufficient_data", "provider_receipts": [
        {"ok": True, "observed_model": None, "attempts": 1}]}
    assert r.stop_reason_for(unknown, generative=True, cli_attempts=1) is None


class _TransportBackend:
    def __init__(self, manifest, out):
        self.started = False
        self.evidence = {}
        self.calls = []

    def start(self):
        self.started = True

    def request(self, *args, **kwargs):
        self.calls.append(kwargs["headers"][r.CASE_HEADER])
        return {"status": None, "payload": None,
                "error_code": "transport_error"}

    def stop(self):
        self.started = False


def test_non_generative_transport_latches_before_generative(monkeypatch, tmp_path):
    monkeypatch.setattr(r, "validate_execution_manifest", lambda manifest: None)
    monkeypatch.setattr(r, "SystemAdversarialBackend", _TransportBackend)
    result = r.execute({"requests": r.build_requests()}, tmp_path / "transport")
    assert not (set(r.GENERATIVE_CASES) & set(result["cases"]))
    assert result["stop_reason"] == "earlier_transport_stop"
    assert set(r.GENERATIVE_CASES) <= set(result["missing_cases"])
    # Read-only A/C probes after the transport failure are permitted.
    assert "C_no_match_native" in result["cases"]


class _BusinessBackend:
    def __init__(self, manifest, out):
        self.started = False
        self.evidence = {}
        self.calls = []

    def start(self):
        self.started = True

    def request(self, *args, **kwargs):
        case = kwargs["headers"][r.CASE_HEADER]
        self.calls.append(case)
        return {"status": 200, "payload": {
            "status": "failed", "error": {"code": "insufficient_data"},
            "_sys098": {"case": case, "real_provider_calls": 0,
                        "provider_ok_calls": 0, "injection_exercised": True}}}

    def stop(self):
        self.started = False


def test_expected_business_errors_allow_later_cases(monkeypatch, tmp_path):
    monkeypatch.setattr(r, "validate_execution_manifest", lambda manifest: None)
    monkeypatch.setattr(r, "SystemAdversarialBackend", _BusinessBackend)
    result = r.execute({"requests": r.build_requests()}, tmp_path / "business")
    assert set(result["cases"]) == set(r.CASE_ORDER)
    assert result["stop_reason"] is None


def _partial_backend(tmp_path):
    backend = r.SystemAdversarialBackend({}, tmp_path)
    backend.state_file.parent.mkdir(parents=True)
    backend.state_file.write_text("{}")
    backend.started = False
    backend.stop_args = SimpleNamespace(state_file=str(backend.state_file))
    return backend


def _lifecycle(monkeypatch, backend, result=None, error=None):
    calls = []

    def fake(action, args):
        calls.append((action, args))
        if error is not None:
            raise error
        return result

    monkeypatch.setattr(backend, "_helper_lifecycle", fake)
    backend.helper = SimpleNamespace(command_stop=object())
    return calls


def test_partial_owned_state_verified_stop(monkeypatch, tmp_path):
    backend = _partial_backend(tmp_path)
    calls = _lifecycle(monkeypatch, backend,
                       result={"status": "stopped",
                               "ports_after": {"mcp": [], "ai": False}})
    backend.stop()
    assert calls and backend.partial_cleanup_verified is True


def test_partial_owned_state_refusal_and_owners_are_unverified(monkeypatch, tmp_path):
    backend = _partial_backend(tmp_path)
    _lifecycle(monkeypatch, backend,
               result={"status": "partial",
                       "ports_after": {"mcp": [123], "ai": []}})
    with pytest.raises(BoundedError) as exc:
        backend.stop()
    assert str(exc.value) == "partial_cleanup_unverified"
    assert backend.partial_cleanup_verified is False

    backend = _partial_backend(tmp_path / "second")
    _lifecycle(monkeypatch, backend,
               result={"status": "stopped",
                       "ports_after": {"mcp": [], "ai": [456]}})
    with pytest.raises(BoundedError):
        backend.stop()
    assert backend.partial_cleanup_verified is False


def test_partial_owned_state_stop_exception_is_closed_and_restores(monkeypatch, tmp_path):
    backend = _partial_backend(tmp_path)
    backend._configure_helper()
    original = backend._original_bootstrap
    _lifecycle(monkeypatch, backend, error=BoundedError("owned_stop_failed"))
    with pytest.raises(BoundedError) as exc:
        backend.stop()
    assert str(exc.value) == "partial_cleanup_unverified"
    assert backend.partial_cleanup_verified is False
    assert backend._original_bootstrap == original


class _PartialNoopBackend:
    def __init__(self, manifest, out):
        self.started = False
        self.evidence = {}
        self.state_file = out / "native_state" / "core_service.json"

    def start(self):
        self.state_file.write_text("{}")
        raise RuntimeError("synthetic partial startup")

    def stop(self):
        if not self.started:
            return


def test_execute_partial_noop_cannot_claim_cleanup(monkeypatch, tmp_path):
    monkeypatch.setattr(r, "validate_execution_manifest", lambda manifest: None)
    monkeypatch.setattr(r, "SystemAdversarialBackend", _PartialNoopBackend)
    result = r.execute({"requests": r.build_requests()}, tmp_path / "partial")
    assert result["collector_error_code"] == "startup_failed"
    assert result["cleanup"]["ok"] is False
    assert result["cleanup"]["error_code"] == "partial_cleanup_unverified"
    assert result["missing_cases"] == list(r.CASE_ORDER)


class _PartialVerifiedBackend(_PartialNoopBackend):
    def __init__(self, manifest, out):
        super().__init__(manifest, out)
        self.partial_cleanup_verified = False

    def stop(self):
        self.partial_cleanup_verified = True


def test_execute_partial_verified_cleanup_can_be_true(monkeypatch, tmp_path):
    monkeypatch.setattr(r, "validate_execution_manifest", lambda manifest: None)
    monkeypatch.setattr(r, "SystemAdversarialBackend", _PartialVerifiedBackend)
    result = r.execute({"requests": r.build_requests()}, tmp_path / "verified")
    assert result["cleanup"]["ok"] is True
    assert result["cleanup"]["error_code"] is None
    assert result["missing_cases"] == list(r.CASE_ORDER)


def test_malformed_b_plan_not_exercised_and_no_http_is_missing():
    payload = {"status": "failed", "error": {"code": "plan_invalid"},
               "_sys098": {"case": "B_unsupported_fields",
                           "real_provider_calls": 1, "provider_ok_calls": 1,
                           "injection_exercised": False,
                           "not_exercised": ["no_valid_plan"]}}
    result = r.classify_case("B_unsupported_fields",
                             {"status": 200, "payload": payload}, {})
    assert result["status"] == "not_exercised"
    assert r.classify_case("B_unsupported_fields",
                           {"status": None, "payload": None},
                           {})["status"] == "missing"
