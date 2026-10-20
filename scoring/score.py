"""scoring/score.py

CHEAP, per-interaction aggregation over a precomputed normalised matrix.

Analytical change log
---------------------
Two deliberate corrections were made when the module was consolidated into
its canonical location.  Both are covered by deterministic tests in
``scoring/tests/test_score.py``.

1. **Strict weight alignment.**

   Previously :func:`_align_weights` fell back to *positional* alignment
   whenever a weight mapping did not contain every matrix column::

       if all(col in global_weights for col in columns):
           return np.asarray([global_weights[col] for col in columns], dtype=float)
       return np.asarray(list(global_weights.values()), dtype=float)   # <- silent

   That fallback silently applied a weight to a *different* criterion than
   the one it was written for, or raised a confusing dimension mismatch.
   A weight vector is now required to cover every column; a partial vector
   raises a :class:`ValueError` naming the missing criteria.

2. **Consistent weight scaling across aggregation methods.**

   ``distance_to_ideal`` renormalised its weights internally while
   ``weighted_sum`` and ``weighted_product`` did not, so the same weight
   vector produced two different *effective* weightings depending on the
   method.  :func:`apply_weights` now normalises the weight vector to sum
   to 1.0 once, before dispatch.  For every currently valid API input
   (weights are already validated to sum to 1.0) this is a no-op; it only
   removes the discrepancy for internal callers.

   Ranking is unaffected by either change: scaling all weights by a
   positive constant leaves a weighted sum's ordering unchanged, and the
   existing API boundary already requires the weights to sum to 1.0.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence, Union

import numpy as np
import pandas as pd


from scoring.aggregate_distance_to_ideal import distance_to_ideal_score
from scoring.aggregate_weighted_product import weighted_product_score
from scoring.aggregate_weighted_sum import weighted_sum_score


METHODS = {
    "weighted_sum": weighted_sum_score,
    "weighted_product": weighted_product_score,
    "distance_to_ideal": distance_to_ideal_score,
}


def apply_weights(
    normalized_matrix,
    global_weights,
    method: str = "weighted_sum",
):
    matrix, index, columns = _unwrap_precomputed_matrix(normalized_matrix)
    weights = _align_weights(global_weights, columns)

    key = method.strip().lower().replace("-", "_").replace(" ", "_")
    if key not in METHODS:
        raise ValueError(
            f"Unknown aggregation method {method!r}. "
            f"Choose one of: {sorted(METHODS)}."
        )

    # Return empty series cleanly if candidate site inventory contains 0 sites
    if matrix.shape[0] == 0:
        return pd.Series([], index=index, dtype=float, name="score")

    # Normalise once so every aggregation method sees the same effective
    # weighting. See the module docstring for the rationale.
    weights = _normalize_weight_vector(weights, columns)

    scores = METHODS[key](matrix, weights)
    return pd.Series(np.asarray(scores, dtype=float), index=index, name="score")


def rank_sites(scores):
    series = _as_score_series(scores)
    ordered = series.sort_values(ascending=False, kind="mergesort")
    ranked = pd.DataFrame(
        {
            "rank": np.arange(1, len(ordered) + 1, dtype=int),
            "site_id": ordered.index,
            "score": ordered.to_numpy(dtype=float),
        }
    )
    return ranked.reset_index(drop=True)


def _unwrap_precomputed_matrix(normalized_matrix):
    """
    Extract (ndarray, index, columns) from the precompute step's output.
    Guarantees thread-safety (read-only array copy) and missing-value handling.
    """
    obj = normalized_matrix
    if hasattr(obj, "matrix") and not isinstance(obj, (np.ndarray, pd.DataFrame)):
        obj = obj.matrix

    if isinstance(obj, pd.DataFrame):
        matrix = obj.to_numpy(dtype=float, copy=True)
        index = obj.index
        columns = list(obj.columns)
    else:
        matrix = np.array(obj, dtype=float, copy=True)
        if matrix.ndim != 2:
            raise ValueError("normalized_matrix must be a 2-D matrix.")
        index = pd.RangeIndex(matrix.shape[0], name="site_id")
        columns = [f"c{j}" for j in range(matrix.shape[1])]

    # Fallback for missing/null criteria values:
    # Impute missing/NaN values column-by-column using the criterion's minimum
    # observed finite value (or 0.0 if all values for that criterion are NaN).
    if matrix.size > 0 and np.isnan(matrix).any():
        for col_idx in range(matrix.shape[1]):
            col = matrix[:, col_idx]
            nans = np.isnan(col)
            if np.any(nans):
                valid = col[~nans]
                fallback = float(np.min(valid)) if valid.size > 0 else 0.0
                col[nans] = fallback

    # Enforce read-only immutability to prevent race conditions during concurrent requests
    matrix.flags.writeable = False

    return matrix, index, columns


def _align_weights(global_weights, columns: Sequence[str]):
    """Align a weight vector with the matrix columns.

    A mapping must supply a weight for **every** column.  A partially
    specified mapping is an error rather than a positional guess, because a
    positional guess silently scores the wrong criterion.

    A sequence is used positionally, which is safe because the caller
    controls the ordering.
    """

    if isinstance(global_weights, Mapping):
        missing = [column for column in columns if column not in global_weights]
        if missing:
            raise ValueError(
                "The weight vector is missing weights for the following "
                f"criteria: {', '.join(missing)}. Supply a weight for every "
                f"criterion in the scoring matrix ({len(columns)} in total)."
            )
        return np.asarray([global_weights[column] for column in columns], dtype=float)

    weights = np.asarray(global_weights, dtype=float).reshape(-1)
    if weights.size != len(columns):
        raise ValueError(
            "The weight vector must contain exactly one weight per criterion "
            f"({weights.size} supplied, {len(columns)} expected)."
        )
    return weights


def _normalize_weight_vector(weights: np.ndarray, columns: Sequence[str]) -> np.ndarray:
    """Scale a weight vector so that it sums to 1.0.

    Zero-weight criteria are preserved: only the positive mass is rescaled.
    A vector with no positive mass is rejected because it cannot produce a
    meaningful ranking.
    """

    if not np.all(np.isfinite(weights)):
        raise ValueError("The weight vector must contain only finite values.")
    if np.any(weights < 0):
        raise ValueError("The weight vector must contain only non-negative values.")

    total = float(weights.sum())
    if total <= 0:
        raise ValueError(
            "The weight vector must contain at least one weight greater than zero."
        )
    if abs(total - 1.0) <= 1e-12:
        return weights
    return weights / total


def _as_score_series(scores) -> pd.Series:
    if isinstance(scores, pd.Series):
        return scores.astype(float)
    if isinstance(scores, pd.DataFrame):
        if "score" in scores.columns:
            idx = scores["site_id"] if "site_id" in scores.columns else scores.index
            return pd.Series(scores["score"].to_numpy(dtype=float), index=idx, name="score")
        if scores.shape[1] != 1:
            raise ValueError("scores DataFrame must have a 'score' column or a single column.")
        return scores.iloc[:, 0].astype(float)
    if isinstance(scores, Mapping):
        return pd.Series(scores, dtype=float, name="score")
    arr = np.asarray(scores, dtype=float).reshape(-1)
    return pd.Series(arr, index=pd.RangeIndex(arr.size, name="site_id"), name="score")


__all__ = ["apply_weights", "rank_sites", "METHODS"]
