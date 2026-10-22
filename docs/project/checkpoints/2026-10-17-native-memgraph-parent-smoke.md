# Native Memgraph capability checkpoint — 2026-10-17

Overall goal ACTIVE/INCOMPLETE. This phase changes the live-engine gap: Docker remains unverified, but the same Memgraph product now answers real read-only probes through an isolated native workspace runtime.

## Independent evidence

Parent normal-host verification at2026-10-17T14:07UTC:
- `native_runtime.sh status` exit0: ownership-validated Linux PID408, start ticks23430, exact executable inside `.runtime-native/memgraph-3.13.2/root`, workspace data directory, ownership token `oc041-20261017T140157Z-4ebee3d6`.
- `ss` shows all three engine listeners bound to127.0.0.1: Bolt17687, monitoring17444, metrics19091. Foreign endpoint0.0.0.0:* is not the local listen address.
- Parent `smoke_probe.py` exit0, saved `OC-041/evidence/parent-native-smoke.json`: real Windows-host Bolt server identifies Memgraph, RETURN1=1, WGS84 point.distance=252164.09551732metres for the documented reference pair, totalnodes=0, configuredmemorylimit1GiB.
- Actual extracted binary `--version`: **memgraph version3.13.2**.
- Actual official core DEB SHA256 `e9e8ba25c045ca6641df3ef817d88ea4f34210fc7ba804eb617871f5e43f56fa`.
- Supplemental libatomic1 DEB SHA256 `fe49cbbc7be753528380c724a8eef5f1e31dffa9221f692c5069048d81c7449d`.
- Actual raw primary GeoJSON hash remains `713b07a62cf89bd2cad9093abaad2a4c5f01e23853321764b3d66bf9f7eee43c`.

## Limits and scope deviation

OC041 process57252 is still live; do not edit its runtime/helper/report scope or assume terminal from files. Exact executor session `ses_eb5dcf98effeEZxuERAgkQ3V77`. Helper/lifecycle full acceptance remains pending final report/diff review. Runtime is currently left running, but revalidate ownership/readiness next session before use; PID numbers are not durable identity.

Executor downloaded an additional official Ubuntu libatomic1 package and extracted it under workspace, beyond the brief's exact Memgraph-only download instruction (which allowed existing extracted vendor libraries). No system installation is evidenced; this is a scope deviation, not proof of compliant execution. Preserve it and inspect package/source/hash provenance before accepting reproducible helper scope. Existing system libpython3.12 is exposed via a per-process workspace link. No MAGE compatibility proof. No approval denial is being bypassed.

The real read-only engine capability is independently proved. This does NOT prove application Cypher compatibility, production import, durable lifecycle, current administration, routes, Docker build/deployment or scientific experiments. No database writes or primary import have been authorized to this executor. Preserve fresh state until a bounded application test/import contract is written and safety-checked.

## Next actions and other ownership

1. Wait for OC041 terminal; review final code/report/dependency handling and lifecycle evidence. Keep healthy instance for subsequent bounded actual application tests.
2. OC038R1 remains live80001/ses_eb6103739ffeZrz54I1vR7BAJ8; parent provenance probes and regression suites required after terminal, before graph-ready adapter/source-snapshot retrieval work.
3. OC040 model-label correction terminal exit0 accepted editorially: current identity DeepSeekV4.1Flash, exact aibox/ds/deepseek-flash, no explicitV4.0. Parent corrected mistaken executor-session-none report; no experimental call was made. Full adapter rejected by independent behavioral probes despite310offlinepasses. Bounded R1 now **process17682**, exact session `ses_eb5fadef2ffe2uT6PlXliJ6gS9`, brief `OC-040/revision-1.md`, log `events-r1.log`. No live model calls until parent acceptance.
4. Portable routing candidate metadata verified/saved `docs/project/native-routing-candidate-20261017.json`: official AdoptiumAPI exact JRE21.0.12.1+1link/checksum, GraphHopper11.1 MavenJAR HEAD200/47331301bytes. This is research only; no routing binary downloaded/started. Prepare a separate bounded task after native writer releases scope, reuse immutable graphhopper/data/hcmc-latest.osm.pbf with fresh cache, loopback-only listeners, ownership and actual route/unit checks. Check current official patched release/advisory; do not use11.0 blindly.
5. Finish all MASTER_GOAL SG01–19/AC01–12 including full primary integration, source-native expansion, real routes/full deployment, controlled H2/H3/memory/adversarial experiments, evidence-backed60–70page thesis and real H1 when participants become available. H1 currently has none; do not re-ask absent changed availability or fabricate study results. Save checkpoint after each major phase.
