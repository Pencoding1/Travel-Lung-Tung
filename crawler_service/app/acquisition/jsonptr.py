"""RFC 6901 JSON Pointer helpers.

Adapters emit JSON Pointers that address the *actual* parsed raw document, and
tests resolve those pointers against the same document to prove that every
recorded fact path is real.
"""

from __future__ import annotations

from typing import Any, List


class PointerError(KeyError):
    """Raised when a JSON Pointer does not resolve against a document."""


def escape_token(token: str) -> str:
    return str(token).replace("~", "~0").replace("/", "~1")


def build_pointer(*tokens: Any) -> str:
    if not tokens:
        return ""
    return "".join(f"/{escape_token(token)}" for token in tokens)


def resolve_pointer(document: Any, pointer: str) -> Any:
    """Resolve an RFC 6901 pointer; the empty pointer returns the document."""

    if pointer == "":
        return document
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise PointerError(f"invalid JSON pointer: {pointer!r}")
    current = document
    for raw_token in pointer.split("/")[1:]:
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            try:
                index = int(token)
            except ValueError as exc:
                raise PointerError(f"non-integer list index {token!r}") from exc
            if index < 0 or index >= len(current):
                raise PointerError(f"list index out of range: {index}")
            current = current[index]
        elif isinstance(current, dict):
            if token not in current:
                raise PointerError(f"missing key {token!r} in {pointer!r}")
            current = current[token]
        else:
            raise PointerError(f"cannot descend into {type(current).__name__}")
    return current


def split_pointer(pointer: str) -> List[str]:
    if pointer == "":
        return []
    return [
        token.replace("~1", "/").replace("~0", "~")
        for token in pointer.split("/")[1:]
    ]
