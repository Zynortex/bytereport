-- ════════════════════════════════════════════════════════════════════════════
-- "Free reports are used up" vs "the reports in your package are used up".
--
-- The first paying customer must not be told their FREE reports ran out. The
-- ledger already knows: an account that ever received a manual grant has
-- paid. Two changes:
--   * consume_report_credit() also returns `paid` when it refuses;
--   * get_report_credit_status() returns {balance, paid} for the web.
--
-- Run after 20261116120000_report_credits.sql. Safe to run more than once.
-- ════════════════════════════════════════════════════════════════════════════

-- True when the account has ever been granted reports by hand (a purchase).
create or replace function public._report_credits_paid(p_user uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1 from credit_events
     where user_id = p_user and kind = 'grant' and amount > 0
  );
$$;

create or replace function public.get_report_credit_status(p_user uuid, p_signup_bonus integer)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_balance integer;
begin
  perform _ensure_report_credits(p_user, p_signup_bonus);
  select balance into v_balance from report_credits where user_id = p_user;
  return jsonb_build_object('balance', v_balance, 'paid', _report_credits_paid(p_user));
end;
$$;

-- Same as before, plus `paid` on a refusal.
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

  if p_daily_cap > 0 then
    select count(*) into v_today
      from credit_events
     where user_id = p_user and kind = 'consume' and refunded_by is null
       and created_at > now() - interval '24 hours';
    if v_today >= p_daily_cap then
      return jsonb_build_object('ok', false, 'reason', 'daily_cap', 'balance', v_balance,
                                'paid', _report_credits_paid(p_user));
    end if;
  end if;

  if v_balance <= 0 then
    return jsonb_build_object('ok', false, 'reason', 'no_credits', 'balance', v_balance,
                              'paid', _report_credits_paid(p_user));
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

revoke all on function public._report_credits_paid(uuid)                   from public, anon, authenticated;
revoke all on function public.get_report_credit_status(uuid, integer)      from public, anon, authenticated;
revoke all on function public.consume_report_credit(uuid, integer, integer) from public, anon, authenticated;
grant execute on function public.get_report_credit_status(uuid, integer)      to service_role;
grant execute on function public.consume_report_credit(uuid, integer, integer) to service_role;
