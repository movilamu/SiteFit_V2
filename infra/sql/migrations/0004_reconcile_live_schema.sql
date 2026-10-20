-- ============================================================================
-- 0004_reconcile_live_schema.sql
--
-- Brings a database that already has the platform tables (0002 and 0003) in
-- line with the analytical schema and with the shapes the application
-- code actually uses.
--
-- The live project was created with an earlier, differently-shaped
-- `candidate_sites` table and with `export_records`, `saved_scenarios` and
-- `project_financial_requirements` that predate the current migrations.
-- This migration is additive and non-destructive: no table is dropped and
-- no existing row is modified.
--
-- Apply it with the Supabase SQL editor, or:
--   supabase db push --include-all
-- ============================================================================
-- The spatial columns below need PostGIS.
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;


-- ---------------------------------------------------------------------------
-- The candidate site inventory
-- ---------------------------------------------------------------------------
-- The live table already exists with an integer key and `latitude` /
-- `longitude`.  It is left exactly as it is; only the columns the
-- application expects but that are absent are added.

ALTER TABLE candidate_sites
    ADD COLUMN IF NOT EXISTS floor_area_sqm DOUBLE PRECISION;
ALTER TABLE candidate_sites
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE candidate_sites
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE candidate_sites
    ADD COLUMN IF NOT EXISTS unit_size DOUBLE PRECISION;
ALTER TABLE candidate_sites
    ADD COLUMN IF NOT EXISTS rent DOUBLE PRECISION;
ALTER TABLE candidate_sites
    ADD COLUMN IF NOT EXISTS tenure_type TEXT;

-- A business key so a site can be referenced by its own identifier.
ALTER TABLE candidate_sites
    ADD COLUMN IF NOT EXISTS site_id TEXT;

-- The retail format of the candidate site.  It is curated by the
-- analyst, not inferred, and the category-relative competition
-- criteria are unavailable while it is empty.
ALTER TABLE candidate_sites
    ADD COLUMN IF NOT EXISTS category TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS candidate_sites_site_id_key
    ON candidate_sites (site_id) WHERE site_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS candidate_sites_status_idx ON candidate_sites (status);

-- ---------------------------------------------------------------------------
-- The analytical schema
-- ---------------------------------------------------------------------------
-- These tables are created here rather than relying on 0001, because the
-- live database never had them.  The definitions match 0001 exactly, with
-- `candidate_catchments` keyed to the integer candidate id.

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

CREATE TABLE IF NOT EXISTS competitor_locations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    category VARCHAR(100),
    geometry GEOMETRY(Point, 4326) NOT NULL,
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
    attractiveness DOUBLE PRECISION,
    current_trading_performance DOUBLE PRECISION,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS own_estate_locations_geometry_idx
    ON own_estate_locations USING GIST (geometry);

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
-- The export record
-- ---------------------------------------------------------------------------
-- The live table has an integer `export_id` primary key and no payload.
-- The payload is what makes an export reproducible, so it is added and the
-- key is moved to a surrogate UUID.

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

ALTER TABLE export_records ALTER COLUMN created_at SET DEFAULT NOW();

CREATE INDEX IF NOT EXISTS export_records_user_idx ON export_records (user_id);

-- ---------------------------------------------------------------------------
-- Scenarios are owned by the user who saved them.
-- ---------------------------------------------------------------------------

ALTER TABLE saved_scenarios
    ADD COLUMN IF NOT EXISTS user_id UUID;

CREATE INDEX IF NOT EXISTS saved_scenarios_user_idx ON saved_scenarios (user_id);

-- ---------------------------------------------------------------------------
-- The financial block keeps the full budget list, so that a budget's scope
-- and its own behaviour are preserved and not only its limit.
-- ---------------------------------------------------------------------------

ALTER TABLE project_financial_requirements
    ADD COLUMN IF NOT EXISTS budgets JSONB NOT NULL DEFAULT '[]'::jsonb;

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------
-- The analytical tables are written by the service-role jobs and are read
-- through the API.  They are not exposed to end users directly.

ALTER TABLE analysis_units ENABLE ROW LEVEL SECURITY;
ALTER TABLE demographic_data ENABLE ROW LEVEL SECURITY;
ALTER TABLE economic_data ENABLE ROW LEVEL SECURITY;
ALTER TABLE accessibility_data ENABLE ROW LEVEL SECURITY;
ALTER TABLE competitor_locations ENABLE ROW LEVEL SECURITY;
ALTER TABLE own_estate_locations ENABLE ROW LEVEL SECURITY;
ALTER TABLE property_listings ENABLE ROW LEVEL SECURITY;
ALTER TABLE isochrone_cache ENABLE ROW LEVEL SECURITY;
ALTER TABLE ors_daily_usage ENABLE ROW LEVEL SECURITY;
ALTER TABLE spatial_boundaries ENABLE ROW LEVEL SECURITY;
ALTER TABLE land_use_polygons ENABLE ROW LEVEL SECURITY;
ALTER TABLE road_network ENABLE ROW LEVEL SECURITY;
ALTER TABLE candidate_catchments ENABLE ROW LEVEL SECURITY;
ALTER TABLE normalized_matrix_versions ENABLE ROW LEVEL SECURITY;

-- The export record belongs to the user who created it.
ALTER TABLE export_records ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS export_records_owner_policy ON export_records;
CREATE POLICY export_records_owner_policy ON export_records
    FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- A saved scenario belongs to the user who saved it.  A scenario with no
-- owner is visible only to the service role, which is what the scheduled
-- jobs use.
ALTER TABLE saved_scenarios ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS saved_scenarios_owner_policy ON saved_scenarios;
CREATE POLICY saved_scenarios_owner_policy ON saved_scenarios
    FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- A user profile is created when a user first signs in.
-- ---------------------------------------------------------------------------

INSERT INTO user_profiles (id)
SELECT id FROM auth.users
ON CONFLICT (id) DO NOTHING;
