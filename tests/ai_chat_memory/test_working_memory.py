"""Bounded working-memory contract tests (OC-009, incl. repair regressions)."""

import asyncio

import pytest
from domains import memory


def _run(coro):
    return asyncio.run(coro)


def test_system_prompt_once_and_extractive_summary_preserves_constraint():
    wm = memory.WorkingMemory(max_completed_turns=2)

    async def scenario():
        for i in range(4):
            async with wm.lease("k") as entry:
                wm.compose(entry, "PERSONA", f"user message {i}")
                wm.commit(entry, [{"role": "assistant", "content": f"reply {i}"}],
                          f"user message {i}")
        async with wm.lease("k") as entry:
            return wm.compose(entry, "PERSONA", "current constraint: only cafes")

    final = _run(scenario())
    systems = [m for m in final if m.get("role") == "system"]
    assert len(systems) == 1
    assert systems[0]["content"].startswith("PERSONA")
    assert "<untrusted_history>" in systems[0]["content"]
    assert "user message 0" in systems[0]["content"]
    assert final[-1] == {"role": "user", "content": "current constraint: only cafes"}


def test_trimming_keeps_whole_tool_exchanges():
    wm = memory.WorkingMemory(max_completed_turns=1)

    async def scenario():
        async with wm.lease("k") as entry:
            wm.commit(entry, [
                {"role": "assistant", "content": None,
                 "tool_calls": [{"id": "c1", "type": "function",
                                 "function": {"name": "t", "arguments": "{}"}}]},
                {"role": "tool", "tool_call_id": "c1", "name": "t", "content": "{}"},
                {"role": "assistant", "content": "final"},
            ], "u1")
            wm.commit(entry, [{"role": "assistant", "content": "second"}], "u2")
            return wm.compose(entry, "P", "cur")

    messages = _run(scenario())
    tool_ids = {m.get("tool_call_id") for m in messages if m.get("role") == "tool"}
    assistant_call_ids = set()
    for m in messages:
        if m.get("role") == "assistant":
            for tc in m.get("tool_calls") or []:
                assistant_call_ids.add(tc.get("id"))
    assert tool_ids <= assistant_call_ids
    assert "final" not in [m.get("content") for m in messages]


def test_same_session_requests_are_serialized():
    wm = memory.WorkingMemory()
    order = []

    async def worker(tag):
        async with wm.lease("s1"):
            order.append(f"{tag}-start")
            await asyncio.sleep(0.02)
            order.append(f"{tag}-end")

    async def main():
        await asyncio.gather(worker("a"), worker("b"))

    _run(main())
    a_start, a_end = order.index("a-start"), order.index("a-end")
    b_start, b_end = order.index("b-start"), order.index("b-end")
    assert not (a_start < b_start < a_end)
    assert not (b_start < a_start < b_end)


def test_separate_sessions_are_isolated():
    wm = memory.WorkingMemory()

    async def scenario():
        async with wm.lease("u1:s1") as entry:
            wm.commit(entry, [{"role": "assistant", "content": "x"}], "hi")

    _run(scenario())
    assert wm.snapshot("u1:s1")["completed_turns"] == 1
    assert wm.snapshot("u2:s1")["completed_turns"] == 0
    assert wm.snapshot("u1:s2")["completed_turns"] == 0


def test_clear_key_only_removes_callers_namespace():
    wm = memory.WorkingMemory()

    async def scenario():
        async with wm.lease("a") as entry:
            wm.commit(entry, [{"role": "assistant", "content": "x"}], "hi")
        async with wm.lease("b") as entry:
            wm.commit(entry, [{"role": "assistant", "content": "x"}], "hi")
        return await wm.clear_key("a"), await wm.clear_key("a")

    first, second = _run(scenario())
    assert first is True
    assert second is False
    assert wm.snapshot("a")["completed_turns"] == 0
    assert wm.snapshot("b")["completed_turns"] == 1


def test_max_sessions_evicts_only_idle_and_bounds_registry():
    wm = memory.WorkingMemory(max_sessions=2)

    async def scenario():
        # 20 sequential unique sessions; registry must stay <= 2 entries.
        for i in range(20):
            async with wm.lease(f"s{i}") as entry:
                wm.commit(entry, [{"role": "assistant", "content": "x"}], "u")
        return len(wm._entries)

    assert _run(scenario()) <= 2


def test_capacity_refused_when_all_sessions_pinned():
    wm = memory.WorkingMemory(max_sessions=2)
    order = []

    async def hold(tag):
        async with wm.lease(tag):
            order.append(tag)
            await asyncio.sleep(0.05)

    async def scenario():
        a = asyncio.create_task(hold("a"))
        b = asyncio.create_task(hold("b"))
        await asyncio.sleep(0.01)
        try:
            async with wm.lease("c"):
                pass
        except memory.SessionCapacityError:
            order.append("refused")
        except BaseException as exc:  # pragma: no cover
            order.append(f"other:{type(exc).__name__}")
        await asyncio.gather(a, b)

    _run(scenario())
    assert "refused" in order


def test_waiter_on_held_key_shares_one_pinned_entry():
    wm = memory.WorkingMemory(max_sessions=1)
    order = []

    async def worker(tag):
        async with wm.lease("shared"):
            order.append(f"{tag}-start")
            await asyncio.sleep(0.02)
            order.append(f"{tag}-end")

    async def scenario():
        await asyncio.gather(worker("a"), worker("b"))

    _run(scenario())
    # Both ran on the same pinned entry despite max_sessions=1 (no capacity
    # error, no second lock) and were serialized.
    assert sorted(order) == ["a-end", "a-start", "b-end", "b-start"]
    assert not (order.index("a-start") < order.index("b-start") < order.index("a-end"))
    assert len(wm._entries) <= 1


def test_clear_serializes_with_inflight_request():
    wm = memory.WorkingMemory()
    order = []

    async def request():
        async with wm.lease("k") as entry:
            order.append("req-start")
            await asyncio.sleep(0.03)
            wm.commit(entry, [{"role": "assistant", "content": "late"}],
                      "user constraint")
            order.append("req-commit")

    async def clearer():
        await asyncio.sleep(0.01)  # start after the request holds the lease
        cleared = await wm.clear_key("k")
        order.append(f"clear:{cleared}")

    async def scenario():
        await asyncio.gather(request(), clearer())

    _run(scenario())
    # Clear waited for the in-flight request and then removed its turn; no stale
    # response repopulated the cleared history.
    assert order.index("req-commit") < order.index("clear:True")
    assert wm.snapshot("k")["completed_turns"] == 0


@pytest.mark.parametrize("kwargs", [
    {"max_completed_turns": 0},
    {"max_sessions": 0},
    {"max_sessions": -1},
    {"ttl_seconds": 0},
    {"ttl_seconds": -5},
    {"ttl_seconds": float("inf")},
    {"ttl_seconds": float("nan")},
    {"max_completed_turns": True},
])
def test_invalid_config_is_rejected(kwargs):
    with pytest.raises(ValueError):
        memory.WorkingMemory(**kwargs)


def test_overlong_session_key_is_rejected():
    wm = memory.WorkingMemory(max_key_chars=10)

    async def scenario():
        async with wm.lease("x" * 11):
            pass

    with pytest.raises(ValueError):
        _run(scenario())


def test_commit_bounds_stored_message_length():
    wm = memory.WorkingMemory()

    async def scenario():
        async with wm.lease("k") as entry:
            wm.commit(entry, [{"role": "assistant", "content": "z" * 100000}], "u")
            return wm.compose(entry, "P", "cur")

    messages = _run(scenario())
    assert all(len(m["content"]) <= memory.MAX_MESSAGE_CHARS
               for m in messages if isinstance(m.get("content"), str))
