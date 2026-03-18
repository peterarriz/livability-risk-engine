-- Livability Risk Engine: Chicago MVP schema
-- Run against a PostGIS-enabled PostgreSQL database.

-- Enable PostGIS if not already enabled.
CREATE EXTENSION IF NOT EXISTS postgis;

-- ---------------------------------------------------------------------------
-- Raw source tables
-- These preserve original source identifiers and fields for traceability.
-- Normalization to the canonical projects table happens separately.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS raw_building_permits (
    -- Internal surrogate key
    id                  SERIAL PRIMARY KEY,

    -- Source identifier from the Chicago Data Portal (stable across re-ingests)
    source_id           TEXT NOT NULL UNIQUE,

    -- Permit metadata
    permit_type         TEXT,
    work_description    TEXT,
    status              TEXT,

    -- Location fields as supplied by the source
    address             TEXT,
    zip_code            TEXT,
    community_area      TEXT,
    ward                INT,
    latitude            DOUBLE PRECISION,
    longitude           DOUBLE PRECISION,
    location_geom       GEOMETRY(Point, 4326),

    -- Date fields as supplied by the source
    issue_date          DATE,
    expiration_date     DATE,
    reported_cost       NUMERIC(14, 2),

    -- Ingest tracking
    source_updated_at   TIMESTAMPTZ,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS raw_building_permits_geom_idx
    ON raw_building_permits USING GIST (location_geom);

CREATE INDEX IF NOT EXISTS raw_building_permits_issue_date_idx
    ON raw_building_permits (issue_date);

CREATE INDEX IF NOT EXISTS raw_building_permits_source_updated_at_idx
    ON raw_building_permits (source_updated_at);


CREATE TABLE IF NOT EXISTS raw_street_closures (
    -- Internal surrogate key
    id                  SERIAL PRIMARY KEY,

    -- Source identifier (stable across re-ingests)
    source_id           TEXT NOT NULL UNIQUE,

    -- Closure metadata
    closure_type        TEXT,
    street_name         TEXT,
    work_description    TEXT,
    permit_type         TEXT,
    status              TEXT,

    -- Location fields as supplied by the source
    address             TEXT,
    zip_code            TEXT,
    community_area      TEXT,
    ward                INT,
    latitude            DOUBLE PRECISION,
    longitude           DOUBLE PRECISION,
    location_geom       GEOMETRY(Point, 4326),

    -- Date fields
    close_date          DATE,
    reopen_date         DATE,

    -- Ingest tracking
    source_updated_at   TIMESTAMPTZ,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS raw_street_closures_geom_idx
    ON raw_street_closures USING GIST (location_geom);

CREATE INDEX IF NOT EXISTS raw_street_closures_close_date_idx
    ON raw_street_closures (close_date);

CREATE INDEX IF NOT EXISTS raw_street_closures_reopen_date_idx
    ON raw_street_closures (reopen_date);
