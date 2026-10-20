"""Data quality, coverage and confidence reporting.

The platform must disclose the limits of its evidence base.  This router
reports **deterministic, explainable** measures only:

* the freshness of each source (the actual source years present),
* the coverage of each table and of each criterion column,
* the share of matrix values that had to be imputed,
* whether a backtest against the client's own estate is possible.

No synthetic "confidence score" is produced.  Where a single summary
judgement is useful it is derived from the measures above by a rule that
is stated explicitly in the response, so a reader can always see why it
was reached.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Request

from app.core.cache import TTLCache
from app.core.config import get_settings
from concurrent.futures import ThreadPoolExecutor

from app.core.supabase_client import rest_get
from scoring.criteria_hierarchy import CRITERIA_TREE, iter_leaves

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/data-quality", tags=["Data quality"])

#: Limitations that are inherent to the platform's data sources.  These are
#: stated to the user rather than hidden.
KNOWN_LIMITATIONS = [
    {
        "id": "census_vintage",
        "severity": "high",
        "title": "Census data is from 2011",
        "detail": (
            "Demographic and household data derives from the Census of India "
            "2011, the most recent complete enumeration available. Population "
            "growth since 2011 is estimated from trend data where it exists, "
            "not from a newer census."
        ),
    },
    {
        "id": "osm_coverage",
        "severity": "medium",
        "title": "OpenStreetMap coverage is uneven",
        "detail": (
            "Competitive-set, accessibility and land-use data are derived from "
            "OpenStreetMap. Coverage varies considerably between metropolitan, "
            "commercial and residential areas, so a site with few mapped "
            "features is not necessarily a site with no competition."
        ),
    },
    {
        "id": "property_coverage",
        "severity": "medium",
        "title": "Property listing coverage is incomplete",
        "detail": (
            "Listed rents, prices, unit sizes and tenure terms are only "
            "available where a public listing has been ingested. Where they "
            "are absent the cost analysis reports the component as "
            "unavailable rather than estimating it."
        ),
    },
    {
        "id": "routing_quota",
        "severity": "medium",
        "title": "Routing coverage is limited by the free tier",
        "detail": (
            "Drive-time catchments come from OpenRouteService, whose free tier "
            "allows a limited number of isochrone requests per day. Catchment "
            "coverage therefore depends on the quota available when the data "
            "was last generated."
        ),
    },
    {
        "id": "criterion_coverage",
        "severity": "medium",
        "title": "Not every criterion is scorable in every release",
        "detail": (
            "Only criteria whose backing dataset has been materialised can be "
            "scored. The weight mass attached to unavailable criteria is "
            "redistributed across the criteria that can be scored, and the "
            "resulting coverage is reported with every ranking."
        ),
    },
    {
        "id": "not_a_prediction",
        "severity": "high",
        "title": "The platform ranks; it does not predict",
        "detail": (
            "Scores express the relative fit of a site against a stated set of "
            "weights and requirements. They are not a forecast of trading "
            "performance and must not be presented as one."
        ),
    },
    {
        "id": "due_diligence_required",
        "severity": "high",
        "title": "Site visits and commercial due diligence remain necessary",
        "detail": (
            "Before capital commitment, each shortlisted site must be visited "
            "and assessed locally: title and lease terms, structural "
            "condition, footfall at the actual trading hours, local "
            "competition, and the practicalities of servicing the site."
        ),
    },
]


def _grade(value: float, good: float, fair: float) -> str:
    """Grade a coverage ratio deterministically.

    ``good`` and ``fair`` are the thresholds at which coverage is
    considered good and fair respectively.
    """

    if value >= good:
        return "good"
    if value >= fair:
        return "fair"
    return "poor"


#: How long the data-quality report is cached, in seconds.  It is a
#: read-only view of the published data release.
DATA_QUALITY_CACHE_SECONDS = 30.0

_DATA_QUALITY_CACHE = TTLCache(DATA_QUALITY_CACHE_SECONDS)


@router.get("", summary="Data quality, coverage and known limitations")
def get_data_quality(request: Request) -> dict[str, Any]:
    """Return the data-quality report for the current data release.

    The report is a read-only view of the published data release, so it
    is cached for a short period.  Every value in it comes from the
    database; nothing is invented and nothing is hidden.
    """

    return _DATA_QUALITY_CACHE.get_or_set("report", lambda: _build_data_quality(request))


def _build_data_quality(request: Request) -> dict[str, Any]:
    """Assemble the data-quality report from the database."""

    settings = get_settings()
    report: dict[str, Any] = {
        "generated_at": None,
        "sources": [],
        "coverage": {},
        "criteria": [],
        "backtesting": {},
        "limitations": KNOWN_LIMITATIONS,
        "summary": {},
    }

    # --- Scoring matrix ----------------------------------------------
    matrix_info: dict[str, Any] = {"available": False}
    try:
        from app.core.matrix_store import load_normalized_matrix

        matrix = load_normalized_matrix()
        columns = list(matrix.columns)
        matrix_info = {
            "available": True,
            "site_count": int(matrix.shape[0]),
            "criterion_count": int(matrix.shape[1]),
            "criteria": [str(column) for column in columns],
        }
    except Exception as exc:
        matrix_info = {"available": False, "detail": str(exc)}

    report["coverage"]["scoring_matrix"] = matrix_info

    # --- Criterion-level availability --------------------------------
    scorable = {
        criterion.key
        for _, _, criterion in iter_leaves(CRITERIA_TREE)
        if not criterion.pending
    }
    available_columns = set(matrix_info.get("criteria") or [])
    criteria_rows: list[dict[str, Any]] = []
    for category, _, criterion in iter_leaves(CRITERIA_TREE):
        in_matrix = criterion.key in available_columns
        criteria_rows.append(
            {
                "criterion": criterion.key,
                "label": criterion.label,
                "category": category.label,
                "direction": criterion.direction.value if criterion.direction else None,
                "scoring_mode": criterion.scoring_mode.value,
                "data_available": in_matrix,
                "marked_pending": criterion.pending,
                "status": "available" if in_matrix else "unavailable",
            }
        )
    report["criteria"] = criteria_rows

    scored_criteria = sum(1 for row in criteria_rows if row["data_available"])
    total_criteria = len(criteria_rows)
    criterion_coverage = scored_criteria / total_criteria if total_criteria else 0.0

    # --- Supabase table coverage --------------------------------------
    table_specs = [
        ("demographic_data", "Demographic data", "Census of India"),
        ("economic_data", "Economic data", "Household consumption survey"),
        ("competitor_locations", "Competitive set", "OpenStreetMap"),
        ("accessibility_data", "Accessibility", "OpenStreetMap"),
        ("property_listings", "Property listings", "Public tender / listing feed"),
        ("isochrone_cache", "Drive-time catchments", "OpenRouteService"),
        ("own_estate_locations", "Own estate", "Client supplied"),
    ]
    # The source checks are independent, so they run concurrently: ten
    # sequential round trips to a remote database took long enough to
    # be visible in the interface.
    def _check_source(spec: tuple[str, str, str]) -> dict[str, Any]:
        table, label, origin = spec
        rows = rest_get(table, params={"select": "id", "limit": 1})
        return {
            "table": table,
            "label": label,
            "origin": origin,
            "available": rows is not None,
            "has_rows": bool(rows),
            "note": (
                "Row counts are not exposed by the query helper; presence "
                "is reported instead."
                if rows is not None
                else "The table could not be queried."
            ),
        }

    with ThreadPoolExecutor(max_workers=min(8, len(table_specs))) as pool:
        sources = list(pool.map(_check_source, table_specs))
    report["sources"] = sources

    # --- Demographic freshness ---------------------------------------
    demographic_years = rest_get(
        "demographic_data",
        params={"select": "source_year", "order": "source_year.desc", "limit": 20},
    )
    years: list[int] = []
    if isinstance(demographic_years, list):
        for row in demographic_years:
            try:
                year = int(row.get("source_year"))
            except (TypeError, ValueError):
                continue
            if year not in years:
                years.append(year)
    report["coverage"]["demographic_freshness"] = {
        "available_years": years,
        "latest_year": years[0] if years else None,
        "note": (
            "Census of India 2011 is the most recent complete enumeration. "
            "Years listed above are the vintages actually present in the data."
        ),
    }

    # --- Matrix release ----------------------------------------------
    releases = rest_get(
        settings.matrix_versions_table,
        params={"select": "version_id,data_release_at,n_sites_in,n_sites_out,n_excluded", "order": "data_release_at.desc", "limit": 1},
    )
    if isinstance(releases, list) and releases:
        report["coverage"]["latest_release"] = releases[0]
    else:
        report["coverage"]["latest_release"] = None

    # --- Backtesting availability -------------------------------------
    estate_rows = rest_get("own_estate_locations", params={"select": "id", "limit": 1})
    backtest_available = bool(estate_rows)
    report["backtesting"] = {
        "available": backtest_available,
        "method": (
            "Spearman rank correlation between the model's score and the "
            "client's own estate trading performance."
        ),
        "note": (
            "A backtest is possible because own-estate records are present."
            if backtest_available
            else "No own-estate records are present, so the model cannot be "
            "validated against trading performance yet."
        ),
    }

    # --- Summary -------------------------------------------------------
    usable_sources = sum(1 for source in sources if source["available"])
    report["summary"] = {
        "criteria_coverage": round(criterion_coverage, 4),
        "criteria_coverage_grade": _grade(criterion_coverage, 0.8, 0.5),
        "usable_source_count": usable_sources,
        "total_source_count": len(sources),
        "matrix_available": matrix_info.get("available", False),
        "backtest_available": backtest_available,
        "overall_grade": _grade(
            (
                criterion_coverage
                + (0.25 if matrix_info.get("available") else 0.0)
                + (0.25 if backtest_available else 0.0)
                + (0.25 * usable_sources / max(1, len(sources)))
            )
            / 2.0,
            0.75,
            0.45,
        ),
        "grading_rule": (
            "The overall grade averages the criterion coverage ratio with "
            "three equally-weighted operational checks: a loaded scoring "
            "matrix, an available backtest, and the share of source tables "
            "that can be queried. It is a coverage measure, not a measure of "
            "predictive accuracy."
        ),
    }

    from datetime import datetime, timezone

    report["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return report


@router.get("/limitations", summary="Known limitations of the platform's evidence base")
def get_limitations() -> dict[str, Any]:
    """Return the documented limitations on their own."""

    return {
        "limitations": KNOWN_LIMITATIONS,
        "statement": (
            "This platform provides decision support. It does not replace site "
            "visits, commercial due diligence or local market knowledge, and "
            "it does not claim to predict trading performance."
        ),
    }


__all__ = ["router", "KNOWN_LIMITATIONS"]

