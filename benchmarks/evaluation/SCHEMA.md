# OC-018 evaluator raw-record schema (versioned)

The evaluator consumes two clearly separated inputs per hypothesis:

| Hypothesis | Manifest | Raw records |
|---|---|---|
| H2 (E3, hybrid itinerary vs LLM-only) | H2 manifest JSON | `oc18.h2.v1` JSONL |
| H3 (E4, two-tier memory / personalization) | H3 manifest JSON | `oc18.h3.v1` JSONL |

Raw records are **explicit recorded outcomes**. The evaluator never executes a
live experiment, never calls a model/provider/network, and never fabricates a
record. A record is one *observation*; the manifest declares which observations
are expected.

## Keying, duplicates and unknown keys

* H2 key = `(scenario_id, condition, repetition)`.
* H3 key = `(profile_id, scenario_id, condition, repetition)`.
* A duplicated key is a hard `RecordError` (never a silent overwrite).
* A `scenario_id`, `profile_id`, `condition` or `repetition` that the manifest
  does not declare is a hard `RecordError`.
* A key declared by the manifest but absent from the records is a **missing run**:
  it stays in the planned denominator and is reported, never dropped.
* Blank lines in JSONL are ignored; a non-object or malformed line fails closed
  with its line number.

## Enum values

* `evidence_level` ∈ {`synthetic_engineering`, `live_model`}.
* `dataset_kind` — free nonblank string, e.g. `synthetic_fixtures`,
  `original_thesis_snapshot`.
* H2 `run_status` ∈ {`completed`, `failed`, `error`, `refused`}.
* H3 `run_status` ∈ {`completed`, `failed`, `error`}.
* `validation_status` ∈ {`feasible`, `partial`, `unverifiable`, `no_plan`,
  `failed`, `unknown`}.
* H2 conditions default to a declared pair (`hybrid`, `llm_only`).
* H3 conditions must distinguish `memory_disabled`, `short_term`, `two_tier`;
  the baseline is `memory_disabled`.

## H2 record — `schema_version = "oc18.h2.v1"`

Required fields:

| field | type | meaning |
|---|---|---|
| `task` | `"H2"` | task discriminator |
| `evidence_level` | enum | synthetic fixture vs live-model evidence |
| `dataset_kind` | string | which dataset the record came from |
| `scenario_id` | string | manifest scenario |
| `condition` | string | declared paired condition |
| `repetition` | int ≥ 0 | repetition index within scenario/condition |
| `run_status` | enum | terminal run state |
| `plan_present` | bool | a plan object was produced |
| `empty_plan` | bool | the plan has no stops |
| `validation_status` | enum | independent validator verdict |
| `temporal_violation` | bool \| null | *observed* temporal violation flag |
| `known_temporal_violations` | int ≥ 0 \| null | count of known violations |
| `violation_count_complete` | bool | the count is a complete enumeration |
| `unverifiable` | bool | required; missing never means "verified false" |

Optional: `unknown_reasons` (string[]), `provenance` (see below), `usage` (see
below), and the secondary fields `selected_poi_ids`, `grounded_source_poi_ids`,
`budget_deviation` (`{amount, currency, unit, comparable}`),
`route_travel_minutes`, `route_distance_km`, `latency_seconds`.

**Completeness contract (required, never defaulted):** every outcome field above
must be present. `violation_count_complete` may be true only when
`known_temporal_violations` is an integer. A missing count/flag is a hard error,
not a verified zero.

**Contradictions are rejected** (they raise `RecordError`, never coerce):

* `validation_status == "feasible"` with any known violation, a non-`false`
  flag, or `unverifiable == true`;
* `temporal_violation == false` with a nonzero **or absent** count, or while
  `unverifiable == true`;
* `temporal_violation == true` with a **complete** count of zero;
* `violation_count_complete == true` with `known_temporal_violations == null`.

**Delivery vs outcome (orthogonal).** Delivery ∈ {`delivered`, `failed`, `error`,
`refused`, `empty`, `missing`}. A real non-empty plan is delivered even when it
is unverifiable (it is not a refusal). Outcome ∈ {`violation`, `clean`,
`unverifiable`, `unknown`, `not_delivered`}: a known violation is retained even
when other facts are unknown; an unknown is never counted as clean.

**Scenario aggregation.** A known violation makes the scenario outcome `true`
even with incomplete coverage. "No verified violation" (`false`) requires **all**
planned repetitions to be complete valid observations. Otherwise the outcome is
`null`. Pairing requires complete comparable coverage in both conditions, so one
observed run is never compared against the planned repetition count.

**Reported violation denominators (metrics == CLI report).** `determined_violation_rate`
carries `numerator`, `denominator` (determined delivered), `delivered_denominator`
(all delivered) and `coverage` (determined / delivered); it is `null` when no
delivered plan is determined. `observed_known_violation_lower_bound` divides known
violations by **all** delivered plans and is a lower bound (undetermined delivered
plans are not clean). The ambiguous key `verified_violation_rate_among_delivered`
is retained only as a deprecated alias of the determined-subset rate.

## H3 record — `schema_version = "oc18.h3.v1"`

Required fields:

| field | type | meaning |
|---|---|---|
| `task` | `"H3"` | task discriminator |
| `evidence_level` | enum | synthetic fixture vs live-model evidence |
| `dataset_kind` | string | which dataset the record came from |
| `profile_id` | string | declared synthetic profile |
| `scenario_id` | string | manifest scenario |
| `condition` | enum | memory condition |
| `repetition` | int ≥ 0 | repetition index |
| `run_status` | enum | terminal run state |
| `plan_present` | bool | a plan object was produced |
| `empty_plan` | bool | the plan has no stops |
| `validation_status` | enum | validator verdict |
| `unverifiable` | bool | facts missing |
| `constraint_valid` | bool \| null | independent constraint validity |
| `selected_poi_ids` | string[] | selected stop ids (grounds preferred share) |

Optional: `provenance` (required for comparative effects), `usage`,
`latency_seconds` (raw seconds), `failure_retries` (int).

**Preferred-share contract.** Denominator = **all selected stops** (after
deduplicating IDs unless the manifest sets `allow_repeated_visits: true`). A
selected stop is *preferred* when its frozen category intersects the authored
active preferred-category truth. When any selected stop has an unknown category
or unknown authored preference, no exact share is claimed: `preferred_share` is
`null` with reason `coverage_gap`, and a coverage interval `preferred_share_lower`
.. `preferred_share_upper` plus a separately labelled `resolved_subset_share` and
a `coverage` fraction are reported. One preferred stop plus one unknown stop
gives `lower=0.5`, `upper=1.0`, `resolved_subset_share=1.0` and is never an exact
100%. Empty plan → `null` (`empty_plan`); no selected stops → `null`
(`no_selected_stops`).

**Comparative effects** are computed across matching `(scenario, repetition)`
units (condition minus baseline within the same unit), never by pooling unmatched
selections. Provenance must be consistent across the two conditions of a pair
(shared `candidate_id`, `route_id`, `prompt_information_id`, `dataset_id`,
`model_id`, `settings_id`; `method_instruction_hash` may differ). A missing or
inconsistent pair blocks that effect with a reason; a missing comparator cannot
produce an effect.

## `provenance` object

Fields: `candidate_id`, `route_id`, `prompt_information_id`, `dataset_id`,
`model_id`, `settings_id`, `method_instruction_hash`. All are nonblank strings
when present. No fake model metadata is defaulted: an absent `model_id` is
unknown, not a placeholder real model name.

## `usage` object

```json
{"usage_basis": "provider_tokens",
 "stages": {"summary": 0, "extraction": 0, "retrieval": 0, "final": 0, "retries": 0},
 "cold": null, "amortized": null}
```

* `usage_basis` must be `provider_tokens`. A character/whitespace proxy is
  **forbidden** as a provider-token result (`character_proxy_forbidden`).
* The total sums `summary + extraction + retrieval + final` (plus `retries`).
  A missing required stage, basis or object makes the total **unknown**
  (never zero). `cold`/`amortized` are reported separately when supplied; no
  time saving is inferred.

## Manifests

### H2 manifest

```json
{"manifest_version": "...", "task": "H2", "label": "...", "thesis_mode": false,
 "paired_conditions": ["hybrid", "llm_only"], "repetitions_per_case": 3,
 "scenarios": [{"scenario_id": "S01"}]}
```

`thesis_mode: true` requires ≥ 20 frozen scenario IDs and exactly two distinct
paired conditions. Expected keys = scenarios × conditions × repetitions.

### H3 manifest

```json
{"manifest_version": "...", "task": "H3", "label": "...", "thesis_mode": false,
 "allow_repeated_visits": false,
 "conditions": ["memory_disabled", "short_term", "two_tier"],
 "baseline_condition": "memory_disabled", "repetitions_per_case": 1,
 "profiles": [{"profile_id": "P1"}], "scenarios": [{"scenario_id": "S01"}],
 "category_truth": {"p_food": ["cat_food"]},
 "active_preference_truth": {"P1": {"S01": ["cat_food"]}}}
```

`thesis_mode: true` requires ≥ 5 declared profiles. `category_truth` is the
frozen explicit `poi_id -> category_ids` map. `active_preference_truth` is the
authored active preferred-category truth; it must already represent any current
explicit preference override. A selected stop with no category entry, or a
scenario with no authored preference truth, is a **coverage gap**, never an
invented preference. `allow_repeated_visits` (default `false`) permits repeated
selected IDs to count as separate stops; otherwise duplicates are deduplicated
and reported.
