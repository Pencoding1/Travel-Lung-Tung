# ADR 014 — Backend itinerary-draft workflow

- Status: accepted
- Date: 2026-10-16
- Task: OC-027
- Supersedes: none
- Related: `backend_service/app/main.py`,
  `backend_service/app/api/rest/v1/endpoint_itinerary.py`,
  `backend_service/app/core/security/auth.py`,
  `backend_service/app/core/domain/itinerary_draft.py`,
  `backend_service/app/core/repositories/`,
  `backend_service/app/core/settings.py`,
  `tests/backend_workflows/`
- Depends on: ADR 007 (chat-memory auth boundary), ADR 009 (optional Firestore,
  fail-loud configuration)

## Context

`backend_service` had domain models, a Firebase repository and an empty
`endpoint_itinerary.py`; there was no FastAPI entrypoint and no runnable core
use case. The verified JWT contract already existed in `ai_service`
(`JWT_SECRET`, HS256, required `exp`/`sub`) and `POI_service`. The AI service's
`POST /generate_itinerary` returns a concrete JSON document that a client must be
able to save and later retrieve.

The missing piece is a bounded, authenticated, durable store for those generated
itineraries — without turning the backend into a second source of trip truth and
without making Firebase (or any network) a startup dependency.

## Decision

### 1. A draft is stored, not verified

The backend accepts the exact `/generate_itinerary` response as `payload` and
persists it verbatim. It performs **structural/resource-bound validation only** —
shape (`reply.stops`), byte size, JSON depth, node count, string/list length and
finite numbers. It never recomputes feasibility, never rewrites a `null` budget,
never changes an `unverifiable`/`partial` planning verdict into `"feasible"`,
never invents POIs/geography/owner/status, and never executes the payload.

### 2. The owner is the verified JWT subject

`app/core/security/auth.py` pins **HS256**, requires `exp` and a nonblank bounded
`sub`, and reads `JWT_SECRET` from the environment at request time. A missing
secret is `503` (configuration), malformed/expired/wrong/subject-less tokens are
`401`. The request schema uses `extra="forbid"`, so a client-supplied
`owner`/`uid`/`id` is rejected `422`; the owner is only ever the verified `sub`.

### 3. Repository abstraction with owner-scoped, fail-loud backends

`ItineraryDraftRepository` defines `create/get/list/delete/close/health`. Every
read/write takes `owner` and adapters apply it **in the storage query**:

- **SQLite** (`ITINERARY_STORAGE=sqlite` + `ITINERARY_SQLITE_PATH`): durable,
  file-backed, one connection per operation (safe under FastAPI's sync threadpool),
  parameterized SQL, atomic create/delete, owner filter in the `WHERE` clause.
- **none** (default): `NullItineraryDraftRepository` returns nothing and fails
  writes with `503`; `/ready` reports `not_ready`.
- **firebase** (optional): an import-safe adapter over an injected Firestore
  client. Enabling it lazily imports `firebase_admin`; a missing package/credential
  fails loudly. **No backend silently falls back to another.**

### 4. Import safety and dependency injection

`app/main.py` exposes `create_app(repository=..., settings=...)`. With no
injection it resolves a repository from the environment; the default (`none`)
means importing the app never imports `firebase_admin`, opens a socket or reads a
credential. Tests inject an in-memory or SQLite repository and run the whole HTTP
surface with no database or network. The repository is created/owned by the app
and closed in the lifespan `finally`.

### 5. Honest health

`GET /health` returns `{"status": "ok", "repository": {...}}`; `GET /ready`
returns `503` when the repository reports `available=false`. Health never implies
a backend that is not actually configured.

## Alternatives considered

- **Re-validate the itinerary for feasibility.** Rejected: the backend is not the
  planner, has no route/graph evidence, and would risk promoting unknowns or
  fabricating facts.
- **Trust a client-supplied owner/id.** Rejected: insecure; owner comes only from
  the verified JWT and ids are server-generated.
- **Default to SQLite so writes always work.** Rejected: the local path is an
  explicit opt-in; silently persisting to disk during import or startup is
  surprising and hides misconfiguration.
- **Fall back from failed Firebase to SQLite.** Rejected: indistinguishable from
  a working Firebase; contradicts ADR 009's fail-loud principle.
- **Use the legacy Firebase repository (module-level `firebase_admin`).**
  Rejected: it imports the SDK and reads credentials at import, breaking local
  startup. The legacy files are untouched; the new adapter is additive.

## Corrections (OC-027-R1)

A corrective pass tightened four boundaries:

- **Storage error normalization.** Every SQLite connection/PRAGMA/query/commit/
  decode failure in *every* operation is converted to a sanitized
  `RepositoryError`; no raw driver message, path or SQL text reaches HTTP, which
  returns a structured `503`. Firestore `list`/`delete` gained the same boundary
  (the `where` call included).
- **Real readiness.** SQLite `health()` now performed a bounded `SELECT 1` plus a
  schema-presence probe, re-creating the schema when missing, and reported
  unavailable on failure — recovering automatically once storage is reachable. It
  no longer reported ready merely because the object exists. *(Superseded by the
  OC-028 correction below: schema recreation during a probe was itself unsafe.)*
- **Bounded Firestore listing.** `list` uses an owner-scoped count aggregation for
  the total and an `order_by(created_at) + offset + limit` page query instead of
  materializing every owner document. This requires an aggregation-capable client
  and (in production) a composite index on `(owner, created_at)`; without them it
  fails closed. Live Firebase remains unverified.
- **Parser-safe deep input.** A non-recursive ASGI body guard
  (`app/core/middleware.py`) rejects over-deep/over-large JSON with a structured
  `422`/`413` before `json.loads` can raise `RecursionError`, and the validator now
  walks bounds before serializing. A `RecursionError` handler is the fallback.

`backend_service/pyproject.toml` now declares `pyjwt>=2.11.0,<3` (already present
in the workspace lock via the root project). The root lock is not edited;
locked-install verification remains pending.

## Corrections (OC-028)

An independent probe of OC-027-R1 (`docs/project/handoffs/OC-027/independent-readiness-probe.json`)
showed that `health()` **recreated** a dropped `itinerary_drafts` table and
reported `available: true` (`table_count_after_health: 1`). A readiness probe
that performs DDL is unsafe: it hides schema/data loss, can resurrect an empty
store a client will then trust, and mutates the very resource it claims to be
observing. OC-028 separates deliberate initialization from observational
readiness:

- **Explicit, mutating initialization.** `SqliteItineraryDraftRepository.initialize()`
  is the *only* path that creates the parent directory, opens the database for
  creation (`mode=rwc`), selects `journal_mode = WAL` and runs
  `CREATE TABLE/INDEX`. It is invoked deliberately at construction
  (`initialize=True`, the default) and again from the FastAPI lifespan startup
  boundary (`app/main.py`). A pre-existing invalid (non-database) file fails
  loudly there — there is **no** automated schema or data-loss recovery.
- **Non-mutating readiness and operations.** `health()` and every ordinary
  operation open the database open-only (`mode=rw`, never create) using
  Windows-safe SQLite URI filenames (`file:///...?mode=…`). If the file, parent
  directory or required schema is missing, they report unavailable / fail closed
  with a sanitized `503` and do **not** recreate the file, tree, table or index,
  do not change the journal mode and write no canary rows.
- **Column-level observational probe.** `health()` runs a single bounded
  `SELECT id, owner, created_at, start_poi_id, end_poi_id, stop_count, payload
  FROM itinerary_drafts LIMIT 0`; a malformed table that merely *exists* but
  lacks required columns is correctly reported unavailable. Readiness recovers
  only when the actually initialized database/schema is present again.
- **Startup boundary documented.** Any `initialize()` (construction or lifespan)
  creates an empty schema if the file is absent, so **deleting the database and
  restarting yields an empty store, not recovery**; this is stated rather than
  implied, and recovery is never automatic.
- **Simplified connection setup.** The journal mode is chosen once at
  initialization; ordinary connections only set connection-local
  `busy_timeout`/`foreign_keys`, so a read/probe cannot mutate the database.

Owner isolation, durability, JSON body guard and bounded-query behaviour from
OC-027-R1 are retained unchanged.

## Consequences

- Positive: an authenticated create/list/get/delete workflow with a durable local
  backend, strict test-time injection, import isolation and honest readiness.
- Trade-off: with the default `none` backend the workflow returns `503` until a
  storage env var is set — deliberate, documented behaviour.
- Evidence boundary: verified with a real ASGI app (httpx `ASGITransport`) and the
  real SQLite adapter in `tests/backend_workflows/`. Firestore is exercised only
  against a fake client; **live Firebase and production deployment remain
  unverified**. Compose wiring is a later gate.
