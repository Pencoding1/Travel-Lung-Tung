"""Frozen prompt templates and shared source-facts rendering.

Both conditions receive byte-identical *source facts*: the frozen scenario input
verbatim (candidates, directed routes, preferences, constraints, days). Only the
method instruction differs. ``author_expected`` lives in a sibling key of the
scenario entry and is therefore never rendered.

The two hashes exported per observation are:

* ``prompt_information_id`` — hash of the shared facts block (identical across
  the paired conditions);
* ``method_instruction_hash`` — hash of the condition instruction (differs).
"""

from __future__ import annotations

from typing import Any, Mapping

from .util import canonical_hash, canonical_json

FACTS_HEADER = "SOURCE FACTS (identical for both experimental conditions):\n"

LLM_ONLY_INSTRUCTION = (
    "You are the LLM-only itinerary condition. Produce a complete timed itinerary "
    "from the source facts alone, with no algorithmic repair.\n"
    "Return exactly one JSON object, no prose and no markdown, with this shape:\n"
    '{"status": "plan" | "no_plan", "no_plan_reason": <string|null>, '
    '"days": [{"day_id": <string>, "stops": [{"poi_id": <string>, '
    '"arrival": <ISO-8601 instant with UTC offset>, '
    '"departure": <ISO-8601 instant with UTC offset>}]}]}\n'
    "Rules: use only poi_id values that appear in the candidates; instants must be "
    "minute-resolution and timezone-aware; use status \"no_plan\" with a reason when "
    "you cannot produce a plan. Do not invent POIs, costs or routes."
)

HYBRID_INSTRUCTION = (
    "You are the hybrid-condition preference extractor. Do NOT schedule times "
    "yourself; a deterministic scheduler will place your chosen candidates.\n"
    "Return exactly one JSON object, no prose and no markdown, with this shape:\n"
    '{"ordered_poi_ids": [<poi_id>, ...], '
    '"day_assignment": {"<poi_id>": "<day_id>"}}\n'
    "Rules: list only candidate poi_id values, in your preferred visiting order "
    "(best first). day_assignment is optional and may be omitted. Do not invent "
    "POIs, costs or routes."
)

_INSTRUCTIONS = {
    "llm_only": LLM_ONLY_INSTRUCTION,
    "hybrid": HYBRID_INSTRUCTION,
}


class PromptError(ValueError):
    """Raised when a condition has no frozen instruction template."""


def scenario_facts(scenario_input: Mapping[str, Any]) -> dict:
    """The shared facts object: the frozen scenario input, unchanged."""
    if not isinstance(scenario_input, Mapping):
        raise PromptError("scenario input must be an object")
    return dict(scenario_input)


def render_facts_block(scenario_input: Mapping[str, Any]) -> str:
    """Deterministic textual rendering of the shared facts."""
    return FACTS_HEADER + canonical_json(scenario_facts(scenario_input))


def instruction_for(condition: str) -> str:
    try:
        return _INSTRUCTIONS[condition]
    except KeyError:
        raise PromptError(f"no frozen instruction for condition '{condition}'")


def build_prompt(condition: str, scenario_input: Mapping[str, Any]) -> str:
    instruction = instruction_for(condition)
    return f"{render_facts_block(scenario_input)}\n\nMETHOD INSTRUCTION:\n{instruction}\n"


def prompt_information_id(scenario_input: Mapping[str, Any]) -> str:
    return canonical_hash(scenario_facts(scenario_input))


def method_instruction_hash(condition: str) -> str:
    return canonical_hash({"condition": condition, "instruction": instruction_for(condition)})


def candidate_poi_ids(scenario_input: Mapping[str, Any]) -> list:
    """The declared candidate POI ids (all pois, including any depot)."""
    pois = scenario_input.get("pois") or []
    return sorted(
        str(poi.get("poi_id"))
        for poi in pois
        if isinstance(poi, Mapping) and poi.get("poi_id")
    )
