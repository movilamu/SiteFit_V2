"""
api/score_routes.py

FastAPI router for multi-criteria site scoring.

Request/Response Schema Convention:
----------------------------------
This router establishes the standardized request payload structure for passing criterion weights
and selecting aggregation methods across the platform.

Consumed by:
- File 54 (Comparison View): Calls POST /score with custom/adjusted weights to compare side-by-side rankings.
- File 56 (Sensitivity View): Repeatedly calls POST /score while perturbing individual criteria weights to generate sensitivity curves.

Request Body (POST /score):
{
    "weights": {
        "resident_density": 0.4,
        "rent": 0.3,
        "competitor_density": 0.3
    },
    "method": "weighted_sum"  # Options: "weighted_sum" | "weighted_product" | "distance_to_ideal"
}

Response Body (200 OK):
{
    "method": "weighted_sum",
    "sites": [
        {"rank": 1, "site_id": "site_101", "score": 0.842},
        {"rank": 2, "site_id": "site_102", "score": 0.715},
        ...
    ]
}
"""

from __future__ import annotations

import math
from typing import Dict, List, Literal, Optional, Sequence, Union

from fastapi import APIRouter, HTTPException, status
import pandas as pd
from pydantic import BaseModel, Field, field_validator, model_validator

# Fallback imports to support module-style package import or direct script execution
from app.core.matrix_store import MatrixUnavailableError
from scoring.criteria_hierarchy import CRITERIA_TREE
from scoring.score import apply_weights, rank_sites
from scoring.weight_model import (
    WeightModelError,
    align_weights_to_columns,
    resolve_leaf_weights,
)


router = APIRouter(prefix="", tags=["scoring"])


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class LevelWeights(BaseModel):
    """Executive/analyst weight configuration over the criteria hierarchy."""

    category_weights: Optional[Dict[str, float]] = Field(
        default=None,
        description="Relative importance of each top-level category.",
    )
    leaf_weights: Optional[Dict[str, Dict[str, float]]] = Field(
        default=None,
        description="Optional within-category leaf weights, keyed by category.",
    )


class ScoreRequest(BaseModel):
    """Payload for scoring sites.

    Exactly one of ``weights`` (explicit leaf weights) or ``level_weights``
    (category weights with optional within-category leaf weights) may be
    supplied.  ``level_weights`` is the form used by the interface, because
    decision makers think in categories while the scoring engine works on
    the 28 leaf criteria.
    """

    weights: Optional[Dict[str, float]] = Field(
        default=None,
        description="Explicit leaf-criterion weights. Must sum to ~1.0.",
    )
    level_weights: Optional[LevelWeights] = Field(
        default=None,
        description="Category weights and optional within-category leaf weights.",
    )
    method: Literal["weighted_sum", "weighted_product", "distance_to_ideal"] = Field(
        default="weighted_sum",
        description="Aggregation method from the scoring engine.",
    )

    @field_validator("weights")
    @classmethod
    def validate_weights_sum(cls, weights: Optional[Dict[str, float]]) -> Optional[Dict[str, float]]:
        """Validate that weights are non-negative and sum to approximately 1.0."""

        if weights is None:
            return None
        if not weights:
            raise ValueError("The 'weights' mapping cannot be empty.")

        for key, value in weights.items():
            if value < 0.0:
                raise ValueError(f"Weight for criterion '{key}' must be non-negative (got {value}).")

        total = sum(weights.values())
        if not math.isclose(total, 1.0, abs_tol=0.01):
            raise ValueError(
                f"Weights must sum to 1.0 (Â±0.01). Current total sum is {total:.4f}."
            )

        return weights

    @model_validator(mode="after")
    def validate_single_source(self) -> "ScoreRequest":
        if (self.weights is None) == (self.level_weights is None):
            raise ValueError(
                "Provide exactly one of 'weights' or 'level_weights'."
            )
        return self


class RankedSiteResult(BaseModel):
    rank: int = Field(..., description="1-based ranking position (1 is best).")
    site_id: Union[str, int] = Field(..., description="Unique site identifier.")
    score: float = Field(..., description="Computed aggregation score.")


class ScoreResponse(BaseModel):
    method: str = Field(..., description="The aggregation method used for scoring.")
    sites: List[RankedSiteResult] = Field(
        ..., description="Ranked list of sites ordered best-first."
    )
    effective_weights: Dict[str, float] = Field(
        default_factory=dict,
        description="The leaf weights actually applied, after rolling down and coverage adjustment.",
    )
    dropped_criteria: List[str] = Field(
        default_factory=list,
        description=(
            "Criteria that could not be scored because their data is not "
            "available in the current data release."
        ),
    )
    coverage: float = Field(
        default=1.0,
        description="Share of the requested weight mass that could actually be scored (0-1).",
    )


# ---------------------------------------------------------------------------
# File 31 normalized matrix â€” same loader as File 46 (no random mock data)
# ---------------------------------------------------------------------------

def _resolve_requested_weights(request: ScoreRequest) -> Dict[str, float]:
    """Resolve the caller's weight configuration into leaf weights.

    ``level_weights`` is rolled down through the criteria hierarchy using
    the documented hierarchical weight model; ``weights`` is used as-is.
    """

    if request.weights is not None:
        return dict(request.weights)

    level = request.level_weights
    assert level is not None  # guaranteed by the request validator
    try:
        return resolve_leaf_weights(
            level.category_weights, level.leaf_weights, CRITERIA_TREE
        )
    except WeightModelError as exc:
        raise ValueError(str(exc)) from exc


def _get_precomputed_matrix(criteria_keys: Sequence[str]) -> pd.DataFrame:
    """Load the precomputed, normalized matrix used for scoring.

    The matrix is produced offline by the precompute job and loaded through
    the shared matrix store, so scoring, decomposition, scenarios and
    sensitivity all analyse exactly the same release.

    The full matrix is returned.  Criteria that the caller asked for but
    that are not present in the release are handled by
    :func:`scoring.weight_model.align_weights_to_columns`, which
    redistributes their weight across the criteria that could be scored
    and reports the dropped criteria.
    """

    from app.routers.scenarios import get_normalized_matrix

    try:
        matrix = get_normalized_matrix()
    except MatrixUnavailableError:
        from app.core.matrix_store import load_normalized_matrix

        matrix = load_normalized_matrix()

    if not criteria_keys:
        return matrix

    available = [key for key in criteria_keys if key in matrix.columns]
    if not available:
        raise ValueError(
            "None of the requested criteria are present in the scoring matrix. "
            "Available criteria: " + ", ".join(map(str, matrix.columns))
        )
    return matrix


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/score",
    response_model=ScoreResponse,
    status_code=status.HTTP_200_OK,
    summary="Compute site scores and rankings",
    description=(
        "Accepts criterion weights and an aggregation method, applies the "
        "aggregation algorithm over the precomputed normalised matrix, and "
        "returns ranked sites sorted descending by score.  The response "
        "reports the effective leaf weights and the share of the requested "
        "weight mass that could be scored."
    ),
)
def compute_scores(request: ScoreRequest) -> ScoreResponse:
    try:
        # 1. Resolve the effective leaf weights.
        requested_weights = _resolve_requested_weights(request)

        # 2. Fetch the precomputed matrix matching the requested criteria.
        normalized_matrix = _get_precomputed_matrix(list(requested_weights.keys()))

        # 3. Align the weights with the criteria that could be scored and
        #    disclose the criteria whose data is unavailable.
        aligned, dropped, coverage = align_weights_to_columns(
            requested_weights, list(normalized_matrix.columns)
        )
        if not aligned:
            raise ValueError(
                "None of the requested criteria could be scored with the "
                "current data release. Available criteria: "
                + ", ".join(map(str, normalized_matrix.columns))
            )

        # 4. Apply weights via the scoring engine.
        scores_series = apply_weights(
            normalized_matrix=normalized_matrix,
            global_weights=aligned,
            method=request.method,
        )

        # 5. Sort and rank sites descending by score.
        ranked_df = rank_sites(scores_series)

        # 6. Transform output into the standard JSON schema response.
        sites_list = [
            RankedSiteResult(
                rank=int(row["rank"]),
                site_id=str(row["site_id"]),
                score=round(float(row["score"]), 6),
            )
            for _, row in ranked_df.iterrows()
        ]

        return ScoreResponse(
            method=request.method,
            sites=sites_list,
            effective_weights={key: round(value, 8) for key, value in aligned.items()},
            dropped_criteria=dropped,
            coverage=round(coverage, 6),
        )

    except ValueError as err:
        # Catch unexpected mathematical or alignment errors and present as 422
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(err),
        ) from err
    except RuntimeError as err:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(err),
        ) from err
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred while scoring: {str(err)}",
        ) from err
