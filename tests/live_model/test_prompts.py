from __future__ import annotations

from live_model import prompts
from live_model.runner import DEFAULT_SCENARIOS, load_scenario_inputs


def test_author_expected_never_rendered():
    scenarios = load_scenario_inputs(DEFAULT_SCENARIOS)
    s03 = scenarios["S03"]
    prompt = prompts.build_prompt("llm_only", s03)
    # A property string from S03's author_expected must not leak into the prompt.
    assert "budget_exceeded exclusion" not in prompt
    assert "author_expected" not in prompt


def test_shared_facts_identical_across_arms():
    scenarios = load_scenario_inputs(DEFAULT_SCENARIOS)
    s01 = scenarios["S01"]
    assert prompts.prompt_information_id(s01) == prompts.prompt_information_id(s01)
    llm = prompts.build_prompt("llm_only", s01)
    hybrid = prompts.build_prompt("hybrid", s01)
    facts = prompts.render_facts_block(s01)
    assert llm.startswith(facts)
    assert hybrid.startswith(facts)


def test_method_instruction_hash_differs_between_conditions():
    assert prompts.method_instruction_hash("llm_only") != prompts.method_instruction_hash("hybrid")
    assert prompts.method_instruction_hash("llm_only") == prompts.method_instruction_hash("llm_only")


def test_candidate_poi_ids_from_candidates_only():
    scenarios = load_scenario_inputs(DEFAULT_SCENARIOS)
    assert prompts.candidate_poi_ids(scenarios["S01"]) == ["p_cafe", "p_food"]
    assert prompts.candidate_poi_ids(scenarios["S12"]) == []
