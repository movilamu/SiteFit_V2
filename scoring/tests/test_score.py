"""Deterministic tests for the scoring engine.

These tests cover the two deliberate corrections documented in
``scoring/score.py``:

1. strict weight alignment, and
2. consistent weight scaling across the aggregation methods.

They also lock in the behaviour that the rest of the platform depends on:
hand-verifiable aggregation results, empty-matrix handling, NaN imputation
and stable ranking.
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from scoring.score import METHODS, apply_weights, rank_sites


# ---------------------------------------------------------------------------
# Aggregation formulas
# ---------------------------------------------------------------------------

def test_weighted_sum_matches_the_hand_verifiable_example() -> None:
    matrix = pd.DataFrame(
        {"a": [0.8, 0.2], "b": [0.4, 1.0]},
        index=["site-1", "site-2"],
    )
    scores = apply_weights(matrix, {"a": 0.6, "b": 0.4})

    # A = 0.6 * 0.8 + 0.4 * 0.4 = 0.64
    # B = 0.6 * 0.2 + 0.4 * 1.0 = 0.52
    assert scores["site-1"] == pytest.approx(0.64)
    assert scores["site-2"] == pytest.approx(0.52)


def test_weighted_product_matches_the_hand_verifiable_example() -> None:
    matrix = pd.DataFrame(
        {"a": [0.8, 0.2], "b": [0.4, 1.0]},
        index=["site-1", "site-2"],
    )
    scores = apply_weights(matrix, {"a": 0.6, "b": 0.4}, method="weighted_product")

    assert scores["site-1"] == pytest.approx((0.8**0.6) * (0.4**0.4))
    assert scores["site-2"] == pytest.approx((0.2**0.6) * (1.0**0.4))


def test_distance_to_ideal_returns_relative_closeness() -> None:
    matrix = pd.DataFrame(
        {
            "a": [0.0, 0.2, 0.5, 1.0],
            "b": [0.0, 0.3, 0.6, 1.0],
        },
        index=["low", "below", "above", "high"],
    )
    scores = apply_weights(matrix, {"a": 0.5, "b": 0.5}, method="distance_to_ideal")

    assert scores["high"] > scores["above"] > scores["below"] > scores["low"]
    assert 0.0 <= scores.min() <= scores.max() <= 1.0


def test_distance_to_ideal_gives_identical_sites_the_midpoint() -> None:
    matrix = pd.DataFrame(
        {"a": [0.4, 0.4], "b": [0.7, 0.7]},
        index=["site-1", "site-2"],
    )
    scores = apply_weights(matrix, {"a": 0.5, "b": 0.5}, method="distance_to_ideal")

    assert scores["site-1"] == pytest.approx(0.5)
    assert scores["site-2"] == pytest.approx(0.5)


def test_identical_sites_receive_the_same_score() -> None:
    matrix = pd.DataFrame(
        {"a": [0.4, 0.4], "b": [0.7, 0.7]},
        index=["site-1", "site-2"],
    )
    scores = apply_weights(matrix, {"a": 0.5, "b": 0.5})
    assert scores["site-1"] == pytest.approx(scores["site-2"])


# ---------------------------------------------------------------------------
# Strict weight alignment
# ---------------------------------------------------------------------------

def test_partial_weight_mapping_is_rejected() -> None:
    matrix = pd.DataFrame({"a": [0.5], "b": [0.5]}, index=["site-1"])

    with pytest.raises(ValueError, match="missing weights"):
        apply_weights(matrix, {"a": 1.0})


def test_partial_weight_mapping_names_the_missing_criteria() -> None:
    matrix = pd.DataFrame(
        {"resident_density": [0.5], "rent": [0.5]}, index=["site-1"]
    )

    with pytest.raises(ValueError) as excinfo:
        apply_weights(matrix, {"resident_density": 1.0})

    assert "rent" in str(excinfo.value)


def test_weight_mapping_in_a_different_order_is_still_aligned_by_name() -> None:
    matrix = pd.DataFrame(
        {"a": [0.8, 0.2], "b": [0.4, 1.0]},
        index=["site-1", "site-2"],
    )
    # The mapping order is the reverse of the column order.  A positional
    # fallback would swap the weights and change the scores.
    scores = apply_weights(matrix, {"b": 0.4, "a": 0.6})

    assert scores["site-1"] == pytest.approx(0.64)
    assert scores["site-2"] == pytest.approx(0.52)


def test_extra_weights_in_the_mapping_are_ignored() -> None:
    matrix = pd.DataFrame({"a": [0.5]}, index=["site-1"])
    scores = apply_weights(matrix, {"a": 1.0, "unused": 5.0})
    assert scores["site-1"] == pytest.approx(0.5)


def test_sequence_weights_must_match_the_column_count() -> None:
    matrix = pd.DataFrame({"a": [0.5], "b": [0.5]}, index=["site-1"])

    with pytest.raises(ValueError, match="exactly one weight per criterion"):
        apply_weights(matrix, [1.0])


# ---------------------------------------------------------------------------
# Consistent weight scaling
# ---------------------------------------------------------------------------

def test_scaling_the_weights_does_not_change_the_ranking() -> None:
    matrix = pd.DataFrame(
        {"a": [0.8, 0.2, 0.5], "b": [0.4, 1.0, 0.5]},
        index=["site-1", "site-2", "site-3"],
    )
    normalised = apply_weights(matrix, {"a": 0.6, "b": 0.4})
    scaled = apply_weights(matrix, {"a": 3.0, "b": 2.0})

    assert list(normalised.sort_values(ascending=False).index) == list(
        scaled.sort_values(ascending=False).index
    )


def test_every_method_sees_the_same_effective_weighting() -> None:
    """A weight vector that does not sum to 1 must not be treated differently
    by different aggregation methods.

    The weighted product is not scale invariant, so without the
    normalisation in ``apply_weights`` the three methods would analyse
    different models.
    """

    matrix = pd.DataFrame(
        {"a": [0.8, 0.2], "b": [0.4, 1.0]},
        index=["site-1", "site-2"],
    )
    weights = {"a": 3.0, "b": 2.0}
    normalised = {"a": 0.6, "b": 0.4}

    for method in METHODS:
        scaled = apply_weights(matrix, weights, method=method)
        unit = apply_weights(matrix, normalised, method=method)
        for site_id in matrix.index:
            assert scaled[site_id] == pytest.approx(unit[site_id]), method


def test_zero_weights_are_preserved() -> None:
    matrix = pd.DataFrame({"a": [0.8, 0.2], "b": [0.4, 1.0]}, index=["s1", "s2"])
    scores = apply_weights(matrix, {"a": 1.0, "b": 0.0})
    assert scores["s1"] == pytest.approx(0.8)
    assert scores["s2"] == pytest.approx(0.2)


def test_a_zero_weight_vector_is_rejected() -> None:
    matrix = pd.DataFrame({"a": [0.5]}, index=["s1"])

    with pytest.raises(ValueError, match="at least one weight greater than zero"):
        apply_weights(matrix, {"a": 0.0})


def test_negative_weights_are_rejected() -> None:
    matrix = pd.DataFrame({"a": [0.5], "b": [0.5]}, index=["s1"])

    with pytest.raises(ValueError, match="non-negative"):
        apply_weights(matrix, {"a": 1.5, "b": -0.5})


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_an_empty_matrix_returns_an_empty_series() -> None:
    matrix = pd.DataFrame(columns=["a", "b"], dtype=float)
    scores = apply_weights(matrix, {"a": 0.5, "b": 0.5})
    assert len(scores) == 0


def test_nan_values_are_imputed_with_the_column_minimum() -> None:
    matrix = pd.DataFrame(
        {"a": [0.8, float("nan"), 0.4], "b": [0.4, 0.5, 1.0]},
        index=["s1", "s2", "s3"],
    )
    scores = apply_weights(matrix, {"a": 0.5, "b": 0.5})

    # The imputed value for "a" is the observed minimum (0.4).
    assert scores["s2"] == pytest.approx(0.4 * 0.5 + 0.5 * 0.5)


def test_an_unknown_method_is_rejected() -> None:
    matrix = pd.DataFrame({"a": [0.5]}, index=["s1"])

    with pytest.raises(ValueError, match="Unknown aggregation method"):
        apply_weights(matrix, {"a": 1.0}, method="not_a_method")


def test_rank_sites_assigns_strict_ranks_best_first() -> None:
    matrix = pd.DataFrame(
        {"a": [0.2, 0.9, 0.5]},
        index=["low", "high", "mid"],
    )
    ranked = rank_sites(apply_weights(matrix, {"a": 1.0}))

    assert list(ranked["site_id"]) == ["high", "mid", "low"]
    assert list(ranked["rank"]) == [1, 2, 3]


def test_rank_sites_uses_the_index_as_the_site_identifier() -> None:
    matrix = pd.DataFrame({"a": [0.2, 0.9]}, index=["site-a", "site-b"])
    ranked = rank_sites(apply_weights(matrix, {"a": 1.0}))

    assert set(ranked["site_id"]) == {"site-a", "site-b"}
    assert all(isinstance(value, str) or not isinstance(value, float) for value in ranked["site_id"])


def test_scores_are_finite_for_valid_input() -> None:
    matrix = pd.DataFrame(
        {"a": [0.0, 1.0], "b": [1.0, 0.0]},
        index=["s1", "s2"],
    )
    for method in METHODS:
        scores = apply_weights(matrix, {"a": 0.5, "b": 0.5}, method=method)
        assert all(math.isfinite(value) for value in scores)
