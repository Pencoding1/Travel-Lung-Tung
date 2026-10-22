# backend_service

Business-logic service. It exposes an authenticated, owner-scoped API for saving,
listing, retrieving and deleting **itinerary drafts**.

A draft is the JSON document returned by the AI service's
`POST /generate_itinerary` (see `ai_service/main.py`), persisted **verbatim**.
This service does **not** re-plan or independently verify a trip: it stores the
client-submitted response, preserving unknown costs, planning status and
provenance exactly as received. A `null` budget stays `null`; a `partial` /
`unverifiable` planning verdict is never rewritten to `"feasible"`. The payload
is never executed. See `docs/decisions/014-backend-itinerary-workflow.md`.

## Endpoints

All `/api/v1/itineraries*` routes require `Authorization: Bearer <HS256 JWT>`.
The owner of a draft is always the verified JWT `sub`; a client-supplied owner is
rejected (`422`). Every read/write is scoped to that subject, so another subject
requesting the same id gets `404`.

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/itineraries` | Create a draft (server-generated id + creation time) |
| `GET` | `/api/v1/itineraries?limit=&offset=` | List your drafts (bounded pagination) |
| `GET` | `/api/v1/itineraries/{id}` | Retrieve your draft |
| `DELETE` | `/api/v1/itineraries/{id}` | Delete your draft |
| `GET` | `/health` | Liveness + repository status |
| `GET` | `/ready` | Readiness; `503` when no durable store is available |

Errors are standard and contain no secrets:
`{"detail": {"code": "...", "message": "..."}}`.

## Configuration (environment only)

| Variable | Values | Meaning |
| --- | --- | --- |
| `JWT_SECRET` | any nonblank string | **Required** for authenticated routes. Absent/blank ⇒ `503`, never an anonymous owner. |
| `ITINERARY_STORAGE` | `none` (default) / `sqlite` / `firebase` | Durable store selection. |
| `ITINERARY_SQLITE_PATH` | file path | Required when `ITINERARY_STORAGE=sqlite`. |
| `FIREBASE_KEY_PATH` | service-account path | Optional, only used with `ITINERARY_STORAGE=firebase`. |

The algorithm is pinned to **HS256**; the secret is never used with an algorithm
named by the caller. There is **no silent fallback** between backends: a failed
Firebase selection fails loudly.

## Storage backends

- `none` (default): the service starts with no storage, `/ready` reports
  `not_ready`, and creates return `503`. Importing the app never imports
  `firebase_admin`, opens a socket or reads a credential.
- `sqlite`: local, durable, file-backed (`ITINERARY_SQLITE_PATH`). Data survives
  restarts; creates/deletes are atomic and parameterized; connections are opened
  per operation so the sync endpoints run safely on FastAPI's threadpool. Every
  connection/query/commit error is normalized to a sanitized `503`. Storage is
  initialized **deliberately** at startup (repository construction and the app
  lifespan) and never from a request: ordinary operations and readiness open the
  database open-only (`mode=rw`, Windows-safe URI paths) and never create the
  file, parent directory, table or index. Readiness (`/ready`) is a bounded,
  purely observational probe (`SELECT <required columns> ... LIMIT 0`) — no DDL,
  no journal-mode change, no canary write — that reports `503` when the storage
  is missing/malformed and recovers only when the initialized database is
  present again. A pre-existing invalid database fails startup loudly.
- `firebase`: optional adapter over an injected Firestore client
  (`app/core/repositories/firestore_itinerary_draft.py`). It is import-safe (no
  top-level `firebase_admin`); listing is bounded at the query level (count
  aggregation + `order_by/offset/limit`, which in production needs a composite
  index on `(owner, created_at)` and an aggregation-capable client). Wiring an
  actual project is an explicit opt-in and is **not** integration-verified here.

All JSON request bodies pass a non-recursive depth/size guard before parsing, so
pathologically nested input is rejected with a structured `422` rather than a
parser `RecursionError`.

## Run locally

```powershell
$env:JWT_SECRET = "a-long-random-secret"
$env:ITINERARY_STORAGE = "sqlite"
$env:ITINERARY_SQLITE_PATH = ".\data\drafts.sqlite3"
uv run uvicorn app.main:create_app --factory --port 8003   # from backend_service/
```

## Docker / isolated integration stack

`backend_service/Dockerfile` runs `app.main:app` with `uvicorn` on the documented
port `8003` (the port it `EXPOSE`s). It is intentionally **not** part of the
production `docker-compose.yaml`; it is wired only into the standalone
`docker-compose.integration.yaml` stack, which publishes loopback host port
`18003`, stores drafts in SQLite inside its own `int_backend_drafts` named volume
(`ITINERARY_STORAGE=sqlite`,
`ITINERARY_SQLITE_PATH=/var/lib/backend_drafts/drafts.sqlite3`) and reuses the
shared, explicitly required `INTEGRATION_JWT_SECRET` / `HS256` contract. It is not
joined to the optional AI durable-memory profile, so chats are never auto-saved.

The image `HEALTHCHECK` probes `/health` (liveness) only and never claims
readiness. No image build or live start is claimed here; only the static contract
is verified.

## Client example: generate → save → retrieve

The `payload` you POST is exactly the JSON body returned by `POST
/generate_itinerary` on the AI service. A successful response has this shape
(fields unchanged from `ai_service/main.py`):

```json
{
  "status": "success",
  "reply": {
    "id": "itin_<server-hex>",
    "id_source": "server",
    "uid": "<verified sub or null>",
    "uid_source": "verified_jwt_sub",
    "start_poi_id": "poi_a",
    "end_poi_id": "poi_b",
    "total_estimated_budget": null,
    "budget_is_estimate": true,
    "stops": [
      {
        "date": "2026-01-01",
        "visit_time": "2026-01-01T09:00:00+07:00",
        "end_time": "2026-01-01T10:00:00+07:00",
        "description": "walk and coffee",
        "description_grounded": false,
        "budget": null,
        "budget_is_estimate": true,
        "poi": { "id": "poi_a", "name": "..." }
      }
    ]
  },
  "planning": { "validator_status": "unverifiable", "cost": { "status": "unknown" } },
  "grounding": { "scope_verification": "verified" }
}
```

```powershell
# 1) generate (AI service)
$gen = Invoke-RestMethod -Method Post -Uri "http://localhost:8000/generate_itinerary" `
    -Headers @{ Authorization = "Bearer $token" } -ContentType application/json -Body $requestJson

# 2) save (backend) — pass the returned body straight through as `payload`
$saved = Invoke-RestMethod -Method Post -Uri "http://localhost:8003/api/v1/itineraries" `
    -Headers @{ Authorization = "Bearer $token" } -ContentType application/json `
    -Body (@{ payload = $gen } | ConvertTo-Json -Depth 100)

# 3) retrieve
Invoke-RestMethod -Uri "http://localhost:8003/api/v1/itineraries/$($saved.id)" `
    -Headers @{ Authorization = "Bearer $token" }
```

> **Verification qualifier.** Saving a draft records the AI response; it does
> **not** turn that response into a verified or feasible itinerary. `null`
> budgets, unknown costs and non-`feasible` planning verdicts are stored as-is.

## Tests

```powershell
.venv-validation\Scripts\python.exe -m pytest tests/backend_workflows -q
```

Tests drive the real ASGI app and the real SQLite adapter with fakes/in-memory
stores; no network, live database, Firebase or model call is made.

## Not in scope

No account management, payments, reviews or commercial features. The production
AI endpoint is untouched. The service is wired only into the isolated integration
stack; production Compose wiring and a verified live deployment remain later
gates.
