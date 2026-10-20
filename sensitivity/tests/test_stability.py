"""Tests for the rank stability analysis.

The stability report is the mechanism that tells a decision maker how much
of the ranking depends on their own weighting choices.  These tests cover
the documented alignment correction and the reproducibility guarantee.
"""

from __future__ import annotations

import pandas as pd
import pytest

from sensitivity.stability import rank_stability_report, sample_weight_perturbations


def _matrix() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "a": [0.90, 0.60, 0.30],
            "b": [0.10, 0.50, 0.80],
        },
        index=["site-1", "site-2", "site-3"],
    )


def test_the_report_covers_every_site() -> None:
    report = rank_stability_report(_matrix(), {"a": 0.6, "b": 0.4}, n_samples=20)
    assert set(report["site_id"]) == {"site-1", "site-2", "site-3"}
    assert "current_rank" in report.columns
    assert "stability_percentage" in report.columns


def test_the_baseline_rank_is_correct() -> None:
    report = rank_stability_report(_matrix(), {"a": 0.6, "b": 0.4}, n_samples=5)
    ranks = dict(zip(report["site_id"], report["current_rank"]))
    assert ranks["site-1"] == 1
    assert ranks["site-3"] == 3


def test_the_report_is_reproducible_for_a_given_seed() -> None:
    first = rank_stability_report(
        _matrix(), {"a": 0.6, "b": 0.4}, n_samples=30, seed=1234
    )
    second = rank_stability_report(
        _matrix(), {"a": 0.6, "b": 0.4}, n_samples=30, seed=1234
    )

    assert list(first["stability_percentage"]) == list(second["stability_percentage"])


def test_a_different_seed_produces_a_different_sample() -> None:
    first = rank_stability_report(
        _matrix(), {"a": 0.6, "b": 0.4}, n_samples=30, seed=1
    )
    second = rank_stability_report(
        _matrix(), {"a": 0.6, "b": 0.4}, n_samples=30, seed=2
    )

    assert list(first["stability_percentage"]) != list(second["stability_percentage"])


def test_the_weight_mapping_order_does_not_change_the_result() -> None:
    """The perturbed weights must be aligned to the matrix columns.

    A positional implementation would apply the perturbations to the wrong
    criteria whenever the mapping's key order differs from the column
    order, which is the normal case.
    """

    forward = rank_stability_report(
        _matrix(), {"a": 0.6, "b": 0.4}, n_samples=40, seed=99
    )
    reverse = rank_stability_report(
        _matrix(), {"b": 0.4, "a": 0.6}, n_samples=40, seed=99
    )

    assert list(forward["stability_percentage"]) == list(reverse["stability_percentage"])


def test_a_partial_weight_mapping_is_rejected() -> None:
    with pytest.raises(ValueError, match="missing weights"):
        rank_stability_report(_matrix(), {"a": 1.0}, n_samples=5)


def test_top_n_reports_membership_of_the_top_n() -> None:
    report = rank_stability_report(
        _matrix(), {"a": 0.6, "b": 0.4}, n_samples=20, top_n=2
    )

    assert set(report["stability_criterion"]) == {"top_2"}
    # A site inside the baseline top two must be more stable than the last.
    by_site = dict(zip(report["site_id"], report["stability_percentage"]))
    assert by_site["site-1"] >= by_site["site-3"]


def test_zero_samples_produces_zero_percentages() -> None:
    report = rank_stability_report(_matrix(), {"a": 0.6, "b": 0.4}, n_samples=0)
    assert all(value == 0.0 for value in report["stability_percentage"])


# ---------------------------------------------------------------------------
# The perturbation sampler
# ---------------------------------------------------------------------------

def test_the_sampler_produces_rows_that_sum_to_one() -> None:
    samples = sample_weight_perturbations([0.6, 0.4], n_samples=25, seed=7)
    assert samples.shape == (25, 2)
    for row in samples:
        assert row.sum() == pytest.approx(1.0)


def test_the_sampler_is_reproducible() -> None:
    first = sample_weight_perturbations([0.6, 0.4], n_samples=10, seed=3)
    second = sample_weight_perturbations([0.6, 0.4], n_samples=10, seed=3)
    assert (first == second).all()


def test_the_sampler_respects_the_perturbation_size() -> None:
    samples = sample_weight_perturbations(
        [0.5, 0.5], n_samples=200, perturbation_size=0.1, seed=11
    )
    # With a +/-10% relative perturbation, no weight should stray far from
    # its starting share.
    for row in samples:
        assert 0.4 <= row[0] <= 0.6


def test_the_sampler_rejects_an_invalid_sample_count() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        sample_weight_perturbations([0.5, 0.5], n_samples=-1)


def test_the_sampler_rejects_an_invalid_perturbation_size() -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        sample_weight_perturbations([0.5, 0.5], perturbation_size=1.5)
