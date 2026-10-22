"""Provider-usage accounting shared by the H2 and H3 evaluators.

Rules enforced here (from the experiment protocol, E3/E4):

* The total sums **all declared provider-call stages** (summary, extraction,
  retrieval, final) plus retries when supplied.
* A missing required stage makes the total **unknown**, never zero.
* A character/whitespace proxy is explicitly *forbidden* as a provider-token
  result; it yields an unknown total with a named reason, never a number.
* Cold-session and amortized costs are reported separately when supplied; the
  evaluator never infers a time saving.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from .common import (
    H3_USAGE_OPTIONAL_STAGES,
    H3_USAGE_REQUIRED_STAGES,
    require_int,
    require_mapping,
)
from .errors import SchemaError

CHARACTER_BASIS = ("character_proxy", "characters", "whitespace_proxy", "whitespace_units")


def parse_provider_usage(raw: Any, field: str = "usage") -> Dict[str, Any]:
    """Return a normalised usage summary.

    Shape::

        {
          "known": bool,
          "total": int | None,
          "reason": str | None,
          "stages": {stage: int|None, ...},
          "retries": int | None,
          "cold": object | None,        # passed through, never merged
          "amortized": object | None,   # passed through, never merged
        }
    """
    if raw is None:
        return {"known": False, "total": None, "reason": "usage_missing",
                "stages": {}, "retries": None, "cold": None, "amortized": None}

    usage = require_mapping(raw, field)
    basis = usage.get("usage_basis")
    if basis is None:
        return {"known": False, "total": None, "reason": "usage_basis_missing",
                "stages": {}, "retries": None,
                "cold": usage.get("cold"), "amortized": usage.get("amortized")}
    if not isinstance(basis, str):
        raise SchemaError(f"{field}.usage_basis: expected a string")
    if basis in CHARACTER_BASIS:
        return {"known": False, "total": None, "reason": "character_proxy_forbidden",
                "stages": {}, "retries": None,
                "cold": usage.get("cold"), "amortized": usage.get("amortized")}
    if basis != "provider_tokens":
        raise SchemaError(f"{field}.usage_basis: '{basis}' is not a recognised provider basis")

    stages = require_mapping(usage.get("stages"), f"{field}.stages")
    normalised: Dict[str, Optional[int]] = {}
    for stage in H3_USAGE_REQUIRED_STAGES:
        value = stages.get(stage)
        if value is None:
            return {"known": False, "total": None, "reason": f"missing_required_stage:{stage}",
                    "stages": {k: stages.get(k) for k in stages}, "retries": stages.get("retries"),
                    "cold": usage.get("cold"), "amortized": usage.get("amortized")}
        normalised[stage] = require_int(value, f"{field}.stages.{stage}", minimum=0)

    retries: Optional[int] = None
    if stages.get("retries") is not None:
        retries = require_int(stages["retries"], f"{field}.stages.retries", minimum=0)
        normalised["retries"] = retries
    for extra in H3_USAGE_OPTIONAL_STAGES:
        if extra in normalised:
            continue
        if stages.get(extra) is not None:
            normalised[extra] = require_int(stages[extra], f"{field}.stages.{extra}", minimum=0)

    total = sum(normalised[stage] for stage in H3_USAGE_REQUIRED_STAGES)
    if retries is not None:
        total += retries
    return {"known": True, "total": total, "reason": None, "stages": normalised,
            "retries": retries, "cold": usage.get("cold"), "amortized": usage.get("amortized")}
