"""
api/sensitivity_routes.py

FastAPI router exposing sensitivity analysis endpoints for retail site selection:
1. GET /sensitivity/thresholds   - File 38 critical threshold report
2. GET /sensitivity/stability    - File 39 rank stability report
3. GET /sensitivity/near-ties    - File 40 near-tie groups
4. GET /sensitivity/cross-method - File 30 cross-method agreement summary

All endpoints consistently accept the current weight vector as input via:
- JSON request body: e.g. {"weights": {"accessibility": 0.4, ...}} or {"accessibility": 0.4, ...}
- Query parameter: e.g. ?weights={"accessibility":0.4,...} or ?accessibility=0.4&demographics=0.6
- App state fallback: request.app.state.current_weights / request.app.state.weights
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Mapping, Optional, Sequence, Union

import numpy as np
import pandas as pd
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

# =============================================================================
# Robust Dependency Imports (with internal fallbacks matching Files 30,32,38,39,40)
# =============================================================================

# --- File 32: Scoring Base ---
from scoring.score import (
    _unwrap_precomputed_matrix,
    apply_weights,
    rank_sites,
)
from scoring.cross_method_agreement import compare_rankings
from sensitivity.critical_thresholds import compute_all_thresholds, find_critical_threshold
from sensitivity.monte_carlo import simulate_rank_distribution
from sensitivity.near_ties import derive_uncertainty_threshold, identify_near_ties
from sensitivity.rank_reversal import detect_rank_reversals
from sensitivity.stability import rank_stability_report, sample_weight_perturbations


# =============================================================================
# Request Schemas & Helper Utilities
# =============================================================================

class WeightPayload(BaseModel):
    """Payload schema allowing flexible input of weight vectors."""
    weights: Optional[Union[Dict[str, float], List[float]]] = Field(
        default=None,
        description="Dictionary mapping criterion name to float weight, or a list of float weights."
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "weights": {
                    "foot_traffic": 0.35,
                    "demographics": 0.25,
                    "accessibility": 0.20,
                    "rental_cost": 0.20
                }
            }
        }
    }


def _clean_json_record(obj: Any) -> Any:
    """Ensure all numpy/pandas types and NaNs are converted to native Python types/None."""
    if isinstance(obj, dict):
        return {k: _clean_json_record(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean_json_record(v) for v in obj]
    if isinstance(obj, (np.floating, float)):
        return None if (np.isnan(obj) or np.isinf(obj)) else float(obj)
    if isinstance(obj, (np.integer, int)):
        return int(obj)
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if pd.isna(obj):
        return None
    return obj


async def resolve_weight_vector(
    request: Request,
    payload: Optional[WeightPayload] = None,
    weights_query: Optional[str] = None,
) -> Union[Dict[str, float], List[float]]:
    """
    Extract the weight vector consistently from:
    1. Pydantic request body `payload.weights`
    2. Raw request body (JSON dict/list directly e.g. `{"c1": 0.5}`)
    3. `weights` query parameter (JSON string or comma-separated pairs)
    4. General query parameters matching criterion names
    5. Application state: `request.app.state.current_weights` or `.weights`
    """
    # 1. Pydantic Payload
    if payload is not None and payload.weights is not None:
        return payload.weights

    # 2. Query Parameter 'weights'
    if weights_query:
        weights_str = weights_query.strip()
        if weights_str.startswith("{") and weights_str.endswith("}"):
            try:
                parsed = json.loads(weights_str)
                if isinstance(parsed, dict):
                    return {str(k): float(v) for k, v in parsed.items()}
            except (json.JSONDecodeError, ValueError):
                pass
        elif weights_str.startswith("[") and weights_str.endswith("]"):
            try:
                parsed = json.loads(weights_str)
                if isinstance(parsed, list):
                    return [float(v) for v in parsed]
            except (json.JSONDecodeError, ValueError):
                pass
        elif "," in weights_str:
            parts = [p.strip() for p in weights_str.split(",") if p.strip()]
            if all(":" in p or "=" in p for p in parts):
                res = {}
                for p in parts:
                    delim = ":" if ":" in p else "="
                    k, v = p.split(delim, 1)
                    res[k.strip()] = float(v.strip())
                return res
            else:
                try:
                    return [float(p) for p in parts]
                except ValueError:
                    pass

    # 3. Raw Body Inspection (for direct GET/POST bodies without wrapping 'weights')
    try:
        raw_body = await request.body()
        if raw_body:
            parsed_json = json.loads(raw_body.decode("utf-8"))
            if isinstance(parsed_json, dict):
                if "weights" in parsed_json and parsed_json["weights"] is not None:
                    return parsed_json["weights"]
                # Direct dictionary of {criterion: weight}
                try:
                    return {str(k): float(v) for k, v in parsed_json.items() if not str(k).startswith("_")}
                except (ValueError, TypeError):
                    pass
            elif isinstance(parsed_json, list):
                return [float(v) for v in parsed_json]
    except Exception:
        pass

    # 4. Check arbitrary query params (e.g. ?c1=0.4&c2=0.6)
    reserved_params = {
        "weights", "n_samples", "top_n", "method", "coarse_steps",
        "uncertainty_threshold", "rank_diff_threshold", "percentile",
        "derive_from_perturbations"
    }
    extracted_params = {}
    for key, val in request.query_params.items():
        if key not in reserved_params:
            try:
                extracted_params[key] = float(val)
            except ValueError:
                pass
    if extracted_params:
        return extracted_params

    # 5. App State Fallback
    for attr in ("current_weights", "weights", "default_weights"):
        if hasattr(request.app.state, attr):
            state_weights = getattr(request.app.state, attr)
            if state_weights is not None:
                return state_weights

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=(
            "Weight vector is required. Provide it via request body (e.g. {'weights': {...}}), "
            "the 'weights' query parameter (e.g. ?weights={'c1':0.5}), or set "
            "request.app.state.current_weights."
        ),
    )


def _require_weights(current_weights: Any) -> Any:
    """Reject a weight vector that cannot produce a report.

    An empty vector, or one in which every weight is zero, is a bad
    request: the analysis has nothing to perturb.  Reporting it as a
    server error would hide the mistake behind a 500.
    """

    if isinstance(current_weights, Mapping):
        values = list(current_weights.values())
    elif isinstance(current_weights, (list, tuple)):
        values = list(current_weights)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The weight vector must be a mapping of criterion to weight.",
        )

    if not values:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "The weight vector is empty. Supply a weight for at least one "
                "criterion."
            ),
        )

    try:
        positive = any(float(value) > 0 for value in values)
    except (TypeError, ValueError):
        positive = False
    if not positive:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The weight vector must contain at least one positive weight.",
        )

    return current_weights


def get_normalized_matrix(request: Request) -> Any:
    """Retrieve the normalized decision matrix used for sensitivity analysis.

    The same resolution path is used as for scoring, so a sensitivity run
    always analyses exactly the matrix that produced the ranking.
    """

    for attr in ("normalized_matrix", "matrix", "precomputed_matrix", "matrix_artifact"):
        if hasattr(request.app.state, attr):
            value = getattr(request.app.state, attr)
            if value is not None:
                return value

    try:
        from api.app.routers.scenarios import get_normalized_matrix

        return get_normalized_matrix()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Normalized decision matrix is not available: {exc}",
        ) from exc


# =============================================================================
# Router Definition
# =============================================================================

router = APIRouter(tags=["Sensitivity Analysis"])


# -----------------------------------------------------------------------------
# 1. GET /sensitivity/thresholds
# -----------------------------------------------------------------------------
@router.get(
    "/sensitivity/thresholds",
    summary="Critical Threshold Report",
    response_description="File 38 critical threshold report for each criterion.",
)
@router.get("/thresholds", include_in_schema=False)
async def get_critical_thresholds(
    request: Request,
    payload: Optional[WeightPayload] = Body(None),
    weights: Optional[str] = Query(None, description="Current weight vector as JSON string or comma-separated pairs."),
    method: str = Query("weighted_sum", description="Scoring aggregation method ('weighted_sum', 'weighted_product', 'distance_to_ideal')."),
    coarse_steps: int = Query(40, ge=2, description="Coarse grid points per direction before bisection."),
    matrix: Any = Depends(get_normalized_matrix),
):
    """
    Returns File 38's critical threshold report for the current weights.

    Finds, for each criterion, how far its weight can move (holding other relative
    proportions fixed) before the top-ranked site changes.
    """
    current_weights = _require_weights(
        await resolve_weight_vector(request, payload=payload, weights_query=weights)
    )

    try:
        report_df = compute_all_thresholds(
            normalized_matrix=matrix,
            current_weights=current_weights,
            method=method,
            coarse_steps=coarse_steps,
        )
        report_clean = report_df.replace({np.nan: None}).to_dict(orient="records")
        return _clean_json_record(report_clean)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Threshold calculation failed: {e}")


# -----------------------------------------------------------------------------
# 2. GET /sensitivity/stability
# -----------------------------------------------------------------------------
@router.get(
    "/sensitivity/stability",
    summary="Rank Stability Report",
    response_description="File 39 rank stability percentages under random weight perturbations.",
)
@router.get("/stability", include_in_schema=False)
async def get_rank_stability(
    request: Request,
    payload: Optional[WeightPayload] = Body(None),
    weights: Optional[str] = Query(None, description="Current weight vector as JSON string or comma-separated pairs."),
    n_samples: int = Query(200, ge=0, description="Number of perturbed weight vectors to evaluate."),
    top_n: Optional[int] = Query(None, gt=0, description="Optional top-N subset stability criterion. If None, checks exact baseline rank."),
    matrix: Any = Depends(get_normalized_matrix),
):
    """
    Returns File 39's rank stability report.

    Evaluates how often each site retains its baseline rank (or stays in top-N)
    under uniform random perturbations of the current criterion weights.
    """
    current_weights = _require_weights(
        await resolve_weight_vector(request, payload=payload, weights_query=weights)
    )

    try:
        report_df = rank_stability_report(
            normalized_matrix=matrix,
            current_weights=current_weights,
            n_samples=n_samples,
            top_n=top_n,
        )
        report_clean = report_df.replace({np.nan: None}).to_dict(orient="records")
        return _clean_json_record(report_clean)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Stability calculation failed: {e}")


# -----------------------------------------------------------------------------
# 3. GET /sensitivity/near-ties
# -----------------------------------------------------------------------------
@router.get(
    "/sensitivity/near-ties",
    summary="Near-Tie Groups",
    response_description="File 40 ordered clusters of effectively tied sites.",
)
@router.get("/near-ties", include_in_schema=False)
async def get_near_ties(
    request: Request,
    payload: Optional[WeightPayload] = Body(None),
    weights: Optional[str] = Query(None, description="Current weight vector as JSON string or comma-separated pairs."),
    uncertainty_threshold: Optional[float] = Query(None, ge=0.0, description="Max score difference to treat as tied. If omitted, uses 0.5% of score spread."),
    method: str = Query("weighted_sum", description="Scoring aggregation method."),
    derive_from_perturbations: bool = Query(False, description="Whether to derive uncertainty threshold from File 39 score std across perturbations."),
    percentile: float = Query(50.0, ge=0.0, le=100.0, description="Percentile of score std if derive_from_perturbations is True."),
    matrix: Any = Depends(get_normalized_matrix),
):
    """
    Returns File 40's near-tie groups.

    Groups adjacent ranked sites whose score difference is smaller than an
    uncertainty threshold, returning them as rank clusters for UI display.
    """
    current_weights = _require_weights(
        await resolve_weight_vector(request, payload=payload, weights_query=weights)
    )

    try:
        # Score sites with the current weights
        scores = apply_weights(matrix, current_weights, method=method)
        ranked_scores = rank_sites(scores)

        # Derive uncertainty threshold from perturbations if requested
        if uncertainty_threshold is None and derive_from_perturbations:
            w = list(current_weights.values()) if isinstance(current_weights, Mapping) else current_weights
            samples = sample_weight_perturbations(w, n_samples=100)
            sampled_scores = [apply_weights(matrix, sw, method=method).to_numpy() for sw in samples]
            score_std = np.std(sampled_scores, axis=0)
            uncertainty_threshold = derive_uncertainty_threshold(score_std, percentile=percentile)

        clusters = identify_near_ties(ranked_scores, uncertainty_threshold=uncertainty_threshold)
        return _clean_json_record(clusters)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Near-tie clustering failed: {e}")


# -----------------------------------------------------------------------------
# 4. GET /sensitivity/cross-method
# -----------------------------------------------------------------------------
@router.get(
    "/sensitivity/cross-method",
    summary="Cross-Method Agreement Summary",
    response_description="File 30 cross-method rank comparisons, pairwise Spearman correlations, and flagged sensitive sites.",
)
@router.get("/cross-method", include_in_schema=False)
async def get_cross_method_agreement(
    request: Request,
    payload: Optional[WeightPayload] = Body(None),
    weights: Optional[str] = Query(None, description="Current weight vector as JSON string or comma-separated pairs."),
    rank_diff_threshold: int = Query(3, ge=0, description="Minimum rank spread across methods to flag a site as ranking-sensitive."),
    matrix: Any = Depends(get_normalized_matrix),
):
    """
    Returns File 30's cross-method agreement summary.

    Compares rankings across:
    - Weighted Sum (File 27)
    - Weighted Product (File 28)
    - Distance to Ideal / TOPSIS (File 29)
    Quantifies overall agreement via Spearman correlation and flags unstable sites.
    """
    current_weights = _require_weights(
        await resolve_weight_vector(request, payload=payload, weights_query=weights)
    )

    try:
        ws_scores = apply_weights(matrix, current_weights, method="weighted_sum")
        wp_scores = apply_weights(matrix, current_weights, method="weighted_product")
        dti_scores = apply_weights(matrix, current_weights, method="distance_to_ideal")

        def _extract_values(s):
            if isinstance(s, (pd.Series, pd.DataFrame)):
                return s.to_numpy().reshape(-1)
            return np.asarray(s, dtype=float).reshape(-1)

        _, site_ids, _ = _unwrap_precomputed_matrix(matrix)

        agreement = compare_rankings(
            weighted_sum_result=_extract_values(ws_scores),
            weighted_product_result=_extract_values(wp_scores),
            distance_to_ideal_result=_extract_values(dti_scores),
            site_ids=site_ids,
            rank_diff_threshold=rank_diff_threshold,
        )
        return _clean_json_record(agreement)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Cross-method agreement failed: {e}")


# -----------------------------------------------------------------------------
# 5. GET /sensitivity/rank-reversals
# -----------------------------------------------------------------------------
@router.get(
    "/sensitivity/rank-reversals",
    summary="Rank Reversal Detection",
    response_description=(
        "The pairs of sites whose order is least stable under weight "
        "perturbations, most exposed first."
    ),
)
@router.get("/rank-reversals", include_in_schema=False)
async def get_rank_reversals(
    request: Request,
    payload: Optional[WeightPayload] = Body(None),
    weights: Optional[str] = Query(None, description="Current weight vector as JSON string or comma-separated pairs."),
    method: str = Query("weighted_sum", description="Scoring aggregation method."),
    n_samples: int = Query(200, ge=1, le=5000, description="Number of perturbed weight vectors to evaluate."),
    perturbation_size: float = Query(0.1, ge=0.0, le=1.0, description="Relative perturbation applied to each weight."),
    seed: int = Query(20260101, description="Seed for the perturbation sampler, so the report is reproducible."),
    max_pairs: int = Query(25, ge=1, le=500, description="The most at-risk pairs to report."),
    matrix: Any = Depends(get_normalized_matrix),
):
    """Return the pairs of sites that are most likely to exchange places.

    A reversal between two sites that are close together is materially
    more important than a reversal far down the list, so the report is
    ordered by how often each pair swapped.
    """

    current_weights = _require_weights(
        await resolve_weight_vector(request, payload=payload, weights_query=weights)
    )

    try:
        report = detect_rank_reversals(
            normalized_matrix=matrix,
            current_weights=current_weights,
            n_samples=n_samples,
            perturbation_size=perturbation_size,
            method=method,
            seed=seed,
            max_pairs=max_pairs,
        )
        return _clean_json_record(report.to_dict())
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Rank reversal detection failed: {e}",
        )


# -----------------------------------------------------------------------------
# 6. GET /sensitivity/monte-carlo
# -----------------------------------------------------------------------------
@router.get(
    "/sensitivity/monte-carlo",
    summary="Monte-Carlo Rank Distribution",
    response_description=(
        "The distribution of ranks each site attains across a simulated "
        "distribution of plausible weightings."
    ),
)
@router.get("/monte-carlo", include_in_schema=False)
async def get_monte_carlo_distribution(
    request: Request,
    payload: Optional[WeightPayload] = Body(None),
    weights: Optional[str] = Query(None, description="Current weight vector as JSON string or comma-separated pairs."),
    method: str = Query("weighted_sum", description="Scoring aggregation method."),
    n_samples: int = Query(200, ge=1, le=5000, description="Number of weightings to simulate."),
    perturbation_size: float = Query(0.1, ge=0.0, le=1.0, description="Relative perturbation applied to each weight."),
    seed: int = Query(20260101, description="Seed for the perturbation sampler, so the report is reproducible."),
    top_n: int = Query(3, ge=1, le=100, description="The size of the top-N share that is reported."),
    matrix: Any = Depends(get_normalized_matrix),
):
    """Return the rank distribution each site attains under uncertain weights.

    This answers the question the stability report cannot: not just how
    often a site holds its rank, but the full spread of ranks it could
    plausibly end up with.
    """

    current_weights = _require_weights(
        await resolve_weight_vector(request, payload=payload, weights_query=weights)
    )

    try:
        report = simulate_rank_distribution(
            normalized_matrix=matrix,
            current_weights=current_weights,
            n_samples=n_samples,
            perturbation_size=perturbation_size,
            method=method,
            seed=seed,
            top_n=top_n,
        )
        return _clean_json_record(report.to_dict())
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Monte-Carlo simulation failed: {e}",
        )


__all__ = ["router"]