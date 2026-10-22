# AI service

FastAPI service for Travel Lung Tung chat, grounded itinerary synthesis, bounded
short-term memory and opt-in durable profiles.

The service is the **only** authority for MCP tool calls, the deterministic
planner and the independent validator. A model may propose content or tool
calls; it never executes anything.

## Run

```powershell
uvicorn main:app --host 0.0.0.0 --port 8002
```

`main.py` resolves `prompt.json` relative to its own file. The Docker image runs
from `/workspace/ai_service`; no service secret is baked into the image.

## Model providers

Provider selection is explicit and process-local. The default is unchanged
Gemini; there is **no silent fallback** between providers.

| Variable | Default | Meaning |
| --- | --- | --- |
| `AI_LLM_PROVIDER` | `gemini` | Exactly `gemini` or `opencode_cli`. |
| `GEMINI_MODEL` | `gemini-2.5-pro` | Gemini model (default mode only). |
| `AI_CLI_MODEL` | `aibox/ds/deepseek-flash` | Requested CLI alias (opt-in mode). |
| `AI_CLI_EXECUTABLE` | auto-resolve | Optional path/name of the native CLI. |
| `AI_CLI_AGENT` | `travel-ai-cli-transport` | Per-process primary agent name. |
| `AI_CLI_TIMEOUT_SECONDS` | `120` | Per-command bound (max 600). |
| `AI_CLI_MAX_OUTPUT_BYTES` | `2000000` | Shared stdout+stderr bound. |
| `AI_CLI_MAX_PROMPT_CHARS` | `200000` | Translated prompt bound. |
| `AI_CLI_MAX_ATTEMPTS` | `1` | Bounded attempts (max 3). |
| `AI_CLI_MAX_CONCURRENCY` | `2` | Bounded in-flight CLI calls (max 8). |
| `AI_CLI_PURE` | `true` | Adds only `run --pure` (disables external plugins). |
| `AI_CLI_EVIDENCE_DIR` | unset | Explicit opt-in raw evidence directory. |

An invalid provider/option, a missing or unsafe CLI executable, a timeout,
output overflow, malformed stream/export, a denied native tool action, or a
provenance mismatch produces a bounded `model_unavailable`-class failure. It
does not call Gemini instead.

### OpenCode CLI mode (`AI_LLM_PROVIDER=opencode_cli`)

The CLI is a **model transport only**:

* every child process gets a fresh per-call ``opencode.json`` whose unique
  primary agent has `permission: {"*": "deny"}`; no files/shell/network/tools;
* `--pure` only disables external plugins and is never a permission relaxation;
* the prompt is passed as one argument with `shell=False`; Windows `.cmd`/`.bat`
  wrappers are refused in favour of `opencode.exe`;
* the service alone executes allowlisted MCP tool calls. For tool-enabled turns
  the CLI must return a strict JSON envelope
  `{"tool_calls":[{"id","name","arguments"}]}`; ids/names/arguments are validated
  against the server tool schemas before any call is returned to the loop;
* plain router JSON, itinerary JSON and ordinary chat text remain assistant
  content (they are not treated as tool calls);
* the exact newly created session is read back with `opencode export <sessionID>`
  and must prove the observed `providerID/modelID` (exactly
  `aibox/ds/deepseek-flash` by default), message/part ids, terminal `stop`,
  text and token components. The requested alias is never injected as observed
  proof. `DeepSeek V4.1 Flash` is the user-confirmed identity; the upstream
  checkpoint remains independently unverified (`upstream_version_verified:
  false`). Neither the display name nor the alias is a provider attestation.

#### OpenCode Go alias

The exact opt-in alias `opencode-go/deepseek-v4.1-flash` binds the built-in
Go provider through the per-call config:

```json
{"providers":{"opencode-go":{"settings":{"apiKey":"{env:OPENCODE_API}"}}}}
```

Only the literal reference is written to the transport config; the value is
never written to config, argv, metadata, evidence or errors. The application
loader takes process `OPENCODE_API` first; only when it is absent does it read
that one key from the code-relative project `.env`, bounded and without
interpolation. Explicit blank/invalid process values fail closed and never fall
through to the file. The key is added only to the Go CLI child environment
(shared by readiness, run and export), not to MCP or another service. The
default CLI alias remains `aibox/ds/deepseek-flash`; no global default changes.

The production image does **not** include OpenCode. CLI mode requires an existing
supported executable in the selected runtime and fails clearly when absent.
Installation/packaging is out of scope here.

#### Request controls

`temperature` (finite, `0..2`) and `top_p` (finite, `0..1`) are validated and
applied per call to the per-process CLI agent configuration; they are not
encoded into prompt text. Any other explicitly supplied provider control
(`max_tokens`, `max_completion_tokens`, `top_k`, `stream`, `tool_choice`, etc.)
fails with a clear `unsupported_model_control`/`invalid_sampling_control` error
before model invocation.

The existing service token caps are Gemini-only. In CLI mode the service does
not send an unsupported token cap and discloses this under
`provider.unsupported_controls`; no text instruction or provider-option guess is
used to pretend the cap was enforced.

#### Usage accounting

Observed components are preserved separately. Prompt usage is
`input + cache_read + cache_write`; completion usage is `output + reasoning`.
The provider total is kept verbatim (never recomputed), so cache/reasoning are
not double-counted. This is **assistant/model-call accounting only**: OpenCode
auxiliary costs (titles, config/plugin work, any other provider traffic) are not
measured. Failed service calls remain in `usage.model_calls`; provider retry
attempts stay visible in `provider.calls`.

#### Evidence and local storage

OpenCode stores its own local sessions. By default this service writes no raw
conversation log. Setting `AI_CLI_EVIDENCE_DIR` explicitly enables raw
`events.jsonl`, stderr, session export and a metadata sidecar for synthetic
verification; the export contains the prompt. Treat that directory as sensitive
and opt-in.

Profile/summary memory is deterministic and extractive; it does not make a
separate model call, so there is no hidden profile/summary provider cost.

## Tests

Offline contract tests use fake transports and never call a live model:

```powershell
.\.venv-ai-validation\Scripts\python.exe -m pytest tests/ai_chat_memory tests/ai_grounding tests/ai_planning_integration tests/ai_provider -q
```
