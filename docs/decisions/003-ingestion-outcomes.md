# ADR 003 — Batch ingestion outcomes, transaction ownership and SSE fan-out

- Status: Accepted
- Date: 2026-10-15
- Task: OC-004 (initial + corrective QA)
- Scope: `POI_service/app/core/services/ingestion.py`,
  `POI_service/app/core/utils/broadcaster.py`,
  `POI_service/app/api/rest/v1/endpoint_ingestion.py`,
  `POI_service/app/core/base/repository.py`,
  `POI_service/app/api/dependencies/services.py`
- Supersedes: none

## Context

Audit of the POI canary/background ingestion and its SSE stream found:

1. **Shared transaction.** `_execute_chunk_with_retry` reused one `self.uow`,
   so a retry ran on a broken/closed transaction.
2. **Malformed input crashed validation.** `_validate_batch` called
   `raw_data.get(...)` on non-dict records.
3. **Null address crashed the worker.** `poi.get("address", {}).get(...)`
   failed when a valid POI had `address = None`.
4. **Background totals ignored the canary.** Terminal counters/indices covered
   only the remainder and restarted at index 0, hiding partial canary failures.
5. **Consuming queue, not fan-out.** The previous broadcaster used a shared
   `asyncio.Queue`: a second subscriber could hang on a consumed terminal,
   disconnecting removed the job (losing retained events), and capacity
   management could evict a job with live subscribers.
6. **Endpoint blocked on the canary.** The synchronous retried canary ran on the
   event loop; malformed non-dict records were rejected by `List[Dict]` before
   per-record accounting; failures returned raw tracebacks or collapsed to 422.
7. **Import side effects.** Importing the dependency module pulled the concrete
   connector (settings requiring `MEMGRAPH_*`, Firebase/neo4j), preventing
   in-process endpoint tests.

## Decision

### 1. Fresh unit of work per write attempt

`_execute_chunk_with_retry` calls `self.uow_factory()` inside the retried body;
the constructor holds no shared UoW. Retries remain bounded to three attempts.

### 2. Non-dict records are validation errors with original indices

`_validate_batch(raw_payloads, start_index=0)` returns
`(valid_pois, valid_indices, failures)`. Non-dict records produce a validation
failure instead of raising; every failure carries the original payload `index`.
`start_index` lets the background worker report global indices.

### 3. Null address is safe

The district roll-up uses `poi.get("address") or {}` and guards non-dict values.

### 4. Whole-batch terminal accounting

`process_background_remainder(remainder, job_id, canary_result=None, start_index=None)`
merges the canary summary and the background counts so the terminal event
describes the **entire submitted batch**. The endpoint passes `canary_result`
and the original offset. A partial canary is therefore never hidden by a
successful remainder.

Terminal event (`complete` means **terminated**, not success):

```json
{
  "type": "complete",
  "status": "success | partial_failure | failed",
  "counts": {
    "total_received": 0, "processed": 0, "accepted": 0,
    "successfully_inserted": 0,
    "validation_failed": 0, "database_failed": 0
  },
  "failed_indices": [0]
}
```

`processed == accepted + validation_failed + database_failed`. Status is
`failed` when nothing was accepted, `partial_failure` when some were accepted
but some failed, `success` otherwise. Synchronous `process_ota_batch` keeps
`is_success: True` for partial success (compatibility) while exposing `status`,
`counts` and `failed_indices`.

### 5. Error mapping and non-blocking canary

`process_ota_batch` sets `error_type` to `unprocessable_entity` (no valid
records) or `database_unavailable` (valid records but the graph rejected all).
The endpoint:

- validates the body as `List[Any]` so malformed records reach per-record
  accounting while the overall list shape is still enforced;
- runs the blocking canary via `asyncio.to_thread` so it never blocks the loop;
- catches unexpected canary exceptions, evicts the job and returns a sanitized
  503 (`internal_error`) with no traceback;
- maps `database_unavailable`/`internal_error` to 503 and invalid records to
  422. `database_details` keeps only the exception **type**.

### 6. Replayable, bounded SSE fan-out

`IngestionBroadcaster` stores a bounded per-job event **history** with sequence
numbers and a per-subscriber cursor (fan-out, not a shared consuming queue):

- `register(job_id)` is called **before** the canary. Registering beyond
  `max_jobs` raises `BroadcasterCapacityError` (mapped to 503 before any write);
  active jobs are never evicted to make room. Expired jobs are pruned first, and
  `evict(job_id)` is available for explicit removal (failed canary, expiry).
- `publish` appends to the history (oldest evicted first past `max_events`) and
  notifies subscribers. Events published before subscribe are retained.
- `subscribe(job_id)` yields from the beginning of the history, then live
  events, ending after the terminal event. The terminal event remains replayable
  until its TTL expires, so reconnecting subscribers still receive it.
- Disconnecting only stops that subscriber's generator; it never removes the
  job. A subscriber that falls behind (cursor points at evicted events) receives
  an explicit `complete` event with `reason: "evicted"` and the stream ends,
  rather than silently skipping data. A new registration is rejected when at
  capacity, so current subscribers can never be stranded by eviction.
- Retention settings (`max_events`, `max_jobs`, `ttl_seconds`) must be positive.

Bounded retention (defaults):

| Bound | Default | Behaviour |
|---|---|---|
| events per job | 256 | oldest event evicted first; count via `evicted_events(job_id)` |
| jobs | 128 | new registration raises capacity error; expired jobs pruned first |
| TTL after terminal | 300 s | terminal job purged; `is_active` returns `False` |

`GET /ingestion/stream/{job_id}` returns 404 for unknown/expired jobs. The auth
dependency (`Depends(verify_jwt_token)`) is unchanged, as are the event `type`
values (`progress`/`warning`/`error`/`complete`).

### 7. Lazy dependency imports

`app/api/dependencies/services.py` imports the concrete connector, UoW and
management service inside the dependency factory functions (and exposes a lazy
`get_memgraph_connector` wrapper). Importing the dependency module therefore no
longer requires `MEMGRAPH_*` settings, Firebase/neo4j, or credentials, which
makes the endpoint testable in-process.

### 8. Connector import isolation in the repository base

`base/repository.py` uses `from __future__ import annotations` and moves the
type-only `neo4j.Transaction` and `FireStoreConnector` imports under
`if TYPE_CHECKING:`.

## Persistence limitation

The SSE broadcaster is **process-local and in-memory**. History/job lifecycle is
not durable across a process restart and is not shared across workers. A restart
loses pending job events; durable delivery (Redis/DB-backed) is out of scope.

## Consequences

- Positive: fresh transactions per attempt; no crash on malformed/null input;
  honest whole-batch terminal reporting with failed indices; true fan-out with
  retained terminal replay; bounded memory; explicit capacity/404/422/503
  semantics; no raw tracebacks; endpoint testable without a database.
- Negative / risk: clients waiting longer than the TTL receive 404; the history
  is memory-only; `complete` must be read as terminated.

## Verification

- `tests/ingestion/` — 39 tests: validation/accounting, fresh-UoW retries,
  exhausted retries, whole-batch canary+background merge, partial canary not
  hidden, broadcaster fan-out/replay/disconnect/eviction/capacity/TTL/settings,
  and runtime FastAPI HTTP tests (auth rejection, 422 vs 503, unexpected-canary
  503, capacity 503 before write, partial batch stream, canary-only stream,
  terminal replay, 404, stream auth).
- `tests/audit` 24 and `tests/domain_identity` 8 remain green.
- Raw run: `docs/project/handoffs/OC-004/pytest_repair.txt` → 71 passed.
