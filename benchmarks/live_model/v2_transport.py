"""Thin production-V2 transport adapter for the existing H2 collector.

This module intentionally does **not** implement a second harness. It is a
narrow seam over the already-accepted production provider:

* :class:`ai_service.domains.providers.opencode_cli.OpenCodeCliProvider` owns
  readiness, the private server, deny-only agent policy, native-tool rejection,
  owned cleanup, Go credential loading and the exact session-export binding;
* the collector only builds the paired prompt, calls ``complete`` once, reads
  the validated assistant text, and normalises a *whitelisted* provider receipt.

Nothing here writes raw CLI event streams or raw session exports, and no
provider path/metadata is invented. Evidence persisted by the caller is
explicitly a **derived structured service/provider receipt**.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]
_AI_ROOT = _REPO_ROOT / "ai_service"
if str(_AI_ROOT) not in sys.path:
    sys.path.insert(0, str(_AI_ROOT))

from domains.providers.cli_runtime import TRANSPORT_SYSTEM_PROMPT  # noqa: E402
from domains.providers.config import ProviderConfig  # noqa: E402
from domains.providers.errors import ModelUnavailableError  # noqa: E402
from domains.providers.opencode_cli import OpenCodeCliProvider  # noqa: E402

from .constants import (  # noqa: E402
    V2_CLI_PURE,
    V2_MAX_ATTEMPTS,
    V2_MAX_CONCURRENCY,
    V2_PROVIDER,
    V2_TRANSPORT_METHOD,
)
from .util import canonical_hash, sha256_text  # noqa: E402

EVIDENCE_KIND = "derived_structured_service_provider_receipt"
EVIDENCE_SOURCE = "OpenCodeCliProvider.complete normalized _provider metadata"
IDENTITY_SOURCE = "opencode_session_export"
REQUIRED_FINISH = "stop"

# Safe, closed projection of ``_provider``. Everything not listed here is
# dropped; in particular raw configs, engine subtrees, headers, paths and error
# bodies never reach an artifact.
_PROVIDER_SCALARS = (
    "requested_model", "prompt_sha256", "ok", "session_id", "observed_model",
    "observed_provider_id", "observed_model_id", "observed_agent",
    "identity_source", "assistant_message_id", "finish", "stream_format",
    "usage_total", "usage_consistent", "attempts", "failed_attempts",
    "runtime", "readiness_gate",
)
_CLI_CAPABILITY_KEYS = (
    "version", "capability_source", "pure_supported", "pure_requested",
    "pure_applied", "plugin_isolation", "reason", "standalone", "server",
    "agent_flag", "format_json", "session_export", "standalone_export",
    "server_export", "stream_format",
)
_ALLOWED_CONTROL_NAMES = ("temperature", "top_p")
_ALLOWED_VERIFICATIONS = frozenset({"not_observable_from_transport",
                                    "no_controls_requested"})
_ALLOWED_BINDINGS = frozenset({"provider_model_request_body"})
_USAGE_COMPONENTS = ("input", "output", "reasoning", "cache_read", "cache_write",
                     "total")
_TRANSPORT_KEYS = ("config_filename", "config_sha256", "scope")
_PREFLIGHT_KEYS = ("status", "transport_config_status", "config_sha256")


def transport_system_prompt() -> str:
    """The exact production V2 transport system prompt (read-only import)."""
    return TRANSPORT_SYSTEM_PROMPT


def settings_id(model: str, agent: str) -> str:
    """Settings identity for the V2 path (distinct from the legacy helper)."""
    return canonical_hash({
        "transport": V2_PROVIDER,
        "transport_method": V2_TRANSPORT_METHOD,
        "model_id": model,
        "agent": agent,
        "system_prompt": transport_system_prompt(),
        "format": "json",
        "permission": "*:deny",
        "cli_pure": V2_CLI_PURE,
        "max_attempts": V2_MAX_ATTEMPTS,
        "max_concurrency": V2_MAX_CONCURRENCY,
        "flags_forbidden": ["--continue", "--session", "--share", "--auto", "--fork"],
    })


def build_provider_config(*, model: str, executable: Optional[str], timeout: float,
                          agent: str) -> ProviderConfig:
    """Explicit provider configuration; native ownership stays in the provider."""
    return ProviderConfig(
        provider="opencode_cli",
        model=model,
        cli_executable=executable,
        cli_agent=agent,
        cli_timeout_seconds=timeout,
        cli_max_attempts=V2_MAX_ATTEMPTS,
        cli_max_concurrency=V2_MAX_CONCURRENCY,
        # Fixed and disclosed: the installed CLI has no --pure. Requesting it
        # fails closed in the collector before any provider call.
        cli_pure=V2_CLI_PURE,
        evidence_dir=None,
    )


def build_payload(prompt: str, model: str) -> Dict[str, Any]:
    """One text-only completion payload with the caller's exact paired prompt."""
    return {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
    }


def default_provider_factory(config: ProviderConfig,
                             cwd: Optional[Path] = None) -> OpenCodeCliProvider:
    return OpenCodeCliProvider(config, cwd=cwd)


# Test seam: unit tests replace *only* this factory (or ``complete_factory``)
# with a scripted fake. Production constructs the accepted provider unchanged.
provider_factory: Callable[..., Any] = default_provider_factory


def production_complete(config: ProviderConfig, cwd: Optional[Path]) -> Callable[..., Any]:
    return provider_factory(config, cwd).complete


# Test seam: returns the async ``complete`` callable for one provider instance.
complete_factory: Callable[[ProviderConfig, Optional[Path]], Callable[..., Any]] = \
    production_complete


def make_complete(config: ProviderConfig, cwd: Optional[Path]) -> Callable[..., Any]:
    return complete_factory(config, cwd)


def call_complete(complete: Callable[..., Any], payload: Mapping[str, Any]) -> Any:
    """Invoke the injected complete seam exactly once.

    A scripted fake may be synchronous; the production provider is async. No
    retry or fallback is performed here.
    """
    result = complete(dict(payload))
    if inspect.isawaitable(result):
        return asyncio.run(result)
    return result


class CompletionRejected(RuntimeError):
    """The completion cannot be admitted; ``code`` is bounded and non-secret."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ValidatedCompletion:
    text: str
    text_sha256: str
    duration_seconds: Optional[float]
    provider: Dict[str, Any] = field(default_factory=dict)
    usage: Dict[str, Any] = field(default_factory=dict)
    model: Optional[str] = None
    session_id: Optional[str] = None
    finish: Optional[str] = None


@dataclass(frozen=True)
class ProviderFailure:
    code: str
    attempts: int = 0
    failed_attempts: int = 0
    retryable: bool = False


def _provider_reason(provider: Mapping[str, Any], requested_model: str) -> Optional[str]:
    if provider.get("ok") is not True:
        return "provider_not_ok"
    observed = provider.get("observed_model")
    if observed != requested_model:
        return "model_mismatch"
    observed_provider = provider.get("observed_provider_id")
    observed_model_id = provider.get("observed_model_id")
    if "/" in requested_model:
        expected_provider, expected_model = requested_model.split("/", 1)
        if observed_provider != expected_provider or observed_model_id != expected_model:
            return "provider_mismatch"
    model = provider.get("session_id")
    if isinstance(model, bool) or not isinstance(model, str) or not model.strip():
        return "unknown_session_provenance"
    if provider.get("identity_source") != IDENTITY_SOURCE:
        return "unknown_identity_source"
    if provider.get("finish") != REQUIRED_FINISH:
        return "unfinished_response"
    attempts = provider.get("attempts")
    if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts != 1:
        return "unexpected_attempts"
    return None


def _usage_int(value: Any) -> Optional[int]:
    """Token counts are non-negative integers; bools/subtrees/nonfinite are null."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _bool_or_none(value: Any) -> Optional[bool]:
    return value if isinstance(value, bool) else None


def _normalise_usage(completion: Mapping[str, Any],
                     provider: Mapping[str, Any]) -> Dict[str, Any]:
    """Preserve observed components and a nullable total; never aggregate."""
    components = provider.get("usage_components")
    if not isinstance(components, Mapping):
        components = {}
    safe_components = {name: _usage_int(components.get(name))
                       for name in _USAGE_COMPONENTS}
    response_usage = completion.get("usage")
    if not isinstance(response_usage, Mapping):
        response_usage = {}
    return {
        "provider_components": safe_components,
        "prompt_tokens": _usage_int(response_usage.get("prompt_tokens")),
        "completion_tokens": _usage_int(response_usage.get("completion_tokens")),
        # Nullable: an absent provider total stays null.
        "total_tokens": _usage_int(response_usage.get("total_tokens")),
        "usage_consistent": _bool_or_none(provider.get("usage_consistent")),
        "coverage": ("assistant_message_components_only; auxiliary/CLI calls "
                     "are not included and no total is fabricated"),
    }


def _scalar_ok(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _scalar_mapping(value: Mapping[str, Any], keys: Sequence[str]) -> Dict[str, Any]:
    """Only whitelisted keys and scalar values; nested subtrees are dropped."""
    return {key: value.get(key) for key in keys if _scalar_ok(value.get(key))}


_INVALID = object()


def _finite_number(value: Any) -> Any:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return _INVALID
    if isinstance(value, float) and not math.isfinite(value):
        return _INVALID
    return value


def _control_number_map(value: Any) -> Dict[str, Any]:
    """Only temperature/top_p and only finite numeric values survive."""
    if not isinstance(value, Mapping):
        return {}
    out: Dict[str, Any] = {}
    for name in _ALLOWED_CONTROL_NAMES:
        if name not in value:
            continue
        number = _finite_number(value.get(name))
        if number is not _INVALID:
            out[name] = number
    return out


def _control_names(value: Any) -> List[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [name for name in value
            if isinstance(name, str) and name in _ALLOWED_CONTROL_NAMES]


def _control_mapping(value: Mapping[str, Any]) -> Dict[str, Any]:
    """Project the exact production ``_control_meta`` contract, closed."""
    out: Dict[str, Any] = {}
    if "requested" in value:
        out["requested"] = _control_number_map(value.get("requested"))
    if "configured" in value:
        out["configured"] = _control_number_map(value.get("configured"))
    if isinstance(value.get("applied"), bool):
        out["applied"] = value.get("applied")
    verification = value.get("verification")
    if verification is None or (isinstance(verification, str)
                                and verification in _ALLOWED_VERIFICATIONS):
        out["verification"] = verification
    binding = value.get("binding")
    if binding is None or (isinstance(binding, str)
                           and binding in _ALLOWED_BINDINGS):
        out["binding"] = binding
    if "unsupported" in value:
        out["unsupported"] = _control_names(value.get("unsupported"))
    return out


def normalise_provider(provider: Mapping[str, Any]) -> Dict[str, Any]:
    """Whitelisted provider metadata projection (no unknown subtrees)."""
    out: Dict[str, Any] = {}
    for key in _PROVIDER_SCALARS:
        if key in ("usage_total", "attempts", "failed_attempts"):
            out[key] = _usage_int(provider.get(key))
            continue
        if key == "usage_consistent":
            out[key] = _bool_or_none(provider.get(key))
            continue
        value = provider.get(key)
        if _scalar_ok(value):
            out[key] = value
    capabilities = provider.get("cli_capabilities")
    if isinstance(capabilities, Mapping):
        out["cli_capabilities"] = _scalar_mapping(capabilities,
                                                  _CLI_CAPABILITY_KEYS)
    controls = provider.get("controls")
    if isinstance(controls, Mapping):
        out["controls"] = _control_mapping(controls)
    transport = provider.get("transport")
    if isinstance(transport, Mapping):
        out["transport"] = _scalar_mapping(transport, _TRANSPORT_KEYS)
    preflight = provider.get("agent_preflight")
    if isinstance(preflight, Mapping):
        out["agent_preflight"] = _scalar_mapping(preflight, _PREFLIGHT_KEYS)
    return out


def _assistant_text(completion: Mapping[str, Any]) -> str:
    choices = completion.get("choices")
    if not isinstance(choices, list) or not choices:
        raise CompletionRejected("invalid_completion_shape")
    first = choices[0]
    if not isinstance(first, Mapping):
        raise CompletionRejected("invalid_completion_shape")
    message = first.get("message")
    if not isinstance(message, Mapping):
        raise CompletionRejected("invalid_completion_shape")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise CompletionRejected("empty_assistant_text")
    if message.get("tool_calls"):
        raise CompletionRejected("unexpected_tool_calls")
    return content


def validate_completion(completion: Any, *, requested_model: str,
                        duration_seconds: Optional[float] = None
                        ) -> ValidatedCompletion:
    """Validate one successful completion and return bounded evidence.

    Raises :class:`CompletionRejected` with a constant code. The caller records
    the rejection as a failed observation (never a retry).
    """
    if not isinstance(completion, Mapping):
        raise CompletionRejected("invalid_completion_shape")
    provider = completion.get("_provider")
    if not isinstance(provider, Mapping):
        raise CompletionRejected("provider_metadata_missing")
    reason = _provider_reason(provider, requested_model)
    if reason is not None:
        raise CompletionRejected(reason)
    if completion.get("model") != requested_model:
        raise CompletionRejected("model_mismatch")
    text = _assistant_text(completion)
    usage = _normalise_usage(completion, provider)
    return ValidatedCompletion(
        text=text,
        text_sha256=sha256_text(text),
        duration_seconds=duration_seconds,
        provider=normalise_provider(provider),
        usage=usage,
        model=provider.get("observed_model"),
        session_id=provider.get("session_id"),
        finish=provider.get("finish"),
    )


def provider_failure(exc: BaseException) -> ProviderFailure:
    """Map a provider failure to constant code/attempt/retryable fields."""
    if isinstance(exc, ModelUnavailableError):
        return ProviderFailure(
            code=str(getattr(exc, "code", "provider_unavailable") or
                     "provider_unavailable"),
            attempts=int(getattr(exc, "attempts", 0) or 0),
            failed_attempts=int(getattr(exc, "failed_attempts", 0) or 0),
            retryable=bool(getattr(exc, "retryable", False)),
        )
    return ProviderFailure(code="provider_transport_exception")


def build_evidence(validated: ValidatedCompletion, *,
                   requested_model: str) -> Dict[str, Any]:
    """Derived receipt for persistence (never a raw CLI transcript/export)."""
    return {
        "schema_version": "exp074.provider-receipt.v1",
        "kind": EVIDENCE_KIND,
        "derived": True,
        "raw_cli_transcript_retained": False,
        "raw_session_export_retained": False,
        "source": EVIDENCE_SOURCE,
        "note": ("Normalized provider metadata and the exact assistant text. "
                 "This is not a raw CLI event stream or a raw session export; "
                 "no config, header, secret, error body or reasoning is stored."),
        "requested_model_id": requested_model,
        "response": {
            "model": validated.model,
            "finish": validated.finish,
            "assistant_text_sha256": validated.text_sha256,
            "assistant_text_chars": len(validated.text),
        },
        "provider": validated.provider,
        "usage": validated.usage,
    }


def canonical_evidence_json(evidence: Mapping[str, Any]) -> str:
    return json.dumps(evidence, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)


def evidence_sha256(evidence: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_evidence_json(evidence).encode("utf-8")).hexdigest()
