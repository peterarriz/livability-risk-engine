-- db/migrate_rls.sql
-- task: data-067
--
-- Idempotent migration: enable Row Level Security on backend-owned data
-- tables and add a public SELECT policy to each. Do not FORCE RLS here:
-- backend writes are expected to run through a backend-owned table owner or
-- privileged DB role. Explicit user-scoped write policies are deferred to a
-- later RLS policy PR.
--
-- Usage:
--   psql "$DATABASE_URL" -f db/migrate_rls.sql
--
-- Safe to re-run: DROP POLICY IF EXISTS ensures idempotency.

BEGIN;

DO $$
DECLARE
    t TEXT;
    tables TEXT[] := ARRAY[
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
        'signal_display',
        'neighborhood_quality'
    ];
BEGIN
    FOREACH t IN ARRAY tables LOOP
        -- Skip tables that don't exist (e.g. signal_display may be absent)
        IF EXISTS (
            SELECT 1 FROM pg_tables
            WHERE schemaname = 'public' AND tablename = t
        ) THEN
            EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
            EXECUTE format('ALTER TABLE %I NO FORCE ROW LEVEL SECURITY', t);
            EXECUTE format('DROP POLICY IF EXISTS select_%I ON %I', t, t);
            EXECUTE format(
                'CREATE POLICY select_%I ON %I FOR SELECT USING (true)', t, t
            );
            RAISE NOTICE 'RLS enabled, FORCE RLS disabled on %', t;
        ELSE
            RAISE NOTICE 'Skipping % (table does not exist)', t;
        END IF;
    END LOOP;
END
$$;

COMMIT;
