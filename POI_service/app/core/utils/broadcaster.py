import asyncio
import time

from collections import OrderedDict, deque
from dataclasses import dataclass, field
from typing import AsyncIterator, Callable, Deque, Dict, Optional

# Bounded in-memory retention. Events are buffered per job so any subscriber
# (including one that connects *after* publishing) can replay them. This store
# is process-local and is NOT durable across a restart.
DEFAULT_MAX_EVENTS_PER_JOB = 256
DEFAULT_MAX_JOBS = 128
DEFAULT_TTL_SECONDS = 300.0

TERMINAL_EVENT_TYPE = "complete"
EVICTED_REASON = "evicted"


class BroadcasterCapacityError(RuntimeError):
    """Raised when a new job cannot be registered at the active-job capacity."""


@dataclass
class _JobState:
    """Replayable per-job event history plus a wake-up condition.

    ``events`` holds sequence numbers ``[base_seq, next_seq)``. ``base_seq``
    advances when the oldest event is evicted, which lets a slow subscriber
    detect that it fell behind.
    """

    created_at: float
    events: Deque[dict] = field(default_factory=deque)
    base_seq: int = 0
    next_seq: int = 0
    terminal: bool = False
    terminal_at: Optional[float] = None
    evicted_events: int = 0
    condition: asyncio.Condition = field(default_factory=asyncio.Condition)


class IngestionBroadcaster:
    """Process-local SSE fan-out with bounded, replayable retention.

    Guarantees:
    - ``publish`` appends to a per-job history that exists before any
      subscriber connects, so events published before subscribe are retained.
    - Each subscriber replays the history from its own cursor; subscribers do
      not consume each other's events (fan-out, not a shared consuming queue).
    - The terminal ``complete`` event stays replayable until its TTL expires.
    - A subscriber that falls behind (its cursor points at evicted events) is
      terminated explicitly with an ``evicted`` terminal event rather than
      silently skipping data.
    - Registering beyond ``max_jobs`` active jobs raises
      ``BroadcasterCapacityError`` instead of evicting an active job. Expired
      jobs are pruned first; callers may also evict explicitly with ``evict``.
    """

    def __init__(
        self,
        max_events: int = DEFAULT_MAX_EVENTS_PER_JOB,
        max_jobs: int = DEFAULT_MAX_JOBS,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ):
        if max_events <= 0:
            raise ValueError("max_events must be a positive integer.")
        if max_jobs <= 0:
            raise ValueError("max_jobs must be a positive integer.")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive.")
        self.max_events = max_events
        self.max_jobs = max_jobs
        self.ttl_seconds = ttl_seconds
        self._clock = clock
        self._jobs: "OrderedDict[str, _JobState]" = OrderedDict()

    # ------------------------------------------------------------------
    # Registration / lifecycle
    # ------------------------------------------------------------------
    def register(self, job_id: str) -> None:
        """Register a job before its canary runs.

        Raises ``BroadcasterCapacityError`` when the active-job capacity is
        reached (after pruning expired jobs). Active jobs are never evicted to
        make room. Idempotent for an existing job.
        """
        self._prune_expired()
        job = self._jobs.get(job_id)
        if job is not None:
            self._jobs.move_to_end(job_id)
            return
        if len(self._jobs) >= self.max_jobs:
            raise BroadcasterCapacityError(
                f"Broadcaster at capacity ({self.max_jobs} active jobs)."
            )
        self._jobs[job_id] = _JobState(created_at=self._clock())

    def _ensure(self, job_id: str) -> _JobState:
        job = self._jobs.get(job_id)
        if job is not None:
            return job
        self.register(job_id)
        return self._jobs[job_id]

    def is_active(self, job_id: str) -> bool:
        """True while the job is known and (if terminal) within its TTL."""
        self._prune_expired()
        return job_id in self._jobs

    def is_terminal(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        return bool(job and job.terminal)

    def evict(self, job_id: str) -> None:
        """Explicitly remove a job. Used for failed canaries and expiry."""
        self._jobs.pop(job_id, None)

    # Backwards-compatible aliases for explicit removal.
    remove = evict
    remove_queue = evict

    def evicted_events(self, job_id: str) -> int:
        job = self._jobs.get(job_id)
        return job.evicted_events if job else 0

    def event_count(self, job_id: str) -> int:
        job = self._jobs.get(job_id)
        return len(job.events) if job else 0

    def job_count(self) -> int:
        return len(self._jobs)

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------
    async def publish(self, job_id: str, data: dict) -> None:
        job = self._ensure(job_id)
        async with job.condition:
            if len(job.events) >= self.max_events:
                job.events.popleft()
                job.base_seq += 1
                job.evicted_events += 1

            job.events.append(data)
            job.next_seq += 1

            if data.get("type") == TERMINAL_EVENT_TYPE:
                job.terminal = True
                job.terminal_at = self._clock()

            job.condition.notify_all()

    # ------------------------------------------------------------------
    # Subscription (replay + live tail)
    # ------------------------------------------------------------------
    async def subscribe(self, job_id: str) -> AsyncIterator[dict]:
        """Yield events from the beginning of the job history, then live ones.

        The generator ends after yielding the terminal event (or after an
        explicit ``evicted`` terminal event if the history overflowed before
        this subscriber caught up). Disconnecting simply stops this generator;
        it never removes the job.
        """
        job = self._jobs.get(job_id)
        if job is None:
            return

        cursor = 0
        while True:
            pending = []
            evicted = False
            done = False

            async with job.condition:
                await job.condition.wait_for(
                    lambda: job.next_seq > cursor
                    or job.terminal
                    or cursor < job.base_seq
                )
                if cursor < job.base_seq:
                    evicted = True
                else:
                    while cursor < job.next_seq:
                        event = job.events[cursor - job.base_seq]
                        cursor += 1
                        pending.append(event)
                        if event.get("type") == TERMINAL_EVENT_TYPE:
                            done = True
                            break
                    if not done and job.terminal and cursor >= job.next_seq:
                        done = True

            if evicted:
                yield {
                    "type": TERMINAL_EVENT_TYPE,
                    "status": "failed",
                    "reason": EVICTED_REASON,
                    "message": "Subscriber lagged; buffered events were evicted.",
                }
                return

            for event in pending:
                yield event

            if done:
                return

    # ------------------------------------------------------------------
    # Internal retention bookkeeping
    # ------------------------------------------------------------------
    def _prune_expired(self) -> None:
        now = self._clock()
        expired = [
            job_id
            for job_id, job in self._jobs.items()
            if job.terminal
            and job.terminal_at is not None
            and (now - job.terminal_at) > self.ttl_seconds
        ]
        for job_id in expired:
            del self._jobs[job_id]


# Global singleton instance
broadcaster = IngestionBroadcaster()
