-- data-086: city coverage registry and 50 expansion-city seed rows.
--
-- These rows are intentionally coverage metadata, not synthetic construction
-- projects. Each city below is repo-backed by an existing neighborhood/context
-- source and is not one of the currently configured permit/closure city feeds.

CREATE TABLE IF NOT EXISTS city_coverage (
    city_slug                    TEXT        PRIMARY KEY,
    city_name                    TEXT        NOT NULL,
    state_code                   TEXT        NOT NULL,
    country_code                 TEXT        NOT NULL DEFAULT 'US',
    coverage_status              TEXT        NOT NULL DEFAULT 'context_ready',
    evidence_quality             TEXT        NOT NULL DEFAULT 'contextual_only',
    disruption_signal_sources    TEXT[]      NOT NULL DEFAULT ARRAY[]::TEXT[],
    context_signal_sources       TEXT[]      NOT NULL DEFAULT ARRAY[]::TEXT[],
    neighborhood_source_key      TEXT,
    staging_file                 TEXT,
    simulation_sources           INT,
    simulation_generated_records INT,
    latest_month_score           INT,
    source_cadence               TEXT,
    coordinate_coverage          TEXT,
    normalization_fit            TEXT,
    caveats                      TEXT,
    added_at                     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                   TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT city_coverage_evidence_quality_check CHECK (
        evidence_quality IN ('strong', 'moderate', 'contextual_only', 'insufficient')
    ),
    CONSTRAINT city_coverage_status_check CHECK (
        coverage_status IN ('active', 'context_ready', 'planned', 'blocked')
    )
);

CREATE INDEX IF NOT EXISTS city_coverage_state_idx
    ON city_coverage (state_code, city_name);

CREATE INDEX IF NOT EXISTS city_coverage_evidence_quality_idx
    ON city_coverage (evidence_quality);

WITH seed (
    city_slug,
    city_name,
    state_code,
    neighborhood_source_key,
    staging_file,
    simulation_sources,
    simulation_generated_records,
    latest_month_score
) AS (
    VALUES
        ('cape_coral_fl', 'Cape Coral', 'FL', 'crime_cape_coral', 'data/raw/cape_coral_crime_trends.json', 1, 14, 29),
        ('chandler_az', 'Chandler', 'AZ', 'crime_chandler', 'data/raw/chandler_crime_trends.json', 1, 14, 25),
        ('durham_nc', 'Durham', 'NC', 'crime_durham', 'data/raw/durham_crime_trends.json', 1, 14, 25),
        ('indianapolis_in', 'Indianapolis', 'IN', 'crime_indianapolis', 'data/raw/indianapolis_crime_trends.json', 1, 14, 31),
        ('providence_ri', 'Providence', 'RI', 'crime_providence', 'data/raw/providence_crime_trends.json', 1, 14, 23),
        ('sacramento_ca', 'Sacramento', 'CA', 'crime_sacramento', 'data/raw/sacramento_crime_trends.json', 1, 14, 23),
        ('st_paul_mn', 'St. Paul', 'MN', 'crime_st_paul', 'data/raw/st_paul_crime_trends.json', 1, 14, 24),
        ('virginia_beach_va', 'Virginia Beach', 'VA', 'crime_virginia_beach', 'data/raw/virginia_beach_crime_trends.json', 1, 14, 29),
        ('akron_oh', 'Akron', 'OH', 'crime_akron', 'data/raw/akron_crime_trends.json', 1, 13, 29),
        ('atlanta_ga', 'Atlanta', 'GA', 'crime_atlanta', 'data/raw/atlanta_crime_trends.json', 1, 13, 27),
        ('birmingham_al', 'Birmingham', 'AL', 'crime_birmingham', 'data/raw/birmingham_crime_trends.json', 1, 13, 20),
        ('chattanooga_tn', 'Chattanooga', 'TN', 'crime_chattanooga', 'data/raw/chattanooga_crime_trends.json', 1, 13, 25),
        ('colorado_springs_co', 'Colorado Springs', 'CO', 'crime_colorado_springs', 'data/raw/colorado_springs_crime_trends.json', 1, 13, 24),
        ('gilbert_az', 'Gilbert', 'AZ', 'crime_gilbert', 'data/raw/gilbert_crime_trends.json', 1, 13, 25),
        ('jersey_city_nj', 'Jersey City', 'NJ', 'crime_jersey_city', 'data/raw/jersey_city_crime_trends.json', 1, 13, 26),
        ('memphis_tn', 'Memphis', 'TN', 'crime_memphis', 'data/raw/memphis_crime_trends.json', 1, 13, 29),
        ('miami_fl', 'Miami', 'FL', 'crime_miami', 'data/raw/miami_crime_trends.json', 1, 13, 25),
        ('oakland_ca', 'Oakland', 'CA', 'crime_oakland', 'data/raw/oakland_crime_trends.json', 1, 13, 22),
        ('omaha_ne', 'Omaha', 'NE', 'crime_omaha', 'data/raw/omaha_crime_trends.json', 1, 13, 24),
        ('orlando_fl', 'Orlando', 'FL', 'crime_orlando', 'data/raw/orlando_crime_trends.json', 1, 13, 27),
        ('pittsburgh_pa', 'Pittsburgh', 'PA', 'crime_pittsburgh', 'data/raw/pittsburgh_crime_trends.json', 1, 13, 28),
        ('albuquerque_nm', 'Albuquerque', 'NM', 'crime_albuquerque', 'data/raw/albuquerque_crime_trends.json', 1, 12, 30),
        ('arlington_tx', 'Arlington', 'TX', 'crime_arlington_tx', 'data/raw/arlington_tx_crime_trends.json', 1, 12, 29),
        ('aurora_co', 'Aurora', 'CO', 'crime_aurora', 'data/raw/aurora_crime_trends.json', 1, 12, 28),
        ('boise_id', 'Boise', 'ID', 'crime_boise', 'data/raw/boise_crime_trends.json', 1, 12, 29),
        ('cary_nc', 'Cary', 'NC', 'crime_cary', 'data/raw/cary_crime_trends.json', 1, 12, 24),
        ('cedar_park_tx', 'Cedar Park', 'TX', 'crime_cedar_park_tx', 'data/raw/cedar_park_tx_crime_trends.json', 1, 12, 27),
        ('cleveland_oh', 'Cleveland', 'OH', 'crime_cleveland', 'data/raw/cleveland_crime_trends.json', 1, 12, 29),
        ('dallas_tx', 'Dallas', 'TX', 'crime_dallas', 'data/raw/dallas_crime_trends.json', 1, 12, 29),
        ('el_paso_tx', 'El Paso', 'TX', 'crime_el_paso', 'data/raw/el_paso_crime_trends.json', 1, 12, 28),
        ('eugene_or', 'Eugene', 'OR', 'crime_eugene', 'data/raw/eugene_crime_trends.json', 1, 12, 21),
        ('fayetteville_nc', 'Fayetteville', 'NC', 'crime_fayetteville_nc', 'data/raw/fayetteville_nc_crime_trends.json', 1, 12, 20),
        ('fort_wayne_in', 'Fort Wayne', 'IN', 'crime_fort_wayne', 'data/raw/fort_wayne_crime_trends.json', 1, 12, 23),
        ('fresno_ca', 'Fresno', 'CA', 'crime_fresno', 'data/raw/fresno_crime_trends.json', 1, 12, 27),
        ('frisco_tx', 'Frisco', 'TX', 'crime_frisco_tx', 'data/raw/frisco_tx_crime_trends.json', 1, 12, 26),
        ('garland_tx', 'Garland', 'TX', 'crime_garland_tx', 'data/raw/garland_tx_crime_trends.json', 1, 12, 30),
        ('glendale_az', 'Glendale', 'AZ', 'crime_glendale_az', 'data/raw/glendale_az_crime_trends.json', 1, 12, 21),
        ('goodyear_az', 'Goodyear', 'AZ', 'crime_goodyear_az', 'data/raw/goodyear_az_crime_trends.json', 1, 12, 26),
        ('grand_rapids_mi', 'Grand Rapids', 'MI', 'crime_grand_rapids', 'data/raw/grand_rapids_crime_trends.json', 1, 12, 30),
        ('henderson_nv', 'Henderson', 'NV', 'crime_henderson', 'data/raw/henderson_crime_trends.json', 1, 12, 20),
        ('honolulu_hi', 'Honolulu', 'HI', 'crime_honolulu', 'data/raw/honolulu_crime_trends.json', 1, 12, 22),
        ('houston_tx', 'Houston', 'TX', 'crime_houston', 'data/raw/houston_crime_trends.json', 1, 12, 22),
        ('huntsville_al', 'Huntsville', 'AL', 'crime_huntsville', 'data/raw/huntsville_crime_trends.json', 1, 12, 30),
        ('jacksonville_fl', 'Jacksonville', 'FL', 'crime_jacksonville', 'data/raw/jacksonville_crime_trends.json', 1, 12, 31),
        ('knoxville_tn', 'Knoxville', 'TN', 'crime_knoxville', 'data/raw/knoxville_crime_trends.json', 1, 12, 26),
        ('laredo_tx', 'Laredo', 'TX', 'crime_laredo_tx', 'data/raw/laredo_tx_crime_trends.json', 1, 12, 29),
        ('lexington_ky', 'Lexington', 'KY', 'crime_lexington', 'data/raw/lexington_crime_trends.json', 1, 12, 20),
        ('lincoln_ne', 'Lincoln', 'NE', 'crime_lincoln', 'data/raw/lincoln_crime_trends.json', 1, 12, 22),
        ('long_beach_ca', 'Long Beach', 'CA', 'crime_long_beach', 'data/raw/long_beach_crime_trends.json', 1, 12, 26),
        ('lubbock_tx', 'Lubbock', 'TX', 'crime_lubbock_tx', 'data/raw/lubbock_tx_crime_trends.json', 1, 12, 25)
)
INSERT INTO city_coverage (
    city_slug,
    city_name,
    state_code,
    country_code,
    coverage_status,
    evidence_quality,
    disruption_signal_sources,
    context_signal_sources,
    neighborhood_source_key,
    staging_file,
    simulation_sources,
    simulation_generated_records,
    latest_month_score,
    source_cadence,
    coordinate_coverage,
    normalization_fit,
    caveats
)
SELECT
    city_slug,
    city_name,
    state_code,
    'US',
    'context_ready',
    'contextual_only',
    ARRAY[]::TEXT[],
    ARRAY['crime_trend']::TEXT[],
    neighborhood_source_key,
    staging_file,
    simulation_sources,
    simulation_generated_records,
    latest_month_score,
    'Repo-backed city-specific neighborhood/context ingest. Refresh cadence follows the corresponding crime trend source script and staging file freshness.',
    'Context source coverage is city/region-level. Address-level disruption confidence still depends on local permit, closure, or project feeds.',
    'Fits the neighborhood_quality loader as contextual evidence. No construction project rows are seeded by this registry entry.',
    'Use as contextual livability/evidence coverage only until a city-specific permit or closure feed is connected and validated.'
FROM seed
ON CONFLICT (city_slug) DO UPDATE SET
    city_name = EXCLUDED.city_name,
    state_code = EXCLUDED.state_code,
    country_code = EXCLUDED.country_code,
    coverage_status = EXCLUDED.coverage_status,
    evidence_quality = EXCLUDED.evidence_quality,
    disruption_signal_sources = EXCLUDED.disruption_signal_sources,
    context_signal_sources = EXCLUDED.context_signal_sources,
    neighborhood_source_key = EXCLUDED.neighborhood_source_key,
    staging_file = EXCLUDED.staging_file,
    simulation_sources = EXCLUDED.simulation_sources,
    simulation_generated_records = EXCLUDED.simulation_generated_records,
    latest_month_score = EXCLUDED.latest_month_score,
    source_cadence = EXCLUDED.source_cadence,
    coordinate_coverage = EXCLUDED.coordinate_coverage,
    normalization_fit = EXCLUDED.normalization_fit,
    caveats = EXCLUDED.caveats,
    updated_at = now();
