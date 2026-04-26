-- db/schema.sql
-- tasks: data-002, data-004, data-005
-- lane: data
--
-- Full database schema for the Livability Risk Engine.
-- Includes raw staging tables (data-002, data-004) and the
-- canonical projects table (data-005) used by the scoring engine.
--
-- Conventions:
--   - Raw tables hold unmodified source records. Never score from raw tables.
--   - The canonical `projects` table is the single source of truth for scoring.
--   - Project radius queries use lat/lon; neighborhood context uses PostGIS KNN.
--   - source_id + source columns provide a stable traceable link back to origin.
--   - Schema changes require App lane review (docs/06_team_working_agreement.md).

-- ---------------------------------------------------------------------------
-- Extensions
-- ---------------------------------------------------------------------------

-- pgcrypto supports generated UUIDs and opaque tokens.
-- PostGIS is required for neighborhood_quality geospatial context/KNN scoring.
CREATE EXTENSION IF NOT EXISTS pgcrypto;
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
-- this shape. Project radius scoring currently uses lat/lon filtering;
-- neighborhood_quality context uses PostGIS separately.
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
    -- Projects do not currently store geom; radius queries use haversine
    -- lat/lon math. PostGIS remains required by neighborhood_quality.

    -- Scoring metadata (populated by normalization; not changed by scoring engine)
    -- severity_hint is a pre-computed signal for the scoring engine to use as
    -- a starting point; the engine may override based on distance/timing.
    severity_hint   TEXT,                   -- 'HIGH' | 'MEDIUM' | 'LOW'

    -- Audit
    normalized_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT projects_source_source_id_unique UNIQUE (source, source_id)
);

-- Lat/lon composite index: used for bounding-box pre-filter in project queries.
CREATE INDEX IF NOT EXISTS projects_location_idx
    ON projects (latitude, longitude)
    WHERE latitude IS NOT NULL AND longitude IS NOT NULL;

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
    'Canonical normalized project table (data-005, updated data-038). '
    'Project radius scoring uses haversine lat/lon math against this table. '
    'PostGIS remains required for neighborhood_quality geospatial context. '
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
    livability_score INT         NOT NULL DEFAULT 0,
    livability_breakdown JSONB   NOT NULL DEFAULT '{}'::jsonb,
    confidence       TEXT        NOT NULL,
    mode             TEXT        NOT NULL DEFAULT 'live',
    batch_id         UUID,
    scored_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE score_history
    ADD COLUMN IF NOT EXISTS livability_score INT NOT NULL DEFAULT 0;
ALTER TABLE score_history
    ADD COLUMN IF NOT EXISTS livability_breakdown JSONB NOT NULL DEFAULT '{}'::jsonb;
-- data-062: lat/lon for geographic aggregation in /score-trend
ALTER TABLE score_history
    ADD COLUMN IF NOT EXISTS latitude  DOUBLE PRECISION;
ALTER TABLE score_history
    ADD COLUMN IF NOT EXISTS longitude DOUBLE PRECISION;
ALTER TABLE score_history
    ADD COLUMN IF NOT EXISTS batch_id UUID;

CREATE INDEX IF NOT EXISTS score_history_address_scored_at_idx
    ON score_history (address, scored_at DESC);
CREATE INDEX IF NOT EXISTS score_history_latlon_idx
    ON score_history (latitude, longitude)
    WHERE latitude IS NOT NULL AND longitude IS NOT NULL;
CREATE INDEX IF NOT EXISTS score_history_batch_id_idx
    ON score_history (batch_id)
    WHERE batch_id IS NOT NULL;

COMMENT ON TABLE score_history IS
    'Saved score snapshots per address (data-025). Each row is a /score response '
    'stored so the frontend can render a sparkline trend over time. '
    'Only live-mode scores are written.';


-- ---------------------------------------------------------------------------
-- Saved reports
--
-- Stores shareable score reports created by POST /save and read by
-- GET /report/{report_id}. score_json stores the full score response payload.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS reports (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    address    TEXT        NOT NULL,
    score_json JSONB       NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS reports_created_at_idx
    ON reports (created_at DESC);

CREATE INDEX IF NOT EXISTS reports_address_created_at_idx
    ON reports (address, created_at DESC);

CREATE INDEX IF NOT EXISTS reports_account_id_idx
    ON reports ((score_json->>'account_id'))
    WHERE score_json ? 'account_id';

COMMENT ON TABLE reports IS
    'Shareable saved score reports created by POST /save and read by GET /report/{report_id}.';


-- ---------------------------------------------------------------------------
-- Score request analytics
--
-- Best-effort request telemetry written by /score. Adopted from
-- db/migrations/add_score_requests.sql so fresh DB bootstraps include it.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS score_requests (
    id                  SERIAL PRIMARY KEY,
    address             TEXT NOT NULL,
    city                TEXT,
    state               TEXT,
    latitude            DOUBLE PRECISION,
    longitude           DOUBLE PRECISION,
    livability_score    INTEGER,
    evidence_quality    TEXT,
    strong_signal_count INTEGER,
    error               TEXT,
    response_time_ms    INTEGER,
    user_id             TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_score_requests_created
    ON score_requests (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_score_requests_city
    ON score_requests (city);

COMMENT ON TABLE score_requests IS
    'Best-effort /score request telemetry used for lightweight usage and error statistics.';


-- ---------------------------------------------------------------------------
-- Amenity richness cache  (data-064)
--
-- Caches OSM Overpass API results keyed on a 0.01° lat/lon bucket
-- (~800 m grid square at Chicago's latitude).  TTL = 7 days.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS amenity_cache (
    id            BIGSERIAL   PRIMARY KEY,
    lat_bucket    NUMERIC(6,2) NOT NULL,   -- round(lat, 2)
    lon_bucket    NUMERIC(6,2) NOT NULL,   -- round(lon, 2)
    amenities     JSONB        NOT NULL DEFAULT '[]',
    amenity_score INT          NOT NULL DEFAULT 0,
    fetched_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS amenity_cache_bucket_idx
    ON amenity_cache (lat_bucket, lon_bucket);

COMMENT ON TABLE amenity_cache IS
    'Cached OSM Overpass amenity results per 0.01° grid cell (data-064). '
    'Rows older than 7 days are treated as stale and re-fetched on next request.';


-- ---------------------------------------------------------------------------
-- Score alert watchlist  (data-030)
--
-- Users subscribe an email + score threshold to an address.
-- When the disruption score crosses that threshold, an entry is written to
-- alert_log (email delivery is stubbed for the MVP).
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS watchlist (
    id              BIGSERIAL   PRIMARY KEY,
    address         TEXT        NOT NULL,
    email           TEXT        NOT NULL,
    token           TEXT        NOT NULL DEFAULT encode(gen_random_bytes(32), 'hex'),
    threshold_score INT         NOT NULL DEFAULT 50,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_active       BOOLEAN     NOT NULL DEFAULT true,

    CONSTRAINT watchlist_email_address_unique UNIQUE (email, address)
);

-- Existing deployments created token as UUID. The backend now stores
-- secrets.token_hex(32), which is 64 hex characters and must be TEXT.
ALTER TABLE watchlist
    ALTER COLUMN token DROP DEFAULT,
    ALTER COLUMN token TYPE TEXT USING token::text,
    ALTER COLUMN token SET DEFAULT encode(gen_random_bytes(32), 'hex');

CREATE INDEX IF NOT EXISTS watchlist_token_idx ON watchlist (token);
CREATE INDEX IF NOT EXISTS watchlist_active_idx ON watchlist (is_active, address);
CREATE INDEX IF NOT EXISTS watchlist_email_idx ON watchlist (email);
CREATE INDEX IF NOT EXISTS watchlist_address_idx ON watchlist (address);

COMMENT ON TABLE watchlist IS
    'Score alert subscriptions (data-030). Subscribe by email + address. '
    'When disruption_score >= threshold_score an alert_log row is written. '
    'Unsubscribe via GET /watch/unsubscribe?token=<opaque-token>.';

COMMENT ON COLUMN watchlist.threshold_score IS
    'Disruption score (0–100). An alert is triggered when the live score is >= this value.';

COMMENT ON COLUMN watchlist.token IS
    'Opaque unsubscribe token included in alert emails so users can opt out without auth.';


CREATE TABLE IF NOT EXISTS alert_log (
    id               BIGSERIAL   PRIMARY KEY,
    watchlist_id     BIGINT      NOT NULL REFERENCES watchlist(id) ON DELETE CASCADE,
    disruption_score INT         NOT NULL,
    triggered_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS alert_log_watchlist_idx
    ON alert_log (watchlist_id, triggered_at DESC);

CREATE INDEX IF NOT EXISTS alert_log_triggered_at_idx
    ON alert_log (triggered_at DESC);

COMMENT ON TABLE alert_log IS
    'Records of triggered score alerts (data-030). One row per alert check '
    'that crossed the threshold. Used to prevent duplicate alerts and track '
    'notification history.';


-- ---------------------------------------------------------------------------
-- Clerk users  (app-024)
--
-- Minimal user record created on first Clerk sign-in via POST /auth/sync.
-- id is the Clerk user_id string (e.g. "user_2abc...").
-- subscription_tier defaults to 'free'; upgrade logic is a future task.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS users (
    id                TEXT        PRIMARY KEY,  -- Clerk user_id
    email             TEXT        NOT NULL,
    subscription_tier TEXT        NOT NULL DEFAULT 'free',
    created_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS users_email_idx ON users (email);

COMMENT ON TABLE users IS
    'Clerk-authenticated user records (app-024). One row per user, created on '
    'first sign-in via POST /auth/sync. id is the Clerk userId string.';


-- ---------------------------------------------------------------------------
-- API keys  (data-027, metering added data-043)
--
-- Stores hashed API keys for /score authentication (opt-in via REQUIRE_API_KEY).
-- call_count and last_called_at are updated on every authenticated /score call
-- so operators can meter usage for billing (see docs/pricing_model.md).
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS api_keys (
    id            BIGSERIAL   PRIMARY KEY,
    prefix        TEXT        NOT NULL,   -- first 8 hex chars of random portion
    key_hash      TEXT        NOT NULL,   -- sha256(full_key)
    label         TEXT        NOT NULL DEFAULT '',
    is_active     BOOLEAN     NOT NULL DEFAULT true,
    call_count    INT         NOT NULL DEFAULT 0,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at  TIMESTAMPTZ,
    last_called_at TIMESTAMPTZ,

    CONSTRAINT api_keys_prefix_unique UNIQUE (prefix)
);

CREATE INDEX IF NOT EXISTS api_keys_prefix_idx ON api_keys (prefix);
CREATE INDEX IF NOT EXISTS api_keys_active_idx ON api_keys (is_active);

COMMENT ON TABLE api_keys IS
    'Hashed API keys for /score authentication (data-027). '
    'call_count incremented on each authenticated call for usage metering (data-043).';

-- Idempotent migration: add metering columns to existing deployments that
-- have api_keys without them (created before data-043).
ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS call_count     INT         NOT NULL DEFAULT 0;
ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS last_called_at TIMESTAMPTZ;

-- app-025: link API keys to Clerk users.
ALTER TABLE api_keys
    ADD COLUMN IF NOT EXISTS user_id TEXT REFERENCES users(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS api_keys_user_id_idx
    ON api_keys (user_id)
    WHERE user_id IS NOT NULL;


-- ---------------------------------------------------------------------------
-- Signal display cache  (data-043)
--
-- Caches generated human-readable display fields for project signals.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS signal_display (
    project_id     TEXT        PRIMARY KEY,
    display_title  TEXT        NOT NULL,
    distance       TEXT        NOT NULL,
    description    TEXT        NOT NULL,
    why_it_matters TEXT        NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE signal_display IS
    'Claude API-generated 4-field display cards for each project signal (data-043). '
    'Keyed on project_id. Populated lazily on the first /score request that references '
    'each project. Falls back to Option A deterministic formatter on API failure. '
    'Supersedes signal_rewrites with richer display_title, distance, description, '
    'and why_it_matters fields.';


-- ---------------------------------------------------------------------------
-- User accounts  (data-045)
--
-- Stores registered user accounts. Supports two auth methods:
--   1. Email + password (password_hash populated, google_id NULL)
--   2. Google OAuth     (google_id populated, password_hash NULL)
--   3. Both             (user linked email account then connected Google)
--
-- watchlist and score_history rows may optionally reference an account_id
-- so saved data can be associated with a user across sessions.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS accounts (
    id              BIGSERIAL   PRIMARY KEY,
    email           TEXT        NOT NULL UNIQUE,
    password_hash   TEXT,                       -- NULL for OAuth-only users
    google_id       TEXT        UNIQUE,          -- NULL for email/password users
    display_name    TEXT,
    email_verified  BOOLEAN     NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at   TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS accounts_email_idx    ON accounts (email);
CREATE INDEX IF NOT EXISTS accounts_google_id_idx ON accounts (google_id) WHERE google_id IS NOT NULL;

COMMENT ON TABLE accounts IS
    'Registered user accounts (data-045). Supports email+password and Google OAuth. '
    'password_hash uses bcrypt. google_id is the Google sub claim. '
    'Linked from watchlist and score_history via account_id FK.';

-- Add nullable account_id FK to watchlist so saved alerts can be owned by a user.
-- NULL = legacy anonymous entry (backward compatible).
ALTER TABLE watchlist
    ADD COLUMN IF NOT EXISTS account_id BIGINT REFERENCES accounts(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS watchlist_account_idx ON watchlist (account_id) WHERE account_id IS NOT NULL;

-- Add nullable account_id FK to score_history so score lookups can be tied to a user.
ALTER TABLE score_history
    ADD COLUMN IF NOT EXISTS account_id BIGINT REFERENCES accounts(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS score_history_account_idx ON score_history (account_id) WHERE account_id IS NOT NULL;


-- ---------------------------------------------------------------------------
-- Neighborhood quality  (data-040)
--
-- Stores neighborhood-level context used by the livability scoring engine:
-- FEMA flood zones, crime trends, Census ACS demographics, and school
-- ratings.  Each row is keyed on (region_type, region_id).
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS neighborhood_quality (
    id               BIGSERIAL    PRIMARY KEY,
    region_type      TEXT         NOT NULL,      -- 'flood_zone' | 'community_area' | 'census_tract' | 'school'
    region_id        TEXT         NOT NULL,

    -- Flood
    fema_flood_zone  TEXT,
    flood_risk       TEXT,

    -- Crime
    crime_12mo       NUMERIC(10,1),
    crime_prior_12mo NUMERIC(10,1),
    crime_trend      TEXT,
    crime_trend_pct  NUMERIC(10,1),

    -- Census ACS demographics
    median_income    NUMERIC(12,2),
    population       INT,
    vacancy_rate     NUMERIC(5,2),
    housing_age_med  INT,

    -- Schools
    school_name      TEXT,
    school_rating    TEXT,
    school_attainment TEXT,
    school_growth    TEXT,

    -- FHFA House Price Index (data-081)
    hpi_index_value  NUMERIC(10,2),    -- most recent quarter index value (NSA)
    hpi_1yr_change   NUMERIC(8,4),     -- 1-year price change (%)
    hpi_5yr_change   NUMERIC(8,4),     -- 5-year price change (%)
    hpi_10yr_change  NUMERIC(8,4),     -- 10-year price change (%)
    hpi_period       TEXT,             -- data period, e.g. '2024Q3'

    -- Location
    latitude         DOUBLE PRECISION,
    longitude        DOUBLE PRECISION,
    geom             GEOMETRY(Point, 4326),

    data_year        INT,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT neighborhood_quality_region_unique UNIQUE (region_type, region_id)
);

CREATE INDEX IF NOT EXISTS neighborhood_quality_region_type_idx
    ON neighborhood_quality (region_type);

CREATE INDEX IF NOT EXISTS neighborhood_quality_geom_idx
    ON neighborhood_quality USING GIST (geom)
    WHERE geom IS NOT NULL;

CREATE INDEX IF NOT EXISTS neighborhood_quality_latlon_idx
    ON neighborhood_quality (latitude, longitude)
    WHERE latitude IS NOT NULL AND longitude IS NOT NULL;

COMMENT ON TABLE neighborhood_quality IS
    'Neighborhood-level context for livability scoring (data-040). '
    'Stores FEMA flood zones, crime trends, Census ACS demographics, '
    'school ratings, and FHFA HPI data keyed on (region_type, region_id).';

-- data-081: idempotent migrations for HPI columns on existing deployments
ALTER TABLE neighborhood_quality ADD COLUMN IF NOT EXISTS hpi_index_value NUMERIC(10,2);
ALTER TABLE neighborhood_quality ADD COLUMN IF NOT EXISTS hpi_1yr_change  NUMERIC(8,4);
ALTER TABLE neighborhood_quality ADD COLUMN IF NOT EXISTS hpi_5yr_change  NUMERIC(8,4);
ALTER TABLE neighborhood_quality ADD COLUMN IF NOT EXISTS hpi_10yr_change NUMERIC(8,4);
ALTER TABLE neighborhood_quality ADD COLUMN IF NOT EXISTS hpi_period      TEXT;


-- ---------------------------------------------------------------------------
-- Row Level Security  (data-067)
--
-- Preserve RLS and public SELECT policies for backend-owned data tables, but
-- do not FORCE RLS here. Backend writes are expected to run through a
-- backend-owned table owner or privileged DB role; explicit user-scoped write
-- policies are deferred to a later RLS policy PR.
-- SELECT policy creation is guarded so schema.sql can be applied repeatedly.
-- ---------------------------------------------------------------------------

DO $$
DECLARE
    target_table TEXT;
BEGIN
    FOREACH target_table IN ARRAY ARRAY[
        'raw_building_permits',
        'raw_street_closures',
        'projects',
        'ingest_runs',
        'score_history',
        'amenity_cache',
        'watchlist',
        'alert_log',
        'users',
        'api_keys',
        'accounts',
        'neighborhood_quality'
    ]
    LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', target_table);
        EXECUTE format('ALTER TABLE public.%I NO FORCE ROW LEVEL SECURITY', target_table);

        IF NOT EXISTS (
            SELECT 1
            FROM pg_policies
            WHERE schemaname = 'public'
              AND tablename = target_table
              AND policyname = 'select_' || target_table
        ) THEN
            EXECUTE format(
                'CREATE POLICY %I ON public.%I FOR SELECT USING (true)',
                'select_' || target_table,
                target_table
            );
        END IF;
    END LOOP;
END $$;
