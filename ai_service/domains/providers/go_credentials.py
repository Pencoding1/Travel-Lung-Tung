"""Narrow credential binding for the explicit OpenCode Go model alias.

The application keeps the coding/executor provider unchanged. Only an exact
``opencode-go/deepseek-v4.1-flash`` transport call may read the named
``OPENCODE_API`` credential, and only into that CLI child environment.

The value is never stored on :class:`ProviderConfig`, metadata, argv, the
materialised transport config, evidence or error text. The generated config
contains only the documented ``{env:OPENCODE_API}`` reference. Process
environment presence is authoritative; a project-root ``.env`` fallback is a
bounded, no-interpolation read of that one key.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Mapping, Optional

GO_PROVIDER_ID = "opencode-go"
GO_MODEL_ID = "deepseek-v4.1-flash"
GO_ALIAS = f"{GO_PROVIDER_ID}/{GO_MODEL_ID}"
GO_ENV_VAR = "OPENCODE_API"
GO_KEY_REF = "{env:OPENCODE_API}"

MAX_KEY_CHARS = 4096
MAX_ENV_BYTES = 64 * 1024
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"


class GoCredentialError(ValueError):
    """A constant failure code; the credential is never part of the message."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def is_go_model(model: object) -> bool:
    """True only for the exact documented Go alias, not a look-alike."""
    return isinstance(model, str) and model == GO_ALIAS


def _validate_key(value: object) -> str:
    if not isinstance(value, str):
        raise GoCredentialError("go_credential_invalid")
    if not value or len(value) > MAX_KEY_CHARS:
        raise GoCredentialError("go_credential_invalid")
    # API keys are opaque but must not smuggle whitespace, controls or line
    # breaks into an environment/config layer. Do not inspect a prefix.
    for char in value:
        code = ord(char)
        if code < 33 or code > 126:
            raise GoCredentialError("go_credential_invalid")
    return value


def _target_value(line: str) -> Optional[str]:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if stripped.startswith("export "):
        stripped = stripped[7:].lstrip()
    name, sep, value = stripped.partition("=")
    if not sep:
        if name.strip() == GO_ENV_VAR:
            raise GoCredentialError("go_credential_file_malformed")
        return None
    if name.strip() != GO_ENV_VAR:
        return None
    value = value.strip()
    if len(value) >= 2 and value[0] in ("'", '"') and value[-1] == value[0]:
        value = value[1:-1]
    return value


def load_go_api_key_file(path: Path) -> str:
    """Read only ``OPENCODE_API`` from one bounded UTF-8 regular file."""
    try:
        info = os.stat(path, follow_symlinks=False)
    except FileNotFoundError:
        raise GoCredentialError("go_credential_missing")
    except OSError:
        raise GoCredentialError("go_credential_file_unreadable")
    if not stat.S_ISREG(info.st_mode):
        raise GoCredentialError("go_credential_file_unreadable")
    if info.st_size > MAX_ENV_BYTES:
        raise GoCredentialError("go_credential_file_too_large")
    try:
        raw = path.read_bytes()
    except OSError:
        raise GoCredentialError("go_credential_file_unreadable")
    if len(raw) > MAX_ENV_BYTES or b"\x00" in raw:
        raise GoCredentialError("go_credential_file_malformed")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise GoCredentialError("go_credential_file_malformed")
    if text.startswith("\ufeff"):
        text = text[1:]
    found: Optional[str] = None
    for line in text.splitlines():
        value = _target_value(line)
        if value is None:
            continue
        if found is not None:
            raise GoCredentialError("go_credential_file_malformed")
        found = value
    if found is None:
        raise GoCredentialError("go_credential_missing")
    return _validate_key(found)


def load_go_api_key(environ: Optional[Mapping[str, str]] = None, *,
                    env_path: Optional[Path] = None,
                    project_root: Optional[Path] = None) -> str:
    """Resolve the exact Go key with process presence taking priority.

    ``environ=None`` means the real process environment and permits the
    code-relative project ``.env`` fallback. An explicit mapping is
    authoritative: a missing/blank/invalid value never falls through to a file.
    Tests that exercise the file loader pass an explicit ``env_path``.
    """
    source = os.environ if environ is None else environ
    if GO_ENV_VAR in source:
        return _validate_key(source.get(GO_ENV_VAR))
    if environ is not None:
        raise GoCredentialError("go_credential_missing")
    path = (Path(env_path) if env_path is not None
            else (Path(project_root) if project_root is not None
                  else PROJECT_ROOT) / ".env")
    return load_go_api_key_file(path)
