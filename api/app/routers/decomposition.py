"""FastAPI router for site score decomposition.

The decomposition explains *why* a site received its score.  It is computed
entirely from the deterministic scoring engine — no language model is
involved, and no value is inferred.

The aggregate score returned here is produced by
:func:`scoring.score.apply_weights`, so it is guaranteed to be identical
to the score shown in the ranking for the same weights and method.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from scoring.score import METHODS, apply_weights
from scoring.weight_model import align_weights_to_columns

router = APIRouter(tags=["decomposition"])


class CriterionDecomposition(BaseModel):
    """Breakdown for an individual criterion for a specific site."""

    criterion: str = Field(..., description="Criterion identifier or column name.")
    label: str = Field(default="", description="Human-readable criterion name.")
    category: str = Field(default="", description="Owning category in the criteria hierarchy.")
    normalized_value: float = Field(..., description="Normalized performance value in [0, 1].")
    weight: float = Field(..., description="Weight applied to this criterion.")
    contribution: float = Field(
        ...,
        description=(
            "Contribution to the total score. Additive for the weighted-sum "
            "method; for the weighted-product and distance-to-ideal methods "
            "the factor each criterion contributes is reported instead."
        ),
    )
    direction: Optional[str] = Field(
        default=None,
        description="'benefit', 'cost' or null for target-band criteria.",
    )


class SiteDecompositionResponse(BaseModel):
    """Response model containing site score decomposition details."""

    site_id: str = Field(..., description="Unique identifier of the site.")
    method: str = Field(..., description="Aggregation method used.")
    total_score: float = Field(..., description="Aggregated total score for the site.")
    criteria: List[CriterionDecomposition] = Field(
        ..., description="Per-criterion decomposition items."
    )
    rank: Optional[int] = Field(
        default=None,
        description="The site's rank under the same weights and method.",
    )
    dropped_criteria: List[str] = Field(
        default_factory=list,
        description="Criteria excluded because their data is unavailable.",
    )
    coverage: float = Field(
        default=1.0,
        description="Share of the requested weight mass that could be scored.",
    )


def _load_normalized_matrix():
    """Load the precomputed normalized matrix used for scoring."""

    try:
        from api.app.routers.scenarios import get_normalized_matrix

        return get_normalized_matrix()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Normalized matrix is unavailable: {exc}",
        ) from exc


def _load_site_data(site_id: str) -> Optional[Dict[str, float]]:
    """Look up a site's precomputed normalized criterion values."""

    matrix = _load_normalized_matrix()
    for index in matrix.index:
        if str(index) == str(site_id):
            row = matrix.loc[index]
            values: Dict[str, float] = {}
            for criterion, value in row.items():
                try:
                    values[str(criterion)] = float(value)
                except (TypeError, ValueError):
                    continue
            return values
    return None


def _parse_weights(weights_param: str) -> Dict[str, float]:
    """Parse the JSON weights query parameter into a mapping."""

    try:
        parsed = json.loads(weights_param)
        if not isinstance(parsed, dict):
            raise ValueError("Weights JSON must represent an object/mapping.")
        return {str(key): float(value) for key, value in parsed.items()}
    except Exception as err:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid weights query parameter. Must be valid JSON mapping: {err}",
        ) from err


def _contribution(method: str, normalized_value: float, weight: float) -> float:
    """Return the criterion's contribution under the chosen method.

    For a weighted sum the contribution is additive and sums to the total
    score.  The weighted product and the distance-to-ideal method are not
    additive, so the factor each criterion contributes is reported instead
    and the aggregate score is computed by the scoring engine.
    """

    if method == "weighted_sum":
        return normalized_value * weight
    if method == "weighted_product":
        return (normalized_value ** weight) if normalized_value > 0 else 0.0
    if method == "distance_to_ideal":
        return weight * ((1.0 - normalized_value) ** 2)
    return normalized_value * weight


def _criterion_metadata() -> Dict[str, Dict[str, Any]]:
    """Return label / category / direction for every leaf criterion."""

    from scoring.criteria_hierarchy import CRITERIA_TREE, iter_leaves

    metadata: Dict[str, Dict[str, Any]] = {}
    for category, _, criterion in iter_leaves(CRITERIA_TREE):
        metadata[criterion.key] = {
            "label": criterion.label,
            "category": category.label,
            "direction": criterion.direction.value if criterion.direction else None,
        }
    return metadata


@router.get(
    "/sites/{site_id}/decomposition",
    response_model=SiteDecompositionResponse,
    summary="Get per-criterion score breakdown for a specific site",
)
def get_site_decomposition(
    site_id: str,
    weights: str = Query(
        ...,
        description=(
            'JSON string of leaf criterion weights, e.g. '
            '{"resident_density":0.4,"projected_growth":0.6}'
        ),
    ),
    method: str = Query(
        "weighted_sum",
        description="Aggregation method (weighted_sum, weighted_product, distance_to_ideal)",
    ),
) -> SiteDecompositionResponse:
    """Explain a site's score criterion by criterion.

    The weights are aligned to the criteria that are actually present in
    the scoring matrix.  Criteria whose data is unavailable are reported
    in ``dropped_criteria`` and the response reports the resulting
    ``coverage`` so the interface can disclose the reduced evidence base.
    """

    normalized_key = method.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized_key not in METHODS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown aggregation method '{method}'. Choose from: {sorted(METHODS.keys())}",
        )

    matrix = _load_normalized_matrix()
    weights_dict = _parse_weights(weights)

    aligned_weights, dropped, coverage = align_weights_to_columns(
        weights_dict, list(matrix.columns)
    )
    if not aligned_weights:
        raise HTTPException(
            status_code=400,
            detail=(
                "None of the requested criteria could be scored with the current "
                "data release. Available criteria: " + ", ".join(map(str, matrix.columns))
            ),
        )

    row = None
    for index in matrix.index:
        if str(index) == str(site_id):
            row = matrix.loc[index]
            break
    if row is None:
        raise HTTPException(status_code=404, detail=f"Site with id '{site_id}' not found.")

    scores = apply_weights(matrix, aligned_weights, method=normalized_key)
    total = float(scores.loc[row.name])

    ranks = scores.sort_values(ascending=False, kind="mergesort")
    rank = int(list(ranks.index).index(row.name)) + 1

    metadata = _criterion_metadata()

    criteria_list: List[CriterionDecomposition] = []
    for criterion, weight in aligned_weights.items():
        norm_val = float(row[criterion])
        info = metadata.get(criterion, {})
        criteria_list.append(
            CriterionDecomposition(
                criterion=criterion,
                label=str(info.get("label") or criterion.replace("_", " ").title()),
                category=str(info.get("category") or ""),
                normalized_value=norm_val,
                weight=weight,
                contribution=_contribution(normalized_key, norm_val, weight),
                direction=info.get("direction"),
            )
        )

    criteria_list.sort(key=lambda item: item.contribution, reverse=True)

    return SiteDecompositionResponse(
        site_id=site_id,
        method=normalized_key,
        total_score=total,
        criteria=criteria_list,
        rank=rank,
        dropped_criteria=dropped,
        coverage=round(coverage, 6),
    )
