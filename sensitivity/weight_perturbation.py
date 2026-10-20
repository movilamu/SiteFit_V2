"""Weight perturbation sampling for sensitivity analysis.

Perturbing the weights is the mechanism used to answer "how sensitive is
this ranking to the weights I chose?".  The perturbation model is
deliberately simple and fully documented:

* every criterion weight is multiplied by an independent factor drawn
  uniformly from ``[1 - p, 1 + p]``,
* the perturbed vector is then renormalised to sum to 1.0.

The default ``p`` of 0.1 corresponds to a +/-10 % relative change in each
criterion's importance, which is a realistic representation of "a
decision maker might not have weighted these exactly as I did".

The sampler accepts a ``seed`` so that a stability report is reproducible:
the same seed and the same weights always produce the same numbers.
"""

from __future__ import annotations

from typing import Mapping, Optional

import numpy as np

DEFAULT_PERTURBATION_SIZE = 0.1
DEFAULT_SAMPLES = 200
DEFAULT_SEED = 20260101


def sample_weight_perturbations(
    current_weights,
    n_samples: int = DEFAULT_SAMPLES,
    perturbation_size: float = DEFAULT_PERTURBATION_SIZE,
    seed: Optional[int] = DEFAULT_SEED,
):
    """Generate randomly perturbed, normalised weight vectors.

    Parameters
    ----------
    current_weights : array-like or mapping
        Current criterion weights.  A mapping is perturbed in its own
        insertion order, so the caller must pass a vector that is already
        aligned with the scoring matrix's column order.
    n_samples : int, default=200
        Number of perturbed vectors to generate.
    perturbation_size : float, default=0.1
        Maximum relative perturbation per criterion. Must be in [0, 1].
    seed : int or None, default=20260101
        Seed for the random generator.  Pass ``None`` for a
        non-reproducible sample.

    Returns
    -------
    numpy.ndarray
        Shape ``(n_samples, n_criteria)``. Every row sums to 1.0.

    Raises
    ------
    ValueError
        If weights are invalid, have a non-positive total, or the sample
        count / perturbation size is invalid.
    """

    if n_samples < 0:
        raise ValueError("n_samples must be non-negative.")
    if not 0 <= perturbation_size <= 1:
        raise ValueError("perturbation_size must be between 0 and 1.")

    if isinstance(current_weights, Mapping):
        weights = np.asarray(list(current_weights.values()), dtype=float)
    else:
        weights = np.asarray(current_weights, dtype=float).reshape(-1)

    if weights.ndim != 1 or weights.size == 0:
        raise ValueError("current_weights must contain at least one weight.")
    if not np.all(np.isfinite(weights)):
        raise ValueError("current_weights must contain only finite values.")
    if np.any(weights < 0):
        raise ValueError("current_weights must be non-negative.")
    total = weights.sum()
    if total <= 0:
        raise ValueError("current_weights must have a positive total.")

    weights = weights / total

    if n_samples == 0:
        return np.empty((0, weights.size), dtype=float)

    generator = np.random.default_rng(seed)
    factors = generator.uniform(
        1.0 - perturbation_size,
        1.0 + perturbation_size,
        size=(n_samples, weights.size),
    )
    samples = weights[None, :] * factors
    row_totals = samples.sum(axis=1, keepdims=True)
    samples /= row_totals
    return samples


__all__ = [
    "DEFAULT_PERTURBATION_SIZE",
    "DEFAULT_SAMPLES",
    "DEFAULT_SEED",
    "sample_weight_perturbations",
]
