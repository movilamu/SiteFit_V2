"""Weight model bridging the criteria hierarchy and the scoring engine.

Why this module exists
----------------------
The criteria hierarchy in :mod:`scoring.criteria_hierarchy` is a three-level
tree::

    root
     └── category          (8 of them: population, demographics, ...)
          └── subcategory  (1 per category today)
               └── criterion (leaf, 28 in total)

The scoring engine, however, operates on **leaf** columns: the normalised
matrix produced by :mod:`scoring.precompute_matrix` has one column per
leaf criterion key, and :func:`scoring.score.apply_weights` multiplies
those columns by a weight vector.

Decision makers, on the other hand, think in terms of the eight
categories.  This module is the single, tested bridge between the two:

* :func:`build_level_weights` turns "category weights + optional within-
  category leaf weights" into the grouped level-weight structure that
  :func:`scoring.hierarchical_rollup.compute_global_weights` consumes.
* :func:`resolve_leaf_weights` performs the roll-up and returns the global
  leaf weights.
* :func:`align_weights_to_columns` maps a leaf weight vector onto the
  columns that are actually present in a normalised matrix and reports
  which criteria could not be scored.

All arithmetic here is a straight product of level weights, i.e. exactly
the formula already implemented and documented in
:mod:`scoring.hierarchical_rollup`.  No new mathematical behaviour is
introduced here.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping, Optional, Sequence

from scoring.criteria_hierarchy import (
    CRITERIA_TREE,
    Category,
    Criterion,
    Subcategory,
    iter_leaves,
)
from scoring.hierarchical_rollup import compute_global_weights

# Tolerance used when validating that a level's weights sum to 1.0.  It is
# deliberately looser than the roll-up's own 1e-5 so that weights rounded
# for display (e.g. "12.5 %") are still accepted.
LEVEL_SUM_TOLERANCE = 1e-3


class WeightModelError(ValueError):
    """Raised when a weight configuration cannot be interpreted."""


# ---------------------------------------------------------------------------
# Tree helpers
# ---------------------------------------------------------------------------

def _as_tree(tree: Optional[Any]) -> tuple:
    if tree is None:
        return CRITERIA_TREE
    if isinstance(tree, (tuple, list)):
        return tuple(tree)
    raise WeightModelError(
        f"Unsupported criteria hierarchy type: {type(tree)!r}"
    )


def category_keys(tree: Optional[Any] = None) -> list[str]:
    """Return the top-level category keys in tree order."""

    return [category.key for category in _as_tree(tree)]


def leaf_keys(tree: Optional[Any] = None) -> list[str]:
    """Return every leaf criterion key in depth-first tree order."""

    return [criterion.key for _, _, criterion in iter_leaves(_as_tree(tree))]


def category_of_leaf(tree: Optional[Any] = None) -> dict[str, str]:
    """Map each leaf criterion key to its owning category key."""

    mapping: dict[str, str] = {}
    for category, _, criterion in iter_leaves(_as_tree(tree)):
        mapping[criterion.key] = category.key
    return mapping


def leaves_of_category(category_key: str, tree: Optional[Any] = None) -> list[str]:
    """Return the leaf keys belonging to one category, in tree order."""

    return [
        criterion.key
        for category, _, criterion in iter_leaves(_as_tree(tree))
        if category.key == category_key
    ]


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

def normalize_vector(weights: Mapping[str, float], tolerance: float = 1e-9) -> dict[str, float]:
    """Scale a weight mapping so that it sums to exactly 1.0.

    Raises:
        WeightModelError: when the weights are all zero, contain a negative
            value, or contain a non-finite value.
    """

    cleaned: dict[str, float] = {}
    for key, raw in weights.items():
        value = float(raw)
        if not math.isfinite(value):
            raise WeightModelError(f"Weight for {key!r} must be a finite number.")
        if value < 0:
            raise WeightModelError(f"Weight for {key!r} must not be negative.")
        cleaned[str(key)] = value

    total = sum(cleaned.values())
    if total <= 0:
        raise WeightModelError("At least one weight must be greater than zero.")
    if abs(total - 1.0) <= tolerance:
        return cleaned
    return {key: value / total for key, value in cleaned.items()}


# ---------------------------------------------------------------------------
# Level-weight construction
# ---------------------------------------------------------------------------

def default_level_weights(tree: Optional[Any] = None) -> dict[str, dict[str, float]]:
    """Build an equal-split level-weight structure for the whole tree.

    Level weights are *local conditional* weights: within each parent, the
    children's weights sum to 1.0.  The global weight of a leaf is the
    product of the level weights along its path, which is exactly the
    formula implemented by
    :func:`scoring.hierarchical_rollup.compute_global_weights`.
    """

    level_weights: dict[str, dict[str, float]] = {}
    categories = _as_tree(tree)

    category_mass = 1.0 / len(categories) if categories else 0.0
    level_weights["root"] = {category.key: category_mass for category in categories}

    for category in categories:
        subcategories = list(category.subcategories)
        if not subcategories:
            continue
        sub_mass = 1.0 / len(subcategories)
        level_weights[category.key] = {sub.key: sub_mass for sub in subcategories}

        for sub in subcategories:
            criteria = list(sub.criteria)
            if not criteria:
                continue
            leaf_mass = 1.0 / len(criteria)
            level_weights[sub.key] = {criterion.key: leaf_mass for criterion in criteria}

    return level_weights


def build_level_weights(
    category_weights: Optional[Mapping[str, float]] = None,
    leaf_weights: Optional[Mapping[str, Mapping[str, float]]] = None,
    tree: Optional[Any] = None,
) -> tuple[dict[str, dict[str, float]], dict[str, float]]:
    """Assemble the grouped level weights used by the hierarchical roll-up.

    Args:
        category_weights: Relative importance of each top-level category.
            Normalised to sum to 1.0.  ``None`` means an equal split.
        leaf_weights: Optional within-category leaf weights, keyed by
            category.  Each inner mapping is normalised within its
            category.  Categories that are absent are split evenly across
            their leaves.
        tree: Optional alternative criteria hierarchy.

    Returns:
        ``(level_weights, normalised_category_weights)`` where
        ``level_weights`` is the grouped structure consumed by
        :func:`scoring.hierarchical_rollup.compute_global_weights`.
    """

    categories = _as_tree(tree)
    if not categories:
        raise WeightModelError("The criteria hierarchy contains no categories.")

    if category_weights:
        unknown = set(category_weights) - {c.key for c in categories}
        if unknown:
            raise WeightModelError(
                "Unknown category key(s): " + ", ".join(sorted(unknown))
            )
        # Normalise across the categories the user actually specified; the
        # remaining categories receive zero weight so that the root level
        # still sums to 1.0.
        specified = normalize_vector(category_weights)
        normalised_categories = {
            category.key: specified.get(category.key, 0.0) for category in categories
        }
    else:
        normalised_categories = {
            category.key: 1.0 / len(categories) for category in categories
        }

    level_weights: dict[str, dict[str, float]] = {
        "root": dict(normalised_categories)
    }

    for category in categories:
        subcategories = list(category.subcategories)
        if not subcategories:
            continue

        # Subcategory weights are local to the category: they sum to 1.0
        # within the category, and the global weight of a leaf is the
        # product of the level weights along its path.
        if len(subcategories) == 1:
            sub_weights = {subcategories[0].key: 1.0}
        else:
            sub_mass = 1.0 / len(subcategories)
            sub_weights = {sub.key: sub_mass for sub in subcategories}

        level_weights[category.key] = sub_weights

        for sub in subcategories:
            criteria = list(sub.criteria)
            if not criteria:
                continue

            requested = (leaf_weights or {}).get(category.key) or {}
            requested = {
                key: float(value)
                for key, value in requested.items()
                if key in {criterion.key for criterion in criteria}
            }

            if requested:
                try:
                    local = normalize_vector(requested)
                except WeightModelError as exc:
                    raise WeightModelError(
                        f"Leaf weights for category {category.key!r} are invalid: {exc}"
                    ) from exc
                # Leaves the user did not mention carry zero weight, so the
                # subcategory level still sums to 1.0 across all its leaves.
                for criterion in criteria:
                    local.setdefault(criterion.key, 0.0)
            else:
                leaf_mass = 1.0 / len(criteria)
                local = {criterion.key: leaf_mass for criterion in criteria}

            level_weights[sub.key] = local

    return level_weights, normalised_categories


# ---------------------------------------------------------------------------
# Roll-up
# ---------------------------------------------------------------------------

def resolve_leaf_weights(
    category_weights: Optional[Mapping[str, float]] = None,
    leaf_weights: Optional[Mapping[str, Mapping[str, float]]] = None,
    tree: Optional[Any] = None,
) -> dict[str, float]:
    """Roll category (and optional leaf) weights up to global leaf weights.

    The returned vector sums to 1.0 across every leaf in the tree.
    """

    level_weights, _ = build_level_weights(category_weights, leaf_weights, tree)
    try:
        return compute_global_weights(_as_tree(tree), level_weights)
    except (ValueError, KeyError) as exc:
        raise WeightModelError(
            f"Could not roll weights up through the criteria hierarchy: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Alignment to a scoring matrix
# ---------------------------------------------------------------------------

def align_weights_to_columns(
    weights: Mapping[str, float],
    columns: Sequence[str],
    *,
    renormalize: bool = True,
) -> tuple[dict[str, float], list[str], float]:
    """Map a leaf weight vector onto the columns present in a matrix.

    Criteria whose data is not available in the current release cannot be
    scored.  Rather than silently discarding their weight, the remaining
    weight mass is redistributed proportionally across the criteria that
    *can* be scored, and the dropped criteria are reported to the caller so
    the interface can disclose the reduced coverage.

    Args:
        weights: Leaf weights keyed by criterion key.
        columns: Column keys of the normalised matrix.
        renormalize: When True (default) the surviving weights are rescaled
            to sum to 1.0.  When False they are left untouched.

    Returns:
        ``(aligned_weights, dropped_criteria, coverage)`` where
        ``coverage`` is the share of the requested weight mass that could
        actually be scored (0.0 when nothing could be scored).
    """

    requested_total = sum(float(value) for value in weights.values())
    if requested_total <= 0:
        raise WeightModelError("Weight vector must contain at least one positive weight.")

    aligned: dict[str, float] = {}
    dropped: list[str] = []

    for column in columns:
        if column in weights:
            aligned[column] = float(weights[column])
        else:
            dropped.append(column)

    # Weight mass attached to criteria that exist but are absent from the
    # matrix is also lost, and must be disclosed.
    scored_mass = sum(aligned.values())
    lost_to_missing_columns = requested_total - scored_mass
    coverage = scored_mass / requested_total if requested_total > 0 else 0.0

    # Disclose the criteria whose data is unavailable in this release.
    for key in weights:
        if key not in aligned and key not in dropped:
            dropped.append(key)

    if not aligned or scored_mass <= 0:
        # Nothing could be scored.  Either no requested criterion is in the
        # matrix, or every criterion that is in the matrix carries a zero
        # weight -- which is what happens when the caller puts all of the
        # weight on a category whose leaves have no data in this release.
        # There is no weight mass to apply, so the caller is told that
        # nothing could be scored instead of being handed a zero vector
        # that would divide by zero downstream.
        return {}, sorted(set(dropped)), 0.0

    if renormalize and abs(scored_mass - 1.0) > 1e-12:
        aligned = {key: value / scored_mass for key, value in aligned.items()}

    if lost_to_missing_columns > 1e-12:
        # Keep the disclosure explicit and stable in ordering.
        dropped = sorted(set(dropped))

    return aligned, sorted(set(dropped)), coverage


def weights_for_report(
    weights: Mapping[str, float],
    tree: Optional[Any] = None,
) -> list[dict[str, Any]]:
    """Return a display-ready breakdown of a leaf weight vector.

    Each row carries the owning category so the interface can group the
    weights without re-deriving the hierarchy client-side.
    """

    owners = category_of_leaf(tree)
    labels = {
        criterion.key: criterion.label
        for _, _, criterion in iter_leaves(_as_tree(tree))
    }
    rows: list[dict[str, Any]] = []
    for key in leaf_keys(tree):
        if key not in weights:
            continue
        rows.append(
            {
                "criterion": key,
                "label": labels.get(key, key),
                "category": owners.get(key),
                "weight": float(weights[key]),
            }
        )
    return rows


__all__ = [
    "LEVEL_SUM_TOLERANCE",
    "WeightModelError",
    "align_weights_to_columns",
    "build_level_weights",
    "category_keys",
    "category_of_leaf",
    "default_level_weights",
    "leaf_keys",
    "leaves_of_category",
    "normalize_vector",
    "resolve_leaf_weights",
    "weights_for_report",
]
