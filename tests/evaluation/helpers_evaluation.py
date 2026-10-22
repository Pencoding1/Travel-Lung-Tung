"""Builders for synthetic H2/H3 manifests and records used only by tests."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

H2_SCHEMA = "oc18.h2.v1"
H3_SCHEMA = "oc18.h3.v1"


def h2_manifest(*, scenarios: Sequence[str] = ("S01",), repetitions: int = 1,
                thesis_mode: bool = False,
                conditions: Sequence[str] = ("hybrid", "llm_only"),
                label: str = "test-h2",
                manifest_version: str = "oc18.h2.test.v1") -> Dict[str, Any]:
    return {
        "manifest_version": manifest_version,
        "task": "H2",
        "label": label,
        "thesis_mode": thesis_mode,
        "paired_conditions": list(conditions),
        "repetitions_per_case": repetitions,
        "scenarios": [{"scenario_id": scenario} for scenario in scenarios],
    }


def h2_provenance(scenario_id: str, condition: str, **overrides: Any) -> Dict[str, Any]:
    provenance: Dict[str, Any] = {
        "candidate_id": f"cand-{scenario_id}",
        "route_id": f"route-{scenario_id}",
        "prompt_information_id": f"info-{scenario_id}",
        "dataset_id": "ds-synthetic-eval",
        "model_id": "synthetic-evaluator-model",
        "settings_id": "settings-v1",
        "method_instruction_hash": f"hash-{condition}",
    }
    provenance.update(overrides)
    return provenance


def h2_record(scenario_id: str, condition: str, repetition: int, *,
              run_status: str = "completed",
              plan_present: bool = True,
              empty_plan: bool = False,
              validation_status: str = "feasible",
              temporal_violation: Optional[bool] = False,
              unverifiable: bool = False,
              known_temporal_violations: Optional[int] = 0,
              violation_count_complete: bool = True,
              unknown_reasons: Optional[Sequence[str]] = None,
              provenance: Optional[Dict[str, Any]] = None,
              usage: Optional[Dict[str, Any]] = None,
              evidence_level: str = "synthetic_engineering",
              dataset_kind: str = "synthetic_fixtures",
              **secondary: Any) -> Dict[str, Any]:
    record = {
        "schema_version": H2_SCHEMA,
        "task": "H2",
        "evidence_level": evidence_level,
        "dataset_kind": dataset_kind,
        "scenario_id": scenario_id,
        "condition": condition,
        "repetition": repetition,
        "run_status": run_status,
        "plan_present": plan_present,
        "empty_plan": empty_plan,
        "validation_status": validation_status,
        "temporal_violation": temporal_violation,
        "unverifiable": unverifiable,
        "known_temporal_violations": known_temporal_violations,
        "violation_count_complete": violation_count_complete,
        "unknown_reasons": list(unknown_reasons or []),
        "provenance": provenance if provenance is not None
        else h2_provenance(scenario_id, condition),
        "usage": usage,
    }
    record.update(secondary)
    return record


def h2_provider_usage(summary: int = 10, extraction: int = 10, retrieval: int = 10,
                      final: int = 10, retries: int = 0) -> Dict[str, Any]:
    return {
        "usage_basis": "provider_tokens",
        "stages": {"summary": summary, "extraction": extraction,
                   "retrieval": retrieval, "final": final, "retries": retries},
    }


def h3_manifest(*, profiles: Sequence[str] = ("P1", "P2", "P3", "P4", "P5"),
                scenarios: Sequence[str] = ("S01",), repetitions: int = 1,
                thesis_mode: bool = False,
                conditions: Sequence[str] = ("memory_disabled", "short_term", "two_tier"),
                label: str = "test-h3",
                manifest_version: str = "oc18.h3.test.v1",
                category_truth: Optional[Dict[str, Sequence[str]]] = None,
                active_preference_truth: Optional[Dict[str, Dict[str, Sequence[str]]]] = None
                ) -> Dict[str, Any]:
    if category_truth is None:
        category_truth = {
            "p_food": ["cat_food"],
            "p_cafe": ["cat_cafe"],
            "p_museum": ["cat_museum"],
        }
    if active_preference_truth is None:
        active_preference_truth = {
            profile: {scenario: ["cat_food"] for scenario in scenarios}
            for profile in profiles
        }
    return {
        "manifest_version": manifest_version,
        "task": "H3",
        "label": label,
        "thesis_mode": thesis_mode,
        "conditions": list(conditions),
        "baseline_condition": "memory_disabled",
        "repetitions_per_case": repetitions,
        "profiles": [{"profile_id": profile} for profile in profiles],
        "scenarios": [{"scenario_id": scenario} for scenario in scenarios],
        "category_truth": {key: list(value) for key, value in category_truth.items()},
        "active_preference_truth": {
            profile: {scenario: list(categories) for scenario, categories in per_scenario.items()}
            for profile, per_scenario in active_preference_truth.items()
        },
    }


def h3_provenance(scenario_id: str, condition: str, **overrides: Any) -> Dict[str, Any]:
    provenance: Dict[str, Any] = {
        "candidate_id": f"cand-{scenario_id}",
        "route_id": f"route-{scenario_id}",
        "prompt_information_id": f"info-{scenario_id}",
        "dataset_id": "ds-synthetic-eval",
        "model_id": "synthetic-evaluator-model",
        "settings_id": "settings-v1",
        "method_instruction_hash": f"hash-{condition}",
    }
    provenance.update(overrides)
    return provenance


def h3_record(profile_id: str, scenario_id: str, condition: str, repetition: int, *,
              selected_poi_ids: Optional[Sequence[str]] = None,
              run_status: str = "completed",
              plan_present: bool = True,
              empty_plan: bool = False,
              validation_status: str = "feasible",
              unverifiable: bool = False,
              constraint_valid: Optional[bool] = True,
              usage: Optional[Dict[str, Any]] = None,
              latency_seconds: Optional[float] = 1.0,
              failure_retries: Optional[int] = 0,
              provenance: Optional[Dict[str, Any]] = None,
              evidence_level: str = "synthetic_engineering",
              dataset_kind: str = "synthetic_fixtures") -> Dict[str, Any]:
    return {
        "schema_version": H3_SCHEMA,
        "task": "H3",
        "evidence_level": evidence_level,
        "dataset_kind": dataset_kind,
        "profile_id": profile_id,
        "scenario_id": scenario_id,
        "condition": condition,
        "repetition": repetition,
        "run_status": run_status,
        "plan_present": plan_present,
        "empty_plan": empty_plan,
        "validation_status": validation_status,
        "unverifiable": unverifiable,
        "constraint_valid": constraint_valid,
        "selected_poi_ids": list(selected_poi_ids or []),
        "usage": usage if usage is not None else h3_provider_usage(),
        "latency_seconds": latency_seconds,
        "failure_retries": failure_retries,
        "provenance": provenance if provenance is not None
        else h3_provenance(scenario_id, condition),
    }


def h3_provider_usage(summary: int = 10, extraction: int = 10, retrieval: int = 10,
                      final: int = 10, retries: int = 0,
                      basis: str = "provider_tokens") -> Dict[str, Any]:
    return {
        "usage_basis": basis,
        "stages": {"summary": summary, "extraction": extraction,
                   "retrieval": retrieval, "final": final, "retries": retries},
    }
