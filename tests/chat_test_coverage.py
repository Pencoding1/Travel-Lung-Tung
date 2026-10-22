"""Behaviour-coverage registry for the two Agent Chat MVP test sets.

The rule from the owner: **both** sets must cover every behaviour clause listed
in the contract. A set that loses a clause is not allowed to run silently, so the
registry is machine-checked by ``scripts/run_chat_tests.py`` before pytest starts.

Clauses:
    B1 claim extraction          B5 planning input
    B2 significant intent        B6 scenario generation
    B3 grounded answer           B7 planning handoff
    B4 booking extraction        G1 no side effect from an information question
                                 G2 no unsupported data
"""

from __future__ import annotations

from pathlib import Path

REQUIRED_CLAUSES = ("B1", "B2", "B3", "B4", "B5", "B6", "B7", "G1", "G2")

# module file stem -> clauses it demonstrably exercises
EVALUATE_MODULES = {
    "test_b1_claim_extraction": ("B1",),
    "test_b2_significant_intent": ("B2",),
    "test_b3_grounded_answer": ("B3", "G2"),
    "test_b4_booking_extraction": ("B4",),
    "test_b5_planning_input": ("B5",),
    "test_b6_scenario_generation": ("B6",),
    "test_b7_planning_handoff": ("B7",),
    "test_g_global_constraints": ("G1",),
}

HIDDEN_MODULES = {
    "test_d0_seeds": ("B1", "B2", "B3", "B4", "B5", "B6", "B7", "G1"),
    "test_d1_paraphrase": ("B2", "B3"),
    "test_d2_entity_substitution": ("B3", "B4"),
    "test_d3_fabrication": ("B3", "G1", "G2"),
    "test_d4_fixture_swap": ("B3",),
    "test_d5_permutation": ("B1", "B2", "B4"),
    "test_d6_surface": ("B3",),
    "test_d7_boundaries": ("B5", "B7"),
    "test_d8_determinism": ("B3", "B4", "B5", "B6"),
    "test_d9_session_isolation": ("B1", "B3", "B4", "B5"),
    "test_d10_test_mode": ("G1",),
}

SETS = {
    "evaluate": {"dir": "tests/ai_chat_mvp", "modules": EVALUATE_MODULES,
                 "expected_tests": 20},
    "test": {"dir": "tests/ai_chat_mvp_hidden", "modules": HIDDEN_MODULES,
             "expected_tests": 100},
}


def inspect(set_name: str, repo_root: Path) -> dict:
    """Return {'missing_files': [...], 'missing_clauses': [...]} for one set."""
    spec = SETS[set_name]
    directory = repo_root / spec["dir"]
    missing_files = [stem for stem in spec["modules"]
                     if not (directory / f"{stem}.py").is_file()]
    covered = set()
    for stem, clauses in spec["modules"].items():
        if (directory / f"{stem}.py").is_file():
            covered.update(clauses)
    missing_clauses = [c for c in REQUIRED_CLAUSES if c not in covered]
    return {"directory": str(directory), "missing_files": missing_files,
            "missing_clauses": missing_clauses}


def describe(set_name: str) -> str:
    spec = SETS[set_name]
    rows = [f"{stem}.py -> {', '.join(clauses)}"
            for stem, clauses in spec["modules"].items()]
    covered = sorted({c for clauses in spec["modules"].values() for c in clauses})
    return (f"{set_name}: {spec['dir']} ({spec['expected_tests']} tests)\n  "
            + "\n  ".join(rows)
            + f"\n  clauses covered: {', '.join(covered)}")
