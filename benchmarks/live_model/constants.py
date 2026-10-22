"""Frozen constants for the OC-021 live-model paired H2 collector.

Everything here is a *declared* control, not a discovery. Changing any value is a
change of experimental conditions and must be recorded as a new manifest version.
"""

from __future__ import annotations

# The single provider/model under test: the user-authorized alias for controlled
# live experiments. The production Gemini configuration is never read or
# modified by this collector.
#
# ``MODEL_ID`` is the *requested* qualified id. The configured display name is
# recorded separately, and a matching alias is explicitly NOT evidence that an
# upstream "4.1" checkpoint was served (see ``MODEL_UPSTREAM_VERSION_VERIFIED``).
MODEL_ID = "aibox/ds/deepseek-flash"
MODEL_DISPLAY_NAME = "DeepSeek V4 Flash"
MODEL_UPSTREAM_VERSION_VERIFIED = False
MODEL_VERSION_NOTE = ("requested alias 'aibox/ds/deepseek-flash'; display name "
                      "'DeepSeek V4 Flash'; upstream '4.1' not verified")

# A unique primary experiment agent, scoped to the child process only via
# OPENCODE_CONFIG_CONTENT. It denies every tool ('*': 'deny').
EXPERIMENT_AGENT = "h2-live-collector"

# The system prompt shipped inside the per-process agent config. It is shared by
# both conditions (it is part of the settings, not the per-condition instruction).
AGENT_SYSTEM_PROMPT = (
    "Return only the requested JSON object. Do not use tools, do not read or "
    "write files, do not run commands, do not ask questions."
)

# Output schema identifiers.
H2_SCHEMA_VERSION = "oc18.h2.v1"
EVIDENCE_LEVEL = "live_model"
DATASET_KIND = "synthetic_live_engineering"

# OC-023 bumps the experimental method/manifest version. The evaluated hybrid arm
# now runs the *production* scheduler (``domains.planning.schedule``). Any run
# created before this version is incompatible and must not silently mix with a
# resumed run (the run-state fingerprint enforces this).
METHOD_VERSION = "oc23.live.v2"
MANIFEST_VERSION = "oc23.live.v2"

# Paired conditions. Order is the declared pairing order for the evaluator
# (condition_a - condition_b); the *execution* order alternates deterministically.
CONDITION_HYBRID = "hybrid"
CONDITION_LLM_ONLY = "llm_only"
CONDITIONS = (CONDITION_HYBRID, CONDITION_LLM_ONLY)

# The frozen input manifest is synthetic engineering fixtures; it is never
# modified and author_expected is never sent to the model.
SCENARIOS_MANIFEST_VERSION = "oc-010.v2"
FROZEN_SCENARIO_COUNT = 20

# Defaults for bounded execution.
DEFAULT_REPETITIONS = 1
DEFAULT_TIMEOUT_SECONDS = 120.0
DEFAULT_MAX_CALLS = 40

# CLI flags that must never be used: --continue, --session, --share, --auto.
FORBIDDEN_CLI_FLAGS = ("--continue", "-c", "--session", "-s", "--share", "--auto", "--fork")

# Nonblank label used in every engineering artifact.
RUN_LABEL = "live-model-synthetic-engineering"

# ---------------------------------------------------------------------------
# EXP-074: explicit transport selection.
#
# ``production-v2`` is the default for the revised collector and routes model
# text through the already-accepted ``OpenCodeCliProvider.complete`` seam. The
# legacy V1 capture path is preserved only for historical tests/resumes and is
# *not* compatible with the installed CLI 2.0.32.
# ---------------------------------------------------------------------------
TRANSPORT_PRODUCTION_V2 = "production-v2"
TRANSPORT_LEGACY_V1 = "legacy-v1"
TRANSPORTS = (TRANSPORT_PRODUCTION_V2, TRANSPORT_LEGACY_V1)
DEFAULT_TRANSPORT = TRANSPORT_PRODUCTION_V2

# New-path declarations are derived explicitly so the historical fixture
# identity above stays byte-for-byte unchanged.
V2_MODEL_ID = "opencode-go/deepseek-v4.1-flash"
V2_MODEL_DISPLAY_NAME = "DeepSeek V4.1 Flash"
V2_MODEL_UPSTREAM_VERSION_VERIFIED = False
V2_MODEL_VERSION_NOTE = (
    "requested alias 'opencode-go/deepseek-v4.1-flash'; user-confirmed identity "
    "'DeepSeek V4.1 Flash'; independent upstream checkpoint verification not "
    "established")
V2_PROVIDER = "opencode_cli"
V2_TRANSPORT_METHOD = "OpenCodeCliProvider.complete"
V2_MAX_ATTEMPTS = 1
V2_MAX_CONCURRENCY = 1
# Deliberate, disclosed compatibility: the installed CLI does not advertise
# --pure, so the V2 path explicitly opts out instead of silently dropping it.
V2_CLI_PURE = False

# Fresh method/manifest identity for the new transport path and the EXP-077
# timing-only companion endpoint. Legacy ``oc23.live.v2`` fingerprints remain
# readable through ``--transport legacy-v1``; old ``exp074.live.v1`` runs are
# incompatible and must fail closed before any provider call.
V2_METHOD_VERSION = "exp077.live.v1"
V2_MANIFEST_VERSION = "exp077.live.v1"

# Dataset declarations. The historical scenarios.json has no ``dataset_kind``
# and is therefore explicitly synthetic; a manifest can never be promoted to
# primary by path/count alone.
DATASET_CLASS_SYNTHETIC = "synthetic_fixture"
DATASET_CLASS_PRIMARY = "real_supplied_primary_snapshot"
PRIMARY_MIN_THESIS_SCENARIOS = 20
