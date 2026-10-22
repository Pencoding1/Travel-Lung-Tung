# EXP089 — read-only live E2 spatial collector

This package is a **separate** E2 collector. It does not modify or reuse the
historical synthetic benchmark in `benchmarks/spatial/`.

## What it measures

For the fixed radii **1, 3 and 5 km**, on the full primary snapshot:

* baseline correctness: every eligible unordered external-ID pair `a < b` is
  tested with the engine's `point.distance` and the fixed radius threshold, and
  the accepted pair rows are returned;
* optimized correctness: the production conservative prefilter is applied
  first, then the **same** `point.distance` predicate and threshold, and the
  accepted pair rows are returned;
* candidate count: a separate read-only query counts pairs passing the exact
  same production prefilter;
* timing baseline/optimized: fixed count-only variants of the two correctness
  queries. They keep the same pair generation, `point.distance` expression and
  radius threshold, but the only final `RETURN` is
  `RETURN count(*) AS accepted_pairs`.

The accepted pair sets are compared in RAM per anchor batch, not by count
alone. The collector persists counts, canonical SHA256 digests, false
negatives/positives, bounded mismatch samples and every batch status.

Timing latency is **count-only end-to-end latency**: it includes producing the
server-side aggregate, not transferring every accepted pair row. The timing
query must return exactly one non-boolean, non-negative integer
`accepted_pairs` no greater than the batch's actual potential pair count.

Candidate counts are **logical prefilter predicate/input counts**. They are not
physically instrumented engine evaluation counts. No latency-improvement or
subquadratic-complexity claim is made.

## Dry run is the default

```text
python benchmarks/spatial_live/runner.py
```

A dry run reads the public primary JSONL, validates its shape and prints a plan.
It makes **zero** driver or network calls and labels itself
`plan_only: true`, `scientific_result: false`, `latency_measured: false`.

The planned full primary input is:

* `data/primary_20261016/graph_ready_v2/prepared_pois.jsonl`
* SHA256 `37340a8021ca7e8b37efc1053718c4c87879f95fa9937d8c53e1a0218f080dd1`
* 6,367 records
* 20,266,161 unordered potential pairs

A subset fixture is always labelled `is_full_primary: false`; it is never
presented as the full primary dataset.

## Reviewed execute only

```text
python benchmarks/spatial_live/runner.py \
  --execute \
  --manifest <reviewed-frozen-manifest.json> \
  --output <new-result.json>
```

`--execute` refuses to start unless:

* the manifest is `frozen: true`;
* the reviewer decision is `approved` and a reviewer is recorded;
* the exact input, collector, production `spatial.py` and every query text hash
  match the manifest;
* the fixed scope hash, 1/3/5 km radii, 128-anchor batches, 1 warm-up and 5
  measured repetitions, 120 s per-query and 3600 s whole-run budgets match;
* the output is new/nonempty-free and a single-writer lock can be acquired.

The manifest emitted by a dry run is deliberately **unfrozen** and
`review: pending` (`candidate_manifest` in the plan JSON). The collector never
sets `frozen: true` itself.

The only live endpoint is the fixed loopback
`bolt://127.0.0.1:17687` with `auth=None`. There is no CLI or manifest switch
for a remote URL, password, provider or model.

## Evidence boundary

* The driver import/construction is lazy and happens only after every manifest
  and output gate passes in an explicit `--execute` run.
* Queries are fixed, parameterized, read-only `MATCH`/`UNWIND`/`WITH`/`WHERE`/
  `RETURN` templates (plus fixed `SHOW INDEX INFO` metadata). There is no
  `CALL`, `CREATE`, `MERGE`, `SET`, `DELETE`, `LOAD` or `DROP`.
* Source areas are **dataset labels**. They are not verified current
  administrative containment.
* Read-only canonical queries do **not** prove stored `:NEAR_BY` relationship
  orientation, duplicate or stale-update semantics. The collector only captures
  fixed directed materialization counts separately. DATA068 is separate prior
  evidence.
* Every timing cell is 1 labelled warm-up plus 5 measured repetitions per
  radius and arm. Warm-ups are excluded from the reported median/range.
  There is no retry, resume or best-of.
* A failure retains earlier rows and marks the remaining 36-cell denominator
  as missing. A missing query is never converted to an empty accepted set or a
  fabricated zero. A malformed timing count (missing, multiple rows, boolean,
  negative or above the actual batch potential) is a failed cell, not zero.
* Explicit installed-driver authorization/permission denial is terminal. It is
  recognized only from the closed public `.code` set
  (`Neo.ClientError.Security.Unauthorized`, `...Forbidden`,
  `...CredentialsExpired`, `...AuthorizationExpired`) or the explicit
  `AuthError`/`AuthConfigurationError`/`Forbidden` exception class names. Raw
  messages/codes and arbitrary text are not retained or used for diagnosis.
  At metadata it blocks the run before any benchmark query; later it stops all
  remaining batches/radii/arms/stages, keeps finished receipts, and records the
  remaining planned items as missing. A generic unsupported `SHOW INDEX INFO`
  remains a disclosed optional metadata gap.
* Offline tests use an in-memory fake database and fake clock. They are
  synthetic engineering evidence, not live Memgraph measurements.

## Remaining work

Actual `--execute`, real engine evidence, `SHOW INDEX INFO` availability,
materialization orientation/duplicate/stale-update tests and disposable-database
fixtures (including poles, dateline, identical coordinates and cross-area
labels) require a separately reviewed live/disposable DB scope. This package
does not create fixture nodes on a populated graph and does not perform those
tests now.

## EXP092 durability and bounded supervision (source amendment)

This amendment adds completed-unit durability and a hard **client-side** process
bound. It does not change any scientific query, radius, anchor batch, warm-up,
repetition, arm order, query text/hash allow-list, projection gate or
auth-denial rule. There are **no new live E2 measurements** in this package yet.

### Journal (completed units, not a result)

`--execute` writes an append-only local JSONL journal beside the output:

```text
<output>.journal.jsonl
```

* stdlib only; opened exclusively (`O_CREAT|O_EXCL`), never truncated, never
  reused, and refused before backend construction if it already exists;
* the header binds the exact frozen-manifest SHA256, input SHA256, live
  runner/journal/supervisor source pins and protocol `exp092.durable.v1`;
* every canonical record is sequence-numbered and SHA256 hash-chained; each
  record is flushed and `fsync`-ed before the next unit starts;
* run-start is durable before backend construction, then projection outcome,
  each finished correctness anchor batch, each final correctness radius, each
  finished timing cell and a bounded final summary are appended;
* timing cells are journaled only **after** `_run_timing_cell` records its end
  clock, so journal I/O is never inside a measured cell; correctness-batch
  journal I/O is outside timing measurement;
* an interrupted/unattempted batch, radius or cell stays **missing**. No zero,
  no synthetic success and no resume is produced. A partially written final
  line is exposed by the offline reader as an explicit incomplete-tail gap and
  is never admitted as an event.

`benchmarks.spatial_live.journal.read_journal()` is offline/read-only. It
rejects interior corruption, checksum/chain breaks, duplicates,
out-of-order sequence and foreign bindings. `fsync` reduces risk; it cannot
prove survival of every hardware/storage failure.

### Output write

The final JSON is written through a same-directory temporary file, flush,
`fsync` and `os.replace` while the existing single-writer output lock is held.
An interrupted write leaves the previous committed file and the journal intact.

### Direct execute vs supervised execute

Direct execute remains available with the same frozen-manifest and scientific
gates:

```text
python -B -X utf8 -m benchmarks.spatial_live.runner --execute \
  --input <path> --manifest <frozen.json> --output <new.json>
```

Bounded supervision launches exactly one fixed child with a list argv
(`shell=False`), suppresses raw child stdout/stderr and records closed
exit/status/timing metadata in a separate atomic `<output>.supervisor.json`:

```text
python -B -X utf8 -m benchmarks.spatial_live.supervisor \
  --input <path> --manifest <frozen.json> --output <new.json>
```

The full-mode hard deadline is 3600 s from child launch plus up to 10 s bounded cleanup
(<=5 s terminate, then only if needed <=5 s kill of that exact child). A
timeout does not prove instantaneous engine transaction cancellation; in-flight
state stays unknown and only the last durable journal unit is known. The
supervisor never infers worker success, invents timings or launches a second
child. Preflight refusals (input/manifest/source-pin/output/journal/report)
spawn zero children. The parent does not pre-create the worker lock.

### Honest limits

* Direct vs supervised: both share the same worker code and gates; the
  supervisor adds process observation and a hard client kill, not extra
  scientific evidence.
* There is no retry, resume, fallback or alternate endpoint. A missing unit is
  never filled in later.
* Per-query timeout remains an engine request (`min(120 s, remaining run
  budget)`), not a guaranteed wall-clock cancellation.
* Journal append/`fsync` and supervisor polling add elapsed time outside
  measured timing cells; they are not part of the latency definition.
* Offline fake-backend/dummy-subprocess tests are synthetic engineering
  evidence, not live Memgraph measurements.

### TIM096: independent timing-only cohort

Codex editorial clarification after independent offline QA: a manifest with
`collection_mode: timing_only_external_correctness` uses protocol
`tim096.external_correctness.v1` and a fixed 7200 s budget in both supervisor
and worker. A missing mode remains legacy `full`, with 3600 s. The CLI has no
budget override. A candidate remains unfrozen until separately reviewed;
offline acceptance does not authorize a live run.

The new mode requires hash-pinned old frozen manifest, durable journal,
parent review and archived runner/journal/supervisor sources. It checks old
source pins against those archives, unchanged query/spatial/input bindings,
the complete correctness chain and actual pair-universe denominators before
constructing a backend or child. Both lexical and resolved reference paths
must stay within approved public trees and match the expected artifact role;
sensitive names and traversal are refused before reading.

After validation it performs a fresh full POI projection check and only the
36 count-only timing cells (6 warm-ups, 30 measured, radii 1/3/5 km).
Each observed count must match its prior engine count; a mismatch fails that
cell and leaves later cells missing without retry. Correctness evidence is
labeled reused, with zero new correctness queries and no invented fresh
pair-set observations. A projection check plus count agreement does not
re-prove raw pair-set equality or a transactionally isolated graph snapshot.

This is a new cohort, never a resume or repair of E2093: its old missing
timings, journal and retained lock stay unchanged. The metric is engine-defined
`point.distance`, not the Python fixed-radius 6371 km reference. OPS094/MET095
observed different distances/counts; Python invocation counters are not
physical Memgraph invocation counters. Exact metric implementation and
physical engine operations remain separate evidence gaps.
