#!/usr/bin/env python3
"""safe_secret_probe.py -- HM-053: chi tra METADATA cua mot bien duoc hoi.

Vi du
-----
  python safe_secret_probe.py --env --name DEMO_API_KEY
  python safe_secret_probe.py --file .env --format dotenv --name DEMO_API_KEY
  python safe_secret_probe.py --file cfg.json --format json --name a.b

Dau ra chi co: present, type, length (so KY TU neu la string), name, source.
KHONG BAO GIO tra value/prefix/suffix/hash/preview.

Bat bien
--------
  * Env: chi doc dung ten duoc hoi; khong liet ke toan bo moi truong.
  * Dotenv: khong evaluate/interpolate/execute; khong goi shell.
  * JSON/TOML: parser chuan cua Python. YAML: chi yaml.safe_load neu co san
    thu vien; thieu thi bao loi da lam sach, KHONG tu cai dat.
  * File: chi doc file thuong, gioi han 1 MiB truoc khi parse, khong theo URL.
  * Loi tra ve ma ly do co dinh; khong bao gio tra nguyen exception (co the
    chua du lieu bi mat).
  * Khong ghi log, khong ghi file.
"""

from __future__ import annotations

import json
import os
import re
import stat
import sys

MAX_FILE_BYTES = 1024 * 1024  # 1 MiB

ALLOWED_FORMATS = ("dotenv", "json", "toml", "yaml")

ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
DOTTED_SEGMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_\-]*$")

USAGE = (
    "usage: safe_secret_probe.py --env --name NAME\n"
    "       safe_secret_probe.py --file PATH --format dotenv|json|toml|yaml --name NAME"
)

_ERROR_REASONS = frozenset(
    {
        "INVALID_ARGUMENTS",
        "INVALID_NAME",
        "URL_NOT_ALLOWED",
        "FILE_NOT_FOUND",
        "FILE_PERMISSION_DENIED",
        "FILE_NOT_REGULAR",
        "FILE_TOO_LARGE",
        "FILE_NOT_UTF8",
        "FILE_UNREADABLE",
        "DOTENV_SYNTAX",
        "DOTENV_UNTERMINATED_VALUE",
        "JSON_PARSE_ERROR",
        "TOML_PARSE_ERROR",
        "TOML_PARSER_UNAVAILABLE",
        "YAML_PARSER_UNAVAILABLE",
        "YAML_PARSE_ERROR",
        "PATH_NOT_MAPPING",
        "INTERNAL_ERROR",
    }
)

_MISSING = object()


class ProbeError(Exception):
    """Loi da lam sach: chi mang ma ly do co dinh."""

    def __init__(self, reason: str):
        self.reason = reason if reason in _ERROR_REASONS else "INTERNAL_ERROR"
        super().__init__(self.reason)

    def __str__(self) -> str:  # khong bao gio chua payload
        return self.reason


# --------------------------------------------------------------------------
# Mo ta gia tri -> metadata (khong stringify payload)
# --------------------------------------------------------------------------


def describe_value(value) -> dict:
    """Tra metadata cua value; khong bao gio tra chinh value."""
    if value is None:
        return {"present": True, "type": "null", "length": None}
    if isinstance(value, bool):
        return {"present": True, "type": "boolean", "length": None}
    if isinstance(value, str):
        return {"present": True, "type": "string", "length": len(value)}
    if isinstance(value, (int, float)):
        return {"present": True, "type": "number", "length": None}
    if isinstance(value, (list, tuple)):
        return {"present": True, "type": "array", "length": None}
    if isinstance(value, dict):
        return {"present": True, "type": "object", "length": None}
    return {"present": True, "type": "unsupported", "length": None}


def describe_missing(name: str, source: str) -> dict:
    return {
        "name": name,
        "source": source,
        "present": False,
        "type": None,
        "length": None,
    }


# --------------------------------------------------------------------------
# Doc file (gioi han kich thuoc truoc khi parse)
# --------------------------------------------------------------------------


def _read_text_file(path: str) -> str:
    if not path or "://" in path:
        raise ProbeError("URL_NOT_ALLOWED")
    try:
        info = os.stat(path)
    except FileNotFoundError:
        raise ProbeError("FILE_NOT_FOUND")
    except PermissionError:
        raise ProbeError("FILE_PERMISSION_DENIED")
    except OSError:
        raise ProbeError("FILE_UNREADABLE")
    if not stat.S_ISREG(info.st_mode):
        raise ProbeError("FILE_NOT_REGULAR")
    if info.st_size > MAX_FILE_BYTES:
        raise ProbeError("FILE_TOO_LARGE")
    try:
        with open(path, "rb") as handle:
            raw = handle.read(MAX_FILE_BYTES + 1)
    except FileNotFoundError:
        raise ProbeError("FILE_NOT_FOUND")
    except PermissionError:
        raise ProbeError("FILE_PERMISSION_DENIED")
    except OSError:
        raise ProbeError("FILE_UNREADABLE")
    if len(raw) > MAX_FILE_BYTES:
        raise ProbeError("FILE_TOO_LARGE")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise ProbeError("FILE_NOT_UTF8")
    if text.startswith("\ufeff"):
        text = text[1:]
    return text


# --------------------------------------------------------------------------
# Parser dotenv (khong interpolate, khong execute)
# --------------------------------------------------------------------------


def parse_dotenv(text: str) -> dict:
    data = {}
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        index += 1
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        if "=" not in line:
            raise ProbeError("DOTENV_SYNTAX")
        key, _, remainder = line.partition("=")
        key = key.strip()
        if not ENV_NAME_RE.match(key):
            raise ProbeError("DOTENV_SYNTAX")
        remainder = remainder.lstrip()
        if remainder[:1] in ('"', "'"):
            quote = remainder[0]
            buffer = remainder[1:]
            chunks = []
            while True:
                out = []
                position = 0
                closed = False
                while position < len(buffer):
                    char = buffer[position]
                    if quote == '"' and char == "\\" and position + 1 < len(buffer):
                        nxt = buffer[position + 1]
                        if nxt in ('"', "\\", "n", "t", "r"):
                            out.append({"n": "\n", "t": "\t", "r": "\r"}.get(nxt, nxt))
                            position += 2
                            continue
                        out.append(char)
                        position += 1
                        continue
                    if char == quote:
                        closed = True
                        position += 1
                        break
                    out.append(char)
                    position += 1
                chunks.append("".join(out))
                if closed:
                    break
                if index >= len(lines):
                    raise ProbeError("DOTENV_UNTERMINATED_VALUE")
                buffer = lines[index]
                index += 1
            value = "\n".join(chunks)
        else:
            value = remainder
            comment = re.search(r"\s+#", value)
            if comment:
                value = value[: comment.start()]
            value = value.rstrip()
        data[key] = value  # trung lap: dong sau thang
    return data


# --------------------------------------------------------------------------
# Parser cau truc
# --------------------------------------------------------------------------


def parse_json(text: str):
    try:
        return json.loads(text)
    except Exception:
        raise ProbeError("JSON_PARSE_ERROR")


def parse_toml(text: str):
    try:
        import tomllib
    except Exception:
        raise ProbeError("TOML_PARSER_UNAVAILABLE")
    try:
        return tomllib.loads(text)
    except Exception:
        raise ProbeError("TOML_PARSE_ERROR")


def parse_yaml(text: str):
    try:
        import yaml  # type: ignore
    except Exception:
        raise ProbeError("YAML_PARSER_UNAVAILABLE")
    try:
        return yaml.safe_load(text)
    except Exception:
        raise ProbeError("YAML_PARSE_ERROR")


_PARSERS = {
    "dotenv": parse_dotenv,
    "json": parse_json,
    "toml": parse_toml,
    "yaml": parse_yaml,
}


def validate_name(name: str, dotted: bool) -> str:
    if not name or not isinstance(name, str):
        raise ProbeError("INVALID_NAME")
    if "*" in name or "?" in name or any(ch.isspace() for ch in name):
        raise ProbeError("INVALID_NAME")
    if dotted:
        for segment in name.split("."):
            if not segment or not DOTTED_SEGMENT_RE.match(segment):
                raise ProbeError("INVALID_NAME")
    else:
        if not ENV_NAME_RE.match(name):
            raise ProbeError("INVALID_NAME")
    return name


def _lookup(document, dotted_name: str):
    current = document
    for segment in dotted_name.split("."):
        if isinstance(current, dict) and segment in current:
            current = current[segment]
        else:
            return _MISSING
    return current


# --------------------------------------------------------------------------
# API thu vien
# --------------------------------------------------------------------------


def probe(
    env_name=None,
    file_path=None,
    file_format=None,
    name=None,
    environ=None,
):
    """Tra metadata cua dung mot bien. Xem docstring module."""
    if env_name is not None and file_path is not None:
        raise ProbeError("INVALID_ARGUMENTS")
    if env_name is not None:
        logical_name = validate_name(name or env_name, dotted=False)
        source_env = os.environ if environ is None else environ
        # chi doc dung bien duoc hoi, khong bao gio liet ke toan bo
        value = source_env.get(logical_name, _MISSING)
        if value is _MISSING:
            return describe_missing(logical_name, "env")
        payload = describe_value(value)
        payload.update({"name": logical_name, "source": "env"})
        return _ordered(payload)
    if file_path is not None:
        if file_format not in ALLOWED_FORMATS:
            raise ProbeError("INVALID_ARGUMENTS")
        logical_name = validate_name(name or "", dotted=file_format != "dotenv")
        text = _read_text_file(file_path)
        parser = _PARSERS[file_format]
        document = parser(text)
        if file_format == "dotenv":
            value = document.get(logical_name, _MISSING)
        else:
            value = _lookup(document, logical_name)
        if value is _MISSING:
            return describe_missing(logical_name, file_format)
        payload = describe_value(value)
        payload.update({"name": logical_name, "source": file_format})
        return _ordered(payload)
    raise ProbeError("INVALID_ARGUMENTS")


def _ordered(payload: dict) -> dict:
    return {
        "name": payload["name"],
        "source": payload["source"],
        "present": payload["present"],
        "type": payload["type"],
        "length": payload["length"],
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def parse_args(argv) -> dict:
    env_mode = False
    file_path = None
    file_format = None
    name = None
    index = 0
    while index < len(argv):
        token = argv[index]
        key, separator, value = token.partition("=")
        if key not in ("--env", "--file", "--format", "--name"):
            raise ProbeError("INVALID_ARGUMENTS")
        if key == "--env":
            if separator:
                raise ProbeError("INVALID_ARGUMENTS")
            env_mode = True
        else:
            if not separator:
                index += 1
                if index >= len(argv):
                    raise ProbeError("INVALID_ARGUMENTS")
                value = argv[index]
            if key == "--file":
                file_path = value
            elif key == "--format":
                file_format = value
            else:
                name = value
        index += 1
    if env_mode and file_path is not None:
        raise ProbeError("INVALID_ARGUMENTS")
    if not env_mode and file_path is None:
        raise ProbeError("INVALID_ARGUMENTS")
    if env_mode and file_format is not None:
        raise ProbeError("INVALID_ARGUMENTS")
    if file_path is not None and file_format not in ALLOWED_FORMATS:
        raise ProbeError("INVALID_ARGUMENTS")
    if not name:
        raise ProbeError("INVALID_ARGUMENTS")
    return {
        "env_mode": env_mode,
        "file_path": file_path,
        "file_format": file_format,
        "name": name,
    }


def _emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=True, sort_keys=True) + "\n")
    sys.stdout.flush()


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if any(item in ("-h", "--help") for item in args):
        sys.stdout.write(USAGE + "\n")
        return 0
    try:
        parsed = parse_args(args)
        result = probe(
            env_name=parsed["name"] if parsed["env_mode"] else None,
            file_path=parsed["file_path"],
            file_format=parsed["file_format"],
            name=parsed["name"],
        )
    except ProbeError as error:
        _emit({"error": str(error)})
        return 1
    except Exception:
        _emit({"error": "INTERNAL_ERROR"})
        return 1
    _emit(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
