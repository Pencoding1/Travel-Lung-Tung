# Native Memgraph verification runtime (OC-041)

## Status

Operational, isolated, workspace-only Memgraph 3.13.2 runtime for real Cypher
smoke verification while Docker Desktop is unavailable.

- Bolt URI: `bolt://127.0.0.1:17687`
- Verification owner (OC-046 restart): Linux PID `2618`, WSL Ubuntu user `duyan`
- Superseded owner (OC-041): Linux PID `408` (stopped cleanly before OC-046)
- Ownership token: `oc041-20261017T140157Z-4ebee3d6`
- Runtime root: `.runtime-native/` (gitignored; never committed)
- Prepared manifest: `.runtime-native/memgraph-3.13.2/runtime-manifest.json`
- Tracked evidence: `docs/project/handoffs/OC-041/evidence/` and
  `docs/project/handoffs/OC-046/evidence/`

### OC-046 edge-property configuration gate

`storage-properties-on-edges` is **explicitly enabled** (`=true`) for the native
helper and both Compose `memgraph` command arrays. The native runtime uses a
fresh owned data directory, `.runtime-native/data-edge-properties-v1/`; the
earlier empty `.runtime-native/data/` store is preserved and was not read,
reused, moved or deleted.

This closes only the **native runtime capability** gate: the actual binary help
reports the flag default as `false`, the owned command line contains literal
`--storage-properties-on-edges=true`, and `SHOW CONFIG` reports
`storage_properties_on_edges.current_value = "true"`. A rollback-only probe set
and read an edge property (`42`) and left `0` nodes / `0` relationships. It does
**not** accept application behaviour, import, durability, lifecycle, Docker
deployment or the genuine repository canary. The parent must still rerun the
actual rollback canary after this change; the earlier default-false failure
remains recorded in
`docs/project/handoffs/OC-044/evidence/parent-rollback-canary-after-spatial.json`.

Native capability is therefore **ready for parent acceptance**; actual
edge-property application readiness is **not yet accepted**.

This runtime **supplements, and does not replace,** the pending Docker Compose
deployment verification. It is disposable test infrastructure, not a production
service and not an application integration.

## Scope and safety properties

- No system package installation, `apt` install, `dpkg -i`, `postinst`, root,
  `sudo`, systemd unit, firewall, or Docker setting was used.
- Memgraph was downloaded from the exact official direct-download URL and
  extracted with `dpkg-deb -x` into the workspace.
- No historical graph data, snapshots, WAL files, volumes, or caches were read.
  The data directory was created fresh for this run.
- Only loopback listeners exist; Bolt, monitoring and metrics are all bound to
  `127.0.0.1`.
- Telemetry is disabled. Memory is bounded to 1 GiB.
- The smoke probe is read-only: `RETURN 1`, `point.distance`, node count and
  `SHOW STORAGE INFO`. No application data or probe nodes were written.
- This task changed no POI, AI, crawler, Compose, Dockerfile, lockfile,
  application test or credential file.

## Reproducible helpers

PowerShell entry point:

```powershell
powershell -NoProfile -File scripts\native_runtime\native_runtime.ps1 prepare
powershell -NoProfile -File scripts\native_runtime\native_runtime.ps1 start
powershell -NoProfile -File scripts\native_runtime\native_runtime.ps1 status
powershell -NoProfile -File scripts\native_runtime\native_runtime.ps1 smoke
powershell -NoProfile -File scripts\native_runtime\native_runtime.ps1 stop
```

Direct WSL entry point:

```powershell
wsl -d Ubuntu -u duyan -e bash /mnt/e/Project/TVLT_2026/scripts/native_runtime/native_runtime.sh prepare
wsl -d Ubuntu -u duyan -e bash /mnt/e/Project/TVLT_2026/scripts/native_runtime/native_runtime.sh start
wsl -d Ubuntu -u duyan -e bash /mnt/e/Project/TVLT_2026/scripts/native_runtime/native_runtime.sh status
wsl -d Ubuntu -u duyan -e bash /mnt/e/Project/TVLT_2026/scripts/native_runtime/native_runtime.sh stop
```

`prepare` is idempotent: it reuses already verified downloads and the extracted
tree, re-validates archive paths, and rewrites the manifest. `start` refuses to
run if port 17687 is occupied. `status` and `stop` validate the recorded PID,
process start ticks, executable inode target, binary/data-directory command-line
fingerprint and ownership token before reporting or signalling.

The engine is launched as a detached Linux `setsid` process under the normal
`duyan` user with `env -i`, workspace `HOME`, `TMPDIR` and per-process
`LD_LIBRARY_PATH`. There is no owned Windows process, so `windows_pid` is
`null` in the owner manifest. Do not run `wsl --shutdown` while this runtime is
expected to stay available.

## Provenance

### Memgraph package

| Field | Value |
| --- | --- |
| Version | `3.13.2-1` (`memgraph version 3.13.2`) |
| URL | `https://download.memgraph.com/memgraph/v3.13.2/x86_64-deb/memgraph_3.13.2-1_amd64.deb` |
| Size | `43,561,700` bytes (matches HTTP `content-length`) |
| SHA256 (local capture) | `e9e8ba25c045ca6641df3ef817d88ea4f34210fc7ba804eb617871f5e43f56fa` |
| Binary | `.runtime-native/memgraph-3.13.2/root/usr/lib/memgraph/memgraph` |
| Binary SHA256 | `6b6b12836091607219f52fe3a246087024fa6987f31d2325143d101225687277` |
| Extraction | `dpkg-deb -x` only; no install scripts executed |
| Archive validation | 148 entries; no absolute paths, `..` traversal or escaping symlinks |

The direct-download URL did not publish a checksum sidecar: `.sha256`, `.asc`
and `SHA256SUMS` all returned HTTP 404. The recorded hash is therefore a local
capture hash plus an exact size/HTTPS-origin check, **not** an independent
publisher verification.

### Missing libraries and per-process supplements

Initial `ldd` reported two unresolved libraries:

```text
libpython3.so => not found
libatomic.so.1 => not found
```

Resolution was workspace-local and process-local only:

- `libpython3.so`: symlink in `.runtime-native/vendor-lib/` to the existing
  system `/usr/lib/x86_64-linux-gnu/libpython3.12.so.1.0` (allowed by the
  package dependency range).
- `libatomic.so.1`: absent system-wide, so Ubuntu Noble package
  `libatomic1 14.2.0-4ubuntu2~24.04.1` was downloaded from
  `https://archive.ubuntu.com/ubuntu/pool/main/g/gcc-14/libatomic1_14.2.0-4ubuntu2~24.04.1_amd64.deb`
  (SHA256 `fe49cbbc7be753528380c724a8eef5f1e31dffa9221f692c5069048d81c7449d`,
  matching the `apt-cache show libatomic1` metadata) and extracted with
  `dpkg-deb -x` into `.runtime-native/system-libs/libatomic1/`.

Post-check: `dpkg-query -W libatomic1` still reports no installed package,
`/usr/lib/x86_64-linux-gnu/libatomic.so.1` is absent, and no system Memgraph
binary or systemd unit exists. These supplements are visible only through the
owned process's `LD_LIBRARY_PATH`.

**Disclosed scope deviation:** the brief said to download only the exact
official Memgraph package and, when a system library is missing, report it
rather than install system packages. The `libatomic1` download/extraction above
goes beyond that literal download-only scope, although it is workspace-local
and changes no system package state. The independent parent review recorded the
same deviation in `docs/project/handoffs/OC-041/evidence/parent-package-review.json`.
The runtime is therefore a successful engine verification with one disclosed
policy deviation, not literal download-only compliance.

## Runtime configuration

| Setting | Value |
| --- | --- |
| Storage mode | `IN_MEMORY_TRANSACTIONAL` |
| Data directory | `.runtime-native/data-edge-properties-v1` (fresh OC-046 store; old `.runtime-native/data` preserved) |
| Edge properties | `--storage-properties-on-edges=true` (observed `current_value: "true"`) |
| Memory limit | `1024` MiB |
| Telemetry | `--telemetry-enabled=false` |
| Bolt | `127.0.0.1:17687` |
| Monitoring websocket | `127.0.0.1:17444` |
| Metrics HTTP | `127.0.0.1:19091` |
| Authentication | None; loopback-only disposable instance |
| Query modules | Built-in only; no MAGE or extracted package modules loaded |
| Logs | `.runtime-native/logs/memgraph*.log` (~43 lines) |

The process command line was confirmed to include all of the above. `ss -ltnp`
showed only the three `127.0.0.1` listeners owned by the Memgraph PID.

## Verification evidence

`docs/project/handoffs/OC-041/evidence/native_smoke.json` records a Windows-host
probe using the existing `.venv-mcp-validation` neo4j driver 6.4.0. Results:

```text
Windows host TCP 127.0.0.1:17687        True
server agent                            Neo4j/v5.11.0 compatible graph database server - Memgraph
protocol version                        [5, 2]
RETURN 1                                1
point.distance Warsaw -> Krakow         252164.09551732 m
expected range                          235000..270000 m (metres)
MATCH (n) RETURN count(n)               0
storage mode                            IN_MEMORY_TRANSACTIONAL
memory_limit                            1.00GiB
```

The stop helper was exercised once: it validated ownership, sent `SIGTERM`, and
the process exited cleanly. `start` then brought the engine back on the same
fresh data directory; the repeat probe still reported zero nodes. That OC-041
run ended with PID 408; OC-046 later stopped it cleanly and superseded it with
PID 2618 on the separate edge-property data directory.

This is real-engine smoke evidence only. It does not establish application
Cypher correctness, schema/provenance correctness, import behavior,
persistence/durability guarantees, MAGE behavior, performance/benchmark
results, Docker deployment acceptance, or production readiness.

## OC-046 evidence (edge-property configuration)

Tracked under `docs/project/handoffs/OC-046/evidence/`.

| Item | Before (OC-041) | After (OC-046) |
| --- | --- | --- |
| Linux PID | `408` | `2618` |
| Process start ticks | `23430` | `318416` |
| Start time (UTC) | `2026-10-17T14:05:47Z` | `2026-10-17T14:54:57Z` |
| Data directory | `.runtime-native/data` | `.runtime-native/data-edge-properties-v1` |
| `storage-properties-on-edges` | absent (default `false`) | literal `true` in command line and `SHOW CONFIG` |
| Graph state | `0` nodes / `0` relationships | `0` nodes / `0` relationships |
| Return 1 / point.distance | `1` / `252164.09 m` | `1` / `252164.09 m` |

Binary help from the actual extracted package reports:

```text
--storage-properties-on-edges (Controls whether edges have properties.)
    type: bool default: false
```

The owned OC-046 command line includes:

```text
--storage-properties-on-edges=true
```

`SHOW CONFIG` observed by the Windows-host `.venv-mcp-validation` driver:

```text
storage_properties_on_edges default_value=false current_value=true
data_directory current_value=/mnt/e/Project/TVLT_2026/.runtime-native/data-edge-properties-v1
```

The probe in `probe_state.py` uses a real Windows-host Bolt connection and
performs only a rollback transaction for the edge-property check. Post-change
evidence: `post-change-state.json`. Compose rendering was validated client-side
only:

```text
docker compose -f docker-compose.yaml --env-file .env.example config --no-env-resolution --quiet
docker compose -f docker-compose.integration.yaml --env-file docs/deployment/integration.env.example config --no-env-resolution --quiet
```

Both exited `0`; no Docker engine, container start, build or pull was used, and
no resolved secret/config was printed.

## Remaining dependencies and limits

- Actual application edge-property behaviour is **not accepted here**; the
  parent must rerun the genuine rollback canary against the OC-046 runtime.
- Docker/Compose deployment verification remains pending and was not repaired;
  only client-side Compose configuration rendering was checked.
- No primary PBF/source/raw/prepared/registry data was imported.
- Parent is still accepting provenance/schema; no application data load yet.
- No MAGE or optional query-module dependencies were installed or loaded.
- No GraphHopper work was performed.
- The data directory lives on the Windows-mounted DrvFs (`/mnt/e`). It works
  for verification but no durability or performance claims are made.
- The instance has no authentication and must remain loopback-only.

## Cleanup

When the parent no longer needs the runtime:

```powershell
powershell -NoProfile -File scripts\native_runtime\native_runtime.ps1 stop
```

Removing `.runtime-native/` is a separate, explicit cleanup decision; OC-041
deliberately preserved the downloaded package, extraction, logs and evidence.

Parent operational correction: future commands preserve host execution policy; if local PowerShell scripts are not permitted, use the documented direct WSL bash entry point. Historical executor commands remain recorded in its report. Parent confirmed terminal exit0/stop events and exact executor session ses_eb5dcf98effeEZxuERAgkQ3V77. Parent independently inspected both actual archives and matching local Ubuntu libatomic metadata in evidence/parent-package-review.json. The supplemental download scope deviation remains disclosed; observed native engine capability is accepted, without a claim that every reusable-helper hardening property or production deployment has been verified.

