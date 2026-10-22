"""H2091 fake-only acceptance tests for the terminal provider-authority stop.

No provider, engine, model, network or configuration read happens here. The
production-V2 ``complete`` seam is always a scripted fake, and every test writes
only beneath pytest's temporary directory.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from live_model import runner, v2_transport
from live_model.constants import CONDITIONS, V2_MODEL_ID

MODEL = V2_MODEL_ID
SCENARIOS = runner.load_scenario_inputs(runner.DEFAULT_SCENARIOS)
SENTINEL = "SYNTHETIC_AUTHORITY_TEXT_MUST_NOT_PERSIST"

PLAN_TEXT = json.dumps({
    "status": "plan", "no_plan_reason": None,
    "days": [{"day_id": "d1", "stops": [
        {"poi_id": "p_food", "arrival": "2026-11-01T09:00:00+07:00",
         "departure": "2026-11-01T10:00:00+07:00"}]}]})
HYBRID_TEXT = json.dumps({"ordered_poi_ids": ["p_food", "p_cafe"]})


@pytest.fixture(autouse=True)
def deny_real_production_v2(monkeypatch):
    """Any accidental real provider/resolver use fails the test immediately."""
    def _deny(*args, **kwargs):
        raise AssertionError("real production-v2 provider/resolver denied")

    monkeypatch.setattr(runner.v2_transport, "complete_factory", _deny)
    monkeypatch.setattr(runner.v2_transport, "provider_factory", _deny)
    monkeypatch.setattr(runner.capture, "resolve_executable", _deny)


def _provider():
    return {
        "ok": True,
        "requested_model": MODEL,
        "observed_model": MODEL,
        "observed_provider_id": "opencode-go",
        "observed_model_id": "deepseek-v4.1-flash",
        "session_id": "ses_synthetic_authority",
        "identity_source": "opencode_session_export",
        "finish": "stop",
        "attempts": 1,
        "failed_attempts": 0,
        "usage_components": {"input": 10, "output": 20, "total": 30},
        "usage_total": 30,
        "usage_consistent": True,
    }


def _completion(text):
    return {
        "model": MODEL,
        "choices": [{"index": 0,
                     "message": {"role": "assistant", "content": text,
                                 "tool_calls": None},
                     "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20,
                  "total_tokens": 30},
        "_provider": _provider(),
    }


def _ok(payload):
    prompt = payload["messages"][0]["content"]
    text = PLAN_TEXT if "LLM-only itinerary condition" in prompt else HYBRID_TEXT
    return _completion(text)


def _failure(code):
    def _raise(payload):
        exc = v2_transport.ModelUnavailableError(
            code, f"raw synthetic diagnostic {SENTINEL}", retryable=False)
        exc.attempts = 1
        exc.failed_attempts = 1
        raise exc
    return _raise


def _runtime_text(payload):
    raise RuntimeError(f"{SENTINEL} unauthorized")


def _unrecognised_code(payload):
    exc = v2_transport.ModelUnavailableError(
        "made_up_authority", f"{SENTINEL} unauthorized", retryable=False)
    exc.attempts = 1
    exc.failed_attempts = 1
    raise exc


def _sequence(*steps):
    state = {"index": 0}

    def _respond(payload):
        index = min(state["index"], len(steps) - 1)
        state["index"] += 1
        return steps[index](payload)

    return _respond


def _install(monkeypatch, responder):
    calls = []

    def _complete(payload):
        calls.append(payload)
        return responder(payload)

    monkeypatch.setattr(runner.v2_transport, "complete_factory",
                        lambda config, cwd: _complete)
    monkeypatch.setattr(runner.capture, "resolve_executable",
                        lambda *args, **kwargs: "opencode")
    return calls


def _logs(out):
    path = Path(out) / "calls.jsonl"
    return [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _summary(out):
    return json.loads((Path(out) / "run_manifest.json").read_text(encoding="utf-8"))


def _manifest(out):
    return json.loads((Path(out) / "manifest.json").read_text(encoding="utf-8"))


def _snapshot(out):
    root = Path(out)
    return {str(path.relative_to(root)): path.read_bytes()
            for path in root.rglob("*") if path.is_file()}


def _run_args(out, *extra):
    return ["--out", str(out), "--scenario-ids", "S01", *extra]


# ---------------------------------------------------------------------------
# A. First-cell terminal authority failure stops every later planned cell.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("code", [
    "server_auth_refused", "forbidden", "rate_limit",
    "cli_server_preflight_failed",
])
def test_first_cell_terminal_authority_stops_later_cells(
        monkeypatch, tmp_path, code):
    out = tmp_path / f"out-{code}"
    calls = _install(monkeypatch, _failure(code))

    rc = runner.main(_run_args(out, "--execute"))

    assert rc == 1
    assert len(calls) == 1
    logs = _logs(out)
    assert len(logs) == 1
    assert logs[0]["provider_failure"] == {
        "code": code, "attempts": 1, "failed_attempts": 1,
        "retryable": False}
    # The attempted failure row is retained without forged output/receipt.
    assert logs[0]["assistant_text_path"] is None
    assert logs[0]["provider_receipt_path"] is None
    assert logs[0]["provenance_ok"] is False

    order = runner.execution_order(["S01"], 1, CONDITIONS)
    summary = _summary(out)
    assert summary["planned_denominator"] == 2
    assert summary["attempted"] == 1
    assert summary["stopped_early"] is True
    assert summary["terminal_provider_authority_stop"] is True
    assert summary["terminal_provider_code"] == code
    assert summary["unattempted_count"] == 1
    assert summary["unattempted"] == [{
        "scenario_id": order[1][0], "condition": order[1][1],
        "repetition": order[1][2],
        "reason": "terminal_provider_authority_stop"}]
    assert summary["gaps"][0]["reason"] == f"provider_failure:{code}"

    policy = runner.authority_stop_policy()
    assert summary["authority_stop_policy"] == policy
    manifest = _manifest(out)
    assert manifest["planned_denominator"] == 2
    assert len(manifest["execution_order"]) == 2
    assert manifest["authority_stop_policy"] == policy
    assert manifest["fingerprint"]["authority_stop"] == {
        "policy_id": policy["policy_id"],
        "terminal_codes_sha256": policy["terminal_codes_sha256"]}

    # Full planned manifest and timing companion still produced; only the one
    # attempted cell exists in the ledger, and no later observation was invented.
    h2_manifest = json.loads((out / "h2_manifest.json").read_text("utf-8"))
    assert [entry["scenario_id"] for entry in h2_manifest["scenarios"]] == ["S01"]
    assert h2_manifest["repetitions_per_case"] == 1
    assert (out / "h2_records.jsonl").exists()
    assert (out / "h2_temporal_manifest.json").exists()
    assert (out / "h2_temporal_records.jsonl").exists()
    assert not list((out / "events").glob("*.assistant.txt"))
    assert not list((out / "events").glob("*.provider-receipt.json"))


# ---------------------------------------------------------------------------
# B. Success then denial at the last cell; only the exact code is authority.
# ---------------------------------------------------------------------------
def test_success_then_denial_keeps_both_rows_and_stops(monkeypatch, tmp_path):
    out = tmp_path / "out"
    calls = _install(monkeypatch, _sequence(
        _ok, _failure("server_auth_refused")))

    rc = runner.main(_run_args(out, "--execute"))

    # Denial at the last planned cell: no later call exists, historical exit 0.
    assert rc == 0
    assert len(calls) == 2
    logs = _logs(out)
    assert len(logs) == 2
    assert logs[0]["run_status"] == "completed"
    assert logs[0]["output_ok"] is True
    assert logs[1]["provider_failure"]["code"] == "server_auth_refused"
    assert logs[1]["provenance_ok"] is False
    summary = _summary(out)
    assert summary["attempted"] == 2
    assert summary["stopped_early"] is False
    assert summary["terminal_provider_authority_stop"] is False
    assert summary["terminal_provider_code"] == "server_auth_refused"
    assert summary["unattempted"] == []
    assert summary["unattempted_count"] == 0


@pytest.mark.parametrize("responder", [_runtime_text, _unrecognised_code])
def test_text_and_unknown_codes_are_not_authority_signals(
        monkeypatch, tmp_path, responder):
    out = tmp_path / "out"
    calls = _install(monkeypatch, responder)

    rc = runner.main(_run_args(out, "--execute"))

    assert rc == 0
    # No exact recognised code: both planned cells are attempted, no retry.
    assert len(calls) == 2
    logs = _logs(out)
    assert len(logs) == 2
    assert [log["provider_failure"]["code"] for log in logs] == (
        ["provider_transport_exception", "provider_transport_exception"]
        if responder is _runtime_text else
        ["made_up_authority", "made_up_authority"])
    summary = _summary(out)
    assert summary["terminal_provider_code"] is None
    assert summary["stopped_early"] is False
    assert summary["unattempted"] == []
    assert SENTINEL not in (out / "calls.jsonl").read_text("utf-8")


# ---------------------------------------------------------------------------
# C. Timeouts/malformed output are failures, never authority stops.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("code", ["provider_timeout", "cli_timeout"])
def test_timeout_codes_continue_without_retry(monkeypatch, tmp_path, code):
    out = tmp_path / "out"
    calls = _install(monkeypatch, _sequence(_failure(code), _ok))

    rc = runner.main(_run_args(out, "--execute"))

    assert rc == 0
    assert len(calls) == 2
    logs = _logs(out)
    assert len(logs) == 2
    assert logs[0]["provider_failure"]["code"] == code
    assert logs[0]["provider_failure"]["attempts"] == 1
    assert logs[0]["run_status"] == "error"
    assert logs[1]["run_status"] == "completed"
    summary = _summary(out)
    assert summary["planned_denominator"] == 2
    assert summary["attempted"] == 2
    assert summary["terminal_provider_code"] is None
    assert summary["stopped_early"] is False
    assert summary["unattempted"] == []


def test_malformed_output_is_failed_not_authority(monkeypatch, tmp_path):
    out = tmp_path / "out"
    calls = _install(monkeypatch, _sequence(
        lambda payload: _completion("not json"), _ok))

    rc = runner.main(_run_args(out, "--execute"))

    assert rc == 0
    assert len(calls) == 2
    logs = _logs(out)
    assert len(logs) == 2
    assert logs[0]["provenance_ok"] is True
    assert logs[0]["output_ok"] is False
    assert logs[0]["run_status"] == "failed"
    assert logs[0]["invalid_output_reason"].startswith("malformed_model_output")
    assert logs[1]["run_status"] == "completed"
    summary = _summary(out)
    assert summary["attempted"] == 2
    assert summary["terminal_provider_code"] is None
    assert summary["stopped_early"] is False
    assert summary["records_written"] == 2


# ---------------------------------------------------------------------------
# D. Dry-run/fingerprint/resume fail-closed boundaries; legacy untouched.
# ---------------------------------------------------------------------------
def test_v2_dry_run_zero_provider_and_policy_recorded(tmp_path):
    out = tmp_path / "out"
    rc = runner.main(_run_args(out))
    assert rc == 0
    assert not (out / "calls.jsonl").exists()
    assert not (out / "events").exists()
    manifest = _manifest(out)
    assert manifest["dry_run"] is True
    assert manifest["planned_denominator"] == 2
    assert manifest["authority_stop_policy"] == runner.authority_stop_policy()
    assert manifest["fingerprint"]["authority_stop"]["policy_id"] == \
        runner.AUTHORITY_STOP_POLICY_ID


def test_changed_fingerprint_refused_before_writes_or_provider(
        monkeypatch, tmp_path):
    out = tmp_path / "out"
    assert runner.main(_run_args(out)) == 0
    before = _snapshot(out)
    calls = _install(monkeypatch, _ok)

    rc = runner.main(_run_args(out, "--resume", "--execute", "--timeout", "60"))

    assert rc == 2
    assert calls == []
    assert _snapshot(out) == before
    assert not (out / "calls.jsonl").exists()


def test_stopped_v2_run_refuses_resume_without_any_mutation(
        monkeypatch, tmp_path):
    out = tmp_path / "out"
    first_calls = _install(monkeypatch, _failure("server_auth_refused"))
    assert runner.main(_run_args(out, "--execute")) == 1
    assert len(first_calls) == 1
    before = _snapshot(out)
    assert _summary(out)["stopped_early"] is True

    resume_calls = _install(monkeypatch, _ok)
    rc = runner.main(_run_args(out, "--execute", "--resume"))

    assert rc == 2
    assert resume_calls == []
    assert _snapshot(out) == before


def test_last_cell_terminal_does_not_block_compatible_noop_resume(
        monkeypatch, tmp_path):
    out = tmp_path / "out"
    _install(monkeypatch, _sequence(_ok, _failure("server_auth_refused")))
    assert runner.main(_run_args(out, "--execute")) == 0
    assert _summary(out)["stopped_early"] is False
    before = _snapshot(out)

    resume_calls = _install(monkeypatch, _ok)
    rc = runner.main(_run_args(out, "--execute", "--resume"))

    assert rc == 0
    assert resume_calls == []
    assert _snapshot(out) == before


def test_legacy_fingerprint_and_dry_run_have_no_authority_policy(tmp_path):
    dataset = runner.load_dataset_declaration(runner.DEFAULT_SCENARIOS)
    legacy = runner._fingerprint(
        MODEL, "h2-live-collector", CONDITIONS, 1, 120.0, dataset.dataset_id,
        dataset.manifest_sha256, ["S01"], 2)
    v2 = runner._fingerprint_v2(
        MODEL, "h2-live-collector", CONDITIONS, 1, 120.0, dataset, ["S01"], 2)
    assert "authority_stop" not in legacy
    assert "authority_stop" in v2

    out = tmp_path / "legacy"
    assert runner.main(_run_args(out, "--transport", "legacy-v1")) == 0
    manifest = _manifest(out)
    assert "authority_stop_policy" not in manifest
    assert "authority_stop" not in manifest["fingerprint"]


# ---------------------------------------------------------------------------
# E. Full 20 x 2 x 3 denominator: one attempt, 119 unattempted, no synthesis.
# ---------------------------------------------------------------------------
def test_full_20x2x3_terminal_stop_preserves_planned_denominator(
        monkeypatch, tmp_path):
    out = tmp_path / "out"
    calls = _install(monkeypatch, _failure("server_auth_refused"))

    rc = runner.main(["--out", str(out), "--repetitions", "3", "--execute"])

    expected_order = runner.execution_order(list(SCENARIOS), 3, CONDITIONS)
    assert len(expected_order) == 120
    assert rc == 1
    assert len(calls) == 1
    logs = _logs(out)
    assert len(logs) == 1
    assert logs[0]["provider_usage"] is None
    assert logs[0]["observed_model_ids"] == []
    assert logs[0]["assistant_text_path"] is None
    assert logs[0]["provider_receipt_path"] is None

    summary = _summary(out)
    assert summary["planned_denominator"] == 120
    assert summary["attempted"] == 1
    assert summary["stopped_early"] is True
    assert summary["terminal_provider_code"] == "server_auth_refused"
    assert summary["unattempted_count"] == 119
    remaining = [(entry["scenario_id"], entry["condition"], entry["repetition"])
                 for entry in summary["unattempted"]]
    assert len(remaining) == 119
    assert len(set(remaining)) == 119
    assert all(entry["reason"] == "terminal_provider_authority_stop"
               for entry in summary["unattempted"])
    assert set(remaining) == set(expected_order[1:])

    manifest = _manifest(out)
    assert manifest["planned_denominator"] == 120
    assert manifest["fingerprint"]["planned_denominator"] == 120
    assert [(entry["scenario_id"], entry["condition"], entry["repetition"])
            for entry in manifest["execution_order"]] == expected_order
    assert calls[0]["messages"][0]["content"] == runner.prompts.build_prompt(
        expected_order[0][1], SCENARIOS[expected_order[0][0]])
    assert calls[0]["model"] == MODEL

    h2_manifest = json.loads((out / "h2_manifest.json").read_text("utf-8"))
    assert len(h2_manifest["scenarios"]) == 20
    assert h2_manifest["repetitions_per_case"] == 3
    assert (out / "h2_temporal_manifest.json").exists()


def test_full_20x2x3_nonterminal_success_counts_unchanged(
        monkeypatch, tmp_path):
    out = tmp_path / "out"
    calls = _install(monkeypatch, _ok)

    rc = runner.main(["--out", str(out), "--repetitions", "3",
                      "--max-calls", "120", "--execute"])
    assert rc == 0
    assert len(calls) == 120
    summary = _summary(out)
    assert summary["planned_denominator"] == 120
    assert summary["attempted"] == 120
    assert summary["records_written"] == 120
    assert summary["unattempted"] == []
    assert summary["unattempted_count"] == 0
    assert summary["stopped_early"] is False
    assert summary["terminal_provider_code"] is None
    records = [json.loads(line) for line in
               (out / "h2_records.jsonl").read_text("utf-8").splitlines()
               if line.strip()]
    assert len(records) == 120
    assert len(_logs(out)) == 120
