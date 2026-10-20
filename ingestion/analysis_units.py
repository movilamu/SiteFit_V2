"""Generate the canonical analysis-unit grid.

The platform's spatial unit of analysis is an H3 resolution-8 cell
(ADR-001).  The grid must:

* cover the area of interest **completely**, with no gaps and no
  overlapping cells,
* be derived from the real H3 tessellation rather than from a regular
  latitude/longitude step, and
* carry the polygon geometry of each cell, so that the areal
  interpolation and the spatial joins can use it.

This module replaces the regular-step fallback that the accessibility
ingestion previously used, which undersampled the resolution-8 grid
(a 0.008 degree step is roughly twice the edge length of a cell) and so
left gaps in the analysis.

The grid is a *derived spatial index*, not a statement about the places
it covers: the population, economy and property attributes still have to
come from their own sources.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from ingestion.env import load_environment

load_environment()

logger = logging.getLogger("ingestion.analysis_units")

#: The canonical resolution of the analysis grid.
DEFAULT_RESOLUTION = 8

#: The default bounding box: min_lat, min_lon, max_lat, max_lon.
DEFAULT_BBOX: Tuple[float, float, float, float] = (12.80, 80.05, 13.25, 80.35)


def _get_supabase_client() -> Any:
    url = os.environ.get("SUPABASE_URL")
    key = (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_KEY")
        or os.environ.get("SUPABASE_ANON_KEY")
    )
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL and a server-side key are required to write the "
            "analysis units."
        )
    from supabase import create_client

    return create_client(url, key)


def _bbox_from_environment() -> Tuple[float, float, float, float]:
    raw = os.environ.get("CHENNAI_BBOX", "")
    if not raw.strip():
        return DEFAULT_BBOX
    parts = [part.strip() for part in raw.split(",") if part.strip()]
    if len(parts) != 4:
        raise ValueError(
            f"CHENNAI_BBOX must hold four comma-separated numbers, got {raw!r}."
        )
    # The environment variable is min_lon,min_lat,max_lon,max_lat; the
    # internal order is min_lat,min_lon,max_lat,max_lon.
    min_lon, min_lat, max_lon, max_lat = (float(part) for part in parts)
    return (min_lat, min_lon, max_lat, max_lon)


def cells_for_bbox(
    bbox: Tuple[float, float, float, float],
    resolution: int = DEFAULT_RESOLUTION,
) -> List[str]:
    """Return every H3 cell that covers the bounding box.

    The box is converted to a polygon and filled with cells, so the result
    is the real tessellation rather than a regular step.
    """

    import h3

    min_lat, min_lon, max_lat, max_lon = bbox
    ring = [
        (min_lat, min_lon),
        (min_lat, max_lon),
        (max_lat, max_lon),
        (max_lat, min_lon),
        (min_lat, min_lon),
    ]
    polygon = h3.LatLngPoly(ring)
    cells = h3.geo_to_cells(polygon, res=resolution)
    return sorted(cells)


def cells_for_points(
    points: Iterable[Tuple[float, float]],
    resolution: int = DEFAULT_RESOLUTION,
) -> List[str]:
    """Return the cell containing each point."""

    import h3

    cells = set()
    for lat, lon in points:
        cells.add(h3.latlng_to_cell(lat, lon, res=resolution))
    return sorted(cells)


def cell_to_record(
    cell: str,
    resolution: int = DEFAULT_RESOLUTION,
    name: Optional[str] = None,
) -> Dict[str, Any]:
    """Return the ``analysis_units`` row for one cell."""

    import h3

    boundary = h3.cell_to_boundary(cell)
    centre = h3.cell_to_latlng(cell)
    coordinates = [[round(lon, 7), round(lat, 7)] for lat, lon in boundary]

    # A closed ring, which is what PostGIS expects for a polygon.
    if coordinates[0] != coordinates[-1]:
        coordinates.append(list(coordinates[0]))

    return {
        "id": cell,
        "name": name or f"H3 r{resolution} {cell}",
        "resolution": resolution,
        "lat": round(centre[0], 7),
        "lon": round(centre[1], 7),
        "geometry": json.dumps({"type": "Polygon", "coordinates": [coordinates]}),
        "source": "H3",
    }


def build_records(
    cells: Sequence[str],
    resolution: int = DEFAULT_RESOLUTION,
) -> List[Dict[str, Any]]:
    return [cell_to_record(cell, resolution) for cell in cells]


def write_records(
    client: Any,
    records: Sequence[Dict[str, Any]],
    batch_size: int = 500,
    dry_run: bool = False,
) -> int:
    if not records:
        return 0

    if dry_run:
        logger.info("[DRY RUN] Would write %d analysis units.", len(records))
        return len(records)

    written = 0
    for start in range(0, len(records), batch_size):
        batch = list(records[start : start + batch_size])
        response = (
            client.table("analysis_units")
            .upsert(batch, on_conflict="id")
            .execute()
        )
        written += len(response.data or batch)
        logger.info("Wrote %d analysis units.", written)

    return written


def main(argv: Optional[Sequence[str]] = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
    )
    parser = argparse.ArgumentParser(
        description="Generate the H3 analysis-unit grid."
    )
    parser.add_argument("--res", type=int, default=DEFAULT_RESOLUTION)
    parser.add_argument(
        "--bbox",
        default=None,
        help="min_lat,min_lon,max_lat,max_lon. Defaults to CHENNAI_BBOX.",
    )
    parser.add_argument(
        "--around-sites",
        action="store_true",
        help="Build the grid around the candidate sites instead of the pilot box.",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.bbox:
        parts = [float(part) for part in args.bbox.split(",")]
        if len(parts) != 4:
            parser.error("--bbox needs four comma-separated numbers.")
        bbox = (parts[0], parts[1], parts[2], parts[3])
    else:
        bbox = _bbox_from_environment()

    if args.around_sites:
        client = _get_supabase_client()
        response = (
            client.table("candidate_sites")
            .select("id,site_id,name,latitude,longitude,status")
            .eq("status", "active")
            .execute()
        )
        points = []
        for row in response.data or []:
            lat = row.get("latitude")
            lon = row.get("longitude")
            if lat is None or lon is None:
                continue
            points.append((float(lat), float(lon)))
        if not points:
            logger.error("No active candidate sites were found.")
            return 1
        cells = cells_for_points(points, args.res)
        logger.info(
            "Built %d cells around %d candidate site(s).", len(cells), len(points)
        )
    else:
        cells = cells_for_bbox(bbox, args.res)
        logger.info(
            "Built %d cells for the box %s at resolution %d.",
            len(cells),
            bbox,
            args.res,
        )

    records = build_records(cells, args.res)
    client = _get_supabase_client()
    written = write_records(client, records, dry_run=args.dry_run)
    logger.info("Done. %d analysis unit(s) written.", written)
    return 0


if __name__ == "__main__":
    sys.exit(main())
