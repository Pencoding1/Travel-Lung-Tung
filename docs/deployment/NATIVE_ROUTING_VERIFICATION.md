# Native GraphHopper 11.1 routing verification

- task_id: OC-042
- executor session: `ses_eb5ca6622ffedFZk0bZp4mO0yj`
- completed_at_utc: 2026-10-17T15:13Z
- status: complete; workspace-owned runtime left running and healthy
- scope: real routing engine only; not Docker/Compose, application integration,
  primary import, H2/H3, benchmark, route-optimality, or full-goal acceptance

## Result

A real GraphHopper 11.1 engine was imported and started from the pinned Maven
artifact using an extracted, workspace-local Temurin JRE 21.0.12.1. It serves
loopback-only HTTP and admin endpoints from a fresh graph cache:

- HTTP: `http://127.0.0.1:18989` (Windows host reaches this through WSL
  localhost forwarding)
- admin: `http://127.0.0.1:18990`
- Linux PID: `2869` (WSL user `duyan`)
- ownership token: `64749b6198a74a4c896a73e538a520fe`
- process start-time ticks: `328597`
- JVM heap cap: `-Xmx1024m`; observed RSS 366536 kB, peak 380388 kB after route checks
- graph: HCMC PBF, 262184 nodes, 317083 edges, car CH with 179944 shortcuts
- profiles in `/info`: `car`, `foot`
- elevation: false
- import date: `2026-10-17T14:22:06Z`
- OSM data date: `2026-03-17T23:00:00Z`

All four real route requests passed. No online service, mock route, or
straight-line substitute was used.

## Pinned provenance

### GraphHopper

- source:
  `https://repo.maven.apache.org/maven2/com/graphhopper/graphhopper-web/11.1/graphhopper-web-11.1.jar`
- bytes: `47331301`
- actual SHA-256:
  `8462f758d9ea49edaded557cec5c687a0a24f004ec371cd4daaeb0534824ea33`
- Maven `.sha1`, `.md5`, `.sha256`, `.sha512` files all returned HTTP 200;
  actual bytes match the published `.sha1`, `.sha256`, and `.sha512` values.
- JAR metadata: manifest/pom version `11.1`; build JDK `17.0.20.1`.
- The official advisory GHSA-mg8w-mq9r-f9c6 lists 3.0 through 11.0 affected
  and 11.1/12.0-pre3 patched. This run used 11.1, not 11.0. No vulnerability
  absence or exploit-resistance claim is made beyond the version choice.

### JRE

- source:
  `https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.12.1%2B1/OpenJDK21U-jre_x64_linux_hotspot_21.0.12.1_1.tar.gz`
- bytes: `52059408`
- vendor-published `.sha256.txt` was fetched independently; it contains
  `2413149700df0f7d440500a84a8f764c535f21e5a5e87d38328b64eec2c5b500`, which
  matches the actual bytes.
- a detached `.sig` was also published and downloaded (310 bytes), but it was
  not cryptographically verified. The checksum match is the only integrity
  proof claimed here.
- archive inspection before extraction: 320 entries, 112 regular files,
  63 directories, 145 symlinks. There were no absolute or parent-relative
  paths, no devices, fifos, or hardlinks, and no install scripts. Every
  symlink target was relative and resolved inside the single top-level
  `jdk-21.0.12.1+1-jre` tree.
- extraction target was empty and fresh; no system install was performed.
- `java -version`:
  `openjdk version "21.0.12.1" 2026-08-18 LTS`,
  `Temurin-21.0.12.1+1`, 64-bit Server VM.
- actual `bin/java` SHA-256:
  `999c141a6e620c71aa4230ccb62341a89162f37818753ff006d766bf935dcbe1`.

### PBF

- source:
  `graphhopper/data/hcmc-latest.osm.pbf` (read-only input)
- bytes: `17907596`
- SHA-256 before and after:
  `c2b7057e7a022ff929692205e4219c59640fc67fd90525a82428022b43cf4afb`
- The PBF was not downloaded again or replaced. The existing
  `graphhopper/data/config.yml` was read only; its SHA-256 is
  `dfd70479abe52d3ff811b12e0508e7cbfb254d3c9b0921bf252f8beaafd25421`.

## Runtime layout and limits

All runtime, download, cache, log, state, HOME, and TMPDIR paths are under:

- `.runtime-native/graphhopper-11.1/` (JAR, config, cache, logs, state, work)
- `.runtime-native/java-21.0.12.1/` (JRE download/root/home/tmp)

The source PBF and the graph cache are separate. The cache is
`.runtime-native/graphhopper-11.1/graph-cache`, never
`graphhopper/data/graph-cache`.

The JVM was launched by absolute path with per-process `HOME` and `TMPDIR`.
No global `JAVA_HOME`, `PATH`, firewall, package, or system configuration was
changed. The heap cap is 1 GiB; the process used about 358 MiB RSS and
380388 kB peak after route checks. The existing Memgraph process (`PID 2618`, memory limit 1024) was not
read, stopped, or reconfigured.

WSL host capacity observed during the run: 7752 MiB total, 6873 MiB available;
project volume 104444563456 bytes available. The download helpers reject
artifacts above 256 MiB and require at least 2 GiB free.

## Configuration and profile compatibility

The native config is
`.runtime-native/graphhopper-11.1/config/config.yml` (SHA-256
`d7935dfbc7d9fcab4b542733f3142d5867003213f5de742fd0392fbfcf7cf853`).

It uses the official built-in models packaged in the 11.1 JAR:

- `car`: `custom_model_files: [car.json]`, CH preparation enabled
- `foot`: `custom_model_files: [foot.json]`, no CH/LM preparation

GraphHopper 11.1 requires `import.osm.ignored_highways` to be explicit. The
native config sets `construction` only, retaining footways, steps, paths, and
cycleways so the foot profile can use them. This differs from the existing
application config, which excludes `footway,construction,cycleway,path,steps`.
The car profile still blocks non-car ways through `car_access`; nevertheless
this is not an identical car graph to the application config. No attempt is
made to claim exact graph equivalence.

Foot requests must use `ch.disable=true` because only `car` has CH. Car
requests use the configured CH preparation. These are engine-profile
capabilities, not proof that the current application can consume the foot
profile: `graphhopper/test.py` still targets port 8989 with the `car` profile,
and no application/Compose source was changed.

Elevation is disabled. `foot_elevation.json` was not used and no SRTM or other
external data was fetched. No custom model, user-upload endpoint, or remote
host endpoint was enabled.

## Health evidence

Read from the Windows host with `curl.exe` against `127.0.0.1`:

- `GET /health` -> HTTP 200, body `OK`
- `GET /info` -> HTTP 200, version `11.1`, profiles `car` and `foot`,
  `elevation:false`, data date `2026-03-17T23:00:00Z`
- admin `GET /healthcheck` on 18990 -> HTTP 200, `deadlocks` and
  `graphhopper` both `healthy:true`
- `GET /info/health` -> HTTP 404
  `{"code":404,"message":"HTTP 404 Not Found"}`. GraphHopper 11.1 exposes
  `/health` and `/info`, not `/info/health`; the 404 is an endpoint fact, not
  an unhealthy engine. The readiness helper therefore uses `/health`.

The first Windows-host attempt returned an empty reply because the WSL relay
exposed only an IPv6-mapped loopback listener; a separate parent read-only
probe preserved a Windows `10061` failure at the same stage. The per-process
JVM option `-Djava.net.preferIPv4Stack=true` produced an IPv4 loopback
listener and made Windows `127.0.0.1:18989` work. No Windows proxy or firewall
change was made. Parent review is recorded in
`docs/project/handoffs/OC-042/parent-readiness-review.md`; final parent
acceptance is not claimed.

## Real route results

All requests used `points_encoded=false`, `instructions=true`, `locale=en`,
and the exact URLs recorded in
`.runtime-native/graphhopper-11.1/state/routes-summary.json`. Car requests
used the CH preparation; foot requests added `ch.disable=true`.

| profile | pair | HTTP | distance (m) | time (ms) | points | snap start/end offset (m) | result |
|---|---|---|---:|---:|---:|---:|---|
| car | Tan Son Nhat -> Ben Thanh | 200 | 7288.322 | 518145 | 70 | 202.4 / 59.1 | pass |
| car | City Hall -> Binh Tay | 200 | 6474.972 | 438493 | 92 | 50.4 / 7.3 | pass |
| foot | Tan Son Nhat -> Ben Thanh | 200 | 7166.864 | 5160148 | 126 | 202.4 / 59.1 | pass |
| foot | City Hall -> Binh Tay | 200 | 7052.180 | 5077570 | 132 | 43.5 / 7.3 | pass |

Route failure denominator: 4 requested, 4 HTTP 200, 4 pass, 0 fail. All
distances and times are finite and nonnegative, all routes have more than ten
geometry points, and all snapped endpoints are within 500 m of the requested
points. The straight-line references (5928.56 m and 6142.75 m) are reported
only as geometric references and are not labeled as road distance.

Raw response files and SHA-256 values:

- `state/route-car-tan-son-nhat-to-ben-thanh.json`
  `a5c5c579e88a4e9a6932c6ebe23f6952a821b1fae81f93131641a66de8e217a5`
- `state/route-car-city-hall-to-binh-tay.json`
  `5143689110e9348eb3686bad3ef73792bd379ad12be679dd8d02c2db23e8a964`
- `state/route-foot-tan-son-nhat-to-ben-thanh.json`
  `66de671a542c9dceb01aa48db40bb61e89ee03da55a13b324a6ccd7b75849c08`
- `state/route-foot-city-hall-to-binh-tay.json`
  `d13b08dd393882dad02d126ef1e8f467d9bd1d66759094acdc5df8eac3ba6f1a`

The summary, info response, health headers/bodies, and ownership fingerprints
are in `.runtime-native/graphhopper-11.1/state/`.

## Startup attempts and corrections

1. First start failed before import because GraphHopper 11.1 requires an
   explicit `import.osm.ignored_highways`. Corrected once with
   `import.osm.ignored_highways: construction` to retain footways for foot.
2. Second start imported and listened on both loopback ports, but the harness
   readiness query used the absent `/info/health` and timed out after 10
   minutes; the process then shut down cleanly. Corrected by using `/health`.
3. Third start was healthy inside WSL but Windows received an empty reply
   through the IPv6-mapped relay. Corrected with the per-process IPv4 stack
   option.
4. Final start succeeded and is the currently running runtime.

Only item 1 was an engine/config requirement correction. Items 2 and 3 were
harness endpoint selection and host/relay integration corrections. All
failures and their concrete causes are preserved in
`.runtime-native/graphhopper-11.1/state/runtime-manifest.json` and the logs.

## Lifecycle checks

- Duplicate start while the owned runtime was alive: refused with exit `10`;
  the existing process was not signaled or restarted.
- Status: ownership-checked PID, executable, cwd, full command line,
  start-time ticks, token, both listeners, and `/health`; result
  `running_owned_healthy`.
- Owned stop: validated PID `2296`, sent `SIGTERM` only after revalidation,
  confirmed process exit and both ports free; result `stopped_owned`.
- Restart: new runtime PID `2869`; Windows launcher PID `35264` (ephemeral);
  ready in 10166 ms; final status `running_owned_healthy`.
- No broad `pkill`/`taskkill`, foreign listener reuse, or Memgraph signal was
  used. The Windows port owner is the shared `wslrelay.exe` PID `32972`, not a
  process owned by this task.

## Reproduce

From `E:\Project\TVLT_2026`:

```powershell
# Download and verify pinned artifacts
wsl -e bash /mnt/e/Project/TVLT_2026/scripts/native_routing/fetch_artifacts.sh
wsl -e bash /mnt/e/Project/TVLT_2026/scripts/native_routing/inspect_and_extract.sh

# Start (Windows Start-Process must stay hidden)
$p = Start-Process -FilePath "wsl.exe" -ArgumentList @('-d','Ubuntu','-e','bash','/mnt/e/Project/TVLT_2026/scripts/native_routing/start_runtime.sh') -WindowStyle Hidden -PassThru

# Verify, inspect, stop, restart
& "E:\Project\TVLT_2026\scripts\native_routing\verify_routes.ps1"
wsl -e bash /mnt/e/Project/TVLT_2026/scripts/native_routing/status_runtime.sh
wsl -e bash /mnt/e/Project/TVLT_2026/scripts/native_routing/stop_runtime.sh
wsl -e bash /mnt/e/Project/TVLT_2026/scripts/native_routing/restart_runtime.sh
wsl -e python3 /mnt/e/Project/TVLT_2026/scripts/native_routing/snapshot_runtime.py
```

## Application integration next steps

1. Decide whether application traffic uses this native runtime on 18989 or a
   containerized GraphHopper on the existing 8989 contract.
2. If native, point the application's GraphHopper base URL at 18989 and keep
   the car URL contract (`/route`, `profile=car`). Do not silently switch the
   application to foot.
3. If foot is exposed to the application, either add foot CH preparation (more
   import time/memory) or send `ch.disable=true`; verify the application's
   timeout and response-size expectations.
4. Reconcile `import.osm.ignored_highways`: the dual-profile graph must retain
   footways, while the current application graph excludes them. This is a real
   graph-composition difference even though both use the official car model.
5. Add a health check against `/health` (not `/info/health`) and keep both
   listeners loopback-only.
6. Re-run Docker/Compose and application integration gates separately; this
   document does not close those gates.

## Artifacts

- `scripts/native_routing/fetch_artifacts.sh`
- `scripts/native_routing/inspect_and_extract.sh`
- `scripts/native_routing/inspect_profiles.py`
- `scripts/native_routing/start_runtime.sh`
- `scripts/native_routing/status_runtime.sh`
- `scripts/native_routing/stop_runtime.sh`
- `scripts/native_routing/restart_runtime.sh`
- `scripts/native_routing/verify_routes.ps1`
- `scripts/native_routing/snapshot_runtime.py`
- `docs/project/handoffs/OC-042/report.md`
- `.runtime-native/graphhopper-11.1/state/runtime-manifest.json`
- `.runtime-native/graphhopper-11.1/state/routes-summary.json`
- `.runtime-native/graphhopper-11.1/state/route-*.json`
- `.runtime-native/graphhopper-11.1/logs/` and `state/`

The runtime is intentionally left running for parent follow-up. Stop it with
`wsl -e bash /mnt/e/Project/TVLT_2026/scripts/native_routing/stop_runtime.sh`.
