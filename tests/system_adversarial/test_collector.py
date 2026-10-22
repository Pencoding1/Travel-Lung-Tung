"""SYS098 offline synthetic tests.

Every collaborator here is an in-process fake.  No subprocess, socket, real
HTTP server, MCP transport, engine, model, CLI command, credential or frozen
evidence is touched.  Injected text is synthetic and explicitly labelled.
"""

from __future__ import annotations

import asyncio
import copy
import json
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
for _path in (REPO_ROOT, REPO_ROOT / "ai_service", REPO_ROOT / "tests" / "ai_grounding"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import main  # noqa: E402
from benchmarks.system_adversarial import qa_runtime as qa  # noqa: E402
from benchmarks.system_adversarial import runner  # noqa: E402
from benchmarks.memory_live.runner import BoundedError  # noqa: E402
from domains.payloads import ItineraryRequest  # noqa: E402


# ---------------------------------------------------------------------------
# Synthetic fakes (no I/O)
# ---------------------------------------------------------------------------
class _Text:
    def __init__(self, text):
        self.text = text


class FakeToolResult:
    def __init__(self, text=None, is_error=False):
        self.isError = is_error
        self.content = [] if text is None else [_Text(text)]


def ok(payload):
    return FakeToolResult(json.dumps(payload))


class FakeSession:
    def __init__(self, handlers):
        self.handlers = handlers
        self.calls = []

    async def call_tool(self, name, arguments=None):
        self.calls.append({"tool": name, "args": dict(arguments or {})})
        return self.handlers[name](arguments or {})


def seam(session):
    @asynccontextmanager
    async def _seam():
        yield session

    return _seam


class FakeChat:
    def __init__(self, response=None, exc=None):
        self.response = response
        self.exc = exc
        self.calls = []

    async def __call__(self, payload):
        self.calls.append(payload)
        if self.exc is not None:
            raise self.exc
        return self.response


def llm(plan):
    return {"choices": [{"message": {"content": json.dumps(plan)}}]}


def source_body(case):
    return runner._case_body(case)


def make_request(case):
    return ItineraryRequest(**source_body(case))


def base_handlers():
    return {
        "get_available_categories": lambda _a: ok(
            {"success": True, "categories": [{"id": "cat_cafe", "name": "Cafe"}]}),
        "explore_pois": lambda _a: ok(
            {"success": True, "results": [{"id": "sys098_poi_a"},
                                          {"id": "sys098_poi_b"}]}),
        "get_poi_details": lambda args: ok(
            {"success": True, "result": {
                "POI_ID": args["poi_id"], "POI_Name": "Evidence Name",
                "POI_Address": "Evidence Address", "POI_Category": "Cafe",
                "latitude": 10.77, "longitude": 106.7,
                "operation_time": "08:00-22:00", "source_context": {}}}),
        "resolve_geographic_id": lambda _a: ok(
            {"success": True, "matches": []}),
    }


def run_with_case(monkeypatch, case, handlers, chat):
    session = FakeSession(handlers)
    with qa.case_context(case) as counters:
        proxy = qa.SessionProxy(session, counters=counters)
        monkeypatch.setattr(main, "open_mcp_session", seam(proxy))
        monkeypatch.setattr(main, "gemini_chat_completion", chat)
        result = asyncio.run(main.generate_itinerary_endpoint(
            make_request(case)))
        return result, session, counters


# ---------------------------------------------------------------------------
# Dry run / manifest / budget / binding
# ---------------------------------------------------------------------------
def test_dry_run_builds_no_backend_and_no_socket(monkeypatch, capsys):
    class ForbiddenBackend:
        def __init__(self, *args, **kwargs):
            raise AssertionError("backend must not be constructed on dry-run")

    monkeypatch.setattr(runner, "SystemAdversarialBackend", ForbiddenBackend)
    assert runner.main([]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["mode"] == "dry_run"
    assert output["backend_constructed"] is False
    assert output["sockets_opened"] is False
    assert output["provider_calls"] == 0
    manifest = output["manifest"]
    assert manifest["frozen"] is False
    assert [case["case"] for case in manifest["cases"]] == list(runner.CASE_ORDER)
    assert len(manifest["requests"]) == 9
    assert sum(1 for request in manifest["requests"] if request["generative"]) == 3


def _approved_candidate():
    manifest = copy.deepcopy(runner.build_candidate_manifest())
    manifest["frozen"] = True
    manifest["review"] = {"decision": "approved", "reviewer": "Codex SYS098 QA"}
    return manifest


def test_approved_manifest_binds_current_hashes():
    runner.validate_execution_manifest(_approved_candidate())


@pytest.mark.parametrize("mutate,code", [
    (lambda m: m.update(frozen=False), "manifest_not_frozen"),
    (lambda m: m["review"].update(decision="pending"), "manifest_not_approved"),
    (lambda m: m["runtime"].update(endpoint="/chat"), "manifest_endpoint_mismatch"),
    (lambda m: m["runtime"].update(model="gemini-2.5-pro"), "manifest_model_mismatch"),
    (lambda m: m["runtime"].update(mcp_port=19101), "manifest_mcp_port_mismatch"),
    (lambda m: m["limits"].update(http_requests=10), "manifest_limits_mismatch"),
    (lambda m: m["dataset"].update(sha256="0" * 64), "manifest_dataset_hash_mismatch"),
    (lambda m: m["source_hashes"].update(runner="0" * 64),
     "manifest_source_hash_mismatch"),
    (lambda m: m["requests"][0].update(path="/chat"), "manifest_request_mismatch"),
    (lambda m: m["cases"].reverse(), "manifest_case_order_mismatch"),
])
def test_manifest_mutations_reject_before_backend(mutate, code):
    manifest = _approved_candidate()
    mutate(manifest)
    with pytest.raises(BoundedError) as exc:
        runner.validate_execution_manifest(manifest)
    assert str(exc.value) == code


# ---------------------------------------------------------------------------
# Case transformations with real-delegation spies
# ---------------------------------------------------------------------------
def test_a_empty_replaces_every_explore_after_real_call():
    session = FakeSession(base_handlers())
    counters = qa._new_counters("A_empty")
    proxy = qa.SessionProxy(session, counters=counters)
    with qa.case_context("A_empty"):
        result = asyncio.run(proxy.call_tool("explore_pois", {"limit": 5}))
    assert session.calls == [{"tool": "explore_pois", "args": {"limit": 5}}]
    assert json.loads(result.content[0].text)["results"] == []
    assert counters["real_tool_calls"] == 1
    assert counters["injection_exercised"] is True


def test_a_enrichment_failed_returns_is_error_after_real_call():
    session = FakeSession(base_handlers())
    counters = qa._new_counters("A_enrichment_failed")
    proxy = qa.SessionProxy(session, counters=counters)
    with qa.case_context("A_enrichment_failed"):
        result = asyncio.run(proxy.call_tool("get_poi_details",
                                             {"poi_id": "sys098_poi_a"}))
    assert session.calls and result.isError is True
    assert counters["injection_counts"]["get_poi_details:isError"] == 1


def test_c_ambiguous_returns_two_authored_district_matches():
    session = FakeSession(base_handlers())
    counters = qa._new_counters("C_ambiguous")
    proxy = qa.SessionProxy(session, counters=counters)
    with qa.case_context("C_ambiguous"):
        result = asyncio.run(proxy.call_tool("resolve_geographic_id",
                                             {"keyword": "District 1"}))
    matches = json.loads(result.content[0].text)["matches"]
    assert len(matches) == 2
    assert len({item["id"] for item in matches}) == 2
    assert session.calls[0]["tool"] == "resolve_geographic_id"
    assert counters["injection_exercised"] is True


def test_c_wrong_parent_is_injected_and_reaches_scope_check(monkeypatch):
    chat = FakeChat(exc=AssertionError("provider must not be called"))
    result, session, counters = run_with_case(
        monkeypatch, "C_wrong_parent", base_handlers(), chat)
    assert result["status"] == "failed"
    assert result["error"]["code"] == "scope_conflict"
    assert chat.calls == []
    assert [call["tool"] for call in session.calls] == [
        "resolve_geographic_id", "resolve_geographic_id"]
    assert counters["injection_counts"]["resolve_geographic_id:wrong_parent"] == 1
    assert counters["injection_counts"]["resolve_geographic_id:wrong_parent_city"] == 1


def test_c_partial_collision_is_not_resolved(monkeypatch):
    result, _session, counters = run_with_case(
        monkeypatch, "C_partial_collision", base_handlers(),
        FakeChat(exc=AssertionError("provider must not be called")))
    assert result["error"]["code"] == "location_not_resolved"
    assert counters["injection_counts"]["resolve_geographic_id:partial_collision"] == 1


def test_c_no_match_native_has_no_injection(monkeypatch):
    result, _session, counters = run_with_case(
        monkeypatch, "C_no_match_native", base_handlers(),
        FakeChat(exc=AssertionError("provider must not be called")))
    assert result["error"]["code"] == "location_not_resolved"
    assert counters["injection_exercised"] is False


def test_a_empty_endpoint_uses_zero_real_provider(monkeypatch):
    chat = FakeChat(exc=AssertionError("provider must not be called"))
    result, session, counters = run_with_case(
        monkeypatch, "A_empty", base_handlers(), chat)
    assert result["error"]["code"] == "insufficient_data"
    assert chat.calls == []
    assert counters["real_provider_calls"] == 0
    assert any(call["tool"] == "explore_pois" for call in session.calls)


def test_b_unknown_id_uses_real_delegate_then_perturbs():
    original = llm({"stops": [{"poi": {"id": "sys098_poi_a"}}]})
    original["usage"] = {"total_tokens": 7}
    original["_provider"] = {"provider": "opencode_cli", "ok": True,
                             "session_id": "ses_synthetic", "usage": {"total_tokens": 7}}
    chat = FakeChat(original)
    counters = qa._new_counters("B_unknown_id")
    with qa.case_context("B_unknown_id"):
        wrapped = qa.wrap_gemini_chat_completion(chat, counters=counters)
        result = asyncio.run(wrapped({"messages": []}))
    assert len(chat.calls) == 1
    plan = json.loads(result["choices"][0]["message"]["content"])
    assert plan["stops"][0]["poi"]["id"] == qa.GHOST_ID
    assert result["_provider"] == original["_provider"]
    assert result["usage"] == original["usage"]
    assert counters["injection_exercised"] is True
    assert counters["real_provider_calls"] == 1


def test_b_unsupported_fields_injected_but_ids_retained():
    original = llm({"stops": [{"poi": {"id": "sys098_poi_a"}},
                              {"poi": {"id": "sys098_poi_b"}}]})
    counters = qa._new_counters("B_unsupported_fields")
    with qa.case_context("B_unsupported_fields"):
        result = qa.perturb_plan_response("B_unsupported_fields", original, counters)
    plan = json.loads(result["choices"][0]["message"]["content"])
    assert [stop["poi"]["id"] for stop in plan["stops"]] == [
        "sys098_poi_a", "sys098_poi_b"]
    assert plan["stops"][0]["poi"]["name"] == qa._AUTHORED_FIELDS["name"]
    assert plan["stops"][0]["poi"]["price"] == qa._AUTHORED_FIELDS["price"]
    assert counters["injection_counts"]["plan:unsupported_fields"] == 1


def test_s_native_control_is_not_perturbed():
    original = llm({"stops": [{"poi": {"id": "sys098_poi_a"}}]})
    counters = qa._new_counters("S_native_control")
    with qa.case_context("S_native_control"):
        assert qa.perturb_plan_response("S_native_control", original, counters) is original
    assert counters["injection_exercised"] is False


def test_malformed_real_model_output_is_not_exercised_without_fabrication():
    original = {"choices": [{"message": {"content": "not json"}}],
                "_provider": {"ok": True, "session_id": "ses_synthetic"}}
    chat = FakeChat(original)
    counters = qa._new_counters("B_unknown_id")
    with qa.case_context("B_unknown_id"):
        wrapped = qa.wrap_gemini_chat_completion(chat, counters=counters)
        result = asyncio.run(wrapped({"messages": []}))
    assert result is original
    assert len(chat.calls) == 1
    assert counters["injection_exercised"] is False
    assert "no_valid_plan" in counters["not_exercised"]


# ---------------------------------------------------------------------------
# Context isolation / unknown case
# ---------------------------------------------------------------------------
def test_contextvar_isolated_concurrent_and_reset():
    async def worker(case):
        with qa.case_context(case) as counters:
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            return qa.current_case(), counters["case"]

    async def run():
        return await asyncio.gather(worker("A_empty"), worker("C_ambiguous"))

    assert asyncio.run(run()) == [("A_empty", "A_empty"),
                                  ("C_ambiguous", "C_ambiguous")]
    assert qa.current_case() is None
    with qa.case_context("A_empty"):
        assert qa.current_case() == "A_empty"
    assert qa.current_case() is None


def test_unknown_case_header_rejected_before_delegation():
    with pytest.raises(qa.QARuntimeError) as exc:
        qa.resolve_case_header("SYS098_not_registered")
    assert str(exc.value) == "unknown_qa_case"
    assert qa.resolve_case_header("S_native_control") == "S_native_control"
    assert qa.resolve_case_header(None) is None


def test_install_requires_static_opt_in(monkeypatch):
    monkeypatch.delenv("SYS098_ENABLE_QA", raising=False)
    with pytest.raises(qa.QARuntimeError) as exc:
        qa.install()
    assert str(exc.value) == "qa_opt_in_required"


# ---------------------------------------------------------------------------
# Unsupported fields / route / failure policy / persistence
# ---------------------------------------------------------------------------
def test_delivered_fields_compared_only_to_real_evidence():
    evidence = {"sys098_poi_a": {
        "name": "Evidence Name", "address": "Evidence Address",
        "operation_time": "08:00-22:00"}}
    delivered = {"reply": {"stops": [{
        "description": qa.NEUTRAL_DESCRIPTION,
        "description_grounded": False,
        "poi": {"id": "sys098_poi_a", "name": "Evidence Name",
                "address": "Evidence Address", "operation_time": "08:00-22:00"}}]}}
    comparisons = qa.compare_delivered_fields(delivered, evidence)
    assert comparisons and all(comparisons.values())

    leaked = copy.deepcopy(delivered)
    leaked["reply"]["stops"][0]["poi"]["name"] = qa._AUTHORED_FIELDS["name"]
    assert qa.compare_delivered_fields(leaked, evidence)["name"] is False


def test_native_control_route_and_unknowns_logic():
    payload = {
        "status": "success",
        "reply": {"stops": [{"poi": {"id": "a", "price_verified": False}},
                            {"poi": {"id": "b", "price_verified": False}}]},
        "planning": {
            "initial_proposal": {"sequence": ["a", "b"]},
            "repaired_schedule": {
                "sequence": ["a", "b"],
                "days": [{"stops": [
                    {"poi_id": "a", "arrival": "2026-11-03T09:00:00+07:00",
                     "departure": "2026-11-03T10:00:00+07:00"},
                    {"poi_id": "b", "arrival": "2026-11-03T10:30:00+07:00",
                     "departure": "2026-11-03T11:30:00+07:00"},
                ]}],
            },
            "selected_plan_route": {"coverage": "complete", "verified": True,
                                    "transport_mode": "car"},
            "route_evidence": {"coverage": "complete", "transport_mode": "car"},
            "cost": {"status": "unknown"},
            "verified": False,
        },
    }
    checks = runner.analyze_native_control(payload, source_ids={"a", "b"})
    counters = {"case": "S_native_control", "real_provider_calls": 1,
                "provider_ok_calls": 1, "injection_exercised": False,
                "control_checks": checks}
    result = runner.classify_case("S_native_control", {"status": 200,
                                                       "payload": payload}, counters)
    assert result["status"] == "observed_pass"
    assert result["route_complete"] is True

    payload["reply"]["stops"][0]["poi"]["price_verified"] = True
    # The classifier never promotes an unknown price to verified global truth.
    receipt = runner.build_case_receipt(
        case="S_native_control", response={"status": 200, "payload": payload},
        counters=counters)
    assert "price_verified" not in json.dumps(receipt)


def test_native_control_nondelivery_with_provider_is_failure():
    payload = {"status": "failed", "error": {"code": "insufficient_data"},
               "_sys098": {"case": "S_native_control", "real_provider_calls": 1,
                           "provider_ok_calls": 1, "injection_exercised": False}}
    result = runner.classify_case(
        "S_native_control", {"status": 200, "payload": payload},
        {"case": "S_native_control", "real_provider_calls": 1,
         "provider_ok_calls": 1, "injection_exercised": False})
    assert result["status"] == "observed_failure"


def test_native_control_negative_shapes_are_not_passes():
    base = {
        "status": "success", "reply": {"stops": [{"poi": {"id": "a"}}]},
        "planning": {
            "repaired_schedule": {
                "sequence": ["a"], "days": [{"stops": [
                    {"poi_id": "a", "arrival": "2026-11-03T09:00:00+07:00",
                     "departure": "2026-11-03T10:00:00+07:00"}]}]},
            "selected_plan_route": {"coverage": "complete", "verified": True,
                                    "transport_mode": "car"},
            "route_evidence": {"coverage": "complete", "transport_mode": "car"},
            "verified": False,
        },
    }
    result = runner.classify_case("S_native_control", {"status": 200, "payload": base},
                                  {"case": "S_native_control", "real_provider_calls": 1,
                                   "provider_ok_calls": 1, "injection_exercised": False})
    assert result["status"] == "observed_failure"

    for mutate in (
        lambda p: p["planning"]["repaired_schedule"]["days"][0]["stops"][0].update(
            {"arrival": "not-a-time"}),
        lambda p: p["planning"]["selected_plan_route"].update({"verified": False}),
        lambda p: p["planning"].update({"verified": True}),
    ):
        payload = copy.deepcopy(base)
        mutate(payload)
        checks = runner.analyze_native_control(payload, source_ids={"a", "b"})
        assert not runner._control_passed(checks)


def test_bad_stop_keeps_unsupported_fields_failure():
    evidence = {"a": {"name": "A", "address": "AA"},
                "b": {"name": "B", "address": "BB"}}
    payload = {"status": "success", "reply": {"stops": [
        {"description": qa.NEUTRAL_DESCRIPTION, "description_grounded": False,
         "poi": {"id": "a", "name": "A", "address": "AA"}},
        {"description": qa.NEUTRAL_DESCRIPTION, "description_grounded": False,
         "poi": {"id": "b", "name": "AUTHORED", "address": "BB"}},
    ]}}
    comparisons = runner.compare_injected_fields(payload, evidence)
    assert comparisons["name"] is False
    result = runner.classify_case(
        "B_unsupported_fields", {"status": 200, "payload": payload},
        {"case": "B_unsupported_fields", "real_provider_calls": 1,
         "provider_ok_calls": 1, "injection_exercised": True,
         "field_comparisons": comparisons})
    assert result["status"] == "observed_failure"


@pytest.mark.parametrize("code,generative,attempts,expected", [
    ("auth_error", True, 1, "fatal_closed_code_stop"),
    ("permission_denied", False, 1, "fatal_closed_code_stop"),
    ("transport_error", True, 1, "generative_transport_stop"),
    ("transport_error", False, 1, None),
    ("insufficient_data", True, 1, None),
    ("timeout", True, 16, "generative_transport_stop"),
    ("insufficient_data", False, 16, "cli_attempt_budget_exceeded"),
])
def test_failure_policy_stops_only_closed_classes(code, generative, attempts, expected):
    assert runner.stop_reason_for({"top_error_code": code},
                                  generative=generative,
                                  cli_attempts=attempts) == expected


def test_missing_case_is_retained_as_missing_not_pass():
    result = runner.classify_case(
        "A_empty", {"status": None, "payload": None},
        {"case": "A_empty", "real_provider_calls": 0})
    assert result["status"] == "missing"
    assert result["checks"] == ["transport_missing"]


# ---------------------------------------------------------------------------
# Exclusive output / ledger durability / cleanup / helper restoration
# ---------------------------------------------------------------------------
def test_output_directory_is_exclusive_and_ledger_is_durable(tmp_path):
    out = tmp_path / "run"
    runner._prepare_output(out)
    with pytest.raises(BoundedError) as exc:
        runner._prepare_output(out)
    assert str(exc.value) == "output_directory_exists"

    ledger = out / "qa_cases" / "case-receipts.jsonl"
    runner._append_jsonl(ledger, {"case": "A_empty", "status": "missing"})
    runner._append_jsonl(ledger, {"case": "C_ambiguous", "status": "missing"})
    lines = ledger.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["case"] for line in lines] == [
        "A_empty", "C_ambiguous"]


class FakeHelper:
    def __init__(self):
        self.guard = "carrier-sentinel"
        self.stop_calls = 0

    def ai_environment(self, *_args, **_kwargs):
        return {
            "OPENCODE_CONFIG_CONTENT": self.guard,
            "OPENCODE_CONFIG": self.guard,
            "MCP_SERVER_URL": "fixture",
        }

    def bootstrap_code(self, _service_root):
        return ("import runpy\n"
                "module = sys.argv[1]\n"
                "runpy.run_module(module, run_name='__main__')\n")

    def command_stop(self, _args):
        self.stop_calls += 1
        return 0


def _backend(tmp_path):
    backend = runner.SystemAdversarialBackend(
        runner.build_candidate_manifest(), tmp_path / "owned")
    backend.helper = FakeHelper()
    return backend


def test_bootstrap_and_guard_carriers_are_preserved_and_restored(tmp_path):
    backend = _backend(tmp_path)
    original_environment = backend.helper.ai_environment
    original_bootstrap = backend.helper.bootstrap_code
    backend._configure_helper()

    env = backend.helper.ai_environment(19601, "alias", Path("C:/python.exe"))
    assert env["SYS098_ENABLE_QA"] == "1"
    assert env["OPENCODE_CONFIG_CONTENT"] == "carrier-sentinel"
    assert env["OPENCODE_CONFIG"] == "carrier-sentinel"

    ai_code = backend.helper.bootstrap_code(runner.AI_SERVICE_ROOT)
    assert ai_code.count(runner.BOOTSTRAP_MARKER) == 1
    assert runner.QA_INSTALL_STATEMENT in ai_code
    assert ai_code.index(runner.QA_INSTALL_STATEMENT) < ai_code.index(
        runner.BOOTSTRAP_MARKER)

    other_code = backend.helper.bootstrap_code(runner.ROOT)
    assert runner.QA_INSTALL_STATEMENT not in other_code

    backend._restore_helper()
    assert backend.helper.ai_environment == original_environment
    assert backend.helper.bootstrap_code == original_bootstrap


def test_bootstrap_marker_change_fails_closed():
    with pytest.raises(BoundedError) as exc:
        runner.qa_bootstrap_code("print('changed')\n", runner.AI_SERVICE_ROOT)
    assert str(exc.value) == "qa_bootstrap_marker_changed"


def test_cleanup_restores_helper_even_when_owned_stop_fails(tmp_path):
    backend = _backend(tmp_path)
    backend._configure_helper()
    original_environment = backend.original_ai_environment
    original_bootstrap = backend._original_bootstrap
    backend.started = True
    backend.stop_args = object()

    def fail(_args):
        raise BoundedError("owned_stop_failed")

    backend.helper.command_stop = fail
    with pytest.raises(BoundedError):
        backend.stop()
    assert backend.helper.ai_environment == original_environment
    assert backend.helper.bootstrap_code == original_bootstrap


def test_fixture_credentials_never_enter_artifacts(tmp_path):
    backend = _backend(tmp_path)
    secret = backend.fixture_secret
    assert secret
    with pytest.raises(BoundedError) as exc:
        backend.assert_clean({"nested": [secret]})
    assert str(exc.value) == "fixture_credential_in_artifact"

    receipt = runner.build_case_receipt(
        case="A_empty",
        response={"status": 200, "payload": {
            "status": "failed", "error": {"code": "insufficient_data"}}},
        counters={"case": "A_empty", "real_provider_calls": 0,
                  "injection_exercised": True})
    assert secret not in json.dumps(receipt)
