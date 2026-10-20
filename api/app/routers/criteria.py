"""Criteria hierarchy API.

The interface must not hard-code criterion names or weights: the analytical
authority for the criteria tree is :mod:`scoring.criteria_hierarchy`, and
this router is the single place where that tree is exposed to clients.

Endpoints
---------
``GET  /criteria``            the full tree with direction, scoring mode and
                              data-availability metadata.
``GET  /criteria/rollup``     resolve a category/leaf weight configuration
                              into global leaf weights.
``POST /criteria/rollup``     same, with a richer request body.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from scoring.criteria_hierarchy import CRITERIA_TREE, iter_leaves
from scoring.weight_model import (
    WeightModelError,
    align_weights_to_columns,
    build_level_weights,
    category_keys,
    leaf_keys,
    resolve_leaf_weights,
    weights_for_report,
)

router = APIRouter(prefix="/criteria", tags=["Criteria"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class CriterionNode(BaseModel):
    key: str
    label: str
    direction: Optional[str] = Field(
        default=None,
        description="'benefit' (higher is better), 'cost' (lower is better) or null for target-band criteria.",
    )
    scoring_mode: str = Field(
        default="monotonic",
        description="'monotonic' or 'target_band'.",
    )
    target_band: Optional[list[float]] = Field(
        default=None,
        description="Ideal range [low, high] for target-band criteria.",
    )
    data_field: str = Field(
        default="",
        description="Dotted path into the ingested data model.",
    )
    data_available: bool = Field(
        default=True,
        description=(
            "False when the backing dataset has not been materialised yet. "
            "Criteria without data are excluded from scoring and the weight "
            "mass they carried is redistributed across the criteria that "
            "can be scored."
        ),
    )
    notes: str = ""


class SubcategoryNode(BaseModel):
    key: str
    label: str
    criteria: list[CriterionNode]


class CategoryNode(BaseModel):
    key: str
    label: str
    subcategories: list[SubcategoryNode]


class CriteriaTreeResponse(BaseModel):
    categories: list[CategoryNode]
    category_keys: list[str]
    leaf_keys: list[str]
    leaf_count: int
    scorable_leaf_count: int
    notes: str = (
        "Criterion weights are expressed over the eight categories and are "
        "rolled down to the 28 leaf criteria by the hierarchical weight "
        "model. Leaves whose data is unavailable in the current data "
        "release are excluded from scoring and disclosed as dropped criteria."
    )


class RollupRequest(BaseModel):
    category_weights: Optional[dict[str, float]] = Field(
        default=None,
        description=(
            "Relative importance of each top-level category. Normalised to "
            "sum to 1.0. Omitted categories receive zero weight."
        ),
    )
    leaf_weights: Optional[dict[str, dict[str, float]]] = Field(
        default=None,
        description=(
            "Optional within-category leaf weights, keyed by category key. "
            "Each inner mapping is normalised within its category; leaves "
            "that are not mentioned receive zero weight."
        ),
    )

    @field_validator("leaf_weights")
    @classmethod
    def _validate_leaf_weights(cls, value):
        if value is None:
            return value
        for category, mapping in value.items():
            if not isinstance(mapping, dict):
                raise ValueError(
                    f"Leaf weights for category {category!r} must be an object."
                )
        return value


class RollupResponse(BaseModel):
    leaf_weights: dict[str, float]
    category_weights: dict[str, float]
    breakdown: list[dict[str, Any]]
    leaf_keys: list[str]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _criterion_node(criterion) -> CriterionNode:
    target_band = list(criterion.target_band) if criterion.target_band else None
    return CriterionNode(
        key=criterion.key,
        label=criterion.label,
        direction=criterion.direction.value if criterion.direction else None,
        scoring_mode=criterion.scoring_mode.value,
        target_band=target_band,
        data_field=criterion.data_field,
        data_available=not criterion.pending,
        notes=criterion.notes,
    )


def build_tree_payload() -> CriteriaTreeResponse:
    """Serialise the criteria tree into the API response shape."""

    categories: list[CategoryNode] = []
    for category in CRITERIA_TREE:
        subcategories = [
            SubcategoryNode(
                key=subcategory.key,
                label=subcategory.label,
                criteria=[
                    _criterion_node(criterion) for criterion in subcategory.criteria
                ],
            )
            for subcategory in category.subcategories
        ]
        categories.append(
            CategoryNode(
                key=category.key,
                label=category.label,
                subcategories=subcategories,
            )
        )

    leaves = list(iter_leaves(CRITERIA_TREE))
    scorable = [criterion for _, _, criterion in leaves if not criterion.pending]

    return CriteriaTreeResponse(
        categories=categories,
        category_keys=category_keys(CRITERIA_TREE),
        leaf_keys=leaf_keys(CRITERIA_TREE),
        leaf_count=len(leaves),
        scorable_leaf_count=len(scorable),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=CriteriaTreeResponse,
    summary="Retrieve the authoritative criteria hierarchy",
)
def get_criteria() -> CriteriaTreeResponse:
    """Return the full criteria tree.

    Clients should render the criteria from this response rather than
    hard-coding names, so that the interface always reflects the
    authoritative scoring model.
    """

    return build_tree_payload()


@router.post(
    "/rollup",
    response_model=RollupResponse,
    summary="Roll category and leaf weights up to global leaf weights",
)
def rollup_weights(payload: RollupRequest) -> RollupResponse:
    """Convert an executive/analyst weight configuration into leaf weights.

    The roll-up is a straight product of the level weights along each
    leaf's path, which is the documented behaviour of the hierarchical
    weighting model.  No site score is produced here.
    """

    try:
        weights = resolve_leaf_weights(
            payload.category_weights, payload.leaf_weights, CRITERIA_TREE
        )
        _, normalised_categories = build_level_weights(
            payload.category_weights, payload.leaf_weights, CRITERIA_TREE
        )
    except WeightModelError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return RollupResponse(
        leaf_weights={key: round(value, 8) for key, value in weights.items()},
        category_weights={
            key: round(value, 8) for key, value in normalised_categories.items()
        },
        breakdown=weights_for_report(weights, CRITERIA_TREE),
        leaf_keys=leaf_keys(CRITERIA_TREE),
    )


@router.get(
    "/rollup",
    response_model=RollupResponse,
    summary="Roll category weights up to global leaf weights (query form)",
)
def rollup_weights_query(
    category_weights: Optional[str] = Query(
        default=None,
        description=(
            "JSON object of category weights, e.g. "
            '\'{"population":0.3,"accessibility":0.4}\'.'
        ),
    ),
) -> RollupResponse:
    """Convenience GET form of :func:`rollup_weights`."""

    parsed: dict[str, float] | None = None
    if category_weights:
        import json

        try:
            decoded = json.loads(category_weights)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"category_weights must be a JSON object: {exc}",
            ) from exc
        if not isinstance(decoded, dict):
            raise HTTPException(
                status_code=400,
                detail="category_weights must be a JSON object.",
            )
        parsed = {str(key): float(value) for key, value in decoded.items()}

    return rollup_weights(RollupRequest(category_weights=parsed))


@router.get(
    "/scorable",
    summary="List the leaf criteria that can be scored in this data release",
)
def scorable_criteria() -> dict[str, Any]:
    """Return the leaf criteria whose backing data is materialised.

    Scoring weights can only be applied to these criteria.  The alignment
    helper in :mod:`scoring.weight_model` redistributes the weight mass
    of unavailable criteria and reports the resulting coverage.
    """

    scorable = [
        criterion.key
        for _, _, criterion in iter_leaves(CRITERIA_TREE)
        if not criterion.pending
    ]
    pending = [
        criterion.key
        for _, _, criterion in iter_leaves(CRITERIA_TREE)
        if criterion.pending
    ]
    return {
        "scorable_criteria": scorable,
        "unavailable_criteria": pending,
        "scorable_count": len(scorable),
        "unavailable_count": len(pending),
    }


@router.get("/alignment", summary="Explain how weights map onto a scoring matrix")
def alignment_preview(
    matrix_columns: str = Query(
        ...,
        description="Comma-separated list of the columns present in the scoring matrix.",
    ),
    category_weights: Optional[str] = Query(default=None),
) -> dict[str, Any]:
    """Preview the weight alignment for a given set of matrix columns.

    Useful for the interface to disclose reduced coverage before the user
    commits to a ranking.
    """

    import json

    columns = [item.strip() for item in matrix_columns.split(",") if item.strip()]
    if not columns:
        raise HTTPException(status_code=400, detail="matrix_columns must not be empty.")

    parsed: dict[str, float] | None = None
    if category_weights:
        try:
            decoded = json.loads(category_weights)
            parsed = {str(key): float(value) for key, value in decoded.items()}
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=400,
                detail=f"category_weights must be a JSON object of numbers: {exc}",
            ) from exc

    try:
        weights = resolve_leaf_weights(parsed, None, CRITERIA_TREE)
    except WeightModelError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    aligned, dropped, coverage = align_weights_to_columns(weights, columns)
    return {
        "aligned_weights": {key: round(value, 8) for key, value in aligned.items()},
        "dropped_criteria": dropped,
        "coverage": round(coverage, 6),
        "scored_criterion_count": len(aligned),
    }
