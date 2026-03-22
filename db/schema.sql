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

COMMENT ON TABLE reports IS
    'Saved score snapshots (data-021). Each row is a /score response stored '
    'so the user can share a persistent /report/<report_id> URL. '
    'score_json is the full API response payload.';


-- ---------------------------------------------------------------------------
-- Score alert watchlist  (data-030)
--
-- Users subscribe an email + score threshold to a Chicago address.
-- When the disruption score crosses that threshold, an entry is written to
-- alert_log (email delivery is stubbed for the MVP).
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS watchlist (
    id          BIGSERIAL   PRIMARY KEY,
    email       TEXT        NOT NULL,
    address     TEXT        NOT NULL,
    -- threshold is an integer disruption score (0–100).
    -- An alert fires when the live score meets or exceeds this value.
    threshold   INT         NOT NULL CHECK (threshold BETWEEN 0 AND 100),
    -- token is used for unsubscribe links so no auth is required.
    token       TEXT        NOT NULL UNIQUE DEFAULT encode(gen_random_bytes(32), 'hex'),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT watchlist_email_address_unique UNIQUE (email, address)
);

CREATE INDEX IF NOT EXISTS watchlist_email_idx
    ON watchlist (email);

CREATE INDEX IF NOT EXISTS watchlist_address_idx
    ON watchlist (address);

COMMENT ON TABLE watchlist IS
    'Email alert subscriptions (data-030). Each row subscribes an email address '
    'to score alerts for a Chicago address when the disruption score crosses threshold. '
    'token is used in unsubscribe links.';

COMMENT ON COLUMN watchlist.threshold IS
    'Disruption score (0–100). An alert is triggered when the live score is >= this value.';

COMMENT ON COLUMN watchlist.token IS
    'Unsubscribe token — included in alert emails so users can opt out without auth.';


CREATE TABLE IF NOT EXISTS alert_log (
    id              BIGSERIAL   PRIMARY KEY,
    watchlist_id    BIGINT      NOT NULL REFERENCES watchlist(id) ON DELETE CASCADE,
    score           INT         NOT NULL,
    triggered_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS alert_log_watchlist_id_idx
    ON alert_log (watchlist_id);

CREATE INDEX IF NOT EXISTS alert_log_triggered_at_idx
    ON alert_log (triggered_at DESC);

COMMENT ON TABLE api_keys IS
    'Hashed API keys for optional /score access gating (data-027). '
    'Keys are only enforced when REQUIRE_API_KEY=true. '
    'Full key is never stored — only the SHA-256 hash.';


-- ---------------------------------------------------------------------------
-- Score alert watchlist  (data-030)
--
-- Users subscribe to score alerts for a specific address + email.
-- When the disruption score crosses threshold_score, an entry is written
-- to alert_log. Actual email delivery requires SMTP configuration.
-- Unsubscribe via GET /watch/unsubscribe?token=<token>.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS watchlist (
    id              BIGSERIAL   PRIMARY KEY,
    address         TEXT        NOT NULL,
    email           TEXT        NOT NULL,
    token           UUID        NOT NULL DEFAULT gen_random_uuid(),
    threshold_score INT         NOT NULL DEFAULT 50,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_active       BOOLEAN     NOT NULL DEFAULT true,

    CONSTRAINT watchlist_email_address_unique UNIQUE (email, address)
);

CREATE INDEX IF NOT EXISTS watchlist_token_idx ON watchlist (token);
CREATE INDEX IF NOT EXISTS watchlist_active_idx ON watchlist (is_active, address);

COMMENT ON TABLE watchlist IS
    'Score alert subscriptions (data-030). Subscribe by email + address. '
    'When disruption_score >= threshold_score an alert_log row is written. '
    'Unsubscribe via GET /watch/unsubscribe?token=<uuid>.';


CREATE TABLE IF NOT EXISTS alert_log (
    id              BIGSERIAL   PRIMARY KEY,
    watchlist_id    BIGINT      NOT NULL REFERENCES watchlist(id),
    disruption_score INT        NOT NULL,
    triggered_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS alert_log_watchlist_idx
    ON alert_log (watchlist_id, triggered_at DESC);

COMMENT ON TABLE alert_log IS
    'Records of triggered score alerts (data-030). One row per alert check '
    'that crossed the threshold. Used to prevent duplicate alerts and track '
    'notification history.';


-- ---------------------------------------------------------------------------
-- Neighborhood quality reference layer  (data-040)
--
-- Stores neighborhood-level context data from three sources:
--   1. FEMA NFHL flood zone designations (region_type = 'flood_zone')
--   2. Chicago community-area crime trends (region_type = 'community_area')
--   3. Census ACS 5-year demographics   (region_type = 'census_tract')
--
-- Each row has a geom (centroid point) for KNN spatial lookup.
-- At /score request time, the nearest record of each region_type is returned
-- as the neighborhood_context field in the API response.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS neighborhood_quality (
    id              BIGSERIAL   PRIMARY KEY,

    -- Geographic region identifier
    region_type     TEXT        NOT NULL,   -- 'flood_zone' | 'community_area' | 'census_tract'
    region_id       TEXT        NOT NULL,   -- stable unique ID per region_type

    -- FEMA flood data (populated for region_type = 'flood_zone')
    fema_flood_zone TEXT,                   -- 'A', 'AE', 'X', 'X500', 'VE', etc.
    flood_risk      TEXT,                   -- 'HIGH', 'MODERATE', 'MINIMAL', 'UNKNOWN'

    -- Crime trend data (populated for region_type = 'community_area')
    crime_12mo      INT,                    -- total crimes in last 12 months
    crime_prior_12mo INT,                   -- total crimes in prior 12 months
    crime_trend     TEXT,                   -- 'INCREASING', 'DECREASING', 'STABLE'
    crime_trend_pct NUMERIC(6, 1),          -- percentage change vs prior period

    -- Census ACS demographics (populated for region_type = 'census_tract')
    median_income   INT,                    -- median household income (dollars)
    population      INT,                    -- total population
    vacancy_rate    NUMERIC(5, 2),          -- % of housing units that are vacant
    housing_age_med INT,                    -- median year structure built

    -- Spatial centroid for KNN proximity lookup
    geom            GEOMETRY(Point, 4326),

    -- Audit
    data_year       INT,
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT nq_region_unique UNIQUE (region_type, region_id)
);

-- Partial spatial indexes per region_type for efficient KNN queries
-- in get_neighborhood_context() in backend/scoring/query.py.
CREATE INDEX IF NOT EXISTS nq_geom_flood_idx
    ON neighborhood_quality USING GIST (geom)
    WHERE region_type = 'flood_zone' AND geom IS NOT NULL;

CREATE INDEX IF NOT EXISTS nq_geom_crime_idx
    ON neighborhood_quality USING GIST (geom)
    WHERE region_type = 'community_area' AND geom IS NOT NULL;

CREATE INDEX IF NOT EXISTS nq_geom_census_idx
    ON neighborhood_quality USING GIST (geom)
    WHERE region_type = 'census_tract' AND geom IS NOT NULL;

CREATE INDEX IF NOT EXISTS nq_region_type_idx
    ON neighborhood_quality (region_type);

COMMENT ON TABLE neighborhood_quality IS
    'Neighborhood quality reference layer (data-040). '
    'Three region_type values: flood_zone (FEMA NFHL), community_area (Chicago crime), '
    'census_tract (Census ACS). KNN spatial lookup via geom column. '
    'Surfaced in /score response as neighborhood_context field.';


-- ---------------------------------------------------------------------------
-- Signal rewrites cache  (data-042)
--
-- Stores Claude API-generated titles and descriptions for each unique project.
-- Keyed on project_id (source:source_id) so each permit/closure is rewritten
-- at most once, regardless of how many /score requests reference it.
-- Populated lazily on the first /score request that references each project_id.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS signal_rewrites (
    project_id            TEXT        PRIMARY KEY,
    rewritten_title       TEXT        NOT NULL,
    rewritten_description TEXT        NOT NULL,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE signal_rewrites IS
    'Claude API-generated clean titles and descriptions for each project signal (data-042). '
    'Cache keyed on project_id. Populated lazily on the first /score request '
    'that references each project. Prevents repeated API calls for the same permit.';
