"""Recursive JSON-Schema enforcement for model-proposed tool calls."""

import json

import pytest
from domains.providers import ModelUnavailableError, convert_assistant_output


def _schema():
    return {
        "type": "object",
        "$defs": {
            "area": {
                "type": "object",
                "properties": {"id": {"type": "string", "minLength": 1}},
                "required": ["id"],
                "additionalProperties": False,
            },
        },
        "properties": {
            "mode": {"type": "string", "enum": ["walk", "drive"]},
            "count": {"type": "integer", "minimum": 1, "maximum": 10,
                      "multipleOf": 1},
            "area": {"$ref": "#/$defs/area"},
            "tags": {"type": "array", "items": {"type": "string",
                                                "pattern": "^[a-z]+$"},
                     "minItems": 1, "maxItems": 3, "uniqueItems": True},
            "when": {"type": "string", "format": "date-time"},
            "choice": {"anyOf": [{"type": "string"}, {"type": "integer"}]},
            "exact": {"oneOf": [{"type": "string"}, {"type": "number"}]},
            "ratio": {"type": "number", "exclusiveMinimum": 0,
                      "exclusiveMaximum": 1},
        },
        "required": ["mode", "count", "area"],
        "additionalProperties": False,
    }


def _payload(schema=None):
    return {"messages": [{"role": "user", "content": "synthetic"}],
            "tools": [{"type": "function", "function": {
                "name": "candidate_lookup",
                "parameters": schema or _schema()}}]}


def _convert(arguments, schema=None):
    envelope = {"tool_calls": [{"id": "call_1",
                                "name": "candidate_lookup",
                                "arguments": arguments}]}
    return convert_assistant_output(json.dumps(envelope), _payload(schema))


def _error(arguments, schema=None):
    with pytest.raises(ModelUnavailableError) as excinfo:
        _convert(arguments, schema)
    return excinfo.value.code


def test_realistic_schema_accepts_valid_nested_arguments():
    result = _convert({
        "mode": "walk",
        "count": 3,
        "area": {"id": "quan_1"},
        "tags": ["cafe", "park"],
        "when": "2026-01-01T09:00:00+07:00",
        "choice": 4,
        "exact": 1.5,
        "ratio": 0.5,
    })
    assert result["tool_calls"][0]["function"]["name"] == "candidate_lookup"


def test_parent_invalid_case_is_rejected():
    assert _error({"mode": "fly", "count": -8,
                   "area": {"id": True, "unexpected": 1}}) == \
        "invalid_tool_arguments"


@pytest.mark.parametrize("arguments", [
    {"mode": "fly", "count": 1, "area": {"id": "a"}},
    {"mode": "walk", "count": -8, "area": {"id": "a"}},
    {"mode": "walk", "count": 11, "area": {"id": "a"}},
    {"mode": "walk", "count": 1, "area": {"id": True}},
    {"mode": "walk", "count": 1, "area": {"id": "a", "unexpected": 1}},
    {"mode": "walk", "count": 1, "area": {}},
    {"mode": "walk", "count": 1, "area": {"id": "a"}, "tags": [1]},
    {"mode": "walk", "count": 1, "area": {"id": "a"}, "tags": ["a", "a"]},
    {"mode": "walk", "count": 1, "area": {"id": "a"}, "tags": []},
    {"mode": "walk", "count": 1, "area": {"id": "a"},
     "when": "not-a-date"},
    {"mode": "walk", "count": 1, "area": {"id": "a"}, "choice": True},
    {"mode": "walk", "count": 1, "area": {"id": "a"}, "exact": True},
    {"mode": "walk", "count": 1, "area": {"id": "a"}, "ratio": 0},
    {"mode": "walk", "count": 1, "area": {"id": "a"}, "ratio": 1},
])
def test_nested_constraints_are_enforced(arguments):
    assert _error(arguments) == "invalid_tool_arguments"


def test_unsupported_validation_keyword_fails_before_execution():
    schema = {"type": "object", "patternProperties": {"^x": {"type": "string"}}}
    assert _error({"x": "a"}, schema) == "unsupported_tool_schema"


def test_recursive_ref_cycle_is_unsupported():
    schema = {"$defs": {"a": {"$ref": "#/$defs/a"}},
              "$ref": "#/$defs/a"}
    assert _error({}, schema) == "unsupported_tool_schema"


def test_all_of_and_type_unions_are_supported():
    schema = {"allOf": [{"type": "object",
                         "properties": {"x": {"type": ["string", "null"]}},
                         "required": ["x"]}],
              "type": "object"}
    assert _convert({"x": None}, schema)["tool_calls"]
    assert _convert({"x": "a"}, schema)["tool_calls"]


def test_nonfinite_and_duplicate_json_are_rejected():
    with pytest.raises(ModelUnavailableError) as excinfo:
        _convert({"mode": "walk", "count": float("nan"),
                  "area": {"id": "a"}})
    assert excinfo.value.code == "invalid_tool_envelope"

    with pytest.raises(ModelUnavailableError) as excinfo:
        _convert({"mode": "walk", "count": 1e999, "area": {"id": "a"}})
    assert excinfo.value.code == "invalid_tool_envelope"

    duplicate = ('{"tool_calls":[{"id":"call_1","name":"candidate_lookup",'
                 '"arguments":{"mode":"walk","count":1,"count":2,'
                 '"area":{"id":"a"}}}]}')
    with pytest.raises(ModelUnavailableError) as excinfo:
        convert_assistant_output(duplicate, _payload())
    assert excinfo.value.code == "invalid_tool_envelope"

    literal_overflow = ('{"tool_calls":[{"id":"call_1",'
                        '"name":"candidate_lookup","arguments":'
                        '{"mode":"walk","count":1e999,'
                        '"area":{"id":"a"}}}]}')
    with pytest.raises(ModelUnavailableError) as excinfo:
        convert_assistant_output(literal_overflow, _payload())
    assert excinfo.value.code == "invalid_tool_arguments"

    huge_integer = ('{"tool_calls":[{"id":"call_1",'
                    '"name":"candidate_lookup","arguments":'
                    '{"mode":"walk","count":' + ("9" * 400) + ','
                    '"area":{"id":"a"}}}]}')
    with pytest.raises(ModelUnavailableError) as excinfo:
        convert_assistant_output(huge_integer, _payload())
    assert excinfo.value.code == "invalid_tool_arguments"


def test_argument_depth_bound_is_bounded():
    schema = {"type": "object"}
    value = "x"
    for _ in range(40):
        value = {"nested": value}
    assert _error(value, schema) == "invalid_tool_arguments"
