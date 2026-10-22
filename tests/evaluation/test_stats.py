"""Exact/statistics correctness for the OC-018 evaluator (stdlib only)."""

import pytest

from evaluation.stats import (
    exact_mcnemar_two_sided,
    paired_effect_bootstrap_ci,
    percentile,
)


@pytest.mark.parametrize("a,b,expected", [
    (0, 0, 1.0),        # no discordant pairs -> uninformative, p = 1
    (1, 0, 1.0),        # 2 * C(1,0) * 0.5
    (3, 0, 0.25),       # 2 * C(3,0) * 0.125
    (5, 0, 0.0625),     # 2 * C(5,0) * 0.03125
    (2, 1, 1.0),        # 2 * (C(3,0)+C(3,1)) * 0.125 = 1.0
])
def test_exact_mcnemar_known_tiny_cases(a, b, expected):
    result = exact_mcnemar_two_sided(a, b)
    assert result["discordant_total"] == a + b
    assert result["p_value"] == pytest.approx(expected)


def test_mcnemar_rejects_negative():
    with pytest.raises(ValueError):
        exact_mcnemar_two_sided(-1, 0)


def test_percentile_linear_interpolation():
    values = [1.0, 2.0, 3.0, 4.0]
    assert percentile(values, 0) == 1.0
    assert percentile(values, 100) == 4.0
    assert percentile(values, 50) == pytest.approx(2.5)
    assert percentile([7.0], 50) == 7.0
    assert percentile([], 50) is None


def test_bootstrap_is_seed_repeatable():
    deltas = [1.0, -1.0, 0.0, 1.0, 0.0, -1.0, 1.0]
    first = paired_effect_bootstrap_ci(deltas, seed=123, draws=500)
    second = paired_effect_bootstrap_ci(deltas, seed=123, draws=500)
    assert first["available"] is True
    assert first["lower"] == second["lower"]
    assert first["upper"] == second["upper"]
    assert first["point"] == pytest.approx(sum(deltas) / len(deltas))


def test_bootstrap_unavailable_for_single_pair():
    result = paired_effect_bootstrap_ci([1.0], seed=1, draws=100)
    assert result["available"] is False
    assert result["reason"] == "insufficient_pairs_for_bootstrap"
    assert result["point"] == 1.0


def test_bootstrap_unavailable_for_no_pairs():
    result = paired_effect_bootstrap_ci([], seed=1, draws=100)
    assert result["available"] is False
    assert result["reason"] == "no_pairs"
