"""CLI safety and labelling tests for the OC-018 evaluator."""

import json
from pathlib import Path

import pytest

from evaluation.cli import _h2_report, _h3_report, main
from evaluation.common import sha256_file

from helpers_evaluation import h2_manifest, h2_record, h3_manifest, h3_record

FIXTURES = Path(__file__).resolve().parents[2] / "benchmarks" / "evaluation" / "fixtures"


def _write_json(path: Path, value):
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, records):
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")


def test_h2_cli_writes_metrics_and_hashes(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    records_path = tmp_path / "records.jsonl"
    out_dir = tmp_path / "out"
    _write_json(manifest_path, h2_manifest(scenarios=("S01",), repetitions=1))
    _write_jsonl(records_path, [
        h2_record("S01", "hybrid", 0, temporal_violation=False),
        h2_record("S01", "llm_only", 0, temporal_violation=False),
    ])

    rc = main(["h2", "--manifest", str(manifest_path), "--records", str(records_path),
               "--out", str(out_dir)])
    assert rc == 0
    metrics_path = out_dir / "h2_metrics.json"
    run_manifest_path = out_dir / "h2_run_manifest.json"
    assert metrics_path.exists()
    assert (out_dir / "h2_report.txt").exists()
    assert run_manifest_path.exists()

    run_manifest = json.loads(run_manifest_path.read_text(encoding="utf-8"))
    assert run_manifest["input_sha256"]["manifest"] == sha256_file(manifest_path)
    assert run_manifest["input_sha256"]["records"] == sha256_file(records_path)
    assert run_manifest["output_sha256"] == sha256_file(metrics_path)
    # Inputs are untouched.
    assert sha256_file(records_path) == sha256_file(records_path)


def test_out_is_required_by_argparse():
    with pytest.raises(SystemExit):
        main(["h2", "--manifest", "m.json", "--records", "r.jsonl"])


def test_cli_refuses_to_write_into_a_file(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    records_path = tmp_path / "records.jsonl"
    _write_json(manifest_path, h2_manifest(scenarios=("S01",), repetitions=1))
    _write_jsonl(records_path, [h2_record("S01", "hybrid", 0)])
    # Passing the records file itself as --out must fail closed.
    rc = main(["h2", "--manifest", str(manifest_path), "--records", str(records_path),
               "--out", str(records_path)])
    assert rc == 2


def test_smoke_is_labelled_synthetic_and_inputs_untouched(tmp_path):
    before = {path.name: sha256_file(path) for path in FIXTURES.glob("*")}
    out_dir = tmp_path / "demo"
    rc = main(["smoke", "--out", str(out_dir)])
    assert rc == 0

    marker = (out_dir / "SYNTHETIC_EVALUATOR_TEST.txt").read_text(encoding="utf-8")
    assert "SYNTHETIC EVALUATOR TEST" in marker
    assert "NOT a real H2/H3 study result" in marker

    demo = json.loads((out_dir / "smoke_demo.json").read_text(encoding="utf-8"))
    assert demo["label"] == "SYNTHETIC EVALUATOR TEST"
    assert demo["h2"]["conclusion_label"] == "SYNTHETIC EVALUATOR TEST"
    assert demo["h3"]["conclusion_label"] == "SYNTHETIC EVALUATOR TEST"

    after = {path.name: sha256_file(path) for path in FIXTURES.glob("*")}
    assert before == after


def test_h3_cli_writes_outputs(tmp_path):
    manifest_path = tmp_path / "h3_manifest.json"
    records_path = tmp_path / "h3_records.jsonl"
    out_dir = tmp_path / "h3out"
    _write_json(manifest_path, h3_manifest(profiles=("P1",), scenarios=("S01",)))
    _write_jsonl(records_path, [
        h3_record("P1", "S01", "memory_disabled", 0, selected_poi_ids=["p_cafe"]),
        h3_record("P1", "S01", "two_tier", 0, selected_poi_ids=["p_food"]),
    ])
    rc = main(["h3", "--manifest", str(manifest_path), "--records", str(records_path),
               "--out", str(out_dir)])
    assert rc == 0
    metrics = json.loads((out_dir / "h3_metrics.json").read_text(encoding="utf-8"))
    assert metrics["task"] == "H3"
    assert metrics["groups"]["P1"]["two_tier"]["preferred_share"] == pytest.approx(1.0)


def test_h2_report_states_denominators_and_suppresses_synthetic_pvalue(run_h2):
    records = [
        h2_record("S01", "hybrid", 0, temporal_violation=False),
        h2_record("S01", "hybrid", 1, validation_status="partial",
                  temporal_violation=True, known_temporal_violations=1),
        h2_record("S01", "hybrid", 2, validation_status="unverifiable", unverifiable=True,
                  temporal_violation=None, known_temporal_violations=None,
                  violation_count_complete=False, unknown_reasons=["hours_unknown"]),
    ]
    metrics = run_h2(h2_manifest(scenarios=("S01",), repetitions=3), records)
    report = _h2_report(metrics)
    assert "violation_determined=0.5 (1/2 determined delivered, coverage=0.666667" in report
    assert "observed_known_violation_lower_bound(all delivered)=0.333333 (1/3)" in report
    assert "secondary outcomes (available/missing" in report
    assert "route_travel_minutes [minutes]: available=0 missing=3" in report
    # Synthetic evidence blocks inference, so no numeric p-value is claimed.
    assert "mcnemar_exact_p=suppressed" in report
    assert "mcnemar_exact_p=1" not in report
    assert "not H2 results" in report


def test_h3_report_labels_all_selected_denominator_and_bounds(run_h3):
    records = [
        h3_record("P1", "S01", "two_tier", 0, selected_poi_ids=["p_food", "p_unknown"]),
    ]
    metrics = run_h3(h3_manifest(profiles=("P1",), scenarios=("S01",)), records)
    report = _h3_report(metrics)
    assert "resolved selected stops" not in report
    assert "denominator = ALL selected stops" in report
    assert "share=null" in report
    assert "bounds=[0.5, 1]" in report
    assert "coverage=0.5" in report
    assert "resolved_subset=1" in report
    assert "not H3 results" in report
