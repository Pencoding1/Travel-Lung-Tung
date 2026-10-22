# ADR 009 — Optional Firestore at startup (graph-only default, honest health)

- Status: accepted
- Date: 2026-10-15
- Task: OC-011
- Supersedes: none
- Related: `POI_service/app/main.py`,
  `POI_service/app/core/infrastructure/db/database/connector.py`,
  `POI_service/app/core/infrastructure/db/uow.py`,
  `POI_service/app/api/dependencies/services.py`,
  `tests/startup/`
- Depends on: ADR 006 (lazy, side-effect-free imports)

## Context

`POI_service/app/core/infrastructure/db/database/connector.py` imported
`firebase_admin` at module import time and `main.py` unconditionally called
`firestore_db.connect()` (which looked for `secrets/serviceAccountKey.json`) and
`verify_connectivity()` (`auth.list_users`, a network call) during startup. As a
result the POI service could not start — and the MCP lazy UnitOfWork path could
not even be imported — without the Firebase package, a credential file and a
reachable Firebase project, even though the graph database is the only strictly
required dependency. `FireStoreConnector.close()` also deleted **every** Firebase
application in `firebase_admin._apps`, including applications it did not create,
and the root endpoint advertised only a static `"online"` string that implicitly
covered Firebase.

## Problem

How do we make graph-only startup (and the lazy MCP UnitOfWork import) independent
of Firebase/Firestore while preserving explicit, opt-in Firestore behaviour with
truthful health reporting and correct resource cleanup?

## Decision

### 1. Firebase is imported lazily, only when enabled

The only `firebase_admin` import now lives inside `_load_firebase_sdk()`, called
from `FireStoreConnector.connect()` only after the dependency is enabled.
`connector.py` therefore imports with no `firebase_admin`, no credential lookup
and no network access; graph-only deployments need neither the package nor the
service-account key, and the MCP `_default_uow_factory` path imports cleanly
without it. This follows the ADR 006 principle that import must have no database
or credential side effects.

### 2. `FIRESTORE_ENABLED` is a strict, documented opt-in

`parse_firestore_enabled()` accepts, case-insensitively:

- true: `true`, `1`, `yes`, `on`
- false: `false`, `0`, `no`, `off`
- absent/blank: `false` (graph-only default)

Any other value raises `ValueError` (invalid configuration is never silently
treated as disabled). `firestore_enabled()` reads the process environment only;
no `.env` is loaded by the connector.

### 3. Enabled means explicitly initialized and verified

`startup_databases()` connects Firestore then calls `verify_connectivity()`. If
initialization or verification fails, or if a required Memgraph connection
fails, it closes everything already initialized and raises a sanitized
`RuntimeError` (`"<stage> startup failed (<ExceptionType>); refusing to start."`)
with `raise ... from None`, so no raw provider/credential text or traceback
propagates. An enabled dependency therefore never starts in a silently degraded
state. Memgraph remains required, with its bounded retry loop intact and Memgraph
authentication failing fast.

### 4. Lifecycle is injectable and testable

`startup_databases(memgraph, firestore, *, enabled=None)` and
`shutdown_databases(memgraph, firestore)` take their connectors as arguments, so
tests drive the real orchestration with fakes. Shutdown closes Firestore in a
`finally` even if closing the graph raises; `main.lifespan` wraps shutdown in
`try/finally` so cleanup runs when the app exits via an exception.

### 5. Close resets state and only deletes owned applications

`FireStoreConnector.connect()` records the application object returned by
`initialize_app`. `close()` deletes only that application (looked up by name in
`_apps`) and never deletes applications created elsewhere. Both connectors reset
their initialized state (and driver/db) on close, so repeated `close()` is a
no-op and connect → close → connect works.

### 6. Honest health reporting

`dependency_health(memgraph, firestore)` returns per-dependency status. Firestore
is reported as `enabled=false, ready=false, status="disabled"` when off (even if a
stale object claims readiness), `not_ready` when enabled but unconnected, `ready`
when connected, and `invalid_configuration` when the flag is malformed. The root
endpoint reports this instead of implying Firebase is online.

## Alternatives considered

- **Keep Firebase as a hard startup dependency.** Rejected: it blocks the
  graph-only service and the lazy MCP path for no functional reason.
- **Treat any unset/unknown value as "enabled if the key exists".** Rejected: the
  flag must be explicit and invalid config must fail loudly.
- **Best-effort `try/except: continue` around Firestore startup.** Rejected: an
  enabled dependency that silently degrades is indistinguishable from one that
  works.
- **Delete `_apps[0]`/all apps on close.** Rejected: the connector must not tear
  down applications it did not create.
- **Expose the raw exception in the startup error.** Rejected: provider/auth
  errors may echo credentials.

## Consequences

- Positive: the service and the MCP lazy UnitOfWork import and start in graph-only
  mode without `firebase_admin` or a service-account key; Firestore is opt-in and
  verified; health is truthful; cleanup is correct and idempotent.
- Trade-off: Firestore is no longer instrumented at startup unless
  `FIRESTORE_ENABLED` is set explicitly; operators that previously relied on the
  implicit Firebase startup must set the flag (and provide the key).
- Behavioural note: `verify_connectivity` still issues an `auth.list_users` call
  when Firestore is enabled; this is intentionally preserved as the readiness
  probe and is the only Firebase network call, made only in enabled mode.
- Evidence boundary: lifecycle and import behaviour are verified with fakes and
  subprocesses in `tests/startup/`. No live Memgraph, Firebase or network call is
  made; graph-only runtime remains unverified until the service is actually
  started (see `docs/project/handoffs/OC-011/`).
