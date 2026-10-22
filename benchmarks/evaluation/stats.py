"""Exact and resampling statistics used by the OC-018 evaluator.

Only stdlib is used. Two procedures are exposed:

* :func:`exact_mcnemar_two_sided` — the exact two-sided McNemar/binomial test
  for a **declared single binary scenario outcome**. It is never applied to
  repetitions as if they were independent scenarios.
* :func:`paired_effect_bootstrap_ci` — a scenario bootstrap of the paired
  effect. The percentile method and a fixed seed make the interval
  reproducible.
"""

from __future__ import annotations

import math
import random
from typing import Dict, List, Optional, Sequence

DEFAULT_BOOTSTRAP_SEED = 20261015
DEFAULT_BOOTSTRAP_DRAWS = 10000
DEFAULT_CI_LOWER = 2.5
DEFAULT_CI_UPPER = 97.5


def exact_mcnemar_two_sided(discordant_a: int, discordant_b: int) -> Dict[str, object]:
    """Exact two-sided McNemar test.

    ``discordant_a`` counts pairs where condition A is positive and B negative;
    ``discordant_b`` the reverse. With no discordant pairs the exact test is
    uninformative (p = 1.0) and that fact is disclosed explicitly.
    """
    if discordant_a < 0 or discordant_b < 0:
        raise ValueError("discordant counts must be nonnegative")
    n = discordant_a + discordant_b
    if n == 0:
        return {
            "available": True,
            "p_value": 1.0,
            "discordant_a_only": 0,
            "discordant_b_only": 0,
            "discordant_total": 0,
            "note": "no discordant pairs; exact test is uninformative (p = 1.0)",
        }
    smaller = min(discordant_a, discordant_b)
    tail = sum(math.comb(n, k) for k in range(smaller + 1))
    p_value = min(1.0, 2.0 * tail / (2 ** n))
    return {
        "available": True,
        "p_value": p_value,
        "discordant_a_only": discordant_a,
        "discordant_b_only": discordant_b,
        "discordant_total": n,
        "note": "exact two-sided binomial test with p = 0.5",
    }


def percentile(sorted_values: Sequence[float], quantile: float) -> Optional[float]:
    """Linear-interpolation percentile of an already-sorted sequence.

    ``quantile`` is in [0, 100]. This is the method documented in the runbook.
    """
    n = len(sorted_values)
    if n == 0:
        return None
    if quantile <= 0:
        return float(sorted_values[0])
    if quantile >= 100:
        return float(sorted_values[-1])
    if n == 1:
        return float(sorted_values[0])
    position = (n - 1) * (quantile / 100.0)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(sorted_values[lower])
    fraction = position - lower
    return float(sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * fraction)


def paired_effect_bootstrap_ci(
    pair_effects: Sequence[float],
    *,
    seed: int = DEFAULT_BOOTSTRAP_SEED,
    draws: int = DEFAULT_BOOTSTRAP_DRAWS,
    lower_quantile: float = DEFAULT_CI_LOWER,
    upper_quantile: float = DEFAULT_CI_UPPER,
) -> Dict[str, object]:
    """Scenario bootstrap (percentile) CI for a paired effect.

    Each element of ``pair_effects`` is one **scenario** (already aggregated
    across repetitions). With fewer than two scenarios the interval is
    unavailable; a point estimate is still reported.
    """
    n = len(pair_effects)
    if n == 0:
        return {
            "available": False, "reason": "no_pairs", "point": None,
            "lower": None, "upper": None, "method": "percentile",
            "seed": seed, "draws": 0, "percentiles": [lower_quantile, upper_quantile],
        }
    point = sum(pair_effects) / n
    if n < 2:
        return {
            "available": False, "reason": "insufficient_pairs_for_bootstrap",
            "point": point, "lower": None, "upper": None, "method": "percentile",
            "seed": seed, "draws": 0, "percentiles": [lower_quantile, upper_quantile],
        }

    rng = random.Random(seed)
    resampled_means: List[float] = []
    for _ in range(draws):
        total = 0.0
        for _ in range(n):
            total += pair_effects[rng.randrange(n)]
        resampled_means.append(total / n)
    resampled_means.sort()
    return {
        "available": True,
        "reason": None,
        "point": point,
        "lower": percentile(resampled_means, lower_quantile),
        "upper": percentile(resampled_means, upper_quantile),
        "method": "percentile",
        "seed": seed,
        "draws": draws,
        "percentiles": [lower_quantile, upper_quantile],
    }
