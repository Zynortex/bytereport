-- ════════════════════════════════════════════════════════════════════════════
-- Export the CURRENT definition of the tables the app already uses
-- (reports, transactions), which so far exist only in the Supabase dashboard.
--
-- Run in the SQL editor, copy each result grid, and send it over. It becomes
-- supabase/migrations/20260501000000_existing_reports.sql, so a fresh project
-- can be rebuilt from the repository alone.
--
-- Read-only: nothing here changes the database.
-- ════════════════════════════════════════════════════════════════════════════

-- 1. Columns
select table_name, ordinal_position, column_name, data_type, udt_name,
       is_nullable, column_default
  from information_schema.columns
 where table_schema = 'public' and table_name in ('reports', 'transactions')
 order by table_name, ordinal_position;

-- 2. Keys, foreign keys, checks
select conrelid::regclass as table_name, conname, pg_get_constraintdef(oid) as definition
  from pg_constraint
 where conrelid in ('public.reports'::regclass, 'public.transactions'::regclass)
 order by 1, 2;

-- 3. Indexes
select tablename, indexname, indexdef
  from pg_indexes
 where schemaname = 'public' and tablename in ('reports', 'transactions')
 order by 1, 2;

-- 4. Is row level security on?
select relname, relrowsecurity as rls_enabled, relforcerowsecurity as rls_forced
  from pg_class
 where oid in ('public.reports'::regclass, 'public.transactions'::regclass);

-- 5. RLS policies
select tablename, policyname, permissive, roles, cmd, qual, with_check
  from pg_policies
 where schemaname = 'public' and tablename in ('reports', 'transactions')
 order by 1, 2;

-- 6. Table privileges per role
select table_name, grantee, string_agg(privilege_type, ', ' order by privilege_type) as privileges
  from information_schema.role_table_grants
 where table_schema = 'public' and table_name in ('reports', 'transactions')
 group by 1, 2
 order by 1, 2;

-- 7. Triggers, if any
select event_object_table as table_name, trigger_name, action_timing, event_manipulation, action_statement
  from information_schema.triggers
 where event_object_schema = 'public' and event_object_table in ('reports', 'transactions');
