-- db/schema.sql
-- tasks: data-002, data-004, data-005
-- lane: data
--
-- Full database schema for the Chicago MVP.
-- Includes raw staging tables (data-002, data-004) and the
-- canonical projects table (data-005) used by the scoring engine.
--
-- Conventions:
--   - Raw tables hold unmodified source records. Never score from raw tables.
--   - The canonical `projects` table is the single source of truth for scoring.
--   - All distance/geospatial queries run against `projects`, not raw tables.
--   - source_id + source columns provide a stable traceable link back to origin.
--   - Schema changes require App lane review (docs/06_team_working_agreement.md).

-- ---------------------------------------------------------------------------
-- Extensions
-- ---------------------------------------------------------------------------

CREATE EXTENSION IF NOT EXISTS postgis;


-- ---------------------------------------------------------------------------
-- Raw building permits  (data-002)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS raw_building_permits (
    id                     BIGSERIAL PRIMARY KEY,
    source_id              TEXT        NOT NULL,   -- permit_ field from Socrata
    permit_type            TEXT,
    work_description       TEXT,
    street_number          TEXT,
    street_direction       TEXT,
    street_name            TEXT,
    suffix                 TEXT,
    issue_date             DATE,
    expiration_date        DATE,
    application_start_date DATE,
    latitude               DOUBLE PRECISION,
    longitude              DOUBLE PRECISION,
    reported_cost          TEXT,
    raw_json               JSONB       NOT NULL,
    ingested_at            TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT raw_building_permits_source_id_unique UNIQUE (source_id)
);

CREATE INDEX IF NOT EXISTS raw_building_permits_issue_date_idx
    ON raw_building_permits (issue_date DESC);

CREATE INDEX IF NOT EXISTS raw_building_permits_location_idx
    ON raw_building_permits (latitude, longitude)
    WHERE latitude IS NOT NULL AND longitude IS NOT NULL;

COMMENT ON TABLE raw_building_permits IS
    'Raw Chicago building permit records from the Socrata API (data-002). '
    'Feed into canonical projects table via data-006 normalization script.';

COMMENT ON COLUMN raw_building_permits.source_id IS
    'Original permit_ identifier from the City of Chicago data portal.';


-- ---------------------------------------------------------------------------
-- Raw street closures  (data-004)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS raw_street_closures (
    id               BIGSERIAL PRIMARY KEY,
    source_id        TEXT        NOT NULL,   -- row_id from Socrata
    work_type        TEXT,
    street_closure_type TEXT,
    closure_reason   TEXT,
    status           TEXT,
    street_name      TEXT,
    from_street      TEXT,
    to_street        TEXT,
    street_direction TEXT,
    start_date       DATE,
    end_date         DATE,
    latitude         DOUBLE PRECISION,
    longitude        DOUBLE PRECISION,
    permit_number    TEXT,
    raw_json         JSONB       NOT NULL,
    ingested_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT raw_street_closures_source_id_unique UNIQUE (source_id)
);

CREATE INDEX IF NOT EXISTS raw_street_closures_start_date_idx
    ON raw_street_closures (start_date DESC);

CREATE INDEX IF NOT EXISTS raw_street_closures_end_date_idx
    ON raw_street_closures (end_date DESC);

CREATE INDEX IF NOT EXISTS raw_street_closures_location_idx
    ON raw_street_closures (latitude, longitude)
    WHERE latitude IS NOT NULL AND longitude IS NOT NULL;

COMMENT ON TABLE raw_street_closures IS
    'Raw Chicago CDOT street closure records from the Socrata API (data-004). '
    'Street closures are the highest-weight input to the scoring model. '
    'Feed into canonical projects table via data-007 normalization script.';


-- ---------------------------------------------------------------------------
-- Canonical projects table  (data-005)
--
-- This is the single table the scoring engine reads from. Every source
-- (building permits, street closures, future sources) normalizes into
-- this shape. The scoring query (data-009) runs ST_DWithin against
-- the `geom` column.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS projects (
    -- Identity
    id              BIGSERIAL   PRIMARY KEY,
    project_id      TEXT        NOT NULL,   -- stable display ID: source:source_id
    source          TEXT        NOT NULL,   -- 'chicago_permits' | 'chicago_closures'
    source_id       TEXT        NOT NULL,   -- original record key from source

    -- Classification (aligns with docs/03_scoring_model.md taxonomy)
    -- impact_type drives base weight assignment in the scoring engine.
    impact_type     TEXT        NOT NULL,   -- 'closure_full' | 'closure_multi_lane' |
                                            -- 'closure_single_lane' | 'demolition' |
                                            -- 'construction' | 'light_permit'
    title           TEXT        NOT NULL,   -- short human-readable description
    notes           TEXT,                   -- additional context for top_risks display

    -- Timing
    start_date      DATE,
    end_date        DATE,
    status          TEXT        NOT NULL DEFAULT 'active',
                                            -- 'active' | 'planned' | 'completed' | 'unknown'

    -- Location
    address         TEXT,                   -- normalized address string
    latitude        DOUBLE PRECISION,
    longitude       DOUBLE PRECISION,
    geom            GEOMETRY(Point, 4326),  -- PostGIS point; used for radius queries

    -- Scoring metadata (populated by normalization; not changed by scoring engine)
    -- severity_hint is a pre-computed signal for the scoring engine to use as
    -- a starting point; the engine may override based on distance/timing.
    severity_hint   TEXT,                   -- 'HIGH' | 'MEDIUM' | 'LOW'

    -- Audit
    normalized_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT projects_source_source_id_unique UNIQUE (source, source_id)
);

-- Spatial index — the core index for radius queries in data-009.
-- ST_DWithin on geom is the primary scoring query pattern.
CREATE INDEX IF NOT EXISTS projects_geom_idx
    ON projects USING GIST (geom)
    WHERE geom IS NOT NULL;

-- Date indexes for timing multiplier lookups.
CREATE INDEX IF NOT EXISTS projects_start_date_idx
    ON projects (start_date DESC)
    WHERE start_date IS NOT NULL;

CREATE INDEX IF NOT EXISTS projects_end_date_idx
    ON projects (end_date DESC)
    WHERE end_date IS NOT NULL;

-- Status index for filtering inactive records out of scoring queries.
CREATE INDEX IF NOT EXISTS projects_status_idx
    ON projects (status);

-- Source traceability index.
CREATE INDEX IF NOT EXISTS projects_source_idx
    ON projects (source, source_id);

COMMENT ON TABLE projects IS
    'Canonical normalized project table (data-005). '
    'All scoring queries run against this table. '
    'Raw source records are preserved in raw_building_permits and raw_street_closures. '
    'Schema changes require Data + App review per docs/06_team_working_agreement.md.';

COMMENT ON COLUMN projects.project_id IS
    'Stable human-readable ID in the format source:source_id. '
    'Used in API top_risks strings and for frontend display.';

COMMENT ON COLUMN projects.impact_type IS
    'Normalized impact classification aligned with the base weight table '
    'in docs/03_scoring_model.md. Drives scoring engine weight assignment. '
    'Valid values: closure_full, closure_multi_lane, closure_single_lane, '
    'demolition, construction, light_permit.';

COMMENT ON COLUMN projects.geom IS
    'PostGIS Point geometry in WGS84 (SRID 4326). '
    'Primary index for ST_DWithin radius queries in the scoring engine.';

COMMENT ON COLUMN projects.severity_hint IS
    'Pre-computed severity hint from normalization. '
    'The scoring engine uses this as a starting point but derives final '
    'severity from the weighted contributions across all nearby projects.';


-- ---------------------------------------------------------------------------
-- Ingestion run log
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS ingest_runs (
    id           BIGSERIAL PRIMARY KEY,
    source       TEXT        NOT NULL,
    started_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at  TIMESTAMPTZ,
    record_count INT,
    status       TEXT        NOT NULL DEFAULT 'running',
    error_msg    TEXT
);

COMMENT ON TABLE ingest_runs IS
    'Tracks each ingestion run for freshness checks (data-010).';


-- ---------------------------------------------------------------------------
-- Score history  (data-025)
--
-- Persists each live /score result so the frontend can surface a sparkline
-- trend showing whether an address is getting better or worse over time.
-- Only live-mode scores are written (demo-mode results are excluded).
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS score_history (
    id               BIGSERIAL   PRIMARY KEY,
    address          TEXT        NOT NULL,
    disruption_score INT         NOT NULL,
    confidence       TEXT        NOT NULL,
    mode             TEXT        NOT NULL DEFAULT 'live',
    scored_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS score_history_address_scored_at_idx
    ON score_history (address, scored_at DESC);

COMMENT ON TABLE score_history IS
    'Records each live /score result for trend analysis (data-025). '
    'Populated by fire-and-forget background writes in the /score endpoint. '
    'Demo-mode scores are excluded. Query via GET /history?address=&limit=.';
