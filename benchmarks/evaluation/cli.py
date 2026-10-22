"""Command-line interface for the OC-018 offline evaluator.

Examples (run from the repository root)::

    python benchmarks/evaluation/evaluator.py h2 \
        --manifest benchmarks/evaluation/fixtures/h2_smoke_manifest.json \
        --records  benchmarks/evaluation/fixtures/h2_smoke_records.jsonl \
        --out      .tmp-evaluation

    python benchmarks/evaluation/evaluator.py h3 ...
    python benchmarks/evaluation/evaluator.py smoke --out .tmp-evaluation

The CLI writes **only** inside the supplied ``--out`` directory and refuses to
overwrite any input manifest or records file.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .common import EVALUATOR_VERSION, SYNTHETIC_LABEL, sha256_bytes, sha256_file
from .errors import EvaluationError
from .h2 import evaluate_h2, load_h2_records, parse_h2_manifest
from .h3 import evaluate_h3, load_h3_records, parse_h3_manifest
from .io_utils import read_json, read_jsonl

FIXTURES = Path(__file__).resolve().parent / "fixtures"

SYNTHETIC_MARKER = (
    "SYNTHETIC EVALUATOR TEST\n"
    "========================\n\n"
    "The output in this directory was produced by the OC-018 evaluator running on\n"
    "hand-authored synthetic fixtures. It is an ENGINEERING SMOKE TEST of the\n"
    "evaluator code, NOT a real H2/H3 study result and NOT the original dataset.\n"
    "Synthetic output must never be reported as a thesis conclusion.\n"
)


def _prepare_out_dir(out: Optional[str], protected: Sequence[Path]) -> Path:
    if not out:
        raise EvaluationError("--out is required; the evaluator never writes implicitly")
    resolved = Path(out).expanduser().resolve()
    if resolved.exists() and not resolved.is_dir():
        raise EvaluationError(f"--out exists and is not a directory: {resolved}")
    resolved.mkdir(parents=True, exist_ok=True)
    protected_set = {path.resolve() for path in protected}
    if resolved in protected_set:
        raise EvaluationError("--out must not be an input file")
    return resolved


def _write_text(path: Path, text: str, protected: Sequence[Path]) -> None:
    if path.resolve() in {item.resolve() for item in protected}:
        raise EvaluationError(f"refusing to overwrite an input file: {path}")
    # Write raw UTF-8 bytes so the on-disk file is byte-identical to the hashed
    # payload (no platform newline translation).
    path.write_bytes(text.encode("utf-8"))


def _write_json(path: Path, value: Any, protected: Sequence[Path]) -> bytes:
    text = json.dumps(value, indent=2, ensure_ascii=False, sort_keys=False) + "\n"
    _write_text(path, text, protected)
    return text.encode("utf-8")


def _run_manifest(task: str, inputs: Dict[str, Optional[str]], metrics_bytes: bytes,
                  extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "task": task,
        "evaluator_version": EVALUATOR_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_sha256": inputs,
        "output_sha256": sha256_bytes(metrics_bytes),
        "no_live_execution": True,
    }
    if extra:
        payload.update(extra)
    return payload


def _load_h2(manifest_path: Path, records_path: Path) -> Dict[str, Any]:
    manifest = parse_h2_manifest(read_json(manifest_path))
    records = load_h2_records(read_jsonl(records_path), manifest)
    return evaluate_h2(
        manifest, records,
        manifest_sha256=sha256_file(manifest_path),
        records_sha256=sha256_file(records_path),
    )


def _load_h3(manifest_path: Path, records_path: Path) -> Dict[str, Any]:
    manifest = parse_h3_manifest(read_json(manifest_path))
    records = load_h3_records(read_jsonl(records_path), manifest)
    return evaluate_h3(
        manifest, records,
        manifest_sha256=sha256_file(manifest_path),
        records_sha256=sha256_file(records_path),
    )


def _h2_report(metrics: Dict[str, Any]) -> str:
    lines = [f"H2 evaluation â€” {metrics['label']}",
             f"manifest={metrics['manifest_version']} thesis_mode={metrics['thesis_mode']}",
             f"evidence={metrics['evidence_levels']} dataset={metrics['dataset_kinds']}",
             f"planned_runs={metrics['planned_runs']} observed_runs={metrics['observed_runs']} "
             f"missing_runs={metrics['missing_runs']}", ""]
    lines.append("per-condition descriptive metrics (planned denominator):")
    for condition, block in metrics["conditions"].items():
        lines.append(
            f"  {condition}: delivery={_fmt(block['delivery_rate'])} "
            f"validated_feasible={_fmt(block['validated_feasibility_rate'])} "
            f"unverifiable={_fmt(block['unverifiable_rate'])} "
            f"refusal={_fmt(block['refusal_rate'])} "
            f"failure={_fmt(block['failure_rate'])} empty={_fmt(block['empty_rate'])}")
        determined = block["determined_violation_rate"]
        lower = block["observed_known_violation_lower_bound"]
        lines.append(
            f"      violation_determined={_fmt(determined['value'])} "
            f"({determined['numerator']}/{determined['denominator']} determined delivered, "
            f"coverage={_fmt(determined['coverage'])} of "
            f"{determined['delivered_denominator']} delivered); "
            f"observed_known_violation_lower_bound(all delivered)="
            f"{_fmt(lower['value'])} ({lower['numerator']}/{lower['denominator']})")
    paired = metrics["paired_inference"]
    lines.append("")
    lines.append(f"paired outcome={paired['declared_binary_outcome']} "
                 f"({paired['condition_a']} - {paired['condition_b']})")
    lines.append(f"  eligible_scenarios={paired['eligible_scenarios']} "
                 f"excluded={len(paired['excluded_scenarios'])}")
    lines.append(f"  rate_a={_fmt(paired['condition_a_positive_rate'])} "
                 f"rate_b={_fmt(paired['condition_b_positive_rate'])}")
    lines.append(f"  discordant a_only={paired['discordant']['a_positive_b_negative']} "
                 f"b_only={paired['discordant']['b_positive_a_negative']}")
    if paired["inferential_available"]:
        lines.append(f"  mcnemar_exact_p={_fmt(paired['mcnemar_exact']['p_value'])}")
    else:
        lines.append("  mcnemar_exact_p=suppressed (no inferential claim; "
                     f"blocked_reasons={paired['blocked_reasons']})")
    boot = paired["bootstrap"]
    if boot["available"]:
        lines.append(f"  paired_effect={_fmt(boot['point'])} "
                     f"95%CI=[{_fmt(boot['lower'])}, {_fmt(boot['upper'])}] "
                     f"(seed={boot['seed']}, draws={boot['draws']}, percentile)")
    else:
        lines.append(f"  paired_effect={_fmt(boot['point'])} "
                     f"CI unavailable ({boot['reason']})")
    lines.append(f"  inferential_available={paired['inferential_available']} "
                 f"blocked_reasons={paired['blocked_reasons']}")
    lines.append("")
    observed = metrics["observed_runs"]
    secondary = metrics["secondary_outcomes"]
    lines.append(f"secondary outcomes (available/missing over {observed} observed runs; "
                 "only aggregating already-computed fields):")
    grounding = secondary["poi_grounding"]
    lines.append(_secondary_line(
        "poi_grounding", grounding["records_with_ids"], observed,
        f"selected={grounding['selected_total']} grounded={grounding['grounded_total']} "
        f"grounded_rate={_fmt(grounding['grounded_rate'])}"))
    budget = secondary["budget_deviation"]
    budget_available = sum(group["n"] for group in budget["groups"]) \
        + budget["non_comparable_records"]
    lines.append(_secondary_line(
        "budget_deviation", budget_available, observed,
        f"non_comparable={budget['non_comparable_records']} "
        f"groups={len(budget['groups'])} pooled_across_units={budget['pooled_across_units']}"))
    for key in ("route_travel_minutes", "route_distance_km", "latency_seconds"):
        series = secondary[key]
        lines.append(_secondary_line(
            f"{key} [{series['unit']}]", series["n"], observed,
            f"median={_fmt(series['median'])} mean={_fmt(series['mean'])} "
            f"min={_fmt(series['min'])} max={_fmt(series['max'])}"))
    if metrics["paired_inference"]["declared_binary_outcome"]:
        lines.append("  (secondary outcomes carry no p-value or inferential claim.)")
    if metrics["label"] == SYNTHETIC_LABEL:
        lines.append("NOTE: synthetic numbers above are evaluator tests, not H2 results.")
    if metrics["diagnostics"]:
        lines.append("")
        lines.append("diagnostics:")
        lines.extend(f"  - {item}" for item in metrics["diagnostics"])
    return "\n".join(lines) + "\n"


def _h3_report(metrics: Dict[str, Any]) -> str:
    lines = [f"H3 evaluation â€” {metrics['label']}",
             f"manifest={metrics['manifest_version']} thesis_mode={metrics['thesis_mode']}",
             f"evidence={metrics['evidence_levels']} dataset={metrics['dataset_kinds']}",
             f"profiles={metrics['profiles']} baseline={metrics['baseline_condition']}",
             f"planned_runs={metrics['planned_runs']} observed_runs={metrics['observed_runs']} "
             f"missing_runs={metrics['missing_runs']}", ""]
    lines.append("per-profile preferred share "
                 "(numerator = preferred selected stops; denominator = ALL selected "
                 "stops; null = coverage gap, see bounds):")
    for effect in metrics["profile_effects"]:
        effect_keys = [key for key in effect if key.startswith("preferred_share_effect_")]
        effects = ", ".join(f"{key.replace('preferred_share_effect_', '')}={_fmt(effect[key])}"
                            for key in effect_keys)
        lines.append(f"  {effect['profile_id']}: effects: {effects}")
        details = effect["preferred_share_detail_by_condition"]
        for condition in metrics["conditions"]:
            detail = details[condition]
            lines.append(f"      {condition}: {_h3_share_text(detail)}")
            if detail["reason"] and detail["value"] is None:
                lines.append(f"          reason={detail['reason']}")
        reductions = effect["token_reduction_by_condition"]
        for condition, reduction in reductions.items():
            lines.append(f"      token_reduction[{condition}]={_fmt(reduction['value'])} "
                         f"({reduction['reason'] or 'defined'})")
    if metrics["label"] == SYNTHETIC_LABEL:
        lines.append("NOTE: synthetic numbers above are evaluator tests, not H3 results.")
    if metrics["diagnostics"]:
        lines.append("")
        lines.append("diagnostics:")
        lines.extend(f"  - {item}" for item in metrics["diagnostics"])
    return "\n".join(lines) + "\n"


def _h3_share_text(detail: Dict[str, Any]) -> str:
    base = (f"share={_fmt(detail['value'])} "
            f"({detail['preferred']}/{detail['selected_total']} selected stops preferred)")
    if detail["value"] is None:
        base += (f" bounds=[{_fmt(detail['lower'])}, {_fmt(detail['upper'])}] "
                 f"coverage={_fmt(detail['coverage'])} "
                 f"resolved_subset={_fmt(detail['resolved_subset_share'])}")
    else:
        base += f" coverage={_fmt(detail['coverage'])}"
    return base


def _fmt(value: Optional[float]) -> str:
    if value is None:
        return "null"
    return f"{value:.6g}"


def _secondary_line(name: str, available: int, total: int, extra: str = "") -> str:
    suffix = f" {extra}" if extra else ""
    return f"  {name}: available={available} missing={total - available}{suffix}"


def command_h2(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest).resolve()
    records_path = Path(args.records).resolve()
    protected = [manifest_path, records_path]
    out_dir = _prepare_out_dir(args.out, protected)
    metrics = _load_h2(manifest_path, records_path)
    metrics_bytes = _write_json(out_dir / "h2_metrics.json", metrics, protected)
    _write_text(out_dir / "h2_report.txt", _h2_report(metrics), protected)
    run_manifest = _run_manifest(
        "H2", {"manifest": sha256_file(manifest_path),
               "records": sha256_file(records_path)}, metrics_bytes,
        extra={"label": metrics["label"], "inferential_available":
               metrics["paired_inference"]["inferential_available"]})
    _write_json(out_dir / "h2_run_manifest.json", run_manifest, protected)
    sys.stdout.write(_h2_report(metrics))
    sys.stdout.write(f"\noutputs written to {out_dir}\n")
    return 0


def command_h3(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest).resolve()
    records_path = Path(args.records).resolve()
    protected = [manifest_path, records_path]
    out_dir = _prepare_out_dir(args.out, protected)
    metrics = _load_h3(manifest_path, records_path)
    metrics_bytes = _write_json(out_dir / "h3_metrics.json", metrics, protected)
    _write_text(out_dir / "h3_report.txt", _h3_report(metrics), protected)
    run_manifest = _run_manifest(
        "H3", {"manifest": sha256_file(manifest_path),
               "records": sha256_file(records_path)}, metrics_bytes,
        extra={"label": metrics["label"]})
    _write_json(out_dir / "h3_run_manifest.json", run_manifest, protected)
    sys.stdout.write(_h3_report(metrics))
    sys.stdout.write(f"\noutputs written to {out_dir}\n")
    return 0


def command_smoke(args: argparse.Namespace) -> int:
    h2_manifest = (FIXTURES / "h2_smoke_manifest.json").resolve()
    h2_records = (FIXTURES / "h2_smoke_records.jsonl").resolve()
    h3_manifest = (FIXTURES / "h3_smoke_manifest.json").resolve()
    h3_records = (FIXTURES / "h3_smoke_records.jsonl").resolve()
    protected = [h2_manifest, h2_records, h3_manifest, h3_records]
    out_dir = _prepare_out_dir(args.out, protected)

    sys.stdout.write(SYNTHETIC_MARKER + "\n")
    _write_text(out_dir / "SYNTHETIC_EVALUATOR_TEST.txt", SYNTHETIC_MARKER, protected)

    h2_metrics = _load_h2(h2_manifest, h2_records)
    h2_bytes = _write_json(out_dir / "h2_metrics.json", h2_metrics, protected)
    _write_text(out_dir / "h2_report.txt", _h2_report(h2_metrics), protected)
    _write_json(out_dir / "h2_run_manifest.json",
                _run_manifest("H2", {"manifest": sha256_file(h2_manifest),
                                     "records": sha256_file(h2_records)}, h2_bytes,
                              extra={"label": h2_metrics["label"]}), protected)

    h3_metrics = _load_h3(h3_manifest, h3_records)
    h3_bytes = _write_json(out_dir / "h3_metrics.json", h3_metrics, protected)
    _write_text(out_dir / "h3_report.txt", _h3_report(h3_metrics), protected)
    _write_json(out_dir / "h3_run_manifest.json",
                _run_manifest("H3", {"manifest": sha256_file(h3_manifest),
                                     "records": sha256_file(h3_records)}, h3_bytes,
                              extra={"label": h3_metrics["label"]}), protected)

    combined = {
        "label": SYNTHETIC_LABEL,
        "warning": ("Generated demonstration output. Synthetic fixtures only; not a real "
                    "H2/H3 study result and not the original dataset."),
        "evaluator_version": EVALUATOR_VERSION,
        "h2": h2_metrics,
        "h3": h3_metrics,
    }
    _write_json(out_dir / "smoke_demo.json", combined, protected)

    sys.stdout.write(_h2_report(h2_metrics))
    sys.stdout.write(_h3_report(h3_metrics))
    sys.stdout.write(f"\n{out_dir}\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="evaluator",
        description="OC-018 offline evaluator for paired H2 / H3 recorded outcomes.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    h2 = subparsers.add_parser("h2", help="evaluate paired H2 itinerary outcomes")
    h2.add_argument("--manifest", required=True, help="frozen H2 manifest JSON")
    h2.add_argument("--records", required=True, help="H2 raw outcome JSONL")
    h2.add_argument("--out", required=True, help="output directory (created if absent)")
    h2.set_defaults(func=command_h2)

    h3 = subparsers.add_parser("h3", help="evaluate H3 memory-profile outcomes")
    h3.add_argument("--manifest", required=True, help="frozen H3 manifest JSON")
    h3.add_argument("--records", required=True, help="H3 raw outcome JSONL")
    h3.add_argument("--out", required=True, help="output directory (created if absent)")
    h3.set_defaults(func=command_h3)

    smoke = subparsers.add_parser(
        "smoke", help="run packaged SYNTHETIC fixtures and write a labelled demo")
    smoke.add_argument("--out", required=True, help="output directory (created if absent)")
    smoke.set_defaults(func=command_smoke)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except EvaluationError as exc:
        sys.stderr.write(f"evaluator error: {exc}\n")
        return 2
