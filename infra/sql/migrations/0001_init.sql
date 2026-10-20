-- ============================================================================
-- 0001_init.sql
-- Core analytical schema for the Retail Site Intelligence platform.
--
-- This migration materialises the tables the ingestion pipeline writes and
-- the scoring engine reads.  The DDL mirrors the table definitions that
-- previously existed only as inline strings inside the Python ETL modules
-- (ingestion/geospatial_base_etl.py, ingestion/generate_catchments.py,
-- ingestion/isochrones.py and scoring/precompute_matrix.py), so the schema
-- is now reproducible from version control.
--
-- Conventions
--   * Timestamps are TIMESTAMPTZ and default to NOW().
--   * Every table has a primary key, a created_at/updated_at pair and the
--     indexes needed by the documented query patterns.
--   * Geometry columns use PostGIS and are indexed with GIST.
--   * Row Level Security is enabled throughout.  Analytical tables are
--     written by service-role ETL jobs and read through the API; the
--     user-owned tables carry an explicit ownership policy.
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------------------
-- Spatial base
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS spatial_boundaries (
    id BIGSERIAL PRIMARY KEY,
    osm_id BIGINT NOT NULL,
    name VARCHAR(255),
    admin_level INT,
    boundary_type VARCHAR(100) DEFAULT 'administrative',
    geometry GEOMETRY(Geometry, 4326) NOT NULL,
    area_sqkm DOUBLE PRECISION,
    properties JSONB DEFAULT '{}'::jsonb,
    source VARCHAR(100) DEFAULT 'OpenStreetMap',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_spatial_boundaries_osm UNIQUE (osm_id, boundary_type)
);

CREATE INDEX IF NOT EXISTS spatial_boundaries_geometry_idx
    ON spatial_boundaries USING GIST (geometry);
CREATE INDEX IF NOT EXISTS spatial_boundaries_name_idx
    ON spatial_boundaries (name);

CREATE TABLE IF NOT EXISTS land_use_polygons (
    id BIGSERIAL PRIMARY KEY,
    osm_id BIGINT NOT NULL,
    landuse_type VARCHAR(100) NOT NULL,
    name VARCHAR(255),
    geometry GEOMETRY(Geometry, 4326) NOT NULL,
    area_sqm DOUBLE PRECISION,
    properties JSONB DEFAULT '{}'::jsonb,
    source VARCHAR(100) DEFAULT 'OpenStreetMap',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_land_use_osm UNIQUE (osm_id, landuse_type)
);

CREATE INDEX IF NOT EXISTS land_use_polygons_geometry_idx
    ON land_use_polygons USING GIST (geometry);
CREATE INDEX IF NOT EXISTS land_use_polygons_type_idx
    ON land_use_polygons (landuse_type);

CREATE TABLE IF NOT EXISTS road_network (
    id BIGSERIAL PRIMARY KEY,
    osm_id BIGINT NOT NULL,
    name VARCHAR(255),
    highway_type VARCHAR(100) NOT NULL,
    oneway BOOLEAN DEFAULT FALSE,
    maxspeed INT,
    length_meters DOUBLE PRECISION NOT NULL,
    estimated_travel_time_sec DOUBLE PRECISION NOT NULL,
    geometry GEOMETRY(LineString, 4326) NOT NULL,
    properties JSONB DEFAULT '{}'::jsonb,
    source VARCHAR(100) DEFAULT 'OpenStreetMap',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_road_network_osm UNIQUE (osm_id)
);

CREATE INDEX IF NOT EXISTS road_network_geometry_idx
    ON road_network USING GIST (geometry);
CREATE INDEX IF NOT EXISTS road_network_highway_type_idx
    ON road_network (highway_type);

-- ---------------------------------------------------------------------------
-- Analysis units — the canonical H3 resolution-8 grid
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS analysis_units (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(255),
    resolution INT NOT NULL DEFAULT 8,
    lat DOUBLE PRECISION NOT NULL,
    lon DOUBLE PRECISION NOT NULL,
    geometry GEOMETRY(Polygon, 4326),
    source VARCHAR(100) DEFAULT 'H3',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS analysis_units_geometry_idx
    ON analysis_units USING GIST (geometry);
CREATE INDEX IF NOT EXISTS analysis_units_resolution_idx
    ON analysis_units (resolution);

-- ---------------------------------------------------------------------------
-- Demographic and economic attributes
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS demographic_data (
    id BIGSERIAL PRIMARY KEY,
    unit_id VARCHAR(64) NOT NULL REFERENCES analysis_units(id) ON DELETE CASCADE,
    population DOUBLE PRECISION,
    age_bands JSONB,
    household_count DOUBLE PRECISION,
    literacy_rate DOUBLE PRECISION,
    workforce_participation DOUBLE PRECISION,
    data_confidence DOUBLE PRECISION,
    source_year INT,
    source VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_demographic_unit_year UNIQUE (unit_id, source_year)
);

CREATE INDEX IF NOT EXISTS demographic_data_unit_idx ON demographic_data (unit_id);
CREATE INDEX IF NOT EXISTS demographic_data_year_idx ON demographic_data (source_year);

CREATE TABLE IF NOT EXISTS economic_data (
    id BIGSERIAL PRIMARY KEY,
    unit_id VARCHAR(64) NOT NULL REFERENCES analysis_units(id) ON DELETE CASCADE,
    spending_by_category JSONB,
    disposable_income_estimate DOUBLE PRECISION,
    expenditure_index DOUBLE PRECISION,
    mpce DOUBLE PRECISION,
    data_confidence DOUBLE PRECISION,
    source_year INT,
    source VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_economic_unit_year UNIQUE (unit_id, source_year)
);

CREATE INDEX IF NOT EXISTS economic_data_unit_idx ON economic_data (unit_id);
CREATE INDEX IF NOT EXISTS economic_data_year_idx ON economic_data (source_year);

-- ---------------------------------------------------------------------------
-- Accessibility
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS accessibility_data (
    id BIGSERIAL PRIMARY KEY,
    unit_id VARCHAR(64) NOT NULL REFERENCES analysis_units(id) ON DELETE CASCADE,
    transit_score DOUBLE PRECISION,
    parking_availability DOUBLE PRECISION,
    footfall_estimate INT,
    data_confidence DOUBLE PRECISION,
    source VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_accessibility_unit UNIQUE (unit_id)
);

CREATE INDEX IF NOT EXISTS accessibility_data_unit_idx ON accessibility_data (unit_id);

-- ---------------------------------------------------------------------------
-- Competitive set and own estate
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS competitor_locations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    category VARCHAR(100),
    geometry GEOMETRY(Point, 4326) NOT NULL,
    -- Size / quality proxy used by the gravity model.  Must be expressed in
    -- the same units for every destination; the ingestion job sets it from
    -- the recorded floor area.  NULL means "not yet measured".
    attractiveness DOUBLE PRECISION,
    source VARCHAR(100) DEFAULT 'OpenStreetMap',
    last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS competitor_locations_geometry_idx
    ON competitor_locations USING GIST (geometry);
CREATE INDEX IF NOT EXISTS competitor_locations_category_idx
    ON competitor_locations (category);

CREATE TABLE IF NOT EXISTS own_estate_locations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    geometry GEOMETRY(Point, 4326) NOT NULL,
    -- Attractiveness proxy in the same units as competitor_locations.
    -- Deliberately separate from current_trading_performance, which is a
    -- currency amount and must never be used as a gravity-model weight.
    attractiveness DOUBLE PRECISION,
    current_trading_performance DOUBLE PRECISION,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS own_estate_locations_geometry_idx
    ON own_estate_locations USING GIST (geometry);

-- ---------------------------------------------------------------------------
-- Property inventory
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS property_listings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255),
    geometry GEOMETRY(Point, 4326),
    unit_size DOUBLE PRECISION,
    floor_area DOUBLE PRECISION,
    rent DOUBLE PRECISION,
    lease_term_years DOUBLE PRECISION,
    tenure_type VARCHAR(50),
    purchase_price DOUBLE PRECISION,
    source VARCHAR(255),
    source_record_id VARCHAR(255),
    last_updated TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Content fingerprint used for idempotent re-ingestion.  The unique index
-- makes a repeated ingest a no-op instead of creating duplicates.
CREATE UNIQUE INDEX IF NOT EXISTS property_listings_source_fingerprint_idx
    ON property_listings (
        COALESCE(source_record_id, md5(
            COALESCE(name, '') || '|' ||
            COALESCE(ST_X(geometry)::text, '') || ',' ||
            COALESCE(ST_Y(geometry)::text, '') || '|' ||
            COALESCE(unit_size::text, '') || '|' ||
            COALESCE(floor_area::text, '') || '|' ||
            COALESCE(rent::text, '') || '|' ||
            COALESCE(lease_term_years::text, '') || '|' ||
            COALESCE(tenure_type, '') || '|' ||
            COALESCE(source, '')
        ))
    );
CREATE INDEX IF NOT EXISTS property_listings_geometry_idx
    ON property_listings USING GIST (geometry);

-- ---------------------------------------------------------------------------
-- Routing and isochrones
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS isochrone_cache (
    id BIGSERIAL PRIMARY KEY,
    lat DOUBLE PRECISION NOT NULL,
    lon DOUBLE PRECISION NOT NULL,
    profile VARCHAR(50) NOT NULL,
    range_value INT NOT NULL,
    geometry GEOMETRY(Polygon, 4326) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_isochrone_cache UNIQUE (lat, lon, profile, range_value)
);

CREATE INDEX IF NOT EXISTS isochrone_cache_geometry_idx
    ON isochrone_cache USING GIST (geometry);

CREATE TABLE IF NOT EXISTS ors_daily_usage (
    usage_date DATE PRIMARY KEY,
    request_count INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- Candidate sites and their catchments
-- ---------------------------------------------------------------------------

-- The shape of this table is the one already deployed in the live
-- project: an integer surrogate key, a business key in `site_id`, and
-- `latitude`/`longitude` rather than `lat`/`lon`.
CREATE TABLE IF NOT EXISTS candidate_sites (
    id BIGSERIAL PRIMARY KEY,
    site_id TEXT,
    name TEXT,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    unit_size DOUBLE PRECISION,
    rent DOUBLE PRECISION,
    tenure_type TEXT,
    attractiveness DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    floor_area_sqm DOUBLE PRECISION,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'paused', 'rejected', 'opened')),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS candidate_sites_site_id_key
    ON candidate_sites (site_id) WHERE site_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS candidate_sites_status_idx ON candidate_sites (status);

CREATE TABLE IF NOT EXISTS candidate_catchments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_site_id BIGINT NOT NULL
        REFERENCES candidate_sites(id) ON DELETE CASCADE,
    profile TEXT NOT NULL DEFAULT 'driving-car',
    range_minutes_short INTEGER NOT NULL DEFAULT 10,
    range_minutes_long INTEGER NOT NULL DEFAULT 15,
    lat DOUBLE PRECISION NOT NULL,
    lon DOUBLE PRECISION NOT NULL,
    isochrone_10min JSONB,
    isochrone_15min JSONB,
    gravity_catchment JSONB,
    competitor_overlap JSONB,
    cannibalization JSONB,
    cannibalization_score DOUBLE PRECISION,
    competitor_count_10min INTEGER,
    own_estate_count_10min INTEGER,
    competitor_count_15min INTEGER,
    own_estate_count_15min INTEGER,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (candidate_site_id, profile, range_minutes_short, range_minutes_long)
);

CREATE INDEX IF NOT EXISTS candidate_catchments_score_idx
    ON candidate_catchments (cannibalization_score);
CREATE INDEX IF NOT EXISTS candidate_catchments_site_idx
    ON candidate_catchments (candidate_site_id);

-- ---------------------------------------------------------------------------
-- Scoring artefacts
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS normalized_matrix_versions (
    version_id TEXT PRIMARY KEY,
    data_release_at TIMESTAMPTZ NOT NULL,
    storage_path TEXT NOT NULL,
    n_sites_in INT,
    n_sites_out INT,
    n_excluded INT,
    scored_criterion_keys JSONB,
    leaf_keys JSONB,
    parent_to_children JSONB,
    excluded_sites JSONB,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS normalized_matrix_versions_release_idx
    ON normalized_matrix_versions (data_release_at DESC);

-- ---------------------------------------------------------------------------
-- User-owned analytical artefacts
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS saved_scenarios (
    scenario_id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL DEFAULT auth.uid(),
    name TEXT NOT NULL CHECK (length(btrim(name)) > 0),
    weight_set JSONB NOT NULL,
    aggregation_method TEXT NOT NULL
        CHECK (aggregation_method IN ('weighted_sum', 'weighted_product', 'distance_to_ideal')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS export_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    export_id BIGINT,
    user_id UUID DEFAULT auth.uid(),
    scenario_id BIGINT REFERENCES saved_scenarios(scenario_id) ON DELETE SET NULL,
    storage_path TEXT,
    weight_set JSONB,
    aggregation_method TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- Reconciliation with an existing installation
-- ---------------------------------------------------------------------------
-- The tables above are created only when they do not already exist.  When
-- they do exist, but with an older shape, the columns the application
-- needs are added here so that this migration can be applied on its own.

ALTER TABLE saved_scenarios
    ADD COLUMN IF NOT EXISTS user_id UUID;

ALTER TABLE export_records
    ADD COLUMN IF NOT EXISTS id UUID DEFAULT gen_random_uuid();
ALTER TABLE export_records
    ADD COLUMN IF NOT EXISTS user_id UUID;
ALTER TABLE export_records
    ADD COLUMN IF NOT EXISTS weight_set JSONB;
ALTER TABLE export_records
    ADD COLUMN IF NOT EXISTS aggregation_method TEXT;
ALTER TABLE export_records
    ADD COLUMN IF NOT EXISTS payload JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE export_records
    ADD COLUMN IF NOT EXISTS storage_path TEXT;

-- The older shape uses an integer identity column as the primary key.
-- The primary key has to be dropped before the column can be changed, and
-- the identity has to be dropped before the column can be made nullable.
ALTER TABLE export_records DROP CONSTRAINT IF EXISTS export_records_pkey;
DO $$
BEGIN
    -- The identity is only present in the older shape, and only the first
    -- migration to run against a given database will find it.
    IF EXISTS (
        SELECT 1 FROM pg_attribute
        WHERE attrelid = 'export_records'::regclass
          AND attname = 'export_id'
          AND attidentity <> ''
    ) THEN
        ALTER TABLE export_records ALTER COLUMN export_id DROP IDENTITY;
    END IF;
END $$;

UPDATE export_records SET id = gen_random_uuid() WHERE id IS NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'export_records'::regclass AND contype = 'p'
    ) THEN
        ALTER TABLE export_records ADD PRIMARY KEY (id);
    END IF;
END $$;


CREATE INDEX IF NOT EXISTS saved_scenarios_user_idx ON saved_scenarios (user_id);
CREATE INDEX IF NOT EXISTS export_records_user_idx ON export_records (user_id);

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------
-- Analytical tables are populated by service-role ETL jobs and are read
-- through the API with server-side credentials.  They are not directly
-- exposed to end users, so the anon/authenticated roles get no access.
-- User-owned tables (saved_scenarios, export_records) are restricted to
-- their owner.

ALTER TABLE spatial_boundaries ENABLE ROW LEVEL SECURITY;
ALTER TABLE land_use_polygons ENABLE ROW LEVEL SECURITY;
ALTER TABLE road_network ENABLE ROW LEVEL SECURITY;
ALTER TABLE analysis_units ENABLE ROW LEVEL SECURITY;
ALTER TABLE demographic_data ENABLE ROW LEVEL SECURITY;
ALTER TABLE economic_data ENABLE ROW LEVEL SECURITY;
ALTER TABLE accessibility_data ENABLE ROW LEVEL SECURITY;
ALTER TABLE competitor_locations ENABLE ROW LEVEL SECURITY;
ALTER TABLE own_estate_locations ENABLE ROW LEVEL SECURITY;
ALTER TABLE property_listings ENABLE ROW LEVEL SECURITY;
ALTER TABLE isochrone_cache ENABLE ROW LEVEL SECURITY;
ALTER TABLE ors_daily_usage ENABLE ROW LEVEL SECURITY;
ALTER TABLE candidate_sites ENABLE ROW LEVEL SECURITY;
ALTER TABLE candidate_catchments ENABLE ROW LEVEL SECURITY;
ALTER TABLE normalized_matrix_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE saved_scenarios ENABLE ROW LEVEL SECURITY;
ALTER TABLE export_records ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS saved_scenarios_owner_policy ON saved_scenarios;
CREATE POLICY saved_scenarios_owner_policy ON saved_scenarios
    FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS export_records_owner_policy ON export_records;
CREATE POLICY export_records_owner_policy ON export_records
    FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);
