# Offline evaluation runbook (OC-018)

Version `oc18.eval.v1`, 2026-10-15. This runbook documents the **reproducible
offline evaluator** for the paired H2 (E3) itinerary outcomes and the H3 (E4)
memory-profile outcomes. It supersedes nothing in
`EXPERIMENT_PROTOCOL.md` / `HUMAN_STUDY_PROTOCOL.md`; it is the tool that scores
*recorded* outcomes once real runs exist.

The evaluator is **stdlib-only** and makes no model, provider, database, graph,
network or credential call. It never executes an experiment and never fabricates
a record: runtime/model unavailability is expected, and the evaluator is
designed to report that honestly rather than invent results. The human-study
protocol is **not** replaced by synthetic participants.

## 1. Inputs

* **Frozen manifest** (per hypothesis) declaring scenario/profile IDs, declared
  paired conditions, repetition count and authored truth. See
  `benchmarks/evaluation/SCHEMA.md` for the full versioned schema.
* **Raw JSONL records** (`oc18.h2.v1` / `oc18.h3.v1`) keyed by
  `(scenario, condition, repetition)` and
  `(profile, scenario, condition, repetition)`.

Inputs are hashed (SHA-256) and echoed in the metrics and in a per-run
`*_run_manifest.json`.

## 2. Commands

Run from the repository root with the validation interpreter:

```
.venv-validation\Scripts\python.exe benchmarks/evaluation/evaluator.py smoke --out benchmarks/evaluation/demo

.venv-validation\Scripts\python.exe benchmarks/evaluation/evaluator.py h2 ^
    --manifest <h2_manifest.json> --records <h2_records.jsonl> --out <dir>

.venv-validation\Scripts\python.exe benchmarks/evaluation/evaluator.py h3 ^
    --manifest <h3_manifest.json> --records <h3_records.jsonl> --out <dir>
```

`--out` is **required**. The CLI writes only inside the supplied directory and
refuses to overwrite an input manifest or records file. Each run writes:

* `h2_metrics.json` / `h3_metrics.json` — machine-readable metrics + diagnostics;
* `h2_report.txt` / `h3_report.txt` — human-readable summary;
* `h2_run_manifest.json` / `h3_run_manifest.json` — input hashes, output hash,
  evaluator version, timestamp.

`smoke` additionally writes `SYNTHETIC_EVALUATOR_TEST.txt` and `smoke_demo.json`,
both prominently labelled **SYNTHETIC EVALUATOR TEST**.

## 3. H2 metrics

Planned denominator = scenarios × paired conditions × repetitions. Descriptive
metrics are reported per condition with explicit denominators:

* **delivery rate** = delivered plans / planned runs;
* **validated-feasibility rate** = validated-feasible plans / planned runs;
* **determined violation rate** (`determined_violation_rate`) = delivered plans
  with a *known* violation / delivered plans with a *determined* outcome
  (clean or known violation), reported with its `numerator`, `denominator`, the
  all-delivered `delivered_denominator` and a `coverage` = determined / delivered.
  When nothing delivered is determined the value is `null` — an
  unverifiable-only set is never 0.0 and is never called clean;
* **observed known-violation lower bound** (`observed_known_violation_lower_bound`)
  = known violations / **all** delivered plans. This is a **lower bound** only:
  undetermined delivered plans are not clean, so the true rate may be higher;
* plus **unverifiable**, **refusal**, **failure** and **empty** rates.

The ambiguous legacy key `verified_violation_rate_among_delivered` equals the
determined-subset rate and is retained only for compatibility; it is listed under
`deprecated_metrics` and must not be quoted as an all-delivered rate. The CLI
report and the JSON metrics use the same names, numerators and denominators.

Delivery and outcome are orthogonal. A real non-empty plan is delivered even when
it is unverifiable (it is not a refusal). A known violation is retained even when
`unverifiable` is true. Failures, errors, refusals, empty plans, unverifiable
(missing-hours) outcomes and missing runs all remain in the planned denominator
and are counted separately; none is ever a zero-violation delivered success.

Outcome fields are required and never defaulted to a verified zero. Contradictory
records are rejected outright: `feasible` with any known violation; a `false`
flag with a nonzero/absent count; a `true` flag with a *complete* count of zero;
`unverifiable` with a `false` flag; a complete count with a null count.

**Paired inference** uses the single declared binary scenario outcome
`scenario_has_verified_temporal_violation`:

* repetitions are aggregated within a scenario *before* resampling;
* the scenario is the independent unit (repeated runs are never treated as
  independent scenarios);
* a scenario is only credited with "no verified violation" when **all** planned
  repetitions are complete valid observations; a known violation stays true even
  with incomplete coverage; anything else stays unknown;
* pairing requires **complete comparable coverage** in both conditions, so one
  observed run is never compared against the planned repetition count;
* exact two-sided McNemar is reported with exposed discordant counts;
* the paired effect `rate(A) − rate(B)` over eligible scenarios gets a scenario
  bootstrap 95% percentile interval (fixed seed `20261015`, 10000 draws by
  default, linear-interpolation percentiles).

Inference is **blocked** (and the reason reported) when: evidence is not
`live_model`, provenance is missing or incompatible across the pair, or there
are no eligible pairs. Ineligible scenarios are listed with their exclusion
reason; the descriptive denominators are always retained.

## 4. H3 metrics

Preferred share per profile and condition = preferred selected stops / **all**
selected stops (the protocol denominator), where a selected stop is preferred
when its frozen category intersects the authored active preferred-category truth.
The truth is evaluated per scenario so a current explicit preference override is
honoured. When any selected stop has an unknown category or unknown authored
preference, no exact share is claimed: the value is `null` (reason
`coverage_gap`) with a coverage interval (`preferred_share_lower`..
`preferred_share_upper`, coverage of resolved stops, and a separately labelled
`resolved_subset_share` diagnostic). A single preferred stop plus an unknown stop
therefore reports `lower=0.5`, `upper=1.0` and is never an unqualified 100%.

* empty plan → share `null` (reason `empty_plan`);
* selected stop with no frozen category → **coverage gap**
  (`unknown_category_stops`), not counted for or against preference;
* scenario with no authored preference truth → coverage gap
  (`unknown_preference_stops`);
* no selected stops → share `null` (reason `no_selected_stops`).

Every declared profile is reported, including null and negative effects
(`two_tier − memory_disabled` is never clamped). Constraint validity
(`evaluated`, `valid`, `rate`) is reported alongside every share so preference
gains cannot hide invalid scheduling.

Usage sums **all** declared provider-call stages (summary, extraction,
retrieval, final) plus retries. A missing stage, a missing basis or a character
proxy makes the total **unknown** (`missing != 0`). Cold and amortized costs are
reported separately when supplied; no time saving is inferred. Latency is kept
in raw seconds and failure retries are retained. Token reduction is `null` with
a reason when usage is unknown or the baseline total is zero.

## 5. Evidence levels and labelling

Every record declares `evidence_level` and `dataset_kind`. When all records are
`live_model`, the label is a live-evidence evaluation awaiting owner review;
otherwise the output is labelled **SYNTHETIC EVALUATOR TEST** (or inconclusive).
`thesis_conclusion` is always `false` — the evaluator never asserts a thesis
conclusion. Synthetic results must never be reported as H2/H3 conclusions, and
the shipped fixtures/demo are engineering smoke tests only.

## 6. Reproducibility

* Hashing: SHA-256 over input bytes and over the canonical metrics payload.
* Statistics: exact McNemar via integer binomial coefficients; bootstrap with a
  fixed seed and the documented percentile method. Re-running the same inputs
  yields byte-identical point estimates and interval endpoints (the run-manifest
  timestamp is the only non-deterministic field).

## 7. Tests

```
.venv-validation\Scripts\python.exe -m pytest tests/evaluation -q -p no:cacheprovider
```

The suite asserts actual metrics and denominators (not just JSON keys): all
failures, all refusals, empty plans, unknown hours, negative preference effect,
no eligible pairs, mixed provenance, duplicate/unknown keys, missing
repetitions, clustered repetition exclusion, exact McNemar tiny cases,
seed-repeatability, undefined token ratios, missing stage usage, character
proxies, and arithmetic preferred share with unknown categories.

## 8. Limitations

* No live model/provider/dataset run is performed or claimed here; the original
  ~200-POI snapshot and configured model access remain dependencies owned by the
  protocol, not this evaluator.
* The evaluator only scores what is recorded. Missing or unknown outcomes limit
  what can be inferred, and that limitation is surfaced explicitly rather than
  papered over.
