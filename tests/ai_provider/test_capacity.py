"""Bounded concurrency: timeout/cancellation recovery without orphan waiters."""

import asyncio
import threading
import time

import pytest
from domains.providers import ModelUnavailableError, OpenCodeCliProvider, ProviderConfig
from domains.providers import process

from helpers_provider import (MODELS_LISTING, FakeRunner, _rebind_export_agent,
                              call_fixture, python_executable)


def _config(**overrides):
    values = {
        "provider": "opencode_cli",
        "model": "aibox/ds/deepseek-flash",
        "cli_executable": python_executable(),
        "cli_agent": "oc040-test-agent",
        "cli_timeout_seconds": 0.05,
        "cli_max_concurrency": 1,
        # The installed CLI has no --pure; these lifecycle tests exercise the
        # transport, so plugin isolation is explicitly opted out.
        "cli_pure": False,
    }
    values.update(overrides)
    return ProviderConfig(**values)


def _payload():
    return {"model": "aibox/ds/deepseek-flash",
            "messages": [{"role": "user", "content": "hi"}]}


def test_timed_out_waiter_does_not_steal_a_later_permit():
    provider = OpenCodeCliProvider(_config(), runner=FakeRunner())
    assert provider._semaphore.acquire() is True
    try:
        with pytest.raises(ModelUnavailableError) as excinfo:
            asyncio.run(provider._acquire())
        assert excinfo.value.code == "provider_busy"
    finally:
        provider._release()

    # The abandoned waiter must be gone: the released permit is available again.
    assert provider._semaphore.acquire(blocking=False) is True
    provider._release()


def test_repeated_event_loops_do_not_leak_waiters_or_permits():
    provider = OpenCodeCliProvider(_config(cli_timeout_seconds=0.2),
                                   runner=FakeRunner())
    for _ in range(5):
        asyncio.run(provider._acquire())
        provider._release()
    assert provider._semaphore.acquire(blocking=False) is True
    provider._release()


def test_cancelled_waiter_does_not_hold_capacity():
    provider = OpenCodeCliProvider(_config(cli_timeout_seconds=5.0),
                                   runner=FakeRunner())
    assert provider._semaphore.acquire() is True

    async def _cancel_waiter():
        task = asyncio.create_task(provider._acquire())
        await asyncio.sleep(0.02)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(_cancel_waiter())
    provider._release()
    assert provider._semaphore.acquire(blocking=False) is True
    provider._release()


def test_all_waiters_terminate_and_capacity_recovers():
    provider = OpenCodeCliProvider(_config(cli_timeout_seconds=5.0),
                                   runner=FakeRunner())
    assert provider._semaphore.acquire() is True

    async def _cancel_all():
        tasks = [asyncio.create_task(provider._acquire()) for _ in range(4)]
        await asyncio.sleep(0.02)
        for task in tasks:
            task.cancel()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        assert all(isinstance(item, asyncio.CancelledError) for item in results)

    started = time.monotonic()
    asyncio.run(_cancel_all())
    assert time.monotonic() - started < 2.0
    provider._release()
    assert provider._semaphore.acquire(blocking=False) is True
    provider._release()


def test_capacity_stays_held_until_cancelled_child_cleanup_finishes():
    events, export = call_fixture("after cleanup")
    first_started = threading.Event()

    class CleanupRunner:
        def __init__(self):
            self.calls = 0
            self.runs = 0

        def __call__(self, argv, *, cwd, timeout, env, max_output_bytes,
                     cancel_event=None):
            self.calls += 1
            if len(argv) > 1 and argv[1] == "models":
                return process.CommandResult(
                    argv=list(argv), exit_code=0, duration_seconds=0.01,
                    timed_out=False, output_overflow=False,
                    stdout=MODELS_LISTING.encode(), stderr=b"")
            if len(argv) > 2 and argv[1:3] == ["session", "export"]:
                return process.CommandResult(
                    argv=list(argv), exit_code=0, duration_seconds=0.01,
                    timed_out=False, output_overflow=False,
                    stdout=_rebind_export_agent(export, cwd), stderr=b"")
            self.runs += 1
            if self.runs == 1:
                first_started.set()
                while not cancel_event.is_set():
                    time.sleep(0.01)
                time.sleep(0.25)  # simulated bounded process-tree cleanup
                return process.CommandResult(
                    argv=list(argv), exit_code=-1, duration_seconds=0.3,
                    timed_out=False, output_overflow=False, stdout=b"",
                    stderr=b"", cancelled=True)
            return process.CommandResult(
                argv=list(argv), exit_code=0, duration_seconds=0.01,
                timed_out=False, output_overflow=False, stdout=events,
                stderr=b"")

    runner = CleanupRunner()
    provider = OpenCodeCliProvider(_config(cli_timeout_seconds=5.0),
                                   runner=runner)
    order = []

    async def _run():
        first = asyncio.create_task(provider.complete(_payload()))
        await asyncio.to_thread(first_started.wait, 2.0)
        assert first_started.is_set()
        first.cancel()

        second = asyncio.create_task(provider.complete(_payload()))
        try:
            await first
        except asyncio.CancelledError:
            order.append("first_cancelled")
        result = await second
        order.append("second_done")
        return result

    result = asyncio.run(_run())
    assert order == ["first_cancelled", "second_done"]
    assert result["choices"][0]["message"]["content"] == "after cleanup"
    assert provider._semaphore.acquire(blocking=False) is True
    provider._release()
