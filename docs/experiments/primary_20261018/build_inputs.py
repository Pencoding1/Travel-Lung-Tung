"""EXP076 offline deterministic primary candidate-input builder.

Builds, from the fixed Codex design and the supplied primary snapshot only:

* ``candidate_manifest.json``  - UNFROZEN H2 candidate scenarios (P01-P20)
* ``source_binding.json``      - design/source/builder/route provenance
* ``h3_profile_candidates.json`` - UNFROZEN five synthetic profile declarations

No network, database, engine or model call is made. No runtime clock or
randomness is used, so repeated runs must be byte-identical. The builder refuses
to write if any declared source/design/route hash or candidate value does not
match the actual input.

Executor scope: this is a candidate input only. It is not frozen, not reviewed,
contains no author_expected/model output and supports no scientific result.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = ROOT / "docs" / "experiments" / "primary_20261018"

DESIGN_PATH = ROOT / "docs/project/handoffs/EXP-076/parent-case-design.json"
H3_PATH = ROOT / "docs/project/handoffs/EXP-076/parent-h3-design.json"
CORRECTION_PATH = ROOT / "docs/project/handoffs/EXP-076/parent-design-correction-1.json"
CORRECTION2_PATH = ROOT / "docs/project/handoffs/EXP-076/parent-design-correction-2.json"
MISSING_PATH = ROOT / "docs/project/handoffs/EXP-076/parent-missing-hours-poi.json"
HISTORICAL_DESIGN_PATH = (
    ROOT / "docs/project/handoffs/EXP-076/historical-initial-parent-case-design.json")
HISTORICAL_H3_PATH = (
    ROOT / "docs/project/handoffs/EXP-076/historical-initial-parent-h3-design.json")
ROUTE_PATH = ROOT / "docs/project/handoffs/EXP-074/parent-case-route-facts.json"
PAYLOAD_PATH = ROOT / "data/primary_20261016/graph_ready_v2/prepared_pois.jsonl"
RAW_PATH = ROOT / "data/primary_20261016/hcm_pois_final.geojson"

# Constants declared by the fixed design (verified against the actual files).
EXPECTED_PAYLOAD_SHA256 = "37340a8021ca7e8b37efc1053718c4c87879f95fa9937d8c53e1a0218f080dd1"
EXPECTED_RAW_SHA256 = "713b07a62cf89bd2cad9093abaad2a4c5f01e23853321764b3d66bf9f7eee43c"
EXPECTED_ROUTE_SHA256 = "4053ad9cc16364155c4e9bedc5f4a234fdbe7c6932a0bf4843c6eca513af29d7"
EXPECTED_PREPARED_RECORDS = 6367
SOURCE_AREA_LABEL = "Quan 1"

# Production hours parser (permitted production import); not a network call.
if str(ROOT / "ai_service") not in sys.path:
    sys.path.insert(0, str(ROOT / "ai_service"))
from domains.planning_adapter import parse_operation_time  # noqa: E402


class Refuse(RuntimeError):
    """A fixed input fact did not match; refuse to emit any output."""


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def json_text(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"


def at(date_str: str, minute: int) -> str:
    """Local +07:00 instant for a minute offset from an authored date.

    A 24/7 daily window is local 00:00 through the *next* local 00:00.
    """
    if minute < 0:
        raise Refuse(f"negative minute offset {minute}")
    local = date.fromisoformat(date_str) + timedelta(days=minute // 1440)
    hour, mins = divmod(minute % 1440, 60)
    return f"{local.isoformat()}T{hour:02d}:{mins:02d}:00+07:00"


def clock_minutes(clock: str) -> int:
    hour, minute = (int(part) for part in clock.split(":"))
    return hour * 60 + minute


def load_prepared(path: Path) -> Dict[str, dict]:
    records: Dict[str, dict] = {}
    order: List[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        poi_id = record.get("id")
        if not isinstance(poi_id, str) or not poi_id:
            raise Refuse("prepared record without a string id")
        if poi_id in records:
            raise Refuse(f"duplicate prepared record id {poi_id!r}")
        records[poi_id] = record
        order.append(poi_id)
    if len(order) != EXPECTED_PREPARED_RECORDS:
        raise Refuse(
            f"prepared payload has {len(order)} records, expected {EXPECTED_PREPARED_RECORDS}")
    return records


def lineage_hash(record: Mapping[str, Any]) -> str:
    raw = record["source_metadata"]["raw_lineage_json"]
    if not isinstance(raw, str) or not raw:
        raise Refuse(f"record {record.get('id')!r} has no raw_lineage_json")
    return sha256_bytes(raw.encode("utf-8"))


def source_projection(record: Mapping[str, Any], dates: Sequence[str]) -> Tuple[List[dict], str, Any]:
    """Project the documented source hours string onto authored dates."""
    raw = record.get("operation_time")
    parsed = parse_operation_time(raw)
    if parsed.status in ("absent", "unsupported"):
        return [], parsed.status, raw
    if parsed.status == "always_open":
        windows = [
            {"day_id": f"d{index + 1}", "start": at(day_date, 0),
             "end": at(day_date, 24 * 60)}
            for index, day_date in enumerate(dates)
        ]
        return windows, parsed.status, raw
    if parsed.status == "daily_window":
        start = clock_minutes(parsed.start_hm)
        end = clock_minutes(parsed.end_hm)
        if not 0 <= start < end <= 24 * 60:
            raise Refuse(f"unexpected parsed hours span for {record.get('id')!r}")
        windows = [
            {"day_id": f"d{index + 1}", "start": at(day_date, start),
             "end": at(day_date, end)}
            for index, day_date in enumerate(dates)
        ]
        return windows, parsed.status, raw
    raise Refuse(f"unknown parser status {parsed.status!r} for {record.get('id')!r}")


def verify_route_universe(facts: Mapping[str, Any], pool_ids: Sequence[str]) -> Dict[Tuple[str, str, str], dict]:
    attempts = facts.get("attempts")
    if not isinstance(attempts, list):
        raise Refuse("route facts have no attempts list")
    index: Dict[Tuple[str, str, str], dict] = {}
    for entry in attempts:
        key = (entry.get("profile_requested"), entry.get("from_poi_id"),
               entry.get("to_poi_id"))
        if key in index:
            raise Refuse(f"duplicate route attempt {key}")
        if entry.get("status") != "success" or entry.get("http_status") != 200:
            raise Refuse(f"route attempt is not an actual HTTP 200 success: {key}")
        if key[1] == key[2]:
            raise Refuse(f"self route attempt {key}")
        if key[0] not in ("car", "foot"):
            raise Refuse(f"unexpected route profile {key[0]!r}")
        if not isinstance(entry.get("response_sha256"), str) \
                or len(entry["response_sha256"]) != 64:
            raise Refuse(f"route attempt without a response hash: {key}")
        index[key] = entry
    for mode in ("car", "foot"):
        expected = {(mode, from_id, to_id)
                    for from_id in pool_ids for to_id in pool_ids if from_id != to_id}
        actual = {key for key in index if key[0] == mode}
        if actual != expected:
            raise Refuse(
                f"{mode} route universe mismatch: missing {len(expected - actual)}, "
                f"extra {len(actual - expected)}")
    if len(attempts) != 112:
        raise Refuse(f"route facts have {len(attempts)} attempts, expected 112")
    return index


def build_route_edges(spec: Mapping[str, Any], index: Mapping[Tuple[str, str, str], dict]) -> List[dict]:
    mode = spec["transport_mode"]
    ids = list(spec["candidate_ids"])
    edges: List[dict] = []
    for from_id in ids:
        for to_id in ids:
            if from_id == to_id:
                continue
            ref = index.get((mode, from_id, to_id))
            if ref is None:
                raise Refuse(
                    f"{spec['scenario_id']} has no actual {mode} route "
                    f"{from_id}->{to_id}")
            raw_seconds = ref.get("adapter_nearest_integer_seconds")
            raw_meters = ref.get("adapter_integer_meters")
            minutes = ref.get("adapter_duration_minutes")
            distance = ref.get("adapter_distance_km")
            if not isinstance(raw_seconds, int) or raw_seconds < 0:
                raise Refuse(f"bad raw duration for {mode} {from_id}->{to_id}")
            if not isinstance(raw_meters, int) or raw_meters < 0:
                raise Refuse(f"bad raw distance for {mode} {from_id}->{to_id}")
            if not isinstance(minutes, int) or minutes != (raw_seconds + 59) // 60:
                raise Refuse(f"duration quantization mismatch for {mode} {from_id}->{to_id}")
            if not isinstance(distance, str) or Decimal(distance) * 1000 != raw_meters:
                raise Refuse(f"distance quantization mismatch for {mode} {from_id}->{to_id}")
            if not isinstance(ref.get("original_GH_distance_meters"), (int, float)):
                raise Refuse(f"missing original GH distance for {mode} {from_id}->{to_id}")
            if not isinstance(ref.get("original_GH_time_ms"), int):
                raise Refuse(f"missing original GH time for {mode} {from_id}->{to_id}")
            provenance = (
                "actual GraphHopper11.1 successful directed loopback response; "
                f"profile={mode}; route_snapshot_sha256={EXPECTED_ROUTE_SHA256}; "
                f"response_sha256={ref['response_sha256']}"
            )
            edges.append({
                "from_poi_id": from_id,
                "to_poi_id": to_id,
                "duration_minutes": minutes,
                "distance_km": distance,
                "transport_mode": mode,
                "provenance": provenance,
                "raw_duration_seconds": raw_seconds,
                "raw_distance_meters": raw_meters,
            })
    expected = len(ids) * (len(ids) - 1)
    if len(edges) != expected:
        raise Refuse(f"{spec['scenario_id']} route count {len(edges)} != {expected}")
    return edges


def build_case(
        spec: Mapping[str, Any],
        records: Mapping[str, dict],
        route_index: Mapping[Tuple[str, str, str], dict],
        design_sha: str,
        route_pool: Mapping[str, dict],
        extra: Mapping[str, Any],
) -> Tuple[dict, dict]:
    sid = spec["scenario_id"]
    dates = list(spec["dates"])
    ids = list(spec["candidate_ids"])
    if len(set(ids)) != len(ids):
        raise Refuse(f"{sid} has duplicate candidate ids")

    pois: List[dict] = []
    evidence: Dict[str, dict] = {}
    for poi_id in ids:
        record = records.get(poi_id)
        if record is None:
            raise Refuse(f"{sid} candidate {poi_id!r} is absent from the prepared payload")
        meta = record.get("source_metadata") or {}
        namespace = meta.get("dataset_namespace")
        input_sha = meta.get("input_sha256")
        district = (record.get("address") or {}).get("district")
        if namespace != "hcm_primary_geojson":
            raise Refuse(f"{sid} {poi_id}: source namespace mismatch")
        if input_sha != EXPECTED_RAW_SHA256:
            raise Refuse(f"{sid} {poi_id}: source input hash mismatch")
        if district != SOURCE_AREA_LABEL:
            raise Refuse(f"{sid} {poi_id}: source area label {district!r} != {SOURCE_AREA_LABEL}")
        categories = [entry["id"] for entry in record.get("poi_categories") or []]
        if not categories:
            raise Refuse(f"{sid} {poi_id}: no source category")
        windows, status, raw_hours = source_projection(record, dates)
        lineage = lineage_hash(record)
        if poi_id in route_pool:
            pool_record = route_pool[poi_id]
            if (pool_record.get("name") != record.get("name")
                    or pool_record.get("category_ids") != categories
                    or pool_record.get("latitude") != record.get("latitude")
                    or pool_record.get("longitude") != record.get("longitude")
                    or pool_record.get("operation_time") != raw_hours
                    or pool_record.get("source_lineage_sha256") != lineage):
                raise Refuse(f"{sid} {poi_id}: prepared/route-facts source binding mismatch")
        if poi_id == extra["poi_id"]:
            if (record.get("name") != extra["name"]
                    or categories != list(extra["category_ids"])
                    or record.get("latitude") != extra["latitude"]
                    or record.get("longitude") != extra["longitude"]
                    or raw_hours is not None
                    or record.get("cost") is not None
                    or lineage != extra["source_lineage_sha256"]
                    or status != "absent"):
                raise Refuse(f"{sid} {poi_id}: missing-hours singleton binding mismatch")

        pois.append({
            "poi_id": poi_id,
            "category_ids": categories,
            "visit_minutes": spec["visit_minutes"],
            "cost": None,
            "opening_windows": windows,
        })
        evidence[poi_id] = {
            "name": record.get("name"),
            "latitude": record.get("latitude"),
            "longitude": record.get("longitude"),
            "raw_operation_time": raw_hours,
            "hours_status": status,
            "category_ids": categories,
            "source_lineage_sha256": lineage,
            "price_status": "unknown_absent_in_source",
        }
    if set(evidence) != set(ids):
        raise Refuse(f"{sid} source evidence is not a closed per-POI map")

    days: List[dict] = []
    for day_index, day_date in enumerate(dates):
        start_min = clock_minutes(spec["day_window"][0])
        end_min = clock_minutes(spec["day_window"][1])
        if not 0 <= start_min < end_min <= 24 * 60:
            raise Refuse(f"{sid} invalid authored day window")
        meals = [
            {
                "category_id": meal["category_id"],
                "start": at(day_date, clock_minutes(meal["start"])),
                "end": at(day_date, clock_minutes(meal["end"])),
            }
            for meal in spec["meal_windows"] if meal["day_index"] == day_index
        ]
        days.append({
            "day_id": f"d{day_index + 1}",
            "date": day_date,
            "window": {"start": at(day_date, start_min), "end": at(day_date, end_min)},
            "max_stops": spec["max_stops_per_day"],
            "meal_windows": meals,
        })

    scenario_input = {
        "scenario_id": sid,
        "seed": spec["seed"],
        "currency": spec["currency"],
        "party_size": spec["party_size"],
        "budget": {
            "amount": spec["budget_amount"],
            "currency": spec["currency"],
            "unit": "per_party",
        },
        "preferences": {"category_weights": dict(spec["shared_preferences"])},
        "required_categories": list(spec["required_categories"]),
        "transport_mode": spec["transport_mode"],
        "days": days,
        "pois": pois,
        "route_edges": build_route_edges(spec, route_index),
        "start_depot_id": None,
        "end_depot_id": None,
        "minimum_stops": spec["minimum_stops"],
        "allow_duplicate_pois": False,
        "source_scope": dict(spec["source_scope"]),
        "source_evidence": {
            "closed": True,
            "per_poi": evidence,
            "notes": (
                "Descriptive source snapshot fields only; prices, freshness, "
                "licence and source URL are absent. Coordinates and names are not "
                "verified current venue facts."
            ),
        },
    }
    metadata = {
        "profile": spec["profile"],
        "variant": spec["variant"],
        "design_path": "docs/project/handoffs/EXP-076/parent-case-design.json",
        "design_sha256": design_sha,
        "authored_fields": [
            "seed", "party_size", "budget", "preferences", "required_categories",
            "transport_mode", "days.window", "days.date", "days.max_stops",
            "days.meal_windows", "minimum_stops", "visit_minutes",
        ],
        "source_derived_fields": [
            "pois.poi_id", "pois.category_ids", "pois.opening_windows",
            "source_scope", "source_evidence", "route_edges",
        ],
        "unknown_fields": ["cost", "freshness", "licence", "source_url"],
        "note": (
            "Source-based candidate scenario with authored request constraints; "
            "not a verified current-venue fact and not a scientific result."
        ),
    }
    case_summary = {
        "scenario_id": sid,
        "profile": spec["profile"],
        "variant": spec["variant"],
        "transport_mode": spec["transport_mode"],
        "route_count": len(scenario_input["route_edges"]),
        "required_categories": list(spec["required_categories"]),
        "pois": [
            {
                "poi_id": poi_id,
                "source_lineage_sha256": evidence[poi_id]["source_lineage_sha256"],
                "raw_operation_time": evidence[poi_id]["raw_operation_time"],
                "hours_status": evidence[poi_id]["hours_status"],
            }
            for poi_id in ids
        ],
    }
    return {"scenario_id": sid, "input": scenario_input, "design_metadata": metadata}, case_summary


def main() -> int:
    # --- fail-closed input verification BEFORE producing outputs -------------
    payload_sha = sha256_file(PAYLOAD_PATH)
    raw_sha = sha256_file(RAW_PATH)
    route_sha = sha256_file(ROUTE_PATH)
    if payload_sha != EXPECTED_PAYLOAD_SHA256:
        raise Refuse(f"prepared payload hash {payload_sha} != declared {EXPECTED_PAYLOAD_SHA256}")
    if raw_sha != EXPECTED_RAW_SHA256:
        raise Refuse(f"raw GeoJSON hash {raw_sha} != declared {EXPECTED_RAW_SHA256}")
    if route_sha != EXPECTED_ROUTE_SHA256:
        raise Refuse(f"route snapshot hash {route_sha} != declared {EXPECTED_ROUTE_SHA256}")

    design = read_json(DESIGN_PATH)
    h3 = read_json(H3_PATH)
    correction = read_json(CORRECTION_PATH)
    correction2 = read_json(CORRECTION2_PATH)
    missing = read_json(MISSING_PATH)
    facts = read_json(ROUTE_PATH)
    design_sha = sha256_file(DESIGN_PATH)
    h3_sha = sha256_file(H3_PATH)
    correction_sha = sha256_file(CORRECTION_PATH)
    correction2_sha = sha256_file(CORRECTION2_PATH)
    if design_sha != correction2["current_design_sha256"]:
        raise Refuse("parent-case-design.json does not match correction-2 current design hash")
    if h3_sha != correction["artifacts"]["parent-h3-design.json"]["after_sha256"]:
        raise Refuse("parent-h3-design.json does not match the corrected design hash")
    if sha256_file(HISTORICAL_DESIGN_PATH) \
            != correction["artifacts"]["parent-case-design.json"]["before_sha256"]:
        raise Refuse("historical initial case design no longer matches correction-1 evidence")
    if sha256_file(HISTORICAL_H3_PATH) \
            != correction["artifacts"]["parent-h3-design.json"]["before_sha256"]:
        raise Refuse("historical initial H3 design no longer matches correction-1 evidence")
    if design.get("payload_sha256") != payload_sha:
        raise Refuse("design payload_sha256 does not match the actual prepared payload")
    if design.get("route_facts_sha256") != route_sha:
        raise Refuse("design route_facts_sha256 does not match the actual route snapshot")
    if design.get("source_scope", {}).get("input_sha256") != raw_sha:
        raise Refuse("design source_scope input_sha256 does not match the raw GeoJSON")
    if design.get("extra_poi") != "parent-missing-hours-poi.json":
        raise Refuse("design extra_poi is not the declared missing-hours file")
    if "source-category:gifts" in json.dumps(design, ensure_ascii=False):
        raise Refuse("design still contains the superseded gifts category alias")

    records = load_prepared(PAYLOAD_PATH)
    facts_pool = {entry["poi_id"]: entry for entry in facts.get("pool") or []}
    if len(facts_pool) != 8:
        raise Refuse(f"route facts pool has {len(facts_pool)} POIs, expected 8")
    route_index = verify_route_universe(facts, list(facts_pool))
    if facts.get("input_payload_sha256") != payload_sha:
        raise Refuse("route facts input_payload_sha256 does not match prepared payload")
    if facts.get("source_scope") != design["source_scope"]:
        raise Refuse("route facts source_scope does not match design source_scope")

    specs = design["case_specs"]
    if not isinstance(specs, list) or len(specs) != 20:
        raise Refuse("design does not declare exactly 20 cases")
    scenario_ids = [spec["scenario_id"] for spec in specs]
    if len(set(scenario_ids)) != 20 or scenario_ids != [f"P{i:02d}" for i in range(1, 21)]:
        raise Refuse("design scenario ids are not exactly P01..P20 in order")

    scenarios: List[dict] = []
    case_summaries: List[dict] = []
    for spec in specs:
        spec = dict(spec)
        spec["shared_preferences"] = design["shared_preferences"]
        spec["source_scope"] = design["source_scope"]
        scenario, summary = build_case(
            spec, records, route_index, design_sha, facts_pool, missing)
        scenarios.append(scenario)
        case_summaries.append(summary)

    # Exact dimension balance required by the fixed design (10 at each marginal).
    dimension_fields = {
        "day_count": [len(spec["dates"]) for spec in specs],
        "transport_mode": [spec["transport_mode"] for spec in specs],
        "visit_minutes": [spec["visit_minutes"] for spec in specs],
        "budget_amount": [spec["budget_amount"] for spec in specs],
    }
    dimensions: Dict[str, Dict[str, int]] = {}
    for name, values in dimension_fields.items():
        counts = Counter(str(value) for value in values)
        dimensions[name] = dict(sorted(counts.items()))
        if sorted(counts.values()) != [10, 10]:
            raise Refuse(f"dimension {name} is not balanced 10/10: {dimensions[name]}")
    profile_counts = Counter(spec["profile"] for spec in specs)
    dimensions["profile"] = dict(sorted(profile_counts.items()))
    if sorted(profile_counts.values()) != [4, 4, 4, 4, 4]:
        raise Refuse(f"profile balance is not 5x4: {dimensions['profile']}")

    manifest = {
        "manifest_version": "exp076.primary.candidate.v1",
        "label": (
            "UNFROZEN primary snapshot scenarios with authored request constraints; "
            "not verified current venues and not a scientific result"
        ),
        "dataset_kind": "real_supplied_primary_snapshot",
        "dataset_class": "real_supplied_primary_snapshot",
        "dataset_id": "primary:hcm_primary_geojson:exp076-candidate-v1",
        "payload_sha256": payload_sha,
        "source_scope": dict(design["source_scope"]),
        "frozen": False,
        "thesis_mode": False,
        "review": {
            "decision": "pending_codex_review",
            "note": (
                "Executor-produced candidate input. Codex independent source-binding, "
                "temporal feasibility and contract review are pending."
            ),
        },
        "design": {
            "author": design.get("author"),
            "task": design.get("task"),
            "path": "docs/project/handoffs/EXP-076/parent-case-design.json",
            "sha256": design_sha,
            "correction_path": "docs/project/handoffs/EXP-076/parent-design-correction-1.json",
            "correction_sha256": correction_sha,
            "correction2_path": "docs/project/handoffs/EXP-076/parent-design-correction-2.json",
            "correction2_sha256": correction2_sha,
        },
        "limitations": {
            "costs": (
                "Every POI cost is null: the source contains no prices. Budget levels are "
                "authored constraints and no budget effect or global budget feasibility "
                "is identifiable."
            ),
            "hours": (
                "Opening windows project documented source daily strings (or 24/7) onto "
                "authored counterfactual dates in +07:00; this is not fresh verification "
                "that a venue is open on those dates. Absent/unsupported source hours "
                "stay empty (unknown), never 'always open'."
            ),
            "freshness": (
                "Collection time, freshness, licence, source URL and rating are absent "
                "in the supplied snapshot and are not invented."
            ),
            "sampling": (
                "Purposive eight-POI supported-hours pool plus one exact missing-hours "
                "singleton; not representative of all 6367 prepared records or current "
                "venues. P20's empty selected pool is an authored stress test, not "
                "evidence that the source has no POIs."
            ),
            "design": (
                "Five profiles x four variants with ten cases at each marginal level of "
                "day count, mode, visit length and budget; not a full factorial and not "
                "an isolated-factor causal design. Factors are confounded."
            ),
            "multi_day": (
                "Production multi-day semantics carry the last scheduled POI as the "
                "next-day origin and charge directed inbound travel after the new day "
                "start; an empty day preserves the origin. The candidate input supplies "
                "only the actual directed pair matrix for the selected IDs; every "
                "cross-day leg is looked up from that same actual matrix, never "
                "invented. No accommodation, hotel or traffic model is assumed."
            ),
            "status": (
                "Unfrozen candidate input. It is not an accepted study, contains no model "
                "outputs or expected outcomes, and supports no H2/H3 finding."
            ),
        },
        "scenarios": scenarios,
    }

    candidate_categories = {
        poi_id: [entry["id"] for entry in records[poi_id].get("poi_categories") or []]
        for poi_id in h3["candidate_ids"]
    }
    if set(candidate_categories) != set(h3["candidate_ids"]):
        raise Refuse("H3 candidate IDs are not all bound to prepared source records")
    profiles_out: List[dict] = []
    for profile in h3["profiles"]:
        preferred = list(profile["preferred_category_ids"])
        matches = sorted(
            poi_id for poi_id, categories in candidate_categories.items()
            if set(preferred) & set(categories)
        )
        if not matches:
            raise Refuse(
                f"profile {profile['profile_id']} preferences do not intersect source categories")
        profiles_out.append({
            "profile_id": profile["profile_id"],
            "synthetic": True,
            "preferred_category_ids": preferred,
            "initial_profile": dict(profile["initial_profile"]),
            "unknown_preferences": list(profile["unknown_preferences"]),
            "matching_candidate_ids": matches,
        })

    h3_manifest = {
        "kind": "h3_profile_candidates",
        "task": "EXP076",
        "author": h3.get("author"),
        "frozen": False,
        "candidate_status": "unfrozen_profile_declarations_no_results",
        "design_path": "docs/project/handoffs/EXP-076/parent-h3-design.json",
        "design_sha256": h3_sha,
        "correction_path": "docs/project/handoffs/EXP-076/parent-design-correction-1.json",
        "correction_sha256": correction_sha,
        "profiles": profiles_out,
        "conditions": list(h3["conditions"]),
        "shared_request": h3["shared_request"],
        "candidate_ids": list(h3["candidate_ids"]),
        "candidate_categories": candidate_categories,
        "required_lifecycle": list(h3["required_lifecycle"]),
        "profiles_are_synthetic": True,
        "not_human_participants": True,
        "profile_declarations_are_not_h3_results": True,
        "no_experiment_results": True,
        "execution_design_status": (
            "Profile/category declarations only. Matched HTTP lifecycle controls "
            "(preference update, contradiction, session restart, delete, unknown "
            "preference) and full-cost accounting design are not yet approved; no "
            "live H3 run is authorized by this file."
        ),
        "limitations": [
            "Profiles are synthetic fixtures, not humans and not H1 participants.",
            "Preferred categories are source category IDs; matching just proves the "
            "declared category exists in the supplied candidate pool.",
            "No memory system was executed and no H3 effect or lifecycle correctness "
            "is claimed.",
            "Lifetime/HTTP protocol and auxiliary model-call cost coverage remain "
            "unapproved and unfrozen.",
        ],
    }

    manifest_text = json_text(manifest)
    h3_text = json_text(h3_manifest)
    manifest_sha = sha256_bytes(manifest_text.encode("utf-8"))
    h3_sha_out = sha256_bytes(h3_text.encode("utf-8"))

    original_measurements = {}
    for entry in facts["attempts"]:
        key = f"{entry['profile_requested']}|{entry['from_poi_id']}|{entry['to_poi_id']}"
        original_measurements[key] = {
            "original_GH_distance_meters": entry["original_GH_distance_meters"],
            "original_GH_time_ms": entry["original_GH_time_ms"],
            "response_sha256": entry["response_sha256"],
        }

    source_binding = {
        "kind": "exp076_candidate_input_source_binding",
        "task": "EXP076",
        "author": "Codex design; OpenCode source binding",
        "frozen": False,
        "design": {
            "case_design_path": "docs/project/handoffs/EXP-076/parent-case-design.json",
            "case_design_sha256": design_sha,
            "h3_design_path": "docs/project/handoffs/EXP-076/parent-h3-design.json",
            "h3_design_sha256": h3_sha,
            "historical_initial_case_design_path": (
                "docs/project/handoffs/EXP-076/"
                "historical-initial-parent-case-design.json"),
            "historical_initial_case_design_sha256": sha256_file(HISTORICAL_DESIGN_PATH),
            "historical_initial_h3_design_path": (
                "docs/project/handoffs/EXP-076/"
                "historical-initial-parent-h3-design.json"),
            "historical_initial_h3_design_sha256": sha256_file(HISTORICAL_H3_PATH),
            "correction_path": (
                "docs/project/handoffs/EXP-076/parent-design-correction-1.json"),
            "correction_sha256": correction_sha,
            "correction_cause": correction.get("cause"),
            "correction_before_any_model_experiment": correction.get(
                "before_any_model_experiment"),
            "correction2_path": (
                "docs/project/handoffs/EXP-076/parent-design-correction-2.json"),
            "correction2_sha256": correction2_sha,
            "correction2_cause": correction2.get("cause"),
            "correction2_classification": correction2.get("classification"),
            "correction2_before_model_scoring": correction2.get("before_model_scoring"),
            "correction2_case_constraints_changed": correction2.get(
                "case_constraints_changed"),
            "correction2_source_facts_changed": correction2.get(
                "source_facts_changed"),
            "corrected_gift_category": "hcm_primary_geojson:source-category:apparel_and_gifts",
            "superseded_gifts_alias_absent": "source-category:gifts" not in json.dumps(
                [manifest, h3_manifest], ensure_ascii=False),
            "payload_sha256_matches": design.get("payload_sha256") == payload_sha,
            "route_facts_sha256_matches": design.get("route_facts_sha256") == route_sha,
            "source_scope_matches": design.get("source_scope", {}).get(
                "input_sha256") == raw_sha,
            "multi_day_semantics": design.get("multi_day"),
        },
        "source": {
            "raw_geojson": {
                "path": "data/primary_20261016/hcm_pois_final.geojson",
                "sha256": raw_sha,
                "expected_sha256": EXPECTED_RAW_SHA256,
                "verified": raw_sha == EXPECTED_RAW_SHA256,
                "bytes": RAW_PATH.stat().st_size,
            },
            "prepared_payload": {
                "path": "data/primary_20261016/graph_ready_v2/prepared_pois.jsonl",
                "sha256": payload_sha,
                "expected_sha256": EXPECTED_PAYLOAD_SHA256,
                "verified": payload_sha == EXPECTED_PAYLOAD_SHA256,
                "record_count": len(records),
            },
            "source_scope": dict(design["source_scope"]),
            "source_area_label_used": SOURCE_AREA_LABEL,
            "source_area_label_scope": (
                "source snapshot label only; not a verified current administrative boundary"),
        },
        "builder": {
            "path": "docs/experiments/primary_20261018/build_inputs.py",
            "sha256": sha256_file(Path(__file__).resolve()),
            "runtime_clock_used": False,
            "randomness_used": False,
            "network_calls": 0,
            "model_calls": 0,
            "database_calls": 0,
            "production_imports": ["domains.planning_adapter.parse_operation_time"],
            "generated_artifact_hashes": {
                "candidate_manifest.json": manifest_sha,
                "h3_profile_candidates.json": h3_sha_out,
            },
        },
        "route_provenance": {
            "path": "docs/project/handoffs/EXP-074/parent-case-route-facts.json",
            "sha256": route_sha,
            "expected_sha256": EXPECTED_ROUTE_SHA256,
            "verified": route_sha == EXPECTED_ROUTE_SHA256,
            "engine": "GraphHopper11.1",
            "engine_jar_sha256": facts["engine"].get("jar_sha256"),
            "engine_pbf_sha256": facts["engine"].get("pbf_sha256"),
            "planning_adapter_sha256": facts.get("planning_adapter_sha256"),
            "route_successes": facts.get("route_successes"),
            "attempt_count": len(facts.get("attempts") or []),
            "route_request_limit": facts.get("route_request_limit"),
            "requests_per_directed_pair_profile": facts.get(
                "requests_per_directed_pair_profile"),
            "retry_limit": facts.get("retry_limit"),
            "profiles": {"car": {"pairs": 56}, "foot": {"pairs": 56}},
            "quantization": facts.get("quantization"),
            "provenance": (
                "direct GraphHopper loopback GET only; no reverse/self edge inference, "
                "no synthetic edge, no model/engine call in this build"),
            "original_gh_measurements": original_measurements,
        },
        "dimensions": dimensions,
        "cases": case_summaries,
        "case_route_count_total": sum(case["route_count"] for case in case_summaries),
        "field_provenance": {
            "poi_id": "exact prepared payload record id (internal local identity)",
            "category_ids": "exact source poi_categories ids in source order",
            "visit_minutes": (
                "authored scenario assumption by pace profile; not a measured venue fact"),
            "opening_windows": (
                "projection of production parse_operation_time over authored dates; "
                "24/7 becomes local 00:00 through next-day 00:00; absent/unsupported "
                "source hours remain empty/unknown"),
            "cost": "always null; source price absent and never inferred as zero",
            "budget": (
                "authored per_party VND request; not a source price and not evidence "
                "of budget feasibility"),
            "days.date": "authored counterfactual itinerary date, not freshness evidence",
            "days.window": "authored request window with explicit +07:00 offset",
            "days.max_stops": "authored request",
            "days.meal_windows": "authored request only on declared day_index",
            "minimum_stops": "authored request",
            "required_categories": "authored request using exact source category ids",
            "transport_mode": "authored single mode for all route edges in a scenario",
            "route_edges": (
                "actual successful directed GraphHopper responses for the exact selected "
                "pair and mode; no self edge, no reverse inference. Every cross-day leg "
                "is looked up from this same actual matrix using production multi-day "
                "semantics (prior last POI is the next-day origin); no inter-day edge is "
                "invented and no hotel/accommodation model is assumed"),
            "multi_day": (
                "Production contract: carry the last scheduled POI as next-day origin; "
                "an empty day preserves the origin; charge directed inbound travel after "
                "the new day start. No accommodation or traffic model, no invented route."),
            "route_edges.duration_minutes": (
                "adapter_duration_minutes; equals ceil(adapter_nearest_integer_seconds/60)"),
            "route_edges.distance_km": (
                "adapter_distance_km decimal string derived from nearest integer metres"),
            "route_edges.raw_duration_seconds": "adapter_nearest_integer_seconds",
            "route_edges.raw_distance_meters": "adapter_integer_meters",
            "route_edges.provenance": (
                "binds the full route snapshot SHA-256 and the exact response SHA-256"),
            "source_scope": "exact explicit frozen source selection from the design",
            "source_evidence": (
                "descriptive source name/coordinates/raw hours/category/lineage; price "
                "status explicitly unknown"),
        },
        "artifacts": {
            "candidate_manifest": {
                "path": "docs/experiments/primary_20261018/candidate_manifest.json",
                "sha256": manifest_sha,
            },
            "h3_profile_candidates": {
                "path": "docs/experiments/primary_20261018/h3_profile_candidates.json",
                "sha256": h3_sha_out,
            },
        },
        "limitations": [
            "All source prices, freshness, licence and source URL values are absent.",
            "Hours are source-string projections on authored future dates, not fresh checks.",
            "The eight-POI pool is purposive, not a population sample; P20 is a stress test.",
            "Factors are confounded; no isolated mode/pace/budget effect is identifiable.",
            "Multi-day travel follows production carry-origin semantics; no hotel, "
            "accommodation, traffic or overnight-verification claim is made.",
            "The candidate is unfrozen and has not been independently reviewed or accepted.",
        ],
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "candidate_manifest.json").write_bytes(manifest_text.encode("utf-8"))
    (OUT_DIR / "source_binding.json").write_bytes(
        json_text(source_binding).encode("utf-8"))
    (OUT_DIR / "h3_profile_candidates.json").write_bytes(h3_text.encode("utf-8"))

    print(json.dumps({
        "status": "written_unfrozen_candidate",
        "scenarios": len(scenarios),
        "route_edges": source_binding["case_route_count_total"],
        "manifest_sha256": manifest_sha,
        "h3_sha256": h3_sha_out,
        "model_calls": 0,
        "network_calls": 0,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
