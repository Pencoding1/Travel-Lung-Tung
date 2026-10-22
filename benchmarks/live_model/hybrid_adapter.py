"""Adapter that maps the hybrid model's candidate order onto the production scheduler.

The evaluated **hybrid** algorithm is the *production* scheduler
(:func:`domains.planning.schedule`) — the same function the application calls — not
a collector-local reimplementation. The previous collector-local
``schedule_from_order`` has been removed.

The model returns an ordered list of candidate ``poi_id`` values and an optional
``day_assignment``. The production scheduler ranks candidates by:

1. hard requirement coverage (outstanding required categories / unsatisfied meal
   categories) — always dominates;
2. descending *category preference weight*;
3. ascending directed travel time;
4. ascending ``poi_id``.

It has **no** notion of an arbitrary per-POI order and **no** ability to pin a POI
to a declared day. The adapter therefore never claims the scheduler follows the
model's literal order.

Documented mapping (the **only** mutation of the typed scenario):

* Each ordered candidate at 0-based index ``i`` of ``N`` contributes
  ``weight = N - i`` to every category it belongs to. Per-category contributions
  are summed and **added** to the scenario's declared category weights.
* The model contribution is a real input to ranking: it changes the
  descending-preference tie-break. It does not override hard requirements, and it
  does not pin a POI to a day.
* ``day_assignment`` is validated and recorded as evidence but explicitly marked
  ``honored: false`` — the production scheduler cannot honor it.
* Unknown / depot candidates are recorded, never turned into facts.
* Every other scenario fact (required categories, meal windows, day windows, route
  edges, costs, budget, unknowns) is preserved byte-for-byte through
  :func:`dataclasses.replace`.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, List, Mapping, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[2]
_AI_ROOT = _REPO_ROOT / "ai_service"
if str(_AI_ROOT) not in sys.path:
    sys.path.insert(0, str(_AI_ROOT))

from domains.planning import schedule as production_schedule  # noqa: E402
from domains.planning.contracts import Plan, Scenario, parse_scenario  # noqa: E402

from .constants import METHOD_VERSION
from .schema import HybridOrder

RANKING_SEMANTICS = (
    "hard_requirement_coverage_then_descending_category_preference_then_"
    "ascending_travel_then_poi_id"
)


def model_category_weights(scenario: Scenario, order: HybridOrder
                           ) -> Tuple[Dict[str, int], Dict[str, Any]]:
    """Translate the model's POI order into additive category preference weights."""
    depots = {d for d in (scenario.start_depot_id, scenario.end_depot_id) if d}
    total = len(order.ordered_poi_ids)

    weights: Dict[str, int] = {}
    known: List[str] = []
    unknown: List[str] = []
    depot_refs: List[str] = []
    for index, poi_id in enumerate(order.ordered_poi_ids):
        if poi_id in depots:
            depot_refs.append(poi_id)
            continue
        poi = scenario.poi(poi_id)
        if poi is None:
            unknown.append(poi_id)
            continue
        known.append(poi_id)
        contribution = total - index
        for category_id in poi.category_ids:
            weights[category_id] = weights.get(category_id, 0) + contribution

    day_ids = {day.day_id for day in scenario.days}
    unknown_assignment_days = sorted(
        {day_id for day_id in order.day_assignment.values() if day_id not in day_ids})
    info: Dict[str, Any] = {
        "known_ordered_pois": known,
        "unknown_pois": unknown,
        "depot_pois": depot_refs,
        "unknown_assignment_days": unknown_assignment_days,
    }
    return weights, info


def adapt(scenario_input: Mapping[str, Any], order: HybridOrder
          ) -> Tuple[Scenario, Dict[str, Any]]:
    """Return ``(adapted_scenario, mapping_report)``.

    The adapted scenario is the production-scheduler input; the mapping report is
    the machine-readable disclosure of exactly what the model contributed and what
    the scheduler does with it.
    """
    base = parse_scenario(dict(scenario_input))
    model_weights, info = model_category_weights(base, order)

    base_weights = dict(base.preferences or {})
    effective = dict(base_weights)
    for category_id, weight in model_weights.items():
        effective[category_id] = effective.get(category_id, 0) + weight

    adapted = replace(base, preferences=effective)

    mapping: Dict[str, Any] = {
        "algorithm": "domains.planning.schedule",
        "method_version": METHOD_VERSION,
        "model_ordered_poi_ids": list(order.ordered_poi_ids),
        "model_day_assignment": dict(order.day_assignment),
        "day_assignment_honored": False,
        "ranking_semantics": RANKING_SEMANTICS,
        "model_category_weights": model_weights,
        "base_category_weights": base_weights,
        "effective_category_weights": effective,
        "notes": [
            "evaluated hybrid algorithm is the production scheduler",
            "model order maps to additive category preference weights only",
            "production scheduler ranks by hard requirements then preference then "
            "travel then poi_id; it does not follow an arbitrary per-POI order",
            "day_assignment is recorded but not honored by the production scheduler",
        ],
    }
    mapping.update(info)
    return adapted, mapping


def schedule_hybrid(scenario_input: Mapping[str, Any], order: HybridOrder
                    ) -> Tuple[Scenario, Plan, Dict[str, Any]]:
    """Run the **production** scheduler on the model-adapted scenario."""
    adapted, mapping = adapt(scenario_input, order)
    plan = production_schedule(adapted)
    mapping["plan_notes"] = list(plan.notes)
    return adapted, plan, mapping
