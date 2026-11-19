"""
Report credits: a balance per account, kept in Supabase.

Replaces "3 per day, in process memory", which reset on every restart and
let a failed AI call eat the user's allowance (refund existed and was never
called). The rules pinned here:

  * a new account gets the signup bonus from pricing.json, once;
  * a successful report spends 1, a failed one gives it back;
  * an empty balance is a 402 that says so, not a generic 429;
  * the owner's own addresses never run out;
  * if the balance cannot be checked, no paid report runs.
"""

import json
import pathlib
import re
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.core.config import settings
from app.models.report import AIReport
from app.services import credits
from app.services import pricing
from main import app
from tests.test_report_layout import REPORT

ROOT = pathlib.Path(__file__).resolve().parents[2]
MIGRATION = next((ROOT / "supabase" / "migrations").glob("*_report_credits.sql"))
client = TestClient(app)

SECRET = "test-only-signing-secret-not-a-real-key"


def _token(sub="user-1", email="owner@biznes.uz") -> str:
    from jose import jwt

    return jwt.encode({
        "sub": sub, "aud": "authenticated", "email": email,
        "exp": int(time.time()) + 3600,
    }, SECRET, algorithm="HS256")


def _auth(**kw) -> dict:
    return {"Authorization": f"Bearer {_token(**kw)}"}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setattr(settings, "supabase_jwt_secret", SECRET)
    monkeypatch.setattr(settings, "unlimited_report_emails", "")
    deps.report_limiter.reset()
    yield
    deps.report_limiter.reset()


@pytest.fixture
def ai_ok(monkeypatch):
    calls = []

    async def fake(**kw):
        calls.append(kw)
        return AIReport.model_validate(REPORT.model_dump())

    monkeypatch.setattr("app.api.routes.report.get_ai_analysis", fake)
    return calls


@pytest.fixture
def ai_down(monkeypatch):
    async def fake(**kw):
        raise RuntimeError("provider timeout")

    monkeypatch.setattr("app.api.routes.report.get_ai_analysis", fake)


def _analyze(**kw):
    return client.post("/report/analyze", json={"metrics": {}}, headers=_auth(**kw))


def _balance(**kw):
    return client.get("/account/credits", headers=_auth(**kw)).json()


# ── The brief's acceptance path ─────────────────────────────────────────────

def test_a_new_account_starts_with_the_signup_bonus():
    body = _balance()
    assert body == {"balance": 3, "unlimited": False, "signup_bonus": 3, "paid": False}


def test_three_reports_run_and_the_fourth_is_refused_clearly(ai_ok):
    for left in (2, 1, 0):
        resp = _analyze()
        assert resp.status_code == 200, resp.text
        assert _balance()["balance"] == left

    resp = _analyze()
    assert resp.status_code == 402
    detail = resp.json()["detail"]
    assert detail == "Бесплатные отчёты закончились."
    assert "/pricing" not in detail and "t.me" not in detail, "no pricing link or contact for now"
    assert len(ai_ok) == 3, "the fourth request must not reach the provider"


def test_a_failed_ai_call_costs_nothing(ai_down):
    resp = _analyze()
    assert resp.status_code == 503
    assert _balance()["balance"] == 3


def test_a_failure_of_any_kind_is_refunded(monkeypatch):
    async def fake(**kw):
        raise KeyError("a bug in our own code")

    monkeypatch.setattr("app.api.routes.report.get_ai_analysis", fake)
    with pytest.raises(KeyError):
        _analyze()
    assert _balance()["balance"] == 3


def test_balances_are_per_account(ai_ok):
    _analyze(sub="a", email="a@biznes.uz")
    assert _balance(sub="a", email="a@biznes.uz")["balance"] == 2
    assert _balance(sub="b", email="b@biznes.uz")["balance"] == 3


def test_the_owner_never_runs_out(monkeypatch, ai_ok, _memory_credits):
    monkeypatch.setattr(settings, "unlimited_report_emails", " Me@ByteReport.uz , other@x.uz")
    _memory_credits.set_balance("owner", 0)
    for _ in range(5):
        assert _analyze(sub="owner", email="me@bytereport.uz").status_code == 200
    assert _balance(sub="owner", email="me@bytereport.uz") == {
        "balance": None, "unlimited": True, "signup_bonus": 3, "paid": False,
    }


def test_the_daily_cap_is_a_second_line(monkeypatch, ai_ok, _memory_credits):
    monkeypatch.setattr(settings, "report_daily_cap", 2)
    _memory_credits.set_balance("user-1", 10)
    assert _analyze().status_code == 200
    assert _analyze().status_code == 200
    resp = _analyze()
    assert resp.status_code == 429
    assert "сутки" in resp.json()["detail"]
    assert _balance()["balance"] == 8, "a capped request spends nothing"


def test_refunded_runs_do_not_count_toward_the_daily_cap(monkeypatch, ai_down, _memory_credits):
    monkeypatch.setattr(settings, "report_daily_cap", 1)
    for _ in range(3):
        assert _analyze().status_code == 503        # provider down, not capped


def test_no_paid_report_runs_when_the_balance_cannot_be_checked(monkeypatch, ai_ok):
    class Broken:
        async def consume(self, user_id):
            raise credits.CreditsUnavailable("supabase down")

        async def status(self, user_id):
            raise credits.CreditsUnavailable("supabase down")

    monkeypatch.setattr(credits, "credit_store", Broken())
    assert _analyze().status_code == 503
    assert not ai_ok
    assert client.get("/account/credits", headers=_auth()).status_code == 503


def test_an_anonymous_caller_has_no_balance():
    assert client.get("/account/credits").status_code == 401


def test_a_refund_is_given_once(_memory_credits):
    import asyncio

    spend = asyncio.run(_memory_credits.consume("u"))
    asyncio.run(_memory_credits.refund(spend.event_id))
    asyncio.run(_memory_credits.refund(spend.event_id))
    assert asyncio.run(_memory_credits.status("u")).balance == 3


# ── The Supabase store speaks to the SQL functions correctly ────────────────

@pytest.fixture
def rpc(monkeypatch):
    """Route the store's HTTP calls to a handler instead of the network."""
    seen = []
    replies = {}

    def handler(request: httpx.Request) -> httpx.Response:
        fn = request.url.path.rsplit("/", 1)[-1]
        seen.append((request, json.loads(request.content or b"{}")))
        status, body = replies.get(fn, (200, None))
        return httpx.Response(status, json=body)

    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    store = credits.SupabaseCredits("https://proj.supabase.co", "service-role-key")
    return store, seen, replies


def test_spending_calls_the_rpc_with_the_service_key(rpc):
    import asyncio

    store, seen, replies = rpc
    replies["consume_report_credit"] = (200, {"ok": True, "balance": 2, "event_id": 41})
    result = asyncio.run(store.consume("uuid-1"))
    assert result == credits.SpendResult(ok=True, balance=2, event_id=41, reason=None)

    request, args = seen[0]
    assert request.url.path == "/rest/v1/rpc/consume_report_credit"
    assert request.headers["apikey"] == "service-role-key"
    assert request.headers["authorization"] == "Bearer service-role-key"
    assert args == {"p_user": "uuid-1", "p_signup_bonus": 3,
                    "p_daily_cap": settings.report_daily_cap}


def test_status_carries_the_paid_flag(rpc):
    import asyncio

    store, seen, replies = rpc
    replies["get_report_credit_status"] = (200, {"balance": 0, "paid": True})
    assert asyncio.run(store.status("uuid-1")) == credits.CreditStatus(balance=0, paid=True)
    assert seen[0][0].url.path == "/rest/v1/rpc/get_report_credit_status"


def test_an_empty_balance_comes_back_as_a_reason(rpc):
    import asyncio

    store, _, replies = rpc
    replies["consume_report_credit"] = (200, {"ok": False, "reason": "no_credits", "balance": 0})
    assert asyncio.run(store.consume("u")).reason == "no_credits"


def test_a_missing_migration_is_unavailable_not_a_crash(rpc):
    import asyncio

    store, _, replies = rpc
    replies["consume_report_credit"] = (404, {"message": "function not found"})
    with pytest.raises(credits.CreditsUnavailable):
        asyncio.run(store.consume("u"))


def test_an_unconfigured_key_is_unavailable():
    import asyncio

    with pytest.raises(credits.CreditsUnavailable):
        asyncio.run(credits.SupabaseCredits("https://p.supabase.co", "").status("u"))


# ── One source for the numbers ──────────────────────────────────────────────

def test_the_signup_bonus_is_the_free_plan():
    data = json.loads((ROOT / "pricing.json").read_text(encoding="utf-8"))
    assert pricing.FREE_REPORTS_ON_SIGNUP == data["free_reports_on_signup"]
    assert pricing.plan("free")["reports"] == data["free_reports_on_signup"]


def test_the_built_in_fallback_matches_the_file():
    data = json.loads((ROOT / "pricing.json").read_text(encoding="utf-8"))
    data.pop("_comment", None)
    assert pricing._FALLBACK == data


def test_the_brief_prices():
    assert (pricing.plan("owner")["price"], pricing.plan("owner")["reports"]) == (150000, 5)
    assert (pricing.plan("accountant")["price"], pricing.plan("accountant")["reports"]) == (450000, 25)
    assert pricing.PRICING["currency"] == "UZS"


# ── The migration does not hand users the keys to their own balance ────────

SQL = MIGRATION.read_text(encoding="utf-8")


def test_rls_is_on_for_both_tables():
    assert "alter table public.report_credits enable row level security" in SQL
    assert "alter table public.credit_events  enable row level security" in SQL


def test_users_may_only_read():
    policies = re.findall(r"create policy .*?;", SQL, re.S)
    assert policies and all("for select" in p for p in policies)


@pytest.mark.parametrize("fn", [
    "get_report_credits(uuid, integer)",
    "consume_report_credit(uuid, integer, integer)",
    "refund_report_credit(bigint)",
    "grant_report_credits(text, integer, text)",
])
def test_no_function_is_callable_from_the_browser(fn):
    revoke = re.search(r"revoke all on function public\." + re.escape(fn) + r"\s+from ([^;]+);", SQL)
    assert revoke, fn
    assert "anon" in revoke.group(1) and "authenticated" in revoke.group(1)


def test_granting_is_for_the_sql_editor_only():
    assert "grant execute on function public.grant_report_credits" not in SQL


def test_the_last_report_cannot_be_spent_twice():
    body = SQL[SQL.index("function public.consume_report_credit"):]
    assert "for update" in body.split("$$;")[0]


# ── Free reports vs a bought package (A1) ───────────────────────────────────

def test_a_paying_account_is_not_told_its_free_reports_ran_out(ai_ok, _memory_credits):
    _memory_credits.grant("user-1", 1)          # signup bonus 3 + a package of 1
    for _ in range(4):
        assert _analyze().status_code == 200
    resp = _analyze()
    assert resp.status_code == 402
    assert resp.json()["detail"] == "Отчёты в пакете закончились."
    assert _balance()["paid"] is True


@pytest.mark.parametrize("lang,free,paid", [
    ("ru", "Бесплатные отчёты закончились.", "Отчёты в пакете закончились."),
    ("uz", "Бепул ҳисоботлар тугади.", "Пакетдаги ҳисоботлар тугади."),
    ("en", "Your free reports are used up.", "The reports in your package are used up."),
])
def test_the_402_speaks_the_interface_language(ai_ok, _memory_credits, lang, free, paid):
    _memory_credits.set_balance("user-1", 0)
    headers = {**_auth(), "Accept-Language": f"{lang}-XX,{lang};q=0.9"}
    assert client.post("/report/analyze", json={"metrics": {}}, headers=headers).json()["detail"] == free
    _memory_credits.grant("user-1", 1)
    _memory_credits.set_balance("user-1", 0)
    assert client.post("/report/analyze", json={"metrics": {}}, headers=headers).json()["detail"] == paid


def test_the_web_banner_reads_the_same_sentences():
    src = ROOT / "bytereport-frontend" / "src"
    store = (src / "store" / "creditsStore.ts").read_text(encoding="utf-8")
    assert '"credits_exhausted.paid"' in store and '"credits_exhausted.free"' in store
    for page in ("pages/Upload.tsx", "components/layout/Sidebar.tsx"):
        assert "t(exhaustedKey(credits))" in (src / page).read_text(encoding="utf-8"), page
    client_ts = (ROOT / "bytereport-frontend" / "src" / "api" / "client.ts").read_text(encoding="utf-8")
    assert "Accept-Language" in client_ts, "the 402 must come back in the interface language"


def test_the_paid_flag_migration_is_versioned():
    sql = next((ROOT / "supabase" / "migrations").glob("*_report_credits_paid_flag.sql")).read_text(encoding="utf-8")
    assert "kind = 'grant' and amount > 0" in sql
    assert "revoke all on function public.get_report_credit_status(uuid, integer)      from public, anon, authenticated" in sql
