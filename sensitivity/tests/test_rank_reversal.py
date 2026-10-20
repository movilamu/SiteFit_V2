"""Tests for the rank-reversal and Monte-Carlo sensitivity modules."""

from __future__ import annotations

import pandas as pd
import pytest

from sensitivity.monte_carlo import simulate_rank_distribution
from sensitivity.rank_reversal import detect_rank_reversals


def _matrix() -> pd.DataFrame:
    """Two sites that score almost identically, and one that is dominated.

    ``site-1`` scores a constant 0.5 whatever the weights, ``site-2``
    edges ahead of it when accessibility is weighted more heavily, and
    ``site-3`` is behind on both criteria so it can never overtake
    either of them.
    """

    return pd.DataFrame(
        {
            "a": [0.500, 0.502, 0.000],
            "b": [0.500, 0.498, 0.100],
        },
        index=["site-1", "site-2", "site-3"],
    )


def test_a_report_is_produced_for_the_evaluated_pairs() -> None:
    report = detect_rank_reversals(
        _matrix(), {"a": 0.5, "b": 0.5}, n_samples=40, seed=11
    )
    assert report.samples == 40
    assert report.to_dict()["reversal_count"] >= 0


def test_a_reversal_is_detected_between_two_near_identical_sites() -> None:
    report = detect_rank_reversals(
        _matrix(), {"a": 0.5, "b": 0.5}, n_samples=200, seed=7
    )
    pairs = {(item.site_a, item.site_b) for item in report.reversals}

    assert ("site-1", "site-2") in pairs
    reversal = next(
        item for item in report.reversals if (item.site_a, item.site_b) == ("site-1", "site-2")
    )
    assert reversal.reversal_rate > 0
    assert reversal.reversals == pytest.approx(reversal.reversal_rate * 200, abs=1)


def test_a_clearly_separated_pair_is_not_reported() -> None:
    report = detect_rank_reversals(
        _matrix(), {"a": 0.5, "b": 0.5}, n_samples=200, seed=7
    )
    pairs = {(item.site_a, item.site_b) for item in report.reversals}
    # site-3 is far behind in both criteria, so it never swaps with the
    # leaders.
    assert ("site-1", "site-3") not in pairs


def test_the_report_is_reproducible() -> None:
    first = detect_rank_reversals(_matrix(), {"a": 0.5, "b": 0.5}, n_samples=30, seed=5)
    second = detect_rank_reversals(_matrix(), {"a": 0.5, "b": 0.5}, n_samples=30, seed=5)

    assert [item.to_dict() for item in first.reversals] == [
        item.to_dict() for item in second.reversals
    ]


def test_a_partial_weight_mapping_is_rejected() -> None:
    with pytest.raises(ValueError, match="missing weights"):
        detect_rank_reversals(_matrix(), {"a": 1.0}, n_samples=5)


def test_zero_samples_is_rejected() -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        detect_rank_reversals(_matrix(), {"a": 0.5, "b": 0.5}, n_samples=0)


# ---------------------------------------------------------------------------
# Monte-Carlo rank distribution
# ---------------------------------------------------------------------------

def test_every_site_gets_a_rank_distribution() -> None:
    report = simulate_rank_distribution(
        _matrix(), {"a": 0.5, "b": 0.5}, n_samples=50, seed=3
    )
    assert len(report.distributions) == 3
    assert report.samples == 50


def test_the_distribution_describes_the_baseline_ranking() -> None:
    report = simulate_rank_distribution(
        _matrix(), {"a": 0.5, "b": 0.5}, n_samples=100, seed=3
    )
    by_site = {item.site_id: item for item in report.distributions}

    # site-3 is far behind on both criteria, so it is never near the top.
    assert by_site["site-3"].top1_share == 0.0
    assert by_site["site-3"].worst_rank == 3


def test_the_two_leaders_share_the_top_position() -> None:
    report = simulate_rank_distribution(
        _matrix(), {"a": 0.5, "b": 0.5}, n_samples=200, seed=3
    )
    by_site = {item.site_id: item for item in report.distributions}
    assert by_site["site-1"].top1_share + by_site["site-2"].top1_share == pytest.approx(1.0, abs=0.05)


def test_the_monte_carlo_report_is_reproducible() -> None:
    first = simulate_rank_distribution(_matrix(), {"a": 0.5, "b": 0.5}, n_samples=25, seed=9)
    second = simulate_rank_distribution(_matrix(), {"a": 0.5, "b": 0.5}, n_samples=25, seed=9)

    assert [item.to_dict() for item in first.distributions] == [
        item.to_dict() for item in second.distributions
    ]
