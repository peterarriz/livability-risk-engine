-- db/migrate_rls.sql
-- task: data-067
--
-- Idempotent migration: enable Row Level Security on all public tables
-- and add a public SELECT policy to each.
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
        'api_keys',
        'accounts',
        'signal_display'
    ];
BEGIN
    FOREACH t IN ARRAY tables LOOP
        -- Skip tables that don't exist (e.g. signal_display may be absent)
        IF EXISTS (
            SELECT 1 FROM pg_tables
            WHERE schemaname = 'public' AND tablename = t
        ) THEN
            EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
            EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
            EXECUTE format('DROP POLICY IF EXISTS select_%I ON %I', t, t);
            EXECUTE format(
                'CREATE POLICY select_%I ON %I FOR SELECT USING (true)', t, t
            );
            RAISE NOTICE 'RLS enabled on %', t;
        ELSE
            RAISE NOTICE 'Skipping % (table does not exist)', t;
        END IF;
    END LOOP;
END
$$;

COMMIT;
