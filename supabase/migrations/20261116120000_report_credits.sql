-- ════════════════════════════════════════════════════════════════════════════
-- Report credits: a per-account balance of full AI reports.
--
-- Replaces the in-memory "3 per day" counter, which reset on every restart and
-- was per-process. The model now:
--   * a new account gets the signup bonus once (amount passed in by the
--     backend from pricing.json, so the number has one source);
--   * a successful full analysis spends 1; a failed AI call gives it back;
--   * paid packages are granted by hand with grant_report_credits().
--
-- Every change to a balance is also written to credit_events, so "who paid
-- for what, and was that failed run refunded" is answerable with a SELECT.
--
-- Safe to run more than once.
-- ════════════════════════════════════════════════════════════════════════════

create table if not exists public.report_credits (
  user_id              uuid primary key references auth.users (id) on delete cascade,
  balance              integer     not null default 0 check (balance >= 0),
  signup_bonus_granted boolean     not null default false,
  created_at           timestamptz not null default now(),
  updated_at           timestamptz not null default now()
);

create table if not exists public.credit_events (
  id          bigint generated always as identity primary key,
  user_id     uuid        not null references auth.users (id) on delete cascade,
  kind        text        not null check (kind in ('signup_bonus', 'grant', 'consume', 'refund')),
  amount      integer     not null,
  note        text,
  -- On a 'consume' row: the 'refund' row that gave it back. A consume can be
  -- refunded once, which makes refund_report_credit() idempotent.
  refunded_by bigint      references public.credit_events (id),
  created_at  timestamptz not null default now()
);

create index if not exists credit_events_user_time
  on public.credit_events (user_id, created_at desc);

-- ── Row level security ──────────────────────────────────────────────────────
-- A signed-in user may READ their own balance and history. Nobody writes
-- through the API: there are no insert/update/delete policies, so only the
-- service role (which bypasses RLS) and the functions below change anything.

alter table public.report_credits enable row level security;
alter table public.credit_events  enable row level security;

drop policy if exists "read own balance" on public.report_credits;
create policy "read own balance" on public.report_credits
  for select to authenticated using (user_id = auth.uid());

drop policy if exists "read own credit events" on public.credit_events;
create policy "read own credit events" on public.credit_events
  for select to authenticated using (user_id = auth.uid());

-- ── Functions ───────────────────────────────────────────────────────────────

-- Create the row if missing and pay the signup bonus exactly once.
create or replace function public._ensure_report_credits(p_user uuid, p_signup_bonus integer)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into report_credits (user_id) values (p_user)
  on conflict (user_id) do nothing;

  update report_credits
     set balance = balance + p_signup_bonus,
         signup_bonus_granted = true,
         updated_at = now()
   where user_id = p_user and not signup_bonus_granted;

  if found and p_signup_bonus > 0 then
    insert into credit_events (user_id, kind, amount, note)
    values (p_user, 'signup_bonus', p_signup_bonus, 'free reports on signup');
  end if;
end;
$$;

-- Current balance (pays the signup bonus on first contact).
create or replace function public.get_report_credits(p_user uuid, p_signup_bonus integer)
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
  v_balance integer;
begin
  perform _ensure_report_credits(p_user, p_signup_bonus);
  select balance into v_balance from report_credits where user_id = p_user;
  return v_balance;
end;
$$;

-- Spend one report. Returns {ok, balance, event_id} or {ok:false, reason}.
-- reason = 'no_credits' | 'daily_cap'. The row is locked for the duration,
-- so two simultaneous requests cannot both spend the last report.
create or replace function public.consume_report_credit(
  p_user uuid, p_signup_bonus integer, p_daily_cap integer
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_balance integer;
  v_today   integer;
  v_event   bigint;
begin
  perform _ensure_report_credits(p_user, p_signup_bonus);

  select balance into v_balance
    from report_credits where user_id = p_user
    for update;

  -- Second line of defence against a scripted account: a cap on spends per
  -- rolling 24 hours, whatever the balance. Refunded (failed) runs do not count.
  if p_daily_cap > 0 then
    select count(*) into v_today
      from credit_events
     where user_id = p_user and kind = 'consume' and refunded_by is null
       and created_at > now() - interval '24 hours';
    if v_today >= p_daily_cap then
      return jsonb_build_object('ok', false, 'reason', 'daily_cap', 'balance', v_balance);
    end if;
  end if;

  if v_balance <= 0 then
    return jsonb_build_object('ok', false, 'reason', 'no_credits', 'balance', v_balance);
  end if;

  update report_credits
     set balance = balance - 1, updated_at = now()
   where user_id = p_user
  returning balance into v_balance;

  insert into credit_events (user_id, kind, amount, note)
  values (p_user, 'consume', -1, 'full AI report')
  returning id into v_event;

  return jsonb_build_object('ok', true, 'balance', v_balance, 'event_id', v_event);
end;
$$;

-- Give back the report spent by one consume event (the AI call failed).
-- Refunding the same event twice does nothing the second time.
create or replace function public.refund_report_credit(p_event bigint)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_user    uuid;
  v_refund  bigint;
  v_balance integer;
begin
  select user_id into v_user
    from credit_events
   where id = p_event and kind = 'consume' and refunded_by is null
   for update;
  if not found then
    return jsonb_build_object('ok', false);
  end if;

  insert into credit_events (user_id, kind, amount, note)
  values (v_user, 'refund', 1, 'AI call failed')
  returning id into v_refund;

  update credit_events set refunded_by = v_refund where id = p_event;

  update report_credits
     set balance = balance + 1, updated_at = now()
   where user_id = v_user
  returning balance into v_balance;

  return jsonb_build_object('ok', true, 'balance', v_balance);
end;
$$;

-- Manual top-up after a card transfer. Run from the SQL editor:
--   select public.grant_report_credits('client@example.com', 5, 'Владелец, 150 000 сум, 16.11');
-- A negative amount corrects a mistake (the balance can never go below 0).
-- Returns the new balance.
create or replace function public.grant_report_credits(
  p_email text, p_amount integer, p_note text default null
)
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
  v_user    uuid;
  v_balance integer;
begin
  if p_amount = 0 then
    raise exception 'amount must not be zero';
  end if;

  select id into v_user from auth.users where lower(email) = lower(trim(p_email));
  if v_user is null then
    raise exception 'no account with email %', p_email;
  end if;

  -- Creating the row here does NOT pay the signup bonus; that still happens
  -- on the account's first contact with the backend.
  insert into report_credits (user_id) values (v_user)
  on conflict (user_id) do nothing;

  update report_credits
     set balance = balance + p_amount, updated_at = now()
   where user_id = v_user
  returning balance into v_balance;

  insert into credit_events (user_id, kind, amount, note)
  values (v_user, 'grant', p_amount, p_note);

  return v_balance;
end;
$$;

-- ── Who may call what ───────────────────────────────────────────────────────
-- Supabase grants EXECUTE on new public functions to anon and authenticated
-- by default. Left that way, any signed-in user could call refund or grant
-- from the browser and mint reports. Only the backend's service role may
-- touch balances; grant_report_credits is for the SQL editor only.

revoke all on function public._ensure_report_credits(uuid, integer)          from public, anon, authenticated;
revoke all on function public.get_report_credits(uuid, integer)              from public, anon, authenticated;
revoke all on function public.consume_report_credit(uuid, integer, integer)  from public, anon, authenticated;
revoke all on function public.refund_report_credit(bigint)                   from public, anon, authenticated;
revoke all on function public.grant_report_credits(text, integer, text)      from public, anon, authenticated, service_role;

grant execute on function public.get_report_credits(uuid, integer)             to service_role;
grant execute on function public.consume_report_credit(uuid, integer, integer) to service_role;
grant execute on function public.refund_report_credit(bigint)                  to service_role;
