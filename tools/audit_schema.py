"""Audit the live Supabase schema against the migrations.

Reports which tables exist, which are missing, and which columns differ
from what the application code expects.  No secret value is ever printed.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.app.core.config import get_settings  # noqa: E402

import requests  # noqa: E402

# The columns the application reads or writes, per table.
EXPECTED: dict[str, list[str]] = {
    "site_selection_projects": [
        "id", "user_id", "name", "status", "business_type", "acquisition_mode",
        "location", "weights", "aggregation_method", "criteria_coverage", "notes",
        "created_at", "updated_at", "confirmed_at", "brief_version",
    ],
    "project_business_requirements": [
        "id", "project_id", "requirement_key", "label", "importance", "value",
        "value_text", "value_type", "unit", "minimum", "maximum", "options",
        "help_text", "created_at",
    ],
    "project_facility_requirements": [
        "id", "project_id", "facility_key", "label", "importance", "created_at",
    ],
    "project_parking_requirements": [
        "id", "project_id", "min_car_spaces", "min_two_wheeler_spaces",
        "min_parking_area_sqft", "behaviour", "scope", "created_at", "updated_at",
    ],
    "project_financial_requirements": [
        "id", "project_id", "budgets", "budget_behaviour", "horizon_months",
        "created_at", "updated_at",
    ],
    "saved_scenarios": [
        "scenario_id", "user_id", "name", "weight_set", "aggregation_method",
        "created_at", "updated_at",
    ],
    "export_records": [
        "id", "user_id", "scenario_id", "weight_set", "aggregation_method",
        "payload", "created_at",
    ],
    "user_profiles": [
        "id", "display_name", "organisation", "role", "avatar_url", "preferences",
        "created_at", "updated_at",
    ],
    "project_rankings": [
        "id", "project_id", "user_id", "label", "weight_set", "level_weights",
        "aggregation_method", "criteria_coverage", "ranking", "matrix_version",
        "created_at",
    ],
    "project_comparisons": [
        "id", "project_id", "user_id", "name", "site_ids", "weight_set",
        "aggregation_method", "notes", "created_at",
    ],
    "brokerage_opportunities": [
        "id", "project_id", "user_id", "site_id", "source_key", "source_label",
        "publisher", "name", "service_area", "website", "phone", "email",
        "source_url", "listing_count", "distance_m", "source_date", "source_status",
        "kind", "notes", "raw", "retrieved_at", "created_at",
    ],
    "data_quality_snapshots": [
        "id", "project_id", "user_id", "matrix_version", "coverage",
        "criteria_availability", "source_availability", "backtest_available",
        "limitations", "captured_at", "created_at",
    ],
    "project_reports": [
        "id", "project_id", "user_id", "title", "format", "payload",
        "generated_at", "created_at",
    ],
    "business_types": ["key", "label", "description", "is_custom", "sort_order", "created_at"],
    "candidate_sites": [
        "id", "site_id", "name", "latitude", "longitude", "unit_size", "rent",
        "tenure_type", "attractiveness", "floor_area_sqm", "status", "metadata",
        "created_at", "updated_at",
    ],
    "candidate_catchments": [
        "id", "candidate_site_id", "profile", "range_minutes_short",
        "range_minutes_long", "lat", "lon", "isochrone_10min", "isochrone_15min",
        "gravity_catchment", "competitor_overlap", "cannibalization",
        "cannibalization_score", "competitor_count_10min", "own_estate_count_10min",
        "competitor_count_15min", "own_estate_count_15min", "computed_at",
        "updated_at",
    ],
    "analysis_units": [
        "id", "name", "resolution", "lat", "lon", "geometry", "source",
        "created_at", "updated_at",
    ],
    "demographic_data": [
        "id", "unit_id", "population", "age_bands", "household_count",
        "literacy_rate", "workforce_participation", "data_confidence", "source_year",
        "source", "created_at", "updated_at",
    ],
    "economic_data": [
        "id", "unit_id", "spending_by_category", "disposable_income_estimate",
        "expenditure_index", "mpce", "data_confidence", "source_year", "source",
        "created_at", "updated_at",
    ],
    "accessibility_data": [
        "id", "unit_id", "transit_score", "parking_availability",
        "footfall_estimate", "data_confidence", "source", "created_at", "updated_at",
    ],
    "competitor_locations": [
        "id", "name", "category", "geometry", "attractiveness", "source",
        "last_updated", "created_at", "updated_at",
    ],
    "own_estate_locations": [
        "id", "name", "geometry", "attractiveness", "current_trading_performance",
        "created_at", "updated_at",
    ],
    "property_listings": [
        "id", "name", "geometry", "unit_size", "floor_area", "rent",
        "lease_term_years", "tenure_type", "purchase_price", "source",
        "source_record_id", "last_updated", "created_at", "updated_at",
    ],
    "isochrone_cache": [
        "id", "lat", "lon", "profile", "range_value", "geometry", "created_at",
    ],
    "ors_daily_usage": ["usage_date", "request_count", "updated_at"],
    "spatial_boundaries": [
        "id", "osm_id", "name", "admin_level", "boundary_type", "geometry",
        "area_sqkm", "properties", "source", "created_at", "updated_at",
    ],
    "land_use_polygons": [
        "id", "osm_id", "landuse_type", "name", "geometry", "area_sqm",
        "properties", "source", "created_at", "updated_at",
    ],
    "road_network": [
        "id", "osm_id", "name", "highway_type", "oneway", "maxspeed",
        "length_meters", "estimated_travel_time_sec", "geometry", "properties",
        "source", "created_at", "updated_at",
    ],
    "normalized_matrix_versions": [
        "version_id", "data_release_at", "storage_path", "n_sites_in", "n_sites_out",
        "n_excluded", "scored_criterion_keys", "leaf_keys", "parent_to_children",
        "excluded_sites", "metadata", "created_at",
    ],
    "property_opportunities": [
        "id", "project_id", "site_id", "source_id", "source_key", "source_label",
        "title", "source_url", "location", "property_type", "area_sqft",
        "purchase_price", "monthly_rent", "security_deposit", "parking_spaces",
        "facilities", "broker_name", "broker_contact", "listed_at", "retrieved_at",
        "price_provenance", "verification_status", "raw", "created_at",
    ],
    "external_sources": [
        "id", "key", "label", "publisher", "homepage_url", "status",
        "last_checked_at", "last_error", "created_at", "updated_at",
    ],
    "project_cost_assessments": [
        "id", "project_id", "site_id", "acquisition_mode", "acquisition_total",
        "setup_total", "recurring_monthly_total", "recurring_annual_total",
        "initial_investment_total", "known_minimum_initial_investment",
        "is_complete", "notes", "created_at",
    ],
    "project_cost_lines": [
        "id", "assessment_id", "line_key", "label", "amount", "provenance",
        "category", "source", "note",
    ],
    "project_saved_comparisons": [
        "id", "project_id", "name", "site_ids", "created_at",
    ],
}

# The tables the read-only analytical endpoints need.
ANALYTICAL = [
    "analysis_units", "demographic_data", "economic_data", "accessibility_data",
    "competitor_locations", "own_estate_locations", "property_listings",
    "isochrone_cache", "ors_daily_usage", "candidate_sites", "candidate_catchments",
    "normalized_matrix_versions",
]

USER_OWNED = [
    "site_selection_projects", "project_business_requirements",
    "project_facility_requirements", "project_parking_requirements",
    "project_financial_requirements", "saved_scenarios", "export_records",
    "user_profiles", "project_rankings", "project_comparisons",
    "brokerage_opportunities", "data_quality_snapshots", "project_reports",
    "business_types", "property_opportunities", "external_sources",
    "project_cost_assessments", "project_cost_lines", "project_saved_comparisons",
]


def main() -> int:
    settings = get_settings()
    if not settings.has_supabase:
        print("Supabase is not configured; cannot audit the live schema.")
        return 1

    base = (settings.supabase_url or "").rstrip("/")
    key = settings.supabase_service_key
    headers = {
        "apikey": key or "",
        "Authorization": f"Bearer {key or ''}",
        "Accept": "application/json",
    }

    print("=" * 78)
    print("LIVE SCHEMA AUDIT")
    print("=" * 78)

    missing_tables: list[str] = []
    missing_columns: list[tuple[str, str]] = []
    row_counts: dict[str, int] = {}

    for table in sorted(EXPECTED):
        response = requests.get(
            f"{base}/rest/v1/{table}",
            headers=headers,
            params={"select": "*", "limit": 1},
            timeout=30,
        )
        if response.status_code == 404:
            missing_tables.append(table)
            print(f"MISSING TABLE  {table}")
            continue
        if response.status_code in (401, 403):
            print(f"NO ACCESS      {table}  (HTTP {response.status_code})")
            missing_tables.append(table)
            continue
        if response.status_code != 200:
            print(f"ERROR          {table}  (HTTP {response.status_code})")
            continue

        rows = response.json()
        present = set(rows[0].keys()) if rows else set()
        if not present:
            # The table exists but is empty: discover the columns from
            # OpenAPI instead.
            spec = requests.get(
                f"{base}/rest/v1/", headers=headers, timeout=30
            )
            if spec.status_code == 200:
                definitions = spec.json().get("definitions", {})
                present = set(definitions.get(table, {}).get("properties", {}).keys())
            else:
                present = set()

        expected = EXPECTED[table]
        absent = [column for column in expected if column not in present]
        if absent:
            for column in absent:
                missing_columns.append((table, column))
            print(f"MISSING COLUMN {table}: {', '.join(absent)}")
        else:
            print(f"OK             {table}")

        # Row count via the exact-count header.
        count_response = requests.get(
            f"{base}/rest/v1/{table}",
            headers={**headers, "Prefer": "count=exact", "Range": "0-0"},
            timeout=30,
        )
        raw_count = count_response.headers.get("content-range", "")
        if "/" in raw_count:
            row_counts[table] = int(raw_count.split("/")[-1])

    print()
    print("=" * 78)
    print("ROW COUNTS")
    print("=" * 78)
    for table, count in sorted(row_counts.items()):
        flag = ""
        if table in ANALYTICAL and count == 0:
            flag = "   <- analytical source is empty"
        print(f"  {table:36s} {count:>8d}{flag}")

    print()
    print("=" * 78)
    print("SUMMARY")
    print("=" * 78)
    print(f"missing tables   : {len(missing_tables)}")
    for table in missing_tables:
        print(f"    - {table}")
    print(f"missing columns  : {len(missing_columns)}")
    for table, column in missing_columns:
        print(f"    - {table}.{column}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
