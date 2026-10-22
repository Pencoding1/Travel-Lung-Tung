#!/usr/bin/env python
"""Single entry point for the Agent Chat MVP test suites.

    python scripts/run_chat_tests.py --evaluate     # 20 spec tests (agent-visible)
    python scripts/run_chat_tests.py --test         # 100 developer tests (hidden)
    python scripts/run_chat_tests.py --test -- -x   # extra pytest args after --

Both modes are behaviour-complete by construction: every clause (B1-B7, G1, G2)
must appear in the selected set, otherwise the runner refuses to run instead of
quietly passing a partial suite.

If the hidden folder has been cut out of the repository, ``--test`` falls back to
the evaluate set and says so explicitly.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TESTS_ROOT = REPO_ROOT / "tests"
if str(TESTS_ROOT) not in sys.path:
    sys.path.insert(0, str(TESTS_ROOT))

import chat_test_coverage as coverage  # noqa: E402


def _pytest() -> list[str]:
    return [sys.executable, "-m", "pytest"]


def _collect_count(directory: Path) -> int:
    result = subprocess.run(
        _pytest() + [str(directory), "--collect-only", "-q", "--no-header",
                     "-p", "no:cacheprovider"],
        cwd=str(REPO_ROOT), capture_output=True, text=True)
    for line in reversed(result.stdout.splitlines()):
        line = line.strip()
        if "test" in line and ("collected" in line or line.endswith("test")):
            number = line.split()[0]
            if number.isdigit():
                return int(number)
    return -1


def _check(set_name: str) -> int:
    report = coverage.inspect(set_name, REPO_ROOT)
    problems = []
    if report["missing_files"]:
        problems.append("missing test modules: " + ", ".join(report["missing_files"]))
    if report["missing_clauses"]:
        problems.append("missing behaviour clauses: " + ", ".join(report["missing_clauses"]))
    if problems:
        print(f"REFUSED: the {set_name} set is not behaviour-complete.")
        for problem in problems:
            print(f"  - {problem}")
        print("Every clause (B1-B7, G1, G2) must be covered in both sets.")
        return 2
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Run one Agent Chat MVP test set.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--evaluate", action="store_true",
                       help="run the 20 agent-visible spec tests")
    group.add_argument("--test", action="store_true",
                       help="run the 100 hidden developer tests (falls back to evaluate)")
    parser.add_argument("--mode", choices=("evaluate", "test"),
                        help="alternative spelling of the flags above")
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER,
                        help="extra arguments passed to pytest (put them after --)")
    args = parser.parse_args(argv)

    set_name = "test" if (args.test or args.mode == "test") else "evaluate"
    target = Path(coverage.SETS[set_name]["dir"])
    directory = REPO_ROOT / target
    fallback_note = ""

    if set_name == "test" and not directory.is_dir():
        print(f"[run_chat_tests] hidden set not found at {target}.", flush=True)
        print("[run_chat_tests] falling back to the evaluate set (20 tests).",
              flush=True)
        set_name = "evaluate"
        target = Path(coverage.SETS[set_name]["dir"])
        directory = REPO_ROOT / target
        fallback_note = " (fallback)"

    status = _check(set_name)
    if status != 0:
        return status

    expected = coverage.SETS[set_name]["expected_tests"]
    collected = _collect_count(directory)
    if collected != expected:
        print(f"REFUSED: {target} collects {collected} tests, expected {expected}.")
        print("A suite that lost cases must not run as if it were complete.")
        return 3

    print(f"[run_chat_tests] mode={set_name}{fallback_note} dir={target} "
          f"tests={collected}", flush=True)
    print(coverage.describe(set_name), flush=True)

    extra = [a for a in args.pytest_args if a != "--"]
    command = _pytest() + [str(directory), "-q"] + extra
    return subprocess.call(command, cwd=str(REPO_ROOT))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
