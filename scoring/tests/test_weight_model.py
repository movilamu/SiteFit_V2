"""Tests for the criteria weight model.

The weight model is the bridge between the executive view (eight criteria
categories) and the scoring engine (28 leaf criteria).  These tests lock in
the roll-up arithmetic, the alignment behaviour and the coverage
disclosure.
"""

from __future__ import annotations

import pytest

from scoring.criteria_hierarchy import CRITERIA_TREE, iter_leaves
from scoring.weight_model import (
    WeightModelError,
    align_weights_to_columns,
    build_level_weights,
    category_keys,
    default_level_weights,
    leaf_keys,
    normalize_vector,
    resolve_leaf_weights,
)


# ---------------------------------------------------------------------------
# The hierarchy
# ---------------------------------------------------------------------------

def test_the_hierarchy_has_eight_categories() -> None:
    assert len(category_keys(CRITERIA_TREE)) == 8


def test_every_leaf_key_is_unique() -> None:
    keys = leaf_keys(CRITERIA_TREE)
    assert len(keys) == len(set(keys))


def test_every_category_has_at_least_one_leaf() -> None:
    owners = {criterion.key: category.key for category, _, criterion in iter_leaves(CRITERIA_TREE)}
    assert set(owners) == set(leaf_keys(CRITERIA_TREE))


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

def test_normalize_vector_scales_to_one() -> None:
    result = normalize_vector({"a": 2.0, "b": 6.0})
    assert sum(result.values()) == pytest.approx(1.0)
    assert result["a"] == pytest.approx(0.25)


def test_normalize_vector_rejects_a_zero_total() -> None:
    with pytest.raises(WeightModelError, match="greater than zero"):
        normalize_vector({"a": 0.0})


def test_normalize_vector_rejects_negative_weights() -> None:
    with pytest.raises(WeightModelError, match="not be negative"):
        normalize_vector({"a": 1.0, "b": -0.5})


def test_normalize_vector_rejects_non_finite_weights() -> None:
    with pytest.raises(WeightModelError, match="finite"):
        normalize_vector({"a": float("nan")})


# ---------------------------------------------------------------------------
# Roll-up
# ---------------------------------------------------------------------------

def test_the_default_level_weights_sum_to_one_at_every_level() -> None:
    level_weights = default_level_weights(CRITERIA_TREE)

    assert sum(level_weights["root"].values()) == pytest.approx(1.0)
    for parent, children in level_weights.items():
        if parent == "root":
            continue
        assert sum(children.values()) == pytest.approx(1.0), parent


def test_rolling_up_default_weights_sums_to_one_over_the_leaves() -> None:
    weights = resolve_leaf_weights()
    assert sum(weights.values()) == pytest.approx(1.0)
    assert set(weights) == set(leaf_keys(CRITERIA_TREE))


def test_rolling_up_respects_the_category_weights() -> None:
    weights = resolve_leaf_weights({"population": 1.0})

    assert sum(weights.values()) == pytest.approx(1.0)
    # Every leaf outside population must carry zero weight.
    population_leaves = {
        criterion.key
        for category, _, criterion in iter_leaves(CRITERIA_TREE)
        if category.key == "population"
    }
    for key, value in weights.items():
        if key not in population_leaves:
            assert value == pytest.approx(0.0)


def test_rolling_up_preserves_the_relative_split_within_a_category() -> None:
    weights = resolve_leaf_weights(
        {"population": 1.0},
        {"population": {"resident_density": 0.7, "projected_growth": 0.3}},
    )

    assert weights["resident_density"] == pytest.approx(0.7)
    assert weights["projected_growth"] == pytest.approx(0.3)
    # Leaves that were not mentioned carry zero weight.
    assert weights["daytime_population"] == pytest.approx(0.0)


def test_rolling_up_redistributes_an_omitted_category_to_zero() -> None:
    weights = resolve_leaf_weights({"population": 0.5, "accessibility": 0.5})
    assert sum(weights.values()) == pytest.approx(1.0)
    assert weights["resident_density"] > 0
    assert weights["drive_time_reach"] > 0


def test_an_unknown_category_is_rejected() -> None:
    with pytest.raises(WeightModelError, match="Unknown category"):
        resolve_leaf_weights({"not_a_category": 1.0})


def test_a_zero_weight_leaf_set_is_rejected() -> None:
    with pytest.raises(WeightModelError):
        resolve_leaf_weights(
            {"population": 1.0},
            {"population": {"resident_density": 0.0, "projected_growth": 0.0}},
        )


def test_build_level_weights_reports_the_normalised_categories() -> None:
    _, categories = build_level_weights({"population": 2.0, "accessibility": 2.0})
    assert sum(categories.values()) == pytest.approx(1.0)
    assert categories["population"] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Alignment to a scoring matrix
# ---------------------------------------------------------------------------

def test_alignment_keeps_every_available_criterion() -> None:
    weights = resolve_leaf_weights()
    columns = ["resident_density", "projected_growth"]
    aligned, dropped, coverage = align_weights_to_columns(weights, columns)

    assert set(aligned) == set(columns)
    assert len(dropped) > 0
    # Coverage is the share of the requested weight mass that could
    # actually be scored.  With 28 leaves and only two of them available,
    # most of the weight mass has no data behind it and that is disclosed.
    assert 0.0 < coverage < 1.0
    assert sum(aligned.values()) == pytest.approx(1.0)


def test_alignment_redistributes_the_weight_of_unavailable_criteria() -> None:
    weights = {"a": 0.5, "b": 0.5}
    aligned, dropped, coverage = align_weights_to_columns(weights, ["a"])

    assert aligned == {"a": 1.0}
    assert "b" in dropped
    assert coverage == pytest.approx(0.5)


def test_alignment_reports_zero_coverage_when_nothing_can_be_scored() -> None:
    aligned, dropped, coverage = align_weights_to_columns({"a": 1.0}, ["z"])

    assert aligned == {}
    assert "z" in dropped
    assert coverage == pytest.approx(0.0)


def test_alignment_can_leave_the_weights_unscaled() -> None:
    aligned, _dropped, _coverage = align_weights_to_columns(
        {"a": 0.5, "b": 0.5}, ["a"], renormalize=False
    )
    assert aligned == {"a": 0.5}


def test_alignment_rejects_an_empty_weight_vector() -> None:
    with pytest.raises(WeightModelError, match="at least one positive weight"):
        align_weights_to_columns({}, ["a"])
