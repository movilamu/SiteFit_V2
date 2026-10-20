"""Rank-reversal detection.

A rank reversal occurs when two sites exchange position.  The most
important case for a decision maker is not a large reversal far down the
list, but a reversal between two sites that are close together and
therefore could plausibly swap places on a slightly different set of
weights.

This module detects those at-risk pairs directly, by perturbing the
weights and measuring how often each pair exchanges order.

The method is deterministic: the same weights and the same seed always
produce the same report, so a finding can be reproduced and quoted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence

import numpy as np
import pandas as pd

from scoring.score import apply_weights, rank_sites
from sensitivity.weight_perturbation import (
    DEFAULT_PERTURBATION_SIZE,
    DEFAULT_SAMPLES,
    DEFAULT_SEED,
    sample_weight_perturbations,
)


@dataclass
class RankReversal:
    """A pair of sites that exchanged order under a weight perturbation."""

    site_a: str
    site_b: str
    reversal_rate: float
    reversals: int
    samples: int
    baseline_a_rank: int
    baseline_b_rank: int

    @property
    def risk(self) -> str:
        """How exposed the pair is to a reversal."""

        if self.reversal_rate >= 0.25:
            return "high"
        if self.reversal_rate >= 0.10:
            return "moderate"
        return "low"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "site_a": self.site_a,
            "site_b": self.site_b,
            "reversal_rate": round(self.reversal_rate, 6),
            "reversals": self.reversals,
            "samples": self.samples,
            "baseline_a_rank": self.baseline_a_rank,
            "baseline_b_rank": self.baseline_b_rank,
            "risk": self.risk,
        }


@dataclass
class RankReversalReport:
    """The outcome of a rank-reversal analysis."""

    reversals: List[RankReversal] = field(default_factory=list)
    samples: int = 0
    perturbation_size: float = DEFAULT_PERTURBATION_SIZE
    seed: int = DEFAULT_SEED

    @property
    def high_risk_pairs(self) -> List[RankReversal]:
        return [item for item in self.reversals if item.risk == "high"]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "samples": self.samples,
            "perturbation_size": self.perturbation_size,
            "seed": self.seed,
            "reversal_count": len(self.reversals),
            "high_risk_count": len(self.high_risk_pairs),
            "reversals": [item.to_dict() for item in self.reversals],
        }


def _aligned_weights(
    current_weights: Any, columns: Sequence[str]
) -> np.ndarray:
    if isinstance(current_weights, Mapping):
        missing = [column for column in columns if column not in current_weights]
        if missing:
            raise ValueError(
                "The weight vector is missing weights for the following "
                f"criteria: {', '.join(missing)}."
            )
        return np.asarray(
            [float(current_weights[column]) for column in columns], dtype=float
        )
    vector = np.asarray(current_weights, dtype=float).reshape(-1)
    if columns and vector.size != len(columns):
        raise ValueError(
            "The weight vector must contain exactly one weight per criterion "
            f"({vector.size} supplied, {len(columns)} expected)."
        )
    return vector


def detect_rank_reversals(
    normalized_matrix,
    current_weights,
    n_samples: int = DEFAULT_SAMPLES,
    perturbation_size: float = DEFAULT_PERTURBATION_SIZE,
    method: str = "weighted_sum",
    seed: int = DEFAULT_SEED,
    max_pairs: Optional[int] = 25,
    minimum_rate: float = 0.01,
) -> RankReversalReport:
    """Find the pairs of sites whose order is least stable.

    Args:
        normalized_matrix: The precomputed normalised decision matrix.
        current_weights: The current leaf weights.
        n_samples: Number of weight perturbations to evaluate.
        perturbation_size: Relative perturbation applied to each weight.
        method: The aggregation method.
        seed: Seed for the perturbation sampler.
        max_pairs: The most at-risk pairs to report.  ``None`` reports all.
        minimum_rate: Pairs that reversed less often than this are omitted.

    Returns:
        A :class:`RankReversalReport` ordered by reversal rate, most
        exposed first.
    """

    if n_samples <= 0:
        raise ValueError("n_samples must be greater than zero.")

    matrix = normalized_matrix
    if hasattr(matrix, "matrix") and not isinstance(matrix, (np.ndarray, pd.DataFrame)):
        matrix = matrix.matrix
    if not isinstance(matrix, pd.DataFrame):
        raise ValueError("normalized_matrix must be a DataFrame.")

    columns = [str(column) for column in matrix.columns]
    aligned = _aligned_weights(current_weights, columns)

    baseline_scores = apply_weights(matrix, aligned, method=method)
    baseline_ranked = rank_sites(baseline_scores)
    baseline_rank = {
        str(site_id): int(rank)
        for site_id, rank in zip(baseline_ranked["site_id"], baseline_ranked["rank"])
    }
    order = [str(site_id) for site_id in baseline_ranked["site_id"]]

    perturbations = sample_weight_perturbations(
        aligned,
        n_samples=n_samples,
        perturbation_size=perturbation_size,
        seed=seed,
    )

    # Count, for every pair, how often the order flipped.
    counts: Dict[tuple, int] = {}
    for perturbed in perturbations:
        scores = apply_weights(matrix, perturbed, method=method)
        perturbed_order = [str(site_id) for site_id in rank_sites(scores)["site_id"]]
        position = {site_id: index for index, site_id in enumerate(perturbed_order)}

        for left in range(len(order)):
            for right in range(left + 1, len(order)):
                site_a = order[left]
                site_b = order[right]
                if position.get(site_a, 0) > position.get(site_b, 0):
                    key = (site_a, site_b)
                    counts[key] = counts.get(key, 0) + 1

    reversals: List[RankReversal] = []
    for (site_a, site_b), count in counts.items():
        rate = count / n_samples
        if rate < minimum_rate:
            continue
        reversals.append(
            RankReversal(
                site_a=site_a,
                site_b=site_b,
                reversal_rate=rate,
                reversals=count,
                samples=n_samples,
                baseline_a_rank=baseline_rank.get(site_a, 0),
                baseline_b_rank=baseline_rank.get(site_b, 0),
            )
        )

    reversals.sort(key=lambda item: item.reversal_rate, reverse=True)
    if max_pairs is not None:
        reversals = reversals[:max_pairs]

    return RankReversalReport(
        reversals=reversals,
        samples=n_samples,
        perturbation_size=perturbation_size,
        seed=seed,
    )


__all__ = [
    "RankReversal",
    "RankReversalReport",
    "detect_rank_reversals",
]
