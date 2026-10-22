"""TIM096 offline tests: reused E2-093 correctness proof + fresh timing cohort.

Every fixture here is synthetic and lives under the dedicated qa-work subtree.
No test constructs the real Neo4j driver, opens a socket, reads a credential
file or performs a live measurement.  The positive proof is a small local
journal, not the historical E2-093 evidence.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from benchmarks.spatial_live import journal, runner, supervisor  # noqa: E402

ARCHIVE_ROOT = REPO_ROOT / "docs/project/handoffs/TIM-096/before-source"
QA_ROOT = REPO_ROOT / "docs/project/handoffs/TIM-096/qa-work/executor-tests"


def _load_helpers():
    path = Path(__file__).with_name("test_runner.py")
    spec = importlib.util.spec_from_file_location("tim096_test_helpers", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


H = _load_helpers()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relative(path: Path) -> str:
    return path.resolve().relative_to(REPO_ROOT).as_posix()


def _entry(path: Path) -> dict:
    return {"path": _relative(path), "sha256": _sha(path)}


def _archive_entries() -> dict[str, dict]:
    names = {"runner": "runner.py", "journal": "journal.py", "supervisor": "supervisor.py"}
    return {key: _entry(ARCHIVE_ROOT / name) for key, name in names.items()}


@pytest.fixture
def proof_root():
    QA_ROOT.mkdir(parents=True, exist_ok=True)
    root = QA_ROOT / f"case-{uuid.uuid4().hex}"
    root.mkdir()
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _world(root: Path, *, count: int, far: bool):
    rows = []
    for index in range(count):
        offset = index * 0.0005 if not far else index * 0.1
        rows.append(
            H.make_raw_record(f"p{index:02d}", 10.0 + offset, 106.0 + offset)
        )
    return H.make_world(root, rows)


def build_proof(
    root: Path,
    *,
    far: bool = False,
    count: int = 2,
    timing_cells: int = 0,
    drop_batch_radius: float | None = None,
    drop_receipt_radius: float | None = None,
    redistribute_batches: bool = False,
    radius_total_delta: int = 0,
    stale_review_hash: bool = False,
    bad_query: bool = False,
    bad_scope: bool = False,
):
    """Build one self-consistent synthetic old proof plus a new manifest."""
    root.mkdir(parents=True, exist_ok=True)
    input_path, records, digest = _world(root, count=count, far=far)
    universe = sorted(record.id for record in records)
    batches = runner.batch_ids(universe)
    batch_potentials = [runner._batch_potential(universe, batch) for batch in batches]
    accepted = 0 if far else sum(batch_potentials)
    pair_digest = hashlib.sha256(b"synthetic-tim096-pair-set").hexdigest()

    archives = _archive_entries()
    old = runner.build_manifest(records, input_path)
    old["frozen"] = True
    old["review"] = {"decision": "approved", "reviewer": "synthetic-proof"}
    old["sources"] = {
        "protocol": runner.DURABILITY_PROTOCOL,
        **archives,
    }
    old["collector"] = {
        "path": archives["runner"]["path"],
        "sha256": archives["runner"]["sha256"],
    }
    old_path = root / "e2-execution.frozen.json"
    old_path.write_text(json.dumps(old, indent=2), encoding="utf-8")
    old_sha = _sha(old_path)

    binding = {
        "protocol": runner.DURABILITY_PROTOCOL,
        "journal_schema": journal.JOURNAL_SCHEMA,
        "manifest_sha256": old_sha,
        "manifest_schema": old["schema"],
        "input_sha256": digest,
        "sources": old["sources"],
    }
    journal_path = root / "result.json.journal.jsonl"
    sink = journal.DurableJournal.open_new(
        journal_path,
        binding=binding,
        planned=runner.journal_planned_denominator(records),
    )
    sink.append("run_start", {"mode": "synthetic", "records": len(records)})
    for cell in runner._timing_plan()[:timing_cells]:
        sink.append(
            "timing_cell",
            {
                "radius_km": cell["radius_km"],
                "arm": cell["arm"],
                "repetition": cell["repetition"],
                "phase": cell["phase"],
                "status": "success",
                "accepted_pairs": accepted,
            },
        )

    declared_batch_potentials = list(batch_potentials)
    if redistribute_batches:
        declared_batch_potentials[0] += 1
        declared_batch_potentials[1] -= 1

    received: dict[float, dict] = {}
    for radius in runner.RADII_KM:
        if radius != drop_batch_radius:
            for index, anchor_batch in enumerate(batches):
                sink.append(
                    "correctness_batch",
                    {
                        "radius_km": radius,
                        "index": index,
                        "status": "success",
                        "anchor_count": len(anchor_batch),
                        "potential_pairs": declared_batch_potentials[index],
                        "baseline_count": accepted,
                        "optimized_count": accepted,
                        "candidate_pairs": accepted,
                        "false_negatives": 0,
                        "false_positives": 0,
                        "baseline_digest": pair_digest,
                        "optimized_digest": pair_digest,
                    },
                )
        if radius == drop_receipt_radius:
            continue
        observed = sum(batch_potentials) + radius_total_delta
        sink.append(
            "correctness_radius",
            {
                "radius_km": radius,
                "status": "passed",
                "passed": True,
                "accepted_sets_equal": True,
                "false_negatives": 0,
                "false_positives": 0,
                "missing_batches": [],
                "error": None,
                "batches_completed": len(batches),
                "potential_pairs_observed": observed,
                "baseline_accepted_pairs": accepted,
                "optimized_accepted_pairs": accepted,
                "candidate_pairs": accepted,
                "baseline_pair_digest": pair_digest,
                "optimized_pair_digest": pair_digest,
            },
        )
        received[radius] = {
            "radius_km": radius,
            "status": "passed",
            "passed": True,
            "accepted_sets_equal": True,
            "false_negatives": 0,
            "false_positives": 0,
            "batches_completed": len(batches),
            "potential_pairs_observed": observed,
            "baseline_accepted_pairs": accepted,
            "optimized_accepted_pairs": accepted,
            "candidate_pairs": accepted,
            "baseline_pair_digest": pair_digest,
            "optimized_pair_digest": pair_digest,
        }
    sink.close()

    journal_entry = _entry(journal_path)
    review = {
        "decision": "ACCEPTED_SYNTHETIC_TIM096_PROOF",
        "check_count": 2,
        "checks": [{"name": "synthetic-chain"}, {"name": "synthetic-sets"}],
        "journal_incomplete_tail": False,
        "journal_events": {
            "correctness_batch": sum(
                1 for radius in runner.RADII_KM if radius != drop_batch_radius
            )
            * len(batches),
            "correctness_radius": len(received),
        },
        "correctness_radii_planned": list(runner.RADII_KM),
        "correctness_radii_passed": len(runner.RADII_KM),
        "correctness": [received[radius] for radius in runner.RADII_KM if radius in received],
        "evidence_hashes": {
            _relative(old_path): old_sha,
            journal_entry["path"]: journal_entry["sha256"],
        },
        "final_result_status": None,
        "limitations": ["synthetic proof; not E2-093 evidence"],
    }
    review_path = root / "parent-primary-result-review.json"
    review_path.write_text(json.dumps(review, indent=2), encoding="utf-8")
    review_entry = _entry(review_path)

    reference = {
        "protocol": runner.TIMING_ONLY_PROTOCOL,
        "frozen_manifest": _entry(old_path),
        "journal": journal_entry,
        "parent_review": review_entry,
        "archived_sources": archives,
        "dataset": {
            **old["dataset"],
            "scope_sha256": old["scope"]["id_coordinate_sha256"],
        },
        "spatial": old["spatial"],
        "queries": old["queries"],
    }
    if bad_query:
        reference["queries"] = {
            **reference["queries"],
            "timing_baseline": "0" * 64,
        }
    if bad_scope:
        reference["dataset"] = {
            **reference["dataset"],
            "scope_sha256": "0" * 64,
        }

    manifest = runner.build_manifest(
        records,
        input_path,
        collection_mode=runner.COLLECTION_MODE_TIMING_ONLY,
        external_correctness=reference,
    )
    manifest["frozen"] = True
    manifest["review"] = {"decision": "approved", "reviewer": "synthetic-new"}
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    if stale_review_hash:
        review_path.write_text(json.dumps(review, indent=2) + "\n\n", encoding="utf-8")

    return {
        "root": root,
        "input": input_path,
        "records": records,
        "digest": digest,
        "manifest": manifest,
        "manifest_path": manifest_path,
        "reference": reference,
        "accepted": accepted,
        "old": old,
    }


def _execute(proof, backend, name="new-result.json", **kwargs):
    return runner.execute_collection(
        proof["input"],
        proof["manifest_path"],
        proof["root"] / name,
        backend_factory=lambda: backend,
        clock=H.FakeClock(),
        on_utc=H.FixedUtc(),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# A. Positive synthetic proof, fresh projection, exact 36 timings
# ---------------------------------------------------------------------------


def test_synthetic_proof_positive_fresh_projection_and_exact_36(proof_root):
    proof = build_proof(proof_root, timing_cells=1)
    backend = H.FakeBackend(proof["records"])
    result = _execute(proof, backend)

    assert result["status"] == "completed"
    assert result["collection_mode"] == runner.COLLECTION_MODE_TIMING_ONLY
    assert result["correctness"] == []
    assert len(result["timings"]) == 36
    assert result["timing_cells"] == {
        "planned": 36,
        "success": 36,
        "error": 0,
        "missing": 0,
        "warmups_success": 6,
        "measured_success": 30,
    }
    assert result["external_correctness"]["status"] == "validated"
    assert result["external_correctness"]["correctness_reused_not_rerun"] is True
    assert result["execution_budget_seconds"] == 7200.0
    assert backend.closed is True

    # No correctness pair-row query and no candidate query in the new cohort.
    assert "baseline" not in backend.calls
    assert "optimized" not in backend.calls
    assert "candidates" not in backend.calls
    timing_calls = [name for name in backend.calls if name.startswith("timing_")]
    assert len(timing_calls) == 36
    assert all(
        text in (runner.TIMING_BASELINE_QUERY, runner.TIMING_OPTIMIZED_QUERY)
        for name, text in backend.call_texts
        if name.startswith("timing_")
    )

    read = journal.read_journal(proof["root"] / "new-result.json.journal.jsonl")
    kinds = [event["kind"] for event in read.events]
    assert kinds.count("correctness_reference_validated") == 1
    assert "correctness_batch" not in kinds
    assert "correctness_radius" not in kinds
    assert read.planned["correctness"]["planned_queries"] == 0
    assert read.planned["correctness"]["correctness_reused_not_rerun"] is True
    assert read.binding["collection_mode"] == runner.COLLECTION_MODE_TIMING_ONLY
    validated = next(
        event for event in read.events if event["kind"] == "correctness_reference_validated"
    )
    assert validated["payload"]["correctness_reused_not_rerun"] is True


# ---------------------------------------------------------------------------
# B/C. Tampering, incomplete correctness, and allowed old partial timing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs,expected_code",
    [
        ({"far": True, "count": 130, "redistribute_batches": True}, "external_correctness"),
        ({"radius_total_delta": 1}, "external_correctness"),
        ({"drop_batch_radius": 3.0}, "external_correctness_incomplete"),
        ({"drop_receipt_radius": 5.0}, "external_correctness_incomplete"),
        ({"stale_review_hash": True}, "external_reference_hash_mismatch"),
        ({"bad_query": True}, "external_query_mismatch"),
        ({"bad_scope": True}, "external_dataset_mismatch"),
    ],
)
def test_invalid_synthetic_proof_rejected_before_backend(
    proof_root, kwargs, expected_code
):
    proof = build_proof(proof_root, **kwargs)
    calls = []

    def factory():
        calls.append(True)
        return H.FakeBackend(proof["records"])

    with pytest.raises(runner.CollectorError) as caught:
        runner.execute_collection(
            proof["input"],
            proof["manifest_path"],
            proof["root"] / "new-result.json",
            backend_factory=factory,
            clock=H.FakeClock(),
            on_utc=H.FixedUtc(),
        )
    assert expected_code in caught.value.code
    assert calls == []
    assert not (proof["root"] / "new-result.json").exists()


def test_old_partial_timing_allowed_but_correctness_mandatory(proof_root):
    partial = build_proof(proof_root / "partial", timing_cells=2)
    validated = runner.validate_external_correctness_reference(
        partial["manifest"], partial["records"], partial["digest"]
    )
    assert validated["status"] == "validated"
    assert validated["journal"]["timing_cell_receipts"] == 2
    assert validated["accepted_counts"]["3.0"] == {
        "baseline": partial["accepted"],
        "optimized": partial["accepted"],
    }

    incomplete = build_proof(
        proof_root / "incomplete", timing_cells=35, drop_batch_radius=1.0
    )
    with pytest.raises(runner.CollectorError) as caught:
        runner.validate_external_correctness_reference(
            incomplete["manifest"], incomplete["records"], incomplete["digest"]
        )
    assert caught.value.code == "external_correctness_incomplete"


# ---------------------------------------------------------------------------
# D. Path safety, including resolved symlink-shaped targets
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "target,code",
    [
        (QA_ROOT / "credentials.env", "external_reference_path_rejected"),
        (QA_ROOT / "secrets/e2-execution.frozen.json", "external_reference_path_rejected"),
        (QA_ROOT / "other.json", "external_reference_role_invalid"),
        (Path("C:/Windows/System32/e2-execution.frozen.json"), "external_reference_path_rejected"),
    ],
)
def test_resolved_target_shape_rejected_before_read(monkeypatch, target, code):
    requested = QA_ROOT / "public/e2-execution.frozen.json"
    original_resolve = Path.resolve

    def resolve(path, *args, **kwargs):
        if path == requested:
            return target
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolve)
    original_is_file = Path.is_file
    monkeypatch.setattr(
        Path,
        "is_file",
        lambda path: True if path == target else original_is_file(path),
    )
    relative = requested.relative_to(REPO_ROOT).as_posix()
    with pytest.raises(runner.CollectorError) as caught:
        runner._external_reference_path(relative, "frozen_manifest")
    assert code in caught.value.code


def test_resolution_error_and_lexical_escape_rejected(monkeypatch):
    original_resolve = Path.resolve

    def explode(path, *args, **kwargs):
        if "e2-execution.frozen.json" in str(path):
            raise RuntimeError("simulated symlink loop")
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", explode)
    with pytest.raises(runner.CollectorError) as caught:
        runner._external_reference_path(
            "docs/project/handoffs/TIM-096/qa-work/e2-execution.frozen.json",
            "frozen_manifest",
        )
    assert caught.value.code == "external_reference_missing"

    for value in (
        "../e2-execution.frozen.json",
        "C:/Windows/e2-execution.frozen.json",
        "docs/project/handoffs/secret/e2-execution.frozen.json",
        "docs/project/handoffs/.env/e2-execution.frozen.json",
    ):
        with pytest.raises(runner.CollectorError):
            runner._external_reference_path(value, "frozen_manifest")


# ---------------------------------------------------------------------------
# E. Projection/auth stop; reference-count mismatch stops later cells
# ---------------------------------------------------------------------------


def test_projection_drift_blocks_before_timing(proof_root):
    proof = build_proof(proof_root)

    def mutate(rows):
        rows[0]["id"] = "foreign-id"
        return rows

    backend = H.FakeBackend(proof["records"], projection_mutator=mutate)
    result = _execute(proof, backend)
    assert result["status"] == "blocked"
    assert result["error"]["code"] == "graph_projection_mismatch"
    assert not any(name.startswith("timing_") for name in backend.calls)
    assert backend.closed is True


def test_projection_auth_denial_blocks_before_timing(proof_root):
    proof = build_proof(proof_root)
    backend = H.FakeBackend(
        proof["records"],
        fail_exceptions={"index_info": H.AuthError("synthetic-auth-denial")},
    )
    result = _execute(proof, backend)
    assert result["status"] == "blocked"
    assert not any(name.startswith("timing_") for name in backend.calls)
    assert backend.closed is True


def test_reference_count_mismatch_fails_current_cell_and_later_missing(proof_root):
    proof = build_proof(proof_root)
    backend = H.FakeBackend(
        proof["records"],
        timing_overrides={"timing_baseline": [{"accepted_pairs": 0}]},
    )
    result = _execute(proof, backend)

    assert result["status"] == "partial"
    first = result["timings"][0]
    assert first["status"] == "error"
    assert first["error"]["code"] == "timing_reference_count_mismatch"
    assert first["accepted_pairs"] is None
    assert first["accepted_pairs_observed"] == 0
    assert first["duration_seconds"] is not None
    assert all(cell["status"] == "missing" for cell in result["timings"][1:])
    assert backend.calls.count("timing_baseline") == 1
    assert "timing_optimized" not in backend.calls


# ---------------------------------------------------------------------------
# F. Zero counts and warm-up/measured ordering retained exactly
# ---------------------------------------------------------------------------


def test_zero_counts_and_warmup_ordering_are_not_defaulted(proof_root):
    proof = build_proof(proof_root, far=True, count=3)
    backend = H.FakeBackend(proof["records"])
    result = _execute(proof, backend)

    assert result["status"] == "completed"
    assert proof["accepted"] == 0
    assert len(result["timings"]) == 36
    assert all(cell["status"] == "success" for cell in result["timings"])
    assert all(cell["accepted_pairs"] == 0 for cell in result["timings"])
    assert all(cell["returned_count"] == 0 for cell in result["timings"])
    assert all(cell["accepted_pairs"] is not None for cell in result["timings"])
    for radius in runner.RADII_KM:
        radius_cells = [
            cell for cell in result["timings"] if cell["radius_km"] == radius
        ]
        assert [cell["phase"] for cell in radius_cells[:2]] == ["warmup"] * 2
        assert [cell["phase"] for cell in radius_cells[2:]] == ["measured"] * 10
    assert sum(1 for cell in result["timings"] if cell["phase"] == "warmup") == 6
    assert sum(1 for cell in result["timings"] if cell["phase"] == "measured") == 30


# ---------------------------------------------------------------------------
# G. Worker/supervisor budgets and invalid values before backend/child
# ---------------------------------------------------------------------------


def test_worker_uses_7200_and_legacy_full_uses_3600(proof_root):
    proof = build_proof(proof_root)
    assert runner.resolve_run_budget(proof["manifest"]) == 7200
    assert runner.resolve_run_budget(proof["old"]) == 3600

    legacy = runner.build_manifest(proof["records"], proof["input"])
    assert runner.resolve_run_budget(legacy) == 3600


@pytest.mark.parametrize("value", [True, -1, float("nan"), 9999, 3600])
def test_invalid_worker_budget_rejected_before_backend(proof_root, value):
    proof = build_proof(proof_root)
    manifest = json.loads(proof["manifest_path"].read_text(encoding="utf-8"))
    manifest["budget"]["run_timeout_seconds"] = value
    invalid_path = proof["root"] / "invalid-manifest.json"
    invalid_path.write_text(json.dumps(manifest), encoding="utf-8")

    calls = []

    def factory():
        calls.append(True)
        return H.FakeBackend(proof["records"])

    with pytest.raises(runner.CollectorError):
        runner.execute_collection(
            proof["input"],
            invalid_path,
            proof["root"] / "invalid-result.json",
            backend_factory=factory,
        )
    assert calls == []


def test_timing_only_rejects_explicit_worker_budget_override(proof_root):
    proof = build_proof(proof_root)
    calls = []

    def factory():
        calls.append(True)
        return H.FakeBackend(proof["records"])

    with pytest.raises(runner.CollectorError) as caught:
        runner.execute_collection(
            proof["input"],
            proof["manifest_path"],
            proof["root"] / "override-result.json",
            backend_factory=factory,
            clock=H.FakeClock(),
            on_utc=H.FixedUtc(),
            run_timeout_seconds=3600,
        )
    assert caught.value.code == "run_budget_override_rejected"
    assert calls == []


def test_supervisor_timing_budget_7200_and_override_rejected(proof_root):
    proof = build_proof(proof_root)
    spawns = []

    def factory(*args, **kwargs):
        spawns.append((args, kwargs))
        return subprocess.Popen(*args, **kwargs)

    report = supervisor.run_supervisor(
        proof["input"],
        proof["manifest_path"],
        proof["root"] / "supervised-ok.json",
        popen_factory=factory,
        child_command=[sys.executable, "-B", "-c", "import sys; sys.exit(0)"],
    )
    assert report["collection_mode"] == runner.COLLECTION_MODE_TIMING_ONLY
    assert report["timeout_seconds"] == 7200.0
    assert report["execution_budget_seconds"] == 7200.0
    assert len(spawns) == 1
    assert spawns[0][1]["shell"] is False

    with pytest.raises(runner.CollectorError) as caught:
        supervisor.run_supervisor(
            proof["input"],
            proof["manifest_path"],
            proof["root"] / "supervised-bad.json",
            timeout_seconds=3600,
            popen_factory=factory,
        )
    assert caught.value.code == "supervisor_budget_override_rejected"
    assert len(spawns) == 1
