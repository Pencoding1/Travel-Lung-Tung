"""OpenCode CLI model transport for the existing AI service (opt-in).

The CLI produces model text only. The AI service remains the sole owner of MCP
tool execution, the deterministic planner and the validator. For tool-enabled
turns the CLI must return a strictly validated JSON envelope; the adapter turns
that envelope into OpenAI-compatible ``tool_calls`` for the existing loop.
Plain router/itinerary JSON and ordinary chat text stay assistant content.

Security/reliability properties:

* every call materialises a fresh, non-secret V2 transport directory with an
  ``opencode.json`` that registers exactly one unique primary agent, a
  text-only ``system`` prompt, ``steps: 1`` and an ordered wildcard
  ``{action: *, resource: *, effect: deny}`` permission set (plus explicit
  native-tool denies). The agent id is also passed with ``--agent`` so the CLI
  refuses to start (before any model call) if the config was not applied;
* both ``run`` and ``session export`` use the installed V2 route with
  ``--standalone`` (a private server), never the background service. The V1
  ``opencode export`` route does not exist in v2.0.32;
* the installed CLI advertises no ``--pure``. Plugin isolation is therefore
  *not* silently lost: when ``AI_CLI_PURE`` is requested the adapter fails
  closed with ``cli_pure_unsupported`` unless the operator explicitly sets
  ``AI_CLI_PURE=false``;
* a bounded ``models --standalone`` readiness probe must list the exact
  requested alias before any prompt is sent; the export must then prove the
  observed agent, alias, single assistant message, finish and text;
* argument arrays + native executables only, a bounded prompt/output/time and
  process-tree cleanup on timeout/overflow; the owned transport directory is
  removed after the call;
* no secret bodies are logged; raw evidence is persisted only when an explicit
  evidence directory is configured.
"""

from __future__ import annotations

import asyncio
import collections
import concurrent.futures
import datetime
import decimal
import hashlib
import ipaddress
import json
import math
import os
import re
import threading
import time
import urllib.parse
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Set, Tuple

from . import cli_runtime, go_credentials, private_server, process
from .config import (DEFAULT_CLI_MODEL, EVIDENCE_NOTE, MODEL_DISPLAY_NAME,
                     MODEL_UPSTREAM_NOTE, MODEL_UPSTREAM_VERSION_VERIFIED,
                     ProviderConfig)
from .errors import ModelUnavailableError
from .events import ParsedStream, parse_event_bytes
from .provenance import ExportError, parse_export_bytes, validate_export

TRANSPORT_SYSTEM_PROMPT = cli_runtime.TRANSPORT_SYSTEM_PROMPT
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_CALL_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_MAX_TOOL_CALLS = 8
_MAX_ARGUMENT_CHARS = 200_000
_MAX_SCHEMA_DEPTH = 32
_MAX_SCHEMA_NODES = 4096
_MAX_TEMPERATURE = 2.0
_MAX_TOP_P = 1.0
_CLEANUP_WAIT_SECONDS = (process.CLEANUP_TIMEOUT_SECONDS * 2) + 2.0
_CAPABILITY_TIMEOUT_SECONDS = 20.0
_CAPABILITY_MAX_OUTPUT_BYTES = 262_144
_PROBE_VERSION_ARGS = ("--version",)
_PROBE_RUN_HELP_ARGS = ("run", "--help")
_PROBE_EXPORT_HELP_ARGS = ("session", "export", "--help")
_MODELS_ARGS = ("models", "--standalone")
_PURE_FLAG_RE = re.compile(r"(?<![\w-])--pure(?![\w-])")
_VERSION_RE = re.compile(r"\bv?(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.\-]+)?)")
_SUPPORTED_PAYLOAD_KEYS = frozenset({
    "model", "messages", "tools", "response_format", "temperature", "top_p",
})

# Service-only secrets are removed from the CLI child environment. Provider
# credentials managed by the CLI itself (for the selected alias) are untouched.
_SANITIZED_ENV_KEYS = cli_runtime.SANITIZED_ENV_KEYS

run_command_type = Callable[..., process.CommandResult]
# Production seam for the owned private server. Unit tests inject a fake through
# the constructor (or the hermetic conftest fixture); the default always starts
# the real installed CLI.
default_private_server_factory = private_server.default_server_factory


def agent_config_content(agent_name: str, *,
                         temperature: Optional[float] = None,
                         top_p: Optional[float] = None,
                         model: str = DEFAULT_CLI_MODEL) -> str:
    """Serialise the per-call V2 config (compatibility helper for callers).

    The agent name/model are only used to build the document; the deny-only
    agent, text-only system prompt and single-step bound are fixed.
    """
    config = ProviderConfig(provider="opencode_cli", model=model,
                            cli_agent=agent_name)
    controls: Dict[str, float] = {}
    if temperature is not None:
        controls["temperature"] = _finite_control(
            {"temperature": temperature}, "temperature", _MAX_TEMPERATURE)
    if top_p is not None:
        controls["top_p"] = _finite_control(
            {"top_p": top_p}, "top_p", _MAX_TOP_P)
    return cli_runtime.transport_config_text(config, controls)


def child_environment(config: ProviderConfig,
                      base: Optional[Mapping[str, str]] = None) -> Dict[str, str]:
    """Sanitised child environment for one CLI invocation.

    The per-call config is a *file* in the owned transport directory; an ambient
    inline ``OPENCODE_CONFIG_CONTENT`` is preserved for the guard check. Only
    the exact Go alias receives the named credential, and only in this child
    mapping. The value is not copied into config, metadata, argv or evidence.
    """
    env = cli_runtime.child_environment(config, base)
    if go_credentials.is_go_model(getattr(config, "model", None)):
        try:
            key = (go_credentials.load_go_api_key(environ=base)
                   if base is not None else go_credentials.load_go_api_key())
        except go_credentials.GoCredentialError as exc:
            raise ModelUnavailableError(
                exc.code,
                "The Go API credential is unavailable; no model call was made."
            ) from exc
        env[go_credentials.GO_ENV_VAR] = key
    else:
        # Do not leak the Go credential into an AIbox or other transport child.
        env.pop(go_credentials.GO_ENV_VAR, None)
    return env


def _finite_control(payload: Mapping[str, Any], name: str,
                    maximum: float) -> Optional[float]:
    if name not in payload or payload.get(name) is None:
        return None
    value = payload.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ModelUnavailableError(
            "invalid_sampling_control",
            f"The '{name}' control must be a finite number.")
    try:
        number = float(value)
    except (OverflowError, ValueError):
        raise ModelUnavailableError(
            "invalid_sampling_control",
            f"The '{name}' control is outside the supported finite range.")
    if not math.isfinite(number) or number < 0 or number > maximum:
        raise ModelUnavailableError(
            "invalid_sampling_control",
            f"The '{name}' control is outside the supported finite range.")
    return number


def extract_model_controls(payload: Mapping[str, Any]) -> Dict[str, float]:
    """Validate and copy the controls the CLI transport can actually enforce.

    Temperature/top_p are documented per-agent controls. Token caps and other
    provider options have no portable local guarantee, so an explicit request
    for them fails before model invocation instead of being silently ignored.
    """
    unsupported = sorted(set(payload) - _SUPPORTED_PAYLOAD_KEYS)
    if unsupported:
        raise ModelUnavailableError(
            "unsupported_model_control",
            "The payload includes a model control the CLI transport cannot "
            "enforce; no model call was made.")
    controls: Dict[str, float] = {}
    temperature = _finite_control(payload, "temperature", _MAX_TEMPERATURE)
    if temperature is not None:
        controls["temperature"] = temperature
    top_p = _finite_control(payload, "top_p", _MAX_TOP_P)
    if top_p is not None:
        controls["top_p"] = top_p
    return controls


def build_run_argv(executable: str, config: ProviderConfig, prompt: str,
                   *, cli_supports_pure: bool = False,
                   server_url: Optional[str] = None,
                   prompt_file: Optional[Path] = None) -> List[str]:
    """Build the bounded ``run --server`` argv for the owned private server."""
    return cli_runtime.build_run_argv(executable, config, prompt,
                                      cli_supports_pure=cli_supports_pure,
                                      server_url=server_url,
                                      prompt_file=prompt_file)


def build_export_argv(executable: str, session_id: str, *,
                      standalone: bool = True,
                      server_url: Optional[str] = None) -> List[str]:
    """Build the installed V2 export argv (owned server when provided).

    The installed CLI has no top-level ``export``; the read-only route is
    ``opencode session export --server <url> <session>``.
    """
    try:
        return cli_runtime.build_export_argv(executable, session_id,
                                             standalone=standalone,
                                             server_url=server_url)
    except ValueError:
        raise ModelUnavailableError("invalid_session_id",
                                    "The observed CLI session id is invalid.")


# ---------------------------------------------------------------------------
# CLI capability detection (flag availability is never assumed)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CliCapabilities:
    """What the installed CLI was observed to support.

    ``source`` is ``help_probe`` when the help texts were read successfully,
    ``probe_failed`` when they could not be trusted, and ``not_probed`` when no
    probe was performed. Flag support is only ever inferred from a clean help
    text: an unknown flag can therefore never kill a run.
    """

    version: Optional[str]
    supports_pure: bool
    source: str
    reason: str
    supports_standalone: bool = False
    supports_agent_flag: bool = False
    supports_format_json: bool = False
    supports_session_export: bool = False
    supports_standalone_export: bool = False
    supports_server: bool = False
    supports_server_export: bool = False

    @property
    def runtime_ready(self) -> bool:
        """All flags the owned-server transport requires for a fail-closed call."""
        return (self.supports_server and self.supports_agent_flag
                and self.supports_format_json and self.supports_session_export
                and self.supports_server_export)


# Module-level default probe runner. It is a seam (like ``runner`` and
# ``export_runner``) so tests never launch a real CLI.
capability_probe_runner: run_command_type = process.run_command

_CAPABILITY_CACHE: Dict[str, CliCapabilities] = {}
_CAPABILITY_LOCK = threading.Lock()


def reset_capability_cache() -> None:
    """Drop cached probes (tests, and after the CLI is reinstalled)."""
    with _CAPABILITY_LOCK:
        _CAPABILITY_CACHE.clear()


def _probe_result(executable: str, args: Tuple[str, ...],
                  probe_runner: run_command_type, env: Dict[str, str],
                  cwd: Optional[Path]) -> Optional[process.CommandResult]:
    """Run one bounded, shell-free capability probe; never raises."""
    try:
        return probe_runner(
            [executable, *args],
            cwd=Path(cwd) if cwd is not None else Path.cwd(),
            timeout=_CAPABILITY_TIMEOUT_SECONDS,
            env=env,
            max_output_bytes=_CAPABILITY_MAX_OUTPUT_BYTES)
    except Exception:  # noqa: BLE001 - a probe failure must never abort a run
        return None


def _probe_text(result: Optional[process.CommandResult]) -> Optional[str]:
    if result is None or result.timed_out or result.output_overflow:
        return None
    if result.exit_code != 0:
        return None
    text = result.stdout.decode("utf-8", "replace")
    if not text.strip():
        text = result.stderr.decode("utf-8", "replace")
    return text or None


def cli_version_text(result: Optional[process.CommandResult]) -> Optional[str]:
    text = _probe_text(result)
    if text is None:
        return None
    first = text.strip().splitlines()[0].strip() if text.strip() else ""
    if not first or _VERSION_RE.search(first) is None:
        return None
    return first[:64]


def help_advertises_pure(text: Optional[str]) -> bool:
    """True only when a successfully read help text lists the ``--pure`` flag."""
    if not text:
        return False
    return _PURE_FLAG_RE.search(text) is not None


def probe_cli_capabilities(executable: str, config: ProviderConfig,
                           *, cwd: Optional[Path] = None,
                           runner: Optional[run_command_type] = None
                           ) -> CliCapabilities:
    """Read ``--version``, ``run --help`` and ``session export --help`` once.

    The probe is a local, bounded, shell-free subprocess with no prompt and no
    model invocation. Anything other than a clean, readable help text is
    reported as ``probe_failed`` and every flag is treated as unsupported.
    """
    probe_runner = runner or capability_probe_runner
    try:
        env = child_environment(config)
    except Exception:  # noqa: BLE001 - env building is not a capability fact
        env = {key: value for key, value in os.environ.items()}

    version = cli_version_text(_probe_result(
        executable, _PROBE_VERSION_ARGS, probe_runner, env, cwd))
    run_help = _probe_text(_probe_result(
        executable, _PROBE_RUN_HELP_ARGS, probe_runner, env, cwd))
    export_help = _probe_text(_probe_result(
        executable, _PROBE_EXPORT_HELP_ARGS, probe_runner, env, cwd))

    run_flags = cli_runtime.advertised_flags(run_help)
    export_flags = cli_runtime.advertised_flags(export_help)
    if run_help is None or export_help is None:
        missing = []
        if run_help is None:
            missing.append("run_help_unavailable")
        if export_help is None:
            missing.append("session_export_help_unavailable")
        return CliCapabilities(
            version=version, supports_pure=False, source="probe_failed",
            reason="+".join(missing),
            supports_standalone="--standalone" in run_flags,
            supports_agent_flag="--agent" in run_flags,
            supports_format_json="--format" in run_flags,
            supports_session_export=bool(export_flags),
            supports_standalone_export="--standalone" in export_flags,
            supports_server="--server" in run_flags,
            supports_server_export="--server" in export_flags)

    supported = help_advertises_pure(run_help)
    return CliCapabilities(
        version=version, supports_pure=supported, source="help_probe",
        reason="supported" if supported else "unsupported",
        supports_standalone="--standalone" in run_flags,
        supports_agent_flag="--agent" in run_flags,
        supports_format_json="--format" in run_flags,
        supports_session_export=True,
        supports_standalone_export="--standalone" in export_flags,
        supports_server="--server" in run_flags,
        supports_server_export="--server" in export_flags)


def capabilities_for(executable: str, config: ProviderConfig,
                     *, cwd: Optional[Path] = None,
                     runner: Optional[run_command_type] = None) -> CliCapabilities:
    """Cached (per process, per executable) capability lookup."""
    with _CAPABILITY_LOCK:
        cached = _CAPABILITY_CACHE.get(executable)
        if cached is not None:
            return cached
        result = probe_cli_capabilities(executable, config, cwd=cwd, runner=runner)
        _CAPABILITY_CACHE[executable] = result
        return result


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if content is None:
        return ""
    try:
        return json.dumps(content, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return str(content)


def _render_tool_calls(tool_calls: Any) -> str:
    if not isinstance(tool_calls, list):
        return ""
    rendered: List[Dict[str, Any]] = []
    for call in tool_calls:
        if not isinstance(call, dict):
            continue
        function = call.get("function")
        if not isinstance(function, dict):
            continue
        rendered.append({
            "id": call.get("id"),
            "name": function.get("name"),
            "arguments": function.get("arguments"),
        })
    return ("\n[ASSISTANT TOOL CALLS]\n"
            + json.dumps(rendered, ensure_ascii=False, separators=(",", ":")))


def _tool_spec_map(tools: Any) -> Dict[str, Dict[str, Any]]:
    specs: Dict[str, Dict[str, Any]] = {}
    if not isinstance(tools, list):
        return specs
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        function = tool.get("function")
        if not isinstance(function, dict):
            continue
        name = function.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        if name in specs:
            raise ModelUnavailableError("invalid_tool_schema",
                                        "Available tool names are ambiguous.")
        specs[name] = function
    return specs


def build_prompt(payload: Mapping[str, Any]) -> str:
    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages:
        raise ModelUnavailableError("invalid_prompt",
                                    "The model payload has no messages.")
    system_parts: List[str] = []
    conversation: List[str] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        content = _content_text(message.get("content"))
        if role == "system":
            if content.strip():
                system_parts.append(content)
        elif role == "user":
            conversation.append(f"[USER]\n{content}")
        elif role == "assistant":
            block = f"[ASSISTANT]\n{content}"
            block += _render_tool_calls(message.get("tool_calls"))
            conversation.append(block)
        elif role == "tool":
            name = message.get("name") or "tool"
            call_id = message.get("tool_call_id") or "unknown"
            conversation.append(
                f"[TOOL RESULT id={call_id} name={name}]\n{content}")
        else:
            conversation.append(f"[{str(role).upper()}]\n{content}")

    sections: List[str] = []
    if system_parts:
        sections.append("SYSTEM INSTRUCTIONS:\n" + "\n\n".join(system_parts))
    if conversation:
        sections.append("CONVERSATION:\n" + "\n\n".join(conversation))

    tools = payload.get("tools")
    tool_specs = _tool_spec_map(tools)
    if tool_specs:
        sections.append(
            "SERVER TOOL PROTOCOL (tools are executed only by the server; you "
            "cannot execute them):\n"
            "Available tool schemas:\n"
            + json.dumps(list(tool_specs.values()), ensure_ascii=False,
                         separators=(",", ":"))
            + "\nTo request one or more tool calls, return ONLY a JSON object "
              'with this exact shape: {"tool_calls":[{"id":"call_1",'
              '"name":"<available tool>","arguments":{}}]}\n'
              "Call ids must be unique and contain only letters, digits, '-' or "
              "'_'. Arguments must be a JSON object matching the tool schema. "
              "To answer, return plain text or ONLY "
              '{"content":"<final answer>"}. Do not return both.')

    response_format = payload.get("response_format")
    if isinstance(response_format, dict) and response_format.get("type") == "json_object":
        sections.append("Return ONLY one valid JSON object. Do not use markdown "
                        "fences and do not add commentary.")
    else:
        sections.append("Respond now with only the requested assistant output.")

    return "\n\n".join(sections)


def _strip_single_fence(text: str) -> Optional[str]:
    match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text.strip(), re.DOTALL)
    return match.group(1).strip() if match else None


class _ArgumentInvalid(ValueError):
    """Internal branch failure (invalid instance against a valid schema)."""


class _SchemaUnsupported(ValueError):
    """The supplied schema uses a keyword this validator cannot enforce."""


_KNOWN_SCHEMA_KEYWORDS = frozenset({
    "$ref", "$defs", "definitions", "$schema", "$id", "$anchor", "$comment",
    "title", "description", "default", "examples", "example", "deprecated",
    "readOnly", "writeOnly", "xml", "externalDocs",
    "type", "enum", "const", "nullable",
    "properties", "required", "additionalProperties", "minProperties",
    "maxProperties",
    "items", "prefixItems", "minItems", "maxItems", "uniqueItems",
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
    "minLength", "maxLength", "pattern", "format",
    "allOf", "anyOf", "oneOf",
})


def _json_norm(value: Any, *, depth: int = 0) -> Any:
    if depth > _MAX_SCHEMA_DEPTH:
        raise _SchemaUnsupported("value hierarchy exceeds the validation bound")
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, (int, float)):
        return ("number", float(value) if isinstance(value, float) else value)
    if isinstance(value, str):
        return ("string", value)
    if value is None:
        return ("null",)
    if isinstance(value, list):
        return ("array", tuple(_json_norm(item, depth=depth + 1) for item in value))
    if isinstance(value, dict):
        return ("object", tuple(sorted(
            (key, _json_norm(item, depth=depth + 1))
            for key, item in value.items())))
    return ("unknown", repr(value))


def _json_equal(left: Any, right: Any) -> bool:
    return _json_norm(left) == _json_norm(right)


def _check_finite(value: Any, *, depth: int = 0) -> None:
    if depth > _MAX_SCHEMA_DEPTH:
        raise _ArgumentInvalid("arguments exceed the validation depth bound")
    if isinstance(value, float):
        if not math.isfinite(value):
            raise _ArgumentInvalid("non-finite numeric argument")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise _ArgumentInvalid("object keys must be strings")
            _check_finite(item, depth=depth + 1)
        return
    if isinstance(value, list):
        for item in value:
            _check_finite(item, depth=depth + 1)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_finite_number(value: Any) -> bool:
    return _is_number(value) and (isinstance(value, int) or math.isfinite(value))


def _type_matches(value: Any, name: str) -> bool:
    if name == "object":
        return isinstance(value, dict)
    if name == "array":
        return isinstance(value, list)
    if name == "string":
        return isinstance(value, str)
    if name == "number":
        return (_is_number(value)
                and (isinstance(value, int) or math.isfinite(value)))
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "boolean":
        return isinstance(value, bool)
    if name == "null":
        return value is None
    raise _SchemaUnsupported("unknown JSON type")


class _ArgumentValidator:
    """Recursive validator for the JSON-Schema subset used by server tools."""

    def __init__(self, root: Any):
        self.root = root
        self.nodes = 0

    def validate(self, value: Any, schema: Any, *,
                 ref_stack: frozenset = frozenset(),
                 depth: int = 0) -> None:
        self.nodes += 1
        if self.nodes > _MAX_SCHEMA_NODES or depth > _MAX_SCHEMA_DEPTH:
            raise _SchemaUnsupported("schema exceeds the validation bound")
        if schema is True:
            return
        if schema is False:
            raise _ArgumentInvalid("schema rejects every value")
        if not isinstance(schema, dict):
            raise _SchemaUnsupported("schema must be an object or boolean")

        unknown = set(schema) - _KNOWN_SCHEMA_KEYWORDS
        if unknown:
            raise _SchemaUnsupported("unsupported validation keyword")

        ref = schema.get("$ref")
        if ref is not None:
            if not isinstance(ref, str):
                raise _SchemaUnsupported("invalid $ref")
            if ref in ref_stack:
                raise _SchemaUnsupported("recursive $ref")
            self.validate(value, self._resolve_ref(ref),
                          ref_stack=ref_stack | {ref}, depth=depth + 1)

        nullable = schema.get("nullable") is True
        if nullable and value is None:
            return

        if "const" in schema and not _json_equal(value, schema["const"]):
            raise _ArgumentInvalid("const mismatch")
        if "enum" in schema:
            enum = schema["enum"]
            if not isinstance(enum, list):
                raise _SchemaUnsupported("enum must be a list")
            if not any(_json_equal(value, item) for item in enum):
                raise _ArgumentInvalid("enum mismatch")

        for key in ("allOf", "anyOf", "oneOf"):
            if key not in schema:
                continue
            branches = schema[key]
            if not isinstance(branches, list) or not branches:
                raise _SchemaUnsupported(f"{key} must be a nonempty list")
            if key == "allOf":
                for branch in branches:
                    self.validate(value, branch, ref_stack=ref_stack,
                                  depth=depth + 1)
                continue
            matches = 0
            for branch in branches:
                try:
                    self.validate(value, branch, ref_stack=ref_stack,
                                  depth=depth + 1)
                    matches += 1
                except _ArgumentInvalid:
                    continue
            if (key == "anyOf" and matches == 0) or (key == "oneOf" and matches != 1):
                raise _ArgumentInvalid(f"{key} mismatch")

        expected_type = schema.get("type")
        if expected_type is not None:
            names = expected_type if isinstance(expected_type, list) else [expected_type]
            if not names or not all(isinstance(name, str) for name in names):
                raise _SchemaUnsupported("invalid type declaration")
            if not any(_type_matches(value, name) for name in names):
                raise _ArgumentInvalid("type mismatch")

        if isinstance(value, dict):
            self._validate_object(value, schema, ref_stack, depth)
        if isinstance(value, list):
            self._validate_array(value, schema, ref_stack, depth)
        if isinstance(value, str):
            self._validate_string(value, schema)
        if _is_number(value):
            self._validate_number(value, schema)

    def _resolve_ref(self, ref: str) -> Any:
        if ref in ("#", ""):
            return self.root
        if not ref.startswith("#/"):
            raise _SchemaUnsupported("only local $ref values are supported")
        node = self.root
        for raw in ref[2:].split("/"):
            token = urllib.parse.unquote(raw).replace("~1", "/").replace("~0", "~")
            if isinstance(node, dict) and token in node:
                node = node[token]
            elif isinstance(node, list) and token.isdigit() and int(token) < len(node):
                node = node[int(token)]
            else:
                raise _SchemaUnsupported("unresolvable local $ref")
        return node

    def _validate_object(self, value: Dict[str, Any], schema: Mapping[str, Any],
                         ref_stack: frozenset, depth: int) -> None:
        required = schema.get("required")
        if required is not None:
            if not isinstance(required, list) or not all(
                    isinstance(key, str) for key in required):
                raise _SchemaUnsupported("required must be a string list")
            for key in required:
                if key not in value:
                    raise _ArgumentInvalid("missing required property")
        properties = schema.get("properties")
        if properties is not None and not isinstance(properties, dict):
            raise _SchemaUnsupported("properties must be an object")
        properties = properties or {}
        additional = schema.get("additionalProperties", True)
        for key, item in value.items():
            if key in properties:
                self.validate(item, properties[key], ref_stack=ref_stack,
                              depth=depth + 1)
            elif additional is False:
                raise _ArgumentInvalid("unexpected property")
            elif isinstance(additional, (dict, bool)):
                self.validate(item, additional, ref_stack=ref_stack,
                              depth=depth + 1)
            else:
                raise _SchemaUnsupported("invalid additionalProperties")
        if "minProperties" in schema or "maxProperties" in schema:
            count = len(value)
            for key, ok in (
                    ("minProperties", count >= schema.get("minProperties", count)),
                    ("maxProperties", count <= schema.get("maxProperties", count))):
                if key in schema and (isinstance(schema[key], bool)
                                      or not isinstance(schema[key], int)):
                    raise _SchemaUnsupported(f"invalid {key}")
                if not ok:
                    raise _ArgumentInvalid(f"{key} mismatch")

    def _validate_array(self, value: List[Any], schema: Mapping[str, Any],
                        ref_stack: frozenset, depth: int) -> None:
        for key in ("minItems", "maxItems"):
            if key in schema:
                bound = schema[key]
                if isinstance(bound, bool) or not isinstance(bound, int) or bound < 0:
                    raise _SchemaUnsupported(f"invalid {key}")
                if key == "minItems" and len(value) < bound:
                    raise _ArgumentInvalid("minItems mismatch")
                if key == "maxItems" and len(value) > bound:
                    raise _ArgumentInvalid("maxItems mismatch")
        if schema.get("uniqueItems") is True:
            seen: Set[str] = set()
            for item in value:
                key = repr(_json_norm(item))
                if key in seen:
                    raise _ArgumentInvalid("duplicate array item")
                seen.add(key)
        elif "uniqueItems" in schema and not isinstance(schema["uniqueItems"], bool):
            raise _SchemaUnsupported("invalid uniqueItems")

        start = 0
        prefix = schema.get("prefixItems")
        if prefix is not None:
            if not isinstance(prefix, list):
                raise _SchemaUnsupported("prefixItems must be a list")
            for index, item_schema in enumerate(prefix):
                if index < len(value):
                    self.validate(value[index], item_schema,
                                  ref_stack=ref_stack, depth=depth + 1)
            start = len(prefix)

        items = schema.get("items")
        if items is not None:
            if isinstance(items, list):
                for index, item_schema in enumerate(items):
                    if index < len(value):
                        self.validate(value[index], item_schema,
                                      ref_stack=ref_stack, depth=depth + 1)
                # Draft-4 additionalItems is intentionally unsupported.
                if "additionalItems" in schema:
                    raise _SchemaUnsupported("additionalItems is unsupported")
            elif isinstance(items, (dict, bool)):
                for item in value[start:]:
                    self.validate(item, items, ref_stack=ref_stack,
                                  depth=depth + 1)
            else:
                raise _SchemaUnsupported("invalid items")

    def _validate_string(self, value: str, schema: Mapping[str, Any]) -> None:
        for key, ok in (
                ("minLength", len(value) >= schema.get("minLength", len(value))),
                ("maxLength", len(value) <= schema.get("maxLength", len(value)))):
            if key in schema:
                bound = schema[key]
                if isinstance(bound, bool) or not isinstance(bound, int) or bound < 0:
                    raise _SchemaUnsupported(f"invalid {key}")
                if not ok:
                    raise _ArgumentInvalid(f"{key} mismatch")
        if "pattern" in schema:
            pattern = schema["pattern"]
            if not isinstance(pattern, str) or len(pattern) > 1000:
                raise _SchemaUnsupported("invalid pattern")
            try:
                if re.search(pattern, value) is None:
                    raise _ArgumentInvalid("pattern mismatch")
            except re.error:
                raise _SchemaUnsupported("invalid pattern")
        fmt = schema.get("format")
        if fmt is None or not isinstance(fmt, str):
            if fmt is not None:
                raise _SchemaUnsupported("invalid format")
            return
        try:
            if fmt == "date-time":
                parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    raise ValueError("missing offset")
            elif fmt == "date":
                datetime.date.fromisoformat(value)
            elif fmt == "time":
                parsed_time = datetime.time.fromisoformat(value.replace("Z", "+00:00"))
                if parsed_time.tzinfo is None:
                    raise ValueError("missing offset")
            elif fmt == "email":
                if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value) is None:
                    raise ValueError("invalid email")
            elif fmt == "uuid":
                uuid.UUID(value)
            elif fmt == "ipv4":
                if ipaddress.ip_address(value).version != 4:
                    raise ValueError("not ipv4")
            elif fmt == "ipv6":
                if ipaddress.ip_address(value).version != 6:
                    raise ValueError("not ipv6")
            elif fmt in ("uri", "uri-reference"):
                parsed_uri = urllib.parse.urlsplit(value)
                if fmt == "uri" and not parsed_uri.scheme:
                    raise ValueError("missing scheme")
            elif fmt == "hostname":
                if len(value) > 253 or re.fullmatch(
                        r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", value) is None:
                    raise ValueError("invalid hostname")
            elif fmt in ("int32", "int64", "float", "double"):
                pass  # numeric formats are covered by type/bounds
            else:
                raise _SchemaUnsupported("unsupported string format")
        except (ValueError, TypeError):
            raise _ArgumentInvalid("format mismatch")

    def _validate_number(self, value: Any, schema: Mapping[str, Any]) -> None:
        if isinstance(value, float):
            if not math.isfinite(value):
                raise _ArgumentInvalid("non-finite number")
            number: Any = value
        else:
            number = value
        if "minimum" in schema:
            bound = schema["minimum"]
            if not _is_finite_number(bound):
                raise _SchemaUnsupported("invalid minimum")
            exclusive = schema.get("exclusiveMinimum") is True
            if exclusive:
                if number <= bound:
                    raise _ArgumentInvalid("minimum mismatch")
            elif number < bound:
                raise _ArgumentInvalid("minimum mismatch")
        if "maximum" in schema:
            bound = schema["maximum"]
            if not _is_finite_number(bound):
                raise _SchemaUnsupported("invalid maximum")
            exclusive = schema.get("exclusiveMaximum") is True
            if exclusive:
                if number >= bound:
                    raise _ArgumentInvalid("maximum mismatch")
            elif number > bound:
                raise _ArgumentInvalid("maximum mismatch")
        for key, comparison in (
                ("exclusiveMinimum", lambda a, b: a <= b),
                ("exclusiveMaximum", lambda a, b: a >= b)):
            bound = schema.get(key)
            if bound is None or isinstance(bound, bool):
                continue
            if not _is_finite_number(bound):
                raise _SchemaUnsupported(f"invalid {key}")
            if comparison(number, bound):
                raise _ArgumentInvalid(f"{key} mismatch")
        if "multipleOf" in schema:
            multiple = schema["multipleOf"]
            if not _is_finite_number(multiple) or multiple <= 0:
                raise _SchemaUnsupported("invalid multipleOf")
            try:
                left = (decimal.Decimal(number) if isinstance(number, int)
                        else decimal.Decimal(str(number)))
                right = decimal.Decimal(str(multiple))
                quotient = left / right
            except (decimal.InvalidOperation, decimal.DivisionByZero):
                raise _ArgumentInvalid("multipleOf mismatch")
            if quotient != quotient.to_integral_value():
                raise _ArgumentInvalid("multipleOf mismatch")
        fmt = schema.get("format")
        if fmt == "int32" and not (-(2 ** 31) <= number <= 2 ** 31 - 1):
            raise _ArgumentInvalid("int32 range mismatch")
        if fmt == "int64" and not (-(2 ** 63) <= number <= 2 ** 63 - 1):
            raise _ArgumentInvalid("int64 range mismatch")


def _validate_arguments(schema: Any, arguments: Dict[str, Any]) -> None:
    try:
        _check_finite(arguments)
    except _ArgumentInvalid:
        raise ModelUnavailableError(
            "invalid_tool_arguments",
            "The tool call arguments exceed the validation bound or contain a "
            "non-finite number.")
    try:
        _ArgumentValidator(schema if schema is not None else True).validate(
            arguments, schema if schema is not None else True)
    except _SchemaUnsupported:
        raise ModelUnavailableError(
            "unsupported_tool_schema",
            "The server tool schema uses a validation keyword this adapter "
            "cannot enforce; the call was not executed.")
    except _ArgumentInvalid:
        raise ModelUnavailableError(
            "invalid_tool_arguments",
            "The tool call arguments do not satisfy the server tool schema.")


def _validated_tool_calls(envelope: Any,
                          tool_specs: Mapping[str, Dict[str, Any]]
                          ) -> List[Dict[str, Any]]:
    if not isinstance(envelope, list) or not envelope:
        raise ModelUnavailableError("invalid_tool_envelope",
                                    "The tool-call envelope is empty or invalid.")
    if len(envelope) > _MAX_TOOL_CALLS:
        raise ModelUnavailableError("invalid_tool_envelope",
                                    "The tool-call envelope is too large.")
    calls: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for item in envelope:
        if not isinstance(item, dict) or set(item) != {"id", "name", "arguments"}:
            raise ModelUnavailableError("invalid_tool_envelope",
                                        "A tool call has an invalid shape.")
        call_id = item.get("id")
        name = item.get("name")
        arguments = item.get("arguments")
        if not isinstance(call_id, str) or not _CALL_ID_RE.fullmatch(call_id):
            raise ModelUnavailableError("invalid_tool_call_id",
                                        "A tool call id is invalid.")
        if call_id in seen:
            raise ModelUnavailableError("invalid_tool_call_id",
                                        "Tool call ids must be unique.")
        seen.add(call_id)
        if not isinstance(name, str) or name not in tool_specs:
            raise ModelUnavailableError("unknown_tool",
                                        "A tool call names an unavailable tool.")
        if not isinstance(arguments, dict):
            raise ModelUnavailableError("invalid_tool_arguments",
                                        "Tool call arguments must be an object.")
        encoded = json.dumps(arguments, ensure_ascii=False, separators=(",", ":"))
        if len(encoded) > _MAX_ARGUMENT_CHARS:
            raise ModelUnavailableError("invalid_tool_arguments",
                                        "Tool call arguments are too large.")
        function = tool_specs[name]
        _validate_arguments(function.get("parameters"), arguments)
        calls.append({
            "id": call_id,
            "type": "function",
            "function": {"name": name, "arguments": encoded},
        })
    return calls


class _StrictJsonError(ValueError):
    pass


def _strict_json_loads(text: str) -> Any:
    """Reject duplicate object keys and non-finite JSON constants.

    Python's default decoder silently keeps the last duplicate key and accepts
    ``NaN``/``Infinity``; either could make a validated call differ from what a
    second parser would execute.
    """
    def object_pairs(pairs: List[Tuple[str, Any]]) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise _StrictJsonError("duplicate object key")
            result[key] = value
        return result

    def reject_constant(value: str) -> Any:
        raise _StrictJsonError(f"non-finite JSON constant {value}")

    try:
        return json.loads(text, object_pairs_hook=object_pairs,
                          parse_constant=reject_constant)
    except _StrictJsonError:
        raise ModelUnavailableError(
            "invalid_tool_envelope",
            "The structured assistant output contains duplicate keys or a "
            "non-finite number.")
    except (TypeError, ValueError):
        raise ModelUnavailableError(
            "invalid_tool_envelope",
            "The CLI returned malformed structured output.")


def convert_assistant_output(text: str, payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Translate CLI text into an OpenAI-compatible assistant message."""
    stripped = text.strip()
    if not stripped:
        raise ModelUnavailableError("empty_response",
                                    "The CLI returned no assistant text.")
    tool_specs = _tool_spec_map(payload.get("tools"))
    if not tool_specs:
        return {"role": "assistant", "content": stripped}

    candidate = stripped
    fenced = _strip_single_fence(stripped)
    if fenced is not None:
        candidate = fenced
        looks_structured = True
    else:
        looks_structured = stripped.startswith("{") or stripped.startswith("[")

    if not looks_structured:
        return {"role": "assistant", "content": stripped}

    decoded = _strict_json_loads(candidate)
    if not isinstance(decoded, dict):
        raise ModelUnavailableError("invalid_tool_envelope",
                                    "The structured assistant output must be an object.")
    keys = set(decoded)
    if keys == {"tool_calls"}:
        calls = _validated_tool_calls(decoded.get("tool_calls"), tool_specs)
        return {"role": "assistant", "content": None, "tool_calls": calls}
    if keys == {"content"}:
        content = decoded.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ModelUnavailableError("invalid_tool_envelope",
                                        "The assistant content envelope is empty.")
        return {"role": "assistant", "content": content.strip()}
    raise ModelUnavailableError(
        "invalid_tool_envelope",
        "The assistant envelope has unknown fields; it was not executed.")


def _usage_component(components: Mapping[str, Optional[int]], name: str,
                     ) -> Optional[int]:
    value = components.get(name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ModelUnavailableError(
            "invalid_usage",
            "The provider reported a usage component that is not a "
            "non-negative integer.")
    return value


def openai_usage(components: Mapping[str, Optional[int]]) -> Dict[str, Any]:
    """Map observed components into OpenAI-compatible prompt/completion usage.

    ``prompt`` = input + cache_read + cache_write; ``completion`` = output +
    reasoning. A component the provider did not report counts as 0 in the sum
    (that is the OpenAI meaning of an absent detail) but is still disclosed as
    ``None`` in ``provider_components``, so nothing is hidden or invented. The
    provider total is preserved verbatim (never recomputed); ``usage_consistent``
    records whether the mapped parts add up to it, so a mismatch is observable
    rather than silently corrected.
    """
    inp = _usage_component(components, "input")
    cache_read = _usage_component(components, "cache_read")
    cache_write = _usage_component(components, "cache_write")
    output = _usage_component(components, "output")
    reasoning = _usage_component(components, "reasoning")
    total = _usage_component(components, "total")

    prompt_tokens: Optional[int] = None
    if inp is not None:
        prompt_tokens = inp + (cache_read or 0) + (cache_write or 0)
    completion_tokens: Optional[int] = None
    if output is not None:
        completion_tokens = output + (reasoning or 0)

    consistent: Optional[bool] = None
    if prompt_tokens is not None and completion_tokens is not None and total is not None:
        consistent = prompt_tokens + completion_tokens == total

    usage: Dict[str, Any] = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total,
        "provider_components": {name: components.get(name) for name in (
            "input", "output", "reasoning", "cache_read", "cache_write", "total")},
        "usage_consistent": consistent,
    }
    prompt_details: Dict[str, int] = {}
    if cache_read is not None:
        prompt_details["cached_tokens"] = cache_read
    if cache_write is not None:
        prompt_details["cache_write_tokens"] = cache_write
    if prompt_details:
        usage["prompt_tokens_details"] = prompt_details
    if reasoning is not None:
        usage["completion_tokens_details"] = {"reasoning_tokens": reasoning}
    return usage


def _validate_event_identity(parsed: ParsedStream, requested_model: str) -> None:
    models = {value for value in parsed.observed_model_ids if value}
    if models and models != {requested_model}:
        raise ModelUnavailableError("model_mismatch",
                                    "The CLI event stream reported a different model.")
    providers = {value for value in parsed.observed_provider_ids if value}
    if providers:
        expected_provider = requested_model.split("/", 1)[0]
        if providers != {expected_provider}:
            raise ModelUnavailableError("provider_mismatch",
                                        "The CLI event stream reported a different provider.")


def _safe_meta_base(config: ProviderConfig, prompt: str) -> Dict[str, Any]:
    return {
        "provider": "opencode_cli",
        "requested_model": config.model,
        "display_name": (MODEL_DISPLAY_NAME if config.model == DEFAULT_CLI_MODEL else None),
        "upstream_version_verified": MODEL_UPSTREAM_VERSION_VERIFIED,
        "upstream_note": MODEL_UPSTREAM_NOTE,
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "evidence_note": EVIDENCE_NOTE,
    }


def _capability_meta(config: ProviderConfig, capabilities: CliCapabilities,
                     applied: bool) -> Dict[str, Any]:
    """Disclose the observed CLI capability and what was actually applied."""
    return {
        "cli_capabilities": {
            "version": capabilities.version,
            "capability_source": capabilities.source,
            "pure_supported": capabilities.supports_pure,
            "pure_requested": bool(config.cli_pure),
            "pure_applied": applied,
            "plugin_isolation": ("applied" if applied else
                                 ("unavailable_in_cli_version"
                                  if config.cli_pure else "not_requested")),
            "reason": capabilities.reason,
            "standalone": capabilities.supports_standalone,
            "server": capabilities.supports_server,
            "agent_flag": capabilities.supports_agent_flag,
            "format_json": capabilities.supports_format_json,
            "session_export": capabilities.supports_session_export,
            "standalone_export": capabilities.supports_standalone_export,
            "server_export": capabilities.supports_server_export,
            "stream_format": "v2" if capabilities.supports_server else "unknown",
        }
    }


def _control_meta(controls: Mapping[str, float]) -> Dict[str, Any]:
    """Controls metadata: configured is not the same as observed applied.

    The adapter can bind temperature/top_p to the exact alias through a
    model-scoped provider ``request.body`` overlay, but it cannot observe the
    outbound provider request, so it never claims ``applied``. The local
    compatibility QA (owned loopback provider) is what proves the mechanism.
    """
    return {
        "requested": dict(controls),
        "configured": dict(controls),
        "applied": False,
        "verification": ("not_observable_from_transport"
                         if controls else "no_controls_requested"),
        "binding": ("provider_model_request_body" if controls else None),
        "unsupported": [],
    }


def _transport_meta(paths: Optional[cli_runtime.TransportPaths],
                    readiness: Optional[str], *,
                    agent_id: Optional[str] = None,
                    preflight: Optional[Mapping[str, Any]] = None,
                    server: Optional[Mapping[str, Any]] = None,
                    prompt_input: Optional[Mapping[str, Any]] = None,
                    ) -> Dict[str, Any]:
    meta: Dict[str, Any] = {
        "runtime": "opencode_v2_private_server",
        "readiness_gate": readiness,
    }
    if paths is not None:
        transport = paths.as_meta()
        if prompt_input is not None:
            transport["prompt_input"] = dict(prompt_input)
        meta["transport"] = transport
    if agent_id is not None:
        meta["agent_id"] = agent_id
    if preflight is not None:
        meta["agent_preflight"] = dict(preflight)
    if server is not None:
        meta["owned_server"] = dict(server)
    return meta


class _Waiter:
    __slots__ = ("future",)

    def __init__(self):
        self.future: concurrent.futures.Future = concurrent.futures.Future()


class _AsyncCapacity:
    """A cross-loop bounded capacity with cancel-safe async waiters.

    No worker thread is used for waiting. Async waiters are queued and handed a
    permit by ``release`` through a ``concurrent.futures.Future`` (wrapped in the
    caller's loop). Timeout/cancellation removes the waiter under the same lock,
    so an abandoned waiter can never steal a later permit. The synchronous
    ``acquire``/``release`` methods are retained for diagnostics/probes.
    """

    def __init__(self, limit: int):
        if limit < 1:
            raise ValueError("capacity limit must be positive")
        self._limit = limit
        self._active = 0
        self._waiters: collections.deque[_Waiter] = collections.deque()
        self._lock = threading.Lock()

    def _take_or_wait_locked(self) -> Tuple[bool, Optional[_Waiter]]:
        if self._active < self._limit:
            self._active += 1
            return True, None
        waiter = _Waiter()
        self._waiters.append(waiter)
        return False, waiter

    async def acquire_async(self, timeout: float) -> None:
        with self._lock:
            granted, waiter = self._take_or_wait_locked()
        if granted:
            return
        assert waiter is not None
        wrapped = asyncio.wrap_future(waiter.future)
        try:
            await asyncio.wait_for(asyncio.shield(wrapped), timeout=timeout)
        except asyncio.TimeoutError:
            self._abandon(waiter)
            raise ModelUnavailableError(
                "provider_busy",
                "The CLI provider is at its concurrency limit.")
        except asyncio.CancelledError:
            self._abandon(waiter)
            raise

    def _abandon(self, waiter: _Waiter) -> None:
        with self._lock:
            if waiter.future.done():
                if not waiter.future.cancelled():
                    # A release granted this waiter concurrently; hand the
                    # permit on (or return it to the pool) exactly once.
                    self._release_locked()
                return
            try:
                self._waiters.remove(waiter)
            except ValueError:
                pass
            waiter.future.cancel()

    def _release_locked(self) -> None:
        while self._waiters:
            waiter = self._waiters.popleft()
            if waiter.future.done():
                continue
            try:
                waiter.future.set_result(True)
                return
            except concurrent.futures.InvalidStateError:
                continue
        if self._active > 0:
            self._active -= 1

    def release(self) -> None:
        with self._lock:
            self._release_locked()

    def acquire(self, blocking: bool = True,
                timeout: Optional[float] = None) -> bool:
        """Synchronous diagnostic acquire (not used by the async path)."""
        deadline = None if timeout is None else time.monotonic() + max(0.0, timeout)
        while True:
            with self._lock:
                if self._active < self._limit:
                    self._active += 1
                    return True
            if not blocking:
                return False
            if deadline is not None and time.monotonic() >= deadline:
                return False
            time.sleep(0.01)


class OpenCodeCliProvider:
    """Async model-transport adapter with injectable bounded command runners."""

    def __init__(self, config: ProviderConfig, *,
                 runner: Optional[run_command_type] = None,
                 export_runner: Optional[run_command_type] = None,
                 capability_runner: Optional[run_command_type] = None,
                 server_factory: Optional[Callable[..., Any]] = None,
                 cwd: Optional[Path] = None):
        if not config.is_cli:
            raise ModelUnavailableError("invalid_configuration",
                                        "The CLI adapter requires opencode_cli.")
        self.config = config
        self._runner = runner or process.run_command
        self._export_runner = export_runner or self._runner
        self._capability_runner = capability_runner
        self._server_factory = server_factory or default_private_server_factory
        self._cwd = Path(cwd) if cwd is not None else Path.cwd()
        self._semaphore = _AsyncCapacity(config.cli_max_concurrency)

    async def _acquire(self) -> None:
        await self._semaphore.acquire_async(self.config.cli_timeout_seconds)

    def _release(self) -> None:
        self._semaphore.release()

    async def _capabilities(self, executable: str) -> CliCapabilities:
        """Probe (once per process) what the installed CLI actually supports."""
        return await asyncio.to_thread(
            capabilities_for, executable, self.config,
            cwd=self._cwd, runner=self._capability_runner)

    async def _run(self, argv: List[str], runner: run_command_type,
                   env: Dict[str, str], cwd: Path) -> process.CommandResult:
        cancel_event = threading.Event()

        def invoke() -> process.CommandResult:
            return runner(
                argv, cwd=cwd, timeout=self.config.cli_timeout_seconds,
                env=env, max_output_bytes=self.config.cli_max_output_bytes,
                cancel_event=cancel_event)

        task = asyncio.create_task(asyncio.to_thread(invoke))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            # The permit must stay held until the owned process tree has been
            # stopped (or bounded cleanup has elapsed). The runner observes the
            # cancellation event and performs process-tree termination.
            cancel_event.set()
            try:
                await asyncio.wait_for(asyncio.shield(task),
                                       timeout=_CLEANUP_WAIT_SECONDS)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
            raise

    def _write_evidence(self, call_dir: Path, attempt: int,
                        run_result: process.CommandResult,
                        export_result: Optional[process.CommandResult],
                        meta: Dict[str, Any],
                        paths: Optional[cli_runtime.TransportPaths] = None) -> None:
        try:
            call_dir.mkdir(parents=True, exist_ok=True)
            prefix = f"attempt-{attempt}"
            (call_dir / f"{prefix}.events.jsonl").write_bytes(run_result.stdout)
            (call_dir / f"{prefix}.stderr.txt").write_bytes(run_result.stderr)
            if export_result is not None:
                (call_dir / f"{prefix}.session-export.json").write_bytes(
                    export_result.stdout)
                (call_dir / f"{prefix}.session-export.stderr.txt").write_bytes(
                    export_result.stderr)
            if paths is not None and paths.config.is_file():
                # Non-secret by construction (no credential/env/header/base URL).
                (call_dir / "transport-config.json").write_bytes(
                    paths.config.read_bytes())
            (call_dir / "meta.json").write_text(
                json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError:
            raise ModelUnavailableError(
                "evidence_write_failed",
                "The configured evidence directory could not be written.")

    async def _server_preflight(self, executable: str,
                                paths: cli_runtime.TransportPaths,
                                call_config: ProviderConfig,
                                env: Optional[Mapping[str, str]] = None):
        """Start one owned server and prove the exact agent before any model.

        The start + API polling runs in a worker thread because it is bounded
        blocking I/O. Cancellation never reaches the model: the worker observes
        the cancel event and the caller's ``finally`` still closes the server.
        The same already-resolved child environment is used for readiness,
        run and export so one Go credential snapshot serves the whole call.
        """
        server = self._server_factory(
            executable, paths.workdir,
            child_environment(self.config) if env is None else dict(env),
            timeout=self.config.cli_timeout_seconds)
        cancel_event = threading.Event()

        def work():
            server.start(cancel_event=cancel_event)
            return server.preflight(
                call_config.cli_agent, paths.workdir, call_config.model,
                cancel_event=cancel_event)

        task = asyncio.create_task(asyncio.to_thread(work))
        try:
            proof = await asyncio.shield(task)
        except asyncio.CancelledError:
            cancel_event.set()
            try:
                await asyncio.wait_for(asyncio.shield(task),
                                       timeout=_CLEANUP_WAIT_SECONDS)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
            try:
                server.close()
            finally:
                raise
        except BaseException:
            # The caller never receives the server object, so close it here.
            try:
                server.close()
            finally:
                raise
        return server, proof

    async def complete(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        requested = payload.get("model")
        if isinstance(requested, str) and requested and requested != self.config.model:
            raise ModelUnavailableError(
                "model_config_mismatch",
                "The payload model does not match the selected CLI model.")
        carriers = cli_runtime.ambient_config_carriers()
        if carriers:
            raise ModelUnavailableError(
                "cli_ambient_config_refused",
                "An ambient OpenCode config carrier is set; refusing before "
                "any CLI process. Unset it explicitly for this transport call.")
        controls = extract_model_controls(payload)
        call_config = replace(
            self.config, cli_agent=cli_runtime.per_call_agent(self.config.cli_agent))
        executable = process.resolve_executable(self.config.cli_executable)
        capabilities = await self._capabilities(executable)
        if not capabilities.runtime_ready:
            raise ModelUnavailableError(
                "cli_runtime_unsupported",
                "The installed CLI does not expose the V2 standalone run/export "
                "route this transport requires; no model call was made.")
        if self.config.cli_pure and not capabilities.supports_pure:
            # The installed CLI has no --pure. Omission would silently drop the
            # requested plugin isolation, so this fails closed instead.
            raise ModelUnavailableError(
                "cli_pure_unsupported",
                "AI_CLI_PURE is requested but the installed CLI cannot apply "
                "plugin isolation; set AI_CLI_PURE=false to opt out explicitly.")
        pure_applied = bool(self.config.cli_pure and capabilities.supports_pure)
        prompt = build_prompt(payload)
        if "\x00" in prompt:
            raise ModelUnavailableError("invalid_prompt",
                                        "The translated prompt contains a NUL byte.")
        if len(prompt) > self.config.cli_max_prompt_chars:
            raise ModelUnavailableError("prompt_too_large",
                                        "The translated prompt exceeds the bound.")
        try:
            prompt_utf8_bytes = len(prompt.encode("utf-8"))
        except UnicodeEncodeError:
            raise ModelUnavailableError(
                "invalid_prompt",
                "The translated prompt is not valid UTF-8 text.") from None
        prompt_input: Dict[str, Any] = {
            "kind": "argv",
            "utf8_bytes": prompt_utf8_bytes,
        }

        call_dir = None
        if self.config.evidence_dir is not None:
            stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
            call_dir = self.config.evidence_dir / f"oc040-{stamp}-{uuid.uuid4().hex[:8]}"

        env = child_environment(self.config)
        attempts: List[Dict[str, Any]] = []
        last_error: Optional[ModelUnavailableError] = None

        await self._acquire()
        paths: Optional[cli_runtime.TransportPaths] = None
        server = None
        readiness: Optional[str] = None
        preflight: Optional[Dict[str, Any]] = None
        server_facts: Optional[Dict[str, Any]] = None
        cleanup_facts: Dict[str, Any] = {"status": "pending"}
        try:
            paths = cli_runtime.create_transport(call_config, controls)
            try:
                config_proof = cli_runtime.validate_transport_config(
                    paths, call_config, controls)
            except cli_runtime.TransportConfigError as exc:
                raise ModelUnavailableError(
                    "cli_agent_preflight_failed",
                    "The generated transport agent policy did not match the "
                    "required restrictive contract; no model call was made."
                ) from exc
            try:
                server, engine_proof = await self._server_preflight(
                    executable, paths, call_config, env=env)
            except private_server.AgentProjectionError as exc:
                raise ModelUnavailableError(
                    "cli_agent_preflight_failed",
                    "The owned server did not project the requested transport "
                    "agent at this Location; no model call was made.") from exc
            except private_server.ServerPreflightError as exc:
                raise ModelUnavailableError(
                    "cli_server_preflight_failed",
                    "The owned private server could not be verified; no model "
                    "call was made.") from exc
            readiness = "same_server_agent_projection_verified"
            server_facts = dict(server.facts())
            server_facts["used_for_run"] = False
            server_facts["used_for_export"] = False
            server_facts["cleanup"] = cleanup_facts
            preflight = {
                "status": engine_proof.get("status"),
                "transport_config_status": config_proof.get("status"),
                "config_sha256": config_proof.get("config_sha256"),
                "engine": dict(engine_proof),
            }
            run_env = server.client_env(env)
            prompt_file: Optional[Path] = None
            for attempt in range(1, self.config.cli_max_attempts + 1):
                attempt_meta: Dict[str, Any] = {"attempt": attempt, "ok": False}
                export_result: Optional[process.CommandResult] = None
                run_result: Optional[process.CommandResult] = None
                try:
                    short_argv = build_run_argv(
                        executable, call_config, prompt,
                        cli_supports_pure=capabilities.supports_pure,
                        server_url=server.url)
                    if (process.command_line_utf16_units(short_argv)
                            > process.COMMAND_LINE_SAFE_UTF16_UNITS):
                        prompt_input["kind"] = "file"
                        if prompt_file is None:
                            try:
                                prompt_file = cli_runtime.write_prompt_file(
                                    paths, prompt)
                            except cli_runtime.PromptFileError as exc:
                                raise ModelUnavailableError(
                                    exc.code,
                                    "The exact prompt input could not be "
                                    "prepared inside the owned transport; no "
                                    "model call was made.") from None
                        argv = build_run_argv(
                            executable, call_config, prompt,
                            cli_supports_pure=capabilities.supports_pure,
                            server_url=server.url,
                            prompt_file=prompt_file)
                    else:
                        argv = short_argv
                    process.ensure_command_line_size(argv)
                    run_result = await self._run(argv, self._runner, run_env,
                                                 paths.workdir)
                    server_facts["used_for_run"] = True
                    attempt_meta["exit_code"] = run_result.exit_code
                    attempt_meta["pure_applied"] = pure_applied
                    attempt_meta["cli_version"] = capabilities.version
                    attempt_meta["timed_out"] = run_result.timed_out
                    attempt_meta["output_overflow"] = run_result.output_overflow
                    attempt_meta["duration_seconds"] = round(
                        run_result.duration_seconds, 3)
                    if run_result.cancelled:
                        raise ModelUnavailableError("cli_cancelled",
                                                    "The CLI call was cancelled.")
                    if run_result.timed_out:
                        raise ModelUnavailableError("cli_timeout",
                                                    "The CLI call timed out.",
                                                    retryable=True)
                    if run_result.output_overflow:
                        raise ModelUnavailableError("cli_output_overflow",
                                                    "The CLI output exceeded the bound.",
                                                    retryable=True)
                    if run_result.exit_code != 0:
                        if (b"Agent not found" in run_result.stdout
                                or b"Agent not found" in run_result.stderr):
                            raise ModelUnavailableError(
                                "cli_agent_unavailable",
                                "The installed CLI did not register the deny-only "
                                "transport agent; no model call completed.")
                        raise ModelUnavailableError("cli_nonzero_exit",
                                                    "The CLI exited unsuccessfully.",
                                                    retryable=True)

                    parsed = parse_event_bytes(run_result.stdout)
                    if parsed.malformed_lines:
                        raise ModelUnavailableError("cli_malformed_stream",
                                                    "The CLI event stream was malformed.",
                                                    retryable=True)
                    if parsed.tool_use_count:
                        raise ModelUnavailableError(
                            "cli_tool_use_denied",
                            "The CLI attempted a native tool action; it was denied.")
                    if parsed.error_count:
                        raise ModelUnavailableError("cli_error_event",
                                                    "The CLI reported an error event.",
                                                    retryable=True)
                    if not parsed.terminal_present:
                        raise ModelUnavailableError(
                            "unfinished_response",
                            "The CLI response did not finish successfully.",
                            retryable=True)
                    _validate_event_identity(parsed, self.config.model)
                    session_id = parsed.session_id
                    if not session_id:
                        raise ModelUnavailableError(
                            "unknown_session_provenance",
                            "The CLI response did not identify exactly one session.",
                            retryable=True)
                    if len({value for value in parsed.assistant_message_ids if value}) != 1:
                        raise ModelUnavailableError(
                            "ambiguous_assistant_identity",
                            "The CLI response did not identify exactly one assistant "
                            "message.")

                    export_argv = build_export_argv(
                        executable, session_id,
                        standalone=capabilities.supports_standalone_export,
                        server_url=server.url)
                    export_result = await self._run(export_argv,
                                                    self._export_runner,
                                                    run_env,
                                                    paths.workdir)
                    server_facts["used_for_export"] = True
                    attempt_meta["export_exit_code"] = export_result.exit_code
                    if (export_result.timed_out or export_result.output_overflow
                            or export_result.cancelled
                            or export_result.exit_code != 0):
                        raise ModelUnavailableError("session_export_failed",
                                                    "The read-only session export failed.",
                                                    retryable=True)
                    try:
                        exported = parse_export_bytes(export_result.stdout)
                    except ExportError as exc:
                        raise ModelUnavailableError(
                            "session_export_malformed",
                            "The session export was malformed.",
                            retryable=True) from exc

                    verdict = validate_export(
                        exported, requested_model_id=self.config.model,
                        raw=parsed, requested_agent=call_config.cli_agent)
                    if not verdict.ok:
                        raise ModelUnavailableError(
                            verdict.reason or "provenance_mismatch",
                            "The session export did not prove a consistent response.")

                    assistant = convert_assistant_output(parsed.combined_text, payload)
                    components = dict(verdict.usage_components or {})
                    usage = openai_usage(components)
                    finish = (exported.assistant_messages[0].finish
                              if exported.assistant_messages else None)
                    attempt_meta.update({
                        "ok": True,
                        "session_id": session_id,
                        "observed_model": verdict.qualified_model_id,
                        "observed_agent": call_config.cli_agent,
                        "assistant_message_id": verdict.assistant_message_id,
                        "finish": finish,
                        "usage_components": components,
                    })
                    attempts.append(attempt_meta)

                    metadata = _safe_meta_base(self.config, prompt)
                    metadata.update({
                        "ok": True,
                        "session_id": session_id,
                        "observed_model": verdict.qualified_model_id,
                        "observed_provider_id": verdict.observed_provider_id,
                        "observed_model_id": verdict.observed_model_id,
                        "observed_agent": call_config.cli_agent,
                        "identity_source": "opencode_session_export",
                        "assistant_message_id": verdict.assistant_message_id,
                        "finish": finish,
                        "stream_format": parsed.stream_format,
                        "usage_components": components,
                        "usage_total": verdict.usage_total,
                        "usage_consistent": usage["usage_consistent"],
                        "attempts": len(attempts),
                        "failed_attempts": len([a for a in attempts if not a["ok"]]),
                        "evidence": "stored" if call_dir is not None else "disabled",
                        "controls": _control_meta(controls),
                    })
                    metadata.update(_capability_meta(self.config, capabilities,
                                                     pure_applied))
                    metadata.update(_transport_meta(
                        paths, readiness, agent_id=call_config.cli_agent,
                        preflight=preflight, server=server_facts,
                        prompt_input=prompt_input))
                    if call_dir is not None:
                        self._write_evidence(call_dir, attempt, run_result,
                                             export_result, metadata, paths)
                    return {
                        "id": f"chatcmpl-{uuid.uuid4().hex}",
                        "object": "chat.completion",
                        "created": int(time.time()),
                        "model": verdict.qualified_model_id,
                        "choices": [{
                            "index": 0,
                            "message": assistant,
                            "finish_reason": ("tool_calls"
                                              if assistant.get("tool_calls") else "stop"),
                        }],
                        "usage": usage,
                        "_provider": metadata,
                    }
                except ModelUnavailableError as exc:
                    attempt_meta["error_code"] = exc.code
                    attempts.append(attempt_meta)
                    last_error = exc
                    if call_dir is not None and run_result is not None:
                        failure_meta = _safe_meta_base(self.config, prompt)
                        failure_meta.update({
                            "ok": False, "error_code": exc.code,
                            "attempts": list(attempts),
                            "evidence_note": EVIDENCE_NOTE,
                            "controls": _control_meta(controls),
                        })
                        failure_meta.update(_capability_meta(
                            self.config, capabilities, pure_applied))
                        failure_meta.update(_transport_meta(
                            paths, readiness, agent_id=call_config.cli_agent,
                            preflight=preflight, server=server_facts,
                            prompt_input=prompt_input))
                        self._write_evidence(call_dir, attempt, run_result,
                                             export_result, failure_meta, paths)
                    if attempt < self.config.cli_max_attempts and exc.retryable:
                        continue
                    break
        finally:
            try:
                if server is not None:
                    cleanup_facts.clear()
                    cleanup_facts.update(server.close())
            finally:
                cli_runtime.cleanup_transport(paths)
                cleanup_facts["transport_removed"] = (
                    paths is None or not paths.root.exists())
                self._release()

        assert last_error is not None
        last_error.attempts = len(attempts)
        last_error.failed_attempts = len([a for a in attempts if not a["ok"]])
        raise last_error
