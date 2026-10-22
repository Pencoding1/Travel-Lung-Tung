# Local deployment runbook — Travel Vo Lo

Scope: validate the local Compose configuration, prepare (but do not take) a
gated snapshot, and run smoke checks **after** the environment and engine are
separately verified. No public tunnel or deployment is enabled by default.

This runbook records wiring inspected statically. It does **not** claim that any
service was started: the Docker engine is unavailable in this environment (see
"Known blockers").

## 0. Execution modes (do not confuse them)

| Mode | What runs | Safety | This repo's status |
|---|---|---|---|
| Static / config | `docker compose config --no-env-resolution ...`, unit & contract tests | No containers, no network | Verified |
| Sandbox / in-process | Unit tests with fakes, no external I/O | Safe, no data touched | Verified for existing suites |
| Live | `docker compose up`, real Memgraph/Firebase/Gemini | Mutates graph/volume, calls external APIs | **Not executed** |

Never describe static validation as "the stack works". A green config check only
means Compose can render the file. Live restore/migration is a gated operator
procedure (section 4), not a script in this document.

## 1. Prerequisites (check only, do not loop restarts)

```powershell
docker --version                 # expect a client version
docker compose version           # expect Compose v2+
docker info                      # MUST succeed before attempting `up`
wsl --status                     # on Windows, confirm the WSL backend is running
```

If `docker info` reports a missing engine pipe, the engine is not running. The
observed host behavior is that the Docker startup command returns exit code `0`
while the engine pipe is still absent. **Do not repeatedly restart or reset
Docker**; stop and treat the engine as an external blocker. Static validation
(section 3) can proceed without it.

## 2. Configure the environment

```powershell
Copy-Item .env.example .env
# Edit .env and replace every `replace_me*` placeholder.
```

The Compose file contains no credentials. Required keys (documented in
`.env.example`):

- `MEMGRAPH_USER`, `MEMGRAPH_PASSWORD`
- `JWT_SECRET` — one shared HS256 key passed explicitly into `poi_api`,
  `poi_mcp` and `ai_service` as `JWT_SECRET=${JWT_SECRET:?...}`;
  `JWT_ALGORITHM` defaults to `HS256`, matching
  `POI_service/app/core/security/auth.py` and `ai_service/domains/memory_auth.py`.
- `FIRESTORE_ENABLED` — explicitly wired to `poi_api`/`poi_mcp` with a **graph-only
  default of `false`**.
- `MEMORY_DB_PATH` — blank/absent keeps durable profile memory **off**.
- `GEMINI_API_KEY`, `GEMINI_MODEL`
- `MCP_SERVER_URL` (defaults to `http://poi_mcp:8001/sse`)
- Tunnel only: `NGROK_AUTHTOKEN`, `NGROK_DOMAIN`

Secrets are referenced by path only; `.env` and `POI_service/.env` are never
read during validation.

Firebase is **optional and off by default**. With `FIRESTORE_ENABLED=false`
(absent/blank is also treated as false) the POI service starts graph-only and
never imports `firebase_admin`, reads a key or calls the network. Setting it to
`true` is an explicit opt-in that requires owner-managed service-account
credentials (e.g. `POI_service/secrets/serviceAccountKey.json`) and a reachable,
verified project; if it cannot be verified the service **refuses to start**
rather than degrading silently (ADR 009). Do not enable it unless those
credentials exist.

Durable profile memory is opt-in: a blank `MEMORY_DB_PATH` disables the
endpoints (HTTP 503) and stores nothing. A nonblank path enables the
authenticated SQLite store; inside Compose it must live under the mounted
`ai_memory` volume (e.g. `/var/lib/ai_memory/profiles.db`). Data persists only in
that named volume — deleting the volume is the sole supported erasure path, and
there is no automatic migration. Profiles are never stored unless an operator
sets the path explicitly.

## 3. Validate configuration (never render the full config)

```powershell
docker compose --env-file .env.example config --no-env-resolution --quiet
docker compose --env-file .env.example config --no-env-resolution --services
docker compose --env-file .env.example config --no-env-resolution --images
docker compose --env-file .env.example config --no-env-resolution --profiles
```

`--env-file .env.example` selects the interpolation source, but it does **not**
suppress per-service `env_file` resolution. The `--no-env-resolution` flag is
required to keep `POI_service/.env` from being read. Earlier validation passes
of this task did **not** use that flag, so they may have resolved service env
files (`POI_service/.env`) in addition to the template; that is why every command
below and in the tests carries the flag. Never run bare
`docker compose config` (it prints interpolated values, including secrets).

Expected default services: `memgraph`, `lab`, `graphhopper`, `poi_api`,
`poi_mcp`, `ai_service`. `ngrok` appears only under the `tunnel` profile.

### Isolated integration stack

`docker-compose.integration.yaml` is a separate, standalone stack intended to run
beside the local stack. Validate it with the same read-only flags, using its own
dummy interpolation template (`docs/deployment/integration.env.example`):

```powershell
docker compose -f docker-compose.integration.yaml --env-file docs/deployment/integration.env.example config --no-env-resolution --quiet
docker compose -f docker-compose.integration.yaml --env-file docs/deployment/integration.env.example config --no-env-resolution --services
docker compose -f docker-compose.integration.yaml --env-file docs/deployment/integration.env.example config --no-env-resolution --profiles
```

Expected integration services: `memgraph`, `graphhopper`, `poi_api`, `poi_mcp`,
`ai_service`, `backend_service` (no `lab`, no tunnel). The project name is
`tvlt_integration`. The template holds dummy values only and is never a real
credential file.

### backend_service — itinerary-draft workflow (integration-only)

`backend_service` runs the authenticated draft API (`app.main:app`) on container
port `8003`, published only on loopback host port `18003`. It is a member of the
isolated integration stack **only**; the production `docker-compose.yaml` has no
`backend_service` container. Drafts are stored with `ITINERARY_STORAGE=sqlite`
and `ITINERARY_SQLITE_PATH=/var/lib/backend_drafts/drafts.sqlite3` inside the
stack-owned `int_backend_drafts` named volume. There is no Firebase default and
no anonymous (`none`) storage, and the service is **not** joined to the optional
AI durable-memory profile, so chats are never auto-saved.

All `/api/v1/itineraries*` routes require `Authorization: Bearer <HS256 JWT>`
signed with the same `INTEGRATION_JWT_SECRET` (`INTEGRATION_JWT_ALGORITHM`,
default `HS256`) used by the other integration services. `GET /health` is
liveness only (it succeeds even with no store); `GET /ready` is readiness and
returns `503` when the durable store is unavailable. Never confuse the two.

The saved `payload` is the exact JSON body returned by the AI service's
`POST /generate_itinerary`, stored verbatim as an **untrusted draft**: unknown
costs, `null` budgets and a `partial`/`unverifiable` planning status are
preserved and never promoted to `"feasible"`.

Generate → save → retrieve → delete (manual; substitute your own values — never
commit a real token, secret or `.env`):

```powershell
# 0) Operator-supplied values (placeholders only; do not commit real ones).
$token   = "<your-integration-hs256-jwt>"   # signed with INTEGRATION_JWT_SECRET
$backend = "http://127.0.0.1:18003"         # loopback host port for backend_service
$ai      = "http://127.0.0.1:18002"         # ai_service host port

# 1) generate (AI service) — a real external model call
$gen = Invoke-RestMethod -Method Post -Uri "$ai/generate_itinerary" `
    -Headers @{ Authorization = "Bearer $token" } -ContentType application/json -Body $requestJson

# 2) save (backend) — pass the AI body through unchanged as `payload`
$saved = Invoke-RestMethod -Method Post -Uri "$backend/api/v1/itineraries" `
    -Headers @{ Authorization = "Bearer $token" } -ContentType application/json `
    -Body (@{ payload = $gen } | ConvertTo-Json -Depth 100)

# 3) retrieve, then 4) delete
Invoke-RestMethod -Uri "$backend/api/v1/itineraries/$($saved.id)" `
    -Headers @{ Authorization = "Bearer $token" }
Invoke-RestMethod -Method Delete -Uri "$backend/api/v1/itineraries/$($saved.id)" `
    -Headers @{ Authorization = "Bearer $token" }
```

The image `HEALTHCHECK` probes `/health` (liveness) only and never claims
readiness. No live start or image build of `backend_service` is claimed: the
Docker engine is unavailable here and builds are unverified. Only the static /
structural contract is checked.

Run the contract suite:

```powershell
.venv-validation\Scripts\python.exe -m pytest tests/deployment -q
```

## 4. Backup/recovery — pending gated operator procedure (no commands here)

No verified, ready-to-run backup or restore command is provided. A hot copy of
a live Memgraph volume can be inconsistent, a console dump is not itself an
archive, and `mgconsole -e ...` has not been established against the running
image. Backup and recovery therefore remain **blocked pending operator review**
and must follow the version-specific official Memgraph documentation for the
exact deployed image before any data is touched. Any future procedure must:

1. use the official, version-matched documentation for the deployed image;
2. take a **consistent** snapshot (not a copy of an open volume);
3. restore into **separate** storage, never over the original `mg_lib`;
4. validate the restored data before any migration.

Named volumes to protect: `mg_lib`, `mg_log`, `mg_etc` (see
`docker-compose.yaml`). Nothing in this repository may delete, move, or
overwrite them.

**Isolation status.** The main `docker-compose.yaml` still defines fixed
`container_name` values (e.g. `memgraph-db`, `travel_ai_hub`) and fixed published
ports, so `docker compose -p tvlt_sandbox ...` alone does **not** isolate a
parallel run: container names and host ports would still collide with the
original stack. For a second, parallel stack use the separate
`docker-compose.integration.yaml`, which sets project name `tvlt_integration`,
omits `container_name` entirely, publishes distinct loopback ports and declares
its own `int_*` volumes. Even so, that stack must **never** mount or restore the
production volumes (`mg_lib`, `mg_log`, `mg_etc`); a live restore remains a gated
operator procedure (section 4) and no restore command is provided here.

## 5. Startup and smoke checks

```powershell
docker compose --env-file .env.example config --no-env-resolution --quiet
docker compose --env-file .env.example config --no-env-resolution --services
docker compose up -d          # infrastructure + app services (no tunnel)
docker compose ps
```

Smoke checks below distinguish what is verified from source from what is assumed.
No check in this section was executed against a running stack.

| Service | Check | Evidence status |
|---|---|---|
| POI REST | `GET http://127.0.0.1:8000/` | Path verified in `POI_service/app/main.py` (`root()` returns `{"status": "online"}`); not runtime-run |
| POI REST auth | `Authorization: Bearer <jwt>` signed with `JWT_SECRET` | Scheme verified in `POI_service/app/core/security/auth.py`; no token issued |
| AI hub | `GET http://127.0.0.1:8002/docs` | FastAPI default docs for `app` in `ai_service/main.py`; not runtime-run |
| GraphHopper route | `GET http://127.0.0.1:8989/route` | Path verified in `POI_service/app/api/mcp/tools.py:28` |
| GraphHopper health | `GET http://127.0.0.1:8989/info` | Only referenced by the Compose healthcheck; **not verified** against a running engine |
| Memgraph | `lab` UI at `http://127.0.0.1:3000` | Only path offered; no CLI health command is claimed (the earlier `mgconsole -e` check is withdrawn as unestablished) |
| backend_service liveness | `GET http://127.0.0.1:18003/health` (integration stack) | Path verified in `backend_service/app/main.py` (`/health` returns `ok` regardless of store); not runtime-run |
| backend_service readiness | `GET http://127.0.0.1:18003/ready` (integration stack) | `503` until the initialized SQLite store is present; verified in source; not runtime-run |

Routing: only the **`car`** profile is enabled
(`graphhopper/data/config.yml`; `POI_service/app/api/mcp/tools.py:29`). Foot and
bike requests are unsupported and must not be advertised.

Model availability: `ai_service` calls Gemini's OpenAI-compatible endpoint using
`GEMINI_MODEL`. Verify the key and quota out-of-band before claiming itinerary
generation; such requests are real external calls. Model availability is not
verified here.

## 6. Known blockers and unfinished services (accurate status)

- **Docker engine**: not reachable here (missing engine pipe). Builds and live
  starts are therefore unverified; image digests are not frozen yet.
- **Firebase / Firestore**: **optional** and off by default
  (`FIRESTORE_ENABLED=false`). Graph-only startup needs no Firebase package, key
  or network. Setting `true` requires owner-managed service-account credentials
  and a verified project; otherwise startup fails closed (ADR 009). Absent
  credentials therefore do **not** block graph-only deployment.
- **backend_service**: now has a runnable FastAPI app (`app.main:app`) and a
  Dockerfile `CMD` bound to the documented port `8003` (OC-030). It is
  intentionally **not** in the production `docker-compose.yaml`; it is wired only
  into the isolated integration stack (`docker-compose.integration.yaml`, loopback
  host port `18003`, own `int_backend_drafts` SQLite volume). The Docker engine is
  unavailable here, so the image build/start is **not** verified; only the static
  contract is checked.
- **crawler_service**: `app.main:app` exists but the service is **not** a member
  of the root uv workspace, so the image does not build as-is. Not added to
  Compose; treat as unsupported until workspace membership and browser
  dependencies are verified.
- **Digest freeze**: image variables default to the previously used `:latest`
  tags. Reproducibility requires pinning `@sha256` digests; this remains an
  acceptance dependency.

## 7. Public exposure policy

The `tunnel` profile is the only path that publishes anything beyond loopback,
it is disabled by default, and all host ports bind `127.0.0.1`. Do not enable the
tunnel or deploy publicly without an explicit request. The previously committed
ngrok token is compromised by history: it must be **rotated by its owner**;
deleting it from the working tree cannot revoke it.

## 8. Data attribution (corrected)

Attribution is split between the historical thesis dataset and the 2026-10-15
expansion sample. They must not be merged into one claim.

- **Historical ~200-POI thesis dataset**: the README states it derives from
  OpenStreetMap with Traveloka/SearchNX enrichment, but that provenance has **not
  been independently verified** here (`docs/research/DATA_SOURCE_SURVEY.md` is a
  feasibility/terms review, not acquisition evidence). Treat it as unverified.
- **Expansion sample (`data/expansion_20261015/`)**: **2** Wikidata entities were
  collected (`Q703871`, `Q933384`), **0** expansion POIs were accepted, and **0**
  OSM entities were collected. One bounded Overpass request and one narrower
  retry both failed with HTTP `502`. The local `graphhopper/data/hcmc-latest.osm.pbf`
  is a possible offline source but its identity/time is uninspected. These counts
  must not be described as successful graph expansion or as two operational live
  sources.
- **Licenses**: OSM data is ODbL (attribution + share-alike obligations);
  Wikidata structured data is CC0. Preserve source records and licenses in
  exported manifests; combined dataset licensing is not automatically resolved.
