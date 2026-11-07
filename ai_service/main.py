import re
import os
import json
import math
import uuid
import httpx
import hashlib
import inspect
import asyncio
import logging
import contextvars

from contextlib import asynccontextmanager
from collections import OrderedDict
from pathlib import Path
from typing import List, Dict, Any, Mapping, Optional, Set, Tuple
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

# MCP Client Imports
from mcp import ClientSession
from mcp.types import TextContent
from mcp.client.sse import sse_client

from domains.payloads import (
    ChatRequest,
    ClearMemoryRequest,
    ItineraryRequest,
)
from domains import chat_agent, chat_mvp, grounding, jev_intent, memory, memory_auth, planning_adapter
from domains import source_gate
from domains.jev_intent import configure_intent_router
from domains.memory import ProfileConflict, get_profile_store
from domains.memory_auth import AuthError
from domains.planning import schedule as planning_schedule
from domains.planning import validate as planning_validate
from domains.providers import (
    AiboxHttpProvider,
    DEFAULT_AIBOX_MODEL,
    DEFAULT_CLI_MODEL,
    MODEL_DISPLAY_NAME,
    MODEL_UPSTREAM_NOTE,
    MODEL_UPSTREAM_VERSION_VERIFIED,
    PROVIDER_AIBOX,
    PROVIDER_GEMINI,
    PROVIDER_OPENCODE_CLI,
    ModelUnavailableError,
    OpenCodeCliProvider,
    ProviderConfig,
    ProviderConfigError,
    ProviderError,
    load_provider_config,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Travel_Lung_Tung_Agent")

PARENT_PATH = Path.cwd()

# --- GEMINI CONFIGURATION (default provider only) ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Using Gemini's OpenAI-compatible endpoint makes migration seamless
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://poi_mcp:8001/sse")

# Explicit, process-local provider selection. Gemini remains the default; the
# CLI mode is never selected implicitly and never falls back to Gemini.
try:
    PROVIDER: Optional[ProviderConfig] = load_provider_config()
    PROVIDER_CONFIG_ERROR: Optional[Dict[str, str]] = None
except ProviderConfigError as _provider_exc:
    PROVIDER = None
    PROVIDER_CONFIG_ERROR = {"code": _provider_exc.code,
                             "message": _provider_exc.message}
    logger.warning("Invalid AI provider configuration (%s); model calls will fail.",
                   _provider_exc.code)

if (PROVIDER is not None and PROVIDER.provider == PROVIDER_GEMINI
        and not GEMINI_API_KEY):
    logger.warning("GEMINI_API_KEY is not set. Gemini API calls will fail.")

# Jev configuration is lazy on first classification (never at module import).
# An explicit configure({}) is hermetic; env=None may load normal app
# credentials. There is no provider fallback and no default threshold.

_CLI_RUNNER = None
_CLI_CWD: Optional[Path] = None
_CLI_PROVIDER_CACHE: Optional[Tuple[Any, OpenCodeCliProvider]] = None
# Per-request provider-call observability (never contains prompts/secrets).
_PROVIDER_CALLS: contextvars.ContextVar[Optional[List[Dict[str, Any]]]] = (
    contextvars.ContextVar("provider_calls", default=None))
_MAX_PROVIDER_CALLS = 32


def configure_provider(env: Optional[Mapping[str, str]] = None, *,
                       cli_runner: Any = None,
                       cwd: Optional[Path] = None) -> Optional[ProviderConfig]:
    """Process-local provider (re)configuration for tests/operators.

    This does not mutate ``os.environ`` or any global OpenCode configuration.
    ``env=None`` reads the current environment; an explicit mapping is used as
    given (an empty mapping selects the Gemini default).
    """
    global PROVIDER, PROVIDER_CONFIG_ERROR, _CLI_RUNNER, _CLI_CWD, _CLI_PROVIDER_CACHE
    try:
        PROVIDER = load_provider_config(env)
        PROVIDER_CONFIG_ERROR = None
    except ProviderConfigError as exc:
        PROVIDER = None
        PROVIDER_CONFIG_ERROR = {"code": exc.code, "message": exc.message}
    _CLI_RUNNER = cli_runner
    _CLI_CWD = Path(cwd) if cwd is not None else None
    _CLI_PROVIDER_CACHE = None
    return PROVIDER


def _provider_name() -> str:
    if PROVIDER is not None:
        return PROVIDER.provider
    return "invalid"


def _selected_model() -> str:
    return PROVIDER.model if PROVIDER is not None else GEMINI_MODEL


def _completion_limit_controls(limit: int) -> Dict[str, int]:
    """Keep Gemini token caps; the CLI has no portable cap enforcement.

    An explicit CLI cap would be an unsupported control (the adapter rejects it
    before model invocation), so the service simply does not claim one in CLI
    mode. This is disclosed in ``provider.controls_note``.
    """
    if PROVIDER is not None and PROVIDER.is_cli:
        return {}
    return {"max_completion_tokens": limit}


def _public_model() -> str:
    """Selected model, or the single observed CLI identity once proven."""
    calls = _PROVIDER_CALLS.get() or []
    observed = {entry.get("observed_model") for entry in calls
                if entry.get("ok") and entry.get("observed_model")}
    if PROVIDER is not None and PROVIDER.is_cli and len(observed) == 1:
        return next(iter(observed))
    return _selected_model()


def _synthesis_label() -> str:
    """Keep the historical Gemini label for the default provider only."""
    if PROVIDER is not None and PROVIDER.is_cli:
        return "OpenCode CLI Synthesis"
    if PROVIDER is not None and PROVIDER.is_aibox:
        return "AIbox HTTP Synthesis"
    return "Gemini Synthesis"


def _record_provider_call(entry: Dict[str, Any]) -> None:
    calls = _PROVIDER_CALLS.get()
    if calls is None or len(calls) >= _MAX_PROVIDER_CALLS:
        return
    safe = {key: value for key, value in entry.items()
            if key not in ("prompt", "messages", "stderr", "stdout")}
    calls.append(safe)


def _provider_block() -> Dict[str, Any]:
    calls = list(_PROVIDER_CALLS.get() or [])
    block: Dict[str, Any] = {
        "calls": calls,
        "observed_model": None,
    }
    if PROVIDER is None:
        block.update({
            "selected": "invalid",
            "requested_model": GEMINI_MODEL,
            "identity_source": "unavailable",
            "config_error": PROVIDER_CONFIG_ERROR,
        })
        return block
    if PROVIDER is not None and PROVIDER.is_aibox:
        observed_aibox = sorted({
            entry.get("observed_model") for entry in calls
            if entry.get("ok") and entry.get("observed_model")
        })
        block.update({
            "selected": PROVIDER_AIBOX,
            "requested_model": PROVIDER.model,
            "observed_model": (observed_aibox[0]
                               if len(observed_aibox) == 1 else None),
            "identity_source": "aibox_http_response",
            "usage_note": ("Provider-reported usage is accumulated when present; "
                           "unknown token values stay null."),
        })
        return block
    if not PROVIDER.is_cli:
        block.update({
            "selected": PROVIDER_GEMINI,
            "requested_model": PROVIDER.model,
            "identity_source": "requested_only",
            "usage_note": ("Provider-reported usage is accumulated when present; "
                           "unknown token values stay null."),
        })
        return block

    observed = sorted({entry.get("observed_model") for entry in calls
                       if entry.get("ok") and entry.get("observed_model")})
    block.update({
        "selected": PROVIDER_OPENCODE_CLI,
        "requested_model": PROVIDER.model,
        "display_name": (MODEL_DISPLAY_NAME
                         if PROVIDER.model == DEFAULT_CLI_MODEL else None),
        "upstream_version_verified": MODEL_UPSTREAM_VERSION_VERIFIED,
        "upstream_note": MODEL_UPSTREAM_NOTE,
        "identity_source": "opencode_session_export",
        "observed_model": observed[0] if len(observed) == 1 else None,
        "identity_conflict": len(observed) > 1,
        "evidence_enabled": PROVIDER.evidence_dir is not None,
        "usage_note": ("Assistant/model service calls only; OpenCode auxiliary "
                       "(title/config/plugin) costs are not measured. Failed "
                       "attempts stay in the call list."),
        "controls_note": ("Per-call temperature/top_p are applied to the "
                          "per-process CLI agent. Portable max-token caps are "
                          "not supported and are not sent in CLI mode."),
        "unsupported_controls": [{
            "name": "max_completion_tokens",
            "reason": ("no portable CLI/provider guarantee; not sent, not "
                       "enforced, and not claimed as a token cap"),
        }],
    })
    return block


def _begin_provider_calls() -> None:
    _PROVIDER_CALLS.set([])


app = FastAPI(title="Travel Lung Tung AI Hub")
_AI_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:8002,http://127.0.0.1:8002,http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if origin.strip() and origin.strip() != "*"
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_AI_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("AI_UNHANDLED_EXCEPTION method=%s type=%s",
                 request.method, type(exc).__name__)
    return JSONResponse(
        status_code=500,
        content={
            "is_success": False,
            "error_type": "internal_server_error",
            "detail": {
                "code": "internal_error",
                "message": "An unexpected internal error occurred.",
            },
        },
    )

# Bounded, session-isolated working memory for the chat surface (OC-009).
WORKING_MEMORY = memory.WorkingMemory()


def _auth_http(exc: AuthError) -> HTTPException:
    """Translate an auth/config failure into a structured HTTP error."""
    return HTTPException(status_code=exc.status_code,
                         detail={"code": exc.code, "message": exc.message})


def _memory_store_or_503():
    store = get_profile_store()
    if store is None:
        raise HTTPException(status_code=503, detail={
            "code": "memory_disabled",
            "message": "Durable profile memory requires MEMORY_DB_PATH.",
        })
    return store


def _store_failure(exc: Exception, code: str = "memory_store_error") -> HTTPException:
    """Sanitized store failure: log the type only, never the raw exception."""
    logger.error("Profile store operation failed: %s", type(exc).__name__)
    return HTTPException(status_code=500, detail={
        "code": code,
        "message": "The memory store could not complete the operation.",
    })


def _parse_expected_version(payload: Dict[str, Any]) -> Optional[int]:
    """Validate ``expected_version`` strictly; reject bool/negative/malformed."""
    if "expected_version" not in payload:
        return None
    value = payload.get("expected_version")
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise HTTPException(status_code=422, detail={
            "code": "invalid_expected_version",
            "message": "expected_version must be a non-negative integer.",
        })
    return value


# Working-memory namespaces must be collision-safe and bounded no matter how
# long or colon-heavy the verified subject / session id is. A naive
# ``f"{owner}:{session_id}"`` aliases distinct tuples: ("a:b", "c") and
# ("a", "b:c") both map to "a:b:c", and the anonymous scope (no bearer) aliases
# any verified subject whose literal value is "anonymous". The key instead
# encodes an unambiguous structured tuple (scope kind, exact subject, exact
# session) as a fixed-length SHA-256 digest of canonical JSON. Colon characters
# and whitespace are preserved verbatim — they are never stripped or banned.
MEMORY_KEY_PREFIX = "wm:"
_MEMORY_SCOPE_USER = "user"
_MEMORY_SCOPE_ANONYMOUS = "anonymous"


def _memory_key(subject: Optional[str], session_id: str) -> str:
    """Build the collision-safe, bounded working-memory namespace key.

    The key is a fixed-length digest of canonical JSON over
    ``{scope, subject, session_id}``. ``scope`` distinguishes the anonymous
    local scope from a verified subject (including a literal ``"anonymous"``),
    and ``subject`` is the exact verified value (never trimmed). Because the
    derived key length is independent of the identifiers, it always satisfies
    ``WorkingMemory``'s key bound; oversized subjects are rejected explicitly at
    the auth boundary (see ``domains.memory_auth``) rather than surfacing an
    uncaught ``ValueError`` here.
    """
    if subject:
        scope = _MEMORY_SCOPE_USER
        owner: Optional[str] = subject
    else:
        scope = _MEMORY_SCOPE_ANONYMOUS
        owner = None
    canonical = json.dumps(
        {"scope": scope, "subject": owner, "session_id": session_id},
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"{MEMORY_KEY_PREFIX}{digest}"

# ---------------------------------------------------------------------------
# Explicit source-snapshot + transport context (CORE-069)
# ---------------------------------------------------------------------------
# The selected tuple is authoritative server-side. The model is told the rules
# but never receives a selector to copy; source_gate injects the exact selection
# into explore_pois and refuses any different one.
TRANSPORT_PROVENANCE_TEXT = {
    "explicit": "explicitly selected in this request",
    "default": "server default because the request did not select a mode",
}


def transport_chat_instructions(mode: str, source: str) -> str:
    """Per-request generation context for the validated travel mode.

    Contains only the two server-validated literals: no selector, guard,
    credential, key or free-form user text.
    """
    provenance = TRANSPORT_PROVENANCE_TEXT.get(source, TRANSPORT_PROVENANCE_TEXT["default"])
    return (
        "\n\n# FIXED TRAVEL MODE (server-enforced)\n"
        f"Travel mode for this request: {mode} ({provenance}).\n"
        "- Use exactly this mode for every route or travel-time suggestion.\n"
        "- Do not change it, and do not infer another mode from the profile, "
        "earlier messages or the user's wording."
    )


SOURCE_CHAT_INSTRUCTIONS = (
    "\n\n# FIXED SOURCE AREA (server-enforced)\n"
    "The user selected one source-snapshot area. The server already performed "
    "the initial source-scoped explore and supplied its qualified POI evidence "
    "in the tool history. The server applies that exact selection to every "
    "explore_pois call and removes any record that does not match it.\n"
    "- Do not ask for, resolve or invent a city/district/street; current "
    "administrative resolution is unavailable in this mode.\n"
    "- Choose relevant POI ids from the supplied evidence. Use get_poi_details "
    "for the ids you select; never use an id that was not returned by a "
    "source-scoped explore.\n"
    "- For a request that needs two or more stops, travel time or a route, call "
    "get_itinerary_route with at least two distinct detail-verified ids in the "
    "requested order and the exact typed travel mode. Do not call it with "
    "unverified, foreign or arbitrary fallback ids merely to make a route "
    "appear green.\n"
    "- Use only POIs returned by explore_pois in this conversation. Never invent "
    "POI ids, names, coordinates, prices, opening hours, availability or "
    "distances. Do not fabricate a pair of stops.\n"
    "- A rejected tool call means the id/area is invalid, not permission to widen "
    "the area.\n"
    "- The source area label is a dataset label, not a present-day boundary. "
    "Keep free-text claims explicitly unverified when hours, prices, current "
    "boundaries or route feasibility were not actually checked; a route result "
    "does not verify those other facts."
)

# One bounded server-authored source query before the first model turn. It uses
# only the exact request tuple and has no current admin filters or inferred
# keyword. ScopeGate still rebuilds/filters the actual MCP arguments/evidence.
# The provider passes the prompt in argv; six qualified records keep the prompt
# comfortably below the Windows process command-line limit while still giving
# the model enough distinct candidates for a two-stop recommendation.
SOURCE_BOOTSTRAP_LIMIT = 6

# Working-memory scope boundary markers. A marker that is absent (first turn,
# restart, another worker) is treated as an unknown previous context: the
# in-memory conversation is reset before the new turn is composed. Durable data,
# the tenant/auth contract and profile storage are never touched.
_SCOPE_MARKERS_MAX = 512
_SCOPE_MARKERS: "OrderedDict[str, str]" = OrderedDict()


def _scope_signature(source_selection: Optional[Dict[str, str]],
                     source_mode: str) -> str:
    """Identity of the explicit *data* context, not the per-request mode.

    Travel mode is a per-request authority injected into every system prompt;
    toggling car/foot in the same selected area keeps the conversation.
    """
    return json.dumps(
        {"source_scope": source_selection, "mode": source_mode},
        sort_keys=True, separators=(",", ":"))


def _apply_scope_boundary(key: str, signature: str, entry: Any) -> bool:
    """Clear the in-memory conversation when the explicit context changed.

    Returns ``True`` when a previous turn was discarded. Must be called while
    holding the lease for ``key`` (``WORKING_MEMORY.clear`` requires it).
    """
    previous = _SCOPE_MARKERS.get(key)
    cleared = False
    if previous != signature:
        cleared = WORKING_MEMORY.clear(entry)
        _SCOPE_MARKERS[key] = signature
    _SCOPE_MARKERS.move_to_end(key)
    while len(_SCOPE_MARKERS) > _SCOPE_MARKERS_MAX:
        _SCOPE_MARKERS.popitem(last=False)
    return cleared


def _forget_scope_marker(key: str) -> None:
    """Drop a marker after an explicit clear so the next turn re-baselines."""
    _SCOPE_MARKERS.pop(key, None)



PROMPT_PATH = Path(__file__).resolve().parent / "prompt.json"
try:
    with open(PROMPT_PATH, "r", encoding="utf-8") as f:
        prompt_data = json.load(f)
        SYSTEM_PROMPT = prompt_data.get("system_prompt", "") + "\n\n" + "\n".join(prompt_data.get("instruction", []))
except FileNotFoundError:
    logger.warning("prompt.json not found. Using default persona.")
    SYSTEM_PROMPT = "You are Travel Lung Tung, an elite AI travel assistant for Vietnam."


def get_gemini_headers():
    return {
        "Authorization": f"Bearer {GEMINI_API_KEY}",
        "Content-Type": "application/json"
    }


# ---------------------------------------------------------------------------
# External collaborator seams (overridable in tests; production uses real I/O).
# ---------------------------------------------------------------------------
@asynccontextmanager
async def open_mcp_session():
    """Yield an initialized MCP client session."""
    async with sse_client(MCP_SERVER_URL) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as mcp_session:
            await mcp_session.initialize()
            yield mcp_session


async def _gemini_chat_completion(payload: Dict[str, Any]) -> Dict[str, Any]:
    """POST a chat-completion payload to Gemini and return the decoded body."""
    async with httpx.AsyncClient(timeout=60.0) as http_client:
        response = await http_client.post(GEMINI_URL, headers=get_gemini_headers(), json=payload)
        response.raise_for_status()
        data = response.json()
    if isinstance(data, dict):
        data.setdefault("_provider", {
            "provider": PROVIDER_GEMINI,
            "ok": True,
            "requested_model": payload.get("model") or GEMINI_MODEL,
            "observed_model": None,
            "identity_source": "requested_only",
            "usage": (data.get("usage") if isinstance(data.get("usage"), dict)
                      else None),
        })
    return data


def _get_cli_provider() -> OpenCodeCliProvider:
    global _CLI_PROVIDER_CACHE
    assert PROVIDER is not None and PROVIDER.is_cli
    key = (PROVIDER, id(_CLI_RUNNER), str(_CLI_CWD))
    if _CLI_PROVIDER_CACHE is None or _CLI_PROVIDER_CACHE[0] != key:
        provider = OpenCodeCliProvider(
            PROVIDER,
            runner=_CLI_RUNNER,
            export_runner=_CLI_RUNNER,
            cwd=_CLI_CWD,
        )
        _CLI_PROVIDER_CACHE = (key, provider)
    return _CLI_PROVIDER_CACHE[1]


async def gemini_chat_completion(payload: Dict[str, Any]) -> Dict[str, Any]:
    """The single model seam: selected provider and OpenAI-compatible body.

    The historical function name is retained so existing monkeypatch call sites
    keep working. Transport failures are observable; there is no silent fallback
    from the selected CLI to Gemini.
    """
    if PROVIDER_CONFIG_ERROR is not None:
        error = ModelUnavailableError(PROVIDER_CONFIG_ERROR["code"],
                                      PROVIDER_CONFIG_ERROR["message"])
        _record_provider_call({"provider": _provider_name(), "ok": False,
                               "error_code": error.code})
        raise error
    assert PROVIDER is not None
    try:
        if PROVIDER.provider == PROVIDER_GEMINI:
            data = await _gemini_chat_completion(payload)
        elif PROVIDER.is_aibox:
            data = await AiboxHttpProvider(PROVIDER).complete(payload)
        else:
            data = await _get_cli_provider().complete(payload)
    except ProviderError as exc:
        _record_provider_call({"provider": _provider_name(), "ok": False,
                               "error_code": exc.code,
                               "retryable": exc.retryable,
                               "attempts": exc.attempts,
                               "failed_attempts": exc.failed_attempts})
        raise
    except Exception:  # noqa: BLE001 - sanitized, no credential body
        _record_provider_call({"provider": _provider_name(), "ok": False,
                               "error_code": "provider_transport_error"})
        raise

    if isinstance(data, dict) and isinstance(data.get("_provider"), dict):
        _record_provider_call(data["_provider"])
    else:
        _record_provider_call({"provider": _provider_name(), "ok": True,
                               "requested_model": payload.get("model")})
    return data


VALID_INTENTS = frozenset({
    "CHITCHAT",
    "TRAVEL",
    "BOOKING",
    "PLAN",
    "MANAGE_SAVED",
    "MANAGE_MEMORY",
})
PROVIDER_TYPESAFE = "typesafe"


def _record_router_attempts(usage: Dict[str, Any],
                            router: Dict[str, Any]) -> None:
    """Record every real Jev HTTP attempt in the shared usage accumulator.

    A validated usage block contributes its actual input/output counts (total
    remains unknown); a failed or usage-less attempt stays an attempted call with
    unknown counts. Configuration/input failures never manufacture a call. Each
    entry is explicitly attributed to TypeSafe with a requested/observed model
    pair; the requested alias is never presented as observed evidence.
    """
    provenance = router.get("provenance")
    attempts = (provenance.get("attempts")
                if isinstance(provenance, dict) else None)
    if not isinstance(attempts, list):
        return

    def identity(value: Any) -> Optional[str]:
        if not isinstance(value, str) or not value or len(value) > 128:
            return None
        if value != value.strip() or any(ord(char) < 0x20 for char in value):
            return None
        return value

    default_requested = identity(router.get("requested_model"))
    for attempt in attempts:
        if not isinstance(attempt, dict):
            continue
        attempt_usage = attempt.get("usage")
        if attempt.get("usage_known") is True and isinstance(attempt_usage, dict):
            chat_agent.record_usage(usage, {"usage": {
                "input_tokens": attempt_usage.get("input_tokens"),
                "output_tokens": attempt_usage.get("output_tokens"),
            }})
        else:
            chat_agent.record_failed_call(usage)
        entry = usage["calls"][-1]
        entry.update({
            "provider": PROVIDER_TYPESAFE,
            "operation": "intent_routing",
            "requested_model": (identity(attempt.get("requested_model"))
                                or default_requested),
            "observed_model": identity(attempt.get("observed_model")),
        })


async def route_intent(user_message: str,
                       usage: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Delegate intent classification to TypeSafe Jev only.

    No provider/model fallback exists. The returned intent is ``None`` unless a
    validated decision is executable; category/uncertainty/failure states stay
    explicit for the caller.
    """
    if usage is None:
        usage = chat_agent.new_usage()
    router = await jev_intent.classify_intent(user_message)
    _record_router_attempts(usage, router)
    return router


async def analyze_intent(user_message: str) -> Optional[str]:
    """Return only the executable intent, or ``None`` when unresolved."""
    return (await route_intent(user_message))["intent"]


def _finite_number(value: Any, minimum: Optional[float] = None,
                   maximum: Optional[float] = None) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    parsed = float(value)
    if not math.isfinite(parsed):
        return None
    if minimum is not None and parsed < minimum:
        return None
    if maximum is not None and parsed > maximum:
        return None
    return parsed


def _safe_text(value: Any, *, maximum: int = 64) -> Optional[str]:
    if not isinstance(value, str) or not value or len(value) > maximum:
        return None
    if value != value.strip() or any(ord(char) < 0x20 for char in value):
        return None
    return value


def _safe_probabilities(value: Any) -> Optional[Dict[str, float]]:
    if not isinstance(value, dict):
        return None
    if set(value.keys()) == set(jev_intent.CHOICES):
        labels = jev_intent.CHOICES
    elif set(value.keys()) == set(jev_intent.CHOICES_V1_1):
        labels = jev_intent.CHOICES_V1_1
    else:
        return None
    probabilities: Dict[str, float] = {}
    for label in labels:
        parsed = _finite_number(value.get(label), 0.0, 1.0)
        if parsed is None:
            return None
        probabilities[label] = parsed
    if abs(sum(probabilities.values()) - 1.0) > 1e-6:
        return None
    return probabilities


def _safe_count(value: Any) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _safe_attempts(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    safe: List[Dict[str, Any]] = []
    for item in value[:4]:
        if not isinstance(item, dict):
            continue
        status = item.get("http_status")
        usage = item.get("usage")
        safe.append({
            "attempt": _safe_count(item.get("attempt")),
            "provider": PROVIDER_TYPESAFE,
            "operation": "intent_routing",
            "requested_model": _safe_text(item.get("requested_model"),
                                          maximum=128),
            "observed_model": _safe_text(item.get("observed_model"),
                                         maximum=128),
            "model": _safe_text(item.get("model"), maximum=128),
            "outcome": (item.get("outcome") if item.get("outcome") in
                        ("success", "error") else "error"),
            "error_code": _safe_text(item.get("error_code")),
            "retryable": item.get("retryable") is True,
            "http_status": (status if isinstance(status, int)
                            and not isinstance(status, bool)
                            and 100 <= status <= 599 else None),
            "latency_ms": _finite_number(item.get("latency_ms"), 0.0),
            "usage_known": item.get("usage_known") is True,
            "usage": ({
                "input_tokens": _safe_count(usage.get("input_tokens")),
                "output_tokens": _safe_count(usage.get("output_tokens")),
                "total_tokens": _safe_count(usage.get("total_tokens")),
            } if isinstance(usage, dict) else None),
            "cleanup_complete": (item.get("cleanup_complete")
                                 if isinstance(item.get("cleanup_complete"),
                                               bool) else None),
            "cleanup_error": _safe_text(item.get("cleanup_error")),
        })
    return safe


def _router_public(router: Any) -> Dict[str, Any]:
    """Additive, safe router metadata; never echoes raw payloads/headers."""
    if not isinstance(router, dict):
        router = {}
    provenance = router.get("provenance")
    source: Dict[str, Any] = dict(router)
    if isinstance(provenance, dict):
        source.update(provenance)

    status = source.get("status")
    if status not in ("ok", "ambiguous", "unavailable", "malformed",
                      "unconfigured"):
        status = "unavailable"
    return {
        "status": status,
        "fallback": False,
        "provider": PROVIDER_TYPESAFE,
        "operation": "intent_routing",
        "configured": source.get("configured") is True,
        "requested_model": _safe_text(source.get("requested_model"),
                                      maximum=128),
        "observed_model": _safe_text(source.get("observed_model"),
                                     maximum=128),
        "confidence": _finite_number(source.get("confidence"), 0.0, 1.0),
        "probabilities": _safe_probabilities(source.get("probabilities")),
        "policy_version": _safe_text(source.get("policy_version")),
        "threshold": _finite_number(source.get("threshold"), 0.0, 1.0),
        "latency_ms": _finite_number(source.get("latency_ms"), 0.0),
        "attempt_count": _safe_count(source.get("attempt_count")),
        "attempts": _safe_attempts(source.get("attempts")),
        "error_code": _safe_text(source.get("error_code")),
    }


_TOKEN_FIELDS = ("input_tokens", "output_tokens", "total_tokens")


def _finalize_usage(usage: Dict[str, Any]) -> Dict[str, Any]:
    """Never present a partial aggregate as complete flow usage.

    If any attempted call lacks a component, the aggregate field becomes
    ``None``; known subtotals and per-component completeness flags stay
    available separately. A total is never inferred from input+output.
    """
    calls = usage.get("calls")
    calls = calls if isinstance(calls, list) else []
    completeness: Dict[str, bool] = {}
    subtotals: Dict[str, Optional[int]] = {}
    for field in _TOKEN_FIELDS:
        complete = bool(calls)
        subtotal = 0
        for call in calls:
            if not isinstance(call, dict):
                complete = False
                continue
            value = call.get(field)
            if (isinstance(value, bool) or not isinstance(value, int)
                    or value < 0):
                complete = False
                continue
            subtotal += value
        completeness[field] = complete
        subtotals[field] = subtotal if calls and any(
            isinstance(call, dict) and isinstance(call.get(field), int)
            and not isinstance(call.get(field), bool)
            for call in calls) else None
        usage[field] = subtotal if complete else None
    usage["token_completeness"] = completeness
    usage["known_subtotals"] = subtotals
    return usage


def _tool_specs(mcp_tools: Any) -> Tuple[List[Dict[str, Any]], Set[str]]:
    """Build OpenAI-style function specs + the set of executable tool names."""
    specs: List[Dict[str, Any]] = []
    names: Set[str] = set()
    tools = getattr(mcp_tools, "tools", None)
    if not isinstance(tools, list):
        return specs, names
    for tool in tools:
        name = grounding.nonblank_str(getattr(tool, "name", None))
        if name is None or name in names:
            continue
        names.add(name)
        specs.append({
            "type": "function",
            "function": {
                "name": name,
                "description": getattr(tool, "description", "") or "",
                "parameters": getattr(tool, "inputSchema", None) or {},
            },
        })
    return specs, names


async def _run_travel_turn(messages: List[Dict[str, Any]],
                           usage: Dict[str, Any],
                           *, source_selection: Optional[Dict[str, str]] = None,
                           transport_mode: str = "car") -> Dict[str, Any]:
    """Run the bounded ReAct loop against the real MCP seam and model seam.

    The explicit request context is enforced by ``source_gate.ScopeGate`` around
    the actual MCP call: arguments are rebuilt server-side and returned evidence
    is re-qualified before the model, trace or memory can observe it.
    """
    gate = source_gate.ScopeGate(source_selection=source_selection,
                                 transport_mode=transport_mode)
    source_bootstrap_requests: List[Dict[str, Any]] = []
    if gate.source_mode:
        source_bootstrap_requests.append({
            "name": source_gate.EXPLORE_TOOL,
            "arguments": {
                "source_scope": dict(gate.selection),
                "limit": SOURCE_BOOTSTRAP_LIMIT,
            },
        })
    try:
        async with open_mcp_session() as mcp_session:
            mcp_tools = await mcp_session.list_tools()
            tool_specs, known_names = _tool_specs(mcp_tools)

            async def call_model(msgs, tools):
                payload = {
                    "model": _selected_model(),
                    "messages": msgs,
                    "tools": tools,
                    "temperature": 0.3,
                }
                return await gemini_chat_completion(payload)

            async def call_tool(name, args):
                decision = gate.prepare(name, args)
                if not decision.ok:
                    return gate.rejection_result(decision)
                raw = await mcp_session.call_tool(name,
                                                  arguments=decision.args or {})
                return gate.filter_result(name, decision.args or {}, raw)

            result = await chat_agent.run_agent_loop(
                messages=messages,
                tool_specs=tool_specs,
                known_tool_names=known_names,
                call_model=call_model,
                call_tool=call_tool,
                usage=usage,
                initial_tool_requests=source_bootstrap_requests,
            )
            if isinstance(result, dict):
                result["scope_gate"] = gate.as_meta()
                if source_bootstrap_requests:
                    result["bootstrap"] = {
                        "origin": "server_bootstrap",
                        "requested_tool_calls": len(source_bootstrap_requests),
                        "evidence_count": len(
                            result.get("source_evidence_ids") or []),
                    }
            return result
    except Exception as e:  # noqa: BLE001 - never leak a traceback to the caller
        logger.error("Agent hub failure: %s", type(e).__name__)
        return {
            "status": chat_agent.STATUS_FAILED,
            "reply": chat_agent.MODEL_UNAVAILABLE_MESSAGE,
            "tool_chain": [],
            "turn_messages": [],
            "source_evidence_ids": [],
            "grounding_status": chat_agent.GROUNDING_INSUFFICIENT,
            "loop_limit": False,
            "scope_gate": gate.as_meta(),
            "error": {"code": "agent_unavailable",
                      "message": "The agent tool runtime is unavailable."},
        }


# ---------------------------------------------------------------------------
# Itinerary generation (grounded)
# ---------------------------------------------------------------------------
def _append_step(tool_chain: List[Dict[str, Any]], tool: str,
                 args: Any = None) -> Dict[str, Any]:
    entry: Dict[str, Any] = {"step": len(tool_chain) + 1, "tool": tool}
    if args is not None:
        entry["args"] = args
    tool_chain.append(entry)
    return entry


async def _call_tool(session: Any, tool: str, args: Dict[str, Any],
                     tool_chain: List[Dict[str, Any]],
                     label: str = None) -> grounding.ToolOutcome:
    entry = _append_step(tool_chain, label or tool, args)
    try:
        raw = await session.call_tool(tool, arguments=args)
    except Exception as e:
        entry["status"] = "failed"
        entry["summary"] = f"transport error: {type(e).__name__}"
        return grounding.ToolOutcome(
            False, code=grounding.TOOL_PROTOCOL_ERROR, detail="tool transport error")

    outcome = grounding.parse_mcp_tool_result(raw)
    entry["status"] = "success" if outcome.ok else "failed"
    if not outcome.ok:
        entry["summary"] = outcome.code
    return outcome


def _structured_error(code: str, message: str, tool_chain: List[Dict[str, Any]],
                      *, details: Any = None, grounding_meta: Any = None,
                      planning: Any = None, status: str = "failed") -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "status": status,
        "error": {"code": code, "message": message},
        "tool_chain": tool_chain,
    }
    if details is not None:
        payload["error"]["details"] = details
    if grounding_meta is not None:
        payload["grounding"] = grounding_meta
    if planning is not None:
        payload["planning"] = planning
    return payload


async def _resolve_area(session: Any, keyword: str, expected_type: str,
                        tool_chain: List[Dict[str, Any]],
                        label: str) -> grounding.ToolOutcome:
    outcome = await _call_tool(session, "resolve_geographic_id", {"keyword": keyword},
                               tool_chain, label)
    if not outcome.ok:
        return outcome
    selected = grounding.select_unique_area((outcome.data or {}).get("matches"),
                                            keyword, expected_type)
    entry = tool_chain[-1]
    if selected.ok:
        entry["summary"] = f"resolved to {selected.data['id']}"
    else:
        entry["status"] = "failed"
        entry["summary"] = selected.code
        entry["details"] = selected.detail
    return selected


def _build_synthesis_prompt(request: ItineraryRequest,
                            poi_context: str,
                            source_scope_summary: Optional[Dict[str, Any]] = None
                            ) -> str:
    transport_mode, transport_source = planning_adapter.request_transport_mode(
        request)
    transport_mode = transport_mode or "car"
    transport_provenance = TRANSPORT_PROVENANCE_TEXT.get(
        transport_source, TRANSPORT_PROVENANCE_TEXT["default"])
    if source_scope_summary is None:
        location_block = f"""
    - City: {request.current_city}
    - Target Area: {request.target_district}"""
        places_title = "AVAILABLE PLACES (verified evidence; you MUST only use these IDs)"
    else:
        location_block = f"""
    - Source snapshot area: {source_scope_summary.get('source_area_label')}
    - Current administrative boundary: UNVERIFIED
      ({source_scope_summary.get('current_boundary_uncertainty')})
    - The source area is fixed by the request. Do not change, widen or infer a
      different area, and do not invent a current city/district."""
        places_title = "AVAILABLE PLACES (source evidence; you MUST only use these IDs)"
    return f"""

    You are the 'Travel Lung Tung' itinerary selection engine.

    Select a {request.duration_days}-day itinerary from the AVAILABLE PLACES below.

    # USER PROFILE & REQUIREMENTS{location_block}
    - Travel Style: {request.travel_type}
    - Group Size: {request.num_travelers} pax
    - Budget: {request.budget_range}
    - Start Date: {request.start_date}
    - Travel mode: {transport_mode} ({transport_provenance}); use exactly this
      mode and do not infer another one from the profile or description.
    - Special Requests: "{request.user_description}"

    # {places_title}
    ```json
    {poi_context}
    ```

    # OUTPUT INSTRUCTIONS
    Output ONLY a valid JSON object (no markdown fences). Do not invent POIs,
    names, coordinates, opening hours, prices or addresses: those are rebuilt by
    the caller from the verified evidence and any values you supply are ignored.

    Schema:
    {{
      "start_poi_id": "string",
      "end_poi_id": "string",
      "total_estimated_budget": float,
      "stops": [
        {{
          "date": "YYYY-MM-DD",
          "visit_time": "ISO 8601 with offset, e.g. 2026-01-01T09:00:00+07:00",
          "end_time": "ISO 8601 with offset",
          "description": "short free text (will be replaced by neutral text)",
          "budget": float,
          "poi": {{ "id": "one of the AVAILABLE PLACES ids" }}
        }}
      ]
    }}

    Rules:
    1. Use only ids present in AVAILABLE PLACES.
    2. start_poi_id and end_poi_id must be the first and last stop ids.
    3. Timestamps must be timezone-aware ISO 8601, in chronological order with
       no overlaps, inside the trip starting {request.start_date} for
       {request.duration_days} day(s) (destination timezone +07:00).
    4. Budgets are estimates only; total_estimated_budget must equal the sum of
       the stop budgets.
    5. Do NOT output "id" or "uid"; the server assigns them.
    6. If the user explicitly asks for multiple stops or a route among places,
       include multiple distinct suitable POIs when the candidate evidence
       supports them; do not collapse the request to one stop. A single-POI
       request may remain one stop. Never invent an arbitrary pair merely to
       satisfy a stop count.
    """


def _extract_model_content(response_data: Any) -> Tuple[Optional[str], Optional[str]]:
    """Extract assistant text from an OpenAI-compatible chat response.

    Returns ``(content, error)``; non-dict bodies, missing/empty ``choices``,
    non-object choices, missing ``message`` and non-string/blank content are all
    treated as invalid so the caller can fail closed.
    """
    if not isinstance(response_data, dict):
        return None, "model response is not an object"
    choices = response_data.get("choices")
    if not isinstance(choices, list) or not choices:
        return None, "model response has no choices"
    first = choices[0]
    if not isinstance(first, dict):
        return None, "model choice is not an object"
    message = first.get("message")
    if not isinstance(message, dict):
        return None, "model message is missing"
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        return None, "model content is missing or not a string"
    return content, None


ITINERARY_MEMORY_ASSISTANT_MAX_CHARS = 2400


def _synthesis_messages(mega_prompt: str,
                        memory_context: Optional[Dict[str, Any]] = None
                        ) -> List[Dict[str, Any]]:
    """Build the synthesis call messages for the HTTP memory bridge.

    ``memory_context`` is private server-side state created by the HTTP
    handler; it is never a public request field. ``None`` keeps the legacy
    direct-helper call shape (one user message) used by existing Python
    callers. When a context is supplied, every HTTP condition receives the
    same fixed base system/current-request text; only stored history differs.

    Stored turns are replayed through the existing ``memory.compose`` window,
    but only textual user/assistant messages are forwarded. Raw tool results,
    tool-call arguments, provider receipts and arbitrary configuration are
    never serialized into the synthesis call.
    """
    if memory_context is None:
        return [{"role": "user", "content": mega_prompt}]

    entry = memory_context.get("entry")
    if memory_context.get("enabled") and entry is not None:
        composed = WORKING_MEMORY.compose(entry, SYSTEM_PROMPT, mega_prompt)
        system_content = composed[0].get("content") if composed else ""
        if not isinstance(system_content, str):
            system_content = ""
        history: List[Dict[str, Any]] = []
        for message in composed[1:-1]:
            if not isinstance(message, dict):
                continue
            role = message.get("role")
            content = message.get("content")
            if role not in ("user", "assistant"):
                continue  # never replay raw tool payloads as current evidence
            if not isinstance(content, str) or not content.strip():
                continue
            history.append({"role": role, "content": content})
        # ``compose`` clips its current-message copy to the stored-memory
        # window. The synthesis prompt is not stored history: it must reach the
        # model in full, so append the original ``mega_prompt`` while keeping
        # the composed system/summary/history exactly as filtered above.
        base = f"{system_content}\n\n{mega_prompt}" if system_content else mega_prompt
        history.append({"role": "user", "content": base})
        return history

    # memory_enabled=false: no store/lease/history/profile, but still the same
    # fixed base persona + current synthesis request (never a different persona).
    return [{"role": "user", "content": f"{SYSTEM_PROMPT}\n\n{mega_prompt}"}]


def _itinerary_memory_assistant_text(result: Any) -> Optional[str]:
    """Bounded public assistant representation for a delivered typed plan.

    Only a genuinely grounded, delivered result is committable. The text is
    rebuilt from the server-reconstructed public reply and the documented
    planner status; raw model prose, errors, provider receipts and config are
    never stored.
    """
    if not isinstance(result, dict) or result.get("status") != "success":
        return None
    if result.get("error"):
        return None
    grounding_meta = result.get("grounding")
    planning = result.get("planning")
    reply = result.get("reply")
    if not isinstance(grounding_meta, dict) \
            or grounding_meta.get("status") != "grounded":
        return None
    if not isinstance(planning, dict) \
            or not isinstance(planning.get("repaired_schedule"), dict):
        return None
    if not isinstance(reply, dict):
        return None
    stops = reply.get("stops")
    if not isinstance(stops, list) or not stops:
        return None
    itinerary_id = grounding.nonblank_str(reply.get("id"))
    if itinerary_id is None:
        return None

    lines = ["Typed grounded itinerary delivered (public server-reconstructed result).",
             f"id: {itinerary_id}"]
    for field in ("start_poi_id", "end_poi_id"):
        value = grounding.nonblank_str(reply.get(field))
        if value is not None:
            lines.append(f"{field}: {value}")
    total = reply.get("total_estimated_budget")
    if isinstance(total, (int, float)) and not isinstance(total, bool) \
            and math.isfinite(float(total)):
        lines.append(f"total_estimated_budget: {format(float(total), 'f')}")
    else:
        lines.append("total_estimated_budget: null (unknown)")
    lines.append("budget_is_estimate: true")
    validator_status = grounding.nonblank_str(planning.get("validator_status"))
    if validator_status is not None:
        lines.append(f"validator_status: {validator_status}")
    lines.append("stops:")
    for stop in stops:
        if not isinstance(stop, dict):
            continue
        poi = stop.get("poi")
        poi_id = (grounding.nonblank_str(poi.get("id"))
                  if isinstance(poi, dict) else None)
        if poi_id is None:
            continue
        date = grounding.nonblank_str(stop.get("date")) or "unknown-date"
        visit = grounding.nonblank_str(stop.get("visit_time")) or "unknown-time"
        end = grounding.nonblank_str(stop.get("end_time")) or "unknown-time"
        name = (grounding.nonblank_str(poi.get("name"))
                if isinstance(poi, dict) else None)
        label = f"{poi_id} ({name})" if name else poi_id
        lines.append(f"- {date} {visit}..{end} {label}")

    text = "\n".join(lines)
    if len(text) > ITINERARY_MEMORY_ASSISTANT_MAX_CHARS:
        text = (text[:ITINERARY_MEMORY_ASSISTANT_MAX_CHARS].rstrip()
                + "\n[truncated]")
    return text


def _accepts_keyword_argument(func: Any, name: str) -> bool:
    """Whether ``func`` accepts ``name`` (used only for legacy test seams)."""
    try:
        parameters = inspect.signature(func).parameters
    except (TypeError, ValueError):
        return False
    if name in parameters:
        return True
    return any(parameter.kind is inspect.Parameter.VAR_KEYWORD
               for parameter in parameters.values())


async def _run_itinerary(request: ItineraryRequest,
                         tool_chain: List[Dict[str, Any]],
                         *,
                         uid: Optional[str] = None,
                         uid_source: str = "anonymous",
                         profile_block: Optional[str] = None,
                         memory_context: Optional[Dict[str, Any]] = None
                         ) -> Dict[str, Any]:
    mode = grounding.request_scope_mode(request)
    source_selection: Optional[Dict[str, str]] = None
    unused_request_fields: List[str] = []
    if mode == grounding.SOURCE_SCOPE_CONTRACT:
        parsed_selection = grounding.parse_source_selection(
            getattr(request, "source_scope", None))
        if not parsed_selection.ok:
            return _structured_error(
                grounding.INVALID_REQUEST,
                "The explicit source snapshot selection is invalid.",
                tool_chain, details=parsed_selection.detail,
                grounding_meta={"scope_mode": mode})
        source_selection = parsed_selection.data
        unused_request_fields = ["current_city"]
        if grounding.nonblank_str(getattr(request, "target_district", None)) is not None:
            unused_request_fields.append("target_district")

    scope_evidence: Dict[str, Any] = (
        {"mode": mode,
         "source_scope": dict(source_selection),
         "unused_request_fields": list(unused_request_fields)}
        if source_selection is not None else {})

    async with open_mcp_session() as session:
        district: Optional[Dict[str, Any]] = None
        city: Optional[Dict[str, Any]] = None

        if mode == grounding.SCOPE_MODE_CURRENT:
            # --- STEP 1: RESOLVE CITY AND DISTRICT (both evidence, unique exact) ---
            district_res = await _resolve_area(
                session, request.target_district, "District", tool_chain,
                f"resolve_geographic_id (district: {request.target_district})")
            if not district_res.ok:
                return _structured_error(district_res.code,
                                          "Could not uniquely resolve the target district.",
                                          tool_chain, details=district_res.detail)

            city_res = await _resolve_area(
                session, request.current_city, "City", tool_chain,
                f"resolve_geographic_id (city: {request.current_city})")
            if not city_res.ok:
                return _structured_error(city_res.code,
                                          "Could not uniquely resolve the requested city.",
                                          tool_chain, details=city_res.detail)

            district = district_res.data
            city = city_res.data
            scope_evidence = {"city": city, "district": district}

            # Reject a district whose resolver-provided parent city conflicts with
            # the requested city.
            parent_city_id = grounding.nonblank_str(district.get("parent_city_id"))
            parent_city_name = grounding.nonblank_str(district.get("parent_city_name"))
            if parent_city_id is not None and parent_city_id != city["id"]:
                return _structured_error(
                    grounding.SCOPE_CONFLICT,
                    "The resolved district belongs to a different city than requested.",
                    tool_chain, grounding_meta={"scope_evidence": scope_evidence})
            if parent_city_name is not None \
                    and grounding.normalize_text(parent_city_name) != grounding.normalize_text(city.get("name")):
                return _structured_error(
                    grounding.SCOPE_CONFLICT,
                    "The resolved district parent city does not match the requested city.",
                    tool_chain, grounding_meta={"scope_evidence": scope_evidence})
        # Source mode deliberately makes no resolver call: the explicit
        # snapshot/area selection is the only geographic criterion.

        # --- STEP 2: DISCOVER CATEGORIES FROM THE ACTUAL TOOL ---
        cat_outcome = await _call_tool(session, "get_available_categories", {},
                                       tool_chain, "get_available_categories")
        categories = grounding.parse_categories(cat_outcome)
        if categories.ok:
            tool_chain[-1]["summary"] = f"discovered {len(categories.data)} categories"
        else:
            tool_chain[-1]["status"] = "failed"
            tool_chain[-1]["summary"] = categories.code
        if not categories.ok and mode == grounding.SCOPE_MODE_CURRENT:
            return _structured_error(
                grounding.INSUFFICIENT_DATA,
                "No usable POI categories were returned; cannot ground candidates.",
                tool_chain, details=categories.code,
                grounding_meta={"scope_evidence": scope_evidence})
        # Source mode continues with the unfiltered floor query below even when
        # the global category catalog is empty or does not overlap the snapshot.
        category_list = categories.data if categories.ok else []

        # --- STEP 3: SCATTER-GATHER CANDIDATES (district + city evidence) ---
        groups: List[Tuple[Optional[str], List[Dict[str, Any]]]] = []
        explore_requests: List[
            Tuple[Optional[str], Dict[str, Any], str]] = []
        if mode == grounding.SOURCE_SCOPE_CONTRACT:
            # One unfiltered floor query makes the source branch independent of
            # an empty/non-overlapping global category catalog. It is never given
            # a fabricated category id.
            explore_requests.append((
                None,
                {"source_scope": dict(source_selection),
                 "limit": grounding.MAX_CANDIDATES},
                "explore_pois (source snapshot area floor)",
            ))
            for cat in category_list:
                explore_requests.append((
                    cat["id"],
                    {"source_scope": dict(source_selection),
                     "category_id": cat["id"], "limit": 6},
                    f"explore_pois ({cat['name'] or cat['id']})",
                ))
        else:
            for cat in category_list:
                explore_requests.append((
                    cat["id"],
                    {"city_id": city["id"], "district_id": district["id"],
                     "category_id": cat["id"], "limit": 6},
                    f"explore_pois ({cat['name'] or cat['id']})",
                ))

        explore_successes = 0
        for category_id, args, label in explore_requests:
            explore_out = await _call_tool(session, "explore_pois", args, tool_chain, label)
            parsed = grounding.parse_explore(explore_out)
            if parsed.ok:
                explore_successes += 1
                tool_chain[-1]["summary"] = f"found {len(parsed.data)} candidates"
                groups.append((category_id, parsed.data))
            else:
                tool_chain[-1]["status"] = "failed"
                tool_chain[-1]["summary"] = parsed.code

        candidate_ids = grounding.collect_candidate_ids([g for _, g in groups])
        # Real category id per candidate, taken from the category it was
        # discovered under (never invented; floor-only candidates get no
        # synthetic category id).
        candidate_category_ids: Dict[str, List[str]] = {}
        for category_id, group in groups:
            if category_id is None:
                continue
            for poi in group:
                pid = grounding.nonblank_str(poi.get("id"))
                if pid is None:
                    continue
                existing = candidate_category_ids.setdefault(pid, [])
                if category_id not in existing:
                    existing.append(category_id)
        if not candidate_ids:
            error_meta: Dict[str, Any] = {"scope_evidence": scope_evidence}
            if source_selection is not None:
                error_meta.update({
                    "scope_mode": mode,
                    "scope_contract": grounding.SOURCE_SCOPE_CONTRACT,
                    "source_scope": dict(source_selection),
                    "explore_success_count": explore_successes,
                })
            if source_selection is not None and explore_successes == 0:
                return _structured_error(
                    grounding.CANDIDATE_RETRIEVAL_FAILED,
                    "Source candidate retrieval failed; no explore response was "
                    "usable. This is a retrieval/serialization failure, not a "
                    "source-qualification result.",
                    tool_chain, grounding_meta=error_meta)
            return _structured_error(
                grounding.INSUFFICIENT_DATA,
                "No POI candidates were retrieved for the requested area.",
                tool_chain, grounding_meta=error_meta)

        # --- STEP 4: ENRICH CANDIDATES (parallel, order-observable) ---
        entries = [
            _append_step(tool_chain, "get_poi_details", {"poi_id": pid})
            for pid in candidate_ids
        ]

        async def _enrich(index: int, poi_id: str) -> Tuple[str, grounding.ToolOutcome]:
            try:
                raw = await session.call_tool("get_poi_details", arguments={"poi_id": poi_id})
            except Exception as e:
                entries[index]["status"] = "failed"
                entries[index]["summary"] = f"transport error: {type(e).__name__}"
                return poi_id, grounding.ToolOutcome(
                    False, code=grounding.TOOL_PROTOCOL_ERROR, detail="tool transport error")
            outcome = grounding.parse_mcp_tool_result(raw)
            if outcome.ok:
                outcome = grounding.parse_enrichment(outcome, poi_id)
            entries[index]["status"] = "success" if outcome.ok else "failed"
            entries[index]["summary"] = "enriched" if outcome.ok else outcome.code
            return poi_id, outcome

        raw_outcomes = await asyncio.gather(
            *[_enrich(i, pid) for i, pid in enumerate(candidate_ids)])
        outcomes = list(raw_outcomes)

        enriched = grounding.build_enriched_index(outcomes)
        if not enriched:
            return _structured_error(
                grounding.INSUFFICIENT_DATA,
                "All candidate enrichments failed; no verified POI evidence.",
                tool_chain, grounding_meta={"scope_evidence": scope_evidence})

        # --- STEP 5: SCOPE EVIDENCE (structured contract only; fail closed) ---
        source_scope_summary: Optional[Dict[str, Any]] = None
        if source_selection is not None:
            verified = {}
            excluded_conflicts = []
            excluded_unknown = []
            for pid in sorted(enriched):
                status = grounding.poi_source_scope_status(
                    enriched[pid], source_selection)
                if status == "qualified":
                    verified[pid] = enriched[pid]
                elif status == "conflict":
                    excluded_conflicts.append(pid)
                else:
                    excluded_unknown.append(pid)

            source_status_meta: Dict[str, Any] = {
                "scope_mode": mode,
                "scope_contract": grounding.SOURCE_SCOPE_CONTRACT,
                "source_scope": dict(source_selection),
                "excluded_source_conflicts": excluded_conflicts,
                "excluded_source_unknown": excluded_unknown,
                "excluded_source_conflict_count": len(excluded_conflicts),
                "excluded_source_unknown_count": len(excluded_unknown),
            }
            if not verified:
                if excluded_conflicts and not excluded_unknown:
                    code = grounding.SCOPE_CONFLICT
                    message = ("All enriched POIs contradict the explicitly "
                               "selected source snapshot area.")
                else:
                    code = grounding.SOURCE_SCOPE_UNVERIFIED
                    message = ("No POI could be qualified against the explicitly "
                               "selected source snapshot area; no usable compact "
                               "source_context was returned.")
                return _structured_error(
                    code, message, tool_chain,
                    grounding_meta={
                        **source_status_meta,
                        "scope_evidence": scope_evidence,
                        "upstream_dependency": (
                            "get_poi_details must expose a valid source_context "
                            "with the exact source_area_scope_v1 claim; until then "
                            "source-mode plans fail closed."),
                    })

            enriched = verified
            scope_verification = "qualified_source_snapshot_area"
            first_context = next(
                (ev.get("source_context") for ev in enriched.values()
                 if isinstance(ev.get("source_context"), dict)), {})
            source_scope_summary = {
                "source_area_label": grounding.nonblank_str(
                    first_context.get("source_area_label")),
                "current_boundary_uncertainty": grounding.nonblank_str(
                    first_context.get("current_boundary_uncertainty")),
            }
            grounding_meta = {
                "status": "grounded",
                "scope_mode": mode,
                "scope_verification": scope_verification,
                "scope_contract": grounding.SOURCE_SCOPE_CONTRACT,
                "source_scope": dict(source_selection),
                "source_area_label": source_scope_summary["source_area_label"],
                "current_boundary_uncertainty": source_scope_summary[
                    "current_boundary_uncertainty"],
                "scope_evidence": scope_evidence,
                "unused_request_fields": list(unused_request_fields),
                "excluded_source_conflicts": excluded_conflicts,
                "excluded_source_unknown": excluded_unknown,
                "excluded_source_conflict_count": len(excluded_conflicts),
                "excluded_source_unknown_count": len(excluded_unknown),
                "enriched_count": len(enriched),
                "selected_poi_ids": list(enriched.keys()),
                "budget_is_estimate": True,
                "description_source": "neutral_selection_text",
                "route_feasibility": "unverified",
                "opening_hours_feasibility": "unverified",
                "id_source": "server",
                "uid_source": uid_source,
                "profile_injected": bool(profile_block),
                "upstream_dependency": (
                    "Source qualification requires get_poi_details to expose a "
                    "valid compact source_context; it is not current "
                    "administrative containment."),
            }
        else:
            verified = {}
            excluded_conflicts = []
            excluded_unknown = []
            for pid in sorted(enriched):
                status = grounding.poi_scope_status(enriched[pid], district, city)
                if status == "verified":
                    verified[pid] = enriched[pid]
                elif status == "conflict":
                    excluded_conflicts.append(pid)
                else:
                    excluded_unknown.append(pid)

            if not verified:
                # Only a fully verified subset may reach synthesis. Unknown parent
                # context is not silently treated as same-city.
                if excluded_conflicts and not excluded_unknown:
                    code = grounding.SCOPE_CONFLICT
                    message = "All enriched POIs contradict the requested geographic scope."
                else:
                    code = grounding.SCOPE_UNVERIFIED
                    message = ("No POI could be verified against a structured "
                               "administrative_context; the enrichment payload has no "
                               "usable parent context.")
                return _structured_error(
                    code, message, tool_chain,
                    grounding_meta={
                        "scope_evidence": scope_evidence,
                        "scope_contract": "administrative_context",
                        "excluded_scope_conflicts": excluded_conflicts,
                        "excluded_scope_unknown": excluded_unknown,
                        "upstream_dependency": (
                            "get_poi_details must expose administrative_context "
                            "({city_id, district_id, city_name, district_name}); until "
                            "then live plans fail closed."),
                    })

            enriched = verified
            scope_verification = "verified"

            grounding_meta = {
                "status": "grounded",
                "scope_verification": scope_verification,
                "scope_contract": "administrative_context",
                "scope_evidence": scope_evidence,
                "excluded_scope_conflicts": excluded_conflicts,
                "excluded_scope_unknown": excluded_unknown,
                "enriched_count": len(enriched),
                "selected_poi_ids": list(enriched.keys()),
                "budget_is_estimate": True,
                "description_source": "neutral_selection_text",
                "route_feasibility": "unverified",
                "opening_hours_feasibility": "unverified",
                "id_source": "server",
                "uid_source": uid_source,
                "profile_injected": bool(profile_block),
                "upstream_dependency": (
                    "Scope verification requires get_poi_details to expose "
                    "administrative_context; until then live plans fail closed."),
            }

        # --- STEP 6: MODEL SYNTHESIS (selected provider; evidence unchanged) ---
        if source_selection is not None:
            # Compact source facts only: no stored provenance, audit pointer or
            # current administrative ids reach the model.
            poi_context = json.dumps(
                [grounding.compact_source_prompt_fact(enriched[pid])
                 for pid in sorted(enriched)], indent=2)
        else:
            poi_context = json.dumps([enriched[pid] for pid in sorted(enriched)], indent=2)
        mega_prompt = _build_synthesis_prompt(
            request, poi_context, source_scope_summary=source_scope_summary)
        if profile_block:
            # Bounded, explicitly secondary to the current request.
            mega_prompt += "\n\n" + profile_block[:memory.MAX_PROFILE_PROMPT_CHARS]
        payload = {
            "model": _selected_model(),
            "messages": _synthesis_messages(mega_prompt, memory_context),
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        _append_step(tool_chain, _synthesis_label(), {
            "model": _selected_model(),
            "provider": _provider_name(),
        })
        tool_chain[-1]["status"] = "processing"
        tool_chain[-1]["summary"] = "Generating JSON plan..."

        # Real provider usage when the response exposes it; every token field
        # stays None (unknown) otherwise. Never a fabricated token estimate.
        synthesis_usage = chat_agent.new_usage()
        try:
            response_data = await gemini_chat_completion(payload)
        except Exception as e:
            tool_chain[-1]["status"] = "failed"
            tool_chain[-1]["summary"] = f"model error: {type(e).__name__}"
            return _structured_error(grounding.LLM_ERROR,
                                     "The language model call failed.",
                                     tool_chain, grounding_meta=grounding_meta)
        chat_agent.record_usage(synthesis_usage, response_data, payload["messages"])

        raw_response, content_error = _extract_model_content(response_data)
        if raw_response is None:
            tool_chain[-1]["status"] = "failed"
            tool_chain[-1]["summary"] = "invalid model response"
            return _structured_error(
                grounding.LLM_ERROR,
                "The language model returned an unusable response shape.",
                tool_chain, details=content_error, grounding_meta=grounding_meta)

        try:
            clean_json = re.sub(r'```json\s*', '', raw_response)
            clean_json = re.sub(r'```', '', clean_json).strip()
            final_itinerary_json = json.loads(clean_json)
        except json.JSONDecodeError:
            tool_chain[-1]["status"] = "failed"
            tool_chain[-1]["summary"] = "malformed model JSON"
            return _structured_error(grounding.LLM_ERROR,
                                     "The language model did not return valid JSON.",
                                     tool_chain, grounding_meta=grounding_meta)

        # --- STEP 7: VALIDATE + RECONSTRUCT FROM EVIDENCE ---
        plan = grounding.validate_and_reconstruct_plan(
            final_itinerary_json, enriched, district, city,
            request.start_date, request.duration_days,
            source_selection=source_selection)
        if not plan.ok:
            tool_chain[-1]["status"] = "failed"
            tool_chain[-1]["summary"] = plan.code
            return _structured_error(plan.code, plan.message, tool_chain,
                                     grounding_meta=grounding_meta)

        tool_chain[-1]["status"] = "success"
        grounding_meta["missing_data"] = plan.missing_data
        grounding_meta["notes"] = plan.notes
        grounding_meta["scope_verifications"] = plan.scope_verifications
        grounding_meta["total_estimated_budget_is_estimate"] = True

        # --- STEP 8: DETERMINISTIC PLANNING + INDEPENDENT VALIDATION --------
        # The validated model proposal is recorded *separately* and used only as
        # a preference/selection input; the scheduler recomputes actual times,
        # order and budget, and the independent validator decides the status.
        initial_stops = plan.stops
        initial_sequence = [stop["poi"]["id"] for stop in initial_stops]

        # Legacy per-POI *model estimates*, kept clearly separate from any source
        # cost (never promoted into the planner's cost evidence).
        model_stop_budgets: Dict[str, Optional[float]] = {}
        model_stops = (final_itinerary_json.get("stops")
                       if isinstance(final_itinerary_json, dict) else None)
        if isinstance(model_stops, list):
            for entry in model_stops:
                if not isinstance(entry, dict):
                    continue
                poi = entry.get("poi")
                pid = grounding.nonblank_str(poi.get("id")) if isinstance(poi, dict) else None
                if pid is None:
                    continue
                raw_budget = entry.get("budget")
                try:
                    model_stop_budgets[pid] = None if raw_budget is None else float(raw_budget)
                except (TypeError, ValueError):
                    model_stop_budgets[pid] = None

        # Deterministic preference transform of the model order (earlier = higher).
        model_category_weights: Dict[str, int] = {}
        for index, poi_id in enumerate(initial_sequence):
            for category_id in candidate_category_ids.get(poi_id, []):
                weight = len(initial_sequence) - index
                if weight > model_category_weights.get(category_id, 0):
                    model_category_weights[category_id] = weight

        budget_constraint, budget_reason = planning_adapter.parse_budget_constraint(request)
        transport_mode, transport_mode_source = planning_adapter.request_transport_mode(
            request)

        planning_block: Dict[str, Any] = {
            "source": "deterministic_scheduler+independent_validator",
            "validator_status": "no_plan",
            "verified": False,
            "verified_conditionally_on_assumptions": False,
            "facts_fully_known": False,
            "model_usage": synthesis_usage,
            "initial_proposal": {
                "sequence": list(initial_sequence),
                "total_estimated_budget": plan.total_estimated_budget,
                "stops": initial_stops,
            },
            "repaired_schedule": None,
            "validation": None,
            "totals": None,
            "cost": None,
            "assumptions": [],
            "source_unknowns": [],
            "hours_parser": {},
            "cost_policy": dict(planning_adapter.COST_POLICY),
            "request_constraints": {
                "transport_mode": transport_mode,
                "transport_mode_source": transport_mode_source,
            },
            "budget_constraint": (
                None if budget_constraint is None else {
                    "amount": format(budget_constraint.amount, "f"),
                    "currency": budget_constraint.currency,
                    "unit": budget_constraint.unit,
                    "source": budget_constraint.source}),
            "budget_parse_reason": budget_reason,
            "route_evidence": planning_adapter.RouteEvidence(
                transport_mode=transport_mode,
                transport_mode_source="request").as_dict(),
            "route_geometry": {"type": "FeatureCollection", "features": []},
            "route_instructions": [],
            "route_geometry_status": "missing",
            "limitations": [],
        }
        if source_selection is not None:
            # Preserve the original explicit selection through every planning
            # branch, including error replies emitted before scenario build.
            planning_block["scope_mode"] = mode
            planning_block["scope_contract"] = grounding.SOURCE_SCOPE_CONTRACT
            planning_block["source_scope"] = dict(source_selection)
            planning_block["request_constraints"] = {
                "transport_mode": transport_mode,
                "transport_mode_source": transport_mode_source,
                "scope_mode": mode,
                "source_scope": dict(source_selection),
            }
            # The initial (model-proposal) metadata stays identifiable even when
            # the deterministic scheduler later adds/reorders/drops stops.
            planning_block["initial_proposal"]["missing_data"] = list(
                plan.missing_data)
            planning_block["initial_proposal"]["scope_verifications"] = list(
                plan.scope_verifications)
            planning_block["initial_proposal"]["notes"] = list(plan.notes)

        # --- Explicit constraint validation BEFORE any route call ----------
        # A malformed/incomplete *explicit* budget field must fail validation;
        # only an absent or legacy free-form/ambiguous budget stays unknown.
        if planning_adapter.budget_reason_is_fatal(budget_reason):
            planning_block["limitations"].append(
                f"budget_constraint_invalid:{budget_reason}")
            return _structured_error(
                grounding.INVALID_REQUEST,
                "The explicit budget fields are malformed or incomplete.",
                tool_chain, details=budget_reason, grounding_meta=grounding_meta,
                planning=planning_block)

        constraint_error = planning_adapter.validate_constraints(
            request, enriched, candidate_category_ids)
        if constraint_error is not None:
            _, constraint_detail = constraint_error
            planning_block["limitations"].append(f"constraint_invalid:{constraint_detail}")
            return _structured_error(
                grounding.INVALID_REQUEST,
                "An explicit planning constraint is invalid or out of scope.",
                tool_chain, details=constraint_detail, grounding_meta=grounding_meta,
                planning=planning_block)

        route_edges, route_evidence = await planning_adapter.collect_route_edges(
            session.call_tool, list(enriched.keys()),
            transport_mode=transport_mode,
            # Only the actual grounded model proposal order is passed, as a
            # capped-pair *preference*. It cannot add ids, modes, categories or
            # preferences, and every pair is still a real route call.
            priority_sequence=list(initial_sequence))
        inputs = planning_adapter.build_scenario(
            request, enriched, candidate_category_ids, route_edges, budget_constraint,
            model_category_weights=model_category_weights)

        planning_block["assumptions"] = list(inputs.assumptions)
        planning_block["source_unknowns"] = list(inputs.unknowns)
        planning_block["hours_parser"] = dict(inputs.hours_source)
        planning_block["cost_policy"] = dict(inputs.cost_policy)
        planning_block["request_constraints"] = dict(inputs.request_constraints)
        planning_block["route_evidence"] = route_evidence.as_dict()

        if inputs.build_error is not None:
            code, detail = inputs.build_error
            planning_block["limitations"].append(f"scenario_build_failed:{code}")
            return _structured_error(
                grounding.INSUFFICIENT_DATA,
                "The verified evidence could not form a valid planning scenario.",
                tool_chain, details=detail, grounding_meta=grounding_meta,
                planning=planning_block)

        scenario = inputs.scenario
        scheduler_plan = planning_schedule(scenario)
        report = planning_validate(scenario, scheduler_plan)

        planned_stops = [stop for day in scheduler_plan.days for stop in day.stops]
        scheduled_ids = [stop.poi_id for stop in planned_stops]
        hours_known = all(inputs.hours_status.get(pid) in ("always_open", "daily_window")
                          for pid in scheduled_ids)
        violation_codes = {v.code for v in report.known_violations}
        # Each dimension is classified from *its own* violation codes and
        # unknowns: an unrelated required-category/budget failure must not be
        # reported as a route or hours violation. A single-stop schedule requires
        # no inter-stop route, so route feasibility is `not_applicable` (never a
        # vacuous `verified`). no_plan/empty can never be `verified`.
        route_violated = bool(violation_codes & {"travel_infeasible",
                                                 "return_depot_infeasible"})
        hours_violated = "opening_violation" in violation_codes
        # Selected-plan coverage: the delivered schedule's own directed legs must
        # each be backed by an actual successful edge. Legs are computed per
        # actual scheduled day (never from a flattened multi-day id list, which
        # would invent a day-N-last -> day-N+1-first edge). Candidate-pool
        # coverage (a different, capped question) stays reported separately.
        scheduled_days = [{"day_id": day.day_id,
                           "poi_ids": [stop.poi_id for stop in day.stops]}
                          for day in scheduler_plan.days]
        selected_route = planning_adapter.selected_plan_day_route_coverage(
            scheduled_days, route_evidence, transport_mode=transport_mode,
            start_depot_id=getattr(scenario, "start_depot_id", None),
            end_depot_id=getattr(scenario, "end_depot_id", None))
        planning_block["selected_plan_route"] = selected_route
        # Selected actual scheduled-day directed legs only. Geometry comes from
        # the real GraphHopper road path; missing legs stay missing (no line is
        # drawn between markers) and are listed explicitly for the UI.
        route_geometry = planning_adapter.selected_plan_day_route_geometry(
            scheduled_days, route_evidence, transport_mode=transport_mode,
            start_depot_id=getattr(scenario, "start_depot_id", None),
            end_depot_id=getattr(scenario, "end_depot_id", None))
        planning_block["route_instructions"] = route_geometry.pop(
            "instructions", [])
        planning_block["route_geometry"] = route_geometry
        if route_geometry["features"]:
            planning_block["route_geometry_status"] = "available"
        elif route_geometry["requested_leg_count"]:
            planning_block["route_geometry_status"] = "missing"
        else:
            planning_block["route_geometry_status"] = "not_applicable"
        selected_route_complete = selected_route["coverage"] == "complete"
        if report.status == "no_plan" or not scheduled_ids:
            route_feasibility = "unknown"
            hours_feasibility = "unknown"
        else:
            if route_violated:
                route_feasibility = "violated"
            elif selected_route["coverage"] == "not_applicable":
                route_feasibility = "not_applicable"
            elif selected_route_complete:
                route_feasibility = "verified"
            else:
                route_feasibility = "unverifiable"
            if hours_violated:
                hours_feasibility = "violated"
            elif hours_known:
                hours_feasibility = "verified"
            else:
                hours_feasibility = "unverifiable"
        grounding_meta["route_feasibility"] = route_feasibility
        grounding_meta["route_coverage_scope"] = planning_adapter.SELECTED_PLAN_COVERAGE_SCOPE
        grounding_meta["candidate_pool_route_coverage"] = route_evidence.coverage
        grounding_meta["opening_hours_feasibility"] = hours_feasibility
        grounding_meta["planning_status"] = report.status
        grounding_meta["plan_verified"] = (report.status == "feasible")

        # `verified`/`success` are qualified: feasible only against the disclosed
        # assumptions (default day window/visit policy), and honest about whether
        # every source fact is known. No unqualified all-facts-known claim.
        facts_fully_known = not inputs.unknowns and not inputs.assumptions
        planning_block["validator_status"] = report.status
        planning_block["verified"] = (report.status == "feasible")
        planning_block["verified_conditionally_on_assumptions"] = bool(
            report.status == "feasible" and inputs.assumptions)
        planning_block["facts_fully_known"] = facts_fully_known
        planning_block["status_semantics"] = (
            "top-level status=success means a grounded proposal was delivered; "
            "planning.verified/verified_conditionally_on_assumptions/facts_fully_known "
            "carry the feasibility qualifier")
        planning_block["validation"] = planning_adapter.render_validation(report)
        planning_block["repaired_schedule"] = planning_adapter.render_plan(scheduler_plan)

        legs = [
            {
                "poi_id": stop.poi_id,
                "travel_from_prev_minutes": stop.travel_from_prev_minutes,
                "travel_from_prev_distance_km": (
                    None if stop.travel_from_prev_distance_km is None
                    else format(stop.travel_from_prev_distance_km, "f")),
            }
            for stop in planned_stops
        ]
        known_costs = [stop.cost_party for stop in planned_stops
                       if stop.cost_party is not None]
        any_unknown_cost = any(stop.cost_party is None for stop in planned_stops)
        known_subtotal = sum(known_costs) if known_costs else None
        total_distance = report.recomputed_total_distance_km
        planning_block["totals"] = {
            "travel_minutes": report.recomputed_total_travel_minutes,
            "distance_km": None if total_distance is None else format(total_distance, "f"),
            "stop_count": report.stop_count,
            "legs": legs,
        }
        planning_block["cost"] = {
            "status": "unknown" if any_unknown_cost else "verified",
            "known_party_subtotal": (None if known_subtotal is None
                                     else format(known_subtotal, "f")),
            "currency": scenario.currency,
            "unknown_reasons": [r for r in report.unknown_reasons
                                if r.startswith("cost_unknown:")],
            "menu_offers_repurposed": False,
            "model_budget_promoted_to_source_cost": False,
        }

        # Known-violating schedules (or refusals) are never delivered as a
        # verified plan: fail closed with the reasons, preserving the proposal.
        if report.status in ("no_plan", "partial"):
            planning_block["limitations"].append(
                f"schedule_withheld:{report.status}")
            message = ("The scheduler produced no deliverable plan."
                       if report.status == "no_plan"
                       else "The deterministic plan has known constraint violations "
                            "and was withheld.")
            return _structured_error(
                grounding.INSUFFICIENT_DATA, message, tool_chain,
                details={
                    "planning_status": report.status,
                    "no_plan_reason": report.no_plan_reason,
                    "known_violations": [v.code for v in report.known_violations],
                    "unsatisfied_required": list(report.unsatisfied_required),
                },
                grounding_meta=grounding_meta, planning=planning_block)

        # --- Build the delivered reply from the *repaired* schedule ---------
        # Re-validate every selected stop against the same explicit selection:
        # scheduler repair must never silently drop the source contract.
        if source_selection is not None:
            for stop in planned_stops:
                evidence = enriched.get(stop.poi_id) or {}
                if grounding.poi_source_scope_status(
                        evidence, source_selection) != "qualified":
                    return _structured_error(
                        grounding.SCOPE_CONFLICT,
                        "A repaired-schedule stop no longer matches the "
                        "explicitly selected source snapshot area.",
                        tool_chain, details={"poi_id": stop.poi_id},
                        grounding_meta=grounding_meta, planning=planning_block)

        day_date_by_id = {day.day_id: day.date for day in scenario.days}
        initial_poi_by_id = {stop["poi"]["id"]: stop["poi"] for stop in initial_stops}
        repaired_stops: List[Dict[str, Any]] = []
        # Final-schedule source metadata is rebuilt from the same verified
        # enrichment evidence, using the delivered stop's own index. This keeps
        # scope/missing metadata aligned with the document actually returned.
        final_missing_data: List[str] = []
        final_scope_verifications: List[str] = []
        final_notes: List[str] = []
        for day in scheduler_plan.days:
            day_date = day_date_by_id.get(day.day_id)
            for stop in day.stops:
                final_index = len(repaired_stops)
                if source_selection is not None:
                    evidence = enriched.get(stop.poi_id) or {}
                    source_context = evidence.get("source_context")
                    if not isinstance(source_context, dict):
                        return _structured_error(
                            grounding.SOURCE_SCOPE_UNVERIFIED,
                            "A delivered stop has no compact source_context.",
                            tool_chain, details={"poi_id": stop.poi_id},
                            grounding_meta=grounding_meta,
                            planning=planning_block)
                    poi_dict = grounding._reconstruct_poi(
                        evidence, None, final_missing_data,
                        f"stops[{final_index}]", source_context=source_context)
                    final_scope_verifications.append(
                        "qualified_source_snapshot_area")
                    final_notes.append(
                        f"stops[{final_index}].description replaced with neutral "
                        "selection text (model free text was not grounded).")
                else:
                    poi_dict = initial_poi_by_id.get(stop.poi_id)
                    if poi_dict is None:
                        evidence = enriched.get(stop.poi_id) or {}
                        admin = evidence.get("administrative_context")
                        poi_dict = grounding._reconstruct_poi(
                            evidence, admin if isinstance(admin, dict) else {},
                            [], f"repaired.{stop.poi_id}")
                repaired_stops.append({
                    "date": day_date,
                    "visit_time": planning_adapter.epoch_to_vn_iso(stop.arrival),
                    "end_time": planning_adapter.epoch_to_vn_iso(stop.departure),
                    "description": grounding.NEUTRAL_DESCRIPTION,
                    "description_grounded": False,
                    "budget": model_stop_budgets.get(stop.poi_id),
                    "budget_is_estimate": True,
                    "poi": poi_dict,
                })

        if source_selection is not None:
            final_notes.append(
                "source_snapshot_area: current city/district are unverified; "
                "source labels are not present-day administrative boundaries.")
            grounding_meta["missing_data"] = final_missing_data
            grounding_meta["scope_verifications"] = final_scope_verifications
            grounding_meta["notes"] = final_notes

        estimates = [model_stop_budgets.get(stop.poi_id) for stop in planned_stops]
        known_estimates = [value for value in estimates if value is not None]
        total_estimate = float(sum(known_estimates)) if known_estimates else None

        # Server-generated identity; the model's id/uid are never adopted.
        reply = {
            "id": f"itin_{uuid.uuid4().hex}",
            "id_source": "server",
            "uid": grounding.nonblank_str(uid),
            "uid_source": uid_source,
            "start_poi_id": scheduler_plan.sequence[0],
            "end_poi_id": scheduler_plan.sequence[-1],
            "total_estimated_budget": total_estimate,
            "budget_is_estimate": True,
            "stops": repaired_stops,
        }

        # No global/unauthenticated conversation side effect: durable/working
        # memory is owned by the authenticated /chat surface only.
        return {
            "status": "success",
            "reply": reply,
            "grounding": grounding_meta,
            "planning": planning_block,
            "tool_chain": tool_chain,
        }


async def _generate_itinerary_impl(request: ItineraryRequest, *,
                                   uid: Optional[str],
                                   uid_source: str,
                                   profile_block: Optional[str],
                                   memory_context: Optional[Dict[str, Any]] = None
                                   ) -> Dict[str, Any]:
    tool_chain: List[Dict[str, Any]] = []

    request_errors = grounding.validate_request(request)
    if request_errors:
        return _structured_error(
            grounding.INVALID_REQUEST,
            "Request failed grounding validation.",
            tool_chain, details=request_errors)

    try:
        # The private context is optional so direct/legacy/monkeypatched callers
        # that only implement the original four keywords keep their semantics.
        if memory_context is not None \
                and _accepts_keyword_argument(_run_itinerary, "memory_context"):
            return await _run_itinerary(
                request, tool_chain, uid=uid, uid_source=uid_source,
                profile_block=profile_block, memory_context=memory_context)
        return await _run_itinerary(request, tool_chain, uid=uid,
                                    uid_source=uid_source,
                                    profile_block=profile_block)
    except Exception as e:
        logger.error(f"General itinerary error: {type(e).__name__}")
        return _structured_error(
            "internal_error",
            "The itinerary pipeline failed before producing a grounded plan.",
            tool_chain)


async def generate_itinerary_endpoint(request: ItineraryRequest,
                                      uid: Optional[str] = None) -> Dict[str, Any]:
    """In-process entry point (no HTTP auth context).

    Anonymous by default: ``uid`` is ``null`` unless the caller explicitly
    supplies an already-verified subject. The session id is never used as an
    owner. The public HTTP route (``generate_itinerary_http``) binds ``uid`` to
    a verified JWT subject or null.
    """
    uid = grounding.nonblank_str(uid)
    _begin_provider_calls()
    result = await _generate_itinerary_impl(
        request,
        uid=uid,
        uid_source=("verified_jwt_sub" if uid else "anonymous"),
        profile_block=None,
    )
    if isinstance(result, dict):
        result["model"] = _public_model()
        result["provider"] = _provider_block()
    return result


@app.post("/generate_itinerary")
async def generate_itinerary_http(request: ItineraryRequest,
                                  http_request: Request) -> Dict[str, Any]:
    _begin_provider_calls()
    try:
        subject = memory_auth.optional_bearer(
            http_request.headers.get("authorization"))
    except AuthError as exc:
        raise _auth_http(exc)

    # Explicit source selection is validated before the profile store, model or
    # MCP work, matching /chat. The parsed tuple is also the scope signature.
    source_selection: Optional[Dict[str, str]] = None
    if request.source_scope is not None:
        parsed_source = grounding.parse_source_selection(request.source_scope)
        if not parsed_source.ok:
            raise HTTPException(status_code=422, detail={
                "code": "invalid_source_scope",
                "message": parsed_source.detail
                or "The explicit source selection is invalid.",
            })
        source_selection = dict(parsed_source.data)

    def _public_result(result: Dict[str, Any]) -> Dict[str, Any]:
        if isinstance(result, dict):
            result["model"] = _public_model()
            result["provider"] = _provider_block()
        return result

    # Typed request validation also happens before any store/model/MCP side
    # effect; the pipeline repeats it defensively for direct Python callers.
    request_errors = grounding.validate_request(request)
    if request_errors:
        early = _structured_error(
            grounding.INVALID_REQUEST,
            "Request failed grounding validation.",
            [], details=request_errors)
        early["memory"] = {
            "enabled": bool(request.memory_enabled),
            "scope": "verified_user" if subject else "anonymous_local_only",
            "profile_injected": False,
            "discarded_turns": 0,
            "context_reset": False,
        }
        return _public_result(early)

    # reply.uid is a verified JWT subject or null — never session_id / model uid.
    profile_block: Optional[str] = None
    if subject is not None and request.memory_enabled:
        store = get_profile_store()
        if store is not None:
            try:
                record = store.get(subject)
            except Exception as exc:  # noqa: BLE001 - sanitized store failure
                raise _store_failure(exc)
            if record:
                profile_block = memory.profile_prompt(record["profile"])

    memory_meta: Dict[str, Any] = {
        "enabled": bool(request.memory_enabled),
        "scope": "verified_user" if subject else "anonymous_local_only",
        "profile_injected": bool(profile_block),
        "discarded_turns": 0,
        "context_reset": False,
    }

    if request.memory_enabled:
        # Same owner+session key, lease and source boundary as /chat. The lease
        # is held across retrieval/synthesis/commit so concurrent same-session
        # work is serialized and an abandoned request cannot leak it.
        memory_key = _memory_key(subject, request.session_id)
        signature = _scope_signature(
            source_selection, grounding.request_scope_mode(request))
        try:
            async with WORKING_MEMORY.lease(memory_key) as entry:
                memory_meta["context_reset"] = _apply_scope_boundary(
                    memory_key, signature, entry)
                result = await _generate_itinerary_impl(
                    request,
                    uid=subject,
                    uid_source=("verified_jwt_sub" if subject else "anonymous"),
                    profile_block=profile_block,
                    memory_context={"enabled": True, "entry": entry},
                )
                assistant_text = _itinerary_memory_assistant_text(result)
                if assistant_text is not None:
                    committed = WORKING_MEMORY.commit(
                        entry,
                        [{"role": "assistant", "content": assistant_text}],
                        request.user_description)
                    memory_meta["discarded_turns"] = committed.get(
                        "discarded_turns", 0)
        except memory.SessionCapacityError:
            raise HTTPException(status_code=503, detail={
                "code": "memory_capacity",
                "message": "Too many active chat sessions; please retry.",
            })
    else:
        # Bypasses the store, lease, history and profile entirely, while keeping
        # the same fixed base persona/current-request construction.
        result = await _generate_itinerary_impl(
            request,
            uid=subject,
            uid_source=("verified_jwt_sub" if subject else "anonymous"),
            profile_block=None,
            memory_context={"enabled": False, "entry": None},
        )

    if isinstance(result, dict):
        result["memory"] = memory_meta
        if result.get("status") == "success":
            chat_mvp.SAVED_DRAFT_STORE.remember_generated(
                _memory_key(subject, request.session_id),
                _public_result(result),
            )
    return _public_result(result)


CHITCHAT_FALLBACK = "I'm thinking a bit slowly today! Could you say that again?"

INTENT_CLARIFY_REPLY_VN = (
    "Bạn muốn trò chuyện hay cần mình tư vấn du lịch? "
    "Vui lòng nói rõ mục đích để mình hỗ trợ đúng nhé."
)
INTENT_UNAVAILABLE_REPLY_VN = (
    "Dịch vụ phân loại ý định tạm thời không khả dụng. "
    "Vui lòng thử lại sau."
)


def _router_gate(router: Any) -> Tuple[str, Optional[str]]:
    """Map a (possibly injected/malformed) router result to a safe gate.

    Only ``status=="ok"`` with an in-enum CHITCHAT/TRAVEL intent may proceed.
    Everything else stops before profile/memory/model/MCP work.
    """
    if not isinstance(router, dict):
        return "unavailable", None
    status = router.get("status")
    intent = router.get("intent")
    if status == "ok" and isinstance(intent, str) and intent in VALID_INTENTS:
        return "proceed", intent
    if status == "ambiguous" or (status == "ok" and intent == "UNCERTAIN"):
        return "clarify", None
    return "unavailable", None


def _unresolved_chat_response(request: ChatRequest, subject: Optional[str],
                              router: Any, usage: Dict[str, Any],
                              outcome: str, *,
                              source_selection: Optional[Dict[str, str]] = None,
                              transport_mode: Optional[str] = None,
                              transport_source: Optional[str] = None) -> JSONResponse:
    """Clarification (200) or deterministic unavailable (503), no downstream I/O."""
    _finalize_usage(usage)
    clarify = outcome == "clarify"
    body: Dict[str, Any] = {
        "intent": None,
        "reply": INTENT_CLARIFY_REPLY_VN if clarify
        else INTENT_UNAVAILABLE_REPLY_VN,
        "status": "needs_clarification" if clarify else "unavailable",
        "model": _public_model(),
        "provider": _provider_block(),
        "transport_mode": transport_mode,
        "transport_mode_source": transport_source,
        "source_scope": source_selection,
        "scope_mode": grounding.request_scope_mode(request),
        "tool_chain": [],
        "source_evidence_ids": [],
        "usage": usage,
        "router": _router_public(router),
        "memory": {
            "enabled": request.memory_enabled,
            "scope": "verified_user" if subject else "anonymous_local_only",
            "profile_injected": False,
            "discarded_turns": 0,
        },
    }
    if clarify:
        body["clarification_required"] = True
        return JSONResponse(status_code=200, content=body)
    body["error"] = {
        "code": "intent_unavailable",
        "message": "The intent classification service is unavailable.",
    }
    return JSONResponse(status_code=503, content=body)


async def _dispatch_intent(intent: str, messages: List[Dict[str, Any]],
                           usage: Dict[str, Any], *,
                           source_selection: Optional[Dict[str, str]] = None,
                           transport_mode: str = "car",
                           owner_key: Optional[str] = None) -> Dict[str, Any]:
    """Dispatch validated executable intents (v1 and v1.1)."""
    user_message = ""
    prior_messages: List[Dict[str, Any]] = []
    for msg in messages:
        if isinstance(msg, dict) and msg.get("role") == "user":
            user_message = str(msg.get("content") or "")
    if len(messages) > 2:
        prior_messages = messages[1:-1]

    if intent == "TRAVEL":
        result = await _run_travel_turn(messages, usage,
                                        source_selection=source_selection,
                                        transport_mode=transport_mode)
        return chat_mvp.apply_mvp_contract(
            intent=intent,
            user_message=user_message,
            prior_messages=prior_messages,
            result=result,
            owner_key=owner_key,
        )

    if intent == "CHITCHAT":
        if chat_mvp.is_poi_lookup_question(user_message):
            result = await chat_mvp.run_grounded_poi_lookup(
                user_message=user_message,
                messages=messages,
                usage=usage,
                open_mcp_session_fn=open_mcp_session,
                call_model_fn=gemini_chat_completion,
                selected_model=_selected_model(),
                completion_controls=_completion_limit_controls(500),
            )
        else:
            result = await _run_chitchat(messages, usage)
        return chat_mvp.apply_mvp_contract(
            intent=intent,
            user_message=user_message,
            prior_messages=prior_messages,
            result=result,
            owner_key=owner_key,
        )

    if intent in ("BOOKING", "PLAN", "MANAGE_SAVED", "MANAGE_MEMORY"):
        result = await _run_chitchat(messages, usage)
        return chat_mvp.apply_mvp_contract(
            intent=intent,
            user_message=user_message,
            prior_messages=prior_messages,
            result=result,
            owner_key=owner_key,
        )

    raise RuntimeError("unresolved intent reached dispatch")


async def _run_chitchat(messages: List[Dict[str, Any]],
                        usage: Dict[str, Any]) -> Dict[str, Any]:
    payload = {
        "model": _selected_model(),
        "messages": messages,
        "temperature": 0.7,
        **_completion_limit_controls(500),
    }
    try:
        response_data = await gemini_chat_completion(payload)
    except Exception as e:  # noqa: BLE001
        chat_agent.record_failed_call(usage, messages)
        logger.error("Chitchat model call failed: %s", type(e).__name__)
        return {
            "status": chat_agent.STATUS_FAILED,
            "reply": CHITCHAT_FALLBACK,
            "tool_chain": [],
            "turn_messages": [],
            "source_evidence_ids": [],
            "grounding_status": None,
            "loop_limit": False,
            "error": {"code": "model_unavailable",
                      "message": "The language model is unavailable."},
        }
    chat_agent.record_usage(usage, response_data, messages)
    message, err = chat_agent.extract_assistant_message(response_data)
    if err is not None:
        logger.warning("Chitchat invalid model response: %s", err)
        return {
            "status": chat_agent.STATUS_FAILED,
            "reply": CHITCHAT_FALLBACK,
            "tool_chain": [],
            "turn_messages": [],
            "source_evidence_ids": [],
            "grounding_status": None,
            "loop_limit": False,
            "error": {"code": "invalid_model_response",
                      "message": "The language model returned an unusable response."},
        }
    content = message.get("content")
    assistant = {"role": "assistant",
                 "content": content if isinstance(content, str) else ""}
    return {
        "status": chat_agent.STATUS_SUCCESS,
        "reply": assistant["content"],
        "tool_chain": [],
        "turn_messages": [assistant],
        "source_evidence_ids": [],
        "grounding_status": None,
        "loop_limit": False,
    }


@app.post("/chat")
async def chat_endpoint(request: ChatRequest,
                        authorization: Optional[str] = Header(default=None)):
    _begin_provider_calls()

    # Explicit request context is validated before auth work, Jev routing, the
    # profile store, working memory, MCP or any model call.
    parsed_scope = None
    if request.source_scope is not None:
        parsed_scope = grounding.parse_source_selection(request.source_scope)
        if not parsed_scope.ok:
            raise HTTPException(status_code=422, detail={
                "code": "invalid_source_scope",
                "message": parsed_scope.detail
                or "The explicit source selection is invalid.",
            })
    source_selection: Optional[Dict[str, str]] = (
        dict(parsed_scope.data) if parsed_scope is not None else None)
    transport_mode, transport_source = planning_adapter.request_transport_mode(
        request)
    if transport_mode is None:
        raise HTTPException(status_code=422, detail={
            "code": "invalid_transport_mode",
            "message": "transport_mode must be exactly 'car' or 'foot'.",
        })
    signature = _scope_signature(
        source_selection, grounding.request_scope_mode(request))

    try:
        subject = memory_auth.optional_bearer(authorization)
    except AuthError as exc:
        raise _auth_http(exc)

    usage = chat_agent.new_usage()
    router = await route_intent(request.message, usage)
    gate, intent = _router_gate(router)
    if gate != "proceed":
        # Stop before profile store, working-memory lease, prompt composition,
        # commit, MCP, planner or any generation model call.
        return _unresolved_chat_response(
            request, subject, router, usage,
            "clarify" if gate == "clarify" else "unavailable",
            source_selection=source_selection,
            transport_mode=transport_mode,
            transport_source=transport_source)

    profile_block: Optional[str] = None
    if request.memory_enabled and subject is not None and intent == "TRAVEL":
        store = get_profile_store()
        if store is not None:
            try:
                record = store.get(subject)
            except Exception as exc:  # noqa: BLE001 - sanitized store failure
                raise _store_failure(exc)
            if record:
                profile_block = memory.profile_prompt(record["profile"])

    context_reset = False
    if request.memory_enabled:
        memory_key = _memory_key(subject, request.session_id)
        try:
            async with WORKING_MEMORY.lease(memory_key) as entry:
                # A changed (or unknown) explicit context must not inherit the
                # previous scope's tool evidence or travel text.
                context_reset = _apply_scope_boundary(
                    memory_key, signature, entry)
                messages = WORKING_MEMORY.compose(entry, SYSTEM_PROMPT,
                                                  request.message)
                if profile_block and intent == "TRAVEL":
                    messages[0]["content"] += "\n\n" + profile_block
                if intent == "TRAVEL":
                    # Profile/history cannot override the typed selection.
                    messages[0]["content"] += transport_chat_instructions(
                        transport_mode, transport_source)
                if source_selection is not None and intent == "TRAVEL":
                    messages[0]["content"] += SOURCE_CHAT_INSTRUCTIONS
                result = await _dispatch_intent(
                    intent, messages, usage,
                    source_selection=source_selection,
                    transport_mode=transport_mode,
                    owner_key=memory_key)
                memory_meta = WORKING_MEMORY.commit(
                    entry, result.get("turn_messages", []), request.message)
        except memory.SessionCapacityError:
            raise HTTPException(status_code=503, detail={
                "code": "memory_capacity",
                "message": "Too many active chat sessions; please retry.",
            })
    else:
        # memory_enabled=false bypasses both short and long-term memory: no
        # session is created/pinned and only the current turn reaches the model.
        messages = [{"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": request.message}]
        if profile_block and intent == "TRAVEL":
            messages[0]["content"] += "\n\n" + profile_block
        if intent == "TRAVEL":
            messages[0]["content"] += transport_chat_instructions(
                transport_mode, transport_source)
        if source_selection is not None and intent == "TRAVEL":
            messages[0]["content"] += SOURCE_CHAT_INSTRUCTIONS
        result = await _dispatch_intent(
            intent, messages, usage,
            source_selection=source_selection,
            transport_mode=transport_mode,
            owner_key=_memory_key(subject, request.session_id))
        memory_meta: Dict[str, Any] = {"discarded_turns": 0}

    _finalize_usage(usage)
    response: Dict[str, Any] = {
        "intent": intent,
        "reply": result.get("reply"),
        "status": result.get("status"),
        "model": _public_model(),
        "provider": _provider_block(),
        "tool_chain": result.get("tool_chain", []),
        "usage": usage,
        "router": _router_public(router),
        "transport_mode": transport_mode,
        "transport_mode_source": transport_source,
        "source_scope": source_selection,
        "scope_mode": grounding.request_scope_mode(request),
        "memory": {
            "enabled": request.memory_enabled,
            "scope": "verified_user" if subject else "anonymous_local_only",
            "profile_injected": bool(profile_block),
            "discarded_turns": memory_meta.get("discarded_turns", 0),
            "context_reset": context_reset,
        },
    }
    if isinstance(result.get("scope_gate"), dict):
        response["scope_gate"] = result["scope_gate"]
        route_evidence = result["scope_gate"].get("route_evidence")
        if isinstance(route_evidence, dict):
            response["route_evidence"] = route_evidence
    if isinstance(result.get("bootstrap"), dict):
        response["bootstrap"] = result["bootstrap"]
    if result.get("grounding_status") is not None:
        response["grounding_status"] = result["grounding_status"]
    if result.get("source_evidence_ids") is not None:
        response["source_evidence_ids"] = result["source_evidence_ids"]
    if result.get("claims") is not None:
        response["claims"] = result["claims"]
    if result.get("actions") is not None:
        response["actions"] = result["actions"]
    if result.get("booking") is not None:
        response["booking"] = result["booking"]
    if result.get("planning") is not None:
        response["planning"] = result["planning"]
    if result.get("saved") is not None:
        response["saved"] = result["saved"]
    if "handoff" in result:
        response["handoff"] = result["handoff"]
    if result.get("loop_limit"):
        response["loop_limit"] = True
    if result.get("error"):
        response["error"] = result["error"]
    return response


STATIC_DIR = Path(__file__).resolve().parent / "static"

SOURCE_CATALOG_TOOL = "explore_pois"
SOURCE_CATALOG_NOTICE = (
    "Source area labels are dataset labels from the selected OSM snapshot; they "
    "are not present-day administrative boundaries and are never called a "
    "current city or district."
)


# ---------------------------------------------------------------------------
# Thin same-origin source catalog (proxies the existing MCP discovery only)
# ---------------------------------------------------------------------------
def _catalog_int(value: Any) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _catalog_scan(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, dict):
        return None
    return {
        "scanned_record_count": _catalog_int(value.get("scanned_record_count")),
        "excluded_corrupt_count": _catalog_int(value.get("excluded_corrupt_count")),
        "scan_complete": value.get("scan_complete") is True,
        "truncated": value.get("truncated") is True,
    }


def _catalog_snapshot(item: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(item, dict):
        return None
    namespace = item.get("dataset_namespace")
    sha = item.get("input_sha256")
    if not isinstance(namespace, str) or not namespace or namespace != namespace.strip():
        return None
    if not isinstance(sha, str) or not grounding.SOURCE_INPUT_SHA256_RE.fullmatch(sha):
        return None
    count = _catalog_int(item.get("valid_record_count"))
    areas = _catalog_int(item.get("source_area_count"))
    if count is None or areas is None:
        return None
    return {
        "dataset_namespace": namespace,
        "input_sha256": sha,
        "valid_record_count": count,
        "source_area_count": areas,
    }


def _catalog_area(item: Any, namespace: str, sha: str
                  ) -> Optional[Dict[str, Any]]:
    if not isinstance(item, dict):
        return None
    area_id = item.get("source_area_id")
    label = item.get("source_area_label")
    if not isinstance(area_id, str) or not grounding.SOURCE_AREA_ID_RE.fullmatch(area_id):
        return None
    if not isinstance(label, str) or not label.strip():
        return None
    assignment = item.get("area_assignment")
    if assignment not in ("qualified", "unassigned"):
        return None
    raw_city = item.get("raw_city")
    raw_area = item.get("raw_area")
    for raw in (raw_city, raw_area):
        if raw is not None and (not isinstance(raw, str) or not raw.strip()):
            return None
    count = _catalog_int(item.get("valid_record_count"))
    if count is None:
        return None
    return {
        # Canonical tuple the client must send back verbatim.
        "selection": {
            "dataset_namespace": namespace,
            "input_sha256": sha,
            "source_area_id": area_id,
        },
        "source_area_label": label,
        "raw_city": raw_city,
        "raw_area": raw_area,
        "area_assignment": assignment,
        "valid_record_count": count,
    }


async def _mcp_discovery(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Call the existing MCP discovery mode; never a model, never a file read."""
    try:
        async with open_mcp_session() as session:
            raw = await session.call_tool(SOURCE_CATALOG_TOOL, arguments=arguments)
    except Exception:  # noqa: BLE001 - sanitized catalog failure
        logger.error("Source catalog transport failure")
        raise HTTPException(status_code=502, detail={
            "code": "catalog_unavailable",
            "message": "The source catalog is temporarily unavailable.",
        })
    outcome = grounding.parse_mcp_tool_result(raw)
    if not outcome.ok or not isinstance(outcome.data, dict):
        logger.error("Source catalog returned unusable data")
        raise HTTPException(status_code=502, detail={
            "code": "catalog_unavailable",
            "message": "The source catalog returned an unusable response.",
        })
    return outcome.data


@app.get("/healthz")
async def healthz() -> Dict[str, Any]:
    return {"status": "ok", "service": "ai_service"}


@app.get("/travel", include_in_schema=False)
async def travel_page():
    page = STATIC_DIR / "travel.html"
    if not page.is_file():
        raise HTTPException(status_code=404, detail={
            "code": "ui_not_installed",
            "message": "The travel page is not installed on this deployment.",
        })
    return FileResponse(page, media_type="text/html; charset=utf-8")


@app.get("/catalog/snapshots")
async def catalog_snapshots() -> Dict[str, Any]:
    data = await _mcp_discovery({"source_discovery": "snapshots"})
    raw_items = data.get("snapshots")
    snapshots = []
    if isinstance(raw_items, list):
        for item in raw_items:
            safe = _catalog_snapshot(item)
            if safe is not None:
                snapshots.append(safe)
    return {
        "status": "ok" if snapshots else "empty",
        "snapshots": snapshots,
        "scan": _catalog_scan(data.get("scan")),
        "notice": SOURCE_CATALOG_NOTICE,
    }


@app.get("/catalog/source_areas")
async def catalog_source_areas(dataset_namespace: str,
                               input_sha256: str) -> Dict[str, Any]:
    if not dataset_namespace or dataset_namespace != dataset_namespace.strip():
        raise HTTPException(status_code=422, detail={
            "code": "invalid_snapshot",
            "message": "dataset_namespace must be nonblank without surrounding "
                       "whitespace.",
        })
    if not grounding.SOURCE_INPUT_SHA256_RE.fullmatch(input_sha256 or ""):
        raise HTTPException(status_code=422, detail={
            "code": "invalid_snapshot",
            "message": "input_sha256 must be a lowercase 64-character SHA256.",
        })

    data = await _mcp_discovery({
        "source_discovery": "source_areas",
        "source_snapshot": {
            "dataset_namespace": dataset_namespace,
            "input_sha256": input_sha256,
        },
    })
    # The service echoes the snapshot it scanned. A different echo means the
    # catalog contract changed; never relabel another snapshot's areas.
    if (data.get("dataset_namespace") != dataset_namespace
            or data.get("input_sha256") != input_sha256):
        logger.error("Source catalog snapshot echo mismatch")
        raise HTTPException(status_code=502, detail={
            "code": "catalog_contract_mismatch",
            "message": "The source catalog did not confirm the requested snapshot.",
        })

    raw_areas = data.get("source_areas")
    areas = []
    if isinstance(raw_areas, list):
        for item in raw_areas:
            safe = _catalog_area(item, dataset_namespace, input_sha256)
            if safe is not None:
                areas.append(safe)
    return {
        "status": "ok" if areas else "empty",
        "dataset_namespace": dataset_namespace,
        "input_sha256": input_sha256,
        "source_areas": areas,
        "scan": _catalog_scan(data.get("scan")),
        "notice": SOURCE_CATALOG_NOTICE,
    }

# ---------------------------------------------------------------------------
# Two-tier memory endpoints (durable profiles are opt-in and authenticated)
# ---------------------------------------------------------------------------
@app.get("/memory/profile")
async def get_memory_profile(authorization: Optional[str] = Header(default=None)):
    try:
        subject = memory_auth.verify_bearer(authorization)
    except AuthError as exc:
        raise _auth_http(exc)
    store = _memory_store_or_503()
    try:
        record = store.get(subject)
    except Exception as exc:  # noqa: BLE001
        raise _store_failure(exc)
    if record is None:
        return {"profile": None, "version": None, "updated_at": None}
    return record


@app.put("/memory/profile")
async def put_memory_profile(payload: Dict[str, Any],
                             authorization: Optional[str] = Header(default=None)):
    try:
        subject = memory_auth.verify_bearer(authorization)
    except AuthError as exc:
        raise _auth_http(exc)
    store = _memory_store_or_503()

    expected_version = _parse_expected_version(payload)

    profile_data: Any = payload
    if isinstance(payload.get("profile"), dict):
        profile_data = payload["profile"]

    ok, errors, normalized = memory.validate_profile(profile_data)
    if not ok:
        raise HTTPException(status_code=422, detail={
            "code": "invalid_profile", "errors": errors})

    try:
        return store.put(subject, normalized, expected_version=expected_version)
    except ProfileConflict as conflict:
        raise HTTPException(status_code=409, detail={
            "code": "revision_conflict",
            "current_version": conflict.current_version,
        })
    except Exception as exc:  # noqa: BLE001 - sanitized store failure
        raise _store_failure(exc)


@app.delete("/memory/profile")
async def delete_memory_profile(authorization: Optional[str] = Header(default=None)):
    try:
        subject = memory_auth.verify_bearer(authorization)
    except AuthError as exc:
        raise _auth_http(exc)
    store = _memory_store_or_503()
    try:
        return {"deleted": store.delete(subject)}
    except Exception as exc:  # noqa: BLE001
        raise _store_failure(exc)


@app.post("/memory/short/clear")
async def clear_short_memory(request: ClearMemoryRequest,
                             authorization: Optional[str] = Header(default=None)):
    try:
        subject = memory_auth.optional_bearer(authorization)
    except AuthError as exc:
        raise _auth_http(exc)
    key = _memory_key(subject, request.session_id)
    # Serialize with any in-flight request for this key (waits for its lease),
    # so a stale response cannot repopulate cleared history.
    existed = await WORKING_MEMORY.clear_key(key)
    _forget_scope_marker(key)
    return {
        "cleared": existed,
        "scope": "verified_user" if subject else "anonymous_local_only",
    }


# ---------------------------------------------------------------------------
# Owner-scoped saved itinerary drafts (KT-07 / MANAGE_SAVED)
# ---------------------------------------------------------------------------
@app.get("/saved/itineraries")
async def list_saved_itineraries(session_id: str = "default",
                                 authorization: Optional[str] = Header(default=None)):
    try:
        subject = memory_auth.optional_bearer(authorization)
    except AuthError as exc:
        raise _auth_http(exc)
    owner_key = _memory_key(subject, session_id or "default")
    items, total = chat_mvp.SAVED_DRAFT_STORE.list(owner_key)
    return {"status": "ok", "items": items, "total": total}


@app.post("/saved/itineraries", status_code=201)
async def save_itinerary_draft(body: Dict[str, Any],
                               authorization: Optional[str] = Header(default=None)):
    try:
        subject = memory_auth.optional_bearer(authorization)
    except AuthError as exc:
        raise _auth_http(exc)
    session_id = str(body.get("session_id") or "default").strip() or "default"
    payload = body.get("payload")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail={
            "code": "invalid_payload",
            "message": "payload must be a JSON object.",
        })
    title = body.get("title") if isinstance(body.get("title"), str) else None
    owner_key = _memory_key(subject, session_id)
    record = chat_mvp.SAVED_DRAFT_STORE.save(owner_key, payload, title=title)
    return {"status": "ok", "item": record}


@app.get("/saved/itineraries/{draft_id}")
async def get_saved_itinerary_draft(draft_id: str,
                                    session_id: str = "default",
                                    authorization: Optional[str] = Header(default=None)):
    try:
        subject = memory_auth.optional_bearer(authorization)
    except AuthError as exc:
        raise _auth_http(exc)
    owner_key = _memory_key(subject, session_id or "default")
    record = chat_mvp.SAVED_DRAFT_STORE.get(owner_key, draft_id)
    if record is None:
        raise HTTPException(status_code=404, detail={
            "code": "draft_not_found",
            "message": "Saved itinerary draft not found.",
        })
    return {"status": "ok", "item": record}


@app.delete("/saved/itineraries/{draft_id}")
async def delete_saved_itinerary_draft(draft_id: str,
                                       session_id: str = "default",
                                       authorization: Optional[str] = Header(default=None)):
    try:
        subject = memory_auth.optional_bearer(authorization)
    except AuthError as exc:
        raise _auth_http(exc)
    owner_key = _memory_key(subject, session_id or "default")
    deleted = chat_mvp.SAVED_DRAFT_STORE.delete(owner_key, draft_id)
    if not deleted:
        raise HTTPException(status_code=404, detail={
            "code": "draft_not_found",
            "message": "Saved itinerary draft not found.",
        })
    return {"status": "ok", "deleted": True, "id": draft_id}
