# ADR 007 — Chat ReAct loop, observability and two-tier memory

- Status: accepted
- Date: 2026-10-15
- Task: OC-009
- Supersedes: none
- Related: `docs/decisions/004-itinerary-grounding.md`,
  `tests/ai_grounding/`, `docs/experiments/EXPERIMENT_PROTOCOL.md` (E1, E4)

## Context

`ai_service/main.py`'s `/chat` surface had three defects:

1. `execute_agent_loop` executed the tools for the first model turn and then
   returned a hard-coded "hitting a limit" string **inside the first `while`
   iteration**, so the second model call never happened. Multi-step ReAct was
   never actually exercised.
2. There was no structured trace, status or usage: the loop returned a bare
   string with no tool chain, and successes and failures were indistinguishable.
3. Conversation state was an unbounded module-global `chat_history` dict with
   no trimming, no session isolation and no memory tier distinction. There was no
   durable, user-authored profile path at all.

At the same time `/generate_itinerary` bound `reply.uid` to `request.session_id`,
which conflates a caller-supplied session id with an identity/owner.

## Decision

### 1. A real, bounded ReAct loop in a pure module

`domains/chat_agent.py` implements `run_agent_loop` with injected model/tool
awaitables:

- at most `MAX_TURNS = 5` model turns and `MAX_TOOL_CALLS = 8` tool calls;
- **the loop continues after appending tool results** (the original bug);
- every tool result message carries the exact `tool_call_id` from the model; a
  missing id is normalized onto both the assistant `tool_calls` entry and the
  tool message so they always match;
- unknown tool names and arguments that do not decode to a JSON **object** are
  refused with a sanitized trace error and are never executed;
- MCP envelopes are parsed with the OC-005 `grounding.parse_mcp_tool_result`
  helpers (`isError` / `success:false` fail closed);
- an invalid model response or transport failure yields a structured
  failure/partial result with a trace — never a traceback or raw credentials;
- the turn/tool budget is explicit; exhaustion returns `status="partial"` with a
  `loop_limit` flag rather than claiming a finished answer.

### 2. Honest grounding labels and a real tool trace

- `tool_chain` contains **only actual tool executions** (chain-of-thought is not
  a tool trace).
- A travel answer that used at least one usable tool result is labelled
  `grounding_status="unverified_free_text"` and returns the `source_evidence_ids`
  observed in tool payloads. The free text is never presented as verified.
- If the model answers with **no usable tool data** (no tools, all failed, or an
  empty `results` list / `null` `result`), the loop returns
  `insufficient_data` and a refusal message instead of hallucinated suggestions.
- ADR 004's `/generate_itinerary` grounding contracts are unchanged.

### 3. Usage accounting

`new_usage`/`record_usage`/`record_failed_call` accumulate provider
`input`/`output`/`total` tokens **when present**, across the router and every
model call, including attempts that failed or produced an unusable response.
Unknown values stay `None` (never coerced to `0`). A separately labelled
character proxy (`char_estimate`) is reported as an approximation and is never
claimed to be provider tokens.

### 4. Bounded working memory (`domains/memory.py`)

- Configurable `max_completed_turns`, `max_sessions` and `ttl_seconds`.
- Trimming removes **whole turns** only, so a tool exchange is never cut in half
  and no `tool` message is orphaned from its assistant call.
- The persona system prompt appears **exactly once**; older user messages are
  folded into a deterministic *extractive* summary (verbatim, truncated user
  text — no new facts, no paraphrase) injected into that single system message.
  The current user message is always preserved verbatim, so current constraints
  are never lost.
- Same-session requests are serialized by a per-key `asyncio.Lock`; distinct
  sessions are isolated.
- Only discarded-turn and character counts are recorded, never provider tokens.
- The legacy global `chat_history` is retained as a **bounded** LRU
  compatibility wrapper; new code uses `WorkingMemory`.

### 5. Opt-in, authenticated durable profiles

- An explicit, user-authored schema: `preferred_categories` (id→bounded finite
  weight), `tags`, `budget`/`currency`, `pace`, `accessibility`. Unknown fields
  (including inferred dietary/medical traits) are rejected; values must be
  finite and bounded.
- `SQLiteProfileStore` uses the stdlib `sqlite3`, one connection per operation,
  explicit transactions, fixed identifiers and **only bound parameters**. A
  malicious subject is inert data. Records carry `version` and `updated_at`;
  updates replace the previous profile; a version mismatch raises
  `ProfileConflict` → HTTP 409; delete removes the row.
- **Deviation from the existing `backend_service` Firestore profile service:**
  that service is unfinished and non-functional, so OC-009 deliberately does not
  reuse it. The `ProfileStore` protocol keeps a future Firestore implementation
  substitutable while shipping a working local SQLite adapter.
- Durable memory is **opt-in**: it requires an explicit `MEMORY_DB_PATH`. There
  is no default persistent personal-data file. A blank/unset path disables the
  endpoints (503).
- Cross-session ownership is the **verified JWT `sub`** only. `verify_bearer`
  requires an HS256 token with `exp` and a nonblank `sub`; missing config is 503,
  invalid/expired/wrong-signature/subject-less tokens are 401. Working memory is
  namespaced by `sub:session`; the anonymous scope is explicitly local-only and
  never exposes a durable profile.
- `/chat` and `/generate_itinerary` accept an **optional** bearer for profile
  injection. An absent token means no long-term profile; a supplied-but-invalid
  token fails 401 and is never silently downgraded to anonymous.

### 6. Profile injection and priority

`profile_prompt` renders a bounded block that states the stored profile is
**secondary**: "Current explicit request constraints ALWAYS override this
profile." Category ids are echoed verbatim (never fabricated). A missing profile
produces no personalized claim (`memory.profile_injected=false`). The block is
injected into both the chat prompt and the itinerary synthesis prompt. When
`memory_enabled=false`, both short- and long-term memory are bypassed and only
the current turn reaches the model.

### 7. `/generate_itinerary` identity

`reply.uid` is a **verified JWT subject or null** — never `session_id` or the
model's `uid`. The HTTP route (`generate_itinerary_http`) derives `uid` from the
optional bearer; a malformed supplied token is 401.

The in-process entry point `generate_itinerary_endpoint(request, uid=None)` is
anonymous by default and only adopts a subject that the caller has already
verified; the session id is never used as an owner. (The former session-derived
compatibility default was removed by the OC-009 corrective QA, and the one stale
OC-005 assertion was updated to expect `null`.)

## Alternatives considered

- **Repair the loop inside `main.py` only.** Rejected: untestable without
  in-process fakes and mixes I/O with loop semantics.
- **Unbounded `chat_history` with a hard truncation.** Rejected: can orphan tool
  messages and loses user constraints.
- **LLM-summarized history.** Rejected: introduces new facts; the protocol
  requires deterministic extraction.
- **Reuse `backend_service` Firestore.** Rejected: unfinished/unusable.
- **Default durable file / anonymous owner fallback.** Rejected: silent
  persistent personal data and unauthenticated ownership are unacceptable.
- **Treat chain-of-thought as the tool trace.** Rejected: it is not an execution
  trace.

## Consequences

- Positive: genuine multi-step execution, inspectable tool trace, explicit
  status/usage, bounded and isolated memory, opt-in authenticated durable
  profiles, no fabricated grounding claims.
- Trade-off: durable profiles need `JWT_SECRET` and `MEMORY_DB_PATH`; anonymous
  chat memory is local-only and **not** production multi-user authentication.
- Limitation: `/generate_itinerary`'s direct-call default retains a
  session-derived `uid` for OC-005 compatibility (see note above).
- Evidence: mocked in-process contract tests only; no live model, MCP, graph or
  database call (see `docs/project/handoffs/OC-009/`).

## Corrective addendum — collision-safe working-memory namespace (OC-015)

- Status: accepted
- Date: 2026-10-15
- Task: OC-015 (corrective follow-up to OC-009)
- Supersedes (in part): section 5, "Working memory is namespaced by `sub:session`"

### Defect

The OC-009 key derivation `_memory_key` concatenated the owner and session with
a colon: `f"{owner}:{session_id}"`. This is **not injective** over the tuple it
is meant to identify:

- `("a:b", "c")` and `("a", "b:c")` both derive `"a:b:c"` (colon reassociation);
- the anonymous scope (`owner = "anonymous"`) aliases a verified subject whose
  literal `sub` is `"anonymous"`, both deriving `"anonymous:<session>"`;
- a long subject plus session can exceed `WorkingMemory`'s 200-character key
  bound, surfacing an uncaught `ValueError` from `_check_key` as a 500 instead of
  an explicit error.

Two distinct identities could therefore share — and read/clear — one working
memory namespace.

### Fix

`_memory_key(subject, session_id)` now encodes the tuple
`(scope kind, exact subject, exact session)` as a **fixed-length SHA-256 digest
of canonical JSON** (`{"scope", "subject", "session_id"}`, `sort_keys=True`,
compact separators). Properties:

- **Injectivity (practical):** distinct tuples map to distinct 256-bit digests;
  colon characters and whitespace in identifiers are preserved verbatim — they
  are never stripped, normalized or banned.
- **Scope separation:** anonymous is `scope="anonymous", subject=null`, while a
  verified subject (including the literal `"anonymous"`) is
  `scope="user", subject=<exact sub>`.
- **Bounded key:** the derived key is `wm:` + 64 hex chars = 67 characters,
  independent of identifier length, so it always satisfies the working-memory
  key bound.
- **Explicit subject bound:** `domains.memory_auth.MAX_SUBJECT_CHARS = 512`;
  `decode_subject` rejects an overlong verified subject with HTTP 401
  `subject_too_long` at the auth boundary (all of `verify_bearer` /
  `optional_bearer` / both `/chat` and `/memory/short/clear`). The exact verified
  subject is otherwise retained unchanged.
- **No migration required:** working memory is process-local, so there is no
  persisted key to migrate; durable profile rows remain owner-keyed by the exact
  verified `sub` (unchanged).

### Evidence

`tests/ai_chat_memory/test_namespace_integration.py`: real `/chat` and
`/memory/short/clear` calls with synthetic HS256 JWTs (secret ≥ 32 bytes),
asserting isolation via the **fake model contexts** (not key strings) for the two
colliding `(subject, session)` pairs and for anonymous vs a literal `anonymous`
subject; scoped clear isolation both ways; an overlong subject producing a
structured 401; and a five-turn ReAct chain that threads the resolver/category
metadata into the next model call, grounds only on the real POI id, and keeps a
metadata-only final answer `insufficient_data`. This addendum is mocked
in-process contract evidence; no live call is made (see
`docs/project/handoffs/OC-015/`).
