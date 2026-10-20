#!/usr/bin/env python3
"""
Demographic ETL Ingestion Script for Tamil Nadu Pilot Sub-Region (Chennai District).

Source: Census of India 2011 - Primary Census Abstract (PCA) / District Census Handbook (DCHB)
Target: Supabase Postgres tables (`analysis_units` and `demographic_data`)

Execution flow:
1. Load configuration and initialize Supabase client from environment variables.
2. Acquire Census 2011 PCA dataset (from direct file path, URL, or local fallback).
3. Filter records for the Chennai pilot sub-region (District 603 / State 33 - Tamil Nadu).
4. Parse demographic indicators: total population, age bands (e.g., 0-6 years),
   household count, literacy rate, and workforce participation rate.
5. Map administrative unit records to canonical H3 grid cells in `analysis_units`.
6. Batch upsert processed records into `demographic_data` table.
"""

import argparse
import json
import logging
import os
import sys
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd
from supabase import Client, create_client

from ingestion.env import load_environment, server_key

load_environment()

# ============================================================================
# Logging Configuration
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("demographic_etl")

# ============================================================================
# Constants & Defaults
# ============================================================================
CENSUS_SOURCE_YEAR = 2011
CHENNAI_DISTRICT_CODE = "603"  # 2011 Census District Code for Chennai, TN
DEFAULT_BATCH_SIZE = 100

# Default Census PCA Column Mappings (standard Census 2011 PCA layout)
PCA_COL_MAP = {
    "STATE": ["State", "STATE", "ST_CODE"],
    "DISTRICT": ["District", "DISTRICT", "DIST_CODE"],
    "SUB_DISTRICT": ["Subdistt", "SUB_DISTRICT", "SUBDIST_CODE"],
    "TOWN_VILLAGE": ["Town/Village", "TOWN_VILLAGE", "VILLAGE_CODE"],
    "NAME": ["Name", "NAME", "MDDS_NAME"],
    "LEVEL": ["Level", "LEVEL"],
    "TRU": ["TRU", "TRU_TYPE"],  # Total / Rural / Urban
    "HOUSEHOLDS": ["No_HH", "HOUSEHOLDS", "NO_HH"],
    "TOT_POP": ["TOT_P", "TOT_POP", "TOTAL_POPULATION"],
    "POP_0_6": ["P_06", "POP_0_6", "P_0_6"],
    "LITERATE_POP": ["P_LIT", "LITERATE_POP", "P_LIT_TOT"],
    "WORKER_POP": ["TOT_WORK_P", "TOTAL_WORKERS", "TOT_WORK"],
}


def get_supabase_client() -> Client:
    """Read credentials from environment and initialize Supabase client."""
    url = os.getenv("SUPABASE_URL")
    key = server_key()

    if not url or not key:
        logger.critical(
            "Missing required environment variables: SUPABASE_URL and SUPABASE_KEY must be set."
        )
        sys.exit(1)

    try:
        return create_client(url, key)
    except Exception as err:
        logger.critical(f"Failed to initialize Supabase client: {err}")
        sys.exit(1)


def download_or_load_census_data(file_path: Optional[str], download_url: Optional[str]) -> pd.DataFrame:
    """Load Census Excel/CSV data from local path or URL."""
    target_path = file_path

    if not target_path and download_url:
        logger.info(f"Downloading Census dataset from: {download_url}")
        target_path = "/tmp/census_chennai_2011.xlsx"
        try:
            urllib.request.urlretrieve(download_url, target_path)
            logger.info(f"Downloaded source file to {target_path}")
        except Exception as err:
            logger.error(f"Failed to download dataset from URL: {err}")
            raise

    if not target_path:
        # Fallback to local default file path if present
        target_path = "data/DDW_PCA3302_2011_MDDS_with_UI.xlsx"
        if not os.path.exists(target_path):
            target_path = "data/census_chennai_2011.csv"

    if not os.path.exists(target_path):
        raise FileNotFoundError(
            f"Census data source file not found at '{target_path}'. "
            "Please provide a valid --file-path or --download-url."
        )

    logger.info(f"Reading Census data from: {target_path}")
    if target_path.endswith(".csv"):
        df = pd.read_csv(target_path, dtype=str)
    else:
        df = pd.read_excel(target_path, dtype=str)

    logger.info(f"Successfully loaded {len(df)} rows from raw source.")
    return df


def normalize_column_names(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, str]]:
    """Map dynamic DataFrame columns to standardized canonical Census names."""
    df.columns = [str(c).strip() for c in df.columns]
    canonical_map = {}

    for canonical_key, candidate_names in PCA_COL_MAP.items():
        found = None
        for candidate in candidate_names:
            matches = [c for c in df.columns if c.upper() == candidate.upper()]
            if matches:
                found = matches[0]
                break
        if found:
            canonical_map[canonical_key] = found
        else:
            logger.warning(f"Could not automatically map column for '{canonical_key}'. Candidates tested: {candidate_names}")

    return df, canonical_map


def filter_chennai_pilot_data(df: pd.DataFrame, col_map: Dict[str, str]) -> pd.DataFrame:
    """Filter records specifically for the Chennai pilot sub-region and remove macro-aggregate rows."""
    dist_col = col_map.get("DISTRICT")
    level_col = col_map.get("LEVEL")
    tru_col = col_map.get("TRU")

    filtered_df = df.copy()

    # Filter by District code if present
    if dist_col and dist_col in filtered_df.columns:
        filtered_df = filtered_df[
            filtered_df[dist_col].astype(str).str.strip().str.zfill(3) == CHENNAI_DISTRICT_CODE.zfill(3)
        ]
        logger.info(f"Filtered for Chennai District ({CHENNAI_DISTRICT_CODE}): {len(filtered_df)} records remaining.")

    # Exclude State/District summary rows (keep Ward/Village/Town granular records)
    if level_col and level_col in filtered_df.columns:
        filtered_df = filtered_df[
            ~filtered_df[level_col].astype(str).str.upper().isin(["STATE", "DISTRICT"])
        ]

    # Prefer 'Total' or 'Urban' rows for Chennai Corporation
    if tru_col and tru_col in filtered_df.columns:
        filtered_df = filtered_df[
            filtered_df[tru_col].astype(str).str.upper().isin(["TOTAL", "URBAN"])
        ]

    logger.info(f"Final scoped records for processing: {len(filtered_df)}")
    return filtered_df


def parse_demographic_record(row: pd.Series, col_map: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """Safe extraction and calculation of demographic attributes from a Census row."""
    def _safe_int(key: str) -> int:
        col = col_map.get(key)
        if not col or col not in row or pd.isna(row[col]):
            return 0
        try:
            return int(float(str(row[col]).replace(",", "").strip()))
        except (ValueError, TypeError):
            return 0

    tot_pop = _safe_int("TOT_POP")
    if tot_pop <= 0:
        return None  # Skip zero-population or invalid rows

    households = _safe_int("HOUSEHOLDS")
    pop_0_6 = _safe_int("POP_0_6")
    literates = _safe_int("LITERATE_POP")
    workers = _safe_int("WORKER_POP")

    # Calculated rates
    literacy_rate = round((literates / tot_pop) * 100.0, 4) if tot_pop > 0 else 0.0
    workforce_participation = round((workers / tot_pop) * 100.0, 4) if tot_pop > 0 else 0.0

    # Structuring age bands (Census PCA provides 0-6, remaining pop as 7+)
    age_bands = {
        "0_6": pop_0_6,
        "7_plus": max(0, tot_pop - pop_0_6),
    }

    raw_id = str(row.get(col_map.get("TOWN_VILLAGE", ""), "")).strip() or str(row.get(col_map.get("NAME", ""), "")).strip()

    return {
        "raw_geo_id": raw_id,
        "population": tot_pop,
        "household_count": households,
        "literacy_rate": literacy_rate,
        "workforce_participation": workforce_participation,
        "age_bands": age_bands,
    }


def map_record_to_analysis_unit(
    record: Dict[str, Any],
    existing_units: Dict[str, str]
) -> Tuple[Optional[str], float]:
    """
    Map a Census administrative unit to an analysis_units H3 cell ID.

    This is the direct 1:1 case.  When a Census unit covers more than one
    H3 cell, use :func:`allocate_record_to_analysis_units`, which performs
    the areal interpolation.
    """
    raw_id = record["raw_geo_id"]

    # Direct lookup attempt against fetched analysis units
    if raw_id in existing_units:
        # Direct match found
        unit_id = existing_units[raw_id]
        data_confidence = 1.0  # Direct 1:1 match starts at full confidence
        return unit_id, data_confidence

    # Fallback for pilot stage: If raw_id is already a valid H3 index
    if len(raw_id) == 15 and raw_id.isalnum():
        return raw_id, 1.0

    logger.debug(
        f"Unit '{raw_id}' does not directly match any analysis_unit ID. "
        "Areal interpolation is required for allocation."
    )
    return None, 0.0


def allocate_record_to_analysis_units(
    record: Dict[str, Any],
    existing_units: Dict[str, str],
    source_geometries: Optional[Dict[str, Any]] = None,
    target_geometries: Optional[Dict[str, Any]] = None,
) -> List[Tuple[str, float, float]]:
    """Allocate a Census record across the analysis units it overlaps.

    A Census ward or village frequently spans several H3 resolution-8
    cells.  When the source polygon and the target cell polygons are both
    available, the record's value is apportioned across the overlapping
    cells using the areal interpolation in
    :mod:`ingestion.areal_interpolation`, and the interpolation's own
    confidence score is carried through to the stored record.

    Returns a list of ``(unit_id, share, confidence)`` tuples, where
    ``share`` is the fraction of the record's value allocated to that
    cell.  The list is empty when the record cannot be allocated, in which
    case the caller must not write a row for it.
    """

    raw_id = record["raw_geo_id"]

    # A direct match needs no interpolation.
    direct = map_record_to_analysis_unit(record, existing_units)
    if direct[0] is not None:
        return [(direct[0], 1.0, direct[1])]

    if not source_geometries or not target_geometries:
        logger.debug(
            f"Unit '{raw_id}' was not allocated: no source or target geometry is "
            "available for the areal interpolation."
        )
        return []

    source_geometry = source_geometries.get(raw_id)
    if source_geometry is None or source_geometry.is_empty:
        logger.debug(
            f"Unit '{raw_id}' was not allocated: no source polygon is available for it."
        )
        return []

    try:
        from ingestion.areal_interpolation import interpolate_to_analysis_unit
    except ImportError:  # pragma: no cover - optional dependency
        logger.warning(
            "The areal interpolation module is unavailable; the record for "
            f"'{raw_id}' cannot be allocated."
        )
        return []

    value = record.get("population")
    try:
        value = float(value)
    except (TypeError, ValueError):
        return []

    allocations: List[Tuple[str, float, float]] = []
    allocated_total = 0.0

    for unit_id, target_geometry in target_geometries.items():
        if target_geometry is None or target_geometry.is_empty:
            continue
        if not source_geometry.intersects(target_geometry):
            continue

        result = interpolate_to_analysis_unit(
            [source_geometry], [value], target_geometry
        )
        allocated = result.value
        if allocated <= 0:
            continue

        allocations.append((unit_id, allocated, result.confidence))
        allocated_total += allocated

    if not allocations or allocated_total <= 0:
        logger.debug(
            f"Unit '{raw_id}' was not allocated: no overlapping analysis unit "
            "received a share of its value."
        )
        return []

    # Convert the allocated values into shares of the source record.
    shares = [
        (unit_id, allocated / allocated_total, confidence)
        for unit_id, allocated, confidence in allocations
    ]
    logger.info(
        f"Unit '{raw_id}' was allocated across {len(shares)} analysis unit(s) "
        f"by areal interpolation."
    )
    return shares


def fetch_existing_analysis_units(supabase: Client) -> Dict[str, str]:
    """Fetch existing analysis_units from Supabase to validate mapping target."""
    logger.info("Fetching existing analysis_units grid cells from Supabase...")
    try:
        response = supabase.table("analysis_units").select("id, name").execute()
        units_map = {}
        for row in response.data:
            units_map[row["id"]] = row["id"]
            if row.get("name"):
                units_map[row["name"]] = row["id"]
        logger.info(f"Retrieved {len(response.data)} active analysis_units for reconciliation.")
        return units_map
    except Exception as err:
        logger.error(f"Failed to fetch analysis_units from database: {err}")
        return {}


def fetch_analysis_unit_geometries(supabase: Client) -> Dict[str, Any]:
    """Fetch the H3 cell polygons used as the interpolation targets.

    A failure here is not fatal: without the target geometries the areal
    interpolation cannot run, and the ETL falls back to direct 1:1
    matching.  The reason is logged so the reduced coverage is visible.
    """
    logger.info("Fetching analysis_unit geometries for areal interpolation...")
    try:
        response = supabase.table("analysis_units").select("id,geometry").execute()
    except Exception as err:
        logger.warning(
            f"Could not fetch analysis_unit geometries ({err}); areal "
            "interpolation will not run for unmatched records."
        )
        return {}

    geometries: Dict[str, Any] = {}
    for row in response.data or []:
        geometry = _parse_geometry(row.get("geometry"))
        if geometry is not None:
            geometries[str(row.get("id"))] = geometry

    logger.info(f"Retrieved {len(geometries)} analysis unit geometries.")
    return geometries


def _parse_geometry(value: Any) -> Optional[Any]:
    """Parse a geometry from WKT, GeoJSON or a PostGIS text representation."""
    if value is None:
        return None
    if hasattr(value, "is_empty"):
        return value
    try:
        from shapely import wkt
        from shapely.geometry import shape
    except ImportError:  # pragma: no cover - optional dependency
        return None

    try:
        if isinstance(value, str):
            text = value.strip()
            if text.startswith("{"):
                return shape(json.loads(text))
            if text.upper().startswith("SRID="):
                text = text[text.index(";") + 1 :]
            if text.upper().startswith(("POINT", "POLYGON", "MULTIPOLYGON", "LINESTRING")):
                return wkt.loads(text)
            return None
        if isinstance(value, dict):
            return shape(value)
    except Exception:
        return None
    return None


def load_source_geometries(path: Optional[str]) -> Dict[str, Any]:
    """Load the Census unit polygons used as the interpolation sources.

    The polygons are supplied by the operator as a CSV with a
    ``raw_geo_id`` column and a ``geometry`` column (WKT or GeoJSON), or
    as a GeoJSON FeatureCollection with a ``raw_geo_id`` property.  They
    are an external data dependency: without them the ETL can only perform
    direct 1:1 matching.
    """
    if not path:
        logger.info(
            "No source boundary file was supplied; the areal interpolation "
            "will only run for records that match an analysis unit directly."
        )
        return {}

    source_path = Path(path)
    if not source_path.exists():
        logger.warning(f"Source boundary file not found: {source_path}")
        return {}

    geometries: Dict[str, Any] = {}
    try:
        if source_path.suffix.lower() in {".geojson", ".json"}:
            with source_path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            for feature in payload.get("features") or []:
                properties = feature.get("properties") or {}
                raw_id = properties.get("raw_geo_id") or properties.get("id")
                geometry = _parse_geometry(feature.get("geometry"))
                if raw_id and geometry is not None:
                    geometries[str(raw_id)] = geometry
        else:
            frame = pd.read_csv(source_path)
            id_column = "raw_geo_id" if "raw_geo_id" in frame.columns else None
            geometry_column = next(
                (column for column in ("geometry", "geom", "wkt") if column in frame.columns),
                None,
            )
            if id_column and geometry_column:
                for _, row in frame.iterrows():
                    geometry = _parse_geometry(row[geometry_column])
                    if geometry is not None:
                        geometries[str(row[id_column])] = geometry
    except Exception as err:
        logger.warning(f"Could not read the source boundary file: {err}")
        return {}

    logger.info(f"Loaded {len(geometries)} source boundary polygons.")
    return geometries


def upsert_demographic_batch(supabase: Client, records: List[Dict[str, Any]], dry_run: bool = False) -> int:
    """Batch upsert processed demographic records into Supabase `demographic_data` table."""
    if not records:
        return 0

    if dry_run:
        logger.info(f"[DRY RUN] Would upsert {len(records)} records into demographic_data.")
        return len(records)

    try:
        response = supabase.table("demographic_data").upsert(
            records,
            on_conflict="unit_id,source_year"
        ).execute()

        inserted_count = len(response.data) if response.data else len(records)
        logger.info(f"Successfully upserted {inserted_count} records into demographic_data.")
        return inserted_count
    except Exception as err:
        logger.error(f"Failed to write batch to Supabase: {err}")
        raise


def run_etl(
    file_path: Optional[str] = None,
    download_url: Optional[str] = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    dry_run: bool = False,
    boundaries_path: Optional[str] = None,
) -> None:
    """Main ETL orchestration pipeline."""
    logger.info("=== Starting Demographic ETL Ingestion Pipeline ===")
    supabase = get_supabase_client()

    # Step 1: Load Raw Dataset
    try:
        raw_df = download_or_load_census_data(file_path, download_url)
    except Exception as err:
        logger.critical(f"ETL pipeline halted during data acquisition: {err}")
        sys.exit(1)

    # Step 2: Normalize and Filter
    df_norm, col_map = normalize_column_names(raw_df)
    pilot_df = filter_chennai_pilot_data(df_norm, col_map)

    if pilot_df.empty:
        logger.error("No valid Census records found matching Chennai pilot scope. Exiting.")
        sys.exit(1)

    # Step 3: Fetch Target Analysis Units for Matching
    existing_units = fetch_existing_analysis_units(supabase)

    # Step 3b: Geometry for the areal interpolation.  Both sides are
    # optional; without them only direct 1:1 matches are possible.
    target_geometries = fetch_analysis_unit_geometries(supabase)
    source_geometries = load_source_geometries(boundaries_path)

    # Step 4: Parse & Transform Records
    upsert_buffer = []
    total_processed = 0
    total_matched = 0
    total_unmatched = 0
    total_allocated = 0

    for idx, row in pilot_df.iterrows():
        parsed = parse_demographic_record(row, col_map)
        if not parsed:
            continue

        total_processed += 1

        allocations = allocate_record_to_analysis_units(
            parsed, existing_units, source_geometries, target_geometries
        )

        if not allocations:
            total_unmatched += 1
            continue

        if len(allocations) > 1:
            total_allocated += 1

        for unit_id, share, confidence in allocations:
            total_matched += 1
            db_record = {
                "unit_id": unit_id,
                "population": parsed["population"] * share,
                "age_bands": json.dumps(
                    {
                        band: value * share
                        for band, value in parsed["age_bands"].items()
                    }
                ),
                "household_count": parsed["household_count"] * share,
                "literacy_rate": parsed["literacy_rate"],
                "workforce_participation": parsed["workforce_participation"],
                "data_confidence": confidence,
                "source_year": CENSUS_SOURCE_YEAR,
            }
            upsert_buffer.append(db_record)

        # Flush batch
        if len(upsert_buffer) >= batch_size:
            upsert_demographic_batch(supabase, upsert_buffer, dry_run=dry_run)
            upsert_buffer.clear()

    # Flush remaining buffer
    if upsert_buffer:
        upsert_demographic_batch(supabase, upsert_buffer, dry_run=dry_run)
        upsert_buffer.clear()

    # Step 5: Final Execution Summary & Diagnostics
    logger.info("=== Demographic ETL Pipeline Execution Summary ===")
    logger.info(f"Total Census records processed  : {total_processed}")
    logger.info(f"Analysis unit records written   : {total_matched}")
    logger.info(f"Records allocated by interpolation: {total_allocated}")
    logger.info(f"Records that could not be mapped : {total_unmatched}")

    if total_unmatched > 0:
        logger.warning(
            f"{total_unmatched} records could not be mapped to an analysis unit. "
            "Supply the Census boundary polygons with --boundaries so that the "
            "areal interpolation can allocate them."
        )

    if total_matched == 0 and not dry_run:
        logger.error("Zero records were written to Supabase. Marking execution as failed.")
        sys.exit(1)

    logger.info("ETL Ingestion completed successfully.")


# ============================================================================
# CLI Entrypoint
# ============================================================================
def main():
    parser = argparse.ArgumentParser(
        description="ETL Pipeline: Ingest Census Demographic Data for Tamil Nadu Pilot into Supabase."
    )
    parser.add_argument(
        "--file-path",
        type=str,
        default=None,
        help="Path to local Census 2011 Excel/CSV data file.",
    )
    parser.add_argument(
        "--download-url",
        type=str,
        default=None,
        help="Direct URL to download Census PCA/DCHB file.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="Number of records per database upsert batch (default: 100).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform parsing and matching validation without writing to Supabase.",
    )
    parser.add_argument(
        "--boundaries",
        type=str,
        default=None,
        help=(
            "Path to the Census boundary polygons (CSV with a raw_geo_id and a "
            "geometry column, or a GeoJSON FeatureCollection). They are "
            "required to allocate a Census unit that spans several analysis "
            "units."
        ),
    )

    args = parser.parse_args()

    run_etl(
        file_path=args.file_path,
        download_url=args.download_url,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
        boundaries_path=args.boundaries,
    )


if __name__ == "__main__":
    main()