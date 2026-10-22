"""Explicit, process-local AI model-provider selection.

The production default remains Gemini. The opt-in ``opencode_cli`` mode makes
the existing OpenCode CLI the *model transport* for exactly one process; it does
not enable CLI tools, mutate a global OpenCode config, install anything, or fall
back to Gemini on failure.

Only documented non-secret options are read here. The Gemini API key is never
part of :class:`ProviderConfig` (``main`` reads it separately for the default
transport).
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional

from .errors import ProviderConfigError

PROVIDER_GEMINI = "gemini"
PROVIDER_OPENCODE_CLI = "opencode_cli"
VALID_PROVIDERS = frozenset({PROVIDER_GEMINI, PROVIDER_OPENCODE_CLI})

DEFAULT_GEMINI_MODEL = "gemini-2.5-pro"
DEFAULT_CLI_MODEL = "aibox/ds/deepseek-flash"
DEFAULT_CLI_AGENT = "travel-ai-cli-transport"
# A unique, per-process agent name: it never merges with a user/global agent.
DEFAULT_CLI_TIMEOUT_SECONDS = 120.0
MAX_CLI_TIMEOUT_SECONDS = 600.0
DEFAULT_CLI_MAX_OUTPUT_BYTES = 2_000_000
MAX_CLI_MAX_OUTPUT_BYTES = 16_000_000
DEFAULT_CLI_MAX_PROMPT_CHARS = 200_000
MAX_CLI_MAX_PROMPT_CHARS = 2_000_000
DEFAULT_CLI_MAX_ATTEMPTS = 1
MAX_CLI_MAX_ATTEMPTS = 3
DEFAULT_CLI_MAX_CONCURRENCY = 2
MAX_CLI_MAX_CONCURRENCY = 8
DEFAULT_CLI_PURE = True

# The requested alias is the only identity that is ever *requested*. The
# user-confirmed display identity and the independently unverified upstream
# checkpoint are disclosed separately so they cannot be mistaken for observed
# proof. The working route remains exactly aibox/ds/deepseek-flash.
MODEL_DISPLAY_NAME = "DeepSeek V4.1 Flash"
MODEL_UPSTREAM_VERSION_VERIFIED = False
MODEL_UPSTREAM_NOTE = (
    "requested alias 'aibox/ds/deepseek-flash'; user-confirmed identity "
    "'DeepSeek V4.1 Flash'; independent upstream verification not established")
EVIDENCE_NOTE = (
    "OpenCode stores its CLI session locally. Raw event/export evidence is "
    "written only when AI_CLI_EVIDENCE_DIR is explicitly set (synthetic "
    "verification); no app raw-conversation log is written by default.")


@dataclass(frozen=True)
class ProviderConfig:
    provider: str
    model: str
    cli_executable: Optional[str] = None
    cli_agent: str = DEFAULT_CLI_AGENT
    cli_timeout_seconds: float = DEFAULT_CLI_TIMEOUT_SECONDS
    cli_max_output_bytes: int = DEFAULT_CLI_MAX_OUTPUT_BYTES
    cli_max_prompt_chars: int = DEFAULT_CLI_MAX_PROMPT_CHARS
    cli_max_attempts: int = DEFAULT_CLI_MAX_ATTEMPTS
    cli_max_concurrency: int = DEFAULT_CLI_MAX_CONCURRENCY
    cli_pure: bool = DEFAULT_CLI_PURE
    evidence_dir: Optional[Path] = None

    @property
    def is_cli(self) -> bool:
        return self.provider == PROVIDER_OPENCODE_CLI


def _text(source: Mapping[str, str], name: str, default: str) -> str:
    raw = source.get(name)
    if raw is None:
        return default
    if not isinstance(raw, str) or not raw.strip():
        raise ProviderConfigError("invalid_provider_config",
                                  f"{name} must be a nonblank string.")
    return raw.strip()


def _optional_text(source: Mapping[str, str], name: str) -> Optional[str]:
    raw = source.get(name)
    if raw is None or not str(raw).strip():
        return None
    if not isinstance(raw, str):
        raise ProviderConfigError("invalid_provider_config",
                                  f"{name} must be a string.")
    return raw.strip()


def _bool(source: Mapping[str, str], name: str, default: bool) -> bool:
    raw = source.get(name)
    if raw is None or not str(raw).strip():
        return default
    value = str(raw).strip().lower()
    if value in ("1", "true", "yes", "on"):
        return True
    if value in ("0", "false", "no", "off"):
        return False
    raise ProviderConfigError("invalid_provider_config",
                              f"{name} must be a boolean (true/false).")


def _int(source: Mapping[str, str], name: str, default: int,
         minimum: int, maximum: int) -> int:
    raw = source.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        raise ProviderConfigError("invalid_provider_config",
                                  f"{name} must be an integer.")
    if isinstance(value, bool) or value < minimum or value > maximum:
        raise ProviderConfigError(
            "invalid_provider_config",
            f"{name} must be between {minimum} and {maximum}.")
    return value


def _float(source: Mapping[str, str], name: str, default: float,
           maximum: float) -> float:
    raw = source.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        value = float(str(raw).strip())
    except (TypeError, ValueError):
        raise ProviderConfigError("invalid_provider_config",
                                  f"{name} must be a number.")
    if not math.isfinite(value) or value <= 0 or value > maximum:
        raise ProviderConfigError(
            "invalid_provider_config",
            f"{name} must be finite, > 0 and <= {maximum:g}.")
    return value


def _validate_model(value: str, name: str) -> str:
    if len(value) > 200:
        raise ProviderConfigError("invalid_provider_config",
                                  f"{name} is too long.")
    if any(ch.isspace() or ch in "\x00\r\n" for ch in value):
        raise ProviderConfigError("invalid_provider_config",
                                  f"{name} must not contain whitespace/control "
                                  "characters.")
    if not value.strip("/") or "//" in value:
        raise ProviderConfigError("invalid_provider_config",
                                  f"{name} is not a qualified model id.")
    return value


def load_provider_config(env: Optional[Mapping[str, str]] = None
                         ) -> ProviderConfig:
    """Load and validate the process-local provider selection.

    ``env=None`` reads ``os.environ``; an explicit mapping (including an empty
    one) is authoritative and is never mutated. An unknown provider is always a
    configuration error; CLI-only options are ignored for the Gemini default.
    """
    source: Mapping[str, str] = os.environ if env is None else env
    provider = _text(source, "AI_LLM_PROVIDER", PROVIDER_GEMINI).lower()
    if provider not in VALID_PROVIDERS:
        raise ProviderConfigError(
            "invalid_provider_config",
            "AI_LLM_PROVIDER must be exactly 'gemini' or 'opencode_cli'.")

    gemini_model = _validate_model(
        _text(source, "GEMINI_MODEL", DEFAULT_GEMINI_MODEL), "GEMINI_MODEL")

    if provider == PROVIDER_GEMINI:
        return ProviderConfig(provider=PROVIDER_GEMINI, model=gemini_model)

    model = _validate_model(_text(source, "AI_CLI_MODEL", DEFAULT_CLI_MODEL),
                            "AI_CLI_MODEL")
    agent = _text(source, "AI_CLI_AGENT", DEFAULT_CLI_AGENT)
    if len(agent) > 100 or any(ch.isspace() or ch in "\x00\r\n" for ch in agent):
        raise ProviderConfigError("invalid_provider_config",
                                  "AI_CLI_AGENT must be a short identifier.")

    evidence_raw = _optional_text(source, "AI_CLI_EVIDENCE_DIR")
    evidence_dir = None
    if evidence_raw is not None:
        if "\x00" in evidence_raw:
            raise ProviderConfigError("invalid_provider_config",
                                      "AI_CLI_EVIDENCE_DIR is invalid.")
        evidence_dir = Path(evidence_raw)

    return ProviderConfig(
        provider=PROVIDER_OPENCODE_CLI,
        model=model,
        cli_executable=_optional_text(source, "AI_CLI_EXECUTABLE"),
        cli_agent=agent,
        cli_timeout_seconds=_float(source, "AI_CLI_TIMEOUT_SECONDS",
                                   DEFAULT_CLI_TIMEOUT_SECONDS,
                                   MAX_CLI_TIMEOUT_SECONDS),
        cli_max_output_bytes=_int(source, "AI_CLI_MAX_OUTPUT_BYTES",
                                  DEFAULT_CLI_MAX_OUTPUT_BYTES, 1024,
                                  MAX_CLI_MAX_OUTPUT_BYTES),
        cli_max_prompt_chars=_int(source, "AI_CLI_MAX_PROMPT_CHARS",
                                  DEFAULT_CLI_MAX_PROMPT_CHARS, 1024,
                                  MAX_CLI_MAX_PROMPT_CHARS),
        cli_max_attempts=_int(source, "AI_CLI_MAX_ATTEMPTS",
                              DEFAULT_CLI_MAX_ATTEMPTS, 1,
                              MAX_CLI_MAX_ATTEMPTS),
        cli_max_concurrency=_int(source, "AI_CLI_MAX_CONCURRENCY",
                                 DEFAULT_CLI_MAX_CONCURRENCY, 1,
                                 MAX_CLI_MAX_CONCURRENCY),
        cli_pure=_bool(source, "AI_CLI_PURE", DEFAULT_CLI_PURE),
        evidence_dir=evidence_dir,
    )
