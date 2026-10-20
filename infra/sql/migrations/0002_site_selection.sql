-- ============================================================================
-- 0002_site_selection.sql
-- Site-selection platform entities.
--
-- These tables hold the *user's* work: a site-selection analysis, the
-- requirements that drive it, the resulting cost position, any external
-- property or brokerage opportunities that were surfaced, and the
-- generated executive reports.
--
-- Every table is owned by a single authenticated user.  Row Level
-- Security guarantees that one user can never read another user's
-- analysis, requirements, cost data or reports.
--
-- Design note
--   The requirement block is inherently variable (it depends on the chosen
--   business type), so it is stored as JSONB and validated by the API.
--   The parts that are queried or aggregated - facilities, parking,
--   budgets, cost lines, property opportunities and reports - are stored
--   relationally so they can be indexed, filtered and audited.
-- ============================================================================
-- The spatial columns below need PostGIS.
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;


-- ---------------------------------------------------------------------------
-- Business type catalogue
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS business_types (
    key TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    is_custom BOOLEAN NOT NULL DEFAULT FALSE,
    sort_order INT NOT NULL DEFAULT 100,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- Site-selection projects (the analysis itself)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS site_selection_projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL DEFAULT auth.uid(),
    name TEXT NOT NULL CHECK (length(btrim(name)) > 0),
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'requirements_confirmed', 'analysed', 'reported', 'archived')),
    business_type TEXT REFERENCES business_types(key) ON DELETE SET NULL,
    acquisition_mode TEXT NOT NULL DEFAULT 'either'
        CHECK (acquisition_mode IN ('buy', 'lease', 'either')),
    -- The geographic search area, as chosen by the user.
    location JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- The confirmed requirement block (business requirements, parking,
    -- facilities, financial inputs and constraint behaviours).
    requirements JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- The weight configuration applied to the ranking.
    weights JSONB,
    aggregation_method TEXT NOT NULL DEFAULT 'weighted_sum'
        CHECK (aggregation_method IN ('weighted_sum', 'weighted_product', 'distance_to_ideal')),
    -- Snapshot of the criteria coverage at the time of analysis.
    criteria_coverage JSONB,
    notes TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS site_selection_projects_user_idx
    ON site_selection_projects (user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS site_selection_projects_status_idx
    ON site_selection_projects (status);

-- ---------------------------------------------------------------------------
-- Requirement detail tables
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS project_business_requirements (
    id BIGSERIAL PRIMARY KEY,
    project_id UUID NOT NULL
        REFERENCES site_selection_projects(id) ON DELETE CASCADE,
    requirement_key TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    importance TEXT NOT NULL CHECK (importance IN ('required', 'preferred', 'not_important')),
    value NUMERIC,
    value_text TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_project_business_requirement
        UNIQUE (project_id, requirement_key)
);

CREATE INDEX IF NOT EXISTS project_business_requirements_project_idx
    ON project_business_requirements (project_id);

CREATE TABLE IF NOT EXISTS project_facility_requirements (
    id BIGSERIAL PRIMARY KEY,
    project_id UUID NOT NULL
        REFERENCES site_selection_projects(id) ON DELETE CASCADE,
    facility_key TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    importance TEXT NOT NULL CHECK (importance IN ('required', 'preferred', 'not_important')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_project_facility_requirement
        UNIQUE (project_id, facility_key)
);

CREATE INDEX IF NOT EXISTS project_facility_requirements_project_idx
    ON project_facility_requirements (project_id);

CREATE TABLE IF NOT EXISTS project_parking_requirements (
    id BIGSERIAL PRIMARY KEY,
    project_id UUID NOT NULL UNIQUE
        REFERENCES site_selection_projects(id) ON DELETE CASCADE,
    min_car_spaces INT,
    min_two_wheeler_spaces INT,
    min_parking_area_sqft NUMERIC,
    behaviour TEXT NOT NULL DEFAULT 'preference'
        CHECK (behaviour IN ('hard', 'preference', 'flexible')),
    scope TEXT NOT NULL DEFAULT 'site'
        CHECK (scope IN ('site', 'site_and_catchment')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS project_financial_requirements (
    id BIGSERIAL PRIMARY KEY,
    project_id UUID NOT NULL UNIQUE
        REFERENCES site_selection_projects(id) ON DELETE CASCADE,
    purchase_budget NUMERIC,
    monthly_rent_budget NUMERIC,
    security_deposit_budget NUMERIC,
    brokerage_budget NUMERIC,
    renovation_budget NUMERIC,
    initial_investment_budget NUMERIC,
    monthly_operating_budget NUMERIC,
    -- 'penalise' keeps a site that exceeds a budget but lowers its score;
    -- 'hard' excludes it.  The default is 'penalise' so that a budget is
    -- never a silent filter.
    budget_behaviour TEXT NOT NULL DEFAULT 'penalise'
        CHECK (budget_behaviour IN ('penalise', 'hard')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- Cost analysis
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS project_cost_assessments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL
        REFERENCES site_selection_projects(id) ON DELETE CASCADE,
    site_id TEXT NOT NULL,
    acquisition_mode TEXT NOT NULL
        CHECK (acquisition_mode IN ('buy', 'lease', 'either')),
    acquisition_total NUMERIC,
    setup_total NUMERIC,
    recurring_monthly_total NUMERIC,
    recurring_annual_total NUMERIC,
    initial_investment_total NUMERIC,
    known_minimum_initial_investment NUMERIC,
    is_complete BOOLEAN NOT NULL DEFAULT FALSE,
    notes TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_project_cost_assessment
        UNIQUE (project_id, site_id)
);

CREATE INDEX IF NOT EXISTS project_cost_assessments_project_idx
    ON project_cost_assessments (project_id);

CREATE TABLE IF NOT EXISTS project_cost_lines (
    id BIGSERIAL PRIMARY KEY,
    assessment_id UUID NOT NULL
        REFERENCES project_cost_assessments(id) ON DELETE CASCADE,
    line_key TEXT NOT NULL,
    label TEXT NOT NULL,
    amount NUMERIC,
    -- The provenance of the amount.  'unavailable' means no defensible
    -- value could be established; it must never be silently treated as 0.
    provenance TEXT NOT NULL
        CHECK (provenance IN ('verified_listed', 'user_provided', 'estimated', 'calculated', 'unavailable')),
    category TEXT NOT NULL CHECK (category IN ('acquisition', 'setup', 'recurring')),
    source TEXT,
    note TEXT NOT NULL DEFAULT '',
    CONSTRAINT uq_project_cost_line UNIQUE (assessment_id, line_key)
);

-- ---------------------------------------------------------------------------
-- External property and brokerage opportunities
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS external_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key TEXT NOT NULL UNIQUE,
    label TEXT NOT NULL,
    publisher TEXT NOT NULL DEFAULT '',
    homepage_url TEXT,
    -- 'operational' | 'unavailable' | 'disabled' | 'rate_limited' | 'error'
    status TEXT NOT NULL DEFAULT 'disabled',
    last_checked_at TIMESTAMPTZ,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS property_opportunities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL
        REFERENCES site_selection_projects(id) ON DELETE CASCADE,
    site_id TEXT,
    source_id UUID REFERENCES external_sources(id) ON DELETE SET NULL,
    source_key TEXT NOT NULL DEFAULT '',
    source_label TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL,
    source_url TEXT,
    location TEXT NOT NULL DEFAULT '',
    property_type TEXT NOT NULL DEFAULT '',
    area_sqft NUMERIC,
    purchase_price NUMERIC,
    monthly_rent NUMERIC,
    security_deposit NUMERIC,
    parking_spaces INT,
    facilities TEXT NOT NULL DEFAULT '',
    broker_name TEXT NOT NULL DEFAULT '',
    broker_contact TEXT NOT NULL DEFAULT '',
    listed_at DATE,
    retrieved_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- 'listed' | 'estimated' | 'unavailable' for the price fields.
    price_provenance TEXT NOT NULL DEFAULT 'unavailable',
    verification_status TEXT NOT NULL DEFAULT 'unverified'
        CHECK (verification_status IN ('unverified', 'source_confirmed', 'expired', 'rejected')),
    raw JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_property_opportunity
        UNIQUE (project_id, source_key, source_url, title)
);

CREATE INDEX IF NOT EXISTS property_opportunities_project_idx
    ON property_opportunities (project_id);
CREATE INDEX IF NOT EXISTS property_opportunities_site_idx
    ON property_opportunities (site_id);

-- ---------------------------------------------------------------------------
-- Reports
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS project_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL
        REFERENCES site_selection_projects(id) ON DELETE CASCADE,
    user_id UUID NOT NULL DEFAULT auth.uid(),
    title TEXT NOT NULL,
    format TEXT NOT NULL DEFAULT 'json' CHECK (format IN ('json', 'html', 'markdown')),
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS project_reports_project_idx ON project_reports (project_id);

-- ---------------------------------------------------------------------------
-- Saved comparisons
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS project_saved_comparisons (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL
        REFERENCES site_selection_projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    site_ids TEXT[] NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_project_saved_comparison UNIQUE (project_id, name)
);

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------

ALTER TABLE business_types ENABLE ROW LEVEL SECURITY;
ALTER TABLE site_selection_projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE project_business_requirements ENABLE ROW LEVEL SECURITY;
ALTER TABLE project_facility_requirements ENABLE ROW LEVEL SECURITY;
ALTER TABLE project_parking_requirements ENABLE ROW LEVEL SECURITY;
ALTER TABLE project_financial_requirements ENABLE ROW LEVEL SECURITY;
ALTER TABLE project_cost_assessments ENABLE ROW LEVEL SECURITY;
ALTER TABLE project_cost_lines ENABLE ROW LEVEL SECURITY;
ALTER TABLE external_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE property_opportunities ENABLE ROW LEVEL SECURITY;
ALTER TABLE project_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE project_saved_comparisons ENABLE ROW LEVEL SECURITY;

-- The business-type catalogue is reference data, readable by every
-- authenticated user and writable only by the service role.
DROP POLICY IF EXISTS business_types_read_policy ON business_types;
CREATE POLICY business_types_read_policy ON business_types
    FOR SELECT TO authenticated USING (TRUE);

-- Everything else belongs to exactly one user.
DROP POLICY IF EXISTS site_selection_projects_owner_policy ON site_selection_projects;
CREATE POLICY site_selection_projects_owner_policy ON site_selection_projects
    FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS project_business_requirements_owner_policy ON project_business_requirements;
CREATE POLICY project_business_requirements_owner_policy ON project_business_requirements
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM site_selection_projects p
            WHERE p.id = project_id AND p.user_id = auth.uid()
        )
    ) WITH CHECK (
        EXISTS (
            SELECT 1 FROM site_selection_projects p
            WHERE p.id = project_id AND p.user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS project_facility_requirements_owner_policy ON project_facility_requirements;
CREATE POLICY project_facility_requirements_owner_policy ON project_facility_requirements
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM site_selection_projects p
            WHERE p.id = project_id AND p.user_id = auth.uid()
        )
    ) WITH CHECK (
        EXISTS (
            SELECT 1 FROM site_selection_projects p
            WHERE p.id = project_id AND p.user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS project_parking_requirements_owner_policy ON project_parking_requirements;
CREATE POLICY project_parking_requirements_owner_policy ON project_parking_requirements
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM site_selection_projects p
            WHERE p.id = project_id AND p.user_id = auth.uid()
        )
    ) WITH CHECK (
        EXISTS (
            SELECT 1 FROM site_selection_projects p
            WHERE p.id = project_id AND p.user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS project_financial_requirements_owner_policy ON project_financial_requirements;
CREATE POLICY project_financial_requirements_owner_policy ON project_financial_requirements
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM site_selection_projects p
            WHERE p.id = project_id AND p.user_id = auth.uid()
        )
    ) WITH CHECK (
        EXISTS (
            SELECT 1 FROM site_selection_projects p
            WHERE p.id = project_id AND p.user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS project_cost_assessments_owner_policy ON project_cost_assessments;
CREATE POLICY project_cost_assessments_owner_policy ON project_cost_assessments
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM site_selection_projects p
            WHERE p.id = project_id AND p.user_id = auth.uid()
        )
    ) WITH CHECK (
        EXISTS (
            SELECT 1 FROM site_selection_projects p
            WHERE p.id = project_id AND p.user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS project_cost_lines_owner_policy ON project_cost_lines;
CREATE POLICY project_cost_lines_owner_policy ON project_cost_lines
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM project_cost_assessments a
            JOIN site_selection_projects p ON p.id = a.project_id
            WHERE a.id = assessment_id AND p.user_id = auth.uid()
        )
    ) WITH CHECK (
        EXISTS (
            SELECT 1 FROM project_cost_assessments a
            JOIN site_selection_projects p ON p.id = a.project_id
            WHERE a.id = assessment_id AND p.user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS external_sources_read_policy ON external_sources;
CREATE POLICY external_sources_read_policy ON external_sources
    FOR SELECT TO authenticated USING (TRUE);

DROP POLICY IF EXISTS property_opportunities_owner_policy ON property_opportunities;
CREATE POLICY property_opportunities_owner_policy ON property_opportunities
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM site_selection_projects p
            WHERE p.id = project_id AND p.user_id = auth.uid()
        )
    ) WITH CHECK (
        EXISTS (
            SELECT 1 FROM site_selection_projects p
            WHERE p.id = project_id AND p.user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS project_reports_owner_policy ON project_reports;
CREATE POLICY project_reports_owner_policy ON project_reports
    FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS project_saved_comparisons_owner_policy ON project_saved_comparisons;
CREATE POLICY project_saved_comparisons_owner_policy ON project_saved_comparisons
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM site_selection_projects p
            WHERE p.id = project_id AND p.user_id = auth.uid()
        )
    ) WITH CHECK (
        EXISTS (
            SELECT 1 FROM site_selection_projects p
            WHERE p.id = project_id AND p.user_id = auth.uid()
        )
    );
