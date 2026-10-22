"""OC-004 broadcaster fan-out, replay, capacity and expiry tests."""

import asyncio

import pytest

from app.core.utils.broadcaster import (
    BroadcasterCapacityError,
    IngestionBroadcaster,
)


def run(coro, timeout=2.0):
    return asyncio.run(asyncio.wait_for(coro, timeout))


async def collect(agen, limit=None):
    out = []
    async for event in agen:
        out.append(event)
        if limit is not None and len(out) >= limit:
            break
    return out


def test_events_published_before_subscribe_are_replayed():
    async def scenario():
        b = IngestionBroadcaster()
        b.register("job")
        await b.publish("job", {"type": "progress", "n": 1})
        await b.publish("job", {"type": "progress", "n": 2})
        await b.publish("job", {"type": "complete", "status": "success"})
        return await collect(b.subscribe("job"))

    events = run(scenario())
    assert [e["type"] for e in events] == ["progress", "progress", "complete"]


def test_fan_out_two_subscribers_each_receive_all_events():
    async def scenario():
        b = IngestionBroadcaster()
        b.register("job")
        first = b.subscribe("job")
        second = b.subscribe("job")
        await b.publish("job", {"type": "progress", "n": 1})
        await b.publish("job", {"type": "complete", "status": "success"})
        return await collect(first), await collect(second)

    a, c = run(scenario())
    assert [e["type"] for e in a] == ["progress", "complete"]
    assert [e["type"] for e in c] == ["progress", "complete"]


def test_reconnect_after_terminal_replays_terminal():
    async def scenario():
        b = IngestionBroadcaster()
        b.register("job")
        await b.publish("job", {"type": "complete", "status": "success"})
        first = await collect(b.subscribe("job"))
        second = await collect(b.subscribe("job"))
        return first, second, b.is_active("job")

    first, second, active = run(scenario())
    assert first[-1]["type"] == "complete"
    assert second[-1]["type"] == "complete"
    assert active is True


def test_disconnect_does_not_remove_job_and_late_events_survive():
    async def scenario():
        b = IngestionBroadcaster()
        b.register("job")
        await b.publish("job", {"type": "progress", "n": 1})

        gen = b.subscribe("job")
        first = await gen.__anext__()  # a subscriber reads one event
        await gen.aclose()  # then disconnects

        await b.publish("job", {"type": "complete", "status": "success"})
        still_active = b.is_active("job")
        remaining = await collect(b.subscribe("job"))
        return first, still_active, remaining

    first, still_active, remaining = run(scenario())
    assert first["n"] == 1
    assert still_active is True
    assert [e["type"] for e in remaining] == ["progress", "complete"]


def test_slow_subscriber_detects_eviction_and_terminates():
    async def scenario():
        b = IngestionBroadcaster(max_events=3)
        b.register("job")
        gen = b.subscribe("job")  # subscribed but never advanced
        for i in range(5):
            await b.publish("job", {"type": "progress", "n": i})
        return await collect(gen)

    events = run(scenario())
    assert len(events) == 1
    assert events[0]["type"] == "complete"
    assert events[0]["reason"] == "evicted"
    assert events[0]["status"] == "failed"


def test_capacity_rejects_new_job_without_evicting_active():
    b = IngestionBroadcaster(max_jobs=2)
    b.register("a")
    b.register("b")
    with pytest.raises(BroadcasterCapacityError):
        b.register("c")
    assert b.is_active("a") is True
    assert b.is_active("b") is True


def test_expired_job_frees_capacity_with_injected_clock():
    clock = {"t": 0.0}
    b = IngestionBroadcaster(max_jobs=1, ttl_seconds=10.0, clock=lambda: clock["t"])
    b.register("a")
    asyncio.run(b.publish("a", {"type": "complete", "status": "success"}))

    with pytest.raises(BroadcasterCapacityError):
        b.register("b")

    clock["t"] = 20.0
    b.register("b")
    assert b.is_active("b") is True
    assert b.is_active("a") is False


def test_terminal_job_expires_after_ttl():
    clock = {"t": 100.0}
    b = IngestionBroadcaster(ttl_seconds=10.0, clock=lambda: clock["t"])
    b.register("job")
    asyncio.run(b.publish("job", {"type": "complete", "status": "success"}))

    assert b.is_active("job") is True
    clock["t"] = 105.0
    assert b.is_active("job") is True
    clock["t"] = 111.0
    assert b.is_active("job") is False


@pytest.mark.parametrize(
    "kwargs",
    [{"max_events": 0}, {"max_events": -1}, {"max_jobs": 0}, {"ttl_seconds": 0}],
)
def test_invalid_retention_settings_are_rejected(kwargs):
    with pytest.raises(ValueError):
        IngestionBroadcaster(**kwargs)


def test_unknown_job_is_not_active():
    assert IngestionBroadcaster().is_active("does-not-exist") is False
