"""JSON Pointer resolver tests."""

import pytest

from crawler_service.app.acquisition.jsonptr import (
    PointerError,
    build_pointer,
    resolve_pointer,
)


def test_resolve_objects_and_arrays():
    document = {"a": {"b": [10, {"c": "x"}]}}
    assert resolve_pointer(document, "/a/b/1/c") == "x"
    assert resolve_pointer(document, "") is document


def test_escape_and_unescape_slash_and_tilde():
    document = {"entities": {"osm/node/1": {"name": "n"}, "a~b": 1}}
    pointer = build_pointer("entities", "osm/node/1", "name")
    assert pointer == "/entities/osm~1node~11/name"
    assert resolve_pointer(document, pointer) == "n"
    assert resolve_pointer(document, build_pointer("entities", "a~b")) == 1


@pytest.mark.parametrize("pointer", ["/missing", "/a/b/9", "a/b", "/a/b/x/c"])
def test_invalid_pointers_raise(pointer):
    with pytest.raises(PointerError):
        resolve_pointer({"a": {"b": [10]}}, pointer)
