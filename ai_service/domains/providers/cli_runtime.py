"""Per-call V2 runtime materialisation for the opt-in OpenCode CLI transport.

The installed CLI (v2.0.32) does not read the V1 ``OPENCODE_CONFIG_CONTENT``
agent shape and has no ``--pure`` flag. The supported mechanism observed with
the installed binary is a *project* ``opencode.json`` discovered from the
process working directory, plus ``--standalone`` for both ``run`` and
``session export``.

This module owns the non-secret, per-call artefacts:

* a fresh transport directory (outside any git work tree, so no repository
  config is consulted) containing that ``opencode.json``;
* the bounded ``run`` / ``session export`` / readiness argv arrays;
* the child environment (service secrets removed, ambient inline config
  removed, provider credentials left to the CLI's own configuration).

Nothing here reads, copies or logs a credential. The generated config is
non-secret by construction: it never contains a provider ``env`` value, an API
key value, a header or a base URL. The exact Go alias carries only the
documented ``{env:OPENCODE_API}`` reference; the loader supplies the value to
the CLI child environment only.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from . import go_credentials

TRANSPORT_SYSTEM_PROMPT = (
    "You are a text-only model transport for the Travel Lung Tung service. "
    "Native tools are forbidden: you cannot read or write files, run commands, "
    "access the network, or ask questions. You may return, as plain text, the "
    "JSON server-tool request envelope asked for by the conversation; that "
    "request is executed only by the Travel AI server, never by you. Never "
    "claim to have executed a tool or taken an action. Produce only the "
    "response requested by the conversation. When the conversation requests "
    "JSON, return only that JSON object."
)

CONFIG_FILENAME = "opencode.json"
OWNER_FILENAME = ".cli060-transport-owner"
PROMPT_FILENAME = "prompt-input.txt"
PROMPT_INSTRUCTION = (
    "Read the attached prompt file and follow it exactly as the request.")
CONFIG_SCHEMA = "https://opencode.ai/config.json"
TRANSPORT_DIR_PREFIX = "opencode-cli-transport-"

# Two primary agent steps: the documented minimum that keeps the first model
# call from being final. On the final step the CLI removes tools and asks the
# model to summarize in text, which is incompatible with asking it to emit a
# JSON server-tool request on its first call. A normal text/JSON reply still
# finishes after one native call. A hallucinated native tool attempt must stay
# denied, so such a failure can cost at most one extra bounded step; this is
# not a native tool permission grant.
AGENT_MAX_STEPS = 2

# Explicit denies in addition to the wildcard. The wildcard is what the
# installed CLI actually enforces (the tool list is removed from the outbound
# request); the explicit entries document intent and survive a future runtime
# that evaluates the named actions separately.
DENIED_ACTIONS: Tuple[str, ...] = (
    "read", "write", "edit", "patch", "list", "glob", "grep",
    "bash", "shell", "execute", "webfetch", "websearch", "fetch",
    "task", "subagent", "question", "skill", "mcp", "browser", "lsp",
)

# Service-only secrets are removed from the CLI child environment. Provider
# credentials managed by the CLI itself (for the selected alias) are untouched.
SANITIZED_ENV_KEYS: Tuple[str, ...] = (
    "GEMINI_API_KEY", "JWT_SECRET", "JWT_ALGORITHM", "MEMORY_DB_PATH",
    "MEMGRAPH_PASSWORD", "NGROK_AUTHTOKEN",
    "TYPESAFE_API_TOKEN", "TYPESAFE_API_KEY",
)

# Ambient inline/explicit config would merge an additional agent/permission
# document into this call. These carriers are never silently removed; the
# adapter refuses before any CLI process when one is nonempty.
AMBIENT_CONFIG_KEYS: Tuple[str, ...] = (
    "OPENCODE_CONFIG_CONTENT", "OPENCODE_CONFIG",
)

RUN_FLAG_NAMES: Tuple[str, ...] = (
    "--standalone", "--server", "--model", "--agent", "--format", "--title")
EXPORT_FLAG_NAMES: Tuple[str, ...] = ("--standalone", "--server")

# Literal session title for every transport call. It is a constant: it never
# contains the prompt, user text, a selector, a credential or any per-call data.
SESSION_TITLE = "Travel Lung Tung text transport"

_SESSION_ID_CHARS = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")
_MAX_SESSION_ID_CHARS = 128


@dataclass(frozen=True)
class TransportPaths:
    """The owned per-call directory and the files created inside it."""

    root: Path
    config: Path
    workdir: Path
    owner_token: str = ""

    def as_meta(self) -> Dict[str, Any]:
        return {
            "config_filename": CONFIG_FILENAME,
            "config_sha256": _sha256_file(self.config),
            "scope": "per_call_transport_directory",
        }


def _sha256_file(path: Path) -> Optional[str]:
    import hashlib

    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def split_alias(model: str) -> Tuple[str, str]:
    """Split ``provider/model`` on the **first** ``/`` only.

    The installed CLI parses selections the same way, so a nested model id such
    as ``ds/deepseek-flash`` keeps ``aibox`` as the provider.
    """
    provider, sep, model_id = model.partition("/")
    if not sep or not provider or not model_id:
        raise ValueError("model alias is not 'provider/model'")
    return provider, model_id


def deny_permissions() -> list:
    """Ordered wildcard deny followed by the explicit native-tool denies."""
    rules = [{"action": "*", "resource": "*", "effect": "deny"}]
    rules.extend(
        {"action": name, "resource": "*", "effect": "deny"}
        for name in DENIED_ACTIONS
    )
    return rules


def _provider_overlay(config: Any,
                      controls: Optional[Mapping[str, float]] = None,
                      ) -> Optional[Dict[str, Any]]:
    """Return the exact minimal provider overlay for the selected alias.

    The Go overlay contains the documented environment reference and never a
    credential value. Non-Go aliases retain the existing control-only overlay.
    """
    provider_id, model_id = split_alias(config.model)
    body = {name: value for name, value in (controls or {}).items()
            if name in ("temperature", "top_p")}
    if go_credentials.is_go_model(getattr(config, "model", None)):
        entry: Dict[str, Any] = {
            "settings": {"apiKey": go_credentials.GO_KEY_REF},
        }
        if body:
            entry["models"] = {model_id: {"body": body}}
        return {provider_id: entry}
    if body:
        return {provider_id: {"models": {model_id: {"body": body}}}}
    return None


def transport_config(config: Any, controls: Optional[Mapping[str, float]] = None,
                     ) -> Dict[str, Any]:
    """Build the non-secret V2 config document for one call.

    ``controls`` (temperature/top_p) are bound to the *exact* requested alias
    through a model-scoped provider ``request.body`` overlay, which is the only
    documented place the current runner applies them. The exact Go alias also
    gets the provider ``settings.apiKey`` environment reference; a literal key
    is never written here.
    """
    agent = config.cli_agent
    document: Dict[str, Any] = {
        "$schema": CONFIG_SCHEMA,
        "share": "disabled",
        "model": config.model,
        "default_agent": agent,
        "permissions": [{"action": "*", "resource": "*", "effect": "deny"}],
        "agents": {
            agent: {
                "description": "Travel AI text-only model transport",
                "mode": "primary",
                "hidden": False,
                "steps": AGENT_MAX_STEPS,
                "system": TRANSPORT_SYSTEM_PROMPT,
                # Bind the projected agent to the exact requested alias so the
                # engine agent reference can be checked before any model run.
                "model": config.model,
                "permissions": deny_permissions(),
            }
        },
    }
    overlay = _provider_overlay(config, controls)
    if overlay is not None:
        document["providers"] = overlay
    return document


def transport_config_text(config: Any,
                          controls: Optional[Mapping[str, float]] = None) -> str:
    return json.dumps(transport_config(config, controls),
                      indent=2, sort_keys=True, ensure_ascii=False)


def create_transport(config: Any, controls: Optional[Mapping[str, float]] = None,
                     *, base_dir: Optional[Path] = None) -> TransportPaths:
    """Create the owned per-call directory and write the config file."""
    if base_dir is not None:
        root = Path(tempfile.mkdtemp(prefix=TRANSPORT_DIR_PREFIX,
                                     dir=str(base_dir)))
    else:
        root = Path(tempfile.mkdtemp(prefix=TRANSPORT_DIR_PREFIX))
    config_path = root / CONFIG_FILENAME
    text = transport_config_text(config, controls)
    config_path.write_text(text, encoding="utf-8")
    token = secrets.token_hex(16)
    owner = root / OWNER_FILENAME
    owner.write_text(token, encoding="utf-8")
    try:
        os.chmod(config_path, 0o600)
        os.chmod(owner, 0o600)
    except OSError:
        pass
    return TransportPaths(root=root, config=config_path, workdir=root,
                          owner_token=token)


class TransportConfigError(ValueError):
    """The generated transport file did not match the restrictive contract."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class PromptFileError(ValueError):
    """The exact prompt could not be written inside the owned transport."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def write_prompt_file(paths: TransportPaths, prompt: str) -> Path:
    """Write the exact UTF-8 prompt inside the verified owned directory.

    The file is a transport input, not a native tool permission. Its bytes are
    the complete rendered system/conversation/tool-protocol text; the caller
    passes only the fixed filename with ``--file``. Raw prompt text is never
    placed in argv, metadata, config or logs.
    """
    if not isinstance(prompt, str):
        raise PromptFileError("cli_prompt_file_unavailable")
    root = paths.root
    if (not root.name.startswith(TRANSPORT_DIR_PREFIX) or root.is_symlink()
            or os.path.normcase(os.path.realpath(root))
            != os.path.normcase(os.path.abspath(root))):
        raise PromptFileError("cli_prompt_file_owner_mismatch")
    marker = root / OWNER_FILENAME
    try:
        token = marker.read_text(encoding="utf-8").strip()
    except OSError:
        raise PromptFileError("cli_prompt_file_owner_mismatch") from None
    if not paths.owner_token or not secrets.compare_digest(
            token, paths.owner_token):
        raise PromptFileError("cli_prompt_file_owner_mismatch")

    target = root / PROMPT_FILENAME
    if target.is_symlink():
        raise PromptFileError("cli_prompt_file_owner_mismatch")
    try:
        raw = prompt.encode("utf-8")
    except UnicodeEncodeError:
        raise PromptFileError("cli_prompt_file_unavailable") from None
    try:
        with open(target, "wb") as handle:
            handle.write(raw)
            handle.flush()
        os.chmod(target, 0o600)
    except OSError:
        try:
            target.unlink()
        except OSError:
            pass
        raise PromptFileError("cli_prompt_file_unavailable") from None
    return target


def validate_transport_config(paths: TransportPaths, config: Any,
                              controls: Optional[Mapping[str, float]] = None,
                              ) -> Dict[str, Any]:
    """Validate the generated file bytes before any CLI process can use them.

    This proves what *we handed* the runtime: exactly one unique primary agent,
    a text-only system prompt, one step, an ordered wildcard deny plus every
    explicit native-tool deny, and a control overlay bound to the exact alias.
    It does not claim an engine-side agent projection; that is disclosed
    separately as unavailable/available by the caller.
    """
    import hashlib

    try:
        raw = paths.config.read_bytes()
        document = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        raise TransportConfigError("transport_config_unreadable")
    if not isinstance(document, dict):
        raise TransportConfigError("transport_config_not_object")

    agent_id = getattr(config, "cli_agent", None)
    if not isinstance(agent_id, str) or not agent_id.strip():
        raise TransportConfigError("transport_agent_missing")
    if document.get("model") != getattr(config, "model", None):
        raise TransportConfigError("transport_model_mismatch")
    if document.get("default_agent") != agent_id:
        raise TransportConfigError("transport_default_agent_mismatch")
    if document.get("share") != "disabled":
        raise TransportConfigError("transport_share_not_disabled")

    expected_root = [{"action": "*", "resource": "*", "effect": "deny"}]
    if document.get("permissions") != expected_root:
        raise TransportConfigError("transport_root_policy_mismatch")

    agents = document.get("agents")
    if not isinstance(agents, dict) or set(agents) != {agent_id}:
        raise TransportConfigError("transport_agent_not_unique")
    agent = agents[agent_id]
    if not isinstance(agent, dict):
        raise TransportConfigError("transport_agent_malformed")
    if agent.get("mode") != "primary":
        raise TransportConfigError("transport_agent_not_primary")
    if agent.get("steps") != AGENT_MAX_STEPS:
        raise TransportConfigError("transport_agent_steps_mismatch")
    if agent.get("system") != TRANSPORT_SYSTEM_PROMPT:
        raise TransportConfigError("transport_agent_system_mismatch")
    if agent.get("model") != getattr(config, "model", None):
        raise TransportConfigError("transport_agent_model_mismatch")

    permissions = agent.get("permissions")
    if not isinstance(permissions, list) or not permissions:
        raise TransportConfigError("transport_agent_permissions_missing")
    if permissions[0] != expected_root[0]:
        raise TransportConfigError("transport_agent_wildcard_missing")
    if any(not isinstance(rule, dict) or rule.get("effect") != "deny"
           or not rule.get("action") or not rule.get("resource")
           for rule in permissions):
        raise TransportConfigError("transport_agent_allow_rule")
    actions = {rule.get("action") for rule in permissions
               if isinstance(rule, dict)}
    if not set(DENIED_ACTIONS).issubset(actions):
        raise TransportConfigError("transport_agent_deny_coverage")

    expected_overlay = _provider_overlay(config, controls)
    providers = document.get("providers")
    if providers != expected_overlay:
        if go_credentials.is_go_model(getattr(config, "model", None)):
            raise TransportConfigError("transport_go_binding_mismatch")
        if expected_overlay is not None:
            raise TransportConfigError("transport_control_binding_mismatch")
        raise TransportConfigError("transport_unexpected_provider_overlay")

    return {
        "status": "generated_config_validated",
        "agent_id": agent_id,
        "config_sha256": hashlib.sha256(raw).hexdigest(),
        "engine_agent_projection": "unavailable",
    }


def cleanup_transport(paths: Optional[TransportPaths]) -> None:
    """Remove only the exact directory this call created.

    The prefix alone is not authority: a same-named directory, a replaced
    directory, a symlink/junction, or any directory without this call's random
    owner marker is left untouched. A raced replacement after the marker check
    is outside what a portable cleanup can prove; it is disclosed.
    """
    if paths is None:
        return
    root = paths.root
    if not root.name.startswith(TRANSPORT_DIR_PREFIX):
        return
    try:
        if root.is_symlink():
            return
        if (os.path.normcase(os.path.realpath(root))
                != os.path.normcase(os.path.abspath(root))):
            return
        marker = root / OWNER_FILENAME
        if not marker.is_file():
            return
        token = marker.read_text(encoding="utf-8").strip()
        if not paths.owner_token or not secrets.compare_digest(
                token, paths.owner_token):
            return
        marker.unlink()
    except OSError:
        return
    shutil.rmtree(root, ignore_errors=True)


def child_environment(config: Any,
                      base: Optional[Mapping[str, str]] = None) -> Dict[str, str]:
    """Return the sanitised child environment for one CLI invocation.

    Ambient ``OPENCODE_CONFIG_CONTENT`` / ``OPENCODE_CONFIG`` carriers are
    preserved here rather than silently dropped. ``OpenCodeCliProvider``
    refuses a nonempty carrier before launching any CLI process; direct callers
    can therefore inspect the same environment without losing a user guard.
    """
    env = dict(os.environ if base is None else base)
    for key in SANITIZED_ENV_KEYS:
        env.pop(key, None)
    return env


def ambient_config_carriers(
        env: Optional[Mapping[str, str]] = None) -> Tuple[str, ...]:
    """Return the names (never values) of nonempty ambient config carriers."""
    source = os.environ if env is None else env
    present: list = []
    for key in AMBIENT_CONFIG_KEYS:
        value = source.get(key)
        if isinstance(value, str) and value.strip():
            present.append(key)
    return tuple(present)


def per_call_agent(base: str) -> str:
    """Return a fresh agent id derived from the configured base."""
    cleaned = (base or "transport").strip() or "transport"
    return f"{cleaned}-{secrets.token_hex(6)}"


def valid_session_id(session_id: str) -> bool:
    return (0 < len(session_id) <= _MAX_SESSION_ID_CHARS
            and set(session_id) <= _SESSION_ID_CHARS)


def build_run_argv(executable: str, config: Any, prompt: str, *,
                   cli_supports_pure: bool = False,
                   server_url: Optional[str] = None,
                   prompt_file: Optional[Path] = None) -> list:
    argv = [executable, "run"]
    if config.cli_pure and cli_supports_pure:
        argv.append("--pure")
    if server_url is not None:
        argv += ["--server", server_url]
    else:
        argv.append("--standalone")
    argv += ["--model", config.model,
             "--agent", config.cli_agent, "--format", "json",
             "--title", SESSION_TITLE]
    if prompt_file is not None:
        # The documented run --file attachment. The message precedes the
        # attachment argv so the fixed instruction remains the run message.
        argv += [PROMPT_INSTRUCTION, "--file", str(prompt_file)]
    else:
        argv.append(prompt)
    return argv


def build_export_argv(executable: str, session_id: str, *,
                      standalone: bool = True,
                      server_url: Optional[str] = None) -> list:
    """V2 export route bound to the owned server when one is provided.

    There is no top-level ``opencode export`` in the installed CLI.
    """
    if not valid_session_id(session_id):
        raise ValueError("invalid session id")
    argv = [executable, "session", "export"]
    if server_url is not None:
        argv += ["--server", server_url]
    elif standalone:
        argv.append("--standalone")
    argv.append(session_id)
    return argv


def build_models_argv(executable: str, *, standalone: bool = True) -> list:
    argv = [executable, "models"]
    if standalone:
        argv.append("--standalone")
    return argv


def advertised_flags(help_text: Optional[str]) -> Tuple[str, ...]:
    if not help_text:
        return ()
    return tuple(name for name in
                 set(RUN_FLAG_NAMES) | set(EXPORT_FLAG_NAMES)
                 if name in help_text)


def model_listing_contains(stdout: bytes, alias: str) -> bool:
    """True only when the readiness listing contains the exact alias."""
    try:
        text = stdout.decode("utf-8")
    except UnicodeDecodeError:
        return False
    wanted = alias.strip()
    if not wanted:
        return False
    for line in text.splitlines():
        if line.strip() == wanted:
            return True
    return False
