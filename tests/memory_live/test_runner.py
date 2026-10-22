"""Focused offline tests for the EXP078 native H3 collector.

No provider, HTTP, native service, engine, credential or CLI session export is
contacted here. Every backend is a scripted in-memory fake.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import re
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = ROOT / "benchmarks"
for path in (str(ROOT), str(BENCHMARKS)):
    if path not in sys.path:
        sys.path.insert(0, path)

from benchmarks.memory_live import runner  # noqa: E402
from benchmarks.live_model.service_projection import project_service_response  # noqa: E402
from benchmarks.evaluation.h3 import evaluate_h3, load_h3_records, parse_h3_manifest  # noqa: E402

SENTINEL = "SENTINEL_fixture_credential_value"
CATEGORY_RE = re.compile(r"mã nhóm (hcm_primary_geojson:source-category:[a-z_]+)")


def _frozen(manifest):
    value = json.loads(json.dumps(manifest))
    value["frozen"] = True
    value["review"] = {"decision": "test_only", "frozen": True,
                       "note": "synthetic test fixture, not a Codex freeze"}
    return value


class FakeBackend:
    def __init__(self, manifest, out):
        self.manifest = manifest
        self.out = Path(out)
        self.starts = 0
        self.stops = 0
        self.calls = []
        self.chat_bodies = []
        self.typed_bodies = []
        self.profiles = {}
        self.session_texts = {}
        self.session_enabled = {}
        self.session_categories = {}
        # CLI sessions differ from app sessions: explicit captured-input map.
        self.cli_session_texts = {}
        self.provider_to_session = {}
        self.chat_count = 0
        self.fail_prep_for = None
        self.failed_prep_once = False
        self.provider_fatal_at = None
        self.fail_chat_at = None
        self.fail_chat_status = 401
        self.fail_chat_error_code = "quota"
        self.fail_stop_on = None
        self.release_after = None
        self.bad_input_for = None
        self.sentinel = SENTINEL
        self.prep_top_error_code = None
        self.prep_failed_error_code = "cli_timeout"
        self.prep_top_error_emitted = False
        self.typed_business_error_code = None
        self.typed_business_remaining = 0

    def start(self):
        self.starts += 1

    def stop(self):
        self.stops += 1
        if self.fail_stop_on is not None and self.stops == self.fail_stop_on:
            raise RuntimeError("synthetic owned stop failure")

    def _provider(self, session_id, ok=True, attempts=1, error_code=None):
        call = {
            "ok": ok,
            "attempts": attempts,
            "session_id": session_id,
            "observed_model": runner.MODEL,
            "raw_provider_blob": SENTINEL,
        }
        if error_code is not None:
            call["error_code"] = error_code
        return {
            "selected": "opencode_cli",
            "observed_model": runner.MODEL,
            "calls": [call],
        }

    def _planning(self, category_id):
        truth = self.manifest["category_truth"]
        ids = [poi_id for poi_id, cats in truth.items() if category_id in cats][:3]
        authored = (("09:00:00", "09:45:00"), ("10:00:00", "10:45:00"),
                    ("11:00:00", "11:45:00"))
        stops = []
        for index, poi_id in enumerate(ids):
            start, end = authored[index % len(authored)]
            stops.append({
                "poi_id": poi_id,
                "arrival": f"2026-11-01T{start}+07:00",
                "departure": f"2026-11-01T{end}+07:00",
                "cost_party": None,
            })
        return {
            "repaired_schedule": {
                "scheduler_status": "ok",
                "sequence": ids,
                "days": [{"day_id": "d1", "stops": stops}],
                "total_cost_party": None,
            },
            "validator_status": "feasible",
            "verified": True,
            "facts_fully_known": False,
            "validation": {"status": "feasible", "known_violations": [],
                           "unsatisfied_required": []},
            "selected_plan_route": {
                "coverage": "partial",
                "scope": "selected_plan",
                "verified": False,
                "legs": [],
            },
            "request_constraints": {
                "transport_mode": "car",
                "transport_mode_source": "request",
                "scope_mode": "source_scope_contract",
                "source_scope": dict(runner.SOURCE),
            },
            "cost": {"total_cost_party": None},
            "totals": {"total_cost_party": None, "total_distance_km": 2.4},
            "model_usage": None,
        }

    def _cli_capture(self, app_session, text):
        """CLI session id differs from the app session id by design."""
        cli_session = "ses_" + "fake" + str(self.chat_count).zfill(8)
        self.provider_to_session[cli_session] = app_session
        self.cli_session_texts[cli_session] = {
            "text": text,
            "enabled": self.session_enabled.get(app_session, False),
        }
        return cli_session

    def _chat_payload(self, body, owner, ok=True):
        message = body["message"]
        if message.startswith("Tôi thích"):
            match = CATEGORY_RE.search(message)
            category = match.group(1) if match else "hcm_primary_geojson:source-category:coffee"
            self.session_categories[body["session_id"]] = category
        # Real /chat preparation and lifecycle replies carry no typed planning.
        cli_session = self._cli_capture(
            body["session_id"],
            "\n".join(self.session_texts.get(body["session_id"], [])))
        return {
            "status": "success",
            "intent": "TRAVEL",
            "reply": "synthetic fake model output, not live evidence",
            "model": runner.MODEL,
            "provider": self._provider(cli_session, ok=ok),
            "source_scope": dict(runner.SOURCE),
            "unknown_private_subtree": {"credential": SENTINEL},
        }

    def _typed_payload(self, body, owner, ok=True):
        app_session = body["session_id"]
        category = self.session_categories.get(app_session)
        if category is None:
            owner_profile = self.profiles.get(owner, {}).get("profile") or {}
            tags = owner_profile.get("tags") or []
            category = tags[0] if tags else "hcm_primary_geojson:source-category:coffee"
        cli_session = self._cli_capture(
            app_session,
            "\n".join(self.session_texts.get(app_session, [])))
        planning = self._planning(category)
        return {
            "status": "success",
            "intent": "TRAVEL",
            "reply": "synthetic fake typed itinerary, not live evidence",
            "model": runner.MODEL,
            "provider": self._provider(cli_session, ok=ok),
            # No top-level source_scope: the typed contract is nested.
            "grounding": {
                "status": "grounded",
                "scope_mode": "source_scope_contract",
                "scope_contract": "source_scope_contract",
                "source_scope": dict(runner.SOURCE),
                "selected_poi_ids": list(planning["repaired_schedule"]["sequence"]),
            },
            "planning": planning,
            "unknown_private_subtree": {"credential": SENTINEL},
        }

    def _generating(self, path, body, owner):
        if (self.prep_top_error_code is not None and not self.prep_top_error_emitted
                and path == "/chat"
                and body["message"].startswith("Tôi thích")):
            self.prep_top_error_emitted = True
            calls = [
                {"ok": True, "attempts": 1, "session_id": "ses_prep_ok_a",
                 "observed_model": runner.MODEL, "raw_provider_blob": SENTINEL},
                {"ok": True, "attempts": 1, "session_id": "ses_prep_ok_b",
                 "observed_model": runner.MODEL, "raw_provider_blob": SENTINEL},
                {"ok": False, "attempts": 1,
                 "error_code": self.prep_failed_error_code,
                 "raw_provider_blob": SENTINEL},
            ]
            return {"status": 200, "payload": {
                        "status": "error",
                        "error": {"code": self.prep_top_error_code},
                        "provider": {"selected": "opencode_cli",
                                     "observed_model": runner.MODEL,
                                     "calls": calls},
                        "detail": SENTINEL, "message": SENTINEL},
                    "elapsed_seconds": 0.01}
        if (self.typed_business_error_code is not None
                and self.typed_business_remaining > 0
                and path == "/generate_itinerary"):
            self.typed_business_remaining -= 1
            return {"status": 200, "payload": {
                        "status": "error", "intent": "TRAVEL",
                        "model": runner.MODEL,
                        "error": {"code": self.typed_business_error_code},
                        "provider": self._provider("ses_typed_business_ok"),
                        "detail": SENTINEL, "message": SENTINEL},
                    "elapsed_seconds": 0.01}
        if (self.fail_chat_at
                and self.chat_count == self.fail_chat_at):
            return {"status": self.fail_chat_status,
                    "payload": {"status": "error",
                                "error": {"code": self.fail_chat_error_code},
                                "detail": SENTINEL,
                                "provider": self._provider(
                                    "ses_fake_failed", ok=False,
                                    error_code=self.fail_chat_error_code)},
                    "elapsed_seconds": 0.01}
        if (self.provider_fatal_at
                and self.chat_count == self.provider_fatal_at):
            return {"status": 200,
                    "payload": {"status": "error", "intent": "TRAVEL",
                                "model": runner.MODEL,
                                "source_scope": dict(runner.SOURCE),
                                "error": {"code": "provider_failed"},
                                "provider": self._provider(
                                    "ses_provider_fatal", ok=False)},
                    "elapsed_seconds": 0.01}
        if (self.fail_prep_for and not self.failed_prep_once
                and path == "/chat"
                and body["message"].startswith("Tôi thích")
                and self.fail_prep_for in body["message"]):
            self.failed_prep_once = True
            return {"status": 200,
                    "payload": {"status": "success", "intent": "GENERAL",
                                "model": runner.MODEL,
                                "source_scope": dict(runner.SOURCE),
                                "provider": self._provider(
                                    "ses_prep_ordinary")},
                    "elapsed_seconds": 0.01}
        return None

    def request(self, method, path, body=None, owner=None):
        self.calls.append({"method": method, "path": path, "owner": owner})
        if method == "PUT" and path == "/memory/profile":
            current = self.profiles.get(owner)
            expected = (body or {}).get("expected_version")
            if expected is not None and (current is None or current["version"] != expected):
                return {"status": 409, "payload": {"detail": {"code": "revision_conflict"}},
                        "elapsed_seconds": 0.01}
            version = 1 if current is None else current["version"] + 1
            self.profiles[owner] = {"profile": body["profile"], "version": version}
            return {"status": 200, "payload": {"profile": body["profile"],
                                               "version": version},
                    "elapsed_seconds": 0.01}
        if method == "GET" and path == "/memory/profile":
            current = self.profiles.get(owner)
            if current is None:
                return {"status": 200, "payload": {"profile": None, "version": None},
                        "elapsed_seconds": 0.01}
            return {"status": 200, "payload": dict(current), "elapsed_seconds": 0.01}
        if method == "DELETE" and path == "/memory/profile":
            existed = owner in self.profiles
            self.profiles.pop(owner, None)
            return {"status": 200, "payload": {"deleted": existed},
                    "elapsed_seconds": 0.01}
        if method == "POST" and path == "/memory/short/clear":
            session = body["session_id"]
            existed = bool(self.session_texts.pop(session, None))
            return {"status": 200, "payload": {"cleared": existed},
                    "elapsed_seconds": 0.01}
        if method == "POST" and path in ("/chat", "/generate_itinerary"):
            self.chat_count += 1
            if path == "/chat":
                self.chat_bodies.append(dict(body))
                text = body["message"]
            else:
                self.typed_bodies.append(dict(body))
                text = body["user_description"]
            injected = self._generating(path, body, owner)
            if injected is not None:
                return injected
            app_session = body["session_id"]
            self.session_texts.setdefault(app_session, []).append(text)
            self.session_enabled[app_session] = body["memory_enabled"]
            if path == "/chat":
                return {"status": 200,
                        "payload": self._chat_payload(body, owner),
                        "elapsed_seconds": 0.01}
            return {"status": 200,
                    "payload": self._typed_payload(body, owner),
                    "elapsed_seconds": 0.01}
        raise AssertionError(f"unexpected fake request {method} {path}")

    def input_flags(self, provider_calls, profile, history_marker):
        session_id = provider_calls[0]["session_id"]
        captured = self.cli_session_texts.get(session_id, {})
        text = captured.get("text", "")
        enabled = captured.get("enabled", False)
        if self.bad_input_for and self.bad_input_for in text:
            return {"status": "unknown", "reason": "synthetic_input_unproven"}
        return {
            "status": "proven",
            "session_export": True,
            "history_marker": enabled and history_marker in text,
            "profile_prompt": bool(profile) and enabled,
            "profile_prompt_expected": bool(profile),
            "fixture_credentials_absent": True,
        }

    def assert_clean(self, value):
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
        if SENTINEL in text:
            raise AssertionError("fixture credential sentinel reached an artifact")


@pytest.fixture()
def manifest():
    return runner.build_candidate_manifest()


@pytest.fixture()
def fake_factory(monkeypatch):
    holder = {}

    def factory(manifest_value, out):
        backend = FakeBackend(manifest_value, out)
        holder["backend"] = backend
        return backend

    monkeypatch.setattr(runner, "backend_factory", factory)
    return holder


def _write_manifest(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _run_execute(tmp_path, monkeypatch, manifest_value):
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path, manifest_value)
    out = tmp_path / "out"
    code = runner.main(["--out", str(out), "--manifest", str(manifest_path),
                        "--execute"])
    return code, out


def test_candidate_manifest_is_exact_unfrozen_plan(manifest):
    parsed = parse_h3_manifest(manifest)
    assert manifest["frozen"] is False
    assert manifest["thesis_mode"] is False
    assert parsed["scenario_ids"] == ("H3_MAIN",)
    assert parsed["repetitions_per_case"] == 1
    assert len(parsed["expected_keys"]) == 15
    assert set(parsed["profile_ids"]) == set(runner.PROFILE_IDS)
    assert set(parsed["conditions"]) == set(runner.CONDITIONS)
    assert len(manifest["category_truth"]) == 1483
    assert len(manifest["primary_cells"]) == 15
    assert manifest["review"]["decision"] == "pending_codex_review"
    for key, path_constant, hash_constant in (
            ("design", runner.EXECUTION_DESIGN, runner.DESIGN_SHA256),
            ("source_analysis", runner.SOURCE_ANALYSIS,
             runner.SOURCE_ANALYSIS_SHA256),
            ("profile_design", runner.PROFILE_DESIGN,
             runner.PROFILE_DESIGN_SHA256),
            ("before_source_manifest", runner.BEFORE_SOURCE_MANIFEST,
             runner.BEFORE_SOURCE_MANIFEST_SHA256)):
        declared = manifest[key]
        resolved = (ROOT / declared["path"]).resolve()
        assert resolved == path_constant.resolve()
        assert declared["sha256"] == hash_constant
        assert runner._sha256_file(resolved) == declared["sha256"]
    with pytest.raises(ValueError):
        runner.validate_execution_manifest(manifest)


def test_dry_run_has_zero_native_calls_and_generates_unfrozen_manifest(
        tmp_path, monkeypatch, manifest):
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path, manifest)

    def deny(*args, **kwargs):
        raise AssertionError("backend factory must not be resolved on dry-run")

    monkeypatch.setattr(runner, "backend_factory", deny)
    out = tmp_path / "dry"
    code = runner.main(["--out", str(out), "--manifest", str(manifest_path)])
    assert code == 0
    summary = json.loads((out / "dry_run.json").read_text(encoding="utf-8"))
    assert summary["native_calls"] == 0
    assert summary["provider_calls"] == 0
    assert summary["planned_primary_cells"] == 15
    assert summary["planned_preparation_chats"] == 15
    assert summary["planned_scoring_chats"] == 15
    assert summary["planned_typed_score_requests"] == 15
    assert summary["planned_lifecycle_chats_max"] == 3
    assert summary["planned_model_generating_requests_max"] == 33
    assert summary["request_paths"] == {"preparation": "/chat",
                                        "primary_score": "/generate_itinerary",
                                        "lifecycle": "/chat"}
    assert all(item["path"] == "/generate_itinerary"
               for item in summary["planned_requests"]
               if item["stage"] == "primary_score")
    assert all(item["path"] == "/chat"
               for item in summary["planned_requests"]
               if item["stage"] == "primary_preparation")
    assert summary["typed_request_body_without_session_and_memory"] == \
        runner.TYPED_SHARED_BODY
    candidate = json.loads((out / "candidate_manifest.json").read_text(encoding="utf-8"))
    assert candidate["frozen"] is False and candidate["thesis_mode"] is False


def test_execute_refuses_unfrozen_before_factory(tmp_path, monkeypatch, manifest):
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path, manifest)

    def deny(*args, **kwargs):
        raise AssertionError("backend factory must not be resolved")

    monkeypatch.setattr(runner, "backend_factory", deny)
    code = runner.main(["--out", str(tmp_path / "out"),
                        "--manifest", str(manifest_path), "--execute"])
    assert code == 2


def test_execute_refuses_wrong_source_or_code_binding(tmp_path, monkeypatch, manifest):
    frozen = _frozen(manifest)
    calls = []

    def factory(*args, **kwargs):
        calls.append(True)
        raise AssertionError("must refuse before factory")

    monkeypatch.setattr(runner, "backend_factory", factory)
    broken = json.loads(json.dumps(frozen))
    broken["source_scope"]["input_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        runner.validate_execution_manifest(broken)
    broken = json.loads(json.dumps(frozen))
    broken["code_binding"]["sha256"] = "0" * 64
    with pytest.raises(ValueError):
        runner.validate_execution_manifest(broken)
    assert not calls


def test_selected_ids_come_only_from_structured_days_and_unknowns_fail(manifest):
    truth = manifest["category_truth"]
    ids = list(truth)[:2]
    payload = {
        "status": "success",
        "model": runner.MODEL,
        "source_scope": dict(runner.SOURCE),
        "provider": {"calls": [{"ok": True, "attempts": 1,
                                "session_id": "ses_projection"}]},
        "planning": {"repaired_schedule": {"days": [
            {"day_id": "d1", "stops": [
                {"poi_id": ids[0], "arrival": "2026-11-01T09:00:00+07:00",
                 "departure": "2026-11-01T09:45:00+07:00", "cost_party": None},
                {"poi_id": ids[1], "arrival": "2026-11-01T10:00:00+07:00",
                 "departure": "2026-11-01T10:45:00+07:00"},
            ]}]}},
    }
    projection = project_service_response(payload, http_status=200, elapsed_seconds=1.5)
    selected, error = runner._selected_ids_from_projection(projection)
    assert error is None and selected == ids
    stop = projection["planning"]["repaired_schedule"]["days"][0]["stops"][0]
    assert stop["cost_party"] is None
    assert stop["arrival"] == "2026-11-01T09:00:00+07:00"
    assert projection["global_feasibility"] == "unverifiable"
    payload["planning"]["repaired_schedule"]["days"][0]["stops"][0]["poi_id"] = "not-in-source"
    projection = project_service_response(payload, http_status=200, elapsed_seconds=1.5)
    selected, _ = runner._selected_ids_from_projection(projection)
    assert selected == ["not-in-source", ids[1]]
    assert all(poi not in truth for poi in selected[:1])


def test_full_primary_and_lifecycle_run_is_exact_and_offline(
        tmp_path, monkeypatch, manifest, fake_factory):
    frozen = _frozen(manifest)
    code, out = _run_execute(tmp_path, monkeypatch, frozen)
    backend = fake_factory["backend"]
    result = json.loads((out / "result.json").read_text(encoding="utf-8"))
    assert code == 0
    assert result["status"] == "completed"
    assert result["calls"]["preparation_chats"] == 15
    assert result["calls"]["scoring_chats"] == 15
    assert result["calls"]["typed_scoring_requests"] == 15
    assert result["calls"]["lifecycle_chats"] == 3
    assert result["calls"]["total_chat_requests"] == 33
    assert result["calls"]["total_model_generating_requests"] == 33
    assert result["stage_accounting"] == {
        "preparation_chat_requests": 15,
        "typed_scoring_requests": 15,
        "lifecycle_chat_requests": 3,
        "lifecycle_setup_requests": 5,
    }
    assert backend.chat_count == 33
    assert len(backend.chat_bodies) == 18
    assert len(backend.typed_bodies) == 15
    assert backend.starts == 2 and backend.stops == 2
    records = [json.loads(line) for line in
               (out / "h3_records.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(records) == 15
    assert all(record["usage"] is None for record in records)
    assert all(record["run_status"] == "completed" for record in records)
    assert result["primary"]["missing_cells"] == 0
    assert result["input_observability"]["verdicts"]["proven"] == 15
    assert result["lifecycle"]["status"] == "completed"
    assert result["lifecycle"]["chats"] == 3
    assert all(case["passed"] is True for case in result["lifecycle"]["cases"])
    assert "preferred_share" not in result["lifecycle"]

    # Latin rotation: each profile's three conditions are a distinct rotation.
    orders = {}
    for cell in frozen["primary_cells"]:
        orders.setdefault(cell["profile_id"], []).append(cell["condition"])
    assert orders["M1"] == ["memory_disabled", "short_term", "two_tier"]
    assert orders["M2"] == ["short_term", "two_tier", "memory_disabled"]
    assert orders["M3"] == ["two_tier", "memory_disabled", "short_term"]

    # Disabled never sends memory_enabled=true; only two_tier writes a profile.
    disabled = [body for body in backend.typed_bodies
                if not body["memory_enabled"]]
    assert len(disabled) == 5
    puts = [call for call in backend.calls
            if call["method"] == "PUT" and call["path"] == "/memory/profile"]
    # Five primary two_tier profiles plus the lifecycle CAS update.
    assert len(puts) == 6
    primary_bodies = backend.chat_bodies[:15] + backend.typed_bodies
    assert len({body["session_id"] for body in primary_bodies}) == 15
    # Preparation and typed score for one cell share owner and session.
    for typed in backend.typed_bodies:
        prep = [item for item in backend.chat_bodies
                if item["session_id"] == typed["session_id"]
                and item["message"].startswith("Tôi thích")]
        assert len(prep) == 1
        assert typed["source_scope"] == prep[0]["source_scope"] == runner.SOURCE
        assert typed["day_windows"][0]["start"] == "2026-11-01T09:00:00+07:00"
        assert typed["visit_minutes"] == 45 and typed["transport_mode"] == "car"
    # Non-session/non-memory typed fields are identical across conditions.
    stripped = [{key: value for key, value in body.items()
                 if key not in ("session_id", "memory_enabled")}
                for body in backend.typed_bodies]
    assert all(item == stripped[0] for item in stripped)
    assert set(stripped[0]) == set(runner.TYPED_SHARED_BODY)
    assert {body["memory_enabled"] for body in backend.typed_bodies} == {
        True, False}

    # The strict evaluator accepts the planned 5x3 records; no p-value exists.
    parsed = parse_h3_manifest(frozen)
    metrics = evaluate_h3(parsed, load_h3_records(records, parsed))
    assert metrics["planned_runs"] == 15
    assert metrics["observed_runs"] == 15
    assert metrics["thesis_conclusion"] is False
    assert "p_value" not in json.dumps(metrics).lower()


def test_setup_failure_keeps_denominator_and_never_retries(
        tmp_path, monkeypatch, manifest, fake_factory):
    frozen = _frozen(manifest)
    original_factory = runner.backend_factory

    def factory(manifest_value, out):
        backend = FakeBackend(manifest_value, out)
        backend.fail_prep_for = "H3_HISTORY_M2"
        fake_factory["backend"] = backend
        return backend

    monkeypatch.setattr(runner, "backend_factory", factory)
    code, out = _run_execute(tmp_path, monkeypatch, frozen)
    backend = fake_factory["backend"]
    result = json.loads((out / "result.json").read_text(encoding="utf-8"))
    assert code == 1
    assert result["primary"]["setup_failures"] == 1
    assert result["primary"]["recorded_cells"] == 14
    assert result["primary"]["missing_cells"] == 1
    assert result["primary"]["stopped_early"] is False
    # Exactly one injected cell fails once; the key is never retried.
    prep_bodies = [body for body in backend.chat_bodies
                   if body["message"].startswith("Tôi thích")]
    assert len(prep_bodies) == 15
    failing = [body for body in prep_bodies
               if body["session_id"].startswith("exp080-M2-short_term-")]
    assert len(failing) == 1
    failing_key = "H3_MAIN:M2:short_term:0:prep"
    ledger = [json.loads(line) for line in
              (out / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
    reserved = [row for row in ledger if row["event"] == "reserved"
                and row["request_key"] == failing_key]
    assert len(reserved) == 1
    not_attempted = [row for row in ledger
                     if row["event"] == "planned_not_attempted"
                     and row["request_key"] == "H3_MAIN:M2:short_term:0:score"]
    assert len(not_attempted) == 1
    assert not_attempted[0]["reason"] == "preparation_failed"


def test_auth_stop_preserves_planned_cells_and_zero_retries(
        tmp_path, monkeypatch, manifest, fake_factory):
    frozen = _frozen(manifest)

    def factory(manifest_value, out):
        backend = FakeBackend(manifest_value, out)
        backend.fail_chat_at = 2
        backend.fail_chat_status = 429
        fake_factory["backend"] = backend
        return backend

    monkeypatch.setattr(runner, "backend_factory", factory)
    code, out = _run_execute(tmp_path, monkeypatch, frozen)
    backend = fake_factory["backend"]
    result = json.loads((out / "result.json").read_text(encoding="utf-8"))
    assert code == 1
    assert result["primary"]["stopped_early"] is True
    assert result["primary"]["planned_cells"] == 15
    assert backend.chat_count == 2  # one prep + one failed score, no retry
    assert result["primary"]["recorded_cells"] == 1
    assert result["primary"]["missing_cells"] == 14


def test_credential_sentinel_and_raw_subtrees_are_not_persisted(
        tmp_path, monkeypatch, manifest, fake_factory):
    frozen = _frozen(manifest)
    _code, out = _run_execute(tmp_path, monkeypatch, frozen)
    for path in out.rglob("*"):
        if path.is_file():
            assert SENTINEL not in path.read_text(encoding="utf-8", errors="ignore")
    observation = json.loads((out / "observations.jsonl").read_text(
        encoding="utf-8").splitlines()[0])
    receipt = observation["provider_receipts"][0]
    assert "raw_provider_blob" not in receipt
    assert set(receipt) <= {"ok", "error_code", "retryable", "attempts",
                            "session_id", "observed_model", "model", "provider",
                            "assistant_message_id", "identity_source",
                            "observed_provider_id", "observed_model_id"}


def test_input_flags_disabled_short_and_two_tier(manifest):
    backend = FakeBackend(manifest, Path("."))
    # Direct fake-contract checks: the runner's expectation table is explicit.
    assert runner._expected_flags("memory_disabled") == {
        "history_marker": False, "profile_prompt": False}
    assert runner._expected_flags("short_term") == {
        "history_marker": True, "profile_prompt": False}
    assert runner._expected_flags("two_tier") == {
        "history_marker": True, "profile_prompt": True}
    assert runner._flags_verdict({"status": "proven", "session_export": True,
                                  "fixture_credentials_absent": True,
                                  "history_marker": False,
                                  "profile_prompt": False}, "memory_disabled") == "proven"
    assert runner._flags_verdict({"status": "proven", "session_export": True,
                                  "fixture_credentials_absent": True,
                                  "history_marker": True,
                                  "profile_prompt": False}, "short_term") == "proven"
    assert runner._flags_verdict({"status": "proven", "session_export": True,
                                  "fixture_credentials_absent": True,
                                  "history_marker": True,
                                  "profile_prompt": True}, "two_tier") == "proven"
    assert runner._flags_verdict({"status": "unknown"}, "two_tier") == "unknown"
    assert runner._flags_verdict({"status": "proven", "history_marker": False,
                                  "profile_prompt": True}, "two_tier") == "unknown"
    assert runner._flags_verdict({"status": "proven", "session_export": True,
                                  "history_marker": False,
                                  "profile_prompt": False}, "memory_disabled") == "unknown"
    assert runner._flags_verdict({"status": "proven", "session_export": True,
                                  "fixture_credentials_absent": False,
                                  "history_marker": False,
                                  "profile_prompt": False}, "memory_disabled") == "unknown"
    assert runner._flags_verdict({"status": "proven", "session_export": True,
                                  "fixture_credentials_absent": True,
                                  "history_marker": False,
                                  "profile_prompt": True}, "two_tier") == "mismatch"


def _export(session_id, text, model="deepseek-v4.1-flash", provider="opencode-go"):
    return {
        "info": {"id": session_id},
        "messages": [
            {"type": "user", "id": "usr_" + session_id, "text": text},
            {"type": "assistant", "id": "msg_" + session_id,
             "model": {"id": model, "providerID": provider},
             "agent": "fixture", "finish": "stop",
             "tokens": {"input": 1, "output": 1, "total": 2},
             "content": [{"type": "text", "text": "synthetic answer"}]},
        ],
    }


def _good_receipt(session_id, **extra):
    receipt = {"ok": True, "attempts": 1, "session_id": session_id,
               "observed_model": runner.MODEL}
    receipt.update(extra)
    return receipt


def test_every_contributing_receipt_requires_exact_identity():
    good = _good_receipt("ses_stage_a")
    assert runner._receipts_identity_error([good]) is None
    assert runner._receipts_identity_error([]) == "provider_receipt_missing"
    bad_receipts = [
        {"ok": False, "attempts": 1, "session_id": "ses_a",
         "observed_model": runner.MODEL},
        {"ok": True, "attempts": True, "session_id": "ses_a",
         "observed_model": runner.MODEL},
        {"ok": True, "attempts": 0, "session_id": "ses_a",
         "observed_model": runner.MODEL},
        {"ok": True, "attempts": 2, "session_id": "ses_a",
         "observed_model": runner.MODEL},
        {"ok": True, "attempts": 1, "session_id": "not-a-session",
         "observed_model": runner.MODEL},
        {"ok": True, "attempts": 1, "session_id": "ses_a",
         "observed_model": "wrong/model"},
        {"ok": True, "attempts": 1, "session_id": "ses_a"},
        "not-a-mapping",
    ]
    for bad in bad_receipts:
        assert runner._receipts_identity_error([bad]) is not None
    assert runner._receipts_identity_error(
        [good, _good_receipt("ses_stage_b", attempts=2)]) == "retry_detected"


def test_native_input_flags_multi_stage_identity_and_last_synthesis(
        tmp_path, monkeypatch, manifest):
    backend = runner.NativeBackend(manifest, tmp_path)
    profile = manifest["profiles"][0]["initial_profile"]
    block = backend._profile_block(profile)
    assert isinstance(block, str) and block
    marker = "H3_HISTORY_M1"
    stage1, stage2 = "ses_native_stage1", "ses_native_stage2"
    calls = [_good_receipt(stage1), _good_receipt(stage2)]
    data = {
        stage1: _export(stage1, "intermediate stage without memory"),
        stage2: _export(stage2, block + "\n" + marker),
    }
    exported = []

    def fake_run(argv, *args, **kwargs):
        session_id = next(session for session in data if session in argv)
        exported.append(session_id)
        return SimpleNamespace(returncode=0, stdout=json.dumps(
            data.get(session_id, {})).encode(), stderr=b"")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    flags = backend.input_flags(calls, profile, marker)
    assert flags["status"] == "proven"
    assert flags["session_export"] is True
    assert flags["history_marker"] is True
    assert flags["profile_prompt"] is True
    assert flags["fixture_credentials_absent"] is True
    assert exported == [stage1, stage2]

    # Only the last contributing stage (synthesis input) is inspected.
    data[stage2] = _export(stage2, "last stage without memory")
    flags = backend.input_flags(calls, profile, marker)
    assert flags["status"] == "proven"
    assert flags["profile_prompt"] is False and flags["history_marker"] is False

    # profile=None is not absence proof: an unexpected fence must not pass.
    data[stage1] = _export(stage1, block + "\n" + marker)
    data[stage2] = _export(
        stage2, "<untrusted_profile>\n# STORED USER PROFILE (unexpected)\n")
    flags = backend.input_flags(calls, None, marker)
    assert flags["status"] == "proven"
    assert flags["profile_prompt"] is True
    assert flags["profile_prompt_expected"] is False
    assert runner._flags_verdict(flags, "memory_disabled") == "mismatch"

    # Wrong identity in any earlier contributing stage cannot prove input.
    data[stage1] = _export(stage1, "earlier", model="wrong-model")
    data[stage2] = _export(stage2, block + "\n" + marker)
    flags = backend.input_flags(calls, profile, marker)
    assert flags["status"] == "unknown"
    assert flags["reason"] == "export_model_mismatch"

    # Foreign exported session cannot satisfy the requested session.
    data[stage1] = _export(stage1, "earlier")
    data[stage2] = _export("ses_foreign", block + "\n" + marker)
    flags = backend.input_flags(calls, profile, marker)
    assert flags["status"] == "unknown"
    assert flags["reason"] == "export_session_mismatch"

    # Supplied assistant-message identity must match the export.
    data[stage2] = _export(stage2, block + "\n" + marker)
    mismatched = [_good_receipt(stage2, assistant_message_id="msg_wrong")]
    flags = backend.input_flags(mismatched, profile, marker)
    assert flags["status"] == "unknown"
    assert flags["reason"] == "export_message_mismatch"

    # A fixture credential in any captured export aborts without persistence.
    data[stage2] = _export(stage2, backend.fixture_secret + " " + marker)
    with pytest.raises(runner.BoundedError) as excinfo:
        backend.input_flags(calls, profile, marker)
    assert excinfo.value.code == "fixture_credential_in_export"


def test_non_proven_input_flags_cannot_deliver(manifest):
    cell = manifest["primary_cells"][0]
    poi_id = next(iter(manifest["category_truth"]))
    payload = {
        "status": "success", "intent": "TRAVEL", "model": runner.MODEL,
        "source_scope": dict(runner.SOURCE),
        "provider": {"observed_model": runner.MODEL,
                     "calls": [{"ok": True, "attempts": 1,
                                "session_id": "ses_record_fixture",
                                "observed_model": runner.MODEL}]},
        "grounding": {"status": "grounded",
                      "source_scope": dict(runner.SOURCE)},
        "planning": {"repaired_schedule": {"scheduler_status": "ok", "days": [{
            "day_id": "d1", "stops": [{"poi_id": poi_id,
                                       "arrival": "2026-11-01T09:00:00+07:00",
                                       "departure": "2026-11-01T09:20:00+07:00"}]}],
            "sequence": [poi_id]},
            "request_constraints": {"source_scope": dict(runner.SOURCE),
                                    "transport_mode": "car"},
            "validator_status": "feasible", "verified": True,
            "validation": {"status": "feasible"}},
        "usage": {"model_calls": 1, "input_tokens": 11,
                  "output_tokens": 7, "total_tokens": 18},
    }
    for verdict in ("mismatch", "unknown"):
        record, observation = runner._record_from_response(
            manifest=manifest, cell=cell, payload=payload, http_status=200,
            elapsed_seconds=0.2,
            provider_receipts=runner._provider_receipts(payload),
            input_flags={"status": "proven", "session_export": True,
                         "history_marker": False, "profile_prompt": False,
                         "fixture_credentials_absent": True},
            input_verdict=verdict)
        expected_code = ("input_proof_mismatch" if verdict == "mismatch"
                         else "input_proof_unknown")
        assert record["run_status"] == "error"
        assert record["selected_poi_ids"] == []
        assert observation["status"] == "not_delivered"
        assert observation["reason"] == expected_code
        assert observation["projection"]["planning"]["repaired_schedule"]
        assert observation["usage_components"]["model_calls"] == 1


def test_http200_provider_fatal_stops_all_remaining_cells(
        tmp_path, monkeypatch, manifest, fake_factory):
    frozen = _frozen(manifest)

    def factory(manifest_value, out):
        backend = FakeBackend(manifest_value, out)
        backend.provider_fatal_at = 2
        fake_factory["backend"] = backend
        return backend

    monkeypatch.setattr(runner, "backend_factory", factory)
    code, out = _run_execute(tmp_path, monkeypatch, frozen)
    backend = fake_factory["backend"]
    result = json.loads((out / "result.json").read_text(encoding="utf-8"))
    assert code == 1
    assert result["primary"]["stopped_early"] is True
    assert result["primary"]["stop_reason"] == "provider_fatal"
    assert backend.chat_count == 2
    assert result["primary"]["recorded_cells"] == 1
    assert result["primary"]["missing_cells"] == 14
    assert result["primary"]["planned_cells"] == 15
    assert result["lifecycle"]["status"] == "skipped"
    ledger = [json.loads(line) for line in
              (out / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
    skipped = [row for row in ledger if row["event"] == "planned_not_attempted"]
    assert len(skipped) == 28
    assert any(row["request_key"] == "H3_MAIN:M1:short_term:0:prep"
               for row in skipped)


def test_lifecycle_provider_fatal_stops_and_counts_attempts(
        tmp_path, monkeypatch, manifest, fake_factory):
    frozen = _frozen(manifest)

    def factory(manifest_value, out):
        backend = FakeBackend(manifest_value, out)
        backend.provider_fatal_at = 31  # first lifecycle chat after 30 primary
        fake_factory["backend"] = backend
        return backend

    monkeypatch.setattr(runner, "backend_factory", factory)
    code, out = _run_execute(tmp_path, monkeypatch, frozen)
    backend = fake_factory["backend"]
    result = json.loads((out / "result.json").read_text(encoding="utf-8"))
    assert code == 1
    assert result["primary"]["recorded_cells"] == 15
    lifecycle = result["lifecycle"]
    assert lifecycle["status"] == "partial"
    assert lifecycle["chats"] == 1
    assert lifecycle["cli_attempts"] == 1
    assert lifecycle["stage_counts"] == {"lifecycle_setup": 2,
                                         "lifecycle_chat": 1}
    assert result["calls"]["lifecycle_chats"] == 1
    assert result["calls"]["known_cli_attempts"] == 31
    # The fake flags look good, but the failed lifecycle chat still cannot pass.
    failed_chat = next(case for case in lifecycle["cases"]
                       if case["case"] == "contradictory_chat_profile_fenced")
    assert failed_chat["passed"] is False
    assert any(case["passed"] is None for case in lifecycle["cases"])
    assert backend.starts == 1 and backend.stops == 1


def test_owned_cleanup_failure_marks_partial(
        tmp_path, monkeypatch, manifest, fake_factory):
    frozen = _frozen(manifest)

    def factory(manifest_value, out):
        backend = FakeBackend(manifest_value, out)
        backend.fail_stop_on = 2  # owned restart stop succeeds; final cleanup fails
        fake_factory["backend"] = backend
        return backend

    monkeypatch.setattr(runner, "backend_factory", factory)
    code, out = _run_execute(tmp_path, monkeypatch, frozen)
    backend = fake_factory["backend"]
    result = json.loads((out / "result.json").read_text(encoding="utf-8"))
    assert code == 1
    assert result["status"] == "partial"
    assert result["failure_code"] == "owned_cleanup_failed"
    assert result["cleanup"] == {"attempted": True, "ok": False,
                                 "error_code": "RuntimeError"}
    assert backend.stops == 2
    assert "synthetic owned stop failure" not in json.dumps(result)


def test_typed_payload_is_exact_and_condition_shared():
    shared = runner._itinerary_payload("app-session", "memory_disabled")
    assert shared.pop("session_id") == "app-session"
    assert shared.pop("memory_enabled") is False
    assert shared == runner.TYPED_SHARED_BODY
    assert runner.TYPED_SHARED_BODY["day_windows"][0] == {
        "date": "2026-11-01",
        "start": "2026-11-01T09:00:00+07:00",
        "end": "2026-11-01T16:00:00+07:00",
    }
    assert runner.TYPED_SHARED_BODY["visit_minutes"] == 45
    assert runner.TYPED_SHARED_BODY["transport_mode"] == "car"
    assert runner.TYPED_SHARED_BODY["source_scope"] == runner.SOURCE
    assert runner.TYPED_SHARED_BODY["minimum_stops"] == \
        runner.TYPED_SHARED_BODY["maximum_stops"] == 3
    for condition in ("short_term", "two_tier"):
        body = runner._itinerary_payload("same", condition)
        assert body["memory_enabled"] is True
        assert {key: value for key, value in body.items()
                if key not in ("session_id", "memory_enabled")} == \
            runner.TYPED_SHARED_BODY


def _typed_record_payload(manifest):
    cell = manifest["primary_cells"][0]
    ids = [poi_id for poi_id, categories in manifest["category_truth"].items()
           if cell["category_id"] in categories][:3]
    stops = [{"poi_id": poi_id,
              "arrival": f"2026-11-01T{9 + index:02d}:00:00+07:00",
              "departure": f"2026-11-01T{9 + index:02d}:45:00+07:00"}
             for index, poi_id in enumerate(ids)]
    payload = {
        "status": "success", "intent": "TRAVEL", "model": runner.MODEL,
        "provider": {"observed_model": runner.MODEL,
                     "calls": [{"ok": True, "attempts": 1,
                                "session_id": "ses_typed_fixture",
                                "observed_model": runner.MODEL}]},
        "grounding": {"status": "grounded",
                      "source_scope": dict(runner.SOURCE)},
        "planning": {
            "validator_status": "feasible",
            "verified": True,
            "facts_fully_known": False,
            "validation": {"status": "feasible", "known_violations": [],
                           "unsatisfied_required": []},
            "selected_plan_route": {"coverage": "partial",
                                    "scope": "selected_plan"},
            "request_constraints": {"transport_mode": "car",
                                    "source_scope": dict(runner.SOURCE)},
            "repaired_schedule": {"scheduler_status": "ok",
                                  "sequence": ids,
                                  "days": [{"day_id": "d1", "stops": stops}]},
        },
    }
    return cell, payload, stops


def test_typed_source_requires_both_nested_scopes(manifest):
    cell, payload, _stops = _typed_record_payload(manifest)

    def record(value):
        return runner._record_from_response(
            manifest=manifest, cell=cell, payload=value, http_status=200,
            elapsed_seconds=0.1,
            provider_receipts=runner._provider_receipts(value),
            input_flags={"status": "proven", "session_export": True,
                         "history_marker": False, "profile_prompt": False,
                         "fixture_credentials_absent": True},
            input_verdict="proven")

    good, observation = record(json.loads(json.dumps(payload)))
    assert good["run_status"] == "completed"
    assert good["selected_poi_ids"] == payload["planning"][
        "repaired_schedule"]["sequence"]
    assert observation["selected_stops"] == [
        {"poi_id": stop["poi_id"], "arrival": stop["arrival"],
         "departure": stop["departure"]} for stop in payload["planning"][
             "repaired_schedule"]["days"][0]["stops"]]

    broken = json.loads(json.dumps(payload))
    del broken["grounding"]
    assert record(broken)[0]["run_status"] == "error"
    assert record(broken)[1]["reason"] == "typed_source_mismatch"

    broken = json.loads(json.dumps(payload))
    del broken["planning"]["request_constraints"]["source_scope"]
    assert record(broken)[1]["reason"] == "typed_source_mismatch"

    broken = json.loads(json.dumps(payload))
    broken["grounding"]["source_scope"] = {"dataset_namespace": "other"}
    assert record(broken)[1]["reason"] == "typed_source_mismatch"

    broken = json.loads(json.dumps(payload))
    broken["planning"]["request_constraints"]["source_scope"] = {}
    assert record(broken)[1]["reason"] == "typed_source_mismatch"

    # A correct top-level source never substitutes for the nested scopes.
    broken = json.loads(json.dumps(payload))
    broken["source_scope"] = dict(runner.SOURCE)
    del broken["grounding"]
    record_broken, observation_broken = record(broken)
    assert record_broken["run_status"] == "error"
    assert record_broken["selected_poi_ids"] == []
    assert observation_broken["status"] == "not_delivered"
    assert record_broken["provenance"]["route_id"]


def test_typed_rejects_wrong_selected_id_and_missing_plan(manifest):
    cell, payload, _stops = _typed_record_payload(manifest)

    def record(value):
        return runner._record_from_response(
            manifest=manifest, cell=cell, payload=value, http_status=200,
            elapsed_seconds=0.1,
            provider_receipts=runner._provider_receipts(value),
            input_flags={"status": "proven", "session_export": True,
                         "history_marker": False, "profile_prompt": False,
                         "fixture_credentials_absent": True},
            input_verdict="proven")

    broken = json.loads(json.dumps(payload))
    broken["planning"]["repaired_schedule"]["days"][0]["stops"][0][
        "poi_id"] = "not-in-frozen-source"
    record_broken, observation = record(broken)
    assert record_broken["run_status"] == "error"
    assert record_broken["selected_poi_ids"] == []
    assert observation["reason"] == "out_of_universe_selected_id"
    assert observation["unknown_selected_ids"] == ["not-in-frozen-source"]

    broken = json.loads(json.dumps(payload))
    broken["planning"]["repaired_schedule"] = None
    assert record(broken)[1]["reason"] == "missing_plan"

    broken = json.loads(json.dumps(payload))
    del broken["planning"]
    assert record(broken)[1]["reason"] == "typed_source_mismatch"


def test_http503_stops_without_retry_and_keeps_denominator(
        tmp_path, monkeypatch, manifest, fake_factory):
    frozen = _frozen(manifest)

    def factory(manifest_value, out):
        backend = FakeBackend(manifest_value, out)
        backend.fail_chat_at = 2
        backend.fail_chat_status = 503
        fake_factory["backend"] = backend
        return backend

    monkeypatch.setattr(runner, "backend_factory", factory)
    code, out = _run_execute(tmp_path, monkeypatch, frozen)
    backend = fake_factory["backend"]
    result = json.loads((out / "result.json").read_text(encoding="utf-8"))
    assert code == 1
    assert result["status"] == "partial"
    assert result["primary"]["stopped_early"] is True
    assert result["primary"]["stop_reason"] == "provider_unavailable"
    assert result["primary"]["planned_cells"] == 15
    assert result["primary"]["recorded_cells"] == 1
    assert result["primary"]["missing_cells"] == 14
    assert backend.chat_count == 2  # one prep + one 503 score, no retry
    assert result["primary"]["stop_reason"] not in ("quota", "auth")
    assert "quota" not in json.dumps(result)
    ledger_text = (out / "ledger.jsonl").read_text(encoding="utf-8")
    assert SENTINEL not in ledger_text
    assert '"detail"' not in ledger_text


def test_http503_prep_persists_closed_receipt_diagnostics(
        tmp_path, monkeypatch, manifest, fake_factory):
    frozen = _frozen(manifest)

    def factory(manifest_value, out):
        backend = FakeBackend(manifest_value, out)
        backend.fail_chat_at = 1  # first preparation request
        backend.fail_chat_status = 503
        backend.fail_chat_error_code = "provider_transport_error"
        fake_factory["backend"] = backend
        return backend

    monkeypatch.setattr(runner, "backend_factory", factory)
    code, out = _run_execute(tmp_path, monkeypatch, frozen)
    backend = fake_factory["backend"]
    result = json.loads((out / "result.json").read_text(encoding="utf-8"))
    assert code == 1
    assert result["status"] == "partial"
    assert result["primary"]["planned_cells"] == 15
    assert result["primary"]["recorded_cells"] == 0
    assert result["primary"]["missing_cells"] == 15
    assert result["primary"]["stopped_early"] is True
    assert result["primary"]["stop_reason"] == "provider_unavailable"
    assert backend.chat_count == 1  # no retry and no dependent score
    assert result["lifecycle"]["status"] == "skipped"

    ledger = [json.loads(line) for line in
              (out / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
    prep_key = "H3_MAIN:M1:memory_disabled:0:prep"
    reserved = [row for row in ledger if row["event"] == "reserved"
                and row["request_key"] == prep_key]
    assert len(reserved) == 1
    closed = [row for row in ledger if row["event"] == "closed"
              and row["request_key"] == prep_key]
    assert len(closed) == 1
    assert closed[0]["error_code"] == "provider_transport_error"
    observation = [row for row in ledger
                   if row["event"] == "request_observation"
                   and row["request_key"] == prep_key]
    assert len(observation) == 1
    row = observation[0]
    assert row["stage"] == "primary_preparation"
    assert row["error_code"] == "provider_transport_error"
    assert row["provider_attempts"] == 1
    assert row["provider_ok"] is False
    assert len(row["provider_receipts"]) == 1
    receipt = row["provider_receipts"][0]
    assert receipt["attempts"] == 1
    assert receipt["error_code"] == "provider_transport_error"
    assert set(receipt) <= {"ok", "error_code", "retryable", "attempts",
                            "session_id", "observed_model", "model",
                            "provider", "assistant_message_id",
                            "identity_source", "observed_provider_id",
                            "observed_model_id"}
    skipped = [item for item in ledger
               if item["event"] == "planned_not_attempted"]
    assert len(skipped) == 29
    artifact_text = (out / "ledger.jsonl").read_text(encoding="utf-8")
    assert SENTINEL not in artifact_text
    assert '"detail"' not in artifact_text
    assert result["primary"]["stop_reason"] not in ("quota", "auth")


def test_unproven_primary_input_cannot_complete(
        tmp_path, monkeypatch, manifest, fake_factory):
    frozen = _frozen(manifest)

    def factory(manifest_value, out):
        backend = FakeBackend(manifest_value, out)
        backend.bad_input_for = "H3_HISTORY_M2"
        fake_factory["backend"] = backend
        return backend

    monkeypatch.setattr(runner, "backend_factory", factory)
    code, out = _run_execute(tmp_path, monkeypatch, frozen)
    result = json.loads((out / "result.json").read_text(encoding="utf-8"))
    assert code == 1
    assert result["status"] == "partial"
    assert result["primary"]["recorded_cells"] == 15
    assert result["primary"]["delivered_cells"] == 12
    assert result["primary"]["primary_errors"] == 3
    assert result["input_observability"]["verdicts"]["unknown"] == 3
    assert result["lifecycle"]["status"] == "completed"


@pytest.mark.parametrize("failed_code", ["cli_timeout",
                                         "invalid_tool_envelope"])
def test_prep_top_and_percall_codes_stay_independent(
        tmp_path, monkeypatch, manifest, fake_factory, failed_code):
    frozen = _frozen(manifest)

    def factory(manifest_value, out):
        backend = FakeBackend(manifest_value, out)
        backend.prep_top_error_code = "model_unavailable"
        backend.prep_failed_error_code = failed_code
        fake_factory["backend"] = backend
        return backend

    monkeypatch.setattr(runner, "backend_factory", factory)
    code, out = _run_execute(tmp_path, monkeypatch, frozen)
    backend = fake_factory["backend"]
    result = json.loads((out / "result.json").read_text(encoding="utf-8"))
    assert code == 1
    assert result["primary"]["planned_cells"] == 15
    assert result["primary"]["recorded_cells"] == 0
    assert result["primary"]["missing_cells"] == 15
    assert result["primary"]["stopped_early"] is True
    assert result["primary"]["stop_reason"] == "provider_fatal"
    assert result["calls"]["preparation_chats"] == 1
    assert result["calls"]["typed_scoring_requests"] == 0
    assert result["calls"]["known_cli_attempts"] == 3
    assert result["cleanup"] == {"attempted": True, "ok": True,
                                 "error_code": None}
    assert backend.chat_count == 1
    assert backend.starts == 1 and backend.stops == 1

    ledger = [json.loads(line) for line in
              (out / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
    prep_key = "H3_MAIN:M1:memory_disabled:0:prep"
    closed = [row for row in ledger if row["event"] == "closed"
              and row["request_key"] == prep_key]
    assert len(closed) == 1 and closed[0]["error_code"] == "model_unavailable"
    observations = [row for row in ledger
                    if row["event"] == "request_observation"
                    and row["request_key"] == prep_key]
    assert len(observations) == 1
    observation = observations[0]
    assert observation["error_code"] == "model_unavailable"
    assert observation["provider_attempts"] == 3
    assert observation["provider_ok"] is False
    receipts = observation["provider_receipts"]
    assert len(receipts) == 3
    assert [receipt["ok"] for receipt in receipts] == [True, True, False]
    assert all(receipt["attempts"] == 1 for receipt in receipts)
    assert receipts[0]["session_id"] == "ses_prep_ok_a"
    assert receipts[1]["session_id"] == "ses_prep_ok_b"
    failed = receipts[2]
    assert failed["error_code"] == failed_code
    assert "session_id" not in failed
    assert "observed_model" not in failed
    assert all(receipt["observed_model"] == runner.MODEL
               for receipt in receipts[:2])
    skipped = [row for row in ledger
               if row["event"] == "planned_not_attempted"]
    assert len(skipped) == 29
    ledger_text = (out / "ledger.jsonl").read_text(encoding="utf-8")
    assert SENTINEL not in ledger_text
    assert '"detail"' not in ledger_text and '"message"' not in ledger_text
    assert result["primary"]["stop_reason"] not in ("quota", "auth")


def test_typed_business_plan_invalid_keeps_denominator_and_continues(
        tmp_path, monkeypatch, manifest, fake_factory):
    frozen = _frozen(manifest)

    def factory(manifest_value, out):
        backend = FakeBackend(manifest_value, out)
        backend.typed_business_error_code = "plan_invalid"
        backend.typed_business_remaining = 1
        fake_factory["backend"] = backend
        return backend

    monkeypatch.setattr(runner, "backend_factory", factory)
    code, out = _run_execute(tmp_path, monkeypatch, frozen)
    backend = fake_factory["backend"]
    result = json.loads((out / "result.json").read_text(encoding="utf-8"))
    assert code == 1
    assert result["status"] == "partial"
    assert result["primary"]["stopped_early"] is False
    assert result["primary"]["planned_cells"] == 15
    assert result["primary"]["recorded_cells"] == 15
    assert result["primary"]["delivered_cells"] == 14
    assert result["primary"]["primary_errors"] == 1
    assert result["primary"]["missing_cells"] == 0
    assert result["calls"]["preparation_chats"] == 15
    assert result["calls"]["typed_scoring_requests"] == 15
    assert result["calls"]["lifecycle_chats"] == 3
    assert backend.chat_count == 33
    assert len(backend.typed_bodies) == 15  # no best-of and no retry

    observations = [json.loads(line) for line in
                    (out / "observations.jsonl").read_text(
                        encoding="utf-8").splitlines()]
    assert len(observations) == 15
    business = next(row for row in observations
                    if row["request_key"] ==
                    "H3_MAIN:M1:memory_disabled:0:score")
    assert business["status"] == "not_delivered"
    assert business["reason"] == "plan_invalid"
    assert business["projection"]["error"]["code"] == "plan_invalid"
    assert business["provider_receipts"][0]["ok"] is True
    assert "error_code" not in business["provider_receipts"][0]
    assert sum(1 for row in observations if row["status"] == "delivered") == 14

    ledger = [json.loads(line) for line in
              (out / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
    closed = [row for row in ledger if row["event"] == "closed"
              and row["request_key"] ==
              "H3_MAIN:M1:memory_disabled:0:score"]
    assert len(closed) == 1
    assert closed[0]["error_code"] == "plan_invalid"
    assert result["primary"]["stop_reason"] is None


def test_unknown_codes_clamp_without_raw_artifacts(
        tmp_path, monkeypatch, manifest, fake_factory):
    approved = json.loads((
        ROOT / "docs/project/handoffs/EXP-086/"
        "parent-approved-error-codes.json").read_text(encoding="utf-8"))
    approved_codes = approved["codes"]
    assert len(approved_codes) == 90
    assert runner._PARENT_APPROVED_CLOSED_ERROR_CODES == \
        frozenset(approved_codes)
    for known in approved_codes:
        assert runner._closed_error_code(known) == known
    assert runner._closed_error_code(123) is None
    assert runner._closed_error_code(None) is None
    assert runner._closed_error_code(["plan_invalid"]) is None

    raw_unknown = "credential_like_opaque_error_value"
    receipts = runner._provider_receipts({"provider": {"calls": [
        {"ok": False, "attempts": 1, "error_code": raw_unknown,
         "message": raw_unknown, "detail": raw_unknown},
        {"ok": False, "attempts": 1, "error_code": 123,
         "message": raw_unknown},
    ]}})
    assert len(receipts) == 2
    assert receipts[0]["error_code"] == "unknown"
    assert "error_code" not in receipts[1]
    assert "message" not in receipts[0] and "detail" not in receipts[0]
    assert "message" not in receipts[1]

    direct_ledger = runner.Ledger(tmp_path / "direct-ledger.jsonl", tmp_path)
    direct_ledger.close("direct", "stage", status="error", http_status=200,
                        elapsed_seconds=0.1, error_code=123)
    direct_row = json.loads((tmp_path / "direct-ledger.jsonl").read_text(
        encoding="utf-8").splitlines()[0])
    assert direct_row["error_code"] is None

    frozen = _frozen(manifest)
    prep_run = tmp_path / "prep"
    prep_run.mkdir()

    def prep_factory(manifest_value, out):
        backend = FakeBackend(manifest_value, out)
        backend.prep_top_error_code = raw_unknown
        backend.prep_failed_error_code = raw_unknown
        fake_factory["backend"] = backend
        return backend

    monkeypatch.setattr(runner, "backend_factory", prep_factory)
    prep_code, prep_out = _run_execute(prep_run, monkeypatch, frozen)
    assert prep_code == 1
    prep_ledger = [json.loads(line) for line in
                   (prep_out / "ledger.jsonl").read_text(
                       encoding="utf-8").splitlines()]
    prep_key = "H3_MAIN:M1:memory_disabled:0:prep"
    prep_closed = [row for row in prep_ledger if row["event"] == "closed"
                   and row["request_key"] == prep_key]
    prep_observation = [row for row in prep_ledger
                        if row["event"] == "request_observation"
                        and row["request_key"] == prep_key]
    assert len(prep_closed) == len(prep_observation) == 1
    assert prep_closed[0]["error_code"] == "unknown"
    assert prep_observation[0]["error_code"] == "unknown"
    assert prep_observation[0]["provider_receipts"][2]["error_code"] == \
        "unknown"

    typed_run = tmp_path / "typed"
    typed_run.mkdir()

    def typed_factory(manifest_value, out):
        backend = FakeBackend(manifest_value, out)
        backend.typed_business_error_code = raw_unknown
        backend.typed_business_remaining = 1
        fake_factory["backend"] = backend
        return backend

    monkeypatch.setattr(runner, "backend_factory", typed_factory)
    typed_code, typed_out = _run_execute(typed_run, monkeypatch, frozen)
    assert typed_code == 1
    typed_observations = [json.loads(line) for line in
                          (typed_out / "observations.jsonl").read_text(
                              encoding="utf-8").splitlines()]
    typed_business = next(row for row in typed_observations
                          if row["request_key"] ==
                          "H3_MAIN:M1:memory_disabled:0:score")
    assert typed_business["reason"] == "unknown"
    assert typed_business["projection"]["error"]["code"] == "unknown"
    typed_ledger = [json.loads(line) for line in
                    (typed_out / "ledger.jsonl").read_text(
                        encoding="utf-8").splitlines()]
    typed_closed = [row for row in typed_ledger if row["event"] == "closed"
                    and row["request_key"] ==
                    "H3_MAIN:M1:memory_disabled:0:score"]
    assert len(typed_closed) == 1
    assert typed_closed[0]["error_code"] == "unknown"

    for artifact in list(prep_out.rglob("*")) + list(typed_out.rglob("*")):
        if artifact.is_file():
            text = artifact.read_text(encoding="utf-8", errors="ignore")
            assert raw_unknown not in text


def test_source_binding_and_gate_rejections_are_enforced(
        tmp_path, monkeypatch, manifest):
    candidate = runner.build_candidate_manifest()
    baseline_rel = "docs/project/handoffs/EXP-086/"
    assert candidate["before_source_manifest"] == {
        "path": baseline_rel + "parent-before-source-manifest.json",
        "sha256": ("4c76c6733f3c4687dcf263032660df3dde39f50e7ab6d925"
                   "6cfe735e4e748a6d"),
    }
    assert candidate["frozen"] is False and candidate["thesis_mode"] is False
    assert candidate["review"]["decision"] == "pending_codex_review"

    baseline_path = ROOT / candidate["before_source_manifest"]["path"]
    assert runner._sha256_file(baseline_path) == \
        candidate["before_source_manifest"]["sha256"]
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    readonly = baseline["readonly_hashes"]
    assert len(readonly) == 46
    assert readonly["ai_service/main.py"] == (
        "d866c52f477b3c32f9ebfd1919e04d31f0a2d6e2b042465c80b1a914f8c10b0d")
    assert runner._sha256_file(ROOT / "ai_service/main.py") == \
        readonly["ai_service/main.py"]
    old_baseline = ROOT / "docs/project/handoffs/EXP-080/"
    old_path = old_baseline / "parent-before-source-manifest.json"
    assert runner._sha256_file(old_path) == (
        "fe40e5cc25aee28b998dbf53f48a174f819dae18257bea9563c87a8b3b778aa3")
    assert len(json.loads(old_path.read_text(
        encoding="utf-8"))["readonly_hashes"]) == 46

    assert candidate["code_binding"]["sha256"] == \
        runner._sha256_file(ROOT / candidate["code_binding"]["path"])
    assert candidate["code_binding"]["dependencies"] == {
        relative: runner._sha256_file(ROOT / relative)
        for relative in runner.CODE_DEPENDENCIES}
    frozen = _frozen(candidate)
    runner.validate_execution_manifest(frozen)

    calls = []

    def deny(*args, **kwargs):
        calls.append(True)
        raise AssertionError("gate must reject before backend resolution")

    monkeypatch.setattr(runner, "backend_factory", deny)
    mutations = {
        "runner_hash": lambda value: value["code_binding"].__setitem__(
            "sha256", "0" * 64),
        "main_dependency_hash": lambda value: value["code_binding"][
            "dependencies"].__setitem__("ai_service/main.py", "0" * 64),
        "other_dependency_hash": lambda value: value["code_binding"][
            "dependencies"].__setitem__("benchmarks/evaluation/h3.py",
                                        "0" * 64),
        "chat_cap": lambda value: value["limits"].__setitem__(
            "maximum_chat_requests", 34),
        "cli_cap": lambda value: value["limits"].__setitem__(
            "maximum_known_cli_attempts", 166),
        "condition": lambda value: value["conditions"].__setitem__(
            0, "other_condition"),
        "profile": lambda value: value["profiles"][0].__setitem__(
            "profile_id", "M9"),
        "source": lambda value: value["source_scope"].__setitem__(
            "input_sha256", "0" * 64),
        "alias": lambda value: value["runtime"].__setitem__(
            "model", "opencode-go/other-alias"),
        "mcp_port": lambda value: value["runtime"].__setitem__(
            "mcp_port", 1),
        "unfrozen": lambda value: value.__setitem__("frozen", False),
    }
    for name, mutate in mutations.items():
        broken = json.loads(json.dumps(frozen))
        mutate(broken)
        with pytest.raises(ValueError):
            runner.validate_execution_manifest(broken)
        manifest_path = tmp_path / f"{name}.json"
        _write_manifest(manifest_path, broken)
        code = runner.main(["--out", str(tmp_path / f"out-{name}"),
                            "--manifest", str(manifest_path), "--execute"])
        assert code == 2
    assert not calls


def test_three_gate_function_ast_bodies_are_pinned():
    tree = ast.parse((ROOT / "benchmarks/memory_live/runner.py").read_text(
        encoding="utf-8"))
    expected = {
        "_validate_shape":
            "3bed557ecbc5ee72af1e65eb79c9c1ad0db4d8702cea141e74470e1c9"
            "cbea5dd",
        "validate_execution_manifest":
            "c645a5dafda0b17dca4c18b81342de78a99a2706aab3ee0eeb71cdf2d"
            "ecb18c9",
        "_validate_readonly_sources":
            "1ae1c989ec7dec4248e9534b1bce9b2ec0ed13b43eeeb63aef5294d388"
            "e22ab2",
    }
    functions = {node.name: node for node in tree.body
                 if isinstance(node, ast.FunctionDef)}
    for name, digest in expected.items():
        dumped = ast.dump(functions[name], annotate_fields=True,
                          include_attributes=False)
        assert hashlib.sha256(dumped.encode()).hexdigest() == digest
