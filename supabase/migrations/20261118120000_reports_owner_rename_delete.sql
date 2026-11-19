-- ════════════════════════════════════════════════════════════════════════════
-- Let an account rename and delete ITS OWN saved reports.
--
-- The dashboard now offers rename and delete. Under row level security an
-- UPDATE/DELETE with no matching policy is not an error — it silently touches
-- zero rows — so these policies are what make the buttons real.
--
-- Deliberately additive: this file does not enable or disable RLS and does not
-- touch existing policies (their definitions are not in the repository yet —
-- see supabase/export_existing_schema.sql). If RLS is off on these tables,
-- the policies are inert and everything already works.
--
-- `user_id::text` on both sides works whether the column is uuid or text.
-- Safe to run more than once.
-- ════════════════════════════════════════════════════════════════════════════

drop policy if exists "owner renames own reports" on public.reports;
create policy "owner renames own reports" on public.reports
  for update to authenticated
  using      (user_id::text = (select auth.uid())::text)
  with check (user_id::text = (select auth.uid())::text);

drop policy if exists "owner deletes own reports" on public.reports;
create policy "owner deletes own reports" on public.reports
  for delete to authenticated
  using (user_id::text = (select auth.uid())::text);

-- A report's transactions go with it (the app deletes them first, in case the
-- foreign key has no ON DELETE CASCADE).
drop policy if exists "owner deletes own transactions" on public.transactions;
create policy "owner deletes own transactions" on public.transactions
  for delete to authenticated
  using (user_id::text = (select auth.uid())::text);
