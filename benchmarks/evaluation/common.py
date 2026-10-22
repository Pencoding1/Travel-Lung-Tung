"""Shared stdlib-only validation helpers and evidence constants.

These helpers deliberately reject ambiguous input (``bool`` where an ``int`` is
expected, blank strings, fractional repetition indices, ``NaN``/``Inf``). The
evaluator must never guess a value, because a guessed value would enter a
denominator as if it were evidence.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from .errors import SchemaError

EVALUATOR_VERSION = "oc18.eval.v1"

EVIDENCE_LEVELS = ("synthetic_engineering", "live_model")
SYNTHETIC_LABEL = "SYNTHETIC EVALUATOR TEST"
LIVE_LABEL = "LIVE-EVIDENCE EVALUATION (requires owner review; not an automatic thesis conclusion)"
INCONCLUSIVE_LABEL = "EVALUATOR CORRECTNESS OUTPUT (no inferential claim)"

# The primary binary H2 outcome is declared explicitly, so the exact McNemar
# test cannot be repurposed onto secondary outcomes by accident.
H2_PRIMARY_BINARY_OUTCOME = "scenario_has_verified_temporal_violation"

H3_CONDITIONS = ("memory_disabled", "short_term", "two_tier")
H3_BASELINE_CONDITION = "memory_disabled"
H3_USAGE_REQUIRED_STAGES = ("summary", "extraction", "retrieval", "final")
H3_USAGE_OPTIONAL_STAGES = ("retries",)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_hash(value: Any) -> str:
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256_bytes(text.encode("utf-8"))


def require_mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise SchemaError(f"{field}: expected a JSON object")
    return value


def require_list(value: Any, field: str) -> List[Any]:
    if not isinstance(value, list):
        raise SchemaError(f"{field}: expected a JSON array")
    return value


def require_nonblank_str(value: Any, field: str) -> str:
    if isinstance(value, bool) or not isinstance(value, str) or not value.strip():
        raise SchemaError(f"{field}: expected a nonblank string")
    return value.strip()


def require_int(value: Any, field: str, *, minimum: Optional[int] = None,
                maximum: Optional[int] = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SchemaError(f"{field}: expected an integer (bools rejected)")
    if minimum is not None and value < minimum:
        raise SchemaError(f"{field}: must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise SchemaError(f"{field}: must be <= {maximum}")
    return value


def require_bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise SchemaError(f"{field}: expected a boolean")
    return value


def require_bool_or_null(value: Any, field: str) -> Optional[bool]:
    if value is None:
        return None
    return require_bool(value, field)


def require_int_or_null(value: Any, field: str, *, minimum: Optional[int] = None) -> Optional[int]:
    if value is None:
        return None
    return require_int(value, field, minimum=minimum)


def require_number_or_null(value: Any, field: str) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SchemaError(f"{field}: expected a number or null")
    number = float(value)
    if math.isnan(number) or math.isinf(number):
        raise SchemaError(f"{field}: NaN/Inf are not allowed")
    return number


def require_enum(value: Any, field: str, allowed: Iterable[str]) -> str:
    text = require_nonblank_str(value, field)
    allowed_tuple = tuple(allowed)
    if text not in allowed_tuple:
        raise SchemaError(f"{field}: '{text}' not in {allowed_tuple}")
    return text


def require_str_list(value: Any, field: str) -> List[str]:
    items = require_list(value, field)
    return [require_nonblank_str(item, f"{field}[{index}]") for index, item in enumerate(items)]


def optional_mapping(value: Any, field: str) -> Optional[Mapping[str, Any]]:
    if value is None:
        return None
    return require_mapping(value, field)


def assert_unique(values: Sequence[str], field: str) -> None:
    seen: Dict[str, int] = {}
    for index, item in enumerate(values):
        if item in seen:
            raise SchemaError(f"{field}: duplicate value '{item}' (index {seen[item]} and {index})")
        seen[item] = index
