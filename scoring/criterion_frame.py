"""Assemble the raw criterion frame used by the precompute job.

The scoring engine's precompute step needs one row per candidate site with
one column per criterion leaf, holding the **raw** value.  This module
assembles that frame from the ingested tables.

Only criteria whose backing data has been materialised are produced.  A
criterion that is missing is simply absent from the frame, and the
precompute step then reports it as a dropped criterion with its weight
redistributed across the criteria that could be scored.

The mapping below is the single place where a criterion key is tied to the
table and column it is computed from.
"""

from __future__ import annotations

import json
import logging
import math
import os
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

EARTH_RADIUS_M = 6371000.0


def _rest_get(table: str, params: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    """Read a table through the Supabase REST API, returning ``None`` on failure."""

    url = os.getenv("SUPABASE_URL")
    key = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_KEY")
        or os.getenv("SUPABASE_ANON_KEY")
    )
    if not url or not key:
        logger.warning("Supabase is not configured; cannot read %s.", table)
        return None

    try:
        import requests
    except ImportError:  # pragma: no cover
        return None

    endpoint = f"{url.rstrip('/')}/rest/v1/{table}"
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    }
    try:
        response = requests.get(endpoint, headers=headers, params=params, timeout=120)
    except Exception as exc:
        logger.warning("Could not read %s: %s", table, exc)
        return None

    if response.status_code != 200:
        # The body is included because a bad column name is the most
        # common cause and it is otherwise invisible.
        logger.warning(
            "Reading %s returned HTTP %s: %s",
            table,
            response.status_code,
            response.text[:400],
        )
        return None
    try:
        payload = response.json()
    except ValueError:
        return None
    return payload if isinstance(payload, list) else None


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres."""

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def _point(row: Dict[str, Any]) -> Optional[tuple[float, float]]:
    lat = row.get("lat", row.get("latitude"))
    lon = row.get("lon", row.get("longitude"))
    try:
        return float(lat), float(lon)
    except (TypeError, ValueError):
        pass

    geometry = row.get("geometry")
    if isinstance(geometry, str) and "POINT" in geometry.upper():
        inner = geometry[geometry.upper().find("POINT") :]
        inner = inner[inner.find("(") + 1 : inner.rfind(")")]
        parts = inner.replace(",", " ").split()
        if len(parts) >= 2:
            try:
                return float(parts[1]), float(parts[0])
            except ValueError:
                return None
    if isinstance(geometry, dict):
        coordinates = geometry.get("coordinates")
        if geometry.get("type") == "Point" and coordinates and len(coordinates) >= 2:
            try:
                return float(coordinates[1]), float(coordinates[0])
            except (TypeError, ValueError):
                return None
    return None


def load_candidate_sites() -> List[Dict[str, Any]]:
    """Load the active candidate sites."""

    rows = _rest_get(
        "candidate_sites",
        {
            "select": (
                "id,site_id,name,latitude,longitude,attractiveness,"
                "floor_area_sqm,unit_size,rent,tenure_type,status,metadata"
            ),
            "status": "eq.active",
            "order": "id.asc",
        },
    )
    return rows or []


def load_demographics() -> Dict[str, Dict[str, Any]]:
    """Load the most recent demographic record per analysis unit."""

    rows = _rest_get(
        "demographic_data",
        {
            "select": "unit_id,population,age_bands,household_count,source_year",
            "order": "source_year.desc",
        },
    )
    latest: Dict[str, Dict[str, Any]] = {}
    for row in rows or []:
        unit_id = str(row.get("unit_id"))
        if unit_id not in latest:
            latest[unit_id] = row
    return latest


def load_analysis_units() -> Dict[str, Dict[str, Any]]:
    """Load the analysis units, keyed by unit id."""

    rows = _rest_get("analysis_units", {"select": "id,lat,lon,name"})
    return {str(row.get("id")): row for row in rows or []}


def load_catchments() -> Dict[str, Dict[str, Any]]:
    """Load the computed catchments, keyed by candidate site id."""

    rows = _rest_get(
        "candidate_catchments",
        {
            "select": (
                "candidate_site_id,competitor_count_10min,own_estate_count_10min,"
                "competitor_count_15min,gravity_catchment,cannibalization_score,"
                "isochrone_10min,competitor_overlap"
            ),
        },
    )
    return {str(row.get("candidate_site_id")): row for row in rows or []}


def load_competitors() -> List[Dict[str, Any]]:
    """Load the competitive set."""

    rows = _rest_get("competitor_locations", {"select": "id,name,category,geometry"})
    return rows or []


def _population_for_site(
    site: Dict[str, Any],
    units: Dict[str, Dict[str, Any]],
    demographics: Dict[str, Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Find the demographics of the analysis unit that contains a site.

    The nearest analysis unit is used.  With the canonical resolution-8
    grid a cell is roughly 460 m across, so the nearest unit is a sound
    approximation of containment.
    """

    point = _point(site)
    if point is None:
        return None

    best_unit: Optional[Dict[str, Any]] = None
    best_distance = float("inf")
    for unit in units.values():
        unit_point = _point(unit)
        if unit_point is None:
            continue
        distance = haversine_m(point[0], point[1], unit_point[0], unit_point[1])
        if distance < best_distance:
            best_distance = distance
            best_unit = unit

    if best_unit is None:
        return None
    return demographics.get(str(best_unit.get("id")))


def _age_band_representation(age_bands: Any) -> Optional[float]:
    """Score how closely a unit's age mix matches a family-oriented profile.

    The target profile is deliberately simple and documented: a family
    retail catchment benefits from a balanced mix of children and adults.
    """

    if isinstance(age_bands, str):
        try:
            age_bands = json.loads(age_bands)
        except json.JSONDecodeError:
            return None
    if not isinstance(age_bands, dict):
        return None

    total = 0.0
    children = 0.0
    for key, value in age_bands.items():
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        total += number
        if key.startswith("0_") or key in {"0-6", "child", "children"}:
            children += number
    if total <= 0:
        return None
    return children / total



def _as_float(value: Any) -> Optional[float]:
    """Return a finite float, or ``None``."""

    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _metadata_of(row: Dict[str, Any]) -> Dict[str, Any]:
    """Return the row's metadata as a dictionary."""

    metadata = row.get("metadata")
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except json.JSONDecodeError:
            return {}
    return metadata if isinstance(metadata, dict) else {}


def _site_category(site: Dict[str, Any]) -> Optional[str]:
    """Return the site's retail category, when one is recorded.

    The category is a property of the candidate site itself, so it is
    read from the site's own column or from its metadata.  It is never
    inferred: an unrecorded category leaves the category-relative
    criteria unavailable rather than measured against the wrong set.
    """

    for candidate in (
        site.get("category"),
        _metadata_of(site).get("retail_category"),
        _metadata_of(site).get("category"),
    ):
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip().lower()
    return None



def _isochrone_area_km2(geometry: Any) -> Optional[float]:
    """Return the area in square kilometres covered by an isochrone.

    The polygon is projected onto a local equirectangular plane anchored
    at its own mean latitude and the planar area is taken with the
    shoelace formula.  For an urban isochrone the projection error is
    well below a tenth of a percent, and it needs no projection library.
    """

    if isinstance(geometry, str):
        try:
            geometry = json.loads(geometry)
        except json.JSONDecodeError:
            return None
    if not isinstance(geometry, dict):
        return None

    kind = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if kind == "Polygon" and isinstance(coordinates, list) and coordinates:
        rings = [coordinates[0]]
    elif kind == "MultiPolygon" and isinstance(coordinates, list) and coordinates:
        largest = max(
            coordinates,
            key=lambda polygon: abs(_ring_area_m2(polygon[0])) if polygon else 0.0,
        )
        rings = [largest[0]]
    else:
        return None

    total = 0.0
    for ring in rings:
        area = _ring_area_m2(ring)
        if area:
            total += abs(area)
    if not total:
        return None

    return total / 1_000_000.0


#: The mean earth radius in metres.
EARTH_RADIUS_M = 6371008.8


def _ring_area_m2(ring: List[Any]) -> float:
    """The area in square metres of a ring given as ``[[lon, lat], ...]``.

    The ring is projected onto a local equirectangular plane anchored at
    its own mean latitude: the longitude axis is scaled by the cosine of
    that latitude and the latitude axis is unscaled.  The planar area
    then follows from the shoelace formula.
    """

    if not ring or len(ring) < 3:
        return 0.0

    try:
        points = [(float(point[0]), float(point[1])) for point in ring]
    except (IndexError, TypeError, ValueError):
        return 0.0

    mean_latitude = sum(point[1] for point in points) / len(points)
    scale = math.cos(math.radians(mean_latitude))

    projected = [
        (
            math.radians(point[0]) * scale * EARTH_RADIUS_M,
            math.radians(point[1]) * EARTH_RADIUS_M,
        )
        for point in points
    ]

    total = 0.0
    count = len(projected)
    for index in range(count):
        x1, y1 = projected[index]
        x2, y2 = projected[(index + 1) % count]
        total += x1 * y2 - x2 * y1

    return total / 2.0


def _catchment_competitor_locations(
    catchment: Dict[str, Any], minutes: int
) -> Optional[List[Dict[str, Any]]]:
    """Return the competitors the catchment overlap recorded."""

    overlap = catchment.get("competitor_overlap")
    if isinstance(overlap, str):
        try:
            overlap = json.loads(overlap)
        except json.JSONDecodeError:
            return None
    if not isinstance(overlap, dict):
        return None

    bucket = overlap.get(f"{minutes}min")
    if not isinstance(bucket, dict):
        return None
    competitors = bucket.get("competitors")
    if not isinstance(competitors, dict):
        return None
    locations = competitors.get("locations")
    if not isinstance(locations, list):
        return None
    return locations


def _catchment_competitor_count(
    catchment: Dict[str, Any], minutes: int, category: Optional[str]
) -> Optional[int]:
    """Count the competitors in the catchment, optionally by category."""

    locations = _catchment_competitor_locations(catchment, minutes)
    if locations is None:
        return None
    if not category:
        return len(locations)
    return sum(
        1
        for location in locations
        if str((location or {}).get("category") or "").strip().lower() == category
    )


def build_raw_criterion_frame() -> pd.DataFrame:
    """Assemble the raw criterion frame for the precompute step.

    The returned frame is indexed by ``site_id`` and holds one column per
    criterion leaf that could be computed from the ingested data.
    """

    sites = load_candidate_sites()
    if not sites:
        logger.warning("No active candidate sites were found.")
        return pd.DataFrame()

    units = load_analysis_units()
    demographics = load_demographics()
    catchments = load_catchments()
    competitors = load_competitors()

    competitor_points = [
        (competitor.get("category"), _point(competitor)) for competitor in competitors
    ]
    competitor_points = [(category, point) for category, point in competitor_points if point]

    records: List[Dict[str, Any]] = []
    sites_without_category: List[str] = []

    for site in sites:
        # The numeric key joins to the catchment; the business key is what
        # the API reports as the site identifier.
        numeric_id = str(site.get("id"))
        site_id = str(site.get("site_id") or site.get("id"))
        point = _point(site)
        if point is None:
            logger.warning("Skipping candidate site %s: no coordinates.", site_id)
            continue

        record: Dict[str, Any] = {"site_id": site_id}
        demographic = _population_for_site(site, units, demographics)

        if demographic is not None:
            population = demographic.get("population")
            households = demographic.get("household_count")
            try:
                population_value = float(population)
            except (TypeError, ValueError):
                population_value = None
            if population_value is not None:
                record["resident_density"] = population_value
                try:
                    household_value = float(households)
                except (TypeError, ValueError):
                    household_value = None
                if household_value and household_value > 0:
                    record["household_size_composition"] = population_value / household_value

            representation = _age_band_representation(demographic.get("age_bands"))
            if representation is not None:
                record["age_band_representation"] = representation

        catchment = catchments.get(numeric_id) or {}

        # The site's own recorded attributes.  ``unit_size`` is the
        # criterion's raw value; ``rent`` is the rent per square foot,
        # which is what the criterion is defined over.
        unit_size = _as_float(site.get("unit_size"))
        if unit_size is None:
            floor_area_sqm = _as_float(site.get("floor_area_sqm"))
            if floor_area_sqm is not None:
                unit_size = floor_area_sqm * 10.7639104167097
        if unit_size is not None and unit_size > 0:
            record["unit_size"] = unit_size

        monthly_rent = _as_float(site.get("rent"))
        if monthly_rent is not None and unit_size:
            record["rent"] = monthly_rent / unit_size

        # The area covered by the site's driving isochrone.  Population is
        # not available for the pilot area, so the area is used instead.
        reach_area = _isochrone_area_km2(catchment.get("isochrone_10min"))
        if reach_area is not None:
            record["drive_time_reach"] = reach_area

        # The site's retail format.  The category-relative criteria are
        # only meaningful against a recorded format.
        site_category = _site_category(site)

        # Competitor density inside the catchment.  When the site's format
        # is known the count is restricted to that format, as the criterion
        # requires; otherwise it reports the whole retail competitive set.
        competitor_count = _catchment_competitor_count(
            catchment, 10, site_category
        )
        if competitor_count is None:
            raw_count = catchment.get("competitor_count_10min")
            if raw_count is not None:
                competitor_count = int(raw_count)
        if competitor_count is not None:
            record["competitor_density_in_catchment"] = float(competitor_count)

        # Competitors within 2 km, by category.
        near_same_format = 0
        near_total = 0
        nearest_same_format: Optional[float] = None
        for category, competitor_point in competitor_points:
            distance = haversine_m(
                point[0], point[1], competitor_point[0], competitor_point[1]
            )
            if distance > 2000:
                continue
            near_total += 1
            if site_category and category == site_category:
                near_same_format += 1
                if nearest_same_format is None or distance < nearest_same_format:
                    nearest_same_format = distance

        if site_category:
            if near_total > 0:
                record["format_overlap"] = near_same_format / near_total
            if nearest_same_format is not None:
                record["distance_to_nearest_direct_competitor"] = nearest_same_format
        else:
            sites_without_category.append(site_id)

        cannibalisation = catchment.get("cannibalization_score")
        if cannibalisation is not None:
            try:
                record["own_estate_catchment_overlap"] = float(cannibalisation)
            except (TypeError, ValueError):
                pass

        records.append(record)

    if sites_without_category:
        logger.warning(
            "%d candidate site(s) have no recorded retail category: %s. "
            "The format-relative criteria (format_overlap, "
            "distance_to_nearest_direct_competitor) are therefore unavailable "
            "for them, and their catchment competitor count covers the whole "
            "retail competitive set. Set candidate_sites.category to restore "
            "the category-relative measures.",
            len(sites_without_category),
            ", ".join(sorted(sites_without_category)),
        )

    frame = pd.DataFrame(records)
    if frame.empty:
        return frame
    return frame.set_index("site_id")


__all__ = [
    "build_raw_criterion_frame",
    "haversine_m",
    "load_analysis_units",
    "load_catchments",
    "load_candidate_sites",
    "load_competitors",
    "load_demographics",
]
