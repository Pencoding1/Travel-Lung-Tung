"""OC-021 live-model paired H2 engineering collector (stdlib only).

Default behaviour is a **dry run**: it writes the frozen run plan and makes no
model call. Actual calls require an explicit ``--execute``.

    python benchmarks/live_model/runner.py --out .tmp-live --scenario-ids S01,S12
    python benchmarks/live_model/runner.py --out .tmp-live --execute --timeout 120

Every observation is a fresh session (no ``--continue``/``--session``), uses an
explicit ``--model``/``--agent`` and ``--format json``, and runs under a
per-process ``OPENCODE_CONFIG_CONTENT`` that denies all tools. Each failure is
retained with a reason; a resume only fills missing keys and never overwrites
completed evidence.
"""

from __future__ import annotations

import pathlib
import sys

if __package__ in (None, ""):
    # Executed as a script (``python benchmarks/live_model/runner.py``): re-enter
    # through the package so the relative imports below resolve.
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
    from live_model.runner import main as _entry

    raise SystemExit(_entry())

import argparse
import math
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from . import (capture, export, hybrid_adapter, prompts, provenance, schema,
               service_projection, temporal_endpoint, v2_transport)
from .constants import (
    CONDITIONS,
    CONDITION_HYBRID,
    CONDITION_LLM_ONLY,
    DATASET_CLASS_PRIMARY,
    DATASET_CLASS_SYNTHETIC,
    DATASET_KIND,
    DEFAULT_MAX_CALLS,
    DEFAULT_REPETITIONS,
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_TRANSPORT,
    EVIDENCE_LEVEL,
    EXPERIMENT_AGENT,
    FORBIDDEN_CLI_FLAGS,
    MANIFEST_VERSION,
    METHOD_VERSION,
    MODEL_DISPLAY_NAME,
    MODEL_ID,
    MODEL_UPSTREAM_VERSION_VERIFIED,
    MODEL_VERSION_NOTE,
    PRIMARY_MIN_THESIS_SCENARIOS,
    RUN_LABEL,
    SCENARIOS_MANIFEST_VERSION,
    TRANSPORT_LEGACY_V1,
    TRANSPORT_PRODUCTION_V2,
    TRANSPORTS,
    V2_MANIFEST_VERSION,
    V2_METHOD_VERSION,
    V2_MODEL_DISPLAY_NAME,
    V2_MODEL_ID,
    V2_MODEL_UPSTREAM_VERSION_VERIFIED,
    V2_MODEL_VERSION_NOTE,
)
from .events import ParsedEvents, parse_event_lines
from .export import Observation
from .ledger import LedgerError, RunLedger, RunLock, validate_ledger_records
from .util import (
    canonical_hash,
    read_json,
    sha256_bytes,
    sha256_text,
    write_bytes_atomic,
    write_json_atomic,
    write_jsonl_atomic,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCENARIOS = REPO_ROOT / "benchmarks" / "planning" / "scenarios.json"

Executor = Callable[..., capture.CallResult]
ExportExecutor = Callable[..., capture.CallResult]


@dataclass
class SessionExportOutcome:
    """Result of the read-only ``opencode export`` sidecar attempt."""

    attempted: bool
    captured: bool
    verdict: Optional[provenance.ProvenanceVerdict]
    meta: Optional[Dict[str, Any]]
    export_path: Optional[str]
    sha256: Optional[str]
    gap_reason: str


def _export_paths(raw_stdout_path: Path) -> Tuple[Path, Path, Path]:
    """Sidecar paths derived from the observation's own raw capture path."""
    raw_stdout_path = Path(raw_stdout_path)
    base = raw_stdout_path.with_suffix("")
    return (base.parent / f"{base.name}.session-export.json",
            base.parent / f"{base.name}.session-export.stderr.txt",
            base.parent / f"{base.name}.session-meta.json")


def default_export_executor(cli: str, *, cwd: Path, timeout: float,
                            env: Dict[str, str]) -> ExportExecutor:
    def _export(session_id: str, export_path: Path, stderr_path: Path) -> capture.CallResult:
        return capture.run_export(cli, session_id, raw_stdout_path=Path(export_path),
                                  stderr_path=Path(stderr_path), cwd=cwd,
                                  timeout=timeout, env=env)
    return _export


def _run_session_export(parsed: ParsedEvents, model: str,
                        export_executor: Optional[ExportExecutor],
                        raw_stdout_path: Path) -> SessionExportOutcome:
    """Capture exactly the observed session id and bind it, or return a gap."""
    if export_executor is None or parsed.session_id is None:
        return SessionExportOutcome(False, False, None, None, None, None,
                                    "unknown_model_provenance")

    export_path, export_stderr, meta_path = _export_paths(raw_stdout_path)
    result = export_executor(parsed.session_id, export_path, export_stderr)

    try:
        data = export_path.read_bytes()
    except OSError:
        data = b""
    if result.timed_out or result.exit_code != 0 or not data:
        if data:
            write_json_atomic(meta_path, {
                "source": provenance.SOURCE_LABEL, "export_path": str(export_path),
                "export_sha256": sha256_bytes(data), "captured": True,
                "session_id": parsed.session_id, "requested_model_id": model,
                "provenance_ok": False, "reason": "session_export_failed"})
        return SessionExportOutcome(True, bool(data), None, None, str(export_path),
                                    sha256_bytes(data) if data else None,
                                    "session_export_failed")
    digest = sha256_bytes(data)
    try:
        exported = provenance.parse_session_export_bytes(data)
    except provenance.ProvenanceError:
        write_json_atomic(meta_path, {
            "source": provenance.SOURCE_LABEL, "export_path": str(export_path),
            "export_sha256": digest, "captured": True,
            "session_id": parsed.session_id, "requested_model_id": model,
            "provenance_ok": False, "reason": "malformed_session_export"})
        return SessionExportOutcome(True, True, None, None, str(export_path), digest,
                                    "malformed_session_export")

    verdict = provenance.validate_observation_export(parsed, exported, model)
    meta = provenance.build_sidecar_metadata(
        export=exported, verdict=verdict, requested_model_id=model,
        export_path=str(export_path), export_sha256=digest, captured=True)
    write_json_atomic(meta_path, meta)
    reason = "ok" if verdict.ok else (verdict.reason or "provenance_unproven")
    return SessionExportOutcome(True, True, verdict, meta, str(export_path), digest, reason)


# ---------------------------------------------------------------------------
# Scenario/dataset loading (never touches author_expected)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class DatasetDeclaration:
    """Explicit dataset identity propagated into every new artifact.

    The historical ``scenarios.json`` has no ``dataset_kind`` and is therefore
    synthetic by declaration. A ``real_supplied_primary_snapshot`` manifest is
    accepted only with an explicit payload hash, source scope, freeze flag and
    reviewed scenario-entry digest; it is never inferred from a path or count.
    """

    kind: str
    dataset_class: str
    dataset_id: str
    label: str
    manifest_version: Optional[str]
    manifest_sha256: str
    thesis_mode: bool
    is_primary: bool
    payload_sha256: Optional[str] = None
    source_scope: Any = None
    review: Optional[Dict[str, Any]] = None
    scenario_count: int = 0

    @property
    def thesis_ready(self) -> bool:
        return bool(self.is_primary and self.thesis_mode and self.review
                    and self.scenario_count >= PRIMARY_MIN_THESIS_SCENARIOS)


def _sha256_hex(value: Any) -> Optional[str]:
    if not isinstance(value, str) or len(value) != 64:
        return None
    try:
        int(value, 16)
    except ValueError:
        return None
    return value.lower()


def _scenario_entries_hash(entries: Sequence[dict]) -> str:
    """Digest of reviewed scenario identity/facts (excluding author_expected)."""
    reviewed = []
    for entry in entries:
        reviewed.append({
            "scenario_id": entry.get("scenario_id"),
            "input": entry.get("input"),
        })
    return canonical_hash(reviewed)


def _load_manifest_entries(path: Path) -> Tuple[dict, List[dict]]:
    try:
        manifest = read_json(path)
    except (OSError, ValueError) as exc:
        raise SystemExit(f"scenarios manifest is not readable JSON: {exc}")
    if not isinstance(manifest, dict):
        raise SystemExit("scenarios manifest must be a JSON object")
    entries = manifest.get("scenarios")
    if not isinstance(entries, list) or not entries:
        raise SystemExit("scenarios manifest has no scenarios")
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise SystemExit("scenario entry is not an object")
        scenario_id = entry.get("scenario_id")
        scenario_input = entry.get("input")
        if not isinstance(scenario_id, str) or not scenario_id.strip():
            raise SystemExit("scenario entry has no scenario_id")
        if not isinstance(scenario_input, dict):
            raise SystemExit(f"scenario {scenario_id!r} has no input object")
        if scenario_input.get("scenario_id") not in (None, scenario_id):
            raise SystemExit(
                f"scenario {scenario_id!r} input.scenario_id does not match")
        if scenario_id in seen:
            raise SystemExit(f"duplicate scenario_id {scenario_id!r}")
        seen.add(scenario_id)
    return manifest, entries


def _declaration_family(name: str, value: Any) -> Optional[str]:
    """Map an explicit declaration to its closed family, or fail."""
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise SystemExit(f"{name} must be a nonblank string when declared")
    if value in (DATASET_KIND, DATASET_CLASS_SYNTHETIC):
        return "synthetic"
    if value == DATASET_CLASS_PRIMARY:
        return "primary"
    raise SystemExit(f"unknown {name} declaration: {value!r}")


def _datasets_family(manifest: dict) -> str:
    """Resolve dataset_kind/dataset_class without letting contradictions pass."""
    kind = _declaration_family("dataset_kind", manifest.get("dataset_kind"))
    klass = _declaration_family("dataset_class", manifest.get("dataset_class"))
    if kind is not None and klass is not None and kind != klass:
        raise SystemExit("contradictory dataset_kind/dataset_class declaration")
    return kind or klass or "synthetic"


def _canonical_source_scope(value: Any) -> Optional[Dict[str, str]]:
    """Validate an explicit selector through the production source gate."""
    from domains.source_gate import canonical_selection
    return canonical_selection(value)


def _entry_source_scopes(entry: dict) -> List[Any]:
    scopes: List[Any] = []
    if "source_scope" in entry:
        scopes.append(entry.get("source_scope"))
    scenario_input = entry.get("input")
    if isinstance(scenario_input, dict) and "source_scope" in scenario_input:
        scopes.append(scenario_input.get("source_scope"))
    return scopes


def _payload_hash(manifest: dict) -> Optional[str]:
    """Graph-ready payload hash; conflicting duplicate fields fail closed."""
    primary = manifest.get("payload_sha256")
    alias = manifest.get("input_payload_sha256")
    if primary is not None and alias is not None and primary != alias:
        raise SystemExit("contradictory payload_sha256/input_payload_sha256 fields")
    return _sha256_hex(primary if primary is not None else alias)


def load_dataset_declaration(path: Path) -> DatasetDeclaration:
    """Validate the dataset declaration *before* any call or write."""
    path = Path(path)
    manifest, entries = _load_manifest_entries(path)
    manifest_sha256 = sha256_bytes(path.read_bytes())
    family = _datasets_family(manifest)
    label = manifest.get("label")
    if not isinstance(label, str) or not label.strip():
        label = RUN_LABEL
    manifest_version = manifest.get("manifest_version")
    if not isinstance(manifest_version, str) or not manifest_version.strip():
        manifest_version = None
    raw_thesis_mode = manifest.get("thesis_mode", False)
    if not isinstance(raw_thesis_mode, bool):
        raise SystemExit("thesis_mode must be a boolean")

    if family == "synthetic":
        if raw_thesis_mode:
            raise SystemExit(
                "synthetic fixtures cannot declare thesis_mode=true")
        digest = manifest_sha256[:16]
        dataset_id = manifest.get("dataset_id")
        if not isinstance(dataset_id, str) or not dataset_id.strip():
            dataset_id = (f"synthetic:{manifest_version or SCENARIOS_MANIFEST_VERSION}:"
                          f"{digest}")
        return DatasetDeclaration(
            kind=DATASET_KIND,
            dataset_class=DATASET_CLASS_SYNTHETIC,
            dataset_id=dataset_id,
            label=label,
            manifest_version=manifest_version,
            manifest_sha256=manifest_sha256,
            thesis_mode=False,
            is_primary=False,
            scenario_count=len(entries),
        )

    # --- Explicit primary declaration: fail closed on any missing fact -----
    if manifest.get("frozen") is not True:
        raise SystemExit("primary manifest must declare frozen=true")
    if manifest.get("excluded_from_original_dataset") is True:
        raise SystemExit("primary manifest contradicts its primary declaration")
    payload = _payload_hash(manifest)
    if payload is None:
        raise SystemExit("primary manifest requires a 64-hex input payload hash")
    source_scope = _canonical_source_scope(manifest.get("source_scope"))
    if source_scope is None:
        raise SystemExit(
            "primary manifest requires a canonical source_scope selector "
            "(dataset_namespace, input_sha256, source_area_id)")
    for entry in entries:
        for declared_scope in _entry_source_scopes(entry):
            if _canonical_source_scope(declared_scope) != source_scope:
                raise SystemExit(
                    f"scenario {entry['scenario_id']!r} source_scope does not "
                    "match the primary selection")
    review = manifest.get("review")
    if not isinstance(review, dict):
        raise SystemExit("primary manifest requires an explicit review proof")
    if review.get("decision") != "frozen_reviewed":
        raise SystemExit("primary review decision must be 'frozen_reviewed'")
    if not isinstance(review.get("reviewed_by"), str) \
            or not review["reviewed_by"].strip():
        raise SystemExit("primary review must name a reviewer")
    declared_hash = _sha256_hex(review.get("scenario_entries_sha256"))
    if declared_hash is None:
        raise SystemExit("primary review requires a scenario entries hash")
    actual_hash = _scenario_entries_hash(entries)
    if declared_hash != actual_hash:
        raise SystemExit("primary review hash does not match scenario entries")
    if raw_thesis_mode and len(entries) < PRIMARY_MIN_THESIS_SCENARIOS:
        raise SystemExit(
            f"thesis_mode requires >= {PRIMARY_MIN_THESIS_SCENARIOS} scenarios")
    dataset_id = manifest.get("dataset_id")
    if not isinstance(dataset_id, str) or not dataset_id.strip():
        dataset_id = f"primary:{payload[:16]}"
    return DatasetDeclaration(
        kind=DATASET_CLASS_PRIMARY,
        dataset_class=DATASET_CLASS_PRIMARY,
        dataset_id=dataset_id,
        label=label,
        manifest_version=manifest_version,
        manifest_sha256=manifest_sha256,
        thesis_mode=raw_thesis_mode,
        is_primary=True,
        payload_sha256=payload,
        source_scope=source_scope,
        review={
            "decision": review.get("decision"),
            "reviewed_by": review.get("reviewed_by"),
            "scenario_entries_sha256": declared_hash,
        },
        scenario_count=len(entries),
    )


def load_scenario_inputs(path: Path) -> "Dict[str, dict]":
    _, entries = _load_manifest_entries(Path(path))
    return {str(entry["scenario_id"]): entry["input"] for entry in entries}


# ---------------------------------------------------------------------------
# Run-state fingerprint / fail-closed validation
# ---------------------------------------------------------------------------
def provenance_strategy(session_export: bool) -> str:
    """The declared provenance policy bound into the run fingerprint."""
    return ("event_stream+session_export:v1" if session_export
            else "event_stream:v1")


def provenance_strategy_v2() -> str:
    return "provider_export:v2"


# ---------------------------------------------------------------------------
# H2091: closed terminal provider-authority stop policy (production-V2 only)
# ---------------------------------------------------------------------------
AUTHORITY_STOP_POLICY_ID = "h2091.authority-stop.v1"

# A positive, closed set of provider-failure *codes* that terminate the batch.
# Membership is by exact equality only: no exception text, substring, HTTP
# status inference or "contains auth" heuristic is used. Codes outside this set
# (including cli_timeout/provider_timeout/malformed output) keep the existing
# per-observation no-retry behaviour and do not stop later planned cells.
TERMINAL_PROVIDER_AUTHORITY_CODES = frozenset({
    "server_auth_refused",
    "server_rate_limited",
    "cli_agent_preflight_failed",
    "cli_server_preflight_failed",
    "cli_ambient_config_refused",
    "auth",
    "auth_error",
    "unauthorized",
    "forbidden",
    "permission_denied",
    "policy_denied",
    "quota",
    "quota_exceeded",
    "rate_limit",
    "rate_limited",
    "native_tool_use",
    "model_mismatch",
    "provider_mismatch",
    "agent_mismatch",
    "provenance_mismatch",
})


def authority_stop_policy() -> Dict[str, Any]:
    """The exact closed policy recorded in the V2 manifest and run summary."""
    codes = sorted(TERMINAL_PROVIDER_AUTHORITY_CODES)
    return {
        "policy_id": AUTHORITY_STOP_POLICY_ID,
        "terminal_codes": codes,
        "terminal_codes_sha256": canonical_hash(codes),
    }


def terminal_provider_authority_code(obs: Observation) -> Optional[str]:
    """Return the exact terminal code, or ``None`` for unknown/nonterminal.

    Only ``obs.provider_failure.code`` is inspected. The exception message,
    rejection text and arbitrary runtime error strings never participate.
    """
    failure = getattr(obs, "provider_failure", None)
    if not isinstance(failure, dict):
        return None
    code = failure.get("code")
    if isinstance(code, str) and code in TERMINAL_PROVIDER_AUTHORITY_CODES:
        return code
    return None


def _fingerprint_v2(model: str, agent: str, conditions: Sequence[str],
                    repetitions: int, timeout: float,
                    dataset: DatasetDeclaration,
                    scenario_ids: Sequence[str], planned_denominator: int
                    ) -> Dict[str, Any]:
    """Frozen settings for the production-V2 path.

    Transport version/method, the *actual* production transport system prompt,
    model, timeout, dataset identity and scenario selection are all bound. A
    change to any of them refuses a resume before any write.
    """
    return {
        "method_version": V2_METHOD_VERSION,
        "manifest_version": V2_MANIFEST_VERSION,
        "transport": {
            "version": TRANSPORT_PRODUCTION_V2,
            "method": v2_transport.V2_TRANSPORT_METHOD,
            "provider": v2_transport.V2_PROVIDER,
            "system_prompt_sha256": sha256_text(
                v2_transport.transport_system_prompt()),
            "cli_pure": v2_transport.V2_CLI_PURE,
            "max_attempts": v2_transport.V2_MAX_ATTEMPTS,
            "max_concurrency": v2_transport.V2_MAX_CONCURRENCY,
            "controls": {},
            "session_export": False,
        },
        "dataset_kind": dataset.kind,
        "dataset_class": dataset.dataset_class,
        "dataset_id": dataset.dataset_id,
        "dataset_payload_sha256": dataset.payload_sha256,
        "dataset_source_scope": dataset.source_scope,
        "scenarios_manifest_sha256": dataset.manifest_sha256,
        "requested_model_id": model,
        "experiment_agent": agent,
        "settings_id": v2_transport.settings_id(model, agent),
        "conditions": list(conditions),
        "repetitions_per_case": repetitions,
        "timeout_seconds": timeout,
        "scenario_ids": list(scenario_ids),
        "planned_denominator": planned_denominator,
        "provenance_strategy": provenance_strategy_v2(),
        "pure_mode": False,
        # H2091: the authority-stop policy identity and exact closed-code hash
        # are frozen source settings. A run created before this policy is
        # incompatible on resume before provider resolution or any write.
        "authority_stop": {
            "policy_id": AUTHORITY_STOP_POLICY_ID,
            "terminal_codes_sha256": authority_stop_policy()[
                "terminal_codes_sha256"],
        },
    }


def _fingerprint(model: str, agent: str, conditions: Sequence[str], repetitions: int,
                 timeout: float, dataset_id: str, manifest_sha256: str,
                 scenario_ids: Sequence[str], planned_denominator: int,
                 provenance_strategy_id: str = "event_stream:v1",
                 pure_mode: bool = False) -> Dict[str, Any]:
    return {
        "method_version": METHOD_VERSION,
        "dataset_id": dataset_id,
        "scenarios_manifest_sha256": manifest_sha256,
        "requested_model_id": model,
        "experiment_agent": agent,
        "settings_id": export.settings_id(model, agent, _system_prompt()),
        "conditions": list(conditions),
        "repetitions_per_case": repetitions,
        "timeout_seconds": timeout,
        # Provenance policy and controlled-call flag are part of the frozen
        # settings: changing either must refuse a resume before any write.
        "provenance_strategy": provenance_strategy_id,
        "pure_mode": bool(pure_mode),
        # Frozen run plan: ordered scenario selection, conditions and repetitions
        # fully determine execution order and denominator. Any selection or order
        # drift must be rejected before any write.
        "scenario_ids": list(scenario_ids),
        "planned_denominator": planned_denominator,
    }


def _evidence_exists(calls_path: Path, raw_dir: Path) -> bool:
    if calls_path.exists() and calls_path.stat().st_size > 0:
        return True
    return raw_dir.exists() and any(entry.is_file() for entry in raw_dir.iterdir())


def _require_compatible(existing: Any, fingerprint: Dict[str, Any]) -> None:
    if not isinstance(existing, dict):
        raise LedgerError("manifest_incompatible", "existing manifest is not an object")
    stored = existing.get("fingerprint")
    if not isinstance(stored, dict):
        raise LedgerError("manifest_incompatible",
                          "existing manifest has no run fingerprint (pre-OC023)")
    drift = {key: (stored.get(key), value)
             for key, value in fingerprint.items() if stored.get(key) != value}
    if drift:
        raise LedgerError("manifest_incompatible", f"settings/source drift: {drift}")


# ---------------------------------------------------------------------------
# Run plan
# ---------------------------------------------------------------------------
def execution_order(scenario_ids: Sequence[str], repetitions: int,
                    conditions: Sequence[str]) -> List[Tuple[str, str, int]]:
    """Deterministic alternating arm order (counterbalances condition order)."""
    plan: List[Tuple[str, str, int]] = []
    for index, scenario_id in enumerate(scenario_ids):
        for repetition in range(repetitions):
            order = tuple(conditions) if (index + repetition) % 2 == 0 else tuple(reversed(conditions))
            for condition in order:
                plan.append((scenario_id, condition, repetition))
    return plan


def _observation_log(obs: Observation) -> Dict[str, Any]:
    """A JSON-safe log line: scalars plus typed plan/report summaries."""
    plan = None
    if obs.plan is not None:
        plan = {
            "status": obs.plan.status,
            "no_plan_reason": obs.plan.no_plan_reason,
            "sequence": list(obs.plan.sequence),
            "total_travel_minutes": obs.plan.total_travel_minutes,
            "total_distance_km": (str(obs.plan.total_distance_km)
                                  if obs.plan.total_distance_km is not None else None),
            "total_cost_party": (str(obs.plan.total_cost_party)
                                 if obs.plan.total_cost_party is not None else None),
        }
    report = None
    if obs.report is not None:
        report = {
            "status": obs.report.status,
            "no_plan_reason": obs.report.no_plan_reason,
            "known_violations": [
                {"code": v.code, "day_id": v.day_id, "poi_id": v.poi_id, "detail": v.detail}
                for v in obs.report.known_violations
            ],
            "unknown_reasons": list(obs.report.unknown_reasons),
            "unsatisfied_required": list(obs.report.unsatisfied_required),
            "stop_count": obs.report.stop_count,
            "recomputed_total_travel_minutes": obs.report.recomputed_total_travel_minutes,
            "recomputed_total_cost_party": (
                str(obs.report.recomputed_total_cost_party)
                if obs.report.recomputed_total_cost_party is not None else None),
            "recomputed_total_distance_km": (
                str(obs.report.recomputed_total_distance_km)
                if obs.report.recomputed_total_distance_km is not None else None),
        }
    return {
        "scenario_id": obs.scenario_id, "condition": obs.condition,
        "repetition": obs.repetition, "provenance_ok": obs.provenance_ok,
        "rejection_reason": obs.rejection_reason, "output_ok": obs.output_ok,
        "invalid_output_reason": obs.invalid_output_reason, "run_status": obs.run_status,
        "exit_code": obs.exit_code, "timed_out": obs.timed_out,
        "duration_seconds": obs.duration_seconds, "session_id": obs.session_id,
        "requested_model_id": obs.requested_model_id,
        "observed_model_ids": list(obs.observed_model_ids),
        "observed_provider_ids": list(obs.observed_provider_ids),
        "cli_version": obs.cli_version, "argv": list(obs.argv),
        "prompt_sha256": obs.prompt_sha256, "raw_event_path": obs.raw_event_path,
        "stderr_path": obs.stderr_path, "provider_usage": obs.provider_usage,
        "total_usage": obs.total_usage, "selected_poi_ids": list(obs.selected_poi_ids),
        "candidate_ids": list(obs.candidate_ids),
        "unknown_reasons": list(obs.unknown_reasons),
        "budget_deviation": obs.budget_deviation, "provenance": obs.provenance,
        "provenance_source": obs.provenance_source,
        "session_export_path": obs.session_export_path,
        "session_export_sha256": obs.session_export_sha256,
        "session_export_source": obs.session_export_source,
        "session_export_message_id": obs.session_export_message_id,
        "transport": obs.transport,
        "dataset_kind": obs.dataset_kind,
        "dataset_id": obs.dataset_id,
        "identity_source": obs.identity_source,
        "assistant_text_path": obs.assistant_text_path,
        "assistant_text_sha256": obs.assistant_text_sha256,
        "provider_receipt_path": obs.provider_receipt_path,
        "provider_receipt_sha256": obs.provider_receipt_sha256,
        "provider_failure": obs.provider_failure,
        "provider_metadata": obs.provider_metadata,
        "initial_proposal": obs.initial_proposal,
        "service_projection": obs.service_projection,
        "plan": plan, "report": report,
        "hybrid_mapping": obs.hybrid_mapping,
    }


def canonical_order(observations: Sequence[Observation],
                    scenario_ids: Sequence[str]) -> List[Observation]:
    index = {sid: i for i, sid in enumerate(scenario_ids)}
    condition_index = {c: i for i, c in enumerate(CONDITIONS)}
    return sorted(observations, key=lambda o: (index.get(o.scenario_id, 1 << 30),
                                               condition_index.get(o.condition, 1 << 30),
                                               o.repetition))


def _write_temporal_sidecars(out_dir: Path, global_manifest: Dict[str, Any],
                             logs: Sequence[Dict[str, Any]], *,
                             only_if_missing: bool = False) -> List[Dict[str, Any]]:
    """Write the EXP-077 companion beside the unchanged global H2 files."""
    manifest_path = out_dir / "h2_temporal_manifest.json"
    records_path = out_dir / "h2_temporal_records.jsonl"
    if only_if_missing and manifest_path.exists() and records_path.exists():
        return []
    temporal_manifest = temporal_endpoint.build_temporal_h2_manifest(global_manifest)
    write_json_atomic(manifest_path, temporal_manifest)
    records = temporal_endpoint.build_temporal_h2_records_from_logs(logs)
    write_jsonl_atomic(records_path, records)
    return records


def _manifest_for_temporal_resume(out_dir: Path,
                                  existing_manifest: Dict[str, Any],
                                  dataset: "DatasetDeclaration",
                                  scenario_ids: Sequence[str],
                                  repetitions: int) -> Dict[str, Any]:
    """Use the stored global H2 manifest, never rewrite it."""
    h2_manifest_path = out_dir / "h2_manifest.json"
    if h2_manifest_path.exists():
        try:
            return read_json(h2_manifest_path)
        except (OSError, ValueError) as exc:
            raise LedgerError("h2_manifest_unreadable",
                              f"existing h2_manifest.json is not valid JSON: {exc}")
    stored_ids = existing_manifest.get("scenario_ids")
    manifest_scenario_ids = (stored_ids if isinstance(stored_ids, list)
                             and stored_ids else list(scenario_ids))
    stored_reps = existing_manifest.get("repetitions_per_case")
    manifest_reps = (stored_reps if isinstance(stored_reps, int)
                     and not isinstance(stored_reps, bool) and stored_reps >= 1
                     else repetitions)
    return export.build_h2_manifest(
        manifest_scenario_ids, manifest_reps,
        manifest_version=(existing_manifest.get("manifest_version")
                          or V2_MANIFEST_VERSION),
        dataset_kind=(existing_manifest.get("dataset_kind") or dataset.kind),
        dataset_id=(existing_manifest.get("dataset_id") or dataset.dataset_id),
        label=(existing_manifest.get("dataset_label") or dataset.label),
        thesis_mode=bool(existing_manifest.get("thesis_mode")))



# ---------------------------------------------------------------------------
# One observation
# ---------------------------------------------------------------------------
def _provenance(scenario_input: dict, scenario_id: str, condition: str, model: str,
                agent: str, dataset_id: str, *,
                settings_id: Optional[str] = None,
                transport: Optional[str] = None) -> Dict[str, Optional[str]]:
    return {
        "candidate_id": canonical_hash({"scenario_id": scenario_id,
                                        "pois": scenario_input.get("pois", [])}),
        "route_id": canonical_hash({"scenario_id": scenario_id,
                                    "route_edges": scenario_input.get("route_edges", [])}),
        "prompt_information_id": prompts.prompt_information_id(scenario_input),
        "dataset_id": dataset_id,
        "model_id": model,  # observed == requested when provenance is proven
        "settings_id": settings_id or export.settings_id(model, agent, _system_prompt()),
        "method_instruction_hash": prompts.method_instruction_hash(condition),
        "transport": transport,
    }


def _system_prompt() -> str:
    from .constants import AGENT_SYSTEM_PROMPT
    return AGENT_SYSTEM_PROMPT


def default_executor(cli: str, *, model: str, agent: str, cwd: Path, timeout: float,
                     env: Dict[str, str], pure: bool = False) -> Executor:
    def _run(prompt: str, raw_stdout_path: Path, stderr_path: Path) -> capture.CallResult:
        return capture.run_opencode(cli, model=model, agent=agent, prompt=prompt,
                                    raw_stdout_path=raw_stdout_path,
                                    stderr_path=stderr_path, cwd=cwd, timeout=timeout,
                                    env=env, pure=pure)
    return _run


def _budget_deviation(scenario_input: dict, report) -> Optional[Dict[str, Any]]:
    budget = scenario_input.get("budget")
    if not isinstance(budget, dict) or report is None:
        return None
    total = report.recomputed_total_cost_party
    if total is None:
        return None
    try:
        amount = Decimal(str(budget.get("amount"))) - total
    except Exception:
        return None
    currency = budget.get("currency")
    if not isinstance(currency, str) or not currency.strip():
        return None
    return {"amount": str(amount), "currency": currency.strip(), "unit": "per_party",
            "comparable": True}


def _raw_identity_reason(event_ids: Sequence[str], event_providers: Sequence[str],
                         model: str) -> Optional[str]:
    """Reject any raw identity that is mixed or contradicts the requested id.

    A single matching hint among several is never sufficient: all observed model
    ids must equal the requested id exactly, and all observed provider ids must
    agree (and match the requested provider when the request is qualified).
    """
    model_set = {value for value in event_ids if value}
    if len(model_set) > 1:
        return "mixed_model_identity"
    if model_set != {model}:
        return "model_mismatch"
    provider_set = {value for value in event_providers if value}
    if len(provider_set) > 1:
        return "mixed_provider_identity"
    if "/" in model and provider_set and provider_set != {model.split("/", 1)[0]}:
        return "provider_mismatch"
    return None


def finalize_model_output(obs: Observation, scenario_input: dict, condition: str,
                          assistant_text: str) -> Observation:
    """Shared parse -> plan -> independent-validate finalisation.

    Legacy V1 and production V2 both use this exact path, so the evaluated
    algorithms and the independent validator are never duplicated.
    """
    mapping: Optional[Dict[str, Any]] = None
    parsed_output: Any = None
    try:
        if condition == CONDITION_LLM_ONLY:
            from .plans import build_llm_only_plan
            parsed_output = schema.parse_llm_only(assistant_text)
            scenario = _parse_scenario(scenario_input)
            plan = build_llm_only_plan(scenario, parsed_output)
        else:
            parsed_output = schema.parse_hybrid(assistant_text)
            scenario, plan, mapping = hybrid_adapter.schedule_hybrid(
                scenario_input, parsed_output)
    except schema.OutputError as exc:
        obs.invalid_output_reason = f"malformed_model_output:{exc}"
        obs.run_status = "failed"
        return obs
    except Exception as exc:  # planning contract rejection is still a failed run
        obs.invalid_output_reason = f"plan_build_failed:{type(exc).__name__}:{exc}"
        obs.run_status = "failed"
        return obs

    from domains.planning import validate
    report = validate(scenario, plan)
    obs.plan = plan
    obs.report = report
    obs.hybrid_mapping = mapping
    obs.initial_proposal = service_projection.initial_proposal(condition,
                                                               parsed_output)
    obs.service_projection = service_projection.build_projection(
        condition=condition, parsed=parsed_output, plan=plan, report=report,
        mapping=mapping, scenario_input=scenario_input)
    obs.selected_poi_ids = tuple(plan.sequence)
    obs.unknown_reasons = tuple(report.unknown_reasons)
    obs.budget_deviation = _budget_deviation(scenario_input, report)
    obs.output_ok = True
    obs.run_status = "refused" if report.status == "no_plan" else "completed"
    return obs


def run_v2_observation(scenario_input: dict, condition: str, repetition: int, *,
                       scenario_id: str, model: str, agent: str,
                       dataset_id: str, dataset_kind: str, prompt: str,
                       evidence_dir: Path,
                       complete: Callable[..., Any]) -> Observation:
    """One production-V2 observation through ``OpenCodeCliProvider.complete``.

    Exactly one call is made. Provider/schema/validation failures stay in the
    denominator as explicit failed observations; nothing is retried or repaired.
    """
    key = f"{scenario_id}__{condition}__r{repetition}"
    assistant_path = evidence_dir / f"{key}.assistant.txt"
    receipt_path = evidence_dir / f"{key}.provider-receipt.json"
    obs = Observation(
        scenario_id=scenario_id, condition=condition, repetition=repetition,
        provenance_ok=False, rejection_reason=None, output_ok=False,
        requested_model_id=model,
        prompt_sha256=sha256_text(prompt),
        raw_event_path=None, stderr_path=None,
        candidate_ids=tuple(prompts.candidate_poi_ids(scenario_input)),
        transport=TRANSPORT_PRODUCTION_V2,
        dataset_kind=dataset_kind,
        dataset_id=dataset_id,
        provenance=_provenance(
            scenario_input, scenario_id, condition, model, agent, dataset_id,
            settings_id=v2_transport.settings_id(model, agent),
            transport=TRANSPORT_PRODUCTION_V2),
    )
    if model in (None, "") or condition not in CONDITIONS:
        obs.rejection_reason = "invalid_configuration"
        return obs

    payload = v2_transport.build_payload(prompt, model)
    started = time.monotonic()
    try:
        completion = v2_transport.call_complete(complete, payload)
        validated = v2_transport.validate_completion(
            completion, requested_model=model,
            duration_seconds=round(time.monotonic() - started, 3))
    except v2_transport.CompletionRejected as exc:
        obs.rejection_reason = f"provider_contract:{exc.code}"
        obs.provider_failure = {
            "code": exc.code, "attempts": 0, "failed_attempts": 0,
            "retryable": False}
        obs.run_status = "failed"
        return obs
    except Exception as exc:  # bounded code only; never a raw exception string
        failure = v2_transport.provider_failure(exc)
        obs.rejection_reason = f"provider_failure:{failure.code}"
        obs.provider_failure = {
            "code": failure.code, "attempts": failure.attempts,
            "failed_attempts": failure.failed_attempts,
            "retryable": failure.retryable}
        obs.run_status = "error"
        return obs

    # Exact assistant text and the derived (not raw) provider receipt.
    assistant_bytes = validated.text.encode("utf-8")
    write_bytes_atomic(assistant_path, assistant_bytes)
    evidence = v2_transport.build_evidence(validated, requested_model=model)
    receipt_sha256 = write_json_atomic(receipt_path, evidence)

    obs.assistant_text_path = str(assistant_path)
    obs.assistant_text_sha256 = sha256_bytes(assistant_bytes)
    obs.provider_receipt_path = str(receipt_path)
    obs.provider_receipt_sha256 = receipt_sha256
    obs.provider_metadata = validated.provider
    obs.provider_usage = validated.usage
    obs.total_usage = validated.usage.get("total_tokens")
    obs.duration_seconds = validated.duration_seconds
    obs.session_id = validated.session_id
    obs.observed_model_ids = ((validated.model,) if validated.model else tuple())
    observed_provider = validated.provider.get("observed_provider_id")
    obs.observed_provider_ids = ((observed_provider,) if observed_provider else tuple())
    obs.identity_source = v2_transport.IDENTITY_SOURCE
    obs.provenance_source = v2_transport.IDENTITY_SOURCE
    capabilities = validated.provider.get("cli_capabilities")
    if isinstance(capabilities, dict):
        version = capabilities.get("version")
        if isinstance(version, str) and version.strip():
            obs.cli_version = version.strip()
    obs.run_status = "completed"
    obs.provenance_ok = True
    obs.rejection_reason = None
    return finalize_model_output(obs, scenario_input, condition, validated.text)


def run_observation(scenario_input: dict, condition: str, repetition: int, *,
                    scenario_id: str, model: str, agent: str, dataset_id: str,
                    prompt: str, raw_stdout_path: Path, stderr_path: Path,
                    executor: Executor,
                    export_executor: Optional[ExportExecutor] = None) -> Observation:
    obs = Observation(
        scenario_id=scenario_id, condition=condition, repetition=repetition,
        provenance_ok=False, rejection_reason=None, output_ok=False,
        requested_model_id=model,
        prompt_sha256=sha256_text(prompt),
        raw_event_path=str(raw_stdout_path), stderr_path=str(stderr_path),
        candidate_ids=tuple(prompts.candidate_poi_ids(scenario_input)),
        transport=TRANSPORT_LEGACY_V1,
        provenance=_provenance(
            scenario_input, scenario_id, condition, model, agent, dataset_id,
            transport=TRANSPORT_LEGACY_V1),
    )
    if model in (None, "") or condition not in CONDITIONS:
        obs.rejection_reason = "invalid_configuration"
        return obs

    try:
        result = executor(prompt, raw_stdout_path, stderr_path)
    except capture.CaptureError as exc:
        obs.rejection_reason = f"launch_failed:{exc}"
        return obs

    obs.exit_code = result.exit_code
    obs.timed_out = result.timed_out
    obs.duration_seconds = result.duration_seconds
    obs.argv = tuple(result.argv)
    obs.run_status = "error"

    try:
        text = Path(result.raw_stdout_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""
    parsed: ParsedEvents = parse_event_lines(text.splitlines())
    obs.session_id = parsed.session_id
    obs.observed_model_ids = parsed.observed_model_ids
    obs.observed_provider_ids = parsed.observed_provider_ids
    obs.provider_usage = parsed.usage.as_dict() if parsed.usage is not None else None
    obs.total_usage = parsed.usage.total_tokens if parsed.usage is not None else None

    # Authoritative sidecar: capture exactly the observed session id and bind it.
    # The raw JSONL is already persisted and is never rewritten.
    export = _run_session_export(parsed, model, export_executor, Path(raw_stdout_path))
    if export.export_path is not None:
        obs.session_export_path = export.export_path
        obs.session_export_sha256 = export.sha256
        obs.session_export_source = provenance.SOURCE_LABEL
    if export.verdict is not None and export.verdict.ok:
        obs.session_export_message_id = export.verdict.assistant_message_id

    event_ids = parsed.observed_model_ids

    if parsed.session_id is None:
        obs.rejection_reason = "unknown_session_provenance"
    elif event_ids:
        obs.provenance_source = "event_stream"
        raw_reason = _raw_identity_reason(event_ids, parsed.observed_provider_ids, model)
        if raw_reason is not None:
            obs.rejection_reason = raw_reason
        elif export.verdict is not None and not export.verdict.ok:
            # A captured export contradicted the raw event identity: fail closed.
            obs.rejection_reason = "provenance_conflict"
        else:
            if export.verdict is not None:
                obs.provenance_source = "event_stream+session_export"
            obs.rejection_reason = None
    elif export.verdict is not None and export.verdict.ok:
        # No model identity in the raw stream: the export is the sole authority.
        obs.provenance_source = "session_export"
        obs.observed_model_ids = (export.verdict.qualified_model_id,)
        obs.observed_provider_ids = (export.verdict.observed_provider_id,)
        obs.rejection_reason = None
    else:
        obs.rejection_reason = (export.gap_reason if export.attempted
                                else "unknown_model_provenance")
    obs.provenance_ok = obs.rejection_reason is None

    failures: List[str] = []
    if parsed.malformed_lines:
        failures.append("malformed_event_stream")
    if parsed.tool_use_count:
        failures.append("tool_use_event")
    if parsed.error_count:
        failures.append("error_event")
    if result.timed_out:
        failures.append("timeout")
    if not parsed.terminal_present:
        failures.append("no_terminal_completion")

    if not obs.provenance_ok:
        return obs

    if failures:
        obs.invalid_output_reason = ",".join(failures)
        obs.run_status = "error" if (result.timed_out or result.exit_code != 0) else "failed"
        return obs

    if result.exit_code != 0:
        obs.invalid_output_reason = f"nonzero_exit:{result.exit_code}"
        obs.run_status = "error"
        return obs

    assistant_text = "".join(parsed.text_parts)
    return finalize_model_output(obs, scenario_input, condition, assistant_text)


def _parse_scenario(scenario_input: dict):
    from domains.planning import parse_scenario
    return parse_scenario(scenario_input)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="live_model_runner",
        description="OC-021 live-model paired H2 engineering collector (dry-run by default).")
    parser.add_argument("--scenarios", default=str(DEFAULT_SCENARIOS))
    parser.add_argument("--out", required=True, help="output directory")
    parser.add_argument("--conditions", default=",".join(CONDITIONS))
    parser.add_argument("--scenario-ids", default=None,
                        help="comma-separated subset in manifest order (default: all)")
    parser.add_argument("--repetitions", type=int, default=DEFAULT_REPETITIONS)
    parser.add_argument("--execute", action="store_true", help="actually call the model")
    parser.add_argument("--resume", action="store_true",
                        help="only fill missing keys; never overwrite existing evidence")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--max-calls", type=int, default=DEFAULT_MAX_CALLS)
    parser.add_argument("--transport", choices=TRANSPORTS, default=DEFAULT_TRANSPORT,
                        help="model transport: production-v2 (default, accepted provider) "
                             "or legacy-v1 (historical tests/resume only)")
    parser.add_argument("--model", default=None,
                        help="explicit requested qualified model id "
                             "(default: production-v2 provider alias or legacy fixture id)")
    parser.add_argument("--agent", default=EXPERIMENT_AGENT)
    parser.add_argument("--cli", default=None, help="explicit opencode executable path")
    parser.add_argument("--cli-version", default=None,
                        help="legacy only: recorded CLI version override; ignored for "
                             "production-v2 (provider metadata is authoritative)")
    parser.add_argument("--session-export", action="store_true",
                        help="legacy-v1 only: bind provenance via read-only "
                             "'opencode export <sessionID>'")
    parser.add_argument("--pure", action="store_true",
                        help="legacy-v1 only: add the supported 'run --pure' flag "
                             "(production-v2 fails closed before any model call)")
    parser.add_argument("--cwd", default=str(REPO_ROOT))
    parser.add_argument("--update-register", action="store_true",
                        help="reserved; no register write happens in this collector")
    return parser


def _validate_flags(argv: Sequence[str]) -> None:
    for forbidden in FORBIDDEN_CLI_FLAGS:
        if forbidden in argv:
            raise SystemExit(f"forbidden flag passed to the collector: {forbidden}")


def prior_terminal_authority_stop(out_dir: Path) -> Optional[Dict[str, Any]]:
    """Return a stopped V2 run summary, or ``None``.

    Read-only: the caller must refuse ``--resume`` before provider resolution or
    any filesystem mutation. A terminal failure at the last/only planned cell is
    not a *stop of later cells* and therefore does not block a no-op resume.
    """
    path = Path(out_dir) / "run_manifest.json"
    if not path.exists():
        return None
    try:
        summary = read_json(path)
    except (OSError, ValueError):
        return None
    if not isinstance(summary, dict):
        return None
    if summary.get("stopped_early") is True \
            or summary.get("terminal_provider_authority_stop") is True:
        return summary
    return None


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _validate_flags(list(argv) if argv is not None else sys.argv[1:])

    if args.repetitions < 1:
        raise SystemExit("--repetitions must be >= 1")
    conditions = tuple(c.strip() for c in args.conditions.split(",") if c.strip())
    unknown = [c for c in conditions if c not in CONDITIONS]
    if unknown:
        raise SystemExit(f"unknown conditions: {unknown}")
    if len(set(conditions)) != len(conditions):
        raise SystemExit("duplicate --conditions are not allowed")
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        raise SystemExit("--timeout must be a finite positive number")
    if args.max_calls < 0:
        raise SystemExit("--max-calls must be >= 0")
    if args.transport not in TRANSPORTS:
        raise SystemExit(f"unknown transport: {args.transport}")
    if args.model is None:
        args.model = (V2_MODEL_ID if args.transport == TRANSPORT_PRODUCTION_V2
                      else MODEL_ID)
    if args.transport == TRANSPORT_PRODUCTION_V2:
        if args.pure:
            raise SystemExit(
                "--pure is not supported by production-v2; failing closed before "
                "any model call (the installed CLI has no --pure flag)")
        if args.session_export:
            raise SystemExit(
                "--session-export is a legacy-v1 flag; production-v2 uses the "
                "provider-owned exact session export")

    manifest_path = Path(args.scenarios)
    dataset = load_dataset_declaration(manifest_path)
    all_inputs = load_scenario_inputs(manifest_path)
    if args.scenario_ids:
        wanted = [s.strip() for s in args.scenario_ids.split(",") if s.strip()]
        if len(set(wanted)) != len(wanted):
            raise SystemExit("duplicate --scenario-ids are not allowed")
        missing = [s for s in wanted if s not in all_inputs]
        if missing:
            raise SystemExit(f"unknown scenario ids: {missing}")
        scenario_ids = wanted
    else:
        scenario_ids = list(all_inputs.keys())

    out_dir = Path(args.out)
    # H2091: a V2 run stopped by a terminal provider-authority failure must not
    # be resumed with fresh credentials to silently fill the missing cells.
    # This read-only refusal happens before the output directory is created or
    # the lock/provider is touched, so every prior byte is retained.
    if args.resume and args.transport == TRANSPORT_PRODUCTION_V2:
        prior_stop = prior_terminal_authority_stop(out_dir)
        if prior_stop is not None:
            print("refused: terminal_provider_authority_stop: prior run stopped "
                  f"early at provider code "
                  f"{prior_stop.get('terminal_provider_code')!r}; a new study/output "
                  "needs fresh reviewed design and authorization (no resume/retry)")
            return 2
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = out_dir / "events"

    calls_path = out_dir / "calls.jsonl"
    manifest_out = out_dir / "manifest.json"

    run_plan = execution_order(scenario_ids, args.repetitions, conditions)
    is_v2 = args.transport == TRANSPORT_PRODUCTION_V2
    if is_v2:
        strategy = provenance_strategy_v2()
        fingerprint = _fingerprint_v2(args.model, args.agent, conditions,
                                      args.repetitions, args.timeout, dataset,
                                      scenario_ids, len(run_plan))
    else:
        strategy = provenance_strategy(args.session_export)
        fingerprint = _fingerprint(args.model, args.agent, conditions,
                                   args.repetitions, args.timeout, dataset.dataset_id,
                                   dataset.manifest_sha256, scenario_ids,
                                   len(run_plan),
                                   provenance_strategy_id=strategy,
                                   pure_mode=args.pure)

    # Single explicit writer. The lock is removed in ``finally`` (net-unchanged on
    # any fail-closed rejection).
    lock = RunLock(out_dir)
    try:
        lock.acquire()
        existing_manifest = None
        if manifest_out.exists():
            try:
                existing_manifest = read_json(manifest_out)
            except (OSError, ValueError) as exc:
                raise LedgerError("manifest_unreadable",
                                  f"existing manifest.json is not valid JSON: {exc}")
        evidence = _evidence_exists(calls_path, raw_dir)

        if args.resume:
            if existing_manifest is None:
                raise LedgerError("resume_missing_manifest",
                                  "cannot resume without a compatible manifest.json")
            _require_compatible(existing_manifest, fingerprint)
            ledger = RunLedger.open(calls_path)
            validate_ledger_records(ledger.records, scenario_ids, conditions,
                                    args.repetitions)
            rewrite_manifest = False  # preserve prior structured evidence byte-for-byte
        else:
            if evidence:
                raise LedgerError(
                    "existing_evidence_requires_resume",
                    "output already holds evidence; pass --resume to continue it")
            if existing_manifest is not None:
                _require_compatible(existing_manifest, fingerprint)
            ledger = RunLedger.open(calls_path)
            validate_ledger_records(ledger.records, scenario_ids, conditions,
                                    args.repetitions)
            rewrite_manifest = True

        # EXP-077: a fully-covered resume needs no resolver/provider.  Rebuild
        # only a missing timing companion from the stored logs; the global files
        # stay byte-identical and no provider is constructed.
        if args.execute and args.resume and all(ledger.has(key) for key in run_plan):
            logs = ledger.merged_logs()
            global_manifest = _manifest_for_temporal_resume(
                out_dir, existing_manifest, dataset, scenario_ids, args.repetitions)
            rebuilt = _write_temporal_sidecars(
                out_dir, global_manifest, logs, only_if_missing=True)
            print(f"attempted=0 records=0 skipped={len(run_plan)} "
                  f"temporal_sidecars_rebuilt={len(rebuilt)} (no-op resume; "
                  f"provider not constructed)")
            return 0

        cli = None
        cli_version = None
        if args.execute:
            cli = capture.resolve_executable(args.cli)
            if not is_v2:
                cli_version = (args.cli_version if args.cli_version is not None
                               else capture.cli_version(cli))

        readiness_reason = (
            "primary_manifest_declared_thesis_ready" if dataset.thesis_ready else
            ("primary_manifest_valid_but_thesis_mode_not_declared"
             if dataset.is_primary else "synthetic_fixtures_not_primary"))
        manifest = {
            "task_id": "EXP-077" if is_v2 else "OC-023",
            "label": dataset.label,
            "method_version": V2_METHOD_VERSION if is_v2 else METHOD_VERSION,
            "manifest_version": V2_MANIFEST_VERSION if is_v2 else MANIFEST_VERSION,
            "evidence_level": EVIDENCE_LEVEL,
            "transport": args.transport,
            "dataset_kind": dataset.kind,
            "dataset_class": dataset.dataset_class,
            "dataset_id": dataset.dataset_id,
            "dataset_label": dataset.label,
            "dataset_payload_sha256": dataset.payload_sha256,
            "dataset_source_scope": dataset.source_scope,
            "dataset_review": dataset.review,
            "thesis_mode": dataset.thesis_mode,
            "thesis_ready": dataset.thesis_ready,
            "readiness_reason": readiness_reason,
            "accepted_primary_study": False,
            "dry_run": not args.execute,
            "requested_model_id": args.model,
            "model_display_name": (V2_MODEL_DISPLAY_NAME if is_v2
                                   else MODEL_DISPLAY_NAME),
            "model_upstream_version_verified": (
                V2_MODEL_UPSTREAM_VERSION_VERIFIED if is_v2
                else MODEL_UPSTREAM_VERSION_VERIFIED),
            "model_version_note": (V2_MODEL_VERSION_NOTE if is_v2
                                   else MODEL_VERSION_NOTE),
            "experiment_agent": args.agent,
            "provenance_strategy": strategy,
            "session_export": bool(args.session_export) if not is_v2 else False,
            "pure_mode": bool(args.pure) if not is_v2 else False,
            "conditions": list(conditions),
            "repetitions_per_case": args.repetitions,
            "scenario_ids": scenario_ids,
            "planned_denominator": len(run_plan),
            "execution_order": [{"scenario_id": s, "condition": c, "repetition": r}
                                for (s, c, r) in run_plan],
            "timeout_seconds": args.timeout,
            "max_calls": args.max_calls,
            "cli_version": cli_version,
            "cli_executable": cli,
            "cli_version_declared_ignored": (args.cli_version if is_v2 else None),
            "scenarios_manifest": str(manifest_path),
            "scenarios_manifest_sha256": dataset.manifest_sha256,
            "fingerprint": fingerprint,
            "notes": (
                [
                    "production-v2 transport: OpenCodeCliProvider.complete",
                    "no raw CLI transcript/session export is retained; the "
                    "assistant text and a whitelisted provider receipt are derived",
                    "dataset declaration is propagated explicitly; synthetic "
                    "fixtures never become primary",
                    "thesis_ready is false unless an explicit primary freeze/review "
                    "and >=20 scenarios are declared (none in this task)",
                    "hybrid arm evaluates the production domains.planning.schedule",
                ] if is_v2 else [
                    "synthetic engineering fixtures; not the original thesis dataset",
                    "thesis_mode is false; no H2 or human-study claim is made",
                    "hybrid arm evaluates the production domains.planning.schedule",
                ]),
        }
        if is_v2:
            manifest["authority_stop_policy"] = authority_stop_policy()
        if rewrite_manifest:
            write_json_atomic(manifest_out, manifest)

        if not args.execute:
            print(f"[dry-run] planned observations: {len(run_plan)} "
                  f"(model={args.model}, conditions={list(conditions)}, reps={args.repetitions})")
            for entry in run_plan:
                print(f"  {entry[0]} {entry[1]} r{entry[2]}")
            print(f"[dry-run] no model call performed. pass --execute to run. "
                  f"plan: {manifest_out}")
            return 0

        # EXP-077: a fully-covered resume needs no provider.  Rebuild only a
        # missing timing companion from the stored logs; the global files stay
        # byte-identical and no resolver/provider is constructed.

        raw_dir.mkdir(parents=True, exist_ok=True)
        executor = None
        export_executor = None
        complete = None
        if is_v2:
            # Constructs the accepted provider only; no readiness probe, process
            # or model call happens until complete() is invoked below.
            provider_config = v2_transport.build_provider_config(
                model=args.model, executable=cli, timeout=args.timeout,
                agent=args.agent)
            complete = v2_transport.make_complete(provider_config, Path(args.cwd))
        else:
            env = capture.child_environment()
            executor = default_executor(cli, model=args.model, agent=args.agent,
                                        cwd=Path(args.cwd), timeout=args.timeout,
                                        env=env, pure=args.pure)
            if args.session_export:
                export_executor = default_export_executor(
                    cli, cwd=Path(args.cwd), timeout=args.timeout, env=env)

        attempts = 0
        skipped: List[Dict[str, Any]] = []
        unattempted: List[Dict[str, Any]] = []
        stopped_early = False
        terminal_provider_code: Optional[str] = None

        for (scenario_id, condition, repetition) in run_plan:
            key = (scenario_id, condition, repetition)
            raw_path = raw_dir / f"{scenario_id}__{condition}__r{repetition}.jsonl"
            stderr_path = raw_dir / f"{scenario_id}__{condition}__r{repetition}.stderr.txt"
            if ledger.has(key):
                skipped.append({"scenario_id": scenario_id, "condition": condition,
                                "repetition": repetition, "reason": "existing_evidence_retained"})
                continue
            if stopped_early:
                unattempted.append({"scenario_id": scenario_id, "condition": condition,
                                    "repetition": repetition,
                                    "reason": "terminal_provider_authority_stop"})
                continue
            if attempts >= args.max_calls:
                unattempted.append({"scenario_id": scenario_id, "condition": condition,
                                    "repetition": repetition, "reason": "max_calls_reached"})
                continue
            prompt = prompts.build_prompt(condition, all_inputs[scenario_id])
            attempts += 1
            if is_v2:
                obs = run_v2_observation(
                    all_inputs[scenario_id], condition, repetition,
                    scenario_id=scenario_id, model=args.model, agent=args.agent,
                    dataset_id=dataset.dataset_id, dataset_kind=dataset.kind,
                    prompt=prompt, evidence_dir=raw_dir, complete=complete)
                obs.dataset_id = dataset.dataset_id
            else:
                obs = run_observation(all_inputs[scenario_id], condition, repetition,
                                      scenario_id=scenario_id, model=args.model,
                                      agent=args.agent,
                                      dataset_id=dataset.dataset_id, prompt=prompt,
                                      raw_stdout_path=raw_path,
                                      stderr_path=stderr_path,
                                      executor=executor,
                                      export_executor=export_executor)
                obs.cli_version = cli_version
            # Durable per-observation commit *before* the next call. The attempted
            # failure row keeps its normal fields; only the summary carries the
            # terminal-stop metadata.
            ledger.append(_observation_log(obs))
            print(f"  {scenario_id} {condition} r{repetition}: run_status={obs.run_status} "
                  f"provenance_ok={obs.provenance_ok} "
                  f"reason={obs.rejection_reason or obs.invalid_output_reason}")
            if is_v2:
                terminal_code = terminal_provider_authority_code(obs)
                if terminal_code is not None:
                    terminal_provider_code = terminal_code
                    remaining = [entry for entry in run_plan
                                 if entry not in ledger.records]
                    if remaining:
                        # Stop ALL later complete/provider calls. Remaining planned
                        # keys are recorded as unattempted below; no synthetic
                        # observation, usage, provenance or failed-model row is
                        # created for them.
                        stopped_early = True
                        print(f"  authority-stop: provider code={terminal_code!r}; "
                              f"{len(remaining)} later planned cell(s) unattempted")

        if ledger.new_count == 0:
            print(f"attempted={attempts} records=0 gaps=0 skipped={len(skipped)} "
                  f"unattempted={len(unattempted)} (no-op resume; nothing written)")
            return 0

        logs = ledger.merged_logs()
        manifest_scenario_ids = scenario_ids
        if args.resume and isinstance(existing_manifest, dict) \
                and isinstance(existing_manifest.get("scenario_ids"), list):
            manifest_scenario_ids = existing_manifest["scenario_ids"]
        h2_manifest = export.build_h2_manifest(
            manifest_scenario_ids, args.repetitions,
            manifest_version=(V2_MANIFEST_VERSION if is_v2 else MANIFEST_VERSION),
            dataset_kind=dataset.kind, dataset_id=dataset.dataset_id,
            label=dataset.label, thesis_mode=dataset.thesis_mode)
        write_json_atomic(out_dir / "h2_manifest.json", h2_manifest)
        records = export.build_h2_records_from_logs(logs)
        records_path = out_dir / "h2_records.jsonl"
        write_jsonl_atomic(records_path, records)

        # EXP-077 timing-only companion.  Both endpoints are regenerated from the
        # same stored logs; the original h2_manifest/h2_records are unchanged.
        temporal_records = _write_temporal_sidecars(
            out_dir, h2_manifest, logs, only_if_missing=False)

        gaps = export.export_gaps_from_logs(logs)
        summary = {
            "task_id": "EXP-077" if is_v2 else "OC-023",
            "label": dataset.label,
            "method_version": V2_METHOD_VERSION if is_v2 else METHOD_VERSION,
            "transport": args.transport,
            "dataset_kind": dataset.kind,
            "dataset_id": dataset.dataset_id,
            "thesis_mode": dataset.thesis_mode,
            "thesis_ready": dataset.thesis_ready,
            "readiness_reason": readiness_reason,
            "accepted_primary_study": False,
            "dry_run": False,
            "requested_model_id": args.model,
            "cli_version": cli_version,
            "planned_denominator": len(run_plan),
            "attempted": attempts,
            "records_written": len(records),
            "temporal_endpoint": {
                "endpoint": temporal_endpoint.TEMPORAL_ENDPOINT,
                "endpoint_method_version": (
                    temporal_endpoint.TEMPORAL_ENDPOINT_METHOD_VERSION),
                "scope": "timing_only_not_global_validity",
                "manifest": "h2_temporal_manifest.json",
                "records": "h2_temporal_records.jsonl",
                "records_written": len(temporal_records),
                "planned_denominator": len(run_plan),
                "global_validity_assessed": False,
            },
            "gaps": gaps,
            "skipped_existing": skipped,
            "unattempted": unattempted,
            "notes": [
                "Only provenance-proven observations become oc18.h2.v1 records.",
                "Unproven-provenance/provider failures remain in the denominator and "
                "are listed as gaps; nothing is retried or repaired.",
                "provider usage is preserved under provider_usage; the evaluator usage "
                "object is unknown and no aggregate is fabricated.",
                "h2_temporal_* is a timing-only companion; it is not global validity.",
                "hybrid arm evaluates the production domains.planning.schedule.",
                "this is readiness evidence, not an accepted primary study",
            ],
        }
        if is_v2:
            # H2091: the full planned denominator stays in planned_denominator;
            # unattempted cells are missing evidence, never synthetic records.
            summary["authority_stop_policy"] = authority_stop_policy()
            summary["stopped_early"] = stopped_early
            summary["terminal_provider_authority_stop"] = stopped_early
            summary["terminal_provider_code"] = terminal_provider_code
            summary["unattempted_count"] = len(unattempted)
        write_json_atomic(out_dir / "run_manifest.json", summary)
        print(f"attempted={attempts} records={len(records)} gaps={len(gaps)} "
              f"skipped={len(skipped)} unattempted={len(unattempted)}")
        print(f"records: {records_path}")
        if stopped_early:
            print(f"stopped_early=true terminal_provider_code={terminal_provider_code} "
                  f"unattempted={len(unattempted)}")
            # Failure + missing cells are durably retained; a nonterminal or
            # last-cell-only run keeps the historical exit 0.
            return 1
        return 0
    except LedgerError as exc:
        print(f"refused: {exc}")
        return 2
    finally:
        lock.release()


if __name__ == "__main__":
    raise SystemExit(main())
