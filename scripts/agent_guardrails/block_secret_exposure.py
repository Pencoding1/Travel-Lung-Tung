#!/usr/bin/env python3
"""block_secret_exposure.py -- HM-053 pre_tool_call guardrail.

Hop dong (contract)
-------------------
stdin : mot JSON object, vi du
        {"hook_event_name": "pre_tool_call",
         "tool_name": "terminal",
         "tool_input": {"command": "..."}}     # hoac "args": ...
stdout: mot JSON decision, KHONG chua payload/command/args
exit  : 0 = allow, 2 = block (fail closed)

Nguyen tac: payload dang duoc kiem tra co the chinh la secret, nen khong bao gio
in lai command/args/exception text. Chi in ma ly do co dinh.

Gioi han da biet (khong duoc quang cao qua muc):
  * Day la phan loai lenh theo mau (defense-in-depth), KHONG phai sandbox va
    KHONG chung minh duoc moi chuong trinh tuy y.
  * Khong pin executable/hash cua interpreter hay cua helper.
  * Duong dan helper duoc phep la duong dan tuyet doi da resolve; bien the
    tuong doi/prefix la se bi tu choi.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys

# --------------------------------------------------------------------------
# Hang so
# --------------------------------------------------------------------------

PRE_TOOL_CALL = "pre_tool_call"
ALLOW = "allow"
BLOCK = "block"

GUARD_DIR = os.path.dirname(os.path.abspath(__file__))
GUARD_BASENAME = "block_secret_exposure.py"
HELPER_BASENAME = "safe_secret_probe.py"
APPROVED_HELPER_PATH = os.path.normcase(
    os.path.realpath(os.path.join(GUARD_DIR, HELPER_BASENAME))
)

SHELL_TOOL_NAMES = frozenset(
    {
        "terminal",
        "shell",
        "bash",
        "sh",
        "zsh",
        "powershell",
        "pwsh",
        "cmd",
        "run_command",
        "run_shell",
        "run_terminal_cmd",
        "shell_command",
        "exec_command",
        "local_shell",
        "container_exec",
        "execute",
        "exec",
        "command",
    }
)

WRITE_TOOL_NAMES = frozenset(
    {
        "write_file",
        "create_file",
        "append_file",
        "patch",
        "edit_file",
        "edit",
        "apply_patch",
        "multi_edit",
        "str_replace",
        "str_replace_editor",
        "insert_text",
        "notebook_edit",
        "delete_file",
        "move_file",
        "rename_file",
        "create_directory",
        "write",
    }
)

PATH_KEY_NAMES = frozenset(
    {
        "path",
        "file_path",
        "filepath",
        "filename",
        "file",
        "target",
        "target_path",
        "destination",
        "dest",
        "new_path",
        "old_path",
        "source",
        "src",
        "pattern",
        "query",
        "glob",
        "dir",
        "directory",
        "cwd",
        "workdir",
    }
)

PY_INTERPRETERS = frozenset(
    {"python", "python3", "py", "pythonw", "python.exe", "python3.exe", "py.exe", "pythonw.exe"}
)

ALLOWED_HELPER_FLAGS = frozenset({"--env", "--file", "--format", "--name"})
ALLOWED_FORMATS = frozenset({"dotenv", "json", "toml", "yaml"})

REASONS = {
    "NO_MATCH": "no guard rule matched",
    "EVENT_NOT_APPLICABLE": "hook event is not pre_tool_call",
    "APPROVED_HELPER_INVOCATION": "exact approved safe_secret_probe invocation",
    "MALFORMED_HOOK_EVENT": "hook event could not be parsed; failing closed",
    "INTERNAL_ERROR": "guard failed internally; failing closed",
    "PROTECTED_GUARD_FILE": "guard/hook configuration is write protected",
    "HELPER_INVOCATION_DENIED": "safe_secret_probe must be invoked exactly, with no extra work",
    "SENSITIVE_FILE_ACCESS": "access to a credential-bearing path is blocked",
    "ENV_DUMP": "environment enumeration/expansion is blocked",
    "OPAQUE_EXECUTION": "encoded or opaque interpreter execution is blocked",
}

# --------------------------------------------------------------------------
# Mau nhan dang
# --------------------------------------------------------------------------

ENV_DUMP_RES = [
    re.compile(p, re.I)
    for p in (
        r"\bget-childitem\s+(?:-(?:path|pspath)\s+)?env:",
        r"\bget-item\s+(?:-(?:path|pspath)\s+)?env:",
        r"\b(?:gci|dir|ls)\s+(?:-(?:path|pspath)\s+)?env:",
        r"\bprintenv\b",
        r"\$\{?env:",
        r"\bos\.environ\b",
        r"\bos\.getenv\s*\(",
        r"\bfrom\s+os\s+import\s+environ\b",
        r"\benviron\.(?:copy|items|keys|values)\b",
        r"\bprocess\.env\b",
        r"\bgetenv\s*\(",
        r"\bdeclare\s+-x\b",
        # declare/typeset voi co chua 'p' = dump toan bo bien (ke ca -p, -xp, -px)
        r"\b(?:declare|typeset)\b[^\n;&|]{0,40}\s-[A-Za-z]*p[A-Za-z]*(?:\s|=|$)",
        r"\bexport\s+-p\b",
        r"\bcompgen\s+-v\b",
        r"\bgetenvironmentvariables\b",
        r"\.net\s+environment\b",
    )
]

BARE_DUMP_RE = re.compile(
    r"(?:^|[;&|]\s*)(?:env|set|export|printenv)\s*(?:$|[;&|])", re.I
)

SECRETY_NAME_RE = re.compile(
    r"(?:^|_)(?:KEY|KEYS|TOKEN|TOKENS|SECRET|SECRETS|PASSWORD|PASSWD|PW|"
    r"CREDENTIAL|CREDENTIALS|APIKEY|API_KEY|PRIVATE_KEY|DSN|CONNECTION_STRING)$",
    re.I,
)

VAR_REF_RES = [
    re.compile(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?"),
    re.compile(r"%([A-Za-z_][A-Za-z0-9_]*)%"),
]

OPAQUE_RES = [
    re.compile(p, re.I)
    for p in (
        r"-encodedcommand\b",
        r"(?:^|\s)-enc(?:\s|=|$)",
        r"(?:^|\s)-ec(?:\s|=|$)",
        r"\bfrombase64string\b",
        r"\binvoke-expression\b",
        r"\biex\b",
        r"\beval\b",
        r"\bexec\s*\(",
        r"\bbase64\s+(?:-d|--decode|-d=)\b",
        r"\bxxd\s+-r\b",
        r"\bopenssl\s+enc\b",
        r"\batob\b",
        r"[A-Za-z0-9+/]{200,}={0,2}",
        r"\b(?:python[0-9.]*|py)\s+-c\b",
    )
]

_WRITE_HINT_RE = re.compile(
    r"(?:>>?|\btee\b|remove-item|\brm\b|\bdel\b|\bmv\b|\bcp\b|\bcopy\b|"
    r"set-content|out-file|\bsed\s+-i\b|truncate|\bchmod\b|\battrib\b|\bwrite\b)",
    re.I,
)

PROTECTED_RES = [
    re.compile(p)
    for p in (
        r"agent_guardrails/block_secret_exposure\.py",
        r"agent_guardrails/safe_secret_probe\.py",
        r"\bguardrail_domain\.py\b",
        r"agent-hooks/",
        r"shell-hooks-allowlist\.json",
        r"hermes/(?:profiles/[^/\s]+/)?config\.ya?ml",
        r"hermes/profiles/[^/\s]+/\.env",
    )
]

HELPER_METACHARS = frozenset(";|&<>`\n\r$(){}")

# F2: helper chi duoc goi bang duong dan tuyet doi day du. 'cwd'/'workdir'
# trong payload la metadata: khong bao gio la co so cap exemption va khong phai
# la phan cua lenh duoc kiem tra.
_CWD_KEY_NAMES = frozenset({"cwd", "workdir", "working_directory"})
_COMMAND_KEY_NAMES = frozenset({"command", "cmd"})

_SENSITIVE_BASENAMES = frozenset(
    {
        ".netrc",
        ".npmrc",
        ".pypirc",
        ".git-credentials",
        ".htpasswd",
        ".pgpass",
        ".ssh",
        ".aws",
        ".gnupg",
        "credentials",
        "credentials.json",
        "credentials.yaml",
        "credentials.yml",
        "credentials.toml",
        "credentials.txt",
        "auth.json",
        "auth.yaml",
        "auth.yml",
        "auth.toml",
        # hop dong safe-config: basename config.* phai di qua metadata helper,
        # khong cho doc raw du nam o thu muc nao
        "config.yaml",
        "config.yml",
        "config.json",
        "config.toml",
        "token.json",
        "tokens.json",
        "secret",
        "secret.json",
        "secret.yaml",
        "secrets",
        "secrets.json",
        "secrets.yaml",
        "secrets.yml",
        "secrets.toml",
        "secrets.txt",
        "service-account.json",
        "client_secret.json",
        "key_exposure_excerpt_private.txt",
    }
)

_SENSITIVE_SUFFIXES = (".pem", ".key", ".pfx", ".p12", ".jks", ".keystore")
_ID_KEY_PREFIXES = ("id_rsa", "id_ed25519", "id_dsa", "id_ecdsa")

# --------------------------------------------------------------------------
# Helper
# --------------------------------------------------------------------------


def _allow(reason: str) -> dict:
    return {"decision": ALLOW, "reason_code": reason}


def _block(reason: str) -> dict:
    return {
        "decision": BLOCK,
        "reason_code": reason,
        "message": REASONS.get(reason, "blocked"),
    }


def _payload_strings(value, depth: int = 0) -> list:
    if depth > 4:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        out = []
        for item in value:
            out.extend(_payload_strings(item, depth + 1))
        return out
    if isinstance(value, dict):
        out = []
        for item in value.values():
            out.extend(_payload_strings(item, depth + 1))
        return out
    if isinstance(value, bool):
        return [str(value).lower()]
    if isinstance(value, (int, float)):
        return [str(value)]
    return []


def _path_fields(payload) -> list:
    out = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if isinstance(key, str) and key.strip().lower() in PATH_KEY_NAMES:
                if isinstance(value, str) and value.strip():
                    out.append(value)
                elif isinstance(value, (list, tuple)):
                    for item in value:
                        if isinstance(item, str) and item.strip():
                            out.append(item)
    return out


def _norm_token_path(token: str) -> str:
    return os.path.normcase(os.path.realpath(os.path.abspath(token)))


def _strip_quotes(token: str) -> str:
    if len(token) >= 2 and token[0] == token[-1] and token[0] in ("'", '"'):
        return token[1:-1]
    return token


def _shell_tokens(text: str) -> list:
    parts = re.split(r"[\s;|&><()'\"`,]+", text)
    return [p for p in parts if p]


def _base_name(token: str) -> str:
    normalised = token.strip().strip("'\"`").replace("\\", "/")
    normalised = normalised.rstrip("/")
    if not normalised:
        return ""
    return normalised.split("/")[-1].lower()


def _is_sensitive_path(token: str) -> bool:
    raw = token.strip().strip("'\"`").replace("\\", "/")
    if not raw or "://" in raw:
        return False
    base = _base_name(raw)
    if not base:
        return False
    if base.startswith(".env"):
        return True
    if base.endswith(".env"):
        return True
    if base in _SENSITIVE_BASENAMES:
        return True
    if base.startswith(_ID_KEY_PREFIXES):
        return True
    if base.endswith(_SENSITIVE_SUFFIXES):
        return True
    return False


def _secrety_var_reference(text: str) -> bool:
    for pattern in VAR_REF_RES:
        for match in pattern.finditer(text):
            if SECRETY_NAME_RE.search(match.group(1)):
                return True
    return False


def _looks_opaque(text: str) -> bool:
    return any(pattern.search(text) for pattern in OPAQUE_RES)


def _protected_hit(text: str) -> bool:
    lowered = text.lower().replace("\\", "/")
    if any(pattern.search(lowered) for pattern in PROTECTED_RES):
        return True
    if "hook" in lowered and re.search(
        r"hermes\s+config\s+(?:set|unset|edit|remove)\b", lowered
    ):
        return True
    return False


def _has_write_hint(text: str) -> bool:
    return bool(_WRITE_HINT_RE.search(text))


def _safe_name_arg(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.\-]*", value or ""))


def _safe_file_arg(value: str) -> bool:
    if not value or "://" in value:
        return False
    if any(ch in value for ch in "*?<>|\"'\n\r\t"):
        return False
    if ".." in value:
        return False
    return True


def _validate_helper_args(args: list):
    env_flag = False
    file_flag = False
    fmt = None
    name = None
    index = 0
    while index < len(args):
        token = args[index]
        key, separator, value = token.partition("=")
        if key not in ALLOWED_HELPER_FLAGS:
            return False, "HELPER_FLAG"
        if key == "--env":
            if separator:
                return False, "HELPER_FLAG"
            env_flag = True
        else:
            if not separator:
                index += 1
                if index >= len(args):
                    return False, "HELPER_VALUE"
                value = args[index]
            if key == "--file":
                if not _safe_file_arg(value):
                    return False, "HELPER_FILE"
                file_flag = True
            elif key == "--format":
                if value not in ALLOWED_FORMATS:
                    return False, "HELPER_FORMAT"
                fmt = value
            else:
                if not _safe_name_arg(value):
                    return False, "HELPER_NAME"
                name = value
        index += 1
    if env_flag == file_flag:
        return False, "HELPER_TARGET"
    if env_flag and fmt is not None:
        return False, "HELPER_FORMAT"
    if file_flag and fmt is None:
        return False, "HELPER_FORMAT"
    if not name:
        return False, "HELPER_NAME"
    return True, "OK"


def _is_fully_absolute_path(token: str) -> bool:
    """True chi khi token la duong dan tuyet doi DAY DU.

    Windows: 'X:\\...', 'X:/...' hoac UNC '\\\\server\\share\\...'.
    Tu choi: 'E:foo' (drive-relative), '\\foo' va '/foo' (root-relative, chua
    xac dinh drive), moi duong dan tuong doi, va ten tran.

    Ly do (F2): duong dan tuong doi phu thuoc cwd. Khong duoc resolve theo cwd
    cua guard process, cung khong duoc dung cwd trong payload lam co so cap
    exemption, vi ca hai deu la dau vao khong dang tin.
    """
    if not token:
        return False
    if os.name == "nt":
        if (
            len(token) >= 3
            and token[0].isalpha()
            and token[1] == ":"
            and token[2] in "\\/"
        ):
            return True
        if token[:2] in ("\\\\", "//"):
            parts = [part for part in re.split(r"[\\/]+", token[2:]) if part]
            return len(parts) >= 2
        return False
    return token.startswith("/")


def _helper_text(payload, joined: str) -> str:
    """Chuoi lenh dung rieng cho phep kiem tra loi goi helper.

    Neu payload la dict chi gom field lenh (command/cmd/...) va field cwd
    (cwd/workdir) thi chi kiem tra chinh chuoi lenh: cwd khong phai la phan cua
    lenh, va F2 cam dung cwd de cap exemption. Moi field la thi giu nguyen
    chuoi gop nhu truoc (bao thu, khong noi long).
    """
    if not isinstance(payload, dict):
        return joined
    command = None
    for key, value in payload.items():
        name = key.strip().lower() if isinstance(key, str) else ""
        if name in _CWD_KEY_NAMES:
            continue
        if name in _COMMAND_KEY_NAMES:
            if command is not None or not isinstance(value, str) or not value.strip():
                return joined
            command = value
            continue
        return joined
    return command if command else joined


def helper_invocation_ok(text: str):
    """True chi khi toan bo lenh la mot loi goi safe_secret_probe da duyet."""
    if any(ch in HELPER_METACHARS for ch in text):
        return False, "HELPER_METACHAR"
    try:
        raw_tokens = shlex.split(text, posix=False)
    except ValueError:
        return False, "HELPER_TOKENIZE"
    tokens = [_strip_quotes(token.strip()) for token in raw_tokens if token.strip()]
    if not tokens:
        return False, "HELPER_EMPTY"
    if os.path.basename(tokens[0]).lower() in PY_INTERPRETERS:
        if len(tokens) < 2:
            return False, "HELPER_NO_SCRIPT"
        script, rest = tokens[1], tokens[2:]
    else:
        script, rest = tokens[0], tokens[1:]
    # F2: phai tuyet doi truoc khi canonicalize; khong resolve relative theo cwd
    if not _is_fully_absolute_path(script):
        return False, "HELPER_PATH_NOT_ABSOLUTE"
    if _norm_token_path(script) != APPROVED_HELPER_PATH:
        return False, "HELPER_PATH"
    return _validate_helper_args(rest)


# --------------------------------------------------------------------------
# Phan loai
# --------------------------------------------------------------------------


def _is_guard_config_edit(text: str) -> bool:
    lowered = text.lower()
    if "hook" not in lowered and "guardrail" not in lowered:
        return False
    return bool(
        re.search(r"hermes\s+config\s+(?:set|unset|edit|remove|reset|add)\b", lowered)
    )


def _classify_shell(text: str) -> dict:
    if _protected_hit(text) and (_has_write_hint(text) or _is_guard_config_edit(text)):
        return _block("PROTECTED_GUARD_FILE")
    for token in _shell_tokens(text):
        if _is_sensitive_path(token):
            return _block("SENSITIVE_FILE_ACCESS")
    if any(pattern.search(text) for pattern in ENV_DUMP_RES):
        return _block("ENV_DUMP")
    if BARE_DUMP_RE.search(text):
        return _block("ENV_DUMP")
    if _secrety_var_reference(text):
        return _block("ENV_DUMP")
    if _looks_opaque(text):
        return _block("OPAQUE_EXECUTION")
    return _allow("NO_MATCH")


def _classify_other(tool: str, payload) -> dict:
    write = tool in WRITE_TOOL_NAMES
    for field in _path_fields(payload):
        if write and _protected_hit(field):
            return _block("PROTECTED_GUARD_FILE")
        if _is_sensitive_path(field):
            return _block("SENSITIVE_FILE_ACCESS")
    return _allow("NO_MATCH")


def classify(tool_name: str, payload) -> dict:
    tool = (tool_name or "").strip().lower()
    strings = _payload_strings(payload)
    text = " ".join(strings)
    if tool in SHELL_TOOL_NAMES:
        if "safe_secret_probe" in text.lower():
            ok, _why = helper_invocation_ok(_helper_text(payload, text))
            if not ok:
                return _block("HELPER_INVOCATION_DENIED")
            return _allow("APPROVED_HELPER_INVOCATION")
        return _classify_shell(text)
    return _classify_other(tool, payload)


def evaluate(event) -> dict:
    """Tra ve decision dict; fail closed voi event khong doc duoc."""
    if not isinstance(event, dict):
        return _block("MALFORMED_HOOK_EVENT")
    event_name = event.get("hook_event_name")
    if not isinstance(event_name, str) or not event_name.strip():
        return _block("MALFORMED_HOOK_EVENT")
    if event_name.strip().lower() != PRE_TOOL_CALL:
        return _allow("EVENT_NOT_APPLICABLE")
    tool_name = event.get("tool_name")
    if not isinstance(tool_name, str) or not tool_name.strip():
        return _block("MALFORMED_HOOK_EVENT")
    if "tool_input" in event:
        payload = event.get("tool_input")
    elif "args" in event:
        payload = event.get("args")
    else:
        return _block("MALFORMED_HOOK_EVENT")
    if payload is None or not isinstance(payload, (dict, list, str)):
        return _block("MALFORMED_HOOK_EVENT")
    return classify(tool_name, payload)


# --------------------------------------------------------------------------
# Entry point (tuong thich hook stdin JSON)
# --------------------------------------------------------------------------


def _read_stdin() -> str:
    stream = getattr(sys.stdin, "buffer", None)
    if stream is not None:
        return stream.read().decode("utf-8", "replace")
    return sys.stdin.read()


def _emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=True, sort_keys=True) + "\n")
    sys.stdout.flush()


def main(argv=None) -> int:
    try:
        raw = _read_stdin()
        if not raw.strip():
            decision = _block("MALFORMED_HOOK_EVENT")
        else:
            try:
                event = json.loads(raw)
            except Exception:
                event = None
            decision = (
                _block("MALFORMED_HOOK_EVENT") if event is None else evaluate(event)
            )
    except Exception:
        decision = _block("INTERNAL_ERROR")
    _emit(decision)
    return 0 if decision.get("decision") == ALLOW else 2


if __name__ == "__main__":
    sys.exit(main())
