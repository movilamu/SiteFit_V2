"""Monte-Carlo rank distribution.

Where :mod:`sensitivity.rank_stability` answers "how often does a site
keep its rank?", this module answers the complementary question: *"if the
weights are uncertain, what is the distribution of ranks a site could
end up with?"*

That distribution is what a decision maker needs when the top of the
shortlist is close: a site that ranks first in 60 % of the plausible
weightings and third in the rest is a materially different proposition
from one that ranks first in 99 %.

The method draws weight vectors from a simplex-constrained distribution
around the current weights, scores every draw, and records the rank each
site attains.  The draw is seeded, so the result is reproducible.
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
class RankDistribution:
    """The distribution of ranks a site attains across the sampled weightings."""

    site_id: str
    median_rank: float
    best_rank: int
    worst_rank: int
    modal_rank: int
    modal_share: float
    expected_rank: float
    rank_std: float
    top1_share: float
    top3_share: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "site_id": self.site_id,
            "median_rank": round(self.median_rank, 3),
            "best_rank": self.best_rank,
            "worst_rank": self.worst_rank,
            "modal_rank": self.modal_rank,
            "modal_share": round(self.modal_share, 4),
            "expected_rank": round(self.expected_rank, 3),
            "rank_std": round(self.rank_std, 3),
            "top1_share": round(self.top1_share, 4),
            "top3_share": round(self.top3_share, 4),
        }


@dataclass
class MonteCarloReport:
    """The outcome of a Monte-Carlo rank analysis."""

    distributions: List[RankDistribution] = field(default_factory=list)
    samples: int = 0
    perturbation_size: float = DEFAULT_PERTURBATION_SIZE
    seed: int = DEFAULT_SEED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "samples": self.samples,
            "perturbation_size": self.perturbation_size,
            "seed": self.seed,
            "distributions": [item.to_dict() for item in self.distributions],
        }


def _aligned_weights(current_weights: Any, columns: Sequence[str]) -> np.ndarray:
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


def simulate_rank_distribution(
    normalized_matrix,
    current_weights,
    n_samples: int = DEFAULT_SAMPLES,
    perturbation_size: float = DEFAULT_PERTURBATION_SIZE,
    method: str = "weighted_sum",
    seed: int = DEFAULT_SEED,
    top_n: int = 3,
) -> MonteCarloReport:
    """Simulate the ranking under a distribution of plausible weightings.

    Args:
        normalized_matrix: The precomputed normalised decision matrix.
        current_weights: The current leaf weights.
        n_samples: Number of weightings to simulate.
        perturbation_size: Relative perturbation applied to each weight.
        method: The aggregation method.
        seed: Seed for the perturbation sampler.
        top_n: The size of the "top N" share that is reported.

    Returns:
        A :class:`MonteCarloReport` with one distribution per site.
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

    perturbations = sample_weight_perturbations(
        aligned,
        n_samples=n_samples,
        perturbation_size=perturbation_size,
        seed=seed,
    )

    ranks_by_site: Dict[str, List[int]] = {}
    for perturbed in perturbations:
        scores = apply_weights(matrix, perturbed, method=method)
        ranked = rank_sites(scores)
        for site_id, rank in zip(ranked["site_id"], ranked["rank"]):
            ranks_by_site.setdefault(str(site_id), []).append(int(rank))

    distributions: List[RankDistribution] = []
    for site_id, ranks in ranks_by_site.items():
        values = np.asarray(ranks, dtype=float)
        counts = np.bincount(values.astype(int))
        modal_rank = int(np.argmax(counts))
        distributions.append(
            RankDistribution(
                site_id=site_id,
                median_rank=float(np.median(values)),
                best_rank=int(values.min()),
                worst_rank=int(values.max()),
                modal_rank=modal_rank,
                modal_share=float(counts[modal_rank] / len(ranks)),
                expected_rank=float(values.mean()),
                rank_std=float(values.std(ddof=0)),
                top1_share=float((values == 1).mean()),
                top3_share=float((values <= top_n).mean()),
            )
        )

    # Most exposed first: the sites whose rank varies the most.
    distributions.sort(key=lambda item: (-item.rank_std, item.expected_rank))

    return MonteCarloReport(
        distributions=distributions,
        samples=n_samples,
        perturbation_size=perturbation_size,
        seed=seed,
    )


__all__ = [
    "MonteCarloReport",
    "RankDistribution",
    "simulate_rank_distribution",
]
