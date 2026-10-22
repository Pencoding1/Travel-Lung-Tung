"""EXP092 offline durability/bounded-execution tests (synthetic only).

No driver, socket, engine, model or real E2 run is used.  Subprocesses are
local Python dummy children.  All fake SQL/JSONL worlds come from the existing
EXP089 test helpers so scientific criteria are not redefined here.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from benchmarks.spatial_live import journal, runner, supervisor  # noqa: E402


def _load_helpers():
    path = Path(__file__).with_name("test_runner.py")
    spec = importlib.util.spec_from_file_location("exp092_test_helpers", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


H = _load_helpers()


def _world(tmp_path: Path, count: int = 2):
    rows = [
        H.make_raw_record(f"p{index:04d}", 10.0 + index * 0.0005, 106.0 + index * 0.0005)
        for index in range(count)
    ]
    return H.make_world(tmp_path, rows)


def _binding(records, manifest):
    return runner.journal_binding(manifest, "a" * 64, "b" * 64)


def _new_journal(tmp_path: Path, records, manifest):
    path = tmp_path / "result.json.journal.jsonl"
    sink = journal.DurableJournal.open_new(
        path,
        binding=_binding(records, manifest),
        planned=runner.journal_planned_denominator(records),
    )
    return sink, path


def _assert_code(callable_obj, code):
    with pytest.raises(runner.CollectorError) as caught:
        callable_obj()
    assert caught.value.code == code


# ---------------------------------------------------------------------------
# A. Header / chain / binding / torn tail / no reuse
# ---------------------------------------------------------------------------


def test_journal_roundtrip_and_binding_checks(tmp_path):
    _, records, _ = _world(tmp_path)
    manifest = H.make_manifest(tmp_path / "input.jsonl", records)
    sink, path = _new_journal(tmp_path, records, manifest)
    sink.append("correctness_batch", {"radius_km": 1.0, "index": 0, "status": "success"})
    sink.close()

    read = journal.read_journal(path, expected_binding=_binding(records, manifest))
    assert read.incomplete_tail is False
    assert [record["kind"] for record in read.events] == ["correctness_batch"]
    assert read.planned["timing_cells_total"] == 36
    assert read.binding["protocol"] == "exp092.durable.v1"

    with pytest.raises(journal.JournalError) as caught:
        journal.read_journal(path, expected_binding={"protocol": "other"})
    assert caught.value.code == "journal_foreign_binding"

    with pytest.raises(journal.JournalError) as caught:
        journal.DurableJournal.open_new(
            path, binding={}, planned={}
        )
    assert caught.value.code == "journal_exists"


def test_journal_rejects_interior_corruption_and_bad_sequence(tmp_path):
    _, records, _ = _world(tmp_path)
    manifest = H.make_manifest(tmp_path / "input.jsonl", records)
    sink, path = _new_journal(tmp_path, records, manifest)
    sink.append("unit", {"n": 1})
    sink.close()

    good = path.read_bytes()
    corrupted = good.replace(b'"kind":"unit"', b'"kind":"unix"')
    path.write_bytes(corrupted)
    with pytest.raises(journal.JournalError) as caught:
        journal.read_journal(path)
    assert caught.value.code == "journal_checksum_invalid"

    path.write_bytes(good)
    lines = good.split(b"\n")
    path.write_bytes(good + lines[1] + b"\n")
    with pytest.raises(journal.JournalError) as caught:
        journal.read_journal(path)
    assert caught.value.code == "journal_sequence_invalid"


def test_torn_final_line_is_explicit_incomplete_tail_and_prefix_untouched(tmp_path):
    _, records, _ = _world(tmp_path)
    manifest = H.make_manifest(tmp_path / "input.jsonl", records)
    sink, path = _new_journal(tmp_path, records, manifest)
    sink.append("unit", {"n": 1})
    sink.close()

    prefix = path.read_bytes()
    path.write_bytes(prefix + b'{"seq":2,"kind":"torn"')
    read = journal.read_journal(path)
    assert read.incomplete_tail is True
    assert read.incomplete_tail_reason == "unterminated_final_record"
    assert [record["kind"] for record in read.events] == ["unit"]
    assert path.read_bytes().startswith(prefix)


def test_existing_journal_and_nonempty_output_refuse_before_backend(tmp_path):
    input_path, records, _ = _world(tmp_path)
    manifest = H.make_manifest(input_path, records)
    manifest_path = H.write_manifest(tmp_path / "manifest.json", manifest)
    output = tmp_path / "result.json"
    journal_path = journal.journal_path_for(output)
    journal_path.write_bytes(b"prior journal evidence\n")
    called = []

    def factory():
        called.append(True)
        return H.FakeBackend(records)

    _assert_code(
        lambda: runner.execute_collection(
            input_path,
            manifest_path,
            output,
            backend_factory=factory,
            clock=H.FakeClock(),
            on_utc=H.FixedUtc(),
        ),
        "journal_exists",
    )
    assert called == []
    assert journal_path.read_bytes() == b"prior journal evidence\n"

    journal_path.unlink()
    output.write_text("prior output\n", encoding="utf-8")
    _assert_code(
        lambda: runner.execute_collection(
            input_path,
            manifest_path,
            output,
            backend_factory=factory,
            clock=H.FakeClock(),
            on_utc=H.FixedUtc(),
        ),
        "output_not_empty",
    )
    assert called == []
    assert output.read_text(encoding="utf-8") == "prior output\n"


# ---------------------------------------------------------------------------
# B. Durable completed units before the next query / crash survival
# ---------------------------------------------------------------------------


def test_completed_units_are_on_disk_before_next_backend_query(tmp_path):
    input_path, records, _ = _world(tmp_path, count=130)
    manifest = H.make_manifest(input_path, records)
    sink, path = _new_journal(tmp_path, records, manifest)
    observed = {"correctness": [], "timing": []}

    class OrderingBackend(H.FakeBackend):
        def run_query(self, name, text, params, timeout_seconds):
            if name == "baseline":
                observed["correctness"].append(
                    len(journal.read_journal(path).events)
                )
            if name in ("timing_baseline", "timing_optimized"):
                observed["timing"].append(
                    len(
                        [
                            event
                            for event in journal.read_journal(path).events
                            if event["kind"] == "timing_cell"
                        ]
                    )
                )
            return super().run_query(name, text, params, timeout_seconds)

    backend = OrderingBackend(records)
    runner.collect_correctness(
        records,
        1.0,
        backend,
        clock=H.FakeClock(),
        run_started=0.0,
        run_timeout_seconds=3600.0,
        on_utc=H.FixedUtc(),
        on_event=sink.append,
    )
    assert observed["correctness"] == [0, 1]

    observed["timing"].clear()
    runner.collect_timings(
        records,
        backend,
        clock=H.FakeClock(),
        run_started=0.0,
        run_timeout_seconds=3600.0,
        on_utc=H.FixedUtc(),
        on_event=sink.append,
    )
    sink.close()
    assert observed["timing"] == [n for n in range(36) for _ in range(2)]
    read = journal.read_journal(path)
    assert read.incomplete_tail is False
    assert sum(1 for e in read.events if e["kind"] == "timing_cell") == 36
    assert all(e["kind"] != "final_result" for e in read.events)


def test_last_fsynced_unit_survives_dummy_child_os_exit(tmp_path):
    journal_path = tmp_path / "crash.jsonl"
    code = (
        "import os, sys\n"
        f"sys.path.insert(0, {str(REPO_ROOT)!r})\n"
        "from benchmarks.spatial_live import journal\n"
        f"j = journal.DurableJournal.open_new({str(journal_path)!r}, "
        "binding={'protocol': 'exp092.durable.v1'}, planned={'timing_cells_total': 36})\n"
        "j.append('correctness_batch', {'radius_km': 1.0, 'index': 0, 'status': 'success'})\n"
        "os._exit(9)\n"
    )
    completed = subprocess.run(
        [sys.executable, "-B", "-c", code],
        cwd=str(REPO_ROOT),
        capture_output=True,
        timeout=30,
    )
    assert completed.returncode == 9
    read = journal.read_journal(journal_path)  # zero engine calls by construction
    assert read.incomplete_tail is False
    assert [event["kind"] for event in read.events] == ["correctness_batch"]
    assert all(event["kind"] != "final_result" for event in read.events)


# ---------------------------------------------------------------------------
# C. Query timeout clamp and run deadline
# ---------------------------------------------------------------------------


def test_query_timeout_clamped_to_remaining_and_zero_at_deadline():
    seen = []

    class RecordingBackend:
        def run_query(self, name, text, params, timeout_seconds):
            seen.append(timeout_seconds)
            return []

        def close(self):
            return None

    backend = RecordingBackend()
    with pytest.raises(runner.CollectorError) as caught:
        runner._engine_query(
            backend,
            "baseline",
            runner.BASELINE_QUERY,
            {},
            clock=lambda: 10.0,
            run_started=0.0,
            run_timeout_seconds=10.0,
        )
    assert caught.value.code == "run_timeout"
    assert seen == []

    runner._engine_query(
        backend,
        "baseline",
        runner.BASELINE_QUERY,
        {},
        clock=lambda: 3.0,
        run_started=0.0,
        run_timeout_seconds=10.0,
    )
    runner._engine_query(
        backend,
        "baseline",
        runner.BASELINE_QUERY,
        {},
        clock=lambda: 1.0,
        run_started=0.0,
        run_timeout_seconds=10_000.0,
    )
    assert seen == [7.0, 120]


def test_deadline_failure_keeps_committed_journal_and_missing_denominator(tmp_path):
    input_path, records, _ = _world(tmp_path)
    manifest = H.make_manifest(input_path, records)
    sink, path = _new_journal(tmp_path, records, manifest)
    sink.append("earlier_unit", {"kind": "committed"})
    backend = H.FakeBackend(records)
    outcome = runner.collect_correctness(
        records,
        1.0,
        backend,
        clock=lambda: 4_000.0,
        run_started=0.0,
        run_timeout_seconds=3_600.0,
        on_utc=H.FixedUtc(),
        on_event=sink.append,
    )
    sink.close()
    assert outcome["status"] == "incomplete"
    assert outcome["error"]["code"] == "run_timeout"
    assert backend.calls == []
    read = journal.read_journal(path)
    assert any(e["kind"] == "earlier_unit" for e in read.events)
    batch_events = [e for e in read.events if e["kind"] == "correctness_batch"]
    assert batch_events and batch_events[0]["payload"]["status"] == "error"
    assert all(
        e["payload"].get("status") != "success" for e in batch_events
    )


# ---------------------------------------------------------------------------
# D. Journal writer delay is outside measured cell duration
# ---------------------------------------------------------------------------


def test_slow_journal_writer_does_not_change_measured_cell_duration(tmp_path):
    input_path, records, _ = _world(tmp_path)
    backend = H.FakeBackend(records)
    clock = H.FakeClock(step=0.25)

    def slow_sink(kind, payload):
        time.sleep(0.005)

    cells = runner.collect_timings(
        records,
        backend,
        clock=clock,
        run_started=1_000.0,
        run_timeout_seconds=3600.0,
        on_utc=H.FixedUtc(),
        on_event=slow_sink,
    )
    assert len(cells) == 36
    assert sum(1 for c in cells if c["phase"] == "warmup") == 6
    assert all(c["status"] == "success" for c in cells)
    assert all(c["duration_seconds"] == 0.5 for c in cells)
    assert "RETURN count(*) AS accepted_pairs" in runner.TIMING_BASELINE_QUERY
    assert "a_id" not in runner.TIMING_BASELINE_QUERY
    assert runner.query_hashes()["timing_baseline"] == runner.query_hashes()[
        "timing_baseline"
    ]


# ---------------------------------------------------------------------------
# E. Auth denial is terminal, sanitized and journaled
# ---------------------------------------------------------------------------


def test_auth_denial_records_terminal_event_without_raw_text(tmp_path):
    input_path, records, _ = _world(tmp_path)
    manifest = H.make_manifest(input_path, records)
    manifest_path = H.write_manifest(tmp_path / "manifest.json", manifest)
    output = tmp_path / "result.json"
    backend = H.FakeBackend(
        records,
        fail_query_numbers={
            6: H.CodedAuthError(
                "Neo.ClientError.Security.Unauthorized", "raw-auth-diagnostic"
            )
        },
    )
    result = runner.execute_collection(
        input_path,
        manifest_path,
        output,
        backend_factory=lambda: backend,
        clock=H.FakeClock(),
        on_utc=H.FixedUtc(),
    )
    assert result["correctness"][0]["error"]["code"] == "engine_auth_denied"
    assert len(backend.calls) == 6
    assert result["timings"] and all(c["status"] == "missing" for c in result["timings"])

    journal_path = journal.journal_path_for(output)
    text = journal_path.read_text(encoding="utf-8")
    assert "raw-auth-diagnostic" not in text
    assert "password" not in text
    read = journal.read_journal(journal_path)
    denied = [
        event
        for event in read.events
        if event["kind"] == "correctness_batch"
        and event["payload"].get("status") == "error"
    ]
    assert denied and denied[0]["payload"]["error"]["code"] == "engine_auth_denied"
    assert "raw-auth-diagnostic" not in output.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# F. Supervisor: one child, fixed argv, bounded cleanup, zero-child refusals
# ---------------------------------------------------------------------------


def test_supervisor_one_child_natural_exit_and_no_relaunch(tmp_path):
    input_path, records, _ = _world(tmp_path)
    manifest = H.make_manifest(input_path, records)
    manifest_path = H.write_manifest(tmp_path / "manifest.json", manifest)
    spawns = []

    def factory(*args, **kwargs):
        spawns.append((args, kwargs))
        return subprocess.Popen(*args, **kwargs)

    report = supervisor.run_supervisor(
        input_path,
        manifest_path,
        tmp_path / "ok.json",
        popen_factory=factory,
        child_command=[sys.executable, "-B", "-c", "import sys; sys.exit(0)"],
    )
    assert report["status"] == "child_exit_zero"
    assert report["exit_code"] == 0
    assert len(spawns) == 1
    assert spawns[0][1]["shell"] is False
    assert (tmp_path / "ok.json.supervisor.json").exists()

    report = supervisor.run_supervisor(
        input_path,
        manifest_path,
        tmp_path / "bad.json",
        popen_factory=factory,
        child_command=[sys.executable, "-B", "-c", "import sys; sys.exit(4)"],
    )
    assert report["status"] == "child_nonzero_exit"
    assert report["exit_code"] == 4
    assert len(spawns) == 2


def test_supervisor_refusals_spawn_zero_children(tmp_path):
    input_path, records, _ = _world(tmp_path)
    manifest = H.make_manifest(input_path, records)
    manifest_path = H.write_manifest(tmp_path / "manifest.json", manifest)
    calls = []

    def factory(*args, **kwargs):
        calls.append(True)
        return subprocess.Popen(*args, **kwargs)

    old = dict(manifest)
    old.pop("sources")
    old_path = H.write_manifest(tmp_path / "old.json", old)
    with pytest.raises(runner.CollectorError) as caught:
        supervisor.run_supervisor(
            input_path, old_path, tmp_path / "a.json", popen_factory=factory
        )
    assert caught.value.code == "manifest_source_pins_missing"

    output = tmp_path / "b.json"
    output.write_text("prior\n", encoding="utf-8")
    with pytest.raises(runner.CollectorError) as caught:
        supervisor.run_supervisor(
            input_path, manifest_path, output, popen_factory=factory
        )
    assert caught.value.code == "output_not_empty"
    assert output.read_text(encoding="utf-8") == "prior\n"

    output2 = tmp_path / "c.json"
    journal.journal_path_for(output2).write_text("held\n", encoding="utf-8")
    with pytest.raises(runner.CollectorError) as caught:
        supervisor.run_supervisor(
            input_path, manifest_path, output2, popen_factory=factory
        )
    assert caught.value.code == "journal_exists"
    assert calls == []


def test_supervisor_timeout_kills_only_its_own_child(tmp_path):
    input_path, records, _ = _world(tmp_path)
    manifest = H.make_manifest(input_path, records)
    manifest_path = H.write_manifest(tmp_path / "manifest.json", manifest)
    report = supervisor.run_supervisor(
        input_path,
        manifest_path,
        tmp_path / "hang.json",
        timeout_seconds=0.4,
        child_command=[sys.executable, "-B", "-c", "import time; time.sleep(60)"],
    )
    assert report["status"] == "timeout"
    assert report["timed_out"] is True
    assert report["child_spawned"] is True
    assert report["pid"] > 0
    cleanup = report["cleanup"]
    assert cleanup["terminate_attempted"] is True
    assert cleanup["reaped_after_terminate"] or cleanup["reaped_after_kill"]
    assert cleanup["failure"] in (None, "kill_wait_timeout")


# ---------------------------------------------------------------------------
# R1 regressions: QA01 blank records, QA02 spawn budget, QA03 wait/cleanup
# ---------------------------------------------------------------------------


def test_complete_blank_and_whitespace_records_are_corruption(tmp_path):
    _, records, _ = _world(tmp_path)
    manifest = H.make_manifest(tmp_path / "input.jsonl", records)
    sink, path = _new_journal(tmp_path, records, manifest)
    sink.append("unit", {"n": 1})
    sink.close()
    good = path.read_bytes()
    first, rest = good.split(b"\n", 1)

    for insertion in (b"\n", b"   \n", b"\t\n"):
        path.write_bytes(first + b"\n" + insertion + rest)
        before = path.read_bytes()
        with pytest.raises(journal.JournalError) as caught:
            journal.read_journal(path)
        assert caught.value.code == "journal_empty_record"
        assert path.read_bytes() == before

    # An extra terminated blank record after the last valid record.
    path.write_bytes(good + b"\n")
    before = path.read_bytes()
    with pytest.raises(journal.JournalError) as caught:
        journal.read_journal(path)
    assert caught.value.code == "journal_empty_record"
    assert path.read_bytes() == before

    # The undamaged journal still reads.
    path.write_bytes(good)
    assert journal.read_journal(path).incomplete_tail is False


def test_supervisor_spawn_time_consumes_remaining_budget(tmp_path, monkeypatch):
    monkeypatch.setattr(
        supervisor, "preflight", lambda *args: ({}, "a" * 64, "b" * 64)
    )
    elapsed = [0.0]
    waits = []

    class Process:
        pid = 4242

        def wait(self, timeout):
            waits.append(timeout)
            return 0

    def factory(argv, **kwargs):
        assert kwargs["shell"] is False
        elapsed[0] = 7.0
        return Process()

    report = supervisor.run_supervisor(
        tmp_path / "in",
        tmp_path / "manifest",
        tmp_path / "out.json",
        timeout_seconds=10,
        popen_factory=factory,
        clock=lambda: elapsed[0],
    )
    assert waits == [3.0]
    assert report["status"] == "child_exit_zero"
    assert report["remaining_after_spawn_seconds"] == 3.0


def test_supervisor_exhausted_at_spawn_cleans_without_full_wait(tmp_path, monkeypatch):
    monkeypatch.setattr(
        supervisor, "preflight", lambda *args: ({}, "a" * 64, "b" * 64)
    )
    elapsed = [0.0]
    waits = []

    class Process:
        pid = 4244

        def wait(self, timeout):
            waits.append(timeout)
            return 0

        def terminate(self):
            return None

        def poll(self):
            return 0

    def factory(argv, **kwargs):
        elapsed[0] = 12.0
        return Process()

    report = supervisor.run_supervisor(
        tmp_path / "in",
        tmp_path / "manifest",
        tmp_path / "out.json",
        timeout_seconds=10,
        popen_factory=factory,
        clock=lambda: elapsed[0],
    )
    assert waits == [5.0]  # only the bounded cleanup wait
    assert report["status"] == "timeout"
    assert report["deadline_error"] == "deadline_exhausted_at_spawn"
    assert report["cleanup"]["reaped_after_terminate"] is True


def test_supervisor_wait_exception_cleans_and_never_leaks_message(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        supervisor, "preflight", lambda *args: ({}, "a" * 64, "b" * 64)
    )
    secret = "synthetic-sensitive-message-not-to-be-retained"
    waits = []

    class Process:
        pid = 4243

        def __init__(self):
            self.terminated = False

        def wait(self, timeout):
            waits.append(timeout)
            if len(waits) == 1:
                raise OSError(secret)
            return 0

        def terminate(self):
            self.terminated = True

        def poll(self):
            return 0

    process = Process()
    report = supervisor.run_supervisor(
        tmp_path / "in",
        tmp_path / "manifest",
        tmp_path / "out.json",
        timeout_seconds=10,
        popen_factory=lambda *args, **kwargs: process,
        clock=lambda: 0.0,
    )
    assert process.terminated is True
    assert waits == [10, 5]
    assert report["status"] == "wait_error"
    assert report["wait_error"] == "OSError"
    assert secret not in json.dumps(report)


def test_supervisor_cleanup_wait_failure_is_explicit_not_fatal(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        supervisor, "preflight", lambda *args: ({}, "a" * 64, "b" * 64)
    )
    secret = "cleanup-secret-message"
    waits = []

    class Process:
        pid = 4245

        def wait(self, timeout):
            waits.append(timeout)
            raise OSError(secret)

        def terminate(self):
            raise OSError(secret)

        def kill(self):
            raise OSError(secret)

        def poll(self):
            raise OSError(secret)

    report = supervisor.run_supervisor(
        tmp_path / "in",
        tmp_path / "manifest",
        tmp_path / "out.json",
        timeout_seconds=10,
        popen_factory=lambda *args, **kwargs: Process(),
        clock=lambda: 0.0,
    )
    assert waits == [10, 5, 5]
    assert report["status"] == "wait_error"
    assert report["cleanup"]["failure"] is not None
    assert report["cleanup"]["terminate_error"] == "OSError"
    assert report["cleanup"]["kill_error"] == "OSError"
    assert all(
        error["type"] == "OSError" for error in report["cleanup"]["errors"]
    )
    assert secret not in json.dumps(report)
    assert (tmp_path / "out.json.supervisor.json").exists()


def test_supervisor_keyboard_interrupt_cleans_and_writes_closed_report(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        supervisor, "preflight", lambda *args: ({}, "a" * 64, "b" * 64)
    )
    waits = []

    class Process:
        pid = 4246

        def __init__(self):
            self.terminated = False

        def wait(self, timeout):
            waits.append(timeout)
            if len(waits) == 1:
                raise KeyboardInterrupt
            return 0

        def terminate(self):
            self.terminated = True

        def poll(self):
            return 0

    process = Process()
    with pytest.raises(KeyboardInterrupt):
        supervisor.run_supervisor(
            tmp_path / "in",
            tmp_path / "manifest",
            tmp_path / "out.json",
            timeout_seconds=10,
            popen_factory=lambda *args, **kwargs: process,
        )
    assert process.terminated is True
    report = json.loads(
        (tmp_path / "out.json.supervisor.json").read_text(encoding="utf-8")
    )
    assert report["status"] == "interrupted"
    assert report["interrupted"] is True
    assert report["pid"] == 4246


# ---------------------------------------------------------------------------
# G. Atomic output write / cleanup failure keeps evidence
# ---------------------------------------------------------------------------


def test_interrupted_atomic_write_preserves_previous_committed_file(tmp_path, monkeypatch):
    path = tmp_path / "result.json"
    lock = runner.OutputLock(path)
    lock.acquire()
    lock.write_json({"committed": True})
    previous = path.read_bytes()

    def boom(src, dst):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(runner.os, "replace", boom)
    _assert_code(lambda: lock.write_json({"committed": False}), "output_write_failed")
    assert path.read_bytes() == previous
    lock.release()


def test_cleanup_failure_is_recorded_without_deleting_journal(tmp_path):
    input_path, records, _ = _world(tmp_path)
    manifest = H.make_manifest(input_path, records)
    manifest_path = H.write_manifest(tmp_path / "manifest.json", manifest)
    output = tmp_path / "result.json"

    class FailingCloseBackend(H.FakeBackend):
        def close(self):
            self.closed = True
            raise RuntimeError("close failed with password=secret")

    result = runner.execute_collection(
        input_path,
        manifest_path,
        output,
        backend_factory=lambda: FailingCloseBackend(records),
        clock=H.FakeClock(),
        on_utc=H.FixedUtc(),
    )
    assert result["status"] == "completed"
    assert result["cleanup"][0]["code"] == "cleanup_error"
    journal_path = journal.journal_path_for(output)
    read = journal.read_journal(journal_path)
    assert any(event["kind"] == "cleanup" for event in read.events)
    assert any(event["kind"] == "final_result" for event in read.events)
    assert "secret" not in journal_path.read_text(encoding="utf-8")
    assert "secret" not in output.read_text(encoding="utf-8")
