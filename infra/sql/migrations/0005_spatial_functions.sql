-- ============================================================================
-- 0005_spatial_functions.sql
--
-- The catchment overlap computation is performed by a PostGIS function so
-- that the spatial predicate runs inside the database rather than over
-- thousands of rows in the client.
--
-- The function definition is held in `ingestion/competitor_overlap.py` as
-- `POSTGIS_RPC_MIGRATION_SQL` and is applied here verbatim, so the code and
-- the schema cannot drift apart.
--
-- Apply it with the Supabase SQL editor, or:
--   supabase db push --include-all
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS postgis;

-- Supabase / PostGIS RPC Migration Function
CREATE OR REPLACE FUNCTION compute_catchment_overlap(
    catchment_geojson JSONB,
    trade_area_radius_m DOUBLE PRECISION DEFAULT 1000.0,
    spatial_predicate TEXT DEFAULT 'ST_Intersects'
)
RETURNS TABLE (
    location_type TEXT,
    id TEXT,
    name TEXT,
    category TEXT,
    current_trading_performance NUMERIC,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    is_contained BOOLEAN,
    is_intersecting BOOLEAN,
    distance_to_centroid_m DOUBLE PRECISION,
    overlap_percentage NUMERIC
)
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    catchment_geom GEOMETRY;
BEGIN
    catchment_geom := ST_SetSRID(ST_GeomFromGeoJSON(catchment_geojson::text), 4326);

    IF catchment_geom IS NULL OR ST_IsEmpty(catchment_geom) THEN
        RAISE EXCEPTION 'Invalid or empty catchment geometry.';
    END IF;

    RETURN QUERY
    WITH site_catchment AS (
        SELECT catchment_geom AS geom
    ),
    competitors AS (
        SELECT
            'competitor'::TEXT AS location_type,
            c.id::TEXT AS id,
            c.name::TEXT AS name,
            c.category::TEXT AS category,
            NULL::NUMERIC AS current_trading_performance,
            ST_Y(c.geometry::geometry) AS latitude,
            ST_X(c.geometry::geometry) AS longitude,
            ST_Contains(sc.geom, c.geometry) AS is_contained,
            ST_Intersects(sc.geom, c.geometry) AS is_intersecting,
            ST_Distance(c.geometry::geography, ST_Centroid(sc.geom)::geography) AS distance_to_centroid_m,
            ROUND(
                (
                    ST_Area(
                        ST_Intersection(
                            ST_Buffer(c.geometry::geography, trade_area_radius_m)::geometry,
                            sc.geom
                        )::geography
                    ) / NULLIF(
                        ST_Area(ST_Buffer(c.geometry::geography, trade_area_radius_m)::geography),
                        0
                    ) * 100.0
                )::NUMERIC,
                2
            ) AS overlap_percentage
        FROM competitor_locations c, site_catchment sc
        WHERE (
            (spatial_predicate = 'ST_Contains' AND ST_Contains(sc.geom, c.geometry))
            OR
            (spatial_predicate = 'ST_Intersects' AND ST_Intersects(sc.geom, c.geometry))
        )
    ),
    own_estate AS (
        SELECT
            'own_estate'::TEXT AS location_type,
            o.id::TEXT AS id,
            o.name::TEXT AS name,
            NULL::TEXT AS category,
            o.current_trading_performance::NUMERIC AS current_trading_performance,
            ST_Y(o.geometry::geometry) AS latitude,
            ST_X(o.geometry::geometry) AS longitude,
            ST_Contains(sc.geom, o.geometry) AS is_contained,
            ST_Intersects(sc.geom, o.geometry) AS is_intersecting,
            ST_Distance(o.geometry::geography, ST_Centroid(sc.geom)::geography) AS distance_to_centroid_m,
            ROUND(
                (
                    ST_Area(
                        ST_Intersection(
                            ST_Buffer(o.geometry::geography, trade_area_radius_m)::geometry,
                            sc.geom
                        )::geography
                    ) / NULLIF(
                        ST_Area(ST_Buffer(o.geometry::geography, trade_area_radius_m)::geography),
                        0
                    ) * 100.0
                )::NUMERIC,
                2
            ) AS overlap_percentage
        FROM own_estate_locations o, site_catchment sc
        WHERE (
            (spatial_predicate = 'ST_Contains' AND ST_Contains(sc.geom, o.geometry))
            OR
            (spatial_predicate = 'ST_Intersects' AND ST_Intersects(sc.geom, o.geometry))
        )
    )
    SELECT * FROM competitors
    UNION ALL
    SELECT * FROM own_estate
    ORDER BY distance_to_centroid_m ASC;
END;
$$;
