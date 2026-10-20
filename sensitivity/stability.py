"""Rank stability under weight perturbations.

This module repeatedly applies the scoring engine's ``apply_weights`` to
small perturbations of the current global weights and measures how often
each site keeps its baseline rank (or remains in a configurable top-N).

Analytical change log
---------------------
One deliberate correction was made when the module was consolidated into
its canonical location.

**Perturbed weights are now aligned to the matrix columns.**

The baseline score was computed by name-aligning the weight mapping
against the matrix columns, but the perturbed vectors were built from the
mapping's *insertion order* and then applied positionally.  Whenever the
mapping's key order differed from the matrix's column order -- which is
the normal case, because the matrix is ordered by the criteria hierarchy
while a caller supplies weights in its own order -- every perturbed
weight vector was applied to the wrong criteria, and the resulting
stability percentages described a different model from the one that
produced the ranking.

The weight vector is now aligned to the matrix columns once, before
sampling, so the baseline and the perturbations analyse the same model.

In addition, the perturbation sampler is now seeded by default, so a
stability report is reproducible rather than changing on every request.
"""

from __future__ import annotations

from typing import Mapping, Optional, Sequence

import numpy as np
import pandas as pd

from scoring.score import apply_weights, rank_sites
from sensitivity.weight_perturbation import (
    DEFAULT_PERTURBATION_SIZE,
    DEFAULT_SAMPLES,
    DEFAULT_SEED,
    sample_weight_perturbations,
)


def _matrix_columns(normalized_matrix) -> list[str]:
    """Return the criterion columns of a normalised matrix, in order."""

    matrix = normalized_matrix
    if hasattr(matrix, "matrix") and not isinstance(matrix, (np.ndarray, pd.DataFrame)):
        matrix = matrix.matrix
    if isinstance(matrix, pd.DataFrame):
        return [str(column) for column in matrix.columns]
    return []


def _aligned_vector(
    current_weights, columns: Sequence[str]
) -> np.ndarray:
    """Return the weight vector aligned to the matrix column order.

    A mapping is re-ordered by column name.  A sequence is used as-is,
    because the caller controls the ordering.
    """

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


def rank_stability_report(
    normalized_matrix,
    current_weights,
    n_samples: int = DEFAULT_SAMPLES,
    top_n: Optional[int] = None,
    method: str = "weighted_sum",
    perturbation_size: float = DEFAULT_PERTURBATION_SIZE,
    seed: Optional[int] = DEFAULT_SEED,
):
    """Report how stable each site's baseline rank is under weight perturbations.

    Parameters
    ----------
    normalized_matrix : ndarray, DataFrame, or matrix artifact
        Already-normalized decision matrix accepted by ``apply_weights``.
    current_weights : array-like or mapping
        Current global criterion weights.
    n_samples : int, default=200
        Number of perturbed weight vectors to evaluate.
    top_n : int or None, default=None
        If provided, report stability as the percentage of samples in which
        each site remains in the baseline top-N. If None, report the
        percentage of samples in which each site keeps its exact baseline
        rank.
    method : str, default='weighted_sum'
        Aggregation method used for the baseline and every perturbation.
    perturbation_size : float, default=0.1
        Maximum relative perturbation applied to each weight.
    seed : int or None, default=20260101
        Seed for the perturbation sampler.  Pass ``None`` for a
        non-reproducible sample.

    Returns
    -------
    pandas.DataFrame
        One row per site, containing ``site_id``, ``current_rank``,
        ``stability_percentage``, and ``stability_criterion``. When ``top_n``
        is supplied, ``top_n`` is also included.
    """

    if n_samples < 0:
        raise ValueError("n_samples must be non-negative.")
    if top_n is not None and top_n <= 0:
        raise ValueError("top_n must be a positive integer or None.")
    if top_n is not None and int(top_n) != top_n:
        raise ValueError("top_n must be a positive integer or None.")
    top_n = int(top_n) if top_n is not None else None

    columns = _matrix_columns(normalized_matrix)
    aligned = _aligned_vector(current_weights, columns)

    # The baseline and every perturbation must analyse the same model, so
    # the weight vector is aligned to the matrix columns up front.
    baseline_scores = apply_weights(normalized_matrix, aligned, method=method)
    baseline_ranked = rank_sites(baseline_scores)

    if top_n is not None:
        top_n = min(top_n, len(baseline_ranked))
        baseline_target = set(baseline_ranked.iloc[:top_n]["site_id"])
        criterion = f"top_{top_n}"
    else:
        baseline_target = {
            row.site_id: int(row["rank"])
            for _, row in baseline_ranked.iterrows()
        }
        criterion = "exact_rank"

    perturbations = sample_weight_perturbations(
        aligned,
        n_samples=n_samples,
        perturbation_size=perturbation_size,
        seed=seed,
    )

    hit_counts = pd.Series(0, index=baseline_ranked["site_id"], dtype=int)

    for perturbed_weights in perturbations:
        scores = apply_weights(normalized_matrix, perturbed_weights, method=method)
        ranked = rank_sites(scores)

        if top_n is not None:
            perturbed_top = set(ranked.iloc[:top_n]["site_id"])
            for site_id in baseline_target:
                if site_id in perturbed_top:
                    hit_counts.loc[site_id] += 1
        else:
            perturbed_ranks = dict(zip(ranked["site_id"], ranked["rank"]))
            for site_id, baseline_rank in baseline_target.items():
                if perturbed_ranks.get(site_id) == baseline_rank:
                    hit_counts.loc[site_id] += 1

    denominator = n_samples
    percentages = (
        hit_counts.to_numpy(dtype=float) / denominator * 100.0
        if denominator
        else np.zeros(len(hit_counts), dtype=float)
    )

    report = baseline_ranked[["site_id", "rank"]].rename(
        columns={"rank": "current_rank"}
    ).copy()
    report["stability_percentage"] = percentages
    report["stability_criterion"] = criterion

    if top_n is not None:
        report["top_n"] = top_n

    return report.reset_index(drop=True)


__all__ = [
    "DEFAULT_PERTURBATION_SIZE",
    "DEFAULT_SAMPLES",
    "DEFAULT_SEED",
    "rank_stability_report",
    "sample_weight_perturbations",
]
