# ByteReport API

FastAPI backend for ByteReport. The web app lives in `../bytereport-frontend`.

## Run locally

```bash
python -m venv venv
venv/Scripts/pip install -r requirements.txt     # Windows; venv/bin/pip elsewhere
cp .env.example .env                             # then fill in the values
venv/Scripts/uvicorn main:app --reload --port 8000
```

No OpenAI key? Set `AI_MOCK=1` in `.env`: every AI answer then comes from
`app/fixtures/ai_mock.json`, nothing is sent to a provider, nothing is spent.

Tests: `venv/Scripts/python -m pytest -q`. They run with `AI_MOCK` on and the
provider keys blanked, and never touch a live Supabase project or AI provider.

Deployment (Render, `render.yaml` in the repository root): see `../DEPLOY.md`.

Every environment variable is listed in [.env.example](.env.example).

## Supabase

Database changes live in [`../supabase/migrations`](../supabase/migrations).
There is no CLI step: open **Supabase → SQL Editor**, paste a migration file,
press **Run**, in file-name order. Each file is safe to run twice.

The backend needs the **service role key** in `SUPABASE_SERVICE_KEY` (Supabase →
Project Settings → API). Without it no report can be charged, so
`/report/analyze` answers 503 instead of running unpaid.

## Report credits

Each account has a balance of full AI reports, stored in `report_credits`, with
every change written to `credit_events`.

| Event | What happens |
|---|---|
| First contact with the backend | +3 free reports, once (`free_reports_on_signup` in [`../pricing.json`](../pricing.json)) |
| Successful full analysis | −1 |
| AI call failed | the −1 is given back automatically |
| Balance 0 | `402` "Бесплатные отчёты закончились." — or "Отчёты в пакете закончились." once the account has had a manual grant; in the caller's language (Accept-Language), the same sentence the upload page shows (`report-copy.json` → `credits_exhausted`) |

Voice, text and photo notes and PDF downloads do not use credits.

### Add reports after a card payment

In the SQL editor:

```sql
-- «Владелец»: 5 reports, 150 000 сум
select public.grant_report_credits('client@example.com', 5, 'Владелец, 150 000 сум, перевод 16.11');

-- «Бухгалтер»: 25 reports for the month, 450 000 сум
select public.grant_report_credits('buh@example.com', 25, 'Бухгалтер, ноябрь, 450 000 сум');
```

The function returns the new balance. A typo in the email is an error, not a
silent no-op. A negative amount corrects a mistake; the balance can never go
below zero. Credits do not expire: "25 в месяц" is kept by granting 25 on
each monthly payment.

### Check an account

```sql
-- Balance
select u.email, c.balance
  from public.report_credits c join auth.users u on u.id = c.user_id
 where u.email = 'client@example.com';

-- History: who paid, what was spent, what was refunded
select e.created_at, e.kind, e.amount, e.note
  from public.credit_events e join auth.users u on u.id = e.user_id
 where u.email = 'client@example.com'
 order by e.created_at desc;
```

### Your own accounts

List them in `UNLIMITED_REPORT_EMAILS` (comma-separated). They are never
charged and never run out; sign-in and the per-IP limits still apply.

### Limits that remain

- **Per account:** at most `REPORT_DAILY_CAP` reports (default 20) in any
  rolling 24 hours, whatever the balance. Counted in `credit_events`, so it
  survives restarts. Failed, refunded runs do not count.
- **Per IP:** `RATE_LIMIT_REPORT_PER_HOUR` / `RATE_LIMIT_AI_PER_HOUR`. These
  are kept in process memory and reset on restart. They only blunt a flood
  from one address; the balance is what controls cost.
