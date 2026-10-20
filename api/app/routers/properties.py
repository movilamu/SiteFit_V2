"""External property and brokerage intelligence.

Given the top-ranked recommended sites, this router searches the
configured public sources for relevant property and brokerage
opportunities near each of them.

The contract is deliberately explicit: every response states which
sources were queried, what each source's status was, and where no source
is available the response says so rather than returning an empty list that
could be mistaken for "nothing available".
"""

from __future__ import annotations

from typing import Any, Optional

from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from api.app.domain.property_sources import (
    STATUS_UNAVAILABLE,
    STATUS_NOT_CONFIGURED,
    STATUS_OK,
    PropertySearchQuery,
    deduplicate,
    list_sources,
    search_properties,
)

router = APIRouter(prefix="/properties", tags=["Property intelligence"])


@router.get("/sources", summary="List the external property sources")
def get_sources() -> dict[str, Any]:
    """Describe every known external source and whether it is usable."""

    sources = list_sources()
    return {
        "sources": sources,
        "enabled_count": sum(1 for source in sources if source["enabled"]),
        "notes": [
            "Opportunities are only ever returned from a live retrieval against "
            "a public or operator-configured source.",
            "Map data is labelled as map data; it is not a broker listing.",
            "Prices and availability are never inferred. Where a figure is not "
            "published it is reported as unavailable.",
        ],
    }


def _resolve_sites(request: Request, site_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Look up the requested sites in the candidate-site inventory."""

    from api.app.routers.sites import get_sites_dataframe

    try:
        sites_df = get_sites_dataframe(request)
    except HTTPException as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=f"Candidate site inventory is unavailable: {exc.detail}",
        ) from exc

    wanted = {str(site_id) for site_id in site_ids}
    resolved: dict[str, dict[str, Any]] = {}

    for _, row in sites_df.iterrows():
        site_id = str(row.get("site_id") or row.get("id") or row.name)
        if site_id not in wanted:
            continue
        latitude = row.get("latitude", row.get("lat"))
        longitude = row.get("longitude", row.get("lon"))
        try:
            lat = float(latitude)
            lon = float(longitude)
        except (TypeError, ValueError):
            continue
        resolved[site_id] = {
            "site_id": site_id,
            "name": str(row.get("name") or f"Site {site_id}"),
            "latitude": lat,
            "longitude": lon,
        }

    return resolved


def _run_search(
    site_ids: list[str],
    radius_m: int,
    business_type: Optional[str],
    acquisition_mode: str,
    source_keys: Optional[list[str]],
    limit_per_site: int,
    request: Request,
) -> dict[str, Any]:
    resolved = _resolve_sites(request, site_ids)

    missing = [site_id for site_id in site_ids if site_id not in resolved]
    results: list[dict[str, Any]] = []
    all_opportunities: list[Any] = []

    def _search_one(site_id: str) -> dict[str, Any]:
        site = resolved.get(site_id)
        if site is None:
            return {
                "site_id": site_id,
                "site_name": None,
                "status": STATUS_UNAVAILABLE,
                "message": (
                    "This site could not be located in the candidate inventory, "
                    "so no external search was performed for it."
                ),
                "sources": [],
                "opportunities": [],
            }

        query = PropertySearchQuery(
            latitude=site["latitude"],
            longitude=site["longitude"],
            radius_m=radius_m,
            business_type=business_type,
            acquisition_mode=acquisition_mode,
            limit=limit_per_site,
        )
        source_results = search_properties(query, source_keys)

        opportunities = deduplicate(
            [item for result in source_results for item in result.opportunities]
        )[:limit_per_site]

        statuses = [result.status for result in source_results]
        if not source_results:
            overall = STATUS_NOT_CONFIGURED
            message = "No external property sources are available."
        elif all(status == STATUS_OK for status in statuses):
            overall = "ok"
            message = f"{len(opportunities)} opportunit(y/ies) found across {len(source_results)} source(s)."
        elif any(status == "ok" for status in statuses):
            overall = "partial"
            message = (
                f"{len(opportunities)} opportunit(y/ies) found. "
                "Some sources did not respond successfully; see the per-source status."
            )
        else:
            overall = "unavailable"
            message = "No external source returned a usable result for this site."

        return {
            "site_id": site_id,
            "site_name": site["name"],
            "latitude": site["latitude"],
            "longitude": site["longitude"],
            "status": overall,
            "message": message,
            "sources": [result.to_dict() for result in source_results],
            "opportunities": [item.to_dict() for item in opportunities],
        }

    # The sites are searched concurrently: each source can take as long
    # as the outbound timeout, so doing them one after another made the
    # request exceed the browser's patience.
    with ThreadPoolExecutor(max_workers=max(1, min(6, len(site_ids)))) as pool:
        results = list(pool.map(_search_one, site_ids))

    for entry in results:
        all_opportunities.extend(entry["opportunities"])

    any_source_working = any(
        source.get("status") == STATUS_OK
        for entry in results
        for source in entry.get("sources") or []
    )

    return {
        "sites": results,
        "opportunity_count": len(all_opportunities),
        "source_status_summary": _summarise(results),
        "any_source_available": any_source_working,
        "disclaimer": (
            "External opportunities are third-party listings retrieved at the "
            "time shown. Availability, price and terms are not verified by this "
            "platform and must be confirmed with the owner or agent before "
            "capital commitment."
        ),
    }


def _summarise(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate the per-source statuses across all searched sites."""

    summary: dict[str, dict[str, Any]] = {}
    for entry in results:
        for source in entry.get("sources") or []:
            record = summary.setdefault(
                source["key"],
                {
                    "key": source["key"],
                    "label": source["label"],
                    "publisher": source["publisher"],
                    "status": source["status"],
                    "message": source.get("message") or "",
                    "checked_sites": 0,
                },
            )
            record["checked_sites"] += 1
    return list(summary.values())


class SiteSearchRequest(BaseModel):
    """Search for property opportunities around a set of recommended sites."""

    site_ids: list[str] = Field(
        ...,
        min_length=1,
        description="The recommended site identifiers to search around.",
    )
    radius_m: int = Field(
        default=1500,
        ge=100,
        le=5000,
        description="Search radius around each site, in metres.",
    )
    business_type: Optional[str] = Field(
        default=None,
        description="The business type, used to label the search.",
    )
    acquisition_mode: str = Field(
        default="either",
        description="Whether the search targets a purchase, a lease or either.",
    )
    sources: Optional[list[str]] = Field(
        default=None,
        description="Restrict the search to these source keys.",
    )
    limit_per_site: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum opportunities returned per site.",
    )


@router.post("/search", summary="Search external sources around recommended sites")
def search(request: Request, payload: SiteSearchRequest) -> dict[str, Any]:
    """Search for property and brokerage opportunities around each site.

    A site's coordinates come from the candidate-site inventory.  Each
    source is queried independently, so a single failing source degrades
    to a reported status rather than an error for the whole request.
    """

    return _run_search(
        site_ids=payload.site_ids,
        radius_m=payload.radius_m,
        business_type=payload.business_type,
        acquisition_mode=payload.acquisition_mode,
        source_keys=payload.sources,
        limit_per_site=payload.limit_per_site,
        request=request,
    )


@router.get(
    "/search-sites",
    summary="Search external sources around the recommended sites (query form)",
)
def search_sites(
    request: Request,
    site_ids: str = Query(
        ...,
        description="Comma-separated site identifiers to search around.",
    ),
    radius_m: int = Query(1500, ge=100, le=5000),
    business_type: Optional[str] = Query(default=None),
    acquisition_mode: str = Query(default="either"),
    sources: Optional[str] = Query(
        default=None,
        description="Comma-separated source keys. Defaults to every enabled source.",
    ),
    limit_per_site: int = Query(10, ge=1, le=50),
) -> dict[str, Any]:
    """Convenience GET form of the property search."""

    parsed_ids = [item.strip() for item in site_ids.split(",") if item.strip()]
    if not parsed_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="site_ids must contain at least one site identifier.",
        )

    parsed_sources = (
        [item.strip() for item in sources.split(",") if item.strip()]
        if sources
        else None
    )

    return _run_search(
        site_ids=parsed_ids,
        radius_m=radius_m,
        business_type=business_type,
        acquisition_mode=acquisition_mode,
        source_keys=parsed_sources,
        limit_per_site=limit_per_site,
        request=request,
    )
