"""Brokerage and agency intelligence.

The brokerage search follows the same source-adapter contract as the
property search: each source operates independently, a failing source is
reported rather than raised, and no agency, contact detail or listing is
ever invented.

Sources that cannot be queried automatically are represented as
*manual navigation* sources: the response carries a direct search link and
states that the result was not retrieved automatically.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from app.domain.brokerage_sources import (
    list_brokerage_sources,
    search_brokerages,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/brokerage", tags=["Brokerage intelligence"])


@router.get("/sources", summary="The configured brokerage sources")
def get_sources() -> dict[str, Any]:
    """Describe every brokerage source and whether it can be queried."""

    sources = list_brokerage_sources()
    return {
        "sources": sources,
        "automated_count": sum(
            1 for source in sources if source["kind"] == "automated"
        ),
        "manual_count": sum(1 for source in sources if source["kind"] == "manual"),
        "notes": [
            "Automated sources are queried live. A source that cannot be "
            "reached is reported with its status; it never fails the search.",
            "Manual sources are not scraped. A direct search link is provided "
            "instead.",
            "No agency, contact detail or listing is invented.",
        ],
    }


@router.get(
    "/search-sites",
    summary="Search for agencies around the recommended sites (query form)",
)
def search_sites(
    request: Request,
    site_ids: str = Query(
        ...,
        description="Comma-separated site identifiers to search around.",
    ),
    radius_m: int = Query(5000, ge=200, le=20000),
    limit_per_site: int = Query(10, ge=1, le=50),
) -> dict[str, Any]:
    """Search every brokerage source around each recommended site."""

    from app.routers.sites import get_sites_dataframe

    parsed_ids = [item.strip() for item in site_ids.split(",") if item.strip()]
    if not parsed_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="site_ids must contain at least one site identifier.",
        )

    try:
        sites_df = get_sites_dataframe(request)
    except HTTPException as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=f"Candidate site inventory is unavailable: {exc.detail}",
        ) from exc

    wanted = set(parsed_ids)
    resolved: dict[str, dict[str, Any]] = {}
    for _, row in sites_df.iterrows():
        site_id = str(row.get("site_id") or row.get("id") or row.name)
        if site_id not in wanted:
            continue
        try:
            latitude = float(row.get("latitude", row.get("lat")))
            longitude = float(row.get("longitude", row.get("lon")))
        except (TypeError, ValueError):
            continue
        resolved[site_id] = {
            "name": str(row.get("name") or f"Site {site_id}"),
            "latitude": latitude,
            "longitude": longitude,
        }

    def _search_one(site_id: str) -> dict[str, Any]:
        site = resolved.get(site_id)
        if site is None:
            return {
                "site_id": site_id,
                "site_name": None,
                "status": "unavailable",
                "message": (
                    "This site could not be located in the candidate "
                    "inventory, so no brokerage search was performed for it."
                ),
                "sources": [],
                "opportunities": [],
            }

        source_results = search_brokerages(
            latitude=site["latitude"],
            longitude=site["longitude"],
            radius_m=radius_m,
            limit=limit_per_site,
        )

        opportunities = [
            opportunity
            for result in source_results
            for opportunity in result.opportunities
        ]

        return {
            "site_id": site_id,
            "site_name": site["name"],
            "status": (
                "ok"
                if any(result.status == "live_source" for result in source_results)
                else "partial"
                if any(result.search_url for result in source_results)
                else "unavailable"
            ),
            "message": (
                f"{len(opportunities)} agency or operator found around this "
                "location."
                if opportunities
                else "No agency was found by the automated sources. The manual "
                "source links below can be searched directly."
            ),
            "sources": [result.to_dict() for result in source_results],
            "opportunities": [opportunity.to_dict() for opportunity in opportunities],
        }

    # The sites are searched concurrently so that the request takes as
    # long as the slowest source rather than the sum of them.
    with ThreadPoolExecutor(max_workers=max(1, min(6, len(parsed_ids)))) as pool:
        results = list(pool.map(_search_one, parsed_ids))

    total = sum(len(entry["opportunities"]) for entry in results)

    return {
        "sites": results,
        "opportunity_count": total,
        "disclaimer": (
            "Agencies are identified from published map data or from the "
            "configured sources. Their coverage of a specific premise is not "
            "verified by this platform and must be confirmed directly."
        ),
    }


__all__ = ["router"]

