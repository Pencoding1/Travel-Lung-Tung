"""EXP092 bounded supervisor for one collector child process (stdlib only).

The supervisor is a *client-side* deadline guard.  It validates the same input,
frozen-manifest, output and journal gates as the collector without creating any
of those paths, then launches exactly one task-owned Python child::

    python -B -X utf8 -m benchmarks.spatial_live.runner --execute \\
        --input <path> --manifest <frozen.json> --output <new.json>

No shell, interpolation, endpoint override, secret inspection, bypass mode or
restart is available.  Raw child stdout/stderr are discarded.  The worker keeps
sole ownership of the output/journal lock.

A hard deadline (default 3600 s) starts at child launch.  On timeout only this
child is terminated, then reaped with bounded waits (<=5 s terminate, <=5 s
kill).  Cleanup failures are recorded, never retried.  The supervisor JSON is a
separate atomically replaced ``<output>.supervisor.json`` and never claims the
worker succeeded or invents timings.

A hard client kill is not proof that an in-flight engine transaction was
cancelled; the worker's last durable journal unit remains inspectable and any
in-flight unit is unknown/missing.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

try:  # pragma: no cover - import shape depends on invocation style
    from . import journal as journal_module
    from . import runner
except ImportError:  # direct script execution
    import journal as journal_module  # type: ignore[no-redef]
    import runner  # type: ignore[no-redef]

SUPERVISOR_SCHEMA = "exp092.supervisor.v1"
TASK_ID = "EXP092"
DEFAULT_TIMEOUT_SECONDS = 3600.0
CLEANUP_BUDGET_SECONDS = 10.0
_TERMINATE_WAIT_SECONDS = 5.0
_KILL_WAIT_SECONDS = 5.0

Runner = runner


def supervisor_path_for(output_path: Path | str) -> Path:
    output = Path(output_path)
    return output.with_name(output.name + ".supervisor.json")


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def child_argv(input_path: Path | str, manifest_path: Path | str, output_path: Path | str) -> list[str]:
    """Fixed list argv; no shell and no caller-controlled flags."""
    return [
        sys.executable,
        "-B",
        "-X",
        "utf8",
        "-m",
        "benchmarks.spatial_live.runner",
        "--execute",
        "--input",
        str(Path(input_path).resolve()),
        "--manifest",
        str(Path(manifest_path).resolve()),
        "--output",
        str(Path(output_path).resolve()),
    ]


def preflight(
    input_path: Path | str,
    manifest_path: Path | str,
    output_path: Path | str,
) -> tuple[Mapping[str, Any], str, str]:
    """Validate input/manifest/output gates without creating anything.

    Returns ``(manifest, manifest_sha256, input_sha256)``.  Raises
    :class:`runner.CollectorError` on refusal, before any child is spawned.
    """
    records, input_sha256 = runner.load_records(input_path)
    manifest, manifest_sha256 = runner.load_manifest(manifest_path)
    runner.validate_manifest(
        manifest,
        records,
        input_path,
        input_sha256,
        require_frozen=True,
    )
    if runner.resolve_collection_mode(manifest) == runner.COLLECTION_MODE_TIMING_ONLY:
        runner.validate_external_correctness_reference(
            manifest, records, input_sha256
        )

    output = Path(output_path)
    if output.exists() and output.stat().st_size > 0:
        raise runner.CollectorError("output_not_empty")
    if journal_module.journal_path_for(output).exists():
        raise runner.CollectorError("journal_exists")
    if supervisor_path_for(output).exists():
        raise runner.CollectorError("supervisor_report_exists")
    if output.with_name(output.name + ".lock").exists():
        raise runner.CollectorError("output_locked")
    return manifest, manifest_sha256, input_sha256


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}.{time.monotonic_ns()}")
    descriptor = os.open(str(tmp), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _cleanup_child(
    process: subprocess.Popen[Any],
    *,
    clock: Callable[[], float],
) -> dict[str, Any]:
    """Terminate then kill only this exact child, with bounded waits.

    Every cleanup call (terminate, both waits, kill) is guarded; a failure is
    recorded as a closed stage/type pair and never re-raised or retried.
    """
    cleanup: dict[str, Any] = {
        "target_pid": process.pid,
        "terminate_attempted": False,
        "terminate_error": None,
        "terminate_wait_seconds": 0.0,
        "reaped_after_terminate": False,
        "kill_attempted": False,
        "kill_error": None,
        "kill_wait_seconds": 0.0,
        "reaped_after_kill": False,
        "failure": None,
        "errors": [],
    }

    def note(stage: str, exc: BaseException) -> None:
        cleanup["errors"].append({"stage": stage, "type": type(exc).__name__})
        if cleanup["failure"] is None:
            cleanup["failure"] = f"{stage}_error"

    started = clock()
    cleanup["terminate_attempted"] = True
    try:
        process.terminate()
    except Exception as exc:  # sanitized type only
        cleanup["terminate_error"] = type(exc).__name__
        note("terminate", exc)

    try:
        process.wait(timeout=_TERMINATE_WAIT_SECONDS)
        cleanup["reaped_after_terminate"] = True
    except subprocess.TimeoutExpired:
        pass
    except Exception as exc:  # sanitized type only
        cleanup["terminate_wait_error"] = type(exc).__name__
        note("terminate_wait", exc)
    cleanup["terminate_wait_seconds"] = round(clock() - started, 6)

    if not cleanup["reaped_after_terminate"]:
        cleanup["kill_attempted"] = True
        kill_started = clock()
        try:
            process.kill()
        except Exception as exc:  # sanitized type only
            cleanup["kill_error"] = type(exc).__name__
            note("kill", exc)
        try:
            process.wait(timeout=_KILL_WAIT_SECONDS)
            cleanup["reaped_after_kill"] = True
        except subprocess.TimeoutExpired:
            if cleanup["failure"] is None:
                cleanup["failure"] = "kill_wait_timeout"
        except Exception as exc:  # sanitized type only
            cleanup["kill_wait_error"] = type(exc).__name__
            note("kill_wait", exc)
        cleanup["kill_wait_seconds"] = round(clock() - kill_started, 6)

    if not (cleanup["reaped_after_terminate"] or cleanup["reaped_after_kill"]):
        if cleanup["failure"] is None:
            cleanup["failure"] = "child_not_reaped"
    return cleanup


def run_supervisor(
    input_path: Path | str,
    manifest_path: Path | str,
    output_path: Path | str,
    *,
    timeout_seconds: float | None = None,
    popen_factory: Callable[..., subprocess.Popen[Any]] | None = None,
    child_command: Sequence[str] | None = None,
    clock: Callable[[], float] = time.monotonic,
    utc_now: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Preflight, spawn exactly one child, wait and write the supervisor JSON.

    The execution budget is resolved only from the validated manifest mode
    (full = 3600 s, timing-only = 7200 s).  ``timeout_seconds`` remains a
    Python-API test seam for the legacy full mode; the CLI has no override and
    a timing-only manifest rejects a mismatched explicit value before spawn.
    """
    utc_now = utc_now or (lambda: datetime.now(timezone.utc))
    manifest, _manifest_sha256, _input_sha256 = preflight(
        input_path, manifest_path, output_path
    )
    mode = runner.resolve_collection_mode(manifest)
    if timeout_seconds is None:
        resolved_budget = float(runner.resolve_run_budget(manifest))
        timeout_seconds = resolved_budget
    else:
        timeout_seconds = runner._finite_number(timeout_seconds)
        if mode == runner.COLLECTION_MODE_TIMING_ONLY:
            resolved_budget = float(runner.resolve_run_budget(manifest))
            if timeout_seconds != resolved_budget:
                raise runner.CollectorError("supervisor_budget_override_rejected")

    output = Path(output_path)
    report_path = supervisor_path_for(output)
    journal_path = journal_module.journal_path_for(output)
    argv = list(child_command) if child_command is not None else child_argv(
        input_path, manifest_path, output_path
    )
    factory = popen_factory or subprocess.Popen

    report: dict[str, Any] = {
        "schema": SUPERVISOR_SCHEMA,
        "task_id": TASK_ID,
        "protocol": journal_module.PROTOCOL,
        "status": "starting",
        "mode": "supervised_execute",
        "collection_mode": mode,
        "scientific_result": False,
        "argv": argv,
        "input_path": str(input_path),
        "manifest_path": str(manifest_path),
        "output_path": str(output),
        "journal_path": str(journal_path),
        "supervisor_path": str(report_path),
        "timeout_seconds": float(timeout_seconds),
        "execution_budget_seconds": float(timeout_seconds),
        "budget_source": "validated_manifest_mode",
        "cleanup_budget_seconds": CLEANUP_BUDGET_SECONDS,
        "started_utc": _utc_iso(utc_now()),
        "finished_utc": None,
        "duration_seconds": None,
        "deadline_origin_monotonic": None,
        "exit_code": None,
        "timed_out": False,
        "child_spawned": False,
        "pid": None,
        "cleanup": None,
        "output_exists": False,
        "journal_exists": False,
        "notes": [
            "hard client execution deadline plus up to 10 s bounded cleanup",
            "no claim of instantaneous engine transaction cancellation",
            "worker journal is the durable completed-unit evidence",
        ],
    }

    started = clock()
    report["deadline_origin_monotonic"] = started
    try:
        process = factory(
            argv,
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=str(runner.REPO_ROOT),
        )
    except Exception as exc:  # sanitized type only
        report["status"] = "spawn_failed"
        report["spawn_error"] = type(exc).__name__
        report["finished_utc"] = _utc_iso(utc_now())
        report["duration_seconds"] = round(clock() - started, 6)
        _atomic_write_json(report_path, report)
        return report

    report["child_spawned"] = True
    report["pid"] = process.pid
    timed_out = False
    timed_out_error: str | None = None
    wait_error_type: str | None = None
    interrupted = False

    # Same persisted pre-launch origin: spawn cost consumes the deadline.
    remaining = timeout_seconds - (clock() - started)
    report["remaining_after_spawn_seconds"] = round(remaining, 6)

    def _poll_safely() -> Any:
        try:
            return process.poll()
        except BaseException as exc:  # sanitized type only, never a message
            report["poll_error"] = type(exc).__name__
            return None

    if remaining <= 0:
        timed_out = True
        timed_out_error = "deadline_exhausted_at_spawn"
        report["timed_out"] = True
        report["cleanup"] = _cleanup_child(process, clock=clock)
        exit_code = _poll_safely()
    else:
        try:
            exit_code = process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            timed_out = True
            timed_out_error = "deadline_exceeded"
            report["timed_out"] = True
            report["cleanup"] = _cleanup_child(process, clock=clock)
            exit_code = _poll_safely()
        except KeyboardInterrupt:
            interrupted = True
            report["interrupted"] = True
            report["cleanup"] = _cleanup_child(process, clock=clock)
            exit_code = _poll_safely()
        except Exception as exc:  # sanitized type only; never the message
            wait_error_type = type(exc).__name__
            report["wait_error"] = wait_error_type
            report["cleanup"] = _cleanup_child(process, clock=clock)
            exit_code = _poll_safely()

    report["exit_code"] = exit_code
    report["duration_seconds"] = round(clock() - started, 6)
    report["finished_utc"] = _utc_iso(utc_now())
    report["output_exists"] = output.exists()
    report["journal_exists"] = journal_path.exists()

    if interrupted:
        report["status"] = "interrupted"
        report["terminal_note"] = (
            "interruption recorded; owned child cleanup attempted; worker "
            "result is not inferred"
        )
    elif timed_out:
        report["status"] = "timeout"
        report["deadline_error"] = timed_out_error
        report["terminal_note"] = (
            "worker result is not inferred; inspect the output/journal evidence"
        )
    elif wait_error_type is not None:
        report["status"] = "wait_error"
        report["terminal_note"] = (
            "child wait failed; owned child cleanup attempted; worker result "
            "is not inferred"
        )
    elif exit_code == 0:
        report["status"] = "child_exit_zero"
        report["terminal_note"] = (
            "worker result is not inferred; inspect the output/journal evidence"
        )
    else:
        report["status"] = "child_nonzero_exit"
        report["terminal_note"] = (
            "worker result is not inferred; inspect the output/journal evidence"
        )
    _atomic_write_json(report_path, report)
    if interrupted:
        raise KeyboardInterrupt
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "EXP092 bounded supervisor: one fixed read-only collector child with "
            "a 3600 s hard client deadline and bounded cleanup."
        )
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = run_supervisor(args.input, args.manifest, args.output)
    except runner.CollectorError as exc:
        print(
            json.dumps(
                {
                    "schema": SUPERVISOR_SCHEMA,
                    "task_id": TASK_ID,
                    "status": "blocked",
                    "mode": "supervised_execute",
                    "scientific_result": False,
                    "child_spawned": False,
                    "error": exc.as_dict(),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 2
    print(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False))
    if report["status"] == "child_exit_zero":
        return 0
    if report["status"] == "timeout":
        return 3
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
