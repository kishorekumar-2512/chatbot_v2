-- migrations/001_enable_rls.sql
-- Enables PostgreSQL Row Level Security (RLS) on multi-tenant tables as a 2nd line of defense.
-- Application connections must set `SET LOCAL app.current_org_id = 'org_xxx';` before executing queries.

BEGIN;

-- Helper function to retrieve current org ID safely
CREATE OR REPLACE FUNCTION current_app_org_id() RETURNS text AS $$
BEGIN
    RETURN current_setting('app.current_org_id', true);
END;
$$ LANGUAGE plpgsql STABLE;

-- Loop through all public schema tables that have a `zecure_org_id` column
DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN
        SELECT table_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND column_name = 'zecure_org_id'
    LOOP
        -- 1. Enable RLS
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY;', r.table_name);
        
        -- 2. Force RLS even for table owners / application user roles
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY;', r.table_name);

        -- 3. Drop existing policy if present
        EXECUTE format('DROP POLICY IF EXISTS org_isolation_policy ON %I;', r.table_name);

        -- 4. Create RLS Policy
        -- Allows access if zecure_org_id matches app.current_org_id session setting,
        -- OR if app.current_org_id is null/empty (for admin/system superuser queries).
        EXECUTE format('
            CREATE POLICY org_isolation_policy ON %I
            FOR ALL
            USING (
                zecure_org_id = current_app_org_id()
                OR current_app_org_id() IS NULL
                OR current_app_org_id() = ''''
            );
        ', r.table_name);

        RAISE NOTICE 'Enabled RLS and created org_isolation_policy on table: %', r.table_name;
    END LOOP;
END;
$$;

COMMIT;
