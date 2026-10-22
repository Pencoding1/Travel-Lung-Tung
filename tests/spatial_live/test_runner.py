"""Offline EXP089 collector tests.

These tests use only an in-memory fake database and a fake clock.  They never
construct the real Neo4j driver, never open a socket and never contact the
loopback runtime.  Any pair sets produced here are synthetic engineering
fixtures, not primary or live-engine observations.
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from benchmarks.spatial_live import runner  # noqa: E402


# ---------------------------------------------------------------------------
# Reference fixtures and fake engine
# ---------------------------------------------------------------------------


def make_raw_record(
    poi_id: str,
    latitude: float,
    longitude: float,
    *,
    city: str = "HCMC",
    district: str = "Quan 1",
) -> dict:
    lineage = json.dumps(
        {"address": {"raw_city": city, "raw_district": district}},
        ensure_ascii=False,
    )
    return {
        "id": poi_id,
        "latitude": latitude,
        "longitude": longitude,
        "source_metadata": {
            "dataset_namespace": "hcm_primary_geojson",
            "input_sha256": "a" * 64,
            "raw_lineage_json": lineage,
            "raw_lineage_sha256": hashlib.sha256(lineage.encode("utf-8")).hexdigest(),
        },
    }


def write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    return path


def make_world(tmp_path: Path, rows: list[dict], name: str = "input.jsonl"):
    path = write_jsonl(tmp_path / name, rows)
    records, digest = runner.load_records(path)
    return path, records, digest


def make_manifest(
    input_path: Path,
    records: list[runner.PoiRecord],
    *,
    frozen: bool = True,
    reviewer: str = "offline-test-reviewer",
) -> dict:
    manifest = runner.build_manifest(records, input_path)
    manifest["frozen"] = frozen
    manifest["review"] = {
        "decision": "approved" if frozen else "pending",
        "reviewer": reviewer if frozen else None,
    }
    return manifest


def write_manifest(path: Path, manifest: dict) -> Path:
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path


def reference_haversine_m(lat1, lon1, lat2, lon2) -> float:
    radius = 6_371_000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2.0) ** 2
    )
    a = min(1.0, max(0.0, a))
    return radius * 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


class CodedAuthError(Exception):
    """Synthetic installed-driver exception with a public exact ``.code``."""

    def __init__(self, code: str, message: str = "raw-auth-diagnostic") -> None:
        super().__init__(message)
        self.code = code


class AuthError(Exception):
    """Synthetic explicit driver exception class (no ``.code``)."""


class AuthConfigurationError(Exception):
    """Synthetic explicit driver exception class (no ``.code``)."""


class Forbidden(Exception):
    """Synthetic explicit driver exception class (no ``.code``)."""


def reference_prefilter(lat1, lon1, lat2, lon2, radius_km) -> bool:
    delta_lat = min(180.0, math.degrees(radius_km / 6300.0))
    if abs(lat1 - lat2) > delta_lat:
        return False
    band_max = max(abs(lat1), abs(lat2)) + delta_lat
    if band_max >= 90.0:
        delta_lon = 180.0
    else:
        cosine = math.cos(math.radians(band_max))
        delta_lon = 180.0 if cosine <= 0.0 else min(180.0, delta_lat / cosine)
    raw = abs(lon1 - lon2)
    wrapped = 360.0 - raw if raw > 180.0 else raw
    return wrapped <= delta_lon


class FakeBackend:
    """Deterministic fake database with optional scripted failures/overrides."""

    def __init__(
        self,
        records: list[runner.PoiRecord],
        *,
        baseline_override=None,
        optimized_override=None,
        candidate_override=None,
        timing_override=None,
        timing_overrides: dict | None = None,
        fail_names: set[str] | None = None,
        fail_on_query_number: int | None = None,
        fail_exceptions: dict | None = None,
        fail_query_numbers: dict | None = None,
        projection_mutator=None,
        extra_poi_count: int = 0,
        index_rows: list[dict] | None = None,
    ) -> None:
        self.records = {record.id: record for record in records}
        self.baseline_override = baseline_override
        self.optimized_override = optimized_override
        self.candidate_override = candidate_override
        self.timing_override = timing_override
        self.timing_overrides = dict(timing_overrides or {})
        self.fail_names = set(fail_names or ())
        self.fail_on_query_number = fail_on_query_number
        self.fail_exceptions = dict(fail_exceptions or {})
        self.fail_query_numbers = dict(fail_query_numbers or {})
        self.projection_mutator = projection_mutator
        self.extra_poi_count = extra_poi_count
        self.index_rows = index_rows if index_rows is not None else [
            {"index type": "label", "label": "POI", "property": "id"}
        ]
        self.calls: list[str] = []
        self.call_texts: list[tuple[str, str]] = []
        self.closed = False

    def run_query(self, name, text, params, timeout_seconds):
        runner.assert_allowed_query(text)
        self.calls.append(name)
        self.call_texts.append((name, text))
        if len(self.calls) in self.fail_query_numbers:
            raise self.fail_query_numbers[len(self.calls)]
        if self.fail_on_query_number is not None and len(self.calls) >= self.fail_on_query_number:
            raise RuntimeError("password=hunter2 secret-shaped diagnostic")
        if name in self.fail_exceptions:
            raise self.fail_exceptions[name]
        if name in self.fail_names:
            raise RuntimeError("password=hunter2 secret-shaped diagnostic")

        if name == "projection":
            rows = []
            for poi_id in params["ids"]:
                record = self.records[poi_id]
                rows.append(
                    {
                        "id": record.id,
                        "latitude": record.latitude,
                        "longitude": record.longitude,
                        "source_area_id": record.source_area_id,
                        "input_sha256": record.source_metadata["input_sha256"],
                        "dataset_namespace": record.source_metadata[
                            "dataset_namespace"
                        ],
                        "metadata_sha256": record.metadata_sha256,
                    }
                )
            if self.projection_mutator is not None:
                rows = self.projection_mutator(rows)
            return rows

        if name == "out_of_universe":
            return [{"extra_poi_count": self.extra_poi_count}]

        if name == "scoped_counts":
            return [
                {
                    "poi_count": len(params["ids"]),
                    "distinct_poi_ids": len(params["ids"]),
                }
            ]

        if name == "materialization":
            return [
                {
                    "directed_edges": 0,
                    "canonical_directed_edges": 0,
                    "noncanonical_or_self_directed_edges": 0,
                }
            ]

        if name == "index_info":
            return self.index_rows

        if name in ("timing_baseline", "timing_optimized"):
            override = self.timing_overrides.get(name, self.timing_override)
            if override is not None:
                return override(params) if callable(override) else override
            radius = float(params["radius_km"])
            optimized = name == "timing_optimized"
            count = 0
            for anchor in params["anchors"]:
                first = self.records[anchor]
                for other_id in params["ids"]:
                    if not anchor < other_id:
                        continue
                    second = self.records[other_id]
                    if optimized and not reference_prefilter(
                        first.latitude,
                        first.longitude,
                        second.latitude,
                        second.longitude,
                        radius,
                    ):
                        continue
                    distance = reference_haversine_m(
                        first.latitude,
                        first.longitude,
                        second.latitude,
                        second.longitude,
                    )
                    if distance <= radius * 1000.0:
                        count += 1
            return [{"accepted_pairs": count}]

        if name in ("baseline", "optimized", "candidates"):
            override = {
                "baseline": self.baseline_override,
                "optimized": self.optimized_override,
                "candidates": self.candidate_override,
            }[name]
            if override is not None:
                return override(params) if callable(override) else override
            radius = float(params["radius_km"])
            anchors = params["anchors"]
            ids = params["ids"]
            if name == "candidates":
                count = 0
                for anchor in anchors:
                    first = self.records[anchor]
                    for other_id in ids:
                        if not anchor < other_id:
                            continue
                        second = self.records[other_id]
                        if reference_prefilter(
                            first.latitude,
                            first.longitude,
                            second.latitude,
                            second.longitude,
                            radius,
                        ):
                            count += 1
                return [{"candidate_pairs": count}]

            rows = []
            for anchor in anchors:
                first = self.records[anchor]
                for other_id in ids:
                    if not anchor < other_id:
                        continue
                    second = self.records[other_id]
                    if name == "optimized" and not reference_prefilter(
                        first.latitude,
                        first.longitude,
                        second.latitude,
                        second.longitude,
                        radius,
                    ):
                        continue
                    distance = reference_haversine_m(
                        first.latitude,
                        first.longitude,
                        second.latitude,
                        second.longitude,
                    )
                    if distance <= radius * 1000.0:
                        rows.append(
                            {"a_id": anchor, "b_id": other_id, "distance_m": distance}
                        )
            return rows

        raise AssertionError(f"unexpected fake query name: {name}")

    def close(self) -> None:
        self.closed = True


class FakeClock:
    def __init__(self, step: float = 0.25, start: float = 1_000.0) -> None:
        self.step = step
        self.value = start
        self.calls = 0

    def __call__(self) -> float:
        self.calls += 1
        current = self.value
        self.value += self.step
        return current


class FixedUtc:
    def __init__(self) -> None:
        self.value = datetime(2026, 10, 19, 12, 0, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        current = self.value
        self.value += timedelta(seconds=1)
        return current


def execute_world(
    tmp_path: Path,
    input_path: Path,
    backend: FakeBackend,
    *,
    manifest: dict | None = None,
    output_name: str = "result.json",
):
    records, _ = runner.load_records(input_path)
    if manifest is None:
        manifest = make_manifest(input_path, records)
    manifest_path = write_manifest(tmp_path / "manifest.json", manifest)
    output_path = tmp_path / output_name
    result = runner.execute_collection(
        input_path,
        manifest_path,
        output_path,
        backend_factory=lambda: backend,
        clock=FakeClock(),
        on_utc=FixedUtc(),
    )
    return result, output_path


def assert_code(callable_obj, code: str) -> None:
    with pytest.raises(runner.CollectorError) as caught:
        callable_obj()
    assert caught.value.code == code


# ---------------------------------------------------------------------------
# A. Dry-run and manifest gates before any driver
# ---------------------------------------------------------------------------


def test_default_dry_run_plan_is_zero_engine_and_only_a_plan(tmp_path, monkeypatch, capsys):
    input_path, records, digest = make_world(
        tmp_path,
        [
            make_raw_record("hcm_primary_geojson_internal:00000000000000000000000000000001", 10.0, 106.0),
            make_raw_record("hcm_primary_geojson_internal:00000000000000000000000000000002", 10.1, 106.1),
        ],
    )

    def bomb():
        raise AssertionError("dry-run must not import or construct a driver")

    monkeypatch.setattr(runner, "_load_neo4j", bomb)
    exit_code = runner.main(
        ["--input", str(input_path)],
        backend_factory=bomb,
        on_utc=FixedUtc(),
    )
    assert exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["status"] == "dry_run_plan"
    assert plan["mode"] == "dry_run"
    assert plan["plan_only"] is True
    assert plan["scientific_result"] is False
    assert plan["latency_measured"] is False
    assert "timings" not in plan
    assert plan["input"]["is_full_primary"] is False
    assert plan["planned"]["timing_cells_total"] == 36
    assert plan["candidate_manifest"]["frozen"] is False
    assert plan["candidate_manifest"]["review"]["decision"] == "pending"
    assert plan["model_calls"] == 0
    assert plan["graph_mutation"] is False


def test_unfrozen_manifest_fails_before_backend_factory(tmp_path):
    input_path, records, _ = make_world(
        tmp_path,
        [make_raw_record("a", 10.0, 106.0), make_raw_record("b", 10.001, 106.001)],
    )
    manifest = make_manifest(input_path, records, frozen=False)
    manifest_path = write_manifest(tmp_path / "manifest.json", manifest)
    output_path = tmp_path / "result.json"
    factory_called = []

    def factory():
        factory_called.append(True)
        return FakeBackend(records)

    exit_code = runner.main(
        [
            "--execute",
            "--input",
            str(input_path),
            "--manifest",
            str(manifest_path),
            "--output",
            str(output_path),
        ],
        backend_factory=factory,
        on_utc=FixedUtc(),
    )
    assert exit_code == 2
    assert factory_called == []
    assert not output_path.exists()


def test_hash_drift_rejected_before_backend_and_input_unchanged(tmp_path):
    input_path, records, _ = make_world(
        tmp_path,
        [make_raw_record("a", 10.0, 106.0), make_raw_record("b", 10.001, 106.001)],
    )
    original = input_path.read_bytes()
    manifest = make_manifest(input_path, records)
    manifest["queries"]["baseline"] = "0" * 64
    manifest_path = write_manifest(tmp_path / "manifest.json", manifest)
    output_path = tmp_path / "result.json"
    factory_called = []

    def factory():
        factory_called.append(True)
        return FakeBackend(records)

    exit_code = runner.main(
        [
            "--execute",
            "--input",
            str(input_path),
            "--manifest",
            str(manifest_path),
            "--output",
            str(output_path),
        ],
        backend_factory=factory,
        on_utc=FixedUtc(),
    )
    assert exit_code == 2
    assert factory_called == []
    assert not output_path.exists()
    assert input_path.read_bytes() == original

    # Spatial source drift is rejected by the same gate.
    spatial_drift = make_manifest(input_path, records)
    spatial_drift["spatial"]["sha256"] = "0" * 64
    spatial_path = write_manifest(tmp_path / "spatial-drift.json", spatial_drift)
    assert_code(
        lambda: runner.execute_collection(
            input_path,
            spatial_path,
            tmp_path / "spatial-result.json",
            backend_factory=factory,
            on_utc=FixedUtc(),
        ),
        "manifest_spatial_hash_drift",
    )
    assert factory_called == []

    # Collector source drift, input byte drift and an invalid schema fail closed.
    collector_drift = make_manifest(input_path, records)
    collector_drift["collector"]["sha256"] = "0" * 64
    collector_path = write_manifest(tmp_path / "collector-drift.json", collector_drift)
    assert_code(
        lambda: runner.execute_collection(
            input_path,
            collector_path,
            tmp_path / "collector-result.json",
            backend_factory=factory,
            on_utc=FixedUtc(),
        ),
        "manifest_collector_hash_drift",
    )

    input_drift = make_manifest(input_path, records)
    write_jsonl(
        input_path,
        [
            make_raw_record("a", 10.0, 106.0),
            make_raw_record("b", 10.001, 106.001),
            make_raw_record("c", 10.002, 106.002),
        ],
    )
    input_drift_path = write_manifest(tmp_path / "input-drift.json", input_drift)
    assert_code(
        lambda: runner.execute_collection(
            input_path,
            input_drift_path,
            tmp_path / "input-result.json",
            backend_factory=factory,
            on_utc=FixedUtc(),
        ),
        "manifest_input_hash_drift",
    )

    invalid_schema = make_manifest(input_path, records)
    invalid_schema["schema"] = "not-exp089"
    invalid_schema_path = write_manifest(tmp_path / "invalid-schema.json", invalid_schema)
    assert_code(
        lambda: runner.execute_collection(
            input_path,
            invalid_schema_path,
            tmp_path / "schema-result.json",
            backend_factory=factory,
            on_utc=FixedUtc(),
        ),
        "manifest_schema_invalid",
    )
    assert factory_called == []


# ---------------------------------------------------------------------------
# B. Full planned counts, 36 cells, subset labels and input rejection
# ---------------------------------------------------------------------------


def test_full_planned_counts_and_timing_cell_count():
    assert runner.DEFAULT_RECORD_COUNT == 6367
    assert runner.potential_pairs(6367) == 20_266_161 == runner.DEFAULT_POTENTIAL_PAIRS
    assert runner.TIMING_CELLS_TOTAL == 36
    assert len(runner._timing_plan()) == 36
    assert len(runner.batch_ids([f"p{index:04d}" for index in range(6367)])) == 50


def test_subset_is_never_labelled_full_primary_and_reordered_input_canonicalizes(tmp_path):
    rows = [
        make_raw_record("b", 10.001, 106.001),
        make_raw_record("a", 10.0, 106.0),
    ]
    path = write_jsonl(tmp_path / "input.jsonl", rows)
    records, digest = runner.load_records(path)
    assert [record.id for record in records] == ["a", "b"]
    manifest = runner.build_manifest(records, path)
    assert manifest["dataset"]["is_full_primary"] is False
    assert manifest["dataset"]["potential_pairs"] == 1
    plan = runner.build_dry_run_plan(
        records, path, digest, manifest, now=FixedUtc()()
    )
    assert plan["input"]["is_full_primary"] is False
    assert plan["manifest"]["frozen"] is False


def test_duplicate_missing_and_invalid_coordinate_inputs_fail_closed(tmp_path):
    duplicate = write_jsonl(
        tmp_path / "duplicate.jsonl",
        [make_raw_record("a", 10.0, 106.0), make_raw_record("a", 10.1, 106.1)],
    )
    assert_code(lambda: runner.load_records(duplicate), "input_duplicate_id")

    missing = write_jsonl(
        tmp_path / "missing.jsonl",
        [
            {
                "id": "a",
                "latitude": 10.0,
                "source_metadata": make_raw_record("a", 10.0, 106.0)["source_metadata"],
            }
        ],
    )
    assert_code(lambda: runner.load_records(missing), "input_coordinate_missing")

    invalid = write_jsonl(
        tmp_path / "invalid.jsonl",
        [make_raw_record("a", float("nan"), 106.0)],
    )
    assert_code(
        lambda: runner.load_records(invalid), "input_coordinate_latitude_nonfinite"
    )

    first = write_jsonl(
        tmp_path / "first.jsonl",
        [make_raw_record("a", 10.0, 106.0), make_raw_record("b", 10.1, 106.1)],
    )
    assert_code(
        lambda: runner.load_records(first, expected_count=3),
        "input_record_count_mismatch",
    )


# ---------------------------------------------------------------------------
# C. Actual-set comparison, missing queries and malformed rows
# ---------------------------------------------------------------------------


def test_equal_counts_but_different_sets_report_false_negatives_and_positives(tmp_path):
    raw = [
        make_raw_record("a", 10.0, 106.0),
        make_raw_record("b", 10.0001, 106.0001),
        make_raw_record("c", 10.0002, 106.0002),
        make_raw_record("d", 10.0003, 106.0003),
        make_raw_record("e", 10.0004, 106.0004),
        make_raw_record("f", 10.0005, 106.0005),
    ]
    input_path, records, _ = make_world(tmp_path, raw)
    backend = FakeBackend(
        records,
        baseline_override=[
            {"a_id": "a", "b_id": "b", "distance_m": 1.0},
            {"a_id": "c", "b_id": "d", "distance_m": 1.0},
        ],
        optimized_override=[
            {"a_id": "a", "b_id": "b", "distance_m": 1.0},
            {"a_id": "e", "b_id": "f", "distance_m": 1.0},
        ],
        candidate_override=[{"candidate_pairs": 2}],
    )
    result, _ = execute_world(tmp_path, input_path, backend)
    correctness = result["correctness"][0]
    assert correctness["baseline_accepted_pairs"] == 2
    assert correctness["optimized_accepted_pairs"] == 2
    assert correctness["accepted_sets_equal"] is False
    assert correctness["false_negatives"] == 1
    assert correctness["false_positives"] == 1
    assert correctness["passed"] is False
    assert result["status"] != "completed"


def test_missing_query_is_not_an_empty_set(tmp_path):
    input_path, records, _ = make_world(
        tmp_path,
        [make_raw_record("a", 10.0, 106.0), make_raw_record("b", 10.001, 106.001)],
    )
    backend = FakeBackend(records, fail_names={"baseline"})
    result, _ = execute_world(tmp_path, input_path, backend)
    correctness = result["correctness"][0]
    assert correctness["baseline_accepted_pairs"] is None
    assert correctness["optimized_accepted_pairs"] is None
    assert correctness["logical_distance_inputs_reference"] == 1
    assert correctness["logical_distance_inputs_optimized"] is None
    assert correctness["status"] == "incomplete"
    assert correctness["batches"][0]["status"] == "error"
    assert correctness["batches"][0]["baseline_count"] is None
    assert result["status"] == "partial"


@pytest.mark.parametrize(
    "rows,code",
    [
        (
            [
                {"a_id": "a", "b_id": "b", "distance_m": 1.0},
                {"a_id": "a", "b_id": "b", "distance_m": 1.0},
            ],
            "duplicate_pair",
        ),
        ([{"a_id": "a", "b_id": "a", "distance_m": 1.0}], "pair_self_rejected"),
        ([{"a_id": "b", "b_id": "a", "distance_m": 1.0}], "pair_not_canonical"),
        ([{"a_id": "a", "b_id": "z", "distance_m": 1.0}], "pair_out_of_universe"),
        ([{"a_id": "a", "b_id": "b", "distance_m": float("nan")}], "pair_distance_nonfinite"),
        ([{"a_id": "a", "b_id": "b", "distance_m": -1.0}], "pair_distance_out_of_radius"),
        ([{"a_id": "a", "b_id": "b", "distance_m": 5000.0}], "pair_distance_out_of_radius"),
    ],
)
def test_malformed_pair_rows_reject(rows, code):
    assert_code(
        lambda: runner.parse_pair_rows(rows, {"a", "b"}, 1.0), code
    )


# ---------------------------------------------------------------------------
# D. Boundary semantics with synthetic fixtures
# ---------------------------------------------------------------------------


def test_identical_coordinates_different_ids_and_cross_area_are_valid(tmp_path):
    input_path, records, _ = make_world(
        tmp_path,
        [
            make_raw_record("a", 10.0, 106.0, district="Quan 1"),
            make_raw_record("b", 10.0, 106.0, district="Quan 3"),
        ],
    )
    backend = FakeBackend(records)
    result, _ = execute_world(tmp_path, input_path, backend)
    correctness = result["correctness"][0]
    assert correctness["passed"] is True
    assert correctness["baseline_accepted_pairs"] == 1
    assert correctness["optimized_accepted_pairs"] == 1
    assert result["projection"]["administrative_binding"] == (
        "source_snapshot_area_only_not_current_admin"
    )


def test_dateline_pole_and_reversed_input_order_boundaries(tmp_path):
    raw = [
        make_raw_record("z-dateline-a", 0.0, 179.99),
        make_raw_record("a-dateline-b", 0.0, -179.99),
        make_raw_record("m-pole-a", 89.99, 0.0),
        make_raw_record("b-pole-b", 89.99, 10.0),
    ]
    input_path, records, _ = make_world(tmp_path, raw)
    backend = FakeBackend(records)
    result, _ = execute_world(tmp_path, input_path, backend)
    # All three radii are checked; the dateline and pole pairs are within 5 km.
    radius_five = result["correctness"][2]
    assert radius_five["radius_km"] == 5.0
    assert radius_five["passed"] is True
    pairs = {
        (batch["baseline_digest"], batch["optimized_digest"])
        for batch in radius_five["batches"]
    }
    assert pairs  # synthetic fixture produced comparable digests
    assert result["correctness"][0]["passed"] is True
    assert result["labels"]["synthetic_offline_tests_are_not_live_engine_evidence"] is True
    assert result["projection"]["administrative_binding"] == (
        "source_snapshot_area_only_not_current_admin"
    )


def test_same_fixed_distance_predicate_and_no_admin_or_live_claim():
    distance_predicate = "distance_m <= $radius_km * 1000.0"
    assert distance_predicate in runner.BASELINE_QUERY
    assert distance_predicate in runner.OPTIMIZED_QUERY
    assert distance_predicate in runner.TIMING_BASELINE_QUERY
    assert distance_predicate in runner.TIMING_OPTIMIZED_QUERY
    assert "point.distance(" in runner.BASELINE_QUERY
    assert "point.distance(" in runner.OPTIMIZED_QUERY
    assert "point.distance(" in runner.TIMING_BASELINE_QUERY
    assert "point.distance(" in runner.TIMING_OPTIMIZED_QUERY
    assert "point.distance(" not in runner.CANDIDATE_COUNT_QUERY
    assert "RETURN count(*) AS accepted_pairs" in runner.TIMING_BASELINE_QUERY
    assert "RETURN count(*) AS accepted_pairs" in runner.TIMING_OPTIMIZED_QUERY
    assert "current district" not in runner.BASELINE_QUERY.lower()


# ---------------------------------------------------------------------------
# E. Warm-up/measured repetition contract and partial failure retention
# ---------------------------------------------------------------------------


def test_36_cells_one_warmup_five_measured_and_alternation(tmp_path):
    input_path, records, _ = make_world(
        tmp_path,
        [make_raw_record("a", 10.0, 106.0), make_raw_record("b", 10.001, 106.001)],
    )
    clock = FakeClock(step=0.25)
    manifest = make_manifest(input_path, records)
    manifest_path = write_manifest(tmp_path / "manifest.json", manifest)
    backend = FakeBackend(records)
    result = runner.execute_collection(
        input_path,
        manifest_path,
        tmp_path / "result.json",
        backend_factory=lambda: backend,
        clock=clock,
        on_utc=FixedUtc(),
    )
    cells = result["timings"]
    assert len(cells) == 36
    assert sum(1 for cell in cells if cell["phase"] == "warmup") == 6
    assert sum(1 for cell in cells if cell["phase"] == "measured") == 30
    assert result["timing_cells"]["success"] == 36
    assert backend.closed is True

    # Alternation is observable per radius/repetition.
    by_radius_rep: dict[tuple[float, int], list[str]] = {}
    for cell in cells:
        by_radius_rep.setdefault((cell["radius_km"], cell["repetition"]), []).append(
            cell["arm"]
        )
    for radius in runner.RADII_KM:
        assert by_radius_rep[(radius, 0)] == ["baseline", "optimized"]
        assert by_radius_rep[(radius, 1)] == ["optimized", "baseline"]
        assert by_radius_rep[(radius, 2)] == ["baseline", "optimized"]
        assert by_radius_rep[(radius, 3)] == ["optimized", "baseline"]
        assert by_radius_rep[(radius, 4)] == ["baseline", "optimized"]
        assert by_radius_rep[(radius, 5)] == ["optimized", "baseline"]

    # With one tiny batch each cell makes start + deadline-check + end calls.
    successful = [cell for cell in cells if cell["status"] == "success"]
    assert len(successful) == 36
    assert all(cell["duration_seconds"] == 0.5 for cell in successful)
    assert all(cell["utc_start"] and cell["utc_end"] for cell in successful)


def test_timing_summary_excludes_warmup_from_median_and_range():
    cells = [
        {
            "radius_km": 1.0,
            "arm": "baseline",
            "phase": "warmup",
            "status": "success",
            "duration_seconds": 999.0,
            "returned_count": 0,
        }
    ]
    for index, duration in enumerate([1.0, 2.0, 3.0, 4.0, 5.0], start=1):
        cells.append(
            {
                "radius_km": 1.0,
                "arm": "baseline",
                "phase": "measured",
                "status": "success",
                "duration_seconds": duration,
                "returned_count": index,
            }
        )
    for arm in ("optimized",):
        cells.append(
            {
                "radius_km": 1.0,
                "arm": arm,
                "phase": "warmup",
                "status": "success",
                "duration_seconds": 777.0,
                "returned_count": 0,
            }
        )
        for duration in [7.0, 8.0, 9.0, 10.0, 11.0]:
            cells.append(
                {
                    "radius_km": 1.0,
                    "arm": arm,
                    "phase": "measured",
                    "status": "success",
                    "duration_seconds": duration,
                    "returned_count": 0,
                }
            )
    summary = {
        (item["radius_km"], item["arm"]): item
        for item in runner.summarize_timings(cells)
    }
    baseline = summary[(1.0, "baseline")]
    assert baseline["warmup_duration_seconds"] == 999.0
    assert baseline["median_seconds"] == 3.0
    assert baseline["range_seconds"] == [1.0, 5.0]
    assert baseline["measured_durations_seconds"] == [1.0, 2.0, 3.0, 4.0, 5.0]


def test_failure_on_measured_rep3_preserves_earlier_rows_and_closes_backend(tmp_path):
    input_path, records, _ = make_world(
        tmp_path,
        [make_raw_record("a", 10.0, 106.0), make_raw_record("b", 10.001, 106.001)],
    )
    # 5 projection/metadata queries + 9 correctness queries + 6 successful
    # timing queries => the 21st query is measured repetition 3 optimized.
    backend = FakeBackend(records, fail_on_query_number=21)
    result, output_path = execute_world(tmp_path, input_path, backend)
    assert output_path.exists()
    assert result["status"] == "partial"
    assert result["timing_cells"]["planned"] == 36
    assert result["timing_cells"]["success"] == 6
    assert result["timing_cells"]["error"] == 1
    assert result["timing_cells"]["missing"] == 29
    assert result["timings"][6]["status"] == "error"
    assert result["timings"][6]["arm"] == "optimized"
    assert result["timings"][6]["repetition"] == 3
    assert all(cell["status"] == "success" for cell in result["timings"][:6])
    assert backend.closed is True
    # No automatic retry: the failing query is the last call.
    assert len(backend.calls) == 21


def test_wrong_before_graph_coordinate_fails_before_benchmark_queries(tmp_path):
    input_path, records, _ = make_world(
        tmp_path,
        [make_raw_record("a", 10.0, 106.0), make_raw_record("b", 10.001, 106.001)],
    )

    def mutate(rows):
        rows[0]["latitude"] = 10.5
        return rows

    backend = FakeBackend(records, projection_mutator=mutate)
    result, _ = execute_world(tmp_path, input_path, backend)
    assert result["status"] == "blocked"
    assert result["stage"] == "graph_projection"
    assert result["error"]["code"] == "graph_projection_mismatch"
    assert "baseline" not in backend.calls
    assert "optimized" not in backend.calls
    assert "candidates" not in backend.calls
    assert backend.closed is True


def test_wrong_before_graph_id_fails_before_benchmark_queries(tmp_path):
    input_path, records, _ = make_world(
        tmp_path,
        [make_raw_record("a", 10.0, 106.0), make_raw_record("b", 10.001, 106.001)],
    )

    def mutate(rows):
        rows[0]["id"] = "not-the-source-id"
        return rows

    backend = FakeBackend(records, projection_mutator=mutate)
    result, _ = execute_world(tmp_path, input_path, backend)
    assert result["status"] == "blocked"
    assert result["error"]["code"] == "graph_projection_mismatch"
    assert "baseline" not in backend.calls
    assert "optimized" not in backend.calls
    assert "candidates" not in backend.calls
    assert backend.closed is True


# ---------------------------------------------------------------------------
# F. Output ownership, sanitized failures and query allow-list
# ---------------------------------------------------------------------------


def test_nonempty_output_and_lock_are_rejected_before_backend(tmp_path):
    input_path, records, _ = make_world(
        tmp_path,
        [make_raw_record("a", 10.0, 106.0), make_raw_record("b", 10.001, 106.001)],
    )
    manifest = make_manifest(input_path, records)
    manifest_path = write_manifest(tmp_path / "manifest.json", manifest)
    output_path = tmp_path / "result.json"
    output_path.write_text("previous evidence\n", encoding="utf-8")
    factory_called = []

    def factory():
        factory_called.append(True)
        return FakeBackend(records)

    assert_code(
        lambda: runner.execute_collection(
            input_path,
            manifest_path,
            output_path,
            backend_factory=factory,
            on_utc=FixedUtc(),
        ),
        "output_not_empty",
    )
    assert factory_called == []
    assert output_path.read_text(encoding="utf-8") == "previous evidence\n"

    lock_path = tmp_path / "locked.json"
    (tmp_path / "locked.json.lock").write_text("held\n", encoding="utf-8")
    assert_code(
        lambda: runner.execute_collection(
            input_path,
            manifest_path,
            lock_path,
            backend_factory=factory,
            on_utc=FixedUtc(),
        ),
        "output_locked",
    )
    assert factory_called == []


def test_second_run_does_not_overwrite_first_result(tmp_path):
    input_path, records, _ = make_world(
        tmp_path,
        [make_raw_record("a", 10.0, 106.0), make_raw_record("b", 10.001, 106.001)],
    )
    backend = FakeBackend(records)
    result, output_path = execute_world(tmp_path, input_path, backend)
    first_bytes = output_path.read_bytes()
    manifest_path = tmp_path / "manifest.json"
    assert_code(
        lambda: runner.execute_collection(
            input_path,
            manifest_path,
            output_path,
            backend_factory=lambda: FakeBackend(records),
            on_utc=FixedUtc(),
        ),
        "output_not_empty",
    )
    assert output_path.read_bytes() == first_bytes


def test_unknown_engine_error_is_closed_and_does_not_persist_raw_text(tmp_path):
    input_path, records, _ = make_world(
        tmp_path,
        [make_raw_record("a", 10.0, 106.0), make_raw_record("b", 10.001, 106.001)],
    )
    backend = FakeBackend(records, fail_names={"baseline"})
    result, output_path = execute_world(tmp_path, input_path, backend)
    encoded = output_path.read_text(encoding="utf-8")
    assert result["correctness"][0]["error"]["code"] == "engine_error"
    assert result["correctness"][0]["error"]["type"] == "RuntimeError"
    assert "hunter2" not in encoded
    assert "password=" not in encoded
    assert "secret-shaped diagnostic" not in encoded


def test_query_allowlist_rejects_writes_and_remote_manifest_override(tmp_path):
    assert_code(
        lambda: runner.assert_allowed_query("MATCH (n) DETACH DELETE n"),
        "query_not_allowlisted",
    )
    assert_code(
        lambda: runner.assert_allowed_query("CREATE (n:POI {id: 'x'})"),
        "query_not_allowlisted",
    )
    runner.assert_allowed_query(runner.BASELINE_QUERY)
    runner.assert_allowed_query(runner.OPTIMIZED_QUERY)
    runner.assert_allowed_query(runner.CANDIDATE_COUNT_QUERY)
    runner.assert_allowed_query(runner.TIMING_BASELINE_QUERY)
    runner.assert_allowed_query(runner.TIMING_OPTIMIZED_QUERY)

    input_path, records, _ = make_world(
        tmp_path,
        [make_raw_record("a", 10.0, 106.0), make_raw_record("b", 10.001, 106.001)],
    )
    manifest = make_manifest(input_path, records)
    manifest["execution"]["engine_uri"] = "bolt://example.invalid:7687"
    manifest_path = write_manifest(tmp_path / "remote.json", manifest)
    assert_code(
        lambda: runner.execute_collection(
            input_path,
            manifest_path,
            tmp_path / "result.json",
            backend_factory=lambda: FakeBackend(records),
            on_utc=FixedUtc(),
        ),
        "remote_endpoint_not_allowed",
    )
    assert runner.FIXED_BOLT_URI == "bolt://127.0.0.1:17687"


# ---------------------------------------------------------------------------
# G. Determinism, denominators and logical-vs-physical labels
# ---------------------------------------------------------------------------


def test_canonical_pair_digest_is_order_independent():
    first = runner.canonical_pairs_digest([("b", "c"), ("a", "b")])
    second = runner.canonical_pairs_digest([("a", "b"), ("b", "c")])
    assert first == second
    assert first != runner.canonical_pairs_digest([("a", "b"), ("a", "c")])


def test_candidate_pruning_and_zero_denominator():
    assert runner.pruning_percent(10, 4) == pytest.approx(60.0)
    assert runner.pruning_percent(1, 0) == pytest.approx(100.0)
    assert runner.pruning_percent(0, 0) is None
    assert runner.potential_pairs(0) == 0
    assert runner.potential_pairs(1) == 0


def test_far_points_give_zero_candidates_and_explicit_logical_labels(tmp_path):
    input_path, records, _ = make_world(
        tmp_path,
        [
            make_raw_record("a", 0.0, 0.0),
            make_raw_record("b", 50.0, 50.0),
            make_raw_record("c", -50.0, -50.0),
        ],
    )
    backend = FakeBackend(records)
    correctness = runner.collect_correctness(
        records,
        1.0,
        backend,
        clock=FakeClock(start=0.0),
        run_started=0.0,
        run_timeout_seconds=3600.0,
        on_utc=FixedUtc(),
    )
    assert correctness["candidate_pairs"] == 0
    assert correctness["logical_distance_inputs_reference"] == 3
    assert correctness["logical_distance_inputs_optimized"] == 0
    assert correctness["physical_engine_evaluation_counts"] is None
    assert correctness["pruning_percent"] == pytest.approx(100.0)
    assert correctness["passed"] is True


def test_synthetic_subset_result_is_not_primary(tmp_path):
    input_path, records, _ = make_world(
        tmp_path,
        [make_raw_record("a", 10.0, 106.0), make_raw_record("b", 10.001, 106.001)],
    )
    result, _ = execute_world(tmp_path, input_path, FakeBackend(records))
    assert result["input"]["is_full_primary"] is False
    assert result["input"]["records"] == 2
    assert result["labels"]["physical_engine_evaluation_counts"] is None
    assert result["assertions"]["no_model_calls"] is True
    assert result["assertions"]["no_graph_mutation"] is True


# ---------------------------------------------------------------------------
# H. QA01 — fixed count-only timing templates
# ---------------------------------------------------------------------------


def _query_prefix(text: str) -> str:
    return text[: text.rindex("RETURN")]


def test_timing_queries_are_count_only_fixed_variants_and_manifest_bound(tmp_path):
    input_path, records, _ = make_world(
        tmp_path,
        [
            make_raw_record("a", 10.0, 106.0),
            make_raw_record("b", 10.0001, 106.0001),
            make_raw_record("c", 20.0, 106.0),
            make_raw_record("d", 20.0001, 106.0001),
        ],
    )
    manifest = runner.build_manifest(records, input_path)
    for name, text in (
        ("timing_baseline", runner.TIMING_BASELINE_QUERY),
        ("timing_optimized", runner.TIMING_OPTIMIZED_QUERY),
    ):
        assert name in manifest["queries"]
        assert manifest["queries"][name] == hashlib.sha256(
            text.encode("utf-8")
        ).hexdigest()
        runner.assert_allowed_query(text)
        assert text.rstrip().endswith("RETURN count(*) AS accepted_pairs")
        assert "RETURN a.id AS a_id" not in text
        assert "point.distance(" in text
        assert "distance_m <= $radius_km * 1000.0" in text

    # Only the final RETURN differs from the accepted correctness query.
    assert _query_prefix(runner.TIMING_BASELINE_QUERY) == _query_prefix(
        runner.BASELINE_QUERY
    )
    assert _query_prefix(runner.TIMING_OPTIMIZED_QUERY) == _query_prefix(
        runner.OPTIMIZED_QUERY
    )

    backend = FakeBackend(records)
    result, _ = execute_world(tmp_path, input_path, backend)
    timing_calls = [
        (name, text)
        for name, text in backend.call_texts
        if name in ("timing_baseline", "timing_optimized")
    ]
    assert len(timing_calls) == 36
    assert {name for name, _ in timing_calls} == {
        "timing_baseline",
        "timing_optimized",
    }
    assert all(
        text in (runner.TIMING_BASELINE_QUERY, runner.TIMING_OPTIMIZED_QUERY)
        for _, text in timing_calls
    )
    assert all("RETURN count(*) AS accepted_pairs" in text for _, text in timing_calls)
    assert all("RETURN a.id AS a_id" not in text for _, text in timing_calls)

    # Correctness still returns pair rows; only timing is count-only.
    assert any(
        name == "baseline" and "RETURN a.id AS a_id" in text
        for name, text in backend.call_texts
    )
    assert any(
        name == "optimized" and "RETURN a.id AS a_id" in text
        for name, text in backend.call_texts
    )

    # The fake returns one count row containing the value 2.  A len(rows)
    # implementation would incorrectly report 1.
    first = result["timings"][0]
    assert first["count_only"] is True
    assert first["query"] == "timing_baseline"
    assert first["accepted_pairs"] == 2
    assert first["returned_count"] == 2
    assert first["batches"][0]["accepted_pairs"] == 2
    assert first["batches"][0]["returned_count"] == 2
    assert result["labels"]["timing_workload"].startswith("count-only aggregate")


@pytest.mark.parametrize(
    "rows,expected_code",
    [
        ([], "timing_count_row_count_invalid"),
        (
            [{"accepted_pairs": 0}, {"accepted_pairs": 0}],
            "timing_count_row_count_invalid",
        ),
        ([{"accepted_pairs": True}], "timing_count_invalid"),
        ([{"accepted_pairs": -1}], "timing_count_invalid"),
        ([{"accepted_pairs": 2}], "timing_count_exceeds_potential"),
    ],
)
def test_malformed_timing_count_fails_cell_not_zero(
    tmp_path, rows, expected_code
):
    input_path, records, _ = make_world(
        tmp_path,
        [make_raw_record("a", 10.0, 106.0), make_raw_record("b", 10.001, 106.001)],
    )
    backend = FakeBackend(
        records, timing_overrides={"timing_baseline": rows}
    )
    result, _ = execute_world(tmp_path, input_path, backend)
    first = result["timings"][0]
    assert first["status"] == "error"
    assert first["error"]["code"] == expected_code
    assert first["accepted_pairs"] is None
    assert first["returned_count"] is None
    assert result["timing_cells"]["success"] == 0
    assert result["timing_cells"]["error"] == 1
    assert result["timing_cells"]["missing"] == 35
    assert all(cell["status"] == "missing" for cell in result["timings"][1:])
    assert backend.calls.count("timing_baseline") == 1
    assert "timing_optimized" not in backend.calls
    assert result["status"] == "partial"
    assert backend.closed is True


# ---------------------------------------------------------------------------
# I. QA02 — closed terminal authorization/permission denial
# ---------------------------------------------------------------------------

_AUTH_CODES = (
    "Neo.ClientError.Security.Unauthorized",
    "Neo.ClientError.Security.Forbidden",
    "Neo.ClientError.Security.CredentialsExpired",
    "Neo.ClientError.Security.AuthorizationExpired",
)


@pytest.mark.parametrize("code", _AUTH_CODES)
def test_index_metadata_auth_denial_blocks_before_benchmark(tmp_path, code):
    input_path, records, _ = make_world(
        tmp_path,
        [make_raw_record("a", 10.0, 106.0), make_raw_record("b", 10.001, 106.001)],
    )
    backend = FakeBackend(
        records,
        fail_exceptions={
            "index_info": CodedAuthError(code, "raw-auth-diagnostic")
        },
    )
    result, output_path = execute_world(tmp_path, input_path, backend)
    assert result["status"] == "blocked"
    assert result["stage"] == "graph_projection"
    assert result["error"]["code"] == "engine_auth_denied"
    assert result["error"]["type"] == "CodedAuthError"
    assert backend.calls == [
        "projection",
        "out_of_universe",
        "scoped_counts",
        "materialization",
        "index_info",
    ]
    assert backend.closed is True

    encoded = output_path.read_text(encoding="utf-8")
    assert "raw-auth-diagnostic" not in encoded
    assert code not in encoded


def test_auth_denial_at_first_baseline_stops_all_later_stages(tmp_path):
    input_path, records, _ = make_world(
        tmp_path,
        [make_raw_record("a", 10.0, 106.0), make_raw_record("b", 10.001, 106.001)],
    )
    backend = FakeBackend(
        records,
        fail_exceptions={
            "baseline": CodedAuthError(
                "Neo.ClientError.Security.Unauthorized", "raw-auth-diagnostic"
            )
        },
    )
    result, output_path = execute_world(tmp_path, input_path, backend)
    assert result["status"] == "partial"
    assert result["correctness"][0]["error"]["code"] == "engine_auth_denied"
    assert result["correctness"][0]["status"] == "incomplete"
    assert result["correctness"][1]["reason"] == "engine_auth_denied_no_continuation"
    assert result["correctness"][2]["reason"] == "engine_auth_denied_no_continuation"
    assert result["correctness"][1]["potential_pairs_observed"] == 1
    assert result["correctness"][1]["batches"][0]["status"] == "missing"
    assert result["terminal_error"]["code"] == "engine_auth_denied"
    assert result["error"]["code"] == "engine_auth_denied"
    assert result["timing_cells"]["success"] == 0
    assert result["timing_cells"]["error"] == 0
    assert result["timing_cells"]["missing"] == 36
    assert all(
        cell["reason"] == "engine_auth_denied_no_continuation"
        for cell in result["timings"]
    )
    assert backend.calls[-1] == "baseline"
    assert backend.calls.count("baseline") == 1
    assert "optimized" not in backend.calls
    assert "candidates" not in backend.calls
    assert "timing_baseline" not in backend.calls
    assert "timing_optimized" not in backend.calls
    assert backend.closed is True
    assert "raw-auth-diagnostic" not in output_path.read_text(encoding="utf-8")


def test_auth_denial_at_candidate_stops_before_optimized_timing_and_next_radius(
    tmp_path,
):
    input_path, records, _ = make_world(
        tmp_path,
        [make_raw_record("a", 10.0, 106.0), make_raw_record("b", 10.001, 106.001)],
    )
    backend = FakeBackend(
        records,
        fail_exceptions={
            "candidates": CodedAuthError(
                "Neo.ClientError.Security.Forbidden", "raw-auth-diagnostic"
            )
        },
    )
    result, _ = execute_world(tmp_path, input_path, backend)
    assert result["correctness"][0]["error"]["code"] == "engine_auth_denied"
    assert result["correctness"][1]["reason"] == "engine_auth_denied_no_continuation"
    assert result["correctness"][2]["reason"] == "engine_auth_denied_no_continuation"
    candidate_index = backend.calls.index("candidates")
    assert candidate_index == len(backend.calls) - 1
    assert backend.calls.count("candidates") == 1
    assert "timing_baseline" not in backend.calls
    assert "timing_optimized" not in backend.calls
    assert result["timing_cells"]["missing"] == 36
    assert backend.closed is True


def test_auth_denial_at_first_timing_count_stops_optimized_and_remaining_cells(
    tmp_path,
):
    input_path, records, _ = make_world(
        tmp_path,
        [make_raw_record("a", 10.0, 106.0), make_raw_record("b", 10.001, 106.001)],
    )
    backend = FakeBackend(
        records,
        fail_exceptions={
            "timing_baseline": CodedAuthError(
                "Neo.ClientError.Security.CredentialsExpired", "raw-auth-diagnostic"
            )
        },
    )
    result, _ = execute_world(tmp_path, input_path, backend)
    assert all(item["passed"] for item in result["correctness"])
    first = result["timings"][0]
    assert first["status"] == "error"
    assert first["error"]["code"] == "engine_auth_denied"
    assert backend.calls[-1] == "timing_baseline"
    assert "timing_optimized" not in backend.calls
    assert result["timing_cells"]["success"] == 0
    assert result["timing_cells"]["error"] == 1
    assert result["timing_cells"]["missing"] == 35
    assert result["timings"][1]["reason"] == "engine_auth_denied_no_continuation"
    assert result["terminal_error"]["code"] == "engine_auth_denied"
    assert backend.closed is True


@pytest.mark.parametrize(
    "exception",
    [
        CodedAuthError("Neo.ClientError.Security.Forbidden"),
        CodedAuthError("Neo.ClientError.Security.AuthorizationExpired"),
        AuthError("raw-auth-diagnostic"),
        AuthConfigurationError("raw-auth-diagnostic"),
        Forbidden("raw-auth-diagnostic"),
        runner.CollectorError("engine_auth_denied"),
        runner.CollectorError("Neo.ClientError.Security.Unauthorized"),
    ],
)
def test_closed_auth_classification_is_terminal(tmp_path, exception):
    input_path, records, _ = make_world(
        tmp_path,
        [make_raw_record("a", 10.0, 106.0), make_raw_record("b", 10.001, 106.001)],
    )
    backend = FakeBackend(records, fail_exceptions={"baseline": exception})
    result, _ = execute_world(tmp_path, input_path, backend)
    assert result["correctness"][0]["error"]["code"] == "engine_auth_denied"
    assert result["correctness"][1]["reason"] == "engine_auth_denied_no_continuation"
    assert "timing_baseline" not in backend.calls
    assert "timing_optimized" not in backend.calls
    assert backend.calls[-1] == "baseline"
    assert backend.closed is True


def test_auth_denial_after_one_successful_batch_preserves_finished_receipts(tmp_path):
    rows = [
        make_raw_record(f"p{index:04d}", 10.0 + index * 1e-5, 106.0)
        for index in range(260)
    ]
    input_path, records, _ = make_world(tmp_path, rows)
    backend = FakeBackend(
        records,
        fail_query_numbers={
            11: CodedAuthError(
                "Neo.ClientError.Security.Unauthorized", "raw-auth-diagnostic"
            )
        },
    )
    result, _ = execute_world(tmp_path, input_path, backend)
    assert len(backend.calls) == 11
    assert backend.calls[-1] == "baseline"
    assert result["correctness"][0]["batches"][0]["status"] == "success"
    assert result["correctness"][0]["batches"][0]["baseline_count"] is not None
    assert result["correctness"][0]["batches"][1]["status"] == "error"
    assert result["correctness"][0]["batches"][1]["error"]["code"] == (
        "engine_auth_denied"
    )
    assert result["correctness"][0]["batches"][2]["status"] == "missing"
    assert result["correctness"][0]["missing_batches"] == [1, 2]
    assert result["correctness"][1]["reason"] == "engine_auth_denied_no_continuation"
    assert result["correctness"][2]["reason"] == "engine_auth_denied_no_continuation"
    assert result["timing_cells"]["missing"] == 36
    assert backend.closed is True


def test_generic_unsupported_index_metadata_remains_a_disclosed_gap(tmp_path):
    input_path, records, _ = make_world(
        tmp_path,
        [make_raw_record("a", 10.0, 106.0), make_raw_record("b", 10.001, 106.001)],
    )
    secret = "unauthorized password=hunter2 raw-index-diagnostic"
    backend = FakeBackend(
        records, fail_exceptions={"index_info": RuntimeError(secret)}
    )
    result, output_path = execute_world(tmp_path, input_path, backend)
    assert result["status"] == "completed"
    info = result["projection"]["index_info"]
    assert info["status"] == "unsupported_or_unavailable"
    assert info["error"]["code"] == "engine_error"
    assert info["error"]["type"] == "RuntimeError"
    assert "engine_auth_denied" not in info["error"]
    encoded = output_path.read_text(encoding="utf-8")
    assert secret not in encoded
    assert "hunter2" not in encoded


def test_runtime_error_text_unauthorized_is_not_an_auth_diagnosis(tmp_path):
    input_path, records, _ = make_world(
        tmp_path,
        [make_raw_record("a", 10.0, 106.0), make_raw_record("b", 10.001, 106.001)],
    )
    secret = "unauthorized password=hunter2 raw-execution-diagnostic"
    backend = FakeBackend(
        records, fail_exceptions={"baseline": RuntimeError(secret)}
    )
    result, output_path = execute_world(tmp_path, input_path, backend)
    error = result["correctness"][0]["error"]
    assert error["code"] == "engine_error"
    assert error["type"] == "RuntimeError"
    assert "terminal_error" not in result
    encoded = output_path.read_text(encoding="utf-8")
    assert secret not in encoded
    assert "hunter2" not in encoded
