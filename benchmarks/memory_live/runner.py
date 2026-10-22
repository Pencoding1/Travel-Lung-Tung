"""EXP080 typed native H3 collector: dry-run by default, explicit ``--execute``.

The collector is intentionally narrow. It plans exactly the accepted five
synthetic profiles x three existing memory conditions x one repetition, uses
``/chat`` only for memory preparation, scores the typed
``/generate_itinerary`` endpoint, reuses the accepted MEM072 native helper
boundary and the accepted EXP074 response projection, and never parses prose
for selected POIs. Dry-run performs zero provider/HTTP/process calls and never
resolves credentials.

This file does not by itself accept or freeze the study. A frozen manifest,
independent source release and Codex QA are still required.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
from typing import Any, Dict, List, Mapping, Optional, Tuple
import urllib.error
import urllib.request

try:  # repository import (`benchmarks.memory_live.runner`)
    from benchmarks.evaluation.h3 import evaluate_h3, load_h3_records, parse_h3_manifest
    from benchmarks.live_model.service_projection import project_service_response
except ImportError:  # benchmark-local import
    from evaluation.h3 import evaluate_h3, load_h3_records, parse_h3_manifest
    from live_model.service_projection import project_service_response

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / "docs/experiments/primary_20261018/h3_candidate_manifest.json"
EXECUTION_DESIGN = ROOT / "docs/project/handoffs/EXP-080/parent-h3-typed-execution-design.json"
SOURCE_ANALYSIS = ROOT / "docs/project/handoffs/EXP-078/parent-source-universe-analysis.json"
BEFORE_SOURCE_MANIFEST = ROOT / "docs/project/handoffs/EXP-086/parent-before-source-manifest.json"
PROFILE_DESIGN = ROOT / "docs/project/handoffs/EXP-076/parent-h3-design.json"
HELPER_PATH = ROOT / "scripts/native_runtime/core_service.py"

TASK = "EXP080"
METHOD = "exp080.http.memory.typed.v2"
PREP_ENDPOINT = "/chat"
TYPED_ENDPOINT = "/generate_itinerary"
H3_SCHEMA_VERSION = "oc18.h3.v1"
SCENARIO_ID = "H3_MAIN"
CONDITIONS = ("memory_disabled", "short_term", "two_tier")
BASELINE = "memory_disabled"
REPETITIONS = 1
PROFILE_IDS = ("M1", "M2", "M3", "M4", "M5")

SOURCE = {
    "dataset_namespace": "hcm_primary_geojson",
    "input_sha256": "713b07a62cf89bd2cad9093abaad2a4c5f01e23853321764b3d66bf9f7eee43c",
    "source_area_id": (
        "source_area_v1:e9eb7238f81d8d56f2d5931f86e38d6b3b318147426191bd2c57d131e1500e1d"
    ),
}
PAYLOAD_SHA256 = "37340a8021ca7e8b37efc1053718c4c87879f95fa9937d8c53e1a0218f080dd1"
CATEGORY_TRUTH_SHA256 = "e586ca54c82922cac2ff16439ec0f2501eb3591433ac15573be040f44962584e"
DESIGN_SHA256 = "788e3cdded9e39a68da920667698edeca65faa4ddebc1a30308047199a08b361"
SOURCE_ANALYSIS_SHA256 = "212f8e52bcfed94ea644dc4d0e681a207ea52627c322707040cbd002253dd893"
BEFORE_SOURCE_MANIFEST_SHA256 = (
    "4c76c6733f3c4687dcf263032660df3dde39f50e7ab6d9256cfe735e4e748a6d"
)
PROFILE_DESIGN_SHA256 = "5ad0f52d2a3bd6f5dde587b420bd983d3e334c670547ed23590500604cc394c8"
ROUTE_FACTS = ROOT / "docs/project/handoffs/EXP-074/parent-case-route-facts.json"
ROUTE_FACTS_SHA256 = "4053ad9cc16364155c4e9bedc5f4a234fdbe7c6932a0bf4843c6eca513af29d7"
CODE_DEPENDENCIES = (
    "benchmarks/live_model/service_projection.py",
    "benchmarks/evaluation/h3.py",
    "scripts/native_runtime/core_service.py",
    "ai_service/domains/memory.py",
    "ai_service/main.py",
)
PROVIDER_SELECTED = "opencode_cli"

MODEL = "opencode-go/deepseek-v4.1-flash"
CLI_EXECUTABLE = "C:/Users/duyan/AppData/Roaming/npm/node_modules/@opencode/cli/bin/opencode.exe"
MCP_PORT = 19601
AI_PORT = 19602
FORBIDDEN_PORTS = frozenset({19101, 19102, 19501, 19502})
CLI_TIMEOUT_SECONDS = 30
HTTP_TIMEOUT_SECONDS = 210
MAX_CHAT_REQUESTS = 33
MAX_CLI_ATTEMPTS = 165
MAX_JEV_REQUESTS = 33

SHARED_SCORING_MESSAGE = (
    "Lập lịch một ngày 2026-11-01 từ 09:00 đến 16:00, gồm ba địa điểm trong "
    "phạm vi dữ liệu đã chọn, nhịp độ thong thả. Chỉ dùng POI có trong dữ liệu; "
    "giữ rõ thông tin giá hoặc giờ còn thiếu."
)
PREP_TEMPLATE = (
    "Tôi thích {category_label_vi} (mã nhóm {category_id}). "
    "Mã chuyến đi H3_HISTORY_{profile_id}. Hãy gợi ý một điểm phù hợp trong "
    "phạm vi dữ liệu đã chọn và ghi nhớ sở thích này."
)
TYPED_SHARED_BODY = {
    "current_city": "Ho Chi Minh City",
    "travel_type": "self-explore, relaxing",
    "num_travelers": 1,
    "start_date": "2026-11-01",
    "target_district": None,
    "duration_days": 1,
    "budget_range": "unknown",
    "user_description": SHARED_SCORING_MESSAGE,
    "transport_mode": "car",
    "source_scope": dict(SOURCE),
    "minimum_stops": 3,
    "maximum_stops": 3,
    "visit_minutes": 45,
    "day_windows": [{
        "date": "2026-11-01",
        "start": "2026-11-01T09:00:00+07:00",
        "end": "2026-11-01T16:00:00+07:00",
    }],
}
CATEGORY_LABELS_VI = {
    "hcm_primary_geojson:source-category:coffee": "cà phê",
    "hcm_primary_geojson:source-category:restaurant": "nhà hàng",
    "hcm_primary_geojson:source-category:specialty_food": "đặc sản",
    "hcm_primary_geojson:source-category:entertainment": "giải trí",
    "hcm_primary_geojson:source-category:apparel_and_gifts": "quần áo và quà tặng",
}
PROFILE_BLOCK_LIMIT = 800
PROFILE_FENCE_MARKERS = ("[Untrusted stored profile data",
                         "<untrusted_profile>",
                         "# STORED USER PROFILE")


class BoundedError(ValueError):
    """A fixed, sanitized refusal code safe to persist."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(Path(path).read_bytes())


def _canonical_hash(value: Any) -> str:
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return _sha256_bytes(text.encode("utf-8"))


def _profile_declarations() -> List[Dict[str, Any]]:
    design = _read_json(PROFILE_DESIGN)
    profiles = design.get("profiles")
    if not isinstance(profiles, list) or len(profiles) != 5:
        raise BoundedError("profile_design_invalid")
    result: List[Dict[str, Any]] = []
    for expected_id, raw in zip(PROFILE_IDS, profiles):
        if not isinstance(raw, dict) or raw.get("profile_id") != expected_id:
            raise BoundedError("profile_design_invalid")
        categories = raw.get("preferred_category_ids")
        initial = raw.get("initial_profile")
        if not isinstance(categories, list) or len(categories) != 1:
            raise BoundedError("profile_design_invalid")
        if not isinstance(initial, dict):
            raise BoundedError("profile_design_invalid")
        category_id = categories[0]
        if category_id not in CATEGORY_LABELS_VI:
            raise BoundedError("profile_category_label_missing")
        result.append({
            "profile_id": expected_id,
            "synthetic": True,
            "preferred_category_ids": list(categories),
            "category_label_vi": CATEGORY_LABELS_VI[category_id],
            "initial_profile": initial,
            "unknown_preferences": list(raw.get("unknown_preferences") or []),
        })
    return result


def _rotation(profile_index: int) -> List[str]:
    shift = profile_index % len(CONDITIONS)
    return list(CONDITIONS[shift:]) + list(CONDITIONS[:shift])


def _planned_cells(profiles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    cells: List[Dict[str, Any]] = []
    for profile_index, profile in enumerate(profiles):
        for condition in _rotation(profile_index):
            cells.append({
                "cell_id": f"{SCENARIO_ID}:{profile['profile_id']}:{condition}:0",
                "profile_id": profile["profile_id"],
                "condition": condition,
                "repetition": 0,
                "category_id": profile["preferred_category_ids"][0],
                "category_label_vi": profile["category_label_vi"],
                "history_marker": f"H3_HISTORY_{profile['profile_id']}",
                "preparation_then_score": True,
                "unique_authenticated_subject_and_session": True,
            })
    return cells


def _expected_templates() -> Dict[str, Any]:
    return {
        "preparation": PREP_TEMPLATE,
        "scoring": SHARED_SCORING_MESSAGE,
        "transport_mode": "car",
        "source_scope": dict(SOURCE),
        "endpoints": {"preparation": PREP_ENDPOINT,
                      "primary_score": TYPED_ENDPOINT,
                      "lifecycle": PREP_ENDPOINT},
        "typed_itinerary_body": dict(TYPED_SHARED_BODY),
        "typed_variable_fields": ["session_id", "memory_enabled"],
    }


def _expected_limits() -> Dict[str, Any]:
    return {
        "primary_cells": 15,
        "preparation_calls": 15,
        "primary_scoring_calls": 15,
        "typed_scoring_calls": 15,
        "maximum_lifecycle_chats": 3,
        "maximum_chat_requests": MAX_CHAT_REQUESTS,
        "maximum_model_generating_requests": MAX_CHAT_REQUESTS,
        "maximum_known_cli_attempts": MAX_CLI_ATTEMPTS,
        "maximum_jev_requests": MAX_JEV_REQUESTS,
        "cli_timeout_seconds": CLI_TIMEOUT_SECONDS,
        "http_timeout_seconds": HTTP_TIMEOUT_SECONDS,
        "retries": 0,
        "best_of": False,
    }


def _expected_runtime() -> Dict[str, Any]:
    return {
        "helper": "scripts/native_runtime/core_service.py",
        "mcp_port": MCP_PORT,
        "ai_port": AI_PORT,
        "model": MODEL,
        "temporary_sqlite_only": True,
        "temporary_hs256_issuer": "secret and bearer tokens RAM only",
        "engines": "existing loopback Memgraph/GraphHopper; readiness only, no restart/import",
    }


def _expected_lifecycle() -> Dict[str, Any]:
    return {
        "outside_primary_cells": True,
        "maximum_chats": 3,
        "profile": "M1",
        "condition": "two_tier",
        "steps": [
            "PUT expected_version=1 coffee->restaurant; one contradictory TRAVEL chat",
            "owned restart with same RAM issuer/SQLite; one new generic chat",
            "DELETE profile and clear own short history; one new generic chat",
        ],
        "not_success_share": "unknown preference is boundary correctness, not preferred-share=0",
    }


def _route_binding() -> Dict[str, Any]:
    facts = _read_json(ROUTE_FACTS)
    engine = facts.get("engine")
    if not isinstance(engine, dict):
        raise BoundedError("route_facts_engine_missing")
    keys = ("name", "jar_sha256", "pbf_sha256")
    return {
        "path": "docs/project/handoffs/EXP-074/parent-case-route-facts.json",
        "sha256": ROUTE_FACTS_SHA256,
        "engine": {key: engine.get(key) for key in keys},
        "planning_adapter_sha256": facts.get("planning_adapter_sha256"),
        "quantization": facts.get("quantization"),
    }


def _expected_scenario() -> Dict[str, Any]:
    return {
        "scenario_id": SCENARIO_ID,
        "transport_mode": "car",
        "source_scope": dict(SOURCE),
        "shared_scoring_message": SHARED_SCORING_MESSAGE,
        "requested_day": "2026-11-01",
        "window": "09:00-16:00",
        "requested_stops": 3,
        "pace": "relaxed",
        "typed_endpoint": TYPED_ENDPOINT,
        "preparation_endpoint": PREP_ENDPOINT,
        "typed_request": dict(TYPED_SHARED_BODY),
    }


def build_candidate_manifest() -> Dict[str, Any]:
    """Build the unfrozen candidate manifest. Performs no network/process work."""
    analysis = _read_json(SOURCE_ANALYSIS)
    if analysis.get("source_scope") != SOURCE:
        raise BoundedError("source_analysis_source_mismatch")
    if analysis.get("payload_sha256") != PAYLOAD_SHA256:
        raise BoundedError("source_analysis_payload_mismatch")
    category_truth = analysis.get("category_truth")
    if not isinstance(category_truth, dict) or len(category_truth) != 1483:
        raise BoundedError("source_analysis_category_truth_invalid")
    if _canonical_hash(category_truth) != CATEGORY_TRUTH_SHA256:
        raise BoundedError("source_analysis_category_truth_mismatch")

    profiles = _profile_declarations()
    cells = _planned_cells(profiles)
    active_truth = {
        profile["profile_id"]: {SCENARIO_ID: list(profile["preferred_category_ids"])}
        for profile in profiles
    }
    code_path = Path(__file__).resolve()
    manifest: Dict[str, Any] = {
        "manifest_version": "exp080.h3.typed.candidate.v2",
        "task": "H3",
        "label": (
            "EXP080 UNFROZEN synthetic typed native-HTTP H3 candidate manifest; "
            "not H1, not a result, not frozen"
        ),
        "thesis_mode": False,
        "frozen": False,
        "conditions": list(CONDITIONS),
        "baseline_condition": BASELINE,
        "repetitions_per_case": REPETITIONS,
        "profiles": profiles,
        "scenarios": [_expected_scenario()],
        "category_truth": category_truth,
        "active_preference_truth": active_truth,
        "dataset_kind": "real_supplied_primary_snapshot",
        "dataset_id": "primary:hcm_primary_geojson:exp080-h3-universe-1483",
        "payload_sha256": PAYLOAD_SHA256,
        "source_scope": dict(SOURCE),
        "category_truth_sha256": CATEGORY_TRUTH_SHA256,
        "templates": _expected_templates(),
        "request_paths": {"preparation": PREP_ENDPOINT,
                          "primary_score": TYPED_ENDPOINT,
                          "lifecycle": PREP_ENDPOINT},
        "typed_request_body_without_session_and_memory": dict(TYPED_SHARED_BODY),
        "primary_cells": cells,
        "lifecycle": _expected_lifecycle(),
        "limits": _expected_limits(),
        "runtime": _expected_runtime(),
        "route_facts": _route_binding(),
        "design": {
            "author": "Codex",
            "path": EXECUTION_DESIGN.relative_to(ROOT).as_posix(),
            "sha256": DESIGN_SHA256,
        },
        "source_analysis": {
            "path": SOURCE_ANALYSIS.relative_to(ROOT).as_posix(),
            "sha256": SOURCE_ANALYSIS_SHA256,
        },
        "profile_design": {
            "path": PROFILE_DESIGN.relative_to(ROOT).as_posix(),
            "sha256": PROFILE_DESIGN_SHA256,
        },
        "before_source_manifest": {
            "path": BEFORE_SOURCE_MANIFEST.relative_to(ROOT).as_posix(),
            "sha256": BEFORE_SOURCE_MANIFEST_SHA256,
        },
        "code_binding": {
            "path": "benchmarks/memory_live/runner.py",
            "sha256": _sha256_file(code_path),
            "dependencies": {
                relative: _sha256_file(ROOT / relative)
                for relative in CODE_DEPENDENCIES
            },
        },
        "review": {
            "decision": "pending_codex_review",
            "frozen": False,
            "note": "Executor candidate only; no reviewer or freeze is claimed.",
        },
        "limitations": [
            "Synthetic five-profile fixture; not humans and not H1.",
            "Retrieved/model-exposed POI subsets may vary as a mediator of memory configuration.",
            "No storage-only or identical-exposure causal claim.",
            "No p-values from five synthetic profiles and no total-cost or token-saving claim.",
            "Lifecycle correctness is separate from the fifteen primary preference cells.",
        ],
    }
    return manifest


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise ValueError(code)


def _validate_shape(manifest: Any) -> None:
    _require(isinstance(manifest, dict), "manifest_not_object")
    _require(manifest.get("task") == "H3", "manifest_task_invalid")
    _require(manifest.get("thesis_mode") is False, "manifest_thesis_mode_invalid")
    _require(tuple(manifest.get("conditions") or ()) == CONDITIONS,
             "manifest_conditions_invalid")
    _require(manifest.get("baseline_condition") == BASELINE,
             "manifest_baseline_invalid")
    _require(manifest.get("repetitions_per_case") == REPETITIONS,
             "manifest_repetitions_invalid")
    profiles = manifest.get("profiles")
    _require(isinstance(profiles, list) and
             [p.get("profile_id") for p in profiles if isinstance(p, dict)] ==
             list(PROFILE_IDS), "manifest_profiles_invalid")
    scenarios = manifest.get("scenarios")
    _require(isinstance(scenarios, list) and len(scenarios) == 1 and
             isinstance(scenarios[0], dict) and
             scenarios[0].get("scenario_id") == SCENARIO_ID,
             "manifest_scenarios_invalid")
    _require(manifest.get("source_scope") == SOURCE, "manifest_source_invalid")
    _require(scenarios[0] == _expected_scenario(), "manifest_scenario_semantics_invalid")
    _require(manifest.get("payload_sha256") == PAYLOAD_SHA256,
             "manifest_payload_invalid")
    truth = manifest.get("category_truth")
    _require(isinstance(truth, dict) and len(truth) == 1483,
             "manifest_category_truth_invalid")
    _require(_canonical_hash(truth) == CATEGORY_TRUTH_SHA256,
             "manifest_category_truth_mismatch")
    _require(manifest.get("category_truth_sha256") == CATEGORY_TRUTH_SHA256,
             "manifest_category_truth_hash_missing")
    active = manifest.get("active_preference_truth")
    _require(isinstance(active, dict) and set(active) == set(PROFILE_IDS),
             "manifest_active_preference_invalid")
    for profile in profiles:
        pid = profile["profile_id"]
        _require(profile.get("synthetic") is True, "manifest_profile_not_synthetic")
        per = active.get(pid)
        _require(isinstance(per, dict) and
                 per.get(SCENARIO_ID) == profile.get("preferred_category_ids"),
                 "manifest_active_preference_mismatch")
    cells = manifest.get("primary_cells")
    _require(isinstance(cells, list) and len(cells) == 15,
             "manifest_primary_cells_invalid")
    expected_cells = _planned_cells(profiles)
    _require([c.get("cell_id") for c in cells if isinstance(c, dict)] ==
             [c["cell_id"] for c in expected_cells], "manifest_primary_cells_order_invalid")
    _require(manifest.get("limits", {}).get("maximum_chat_requests") ==
             MAX_CHAT_REQUESTS, "manifest_request_cap_invalid")


def _validate_readonly_sources() -> None:
    _require(_sha256_file(BEFORE_SOURCE_MANIFEST) == BEFORE_SOURCE_MANIFEST_SHA256,
             "before_source_manifest_mismatch")
    baseline = _read_json(BEFORE_SOURCE_MANIFEST).get("readonly_hashes")
    _require(isinstance(baseline, dict) and baseline, "before_source_manifest_invalid")
    for relative, expected in baseline.items():
        path = ROOT / relative
        _require(path.is_file(), "readonly_source_missing")
        _require(_sha256_file(path) == expected, "readonly_source_hash_mismatch")


def validate_execution_manifest(manifest: Mapping[str, Any]) -> None:
    """Raise a bounded ``ValueError`` unless the execution manifest is frozen.

    The function is read-only (it never mutates the manifest) and is called
    before backend/provider/process resolution.
    """
    _validate_shape(manifest)
    _require(manifest.get("frozen") is True, "manifest_not_frozen")
    _require(manifest.get("profiles") == _profile_declarations(),
             "manifest_profile_semantics_invalid")
    _require(manifest.get("templates") == _expected_templates(),
             "manifest_template_semantics_invalid")
    _require(manifest.get("limits") == _expected_limits(),
             "manifest_limits_semantics_invalid")
    _require(manifest.get("runtime") == _expected_runtime(),
             "manifest_runtime_semantics_invalid")
    _require(manifest.get("lifecycle") == _expected_lifecycle(),
             "manifest_lifecycle_semantics_invalid")
    _require(manifest.get("route_facts") == _route_binding(),
             "manifest_route_facts_invalid")
    _require(manifest.get("primary_cells") ==
             _planned_cells(_profile_declarations()),
             "manifest_cell_semantics_invalid")
    _require(_sha256_file(SOURCE_ANALYSIS) == SOURCE_ANALYSIS_SHA256,
             "source_analysis_hash_mismatch")
    _require(_read_json(SOURCE_ANALYSIS).get("category_truth") ==
             manifest.get("category_truth"), "category_truth_source_mismatch")
    _require(_sha256_file(EXECUTION_DESIGN) == DESIGN_SHA256,
             "execution_design_hash_mismatch")
    _require(_sha256_file(PROFILE_DESIGN) == PROFILE_DESIGN_SHA256,
             "profile_design_hash_mismatch")
    _require(_sha256_file(ROUTE_FACTS) == ROUTE_FACTS_SHA256,
             "route_facts_hash_mismatch")
    _validate_readonly_sources()
    code = manifest.get("code_binding")
    _require(isinstance(code, dict) and
             code.get("path") == "benchmarks/memory_live/runner.py",
             "code_binding_missing")
    _require(_sha256_file(ROOT / code["path"]) == code.get("sha256"),
             "code_binding_mismatch")
    _require(code.get("dependencies") == {
        relative: _sha256_file(ROOT / relative)
        for relative in CODE_DEPENDENCIES}, "code_dependency_binding_mismatch")


def _ensure_out_dir(out: Path) -> None:
    if out.exists():
        if not out.is_dir():
            raise BoundedError("out_not_directory")
        if any(out.iterdir()):
            raise BoundedError("evidence_exists")
    else:
        out.mkdir(parents=True, exist_ok=False)


def _append_jsonl(path: Path, row: Mapping[str, Any], backend: Any = None) -> None:
    if backend is not None and hasattr(backend, "assert_clean"):
        backend.assert_clean(row)
    text = json.dumps(dict(row), ensure_ascii=False, sort_keys=True)
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(text + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _write_json(path: Path, value: Mapping[str, Any], backend: Any = None) -> None:
    if backend is not None and hasattr(backend, "assert_clean"):
        backend.assert_clean(value)
    path.write_text(json.dumps(dict(value), ensure_ascii=False, indent=2,
                               sort_keys=True) + "\n", encoding="utf-8")


class Ledger:
    """Append-only request ledger; reserve before a call, close after it."""

    def __init__(self, path: Path, out: Path):
        self.path = path
        self.out = out

    def observe(self, request_key: str, stage: str, *,
                provider_receipts: Any, error_code: Any = None) -> None:
        """Sanitized provider receipts for a failed prep/lifecycle request.

        Only the ``_provider_receipts`` whitelist and a fixed error enum are
        persisted; raw payload bodies, messages, headers and exceptions never
        reach this row.
        """
        receipts = _provider_receipts(
            {"provider": {"calls": list(provider_receipts or ())}})
        attempts = 0
        for receipt in receipts:
            value = receipt.get("attempts")
            if isinstance(value, int) and not isinstance(value, bool):
                attempts += value
        _append_jsonl(self.path, {
            "event": "request_observation",
            "request_key": request_key,
            "stage": stage,
            "error_code": _closed_error_code(error_code),
            "provider_receipts": receipts,
            "provider_attempts": attempts,
            "provider_ok": bool(receipts) and all(
                receipt.get("ok") is True for receipt in receipts),
            "at_unix": time.time(),
        })

    def reserve(self, request_key: str, stage: str, method: str, path: str) -> None:
        _append_jsonl(self.path, {
            "event": "reserved",
            "request_key": request_key,
            "stage": stage,
            "method": method,
            "path": path,
            "at_unix": time.time(),
        })

    def close(self, request_key: str, stage: str, *, status: Any,
              http_status: Any, elapsed_seconds: Any,
              error_code: Optional[str] = None, outcome: Any = None) -> None:
        closed_outcome = None
        if isinstance(outcome, Mapping):
            closed_outcome = {}
            for key, value in outcome.items():
                scalar = _scalar(value)
                if isinstance(key, str) and scalar is not None:
                    closed_outcome[key] = scalar
        _append_jsonl(self.path, {
            "event": "closed",
            "request_key": request_key,
            "stage": stage,
            "status": _scalar(status),
            "http_status": _scalar(http_status),
            "elapsed_seconds": _scalar(elapsed_seconds),
            "error_code": _closed_error_code(error_code),
            "outcome": closed_outcome,
            "at_unix": time.time(),
        })

    def planned_not_attempted(self, request_key: str, stage: str, reason: str) -> None:
        _append_jsonl(self.path, {
            "event": "planned_not_attempted",
            "request_key": request_key,
            "stage": stage,
            "reason": reason,
            "at_unix": time.time(),
        })


def _scalar(value: Any) -> Any:
    """Keep only closed JSON scalar values; nested carriers are dropped."""
    if isinstance(value, bool) or isinstance(value, int) or isinstance(value, float):
        return value
    if isinstance(value, str):
        return value
    return None


def _provider_receipts(payload: Any) -> List[Dict[str, Any]]:
    if not isinstance(payload, Mapping):
        return []
    provider = payload.get("provider")
    if not isinstance(provider, Mapping):
        return []
    calls = provider.get("calls")
    if not isinstance(calls, list):
        return []
    keys = ("ok", "error_code", "retryable", "attempts", "session_id",
            "observed_model", "model", "provider", "assistant_message_id",
            "identity_source", "observed_provider_id", "observed_model_id")
    receipts: List[Dict[str, Any]] = []
    for call in calls:
        if not isinstance(call, Mapping):
            continue
        receipt: Dict[str, Any] = {}
        for key in keys:
            if key not in call:
                continue
            if key == "error_code":
                value = _closed_error_code(call.get(key))
            else:
                value = _scalar(call.get(key))
            if value is not None:
                receipt[key] = value
        receipts.append(receipt)
    return receipts


_FATAL_PROVIDER_CODES = frozenset({
    "quota", "quota_exceeded", "rate_limit", "rate_limited",
    "auth", "authentication_failed", "unauthorized", "forbidden",
    "transport", "transport_error", "timeout",
    "provider_failed", "provider_unavailable",
})

_PARENT_APPROVED_CLOSED_ERROR_CODES = frozenset({
    "ambiguous_assistant_identity",
    "budget_invalid",
    "candidate_retrieval_failed",
    "category_discovery_failed",
    "cli_agent_preflight_failed",
    "cli_agent_unavailable",
    "cli_ambient_config_refused",
    "cli_cancelled",
    "cli_command_line_too_long",
    "cli_error_event",
    "cli_launch_failed",
    "cli_malformed_stream",
    "cli_nonzero_exit",
    "cli_not_found",
    "cli_output_overflow",
    "cli_pure_unsupported",
    "cli_runtime_unsupported",
    "cli_server_preflight_failed",
    "cli_timeout",
    "cli_tool_use_denied",
    "cli_unsafe_executable",
    "duplicate_stops",
    "empty_response",
    "enrichment_failed",
    "enrichment_id_mismatch",
    "evidence_write_failed",
    "export_missing_info",
    "export_missing_messages",
    "export_mixed_shapes",
    "export_not_json",
    "export_not_object",
    "export_not_utf8",
    "insufficient_data",
    "invalid_configuration",
    "invalid_model_response",
    "invalid_prompt",
    "invalid_provider_config",
    "invalid_sampling_control",
    "invalid_session_id",
    "invalid_tool_arguments",
    "invalid_tool_call_id",
    "invalid_tool_envelope",
    "invalid_tool_schema",
    "invalid_usage",
    "llm_error",
    "location_ambiguous",
    "location_not_resolved",
    "location_type_mismatch",
    "loop_limit",
    "model_config_mismatch",
    "model_mismatch",
    "model_unavailable",
    "plan_invalid",
    "prompt_too_large",
    "provider_busy",
    "provider_mismatch",
    "scope_conflict",
    "scope_unverified",
    "session_export_failed",
    "session_export_malformed",
    "source_scope_unverified",
    "start_end_mismatch",
    "time_order_invalid",
    "tool_protocol_error",
    "transport_agent_allow_rule",
    "transport_agent_deny_coverage",
    "transport_agent_malformed",
    "transport_agent_missing",
    "transport_agent_model_mismatch",
    "transport_agent_not_primary",
    "transport_agent_not_unique",
    "transport_agent_permissions_missing",
    "transport_agent_steps_mismatch",
    "transport_agent_system_mismatch",
    "transport_agent_wildcard_missing",
    "transport_config_not_object",
    "transport_config_unreadable",
    "transport_control_binding_mismatch",
    "transport_default_agent_mismatch",
    "transport_go_binding_mismatch",
    "transport_model_mismatch",
    "transport_root_policy_mismatch",
    "transport_share_not_disabled",
    "transport_unexpected_provider_overlay",
    "unfinished_response",
    "unknown_poi",
    "unknown_session_provenance",
    "unknown_tool",
    "unsupported_model_control",
    "unsupported_tool_schema",
})

_CLOSED_ERROR_CODES = (
    _FATAL_PROVIDER_CODES
    | _PARENT_APPROVED_CLOSED_ERROR_CODES
    | frozenset({
        "provider_transport_error", "invalid_request",
        "grounding_insufficient", "missing_response", "invalid_response",
        "no_plan", "unknown",
    })
)


def _closed_error_code(value: Any) -> Optional[str]:
    """Persist only a fixed enum; unknown text stays unknown."""
    if not isinstance(value, str):
        return None
    if value in _CLOSED_ERROR_CODES:
        return value
    return "unknown"


def _payload_error_code(payload: Any) -> Optional[str]:
    if not isinstance(payload, Mapping):
        return None
    error = payload.get("error")
    if isinstance(error, Mapping):
        return _closed_error_code(error.get("code"))
    return _closed_error_code(payload.get("error_code"))


def _receipt_identity_error(receipt: Any) -> Optional[str]:
    """Fixed code unless one contributing provider receipt has exact identity."""
    if not isinstance(receipt, Mapping):
        return "provider_receipt_not_object"
    if receipt.get("ok") is not True:
        return "provider_failure"
    attempts = receipt.get("attempts")
    if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts != 1:
        return "retry_detected"
    session_id = receipt.get("session_id")
    if not isinstance(session_id, str) or not session_id.startswith("ses_"):
        return "unproven_session"
    if receipt.get("observed_model") != MODEL:
        return "wrong_model"
    return None


def _receipts_identity_error(receipts: Any) -> Optional[str]:
    """Validate every contributing call; no any-good-session shortcut."""
    if not isinstance(receipts, (list, tuple)) or not receipts:
        return "provider_receipt_missing"
    for receipt in receipts:
        error = _receipt_identity_error(receipt)
        if error is not None:
            return error
    return None


def _usage_components(payload: Any) -> Any:
    if not isinstance(payload, Mapping):
        return None
    usage = payload.get("usage")
    if not isinstance(usage, Mapping):
        return None
    result: Dict[str, Any] = {}
    for key in ("model_calls", "input_tokens", "output_tokens", "total_tokens",
                "usage_basis"):
        if key in usage:
            value = _scalar(usage.get(key))
            if value is not None:
                result[key] = value
    stages = usage.get("stages")
    if isinstance(stages, Mapping):
        for stage in ("summary", "extraction", "retrieval", "final", "retries"):
            value = _scalar(stages.get(stage))
            if isinstance(value, int) and not isinstance(value, bool):
                result[f"stage_{stage}"] = value
    return result or None


_CLOSED_FLAG_KEYS = ("status", "session_export", "history_marker",
                     "profile_prompt", "profile_prompt_expected",
                     "fixture_credentials_absent", "reason")


def _closed_input_flags(flags: Any) -> Dict[str, Any]:
    if not isinstance(flags, Mapping):
        return {"status": "unknown", "reason": "input_flags_missing"}
    result: Dict[str, Any] = {}
    for key in _CLOSED_FLAG_KEYS:
        if key in flags:
            value = _scalar(flags.get(key))
            if value is not None:
                result[key] = value
    if result.get("status") not in ("proven", "unknown", "mismatch"):
        result["status"] = "unknown"
        result.setdefault("reason", "input_flags_malformed")
    return result


def _selected_ids_from_projection(projection: Mapping[str, Any]
                                  ) -> Tuple[List[str], Optional[str]]:
    planning = projection.get("planning")
    if not isinstance(planning, Mapping):
        return [], "missing_plan"
    repaired = planning.get("repaired_schedule")
    if not isinstance(repaired, Mapping):
        return [], "missing_plan"
    days = repaired.get("days")
    if not isinstance(days, list) or not days:
        return [], "missing_plan_days"
    selected: List[str] = []
    for day in days:
        if not isinstance(day, Mapping):
            return [], "malformed_day"
        stops = day.get("stops")
        if not isinstance(stops, list):
            return [], "malformed_stops"
        for stop in stops:
            if not isinstance(stop, Mapping):
                return [], "malformed_stop"
            poi_id = stop.get("poi_id")
            if not isinstance(poi_id, str) or not poi_id.strip():
                return [], "malformed_stop_id"
            selected.append(poi_id)
    return selected, None


def _validation_status(planning: Mapping[str, Any]) -> str:
    status = planning.get("validator_status")
    if isinstance(status, str) and status in (
            "feasible", "partial", "unverifiable", "no_plan", "failed"):
        return status
    validation = planning.get("validation")
    if isinstance(validation, Mapping):
        status = validation.get("status")
        if isinstance(status, str) and status in (
                "feasible", "partial", "unverifiable", "no_plan", "failed"):
            return status
    return "unknown"


def _constraint_valid(planning: Mapping[str, Any]) -> Optional[bool]:
    validation = planning.get("validation")
    validation = validation if isinstance(validation, Mapping) else {}
    violations = validation.get("known_violations")
    unsatisfied = validation.get("unsatisfied_required")
    if (violations or unsatisfied or validation.get("status") == "failed"
            or planning.get("validator_status") == "failed"):
        return False
    if (planning.get("validator_status") == "feasible"
            and validation.get("status") == "feasible"):
        return True
    if planning.get("verified") is True:
        return True
    return None


def _provenance(manifest: Mapping[str, Any]) -> Dict[str, str]:
    truth_hash = manifest["category_truth_sha256"]
    base = {
        "message": SHARED_SCORING_MESSAGE,
        "source_scope": dict(SOURCE),
        "transport_mode": "car",
        "day": "2026-11-01",
        "window": "09:00-16:00",
        "stops": 3,
        "pace": "relaxed",
    }
    limits = manifest.get("limits") or {}
    route = manifest.get("route_facts") or {}
    return {
        "candidate_id": _canonical_hash({
            "universe": SOURCE, "category_truth_sha256": truth_hash}),
        "route_id": _canonical_hash({
            "source": SOURCE, "model": MODEL, "mode": "typed_native_http_h3",
            "transport_mode": "car",
            "endpoint": TYPED_ENDPOINT,
            "roadmap": "planning_adapter.render_plan+independent_validator",
            "engine": route.get("engine"),
            "planning_adapter_sha256": route.get("planning_adapter_sha256"),
        }),
        "prompt_information_id": _canonical_hash({
            **base, "typed_request": TYPED_SHARED_BODY}),
        "dataset_id": manifest["dataset_id"],
        "model_id": MODEL,
        "settings_id": _canonical_hash({
            "model": MODEL,
            "preparation_endpoint": PREP_ENDPOINT,
            "primary_score_endpoint": TYPED_ENDPOINT,
            "cli_timeout_seconds": limits.get("cli_timeout_seconds"),
            "http_timeout_seconds": limits.get("http_timeout_seconds"),
            "retries": 0,
        }),
        "method_instruction_hash": _canonical_hash({
            "preparation": PREP_TEMPLATE,
            "scoring": SHARED_SCORING_MESSAGE,
            "typed_request": TYPED_SHARED_BODY,
            "endpoints": {"preparation": PREP_ENDPOINT,
                          "primary_score": TYPED_ENDPOINT},
        }),
    }


def _expected_flags(condition: str) -> Dict[str, bool]:
    return {
        "history_marker": condition in ("short_term", "two_tier"),
        "profile_prompt": condition == "two_tier",
    }


def _flags_verdict(flags: Any, condition: str) -> str:
    if not isinstance(flags, Mapping) or flags.get("status") != "proven":
        return "unknown"
    if (flags.get("session_export") is not True
            or flags.get("fixture_credentials_absent") is not True):
        return "unknown"
    expected = _expected_flags(condition)
    observed: Dict[str, bool] = {}
    for key in expected:
        value = flags.get(key)
        if value is not True and value is not False:
            return "unknown"
        observed[key] = value
    if observed == expected:
        return "proven"
    return "mismatch"


def _chat_payload(session_id: str, message: str, condition: str) -> Dict[str, Any]:
    return {
        "session_id": session_id,
        "message": message,
        "memory_enabled": condition != "memory_disabled",
        "transport_mode": "car",
        "source_scope": dict(SOURCE),
    }


def _itinerary_payload(session_id: str, condition: str) -> Dict[str, Any]:
    """Exact typed request body from the Codex EXP080 execution design.

    Every condition shares all non-session/non-memory fields. Only
    ``session_id`` and ``memory_enabled`` vary with the cell.
    """
    body = json.loads(json.dumps(TYPED_SHARED_BODY))
    body["session_id"] = session_id
    body["memory_enabled"] = condition != "memory_disabled"
    return body


def _typed_source_error(payload: Any) -> Optional[str]:
    """Typed source requires both nested scopes; top-level is insufficient."""
    if not isinstance(payload, Mapping):
        return "typed_source_mismatch"
    grounding = payload.get("grounding")
    planning = payload.get("planning")
    if not isinstance(grounding, Mapping) or not isinstance(planning, Mapping):
        return "typed_source_mismatch"
    constraints = planning.get("request_constraints")
    if not isinstance(constraints, Mapping):
        return "typed_source_mismatch"
    if (grounding.get("source_scope") != SOURCE
            or constraints.get("source_scope") != SOURCE):
        return "typed_source_mismatch"
    return None


def _selected_stops_from_projection(projection: Mapping[str, Any]
                                    ) -> List[Dict[str, Any]]:
    """Whitelisted stop ids/timestamps, only from the repaired schedule."""
    planning = projection.get("planning")
    if not isinstance(planning, Mapping):
        return []
    repaired = planning.get("repaired_schedule")
    if not isinstance(repaired, Mapping):
        return []
    stops_out: List[Dict[str, Any]] = []
    for day in repaired.get("days") or []:
        if not isinstance(day, Mapping):
            continue
        for stop in day.get("stops") or []:
            if not isinstance(stop, Mapping):
                continue
            stops_out.append({
                "poi_id": stop.get("poi_id"),
                "arrival": stop.get("arrival"),
                "departure": stop.get("departure"),
            })
    return stops_out


def _record_from_response(*, manifest: Mapping[str, Any], cell: Mapping[str, Any],
                          payload: Any, http_status: Any, elapsed_seconds: Any,
                          provider_receipts: List[Dict[str, Any]],
                          input_flags: Any, input_verdict: str,
                          failure_code: Optional[str] = None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    profile_id = cell["profile_id"]
    condition = cell["condition"]
    repetition = cell["repetition"]
    projection = project_service_response(payload, http_status=http_status,
                                          elapsed_seconds=elapsed_seconds)
    projection_error_code: Optional[str] = None
    if isinstance(projection, Mapping):
        projected_error = projection.get("error")
        projection_error_code = (
            _closed_error_code(projected_error.get("code"))
            if isinstance(projected_error, Mapping) else None)
        if isinstance(projected_error, Mapping):
            closed_projection = dict(projection)
            closed_projection["error"] = (
                {"code": projection_error_code}
                if projection_error_code is not None else None)
            projection = closed_projection
    selected: List[str] = []
    reason = failure_code
    plan_present = False
    empty_plan = False
    run_status = "error"
    validation_status = "unknown"
    constraint_valid: Optional[bool] = None
    unknown_ids: List[str] = []

    ok = (
        failure_code is None
        and http_status == 200
        and projection.get("response_status") == "success"
        and projection.get("model") == MODEL
        and isinstance(payload, Mapping)
    )
    if ok:
        source_error = _typed_source_error(payload)
        if source_error is not None:
            ok = False
            reason = source_error
    if ok:
        provider = payload.get("provider") or {}
        model = provider.get("observed_model") if isinstance(provider, Mapping) else None
        if model != MODEL:
            ok = False
            reason = "wrong_model"
        else:
            receipt_error = _receipts_identity_error(provider_receipts)
            if receipt_error is not None:
                ok = False
                reason = receipt_error

    if ok and input_verdict != "proven":
        ok = False
        reason = ("input_proof_mismatch" if input_verdict == "mismatch"
                  else "input_proof_unknown")

    if ok:
        planning = projection.get("planning")
        if not isinstance(planning, Mapping):
            ok = False
            reason = "missing_plan"
        else:
            repaired = planning.get("repaired_schedule")
            plan_present = isinstance(repaired, Mapping)
            selected, selected_error = _selected_ids_from_projection(projection)
            if selected_error is not None:
                ok = False
                reason = selected_error
            else:
                unknown_ids = [poi_id for poi_id in selected
                               if poi_id not in manifest["category_truth"]]
                if unknown_ids:
                    ok = False
                    reason = "out_of_universe_selected_id"
                else:
                    run_status = "completed"
                    empty_plan = not selected
                    validation_status = _validation_status(planning)
                    if (isinstance(repaired, Mapping)
                            and repaired.get("scheduler_status") == "no_plan"):
                        validation_status = "no_plan"
                    constraint_valid = _constraint_valid(planning)

    if not ok:
        if reason is None and projection_error_code is not None:
            reason = projection_error_code
        selected = []
        plan_present = False
        empty_plan = False
        run_status = "error"
        validation_status = "unknown"
        constraint_valid = None

    record = {
        "schema_version": H3_SCHEMA_VERSION,
        "task": "H3",
        "evidence_level": "live_model",
        "dataset_kind": manifest["dataset_kind"],
        "profile_id": profile_id,
        "scenario_id": SCENARIO_ID,
        "condition": condition,
        "repetition": repetition,
        "run_status": run_status,
        "plan_present": plan_present,
        "empty_plan": empty_plan,
        "validation_status": validation_status,
        "unverifiable": validation_status == "unverifiable",
        "constraint_valid": constraint_valid,
        "selected_poi_ids": selected,
        # Full end-to-end provider coverage is not proven, so the evaluator
        # usage field stays unknown instead of being zero-filled.
        "usage": None,
        "latency_seconds": elapsed_seconds if isinstance(elapsed_seconds, (int, float)) else None,
        "failure_retries": 0,
        "provenance": _provenance(manifest),
    }
    observation = {
        "cell_id": cell["cell_id"],
        "request_key": f"{cell['cell_id']}:score",
        "stage": "primary_score",
        "profile_id": profile_id,
        "condition": condition,
        "repetition": repetition,
        "status": ("delivered" if ok and not empty_plan
                   else ("empty_plan" if ok else "not_delivered")),
        "reason": reason,
        "http_status": http_status,
        "elapsed_seconds": elapsed_seconds,
        "observed_model": projection.get("model"),
        "provider_receipts": provider_receipts,
        "usage_components": _usage_components(payload),
        "input_flags": input_flags,
        "input_flag_verdict": input_verdict,
        "projection": projection,
        "selected_poi_ids": selected,
        "selected_stops": _selected_stops_from_projection(projection) if ok else [],
        "unknown_selected_ids": unknown_ids,
        "not_evaluator_result": True,
    }
    return record, observation


def _aggregate_usage(receipts: Sequence[Mapping[str, Any]]) -> int:
    total = 0
    for receipt in receipts:
        attempts = receipt.get("attempts")
        if isinstance(attempts, int) and not isinstance(attempts, bool):
            total += attempts
    return total


def _provider_fatal(response: Mapping[str, Any], receipts: Any, payload: Any) -> bool:
    """Positive provider/auth/quota/transport stop signal; never inferred."""
    status = response.get("status")
    if status in (401, 403, 429, 503) or status is None:
        return True
    if isinstance(receipts, (list, tuple)) and any(
            not isinstance(receipt, Mapping) or receipt.get("ok") is not True
            for receipt in receipts):
        return True
    if not isinstance(payload, Mapping):
        return False
    codes: List[str] = []
    error = payload.get("error")
    if isinstance(error, Mapping) and isinstance(error.get("code"), str):
        codes.append(error["code"])
    if isinstance(payload.get("error_code"), str):
        codes.append(payload["error_code"])
    return any(code in _FATAL_PROVIDER_CODES for code in codes)


def _http_fatal(response: Mapping[str, Any]) -> bool:
    return response.get("status") in (401, 403, 429, 503) or response.get("status") is None


def _fatal_reason(response: Mapping[str, Any]) -> str:
    """Closed reason enum; HTTP503 alone never means quota or auth."""
    return ("provider_unavailable" if response.get("status") == 503
            else "provider_fatal")


def _run_lifecycle(*, backend: Any, manifest: Mapping[str, Any], ledger: Ledger,
                   out: Path, run_nonce: str, m1_owner: str,
                   m1_session_primary: str) -> Dict[str, Any]:
    """Exactly three post-primary lifecycle chats; never part of H3 evaluation."""
    result: Dict[str, Any] = {
        "status": "skipped",
        "chats": 0,
        "cases": [],
        "cli_attempts": 0,
        "stage_counts": {"lifecycle_setup": 0, "lifecycle_chat": 0},
        "unknown_preference_boundary": (
            "Boundary correctness only; no preferred-share success is inferred."),
    }
    profiles = {p["profile_id"]: p for p in manifest["profiles"]}
    restaurant = "hcm_primary_geojson:source-category:restaurant"
    updated_profile = {"tags": [restaurant], "pace": "relaxed"}
    case_order = (
        "profile_update_expected_version_1",
        "current_profile_is_restaurant",
        "contradictory_chat_profile_fenced",
        "updated_profile_survives_owned_restart",
        "new_chat_has_updated_profile_and_no_old_short_history",
        "explicit_profile_delete",
        "post_delete_no_profile_or_history",
    )
    done: set = set()

    def case(name: str, passed: Optional[bool], detail: Any = None) -> None:
        done.add(name)
        result["cases"].append({"case": name, "passed": passed, "detail": detail})

    def finish_stop(reason: str) -> Dict[str, Any]:
        for name in case_order:
            if name not in done:
                case(name, None, {"not_attempted": reason})
        result["stop_reason"] = reason
        result["status"] = "partial"
        return result

    def chat(request_key: str, session_id: str, message: str,
             profile_for_flags: Optional[Dict[str, Any]], marker: str,
             expected_history: bool, expected_profile: bool,
             flag_condition: str) -> Dict[str, Any]:
        body = _chat_payload(session_id, message, "two_tier")
        ledger.reserve(request_key, "lifecycle_chat", "POST", "/chat")
        response = backend.request("POST", "/chat", body, owner=m1_owner)
        receipts = _provider_receipts(response.get("payload"))
        payload = response.get("payload") if isinstance(response.get("payload"), Mapping) else {}
        fatal = _provider_fatal(response, receipts, payload)
        ledger.close(
            request_key, "lifecycle_chat",
            status=payload.get("status") if isinstance(payload, Mapping) else "unknown",
            http_status=response.get("status"),
            elapsed_seconds=response.get("elapsed_seconds"),
            error_code=(response.get("error_code")
                        or _payload_error_code(payload)),
            outcome={"provider_ok": bool(receipts) and
                     all(r.get("ok") is True for r in receipts),
                     "provider_fatal": fatal},
        )
        result["chats"] += 1
        result["stage_counts"]["lifecycle_chat"] += 1
        result["cli_attempts"] += _aggregate_usage(receipts)
        flags = None
        try:
            flags = backend.input_flags(receipts, profile_for_flags, marker)
        except Exception as exc:  # sanitized type only
            flags = {"status": "unknown", "reason": type(exc).__name__}
        flags_ok = (
            isinstance(flags, Mapping)
            and flags.get("status") == "proven"
            and flags.get("session_export") is True
            and flags.get("fixture_credentials_absent") is True
            and flags.get("history_marker") is expected_history
            and flags.get("profile_prompt") is expected_profile
        )
        chat_ok = (
            not fatal
            and response.get("status") == 200
            and isinstance(payload, Mapping)
            and payload.get("status") == "success"
            and payload.get("model") == MODEL
            and payload.get("source_scope") == SOURCE
            and _receipts_identity_error(receipts) is None
            and flags_ok
        )
        if not chat_ok:
            ledger.observe(
                request_key, "lifecycle_chat",
                provider_receipts=receipts,
                error_code=(response.get("error_code")
                            or _payload_error_code(payload)))
        return {"ok": chat_ok, "fatal": fatal, "flags": flags,
                "verdict": _flags_verdict(flags, flag_condition),
                "strict_flags_ok": flags_ok}

    try:
        # Step 1: explicit profile replacement (CAS version 1) and contradiction.
        ledger.reserve("lifecycle:profile_update", "lifecycle_setup", "PUT",
                       "/memory/profile")
        body = {"profile": updated_profile, "expected_version": 1}
        response = backend.request("PUT", "/memory/profile", body, owner=m1_owner)
        result["stage_counts"]["lifecycle_setup"] += 1
        payload = response.get("payload") if isinstance(response.get("payload"), Mapping) else {}
        ledger.close("lifecycle:profile_update", "lifecycle_setup",
                     status=payload.get("version"), http_status=response.get("status"),
                     elapsed_seconds=response.get("elapsed_seconds"),
                     error_code=response.get("error_code"))
        case("profile_update_expected_version_1",
             response.get("status") == 200 and payload.get("version") == 2,
             {"http": response.get("status"), "version": payload.get("version")})
        if _http_fatal(response):
            return finish_stop("provider_or_transport_fatal")

        ledger.reserve("lifecycle:profile_read_1", "lifecycle_setup", "GET",
                       "/memory/profile")
        response = backend.request("GET", "/memory/profile", None, owner=m1_owner)
        result["stage_counts"]["lifecycle_setup"] += 1
        current = response.get("payload") if isinstance(response.get("payload"), Mapping) else {}
        ledger.close("lifecycle:profile_read_1", "lifecycle_setup",
                     status="read", http_status=response.get("status"),
                     elapsed_seconds=response.get("elapsed_seconds"),
                     error_code=response.get("error_code"))
        case("current_profile_is_restaurant",
             response.get("status") == 200
             and current.get("version") == 2
             and current.get("profile") == updated_profile,
             {"http": response.get("status"), "version": current.get("version")})
        if _http_fatal(response):
            return finish_stop("provider_or_transport_fatal")

        chat1_session = f"exp080-M1-two_tier-lifecycle1-{run_nonce}"
        outcome1 = chat(
            "lifecycle:chat1", chat1_session,
            "Tôi không còn thích cà phê; hãy gợi ý một nhà hàng cho ngày "
            "2026-11-01 trong phạm vi dữ liệu đã chọn, nhịp độ thong thả.",
            updated_profile, "H3_HISTORY_M1", False, True, "two_tier")
        case("contradictory_chat_profile_fenced", outcome1["ok"],
             {"input_flag_verdict": outcome1["verdict"],
              "strict_flags_ok": outcome1["strict_flags_ok"],
              "provider_fatal": outcome1["fatal"]})
        if outcome1["fatal"]:
            return finish_stop("provider_fatal")

        # Step 2: owned restart, same RAM issuer and SQLite database.
        backend.stop()
        backend.start()
        ledger.reserve("lifecycle:profile_read_2", "lifecycle_setup", "GET",
                       "/memory/profile")
        response = backend.request("GET", "/memory/profile", None, owner=m1_owner)
        result["stage_counts"]["lifecycle_setup"] += 1
        after = response.get("payload") if isinstance(response.get("payload"), Mapping) else {}
        ledger.close("lifecycle:profile_read_2", "lifecycle_setup",
                     status="read", http_status=response.get("status"),
                     elapsed_seconds=response.get("elapsed_seconds"),
                     error_code=response.get("error_code"))
        case("updated_profile_survives_owned_restart",
             response.get("status") == 200 and after.get("profile") == updated_profile,
             {"http": response.get("status"), "version": after.get("version")})
        if _http_fatal(response):
            return finish_stop("provider_or_transport_fatal")
        chat2_session = f"exp080-M1-two_tier-lifecycle2-{run_nonce}"
        outcome2 = chat("lifecycle:chat2", chat2_session,
                        SHARED_SCORING_MESSAGE, updated_profile, "H3_HISTORY_M1",
                        False, True, "two_tier")
        case("new_chat_has_updated_profile_and_no_old_short_history",
             outcome2["ok"],
             {"input_flag_verdict": outcome2["verdict"],
              "strict_flags_ok": outcome2["strict_flags_ok"],
              "provider_fatal": outcome2["fatal"]})
        if outcome2["fatal"]:
            return finish_stop("provider_fatal")

        # Step 3: explicit delete + own short clear, then unknown-preference boundary.
        ledger.reserve("lifecycle:profile_delete", "lifecycle_setup", "DELETE",
                       "/memory/profile")
        response = backend.request("DELETE", "/memory/profile", None, owner=m1_owner)
        result["stage_counts"]["lifecycle_setup"] += 1
        deleted = response.get("payload") if isinstance(response.get("payload"), Mapping) else {}
        ledger.close("lifecycle:profile_delete", "lifecycle_setup",
                     status=deleted.get("deleted"), http_status=response.get("status"),
                     elapsed_seconds=response.get("elapsed_seconds"),
                     error_code=response.get("error_code"))
        case("explicit_profile_delete", response.get("status") == 200 and
             deleted.get("deleted") is True, {"http": response.get("status")})
        if _http_fatal(response):
            return finish_stop("provider_or_transport_fatal")
        chat3_session = f"exp080-M1-two_tier-lifecycle3-{run_nonce}"
        ledger.reserve("lifecycle:short_clear", "lifecycle_setup", "POST",
                       "/memory/short/clear")
        response = backend.request("POST", "/memory/short/clear",
                                   {"session_id": chat3_session}, owner=m1_owner)
        result["stage_counts"]["lifecycle_setup"] += 1
        cleared = response.get("payload") if isinstance(response.get("payload"), Mapping) else {}
        ledger.close("lifecycle:short_clear", "lifecycle_setup",
                     status=cleared.get("cleared"), http_status=response.get("status"),
                     elapsed_seconds=response.get("elapsed_seconds"),
                     error_code=response.get("error_code"))
        if _http_fatal(response):
            return finish_stop("provider_or_transport_fatal")
        outcome3 = chat("lifecycle:chat3", chat3_session, SHARED_SCORING_MESSAGE,
                        None, "H3_HISTORY_M1", False, False, "memory_disabled")
        case("post_delete_no_profile_or_history", outcome3["ok"],
             {"input_flag_verdict": outcome3["verdict"],
              "strict_flags_ok": outcome3["strict_flags_ok"],
              "provider_fatal": outcome3["fatal"]})
        if outcome3["fatal"]:
            return finish_stop("provider_fatal")
        result["status"] = ("completed" if all(c["passed"] is True for c in result["cases"])
                            else "partial")
    except Exception as exc:
        result["status"] = "partial"
        result["error_type"] = type(exc).__name__
        for name in case_order:
            if name not in done:
                case(name, None, {"not_attempted": "lifecycle_exception"})
    return result


def _execute(manifest: Mapping[str, Any], out: Path) -> Tuple[int, Dict[str, Any]]:
    ledger = Ledger(out / "ledger.jsonl", out)
    records_path = out / "h3_records.jsonl"
    observations_path = out / "observations.jsonl"
    _write_json(out / "executed_manifest.json", manifest)
    run_nonce = secrets.token_hex(6)
    backend = backend_factory(manifest, out)
    started = False
    stopped_early = False
    stop_reason: Optional[str] = None
    prep_count = 0
    score_count = 0
    lifecycle_chats = 0
    known_cli_attempts = 0
    setup_failures = 0
    primary_errors = 0
    delivered_cells = 0
    records: List[Dict[str, Any]] = []
    observations: List[Dict[str, Any]] = []
    stage_usage: Dict[str, int] = {"preparation_chat_requests": 0,
                                   "typed_scoring_requests": 0,
                                   "lifecycle_chat_requests": 0}
    profiles = {p["profile_id"]: p for p in manifest["profiles"]}
    cells = list(manifest["primary_cells"])
    m1_cell = next((c for c in cells if c["profile_id"] == "M1"
                    and c["condition"] == "two_tier"), None)
    m1_owner = f"exp080:{m1_cell['cell_id']}" if m1_cell else ""
    m1_session = f"exp080-M1-two_tier-r0-{run_nonce}"
    m1_primary_ok = False
    cleanup: Dict[str, Any] = {"attempted": False, "ok": None, "error_code": None}
    result: Dict[str, Any] = {}

    try:
        backend.start()
        started = True
        for cell in cells:
            if stopped_early:
                ledger.planned_not_attempted(
                    f"{cell['cell_id']}:prep", "primary_preparation",
                    stop_reason or "stopped")
                ledger.planned_not_attempted(
                    f"{cell['cell_id']}:score", "primary_score",
                    stop_reason or "stopped")
                continue
            if prep_count + score_count + lifecycle_chats >= MAX_CHAT_REQUESTS:
                stopped_early = True
                stop_reason = "chat_request_cap"
                continue
            profile = profiles[cell["profile_id"]]
            condition = cell["condition"]
            category_id = cell["category_id"]
            owner = f"exp080:{cell['cell_id']}"
            session_id = (f"exp080-{cell['profile_id']}-{condition}-"
                          f"r{cell['repetition']}-{run_nonce}")
            preparation = PREP_TEMPLATE.format(
                category_label_vi=cell["category_label_vi"],
                category_id=category_id,
                profile_id=cell["profile_id"],
            )

            # Explicit durable profile only for two_tier, before preparation.
            if condition == "two_tier":
                ledger.reserve(f"{cell['cell_id']}:profile", "primary_setup",
                               "PUT", "/memory/profile")
                response = backend.request(
                    "PUT", "/memory/profile",
                    {"profile": profile["initial_profile"]}, owner=owner)
                body = response.get("payload") if isinstance(response.get("payload"), Mapping) else {}
                ledger.close(
                    f"{cell['cell_id']}:profile", "primary_setup",
                    status=body.get("version"), http_status=response.get("status"),
                    elapsed_seconds=response.get("elapsed_seconds"),
                    error_code=response.get("error_code"))
                if response.get("status") != 200 or body.get("version") != 1:
                    setup_failures += 1
                    ledger.planned_not_attempted(
                        f"{cell['cell_id']}:score", "primary_score",
                        "profile_setup_failed")
                    ledger.planned_not_attempted(
                        f"{cell['cell_id']}:prep", "primary_preparation",
                        "profile_setup_failed")
                    continue

            # Preparation chat immediately before the typed score request.
            prep_key = f"{cell['cell_id']}:prep"
            ledger.reserve(prep_key, "primary_preparation", "POST", PREP_ENDPOINT)
            response = backend.request(
                "POST", PREP_ENDPOINT, _chat_payload(session_id, preparation, condition),
                owner=owner)
            prep_count += 1
            stage_usage["preparation_chat_requests"] += 1
            payload = response.get("payload") if isinstance(response.get("payload"), Mapping) else None
            receipts = _provider_receipts(payload)
            known_cli_attempts += _aggregate_usage(receipts)
            ledger.close(
                prep_key, "primary_preparation",
                status=(payload or {}).get("status") if isinstance(payload, Mapping) else "unknown",
                http_status=response.get("status"),
                elapsed_seconds=response.get("elapsed_seconds"),
                error_code=(response.get("error_code")
                            or _payload_error_code(payload)),
                outcome={"provider_receipts": len(receipts),
                         "provider_ok": bool(receipts) and
                         all(r.get("ok") is True for r in receipts)})
            prep_ok = (
                response.get("status") == 200
                and isinstance(payload, Mapping)
                and payload.get("status") == "success"
                and payload.get("intent") == "TRAVEL"
                and isinstance(payload.get("model"), str)
                and payload.get("model") == MODEL
                and payload.get("source_scope") == SOURCE
                and receipts
                and all(r.get("ok") is True for r in receipts)
            )
            if not prep_ok:
                setup_failures += 1
                fatal = _provider_fatal(response, receipts, payload)
                ledger.observe(
                    prep_key, "primary_preparation",
                    provider_receipts=receipts,
                    error_code=(response.get("error_code")
                                or _payload_error_code(payload)))
                ledger.planned_not_attempted(
                    f"{cell['cell_id']}:score", "primary_score",
                    "provider_fatal" if fatal else "preparation_failed")
                if fatal:
                    stopped_early = True
                    stop_reason = _fatal_reason(response)
                continue

            # Primary scoring through the real typed itinerary endpoint.
            score_key = f"{cell['cell_id']}:score"
            if prep_count + score_count + lifecycle_chats >= MAX_CHAT_REQUESTS:
                stopped_early = True
                stop_reason = "chat_request_cap"
                ledger.planned_not_attempted(score_key, "primary_score",
                                             stop_reason)
                continue
            ledger.reserve(score_key, "primary_score", "POST", TYPED_ENDPOINT)
            response = backend.request(
                "POST", TYPED_ENDPOINT,
                _itinerary_payload(session_id, condition),
                owner=owner)
            score_count += 1
            stage_usage["typed_scoring_requests"] += 1
            payload = response.get("payload") if isinstance(response.get("payload"), Mapping) else None
            receipts = _provider_receipts(payload)
            known_cli_attempts += _aggregate_usage(receipts)
            ledger.close(
                score_key, "primary_score",
                status=(payload or {}).get("status") if isinstance(payload, Mapping) else "unknown",
                http_status=response.get("status"),
                elapsed_seconds=response.get("elapsed_seconds"),
                error_code=(response.get("error_code")
                            or _payload_error_code(payload)),
                outcome={"provider_receipts": len(receipts),
                         "provider_ok": bool(receipts) and
                         all(r.get("ok") is True for r in receipts)})

            flags = None
            try:
                flags = backend.input_flags(
                    receipts,
                    profile["initial_profile"] if condition == "two_tier" else None,
                    cell["history_marker"])
            except Exception as exc:  # sanitized type only
                flags = {"status": "unknown", "reason": type(exc).__name__}
            verdict = _flags_verdict(flags, condition)
            fatal = _provider_fatal(response, receipts, payload)
            failure_code = None
            if fatal:
                failure_code = _fatal_reason(response)
                stopped_early = True
                stop_reason = failure_code
            record, observation = _record_from_response(
                manifest=manifest, cell=cell, payload=payload,
                http_status=response.get("status"),
                elapsed_seconds=response.get("elapsed_seconds"),
                provider_receipts=receipts, input_flags=flags,
                input_verdict=verdict, failure_code=failure_code)
            _append_jsonl(records_path, record, backend)
            _append_jsonl(observations_path, observation, backend)
            records.append(record)
            observations.append(observation)
            if (record["run_status"] == "completed"
                    and record["plan_present"] and not record["empty_plan"]):
                delivered_cells += 1
            else:
                primary_errors += 1
            if cell["profile_id"] == "M1" and condition == "two_tier" \
                    and record["run_status"] == "completed" \
                    and record["plan_present"] and not record["empty_plan"]:
                m1_primary_ok = True
            if failure_code is not None:
                continue

        lifecycle: Dict[str, Any]
        if stopped_early or not m1_primary_ok or lifecycle_chats:
            lifecycle = {"status": "skipped", "chats": 0, "cases": [],
                         "reason": stop_reason or "primary_m1_two_tier_not_delivered"}
        else:
            lifecycle = _run_lifecycle(
                backend=backend, manifest=manifest, ledger=ledger, out=out,
                run_nonce=run_nonce, m1_owner=m1_owner,
                m1_session_primary=m1_session)
            lifecycle_chats = int(lifecycle.get("chats") or 0)
            stage_usage["lifecycle_chat_requests"] = lifecycle_chats
            stage_usage["lifecycle_setup_requests"] = int(
                (lifecycle.get("stage_counts") or {}).get("lifecycle_setup") or 0)
            known_cli_attempts += int(lifecycle.get("cli_attempts") or 0)

        total_chats = prep_count + score_count + lifecycle_chats
        if total_chats > MAX_CHAT_REQUESTS:
            stopped_early = True
            stop_reason = stop_reason or "chat_request_cap_exceeded"
        status = (
            "completed"
            if (score_count == 15 and setup_failures == 0
                and primary_errors == 0 and not stopped_early
                and lifecycle.get("status") == "completed")
            else "partial")
        result = {
            "task": TASK,
            "method": METHOD,
            "status": status,
            "execute": True,
            "run_nonce": run_nonce,
            "manifest_sha256": _canonical_hash(manifest),
            "calls": {
                "preparation_chats": prep_count,
                "scoring_chats": score_count,
                # Compatibility alias: typed score requests are not chat calls.
                "typed_scoring_requests": score_count,
                "lifecycle_chats": lifecycle_chats,
                "total_chat_requests": total_chats,
                "total_model_generating_requests": total_chats,
                "known_cli_attempts": known_cli_attempts,
                "jev_requests_observed": None,
                "compatibility_note": (
                    "Legacy 'scoring_chats' is retained for EXP078 readers and "
                    "counts typed /generate_itinerary requests; use "
                    "'typed_scoring_requests' as the canonical field."),
            },
            "limits": dict(manifest.get("limits") or {}),
            "primary": {
                "planned_cells": 15,
                "recorded_cells": len(records),
                "delivered_cells": delivered_cells,
                "setup_failures": setup_failures,
                "primary_errors": primary_errors,
                "missing_cells": 15 - len(records),
                "stopped_early": stopped_early,
                "stop_reason": stop_reason,
            },
            "stage_accounting": stage_usage,
            "lifecycle": lifecycle,
            "input_observability": {
                "verdicts": {state: sum(1 for o in observations
                                        if o["input_flag_verdict"] == state)
                             for state in ("proven", "mismatch", "unknown")},
                "raw_export_persisted": False,
                "fixture_credentials_persisted": False,
                "note": "Missing export/proof stays unknown, never pass.",
            },
            "not_claimed": [
                "no full end-to-end provider usage/total savings inference",
                "no p-values from five synthetic profiles",
                "no H1 participants, grow-with-user or crawler",
                "lifecycle correctness is separate from primary H3 cells",
            ],
        }
        try:
            parsed = parse_h3_manifest(manifest)
            loaded = load_h3_records(records, parsed)
            result["evaluation"] = evaluate_h3(
                parsed, loaded,
                manifest_sha256=_canonical_hash(manifest),
                records_sha256=_sha256_file(records_path)
                if records_path.exists() else None)
        except Exception as exc:
            result["evaluation"] = {"error_type": type(exc).__name__}
            result["status"] = "partial"
    except Exception as exc:
        result = {
            "task": TASK,
            "method": METHOD,
            "status": "partial",
            "execute": True,
            "run_nonce": run_nonce,
            "manifest_sha256": _canonical_hash(manifest),
            "error_type": type(exc).__name__,
            "not_claimed": ["executor does not accept or freeze the study"],
        }
    finally:
        if started:
            cleanup["attempted"] = True
            try:
                backend.stop()
                cleanup["ok"] = True
            except Exception as exc:
                cleanup["ok"] = False
                cleanup["error_code"] = type(exc).__name__
    result["cleanup"] = cleanup
    if cleanup["ok"] is False:
        result["status"] = "partial"
        result["failure_code"] = "owned_cleanup_failed"
    _write_json(out / "result.json", result, backend)
    return (0 if result["status"] == "completed" else 1), result


def _dry_run(manifest: Mapping[str, Any], manifest_path: Path, out: Path) -> int:
    _validate_shape(manifest)
    _ensure_out_dir(out)
    _write_json(out / "candidate_manifest.json", manifest)
    planned = manifest["primary_cells"]
    planned_requests = []
    for cell in planned:
        planned_requests.append({"request_key": f"{cell['cell_id']}:prep",
                                 "stage": "primary_preparation",
                                 "method": "POST", "path": PREP_ENDPOINT})
        if cell["condition"] == "two_tier":
            planned_requests.append({"request_key": f"{cell['cell_id']}:profile",
                                     "stage": "primary_setup",
                                     "method": "PUT", "path": "/memory/profile"})
        planned_requests.append({"request_key": f"{cell['cell_id']}:score",
                                 "stage": "primary_score",
                                 "method": "POST", "path": TYPED_ENDPOINT})
    summary = {
        "task": TASK,
        "method": METHOD,
        "status": "dry_run",
        "execute": False,
        "native_calls": 0,
        "provider_calls": 0,
        "http_calls": 0,
        "process_calls": 0,
        "manifest_path": str(manifest_path),
        "manifest_sha256": _canonical_hash(manifest),
        "manifest_frozen": manifest.get("frozen") is True,
        "thesis_mode": manifest.get("thesis_mode") is True,
        "source_scope": dict(SOURCE),
        "payload_sha256": PAYLOAD_SHA256,
        "category_truth_records": len(manifest["category_truth"]),
        "category_truth_sha256": CATEGORY_TRUTH_SHA256,
        "profiles": list(PROFILE_IDS),
        "conditions": list(CONDITIONS),
        "scenario_id": SCENARIO_ID,
        "repetitions_per_case": REPETITIONS,
        "planned_primary_cells": len(planned),
        "planned_preparation_chats": 15,
        "planned_scoring_chats": 15,
        "planned_typed_score_requests": 15,
        "planned_lifecycle_chats_max": 3,
        "planned_chat_requests_max": MAX_CHAT_REQUESTS,
        "planned_model_generating_requests_max": MAX_CHAT_REQUESTS,
        "request_paths": {"preparation": PREP_ENDPOINT,
                          "primary_score": TYPED_ENDPOINT,
                          "lifecycle": PREP_ENDPOINT},
        "typed_request_body_without_session_and_memory": dict(TYPED_SHARED_BODY),
        "planned_requests": planned_requests,
        "limits": dict(manifest.get("limits") or {}),
        "guard": "synthetic, unfrozen candidate; not H1; no reviewer/freeze claimed",
    }
    _write_json(out / "dry_run.json", summary)
    if not manifest_path.exists():
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        _write_json(manifest_path, manifest)
    print(json.dumps({
        "status": "dry_run",
        "native_calls": 0,
        "planned_cells": 15,
        "planned_preparation_chats": 15,
        "planned_typed_score_requests": 15,
        "planned_chat_requests": 30,
        "lifecycle_chat_cap": 3,
        "frozen": False,
        "out": str(out),
    }, ensure_ascii=False))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="EXP080 typed native H3 collector (dry-run by default)")
    parser.add_argument("--out", required=True,
                        help="unique evidence output directory")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST),
                        help="candidate/execution manifest path")
    parser.add_argument("--execute", action="store_true",
                        help="explicitly execute frozen live collection")
    args = parser.parse_args(argv)
    manifest_path = Path(args.manifest)
    try:
        manifest = (_read_json(manifest_path) if manifest_path.exists()
                    else build_candidate_manifest())
        out = Path(args.out)
        if not args.execute:
            return _dry_run(manifest, manifest_path, out)
        # Freeze, source and code bindings are checked before any backend,
        # credential or process resolution.
        validate_execution_manifest(manifest)
        _ensure_out_dir(out)
        _write_json(out / "execution_manifest.json", manifest)
    except ValueError as exc:
        print(json.dumps({"status": "refused",
                          "error": str(exc) if str(exc) else "manifest_invalid"},
                         ensure_ascii=False))
        return 2
    try:
        code, _result = _execute(manifest, out)
    except Exception as exc:  # sanitized type only; never raw exception text
        _write_json(out / "result.json", {
            "task": TASK, "method": METHOD, "status": "partial",
            "execute": True, "error_type": type(exc).__name__,
            "not_claimed": ["executor does not accept or freeze the study"],
        })
        code = 1
    return code


class NativeBackend:
    """RAM-only JWT issuer plus the accepted MEM072 helper/API transport."""

    def __init__(self, manifest: Mapping[str, Any], output_dir: Path):
        self.manifest = manifest
        self.out = Path(output_dir)
        self.state_file = self.out / "native_state" / "core_service.json"
        self.database = self.out / "profiles.sqlite3"
        self.fixture_secret = secrets.token_urlsafe(48)
        self.tokens: Dict[str, str] = {}
        self.subjects: Dict[str, str] = {}
        self.helper: Any = None
        self.original_ai_environment: Any = None
        self.start_args: Any = None
        self.stop_args: Any = None
        self.started = False
        for port in (MCP_PORT, AI_PORT):
            if port in FORBIDDEN_PORTS:
                raise BoundedError("forbidden_port")

    def _load_helper(self) -> Any:
        if self.helper is not None:
            return self.helper
        spec = importlib.util.spec_from_file_location("exp080_native_helper", HELPER_PATH)
        if spec is None or spec.loader is None:
            raise BoundedError("helper_unavailable")
        helper = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = helper
        spec.loader.exec_module(helper)
        self.helper = helper
        return helper

    def _configure_helper(self) -> None:
        helper = self._load_helper()
        if self.original_ai_environment is None:
            self.original_ai_environment = helper.ai_environment
        original = self.original_ai_environment
        database = str(self.database)
        secret = self.fixture_secret

        def configured_ai_env(*args: Any, **kwargs: Any) -> Dict[str, str]:
            env = original(*args, **kwargs)
            env.update({
                "JWT_SECRET": secret,
                "MEMORY_DB_PATH": database,
                "AI_CLI_TIMEOUT_SECONDS": str(CLI_TIMEOUT_SECONDS),
            })
            return env

        helper.ai_environment = configured_ai_env

    def _restore_helper(self) -> None:
        if self.helper is not None and self.original_ai_environment is not None:
            self.helper.ai_environment = self.original_ai_environment

    def _helper_lifecycle(self, action: Any, args: Any) -> Dict[str, Any]:
        capture = io.StringIO()
        with contextlib.redirect_stdout(capture):
            code = action(args)
        text = capture.getvalue()
        if self.fixture_secret in text or any(t in text for t in self.tokens.values()):
            raise BoundedError("fixture_credential_in_lifecycle_output")
        if code != 0:
            try:
                payload = json.loads(text)
            except (ValueError, UnicodeError):
                payload = {}
            raise BoundedError(str(payload.get("error") or "owned_lifecycle_failed"))
        try:
            payload = json.loads(text)
        except (ValueError, UnicodeError) as exc:
            raise BoundedError("owned_lifecycle_output_invalid") from exc
        return {key: payload.get(key) for key in
                ("status", "run_id", "ports", "services", "ports_after")}

    def start(self) -> None:
        if self.started:
            return
        if self.state_file.exists():
            raise BoundedError("foreign_state_present")
        for port in (17687, 18989):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=2.0):
                    pass
            except OSError as exc:
                raise BoundedError("loopback_engine_not_ready") from exc
        self._configure_helper()
        args = self.helper.build_parser().parse_args([
            "start", "--alias", MODEL,
            "--mcp-port", str(MCP_PORT), "--ai-port", str(AI_PORT),
            "--state-file", str(self.state_file)])
        self.start_args = args
        self.stop_args = self.helper.build_parser().parse_args([
            "stop", "--state-file", str(self.state_file)])
        try:
            self._helper_lifecycle(self.helper.command_start, args)
            self.started = True
        except Exception:
            self._restore_helper()
            raise

    def stop(self) -> None:
        if not self.started or self.helper is None:
            return
        try:
            self._helper_lifecycle(self.helper.command_stop, self.stop_args)
            self.started = False
        finally:
            self._restore_helper()

    def _owner_token(self, owner: Optional[str]) -> Optional[str]:
        if owner is None:
            return None
        if owner not in self.tokens:
            subject = "exp080-" + hashlib.sha256(
                (owner + ":" + secrets.token_hex(12)).encode("utf-8")).hexdigest()[:32]
            self.subjects[owner] = subject
            import jwt  # imported only on live execution
            self.tokens[owner] = jwt.encode(
                {"sub": subject, "exp": int(time.time()) + 3600},
                self.fixture_secret, algorithm="HS256")
        return self.tokens[owner]

    def request(self, method: str, path: str, body: Any = None,
                owner: Optional[str] = None) -> Dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        token = self._owner_token(owner)
        if token is not None:
            headers["Authorization"] = "Bearer " + token
        data = None if body is None else json.dumps(
            body, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"http://127.0.0.1:{AI_PORT}{path}", data=data,
            headers=headers, method=method)
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
                payload = json.load(response)
            return {"status": 200, "payload": payload,
                    "elapsed_seconds": round(time.monotonic() - started, 6)}
        except urllib.error.HTTPError as exc:
            try:
                payload = json.loads(exc.read())
            except (ValueError, UnicodeError):
                payload = None
            return {"status": exc.code, "payload": payload,
                    "elapsed_seconds": round(time.monotonic() - started, 6)}
        except (urllib.error.URLError, TimeoutError, OSError):
            return {"status": None, "payload": None,
                    "elapsed_seconds": round(time.monotonic() - started, 6),
                    "error_code": "transport_error"}

    def _profile_block(self, profile: Optional[Mapping[str, Any]]) -> Optional[str]:
        if not isinstance(profile, Mapping):
            return None
        try:
            from ai_service.domains.memory import profile_prompt
        except ImportError:
            return None
        return profile_prompt(dict(profile), limit=PROFILE_BLOCK_LIMIT)

    def input_flags(self, provider_calls: Any, profile: Optional[Mapping[str, Any]],
                    history_marker: str) -> Dict[str, Any]:
        calls = list(provider_calls or []) if isinstance(provider_calls, (list, tuple)) else []
        error = _receipts_identity_error(calls)
        if error is not None:
            return {"status": "unknown", "reason": error}
        groups: Dict[str, List[Mapping[str, Any]]] = {}
        order: List[str] = []
        for call in calls:
            session_id = call["session_id"]
            if session_id not in groups:
                groups[session_id] = []
                order.append(session_id)
            groups[session_id].append(call)
        try:
            from ai_service.domains.providers.provenance import (
                ExportError, parse_export_bytes)
        except ImportError:  # benchmark-local sys.path also exposes ``domains``
            from domains.providers.provenance import ExportError, parse_export_bytes
        exports: Dict[str, bytes] = {}
        for session_id in order:
            try:
                process = subprocess.run(
                    [CLI_EXECUTABLE, "session", "export", "--standalone", session_id],
                    cwd=str(self.out), capture_output=True, timeout=45)
            except (OSError, subprocess.SubprocessError):
                return {"status": "unknown", "reason": "exact_export_unavailable"}
            if process.returncode != 0:
                return {"status": "unknown", "reason": "exact_export_unavailable"}
            stdout = process.stdout if isinstance(process.stdout, bytes) else b""
            stderr = process.stderr if isinstance(process.stderr, bytes) else b""
            secret = self.fixture_secret.encode()
            leaked = (secret in stdout or secret in stderr
                      or any(token.encode() in stdout or token.encode() in stderr
                             for token in self.tokens.values()))
            if leaked:
                raise BoundedError("fixture_credential_in_export")
            exports[session_id] = stdout

        user_texts: Dict[str, str] = {}
        for session_id in order:
            raw = exports[session_id]
            try:
                parsed = parse_export_bytes(raw)
            except ExportError:
                return {"status": "unknown", "reason": "exact_export_malformed"}
            if parsed.session_id != session_id:
                return {"status": "unknown", "reason": "export_session_mismatch"}
            if parsed.shape != "v2":
                return {"status": "unknown", "reason": "export_shape_unsupported"}
            assistants = parsed.assistant_messages
            if not assistants:
                return {"status": "unknown", "reason": "export_identity_missing"}
            message_ids = set()
            model_ids = set()
            provider_ids = set()
            for message in assistants:
                if message.content_error is not None:
                    return {"status": "unknown", "reason": "export_content_invalid"}
                if f"{message.provider_id}/{message.model_id}" != MODEL:
                    return {"status": "unknown", "reason": "export_model_mismatch"}
                if message.message_id:
                    message_ids.add(message.message_id)
                model_ids.add(message.model_id)
                provider_ids.add(message.provider_id)
            for call in groups[session_id]:
                expected_message = call.get("assistant_message_id")
                if expected_message is not None and expected_message not in message_ids:
                    return {"status": "unknown", "reason": "export_message_mismatch"}
                expected_provider = call.get("observed_provider_id")
                if expected_provider is not None and expected_provider not in provider_ids:
                    return {"status": "unknown", "reason": "export_provider_mismatch"}
                expected_model = call.get("observed_model_id")
                if expected_model is not None and expected_model not in model_ids:
                    return {"status": "unknown", "reason": "export_model_identity_mismatch"}
            try:
                data = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                return {"status": "unknown", "reason": "exact_export_malformed"}
            chunks: List[str] = []
            for message in data.get("messages") or []:
                if not isinstance(message, Mapping) or message.get("type") != "user":
                    continue
                text = message.get("text")
                if not isinstance(text, str):
                    return {"status": "unknown", "reason": "export_user_text_malformed"}
                chunks.append(text)
            user_texts[session_id] = "\n".join(chunks)

        # Presence is judged only on the last contributing stage (synthesis input).
        raw_text = user_texts[order[-1]]
        normalized = raw_text.replace("\r\n", "\n").replace("\r", "\n")
        expected_block = self._profile_block(profile)
        fence_present = any(marker in normalized for marker in PROFILE_FENCE_MARKERS)
        if expected_block:
            normalized_block = expected_block.replace("\r\n", "\n").replace("\r", "\n")
            profile_prompt = normalized_block in normalized or fence_present
        else:
            # profile=None is not proof of absence: an unexpected production
            # stored-profile fence means the input is not the intended condition.
            profile_prompt = fence_present
        return {
            "status": "proven",
            "session_export": True,
            "history_marker": history_marker in raw_text,
            "profile_prompt": profile_prompt,
            "profile_prompt_expected": bool(expected_block),
            "fixture_credentials_absent": True,
        }

    def assert_clean(self, value: Any) -> None:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
        if self.fixture_secret in text or any(t in text for t in self.tokens.values()):
            raise BoundedError("fixture_credential_in_artifact")


def backend_factory(manifest: Mapping[str, Any], output_dir: Path) -> Any:
    """Public native-execution boundary. Tests replace this callable."""
    return NativeBackend(manifest, output_dir)


if __name__ == "__main__":
    raise SystemExit(main())
