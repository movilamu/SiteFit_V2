-- ============================================================================
-- 0003_authentication_and_artefacts.sql
--
-- Adds the authenticated-user layer and the analytical artefacts that a
-- user-owned analysis accumulates over time.
--
-- Design notes
--   * `user_profiles` mirrors the Supabase Auth user so the platform can
--     store a display name, a role and a preference without reading the
--     auth service on every request.
--   * `project_rankings` stores a *snapshot* of a ranking, with the exact
--     weight configuration that produced it.  A snapshot is what makes a
--     result reproducible and auditable after the weights have moved on.
--   * `project_comparisons` stores a saved side-by-side comparison.
--   * `brokerage_opportunities` stores the agencies discovered for a
--     location, with their source and retrieval time.
--   * `data_quality_snapshots` records the coverage figures for a data
--     release, so a report can state the evidence base it was produced
--     from.
--
-- Every table that belongs to a user is protected by Row Level Security
-- keyed on `auth.uid()`.  Nothing here weakens the policies in 0001 and
-- 0002.
-- ============================================================================
-- The spatial columns below need PostGIS.
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;


-- ---------------------------------------------------------------------------
-- User profiles
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS user_profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    display_name TEXT,
    organisation TEXT,
    role TEXT NOT NULL DEFAULT 'analyst'
        CHECK (role IN ('analyst', 'manager', 'admin')),
    avatar_url TEXT,
    preferences JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS user_profiles_self_policy ON user_profiles;
CREATE POLICY user_profiles_self_policy ON user_profiles
    FOR ALL
    USING (auth.uid() = id)
    WITH CHECK (auth.uid() = id);

-- A profile row is created on first sign-in by the API.
INSERT INTO user_profiles (id)
SELECT id FROM auth.users
ON CONFLICT (id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Ranking snapshots
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS project_rankings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL
        REFERENCES site_selection_projects(id) ON DELETE CASCADE,
    user_id UUID NOT NULL DEFAULT auth.uid(),
    label TEXT NOT NULL DEFAULT 'Ranking',
    -- The exact configuration that produced this ranking.  A result is only
    -- reproducible if the weights and the method are recorded with it.
    weight_set JSONB NOT NULL,
    level_weights JSONB,
    aggregation_method TEXT NOT NULL
        CHECK (aggregation_method IN ('weighted_sum', 'weighted_product', 'distance_to_ideal')),
    criteria_coverage JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- The ranked sites: [{rank, site_id, score}]
    ranking JSONB NOT NULL DEFAULT '[]'::jsonb,
    matrix_version TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS project_rankings_project_idx
    ON project_rankings (project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS project_rankings_user_idx ON project_rankings (user_id);

ALTER TABLE project_rankings ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS project_rankings_owner_policy ON project_rankings;
CREATE POLICY project_rankings_owner_policy ON project_rankings
    FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- Saved comparisons
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS project_comparisons (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL
        REFERENCES site_selection_projects(id) ON DELETE CASCADE,
    user_id UUID NOT NULL DEFAULT auth.uid(),
    name TEXT NOT NULL,
    site_ids TEXT[] NOT NULL DEFAULT '{}',
    weight_set JSONB,
    aggregation_method TEXT,
    notes TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS project_comparisons_project_idx
    ON project_comparisons (project_id, created_at DESC);

ALTER TABLE project_comparisons ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS project_comparisons_owner_policy ON project_comparisons;
CREATE POLICY project_comparisons_owner_policy ON project_comparisons
    FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- Brokerage opportunities
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS brokerage_opportunities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID
        REFERENCES site_selection_projects(id) ON DELETE CASCADE,
    user_id UUID DEFAULT auth.uid(),
    site_id TEXT,
    source_key TEXT NOT NULL,
    source_label TEXT NOT NULL DEFAULT '',
    publisher TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL,
    service_area TEXT NOT NULL DEFAULT '',
    website TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL DEFAULT '',
    listing_count INT NOT NULL DEFAULT 0,
    distance_m DOUBLE PRECISION,
    source_date DATE,
    -- live_source | recently_retrieved | source_date_available |
    -- source_date_unknown | unavailable
    source_status TEXT NOT NULL DEFAULT 'unavailable',
    kind TEXT NOT NULL DEFAULT 'automated'
        CHECK (kind IN ('automated', 'manual')),
    notes TEXT NOT NULL DEFAULT '',
    raw JSONB NOT NULL DEFAULT '{}'::jsonb,
    retrieved_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS brokerage_opportunities_project_idx
    ON brokerage_opportunities (project_id, site_id);
CREATE INDEX IF NOT EXISTS brokerage_opportunities_user_idx
    ON brokerage_opportunities (user_id);

ALTER TABLE brokerage_opportunities ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS brokerage_opportunities_owner_policy ON brokerage_opportunities;
CREATE POLICY brokerage_opportunities_owner_policy ON brokerage_opportunities
    FOR ALL
    USING (auth.uid() = user_id OR user_id IS NULL)
    WITH CHECK (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- Data-quality snapshots
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS data_quality_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID
        REFERENCES site_selection_projects(id) ON DELETE CASCADE,
    user_id UUID DEFAULT auth.uid(),
    matrix_version TEXT,
    -- The coverage figures as they were at the time of the snapshot.
    coverage JSONB NOT NULL DEFAULT '{}'::jsonb,
    criteria_availability JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_availability JSONB NOT NULL DEFAULT '[]'::jsonb,
    backtest_available BOOLEAN NOT NULL DEFAULT FALSE,
    limitations JSONB NOT NULL DEFAULT '[]'::jsonb,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS data_quality_snapshots_project_idx
    ON data_quality_snapshots (project_id, captured_at DESC);

ALTER TABLE data_quality_snapshots ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS data_quality_snapshots_owner_policy ON data_quality_snapshots;
CREATE POLICY data_quality_snapshots_owner_policy ON data_quality_snapshots
    FOR ALL
    USING (auth.uid() = user_id OR user_id IS NULL)
    WITH CHECK (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- Report artefacts
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS project_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL
        REFERENCES site_selection_projects(id) ON DELETE CASCADE,
    user_id UUID NOT NULL DEFAULT auth.uid(),
    title TEXT NOT NULL,
    format TEXT NOT NULL DEFAULT 'json'
        CHECK (format IN ('json', 'html', 'markdown', 'pdf', 'csv', 'xlsx')),
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS project_reports_project_idx
    ON project_reports (project_id, generated_at DESC);

ALTER TABLE project_reports ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS project_reports_owner_policy ON project_reports;
CREATE POLICY project_reports_owner_policy ON project_reports
    FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- The project row is the anchor for every artefact above, so it carries the
-- confirmation state and the brief version explicitly.
-- ---------------------------------------------------------------------------

ALTER TABLE site_selection_projects
    ADD COLUMN IF NOT EXISTS confirmed_at TIMESTAMPTZ;

ALTER TABLE site_selection_projects
    ADD COLUMN IF NOT EXISTS brief_version TEXT NOT NULL DEFAULT '2';

-- The requirements are held relationally in the project_*_requirements
-- tables, so the duplicated JSONB column is removed.
ALTER TABLE site_selection_projects
    DROP COLUMN IF EXISTS requirements;

-- The financial block gains the ownership horizon.
ALTER TABLE project_financial_requirements
    ADD COLUMN IF NOT EXISTS horizon_months INT NOT NULL DEFAULT 60;

-- The business requirement row carries the full definition, so the
-- interface can rebuild the form without a second lookup.
ALTER TABLE project_business_requirements
    ADD COLUMN IF NOT EXISTS value_type TEXT NOT NULL DEFAULT 'number';
ALTER TABLE project_business_requirements
    ADD COLUMN IF NOT EXISTS unit TEXT NOT NULL DEFAULT '';
ALTER TABLE project_business_requirements
    ADD COLUMN IF NOT EXISTS minimum DOUBLE PRECISION;
ALTER TABLE project_business_requirements
    ADD COLUMN IF NOT EXISTS maximum DOUBLE PRECISION;
ALTER TABLE project_business_requirements
    ADD COLUMN IF NOT EXISTS options JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE project_business_requirements
    ADD COLUMN IF NOT EXISTS help_text TEXT NOT NULL DEFAULT '';

-- The business-type catalogue is reference data shared by every user.
INSERT INTO business_types (key, label, description, is_custom, sort_order)
VALUES
    ('restaurant', 'Restaurant', 'Full-service or casual dining venue.', FALSE, 10),
    ('cafe', 'Café / Coffee Shop', 'Café, coffee bar or quick-service beverage outlet.', FALSE, 20),
    ('supermarket', 'Supermarket / Hypermarket', 'Full-line grocery retail.', FALSE, 30),
    ('hardware', 'Hardware / Building Materials', 'Hardware, building materials and trade supply.', FALSE, 40),
    ('pharmacy', 'Pharmacy', 'Retail pharmacy or chemist counter.', FALSE, 50),
    ('electronics', 'Electronics Retail', 'Consumer electronics and appliance retail.', FALSE, 60),
    ('clothing', 'Apparel / Clothing', 'Fashion, apparel and footwear retail.', FALSE, 70),
    ('furniture', 'Furniture / Home Furnishing', 'Furniture, home décor and furnishings retail.', FALSE, 80),
    ('jewellery', 'Jewellery', 'Jewellery, gem or watch retail with high-value stock.', FALSE, 90),
    ('convenience', 'Convenience / General Retail', 'Neighbourhood convenience store or general retail.', FALSE, 100),
    ('speciality_food', 'Speciality Food & Beverage', 'Speciality grocery, deli or food retail.', FALSE, 110),
    ('beauty', 'Beauty & Personal Care', 'Beauty, cosmetics and personal-care retail.', FALSE, 120),
    ('bank_branch', 'Bank Branch', 'Retail banking branch.', FALSE, 130),
    ('commercial', 'Commercial / Office', 'Office or commercial lease rather than consumer retail.', FALSE, 140),
    ('other', 'Other / Custom', 'A business type not covered above.', TRUE, 999)
ON CONFLICT (key) DO UPDATE
    SET label = EXCLUDED.label,
        description = EXCLUDED.description,
        is_custom = EXCLUDED.is_custom,
        sort_order = EXCLUDED.sort_order;
