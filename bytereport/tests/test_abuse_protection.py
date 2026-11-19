"""
Abuse protection, and the two PDF text bugs.

The starting point for all of this: the backend had NO authentication. Every
endpoint that spends OpenAI money answered the open internet, and the
account-level measures (email confirmation, disposable domains, per-account
limits) all live at the sign-up layer that a script never touches. The first
group of tests pins the thing that makes the others mean anything.
"""

import time

import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.core.abuse import SlidingWindow, is_disposable
from app.core.config import settings
from app.services.ai_text import humanize, looks_like_a_bare_token, sanitize, scrub_model
from main import app

client = TestClient(app)

# Every endpoint that calls a paid API, with a body good enough to reach the
# dependency. None of them should answer an anonymous caller.
PAID_ENDPOINTS = [
    ("/report/analyze", {"metrics": {}}),
    ("/chat", {"message": "hi", "history": [], "metrics": {}}),
    ("/voice/parse", {"text": "получил 500 тысяч"}),
]


@pytest.fixture(autouse=True)
def _clean_state():
    deps.report_limiter.reset()
    deps.ai_limiter.reset()
    deps.upload_limiter.reset()
    yield
    deps.report_limiter.reset()
    deps.ai_limiter.reset()
    deps.upload_limiter.reset()


# ── The hole ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("path,body", PAID_ENDPOINTS)
def test_a_paid_endpoint_refuses_an_anonymous_caller(path, body):
    resp = client.post(path, json=body)
    assert resp.status_code == 401, (
        f"{path} answered without a token — this is the whole exposure"
    )


def test_a_paid_endpoint_refuses_a_forged_token():
    resp = client.post(
        "/report/analyze", json={"metrics": {}},
        headers={"Authorization": "Bearer not.a.real.token"},
    )
    assert resp.status_code == 401


def test_a_paid_endpoint_refuses_an_unsigned_token():
    """
    alg=none is the classic bypass: a well-formed token with no signature.
    """
    import base64
    import json as _json

    def seg(d):
        return base64.urlsafe_b64encode(_json.dumps(d).encode()).decode().rstrip("=")

    forged = ".".join([
        seg({"alg": "none", "typ": "JWT"}),
        seg({"sub": "attacker", "email": "a@b.com", "aud": "authenticated"}),
        "",
    ])
    resp = client.post(
        "/report/analyze", json={"metrics": {}},
        headers={"Authorization": f"Bearer {forged}"},
    )
    assert resp.status_code == 401


def test_every_ai_route_carries_a_caller_dependency():
    """
    A new AI endpoint must not be able to ship unprotected. The voice feature
    was added while the API had no auth at all; this is what would have caught
    it.
    """
    from fastapi.routing import APIRoute

    guarded = {"ai_caller", "report_caller", "require_verified_user", "require_user"}
    # Endpoints that reach a paid API. /report/pdf and /voice/excel render
    # locally and cost nothing upstream, so they are throttled rather than
    # gated — /report/pdf deliberately, to keep the public demo's download
    # button working for a visitor who has not signed up yet.
    paid_paths = {
        "/report/analyze", "/chat",
        "/voice/transcribe", "/voice/parse", "/voice/photo",
    }
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path in paid_paths:
            names = {
                d.call.__name__ for d in route.dependant.dependencies
                if getattr(d, "call", None)
            }
            assert names & guarded, f"{route.path} has no caller dependency"


def test_auth_is_required_by_default():
    """The safe default for 'who may spend our budget' is 'someone we know'."""
    assert settings.auth_required is True
    assert settings.block_disposable_email is True


def test_email_confirmation_is_left_to_supabase():
    """
    Off by default on purpose. Supabase's own "Confirm email" setting is the
    real gate — with it on, an unconfirmed user never gets a session. The JWT
    carries no trustworthy confirmation claim to re-check against, and checking
    anyway refused accounts that were genuinely confirmed.
    """
    assert settings.require_email_verification is False


# ── Disposable addresses ────────────────────────────────────────────────────

@pytest.mark.parametrize("email", [
    "a@mailinator.com", "b@guerrillamail.com", "c@10minutemail.com",
    "d@yopmail.com", "E@TEMP-MAIL.ORG", "f@trashmail.de",
])
def test_known_throwaway_domains_are_caught(email):
    assert is_disposable(email)


def test_a_subdomain_of_a_throwaway_service_is_caught():
    assert is_disposable("x@inbox.mailinator.com")


@pytest.mark.parametrize("email", [
    "user@gmail.com", "buhgalter@company.uz", "a@mail.ru", "b@yandex.ru",
])
def test_real_addresses_are_not_caught(email):
    assert not is_disposable(email)


def test_a_malformed_address_is_not_treated_as_disposable():
    """Rejecting it is the auth layer's job; this must not guess."""
    assert not is_disposable("nonsense")
    assert not is_disposable("")


# ── Rate limiting ───────────────────────────────────────────────────────────

def test_the_window_allows_up_to_the_limit_then_refuses():
    w = SlidingWindow(limit=3, window_seconds=60.0)
    assert all(w.check("ip")[0] for _ in range(3))
    allowed, retry_after = w.check("ip")
    assert not allowed and retry_after > 0


def test_the_window_slides_rather_than_resetting_on_the_hour():
    """
    A fixed bucket lets a caller spend the whole allowance at 11:59 and again
    at 12:00 — twice the limit back to back, which is the exact burst this is
    meant to stop.
    """
    w = SlidingWindow(limit=2, window_seconds=0.3)
    assert w.check("ip")[0] and w.check("ip")[0]
    assert not w.check("ip")[0]
    time.sleep(0.35)
    assert w.check("ip")[0], "the window never freed up"


def test_limits_are_per_caller():
    w = SlidingWindow(limit=1, window_seconds=60.0)
    assert w.check("1.1.1.1")[0]
    assert not w.check("1.1.1.1")[0]
    assert w.check("2.2.2.2")[0], "one caller exhausted everyone's allowance"


def test_the_forwarded_header_cannot_be_used_to_mint_new_identities():
    """
    X-Forwarded-For is client-controlled. Reading the FIRST entry would let a
    caller present a fresh address per request and never hit a limit; the last
    entry is the one the proxy itself appended.
    """
    from app.core.abuse import client_ip

    class _Req:
        headers = {"x-forwarded-for": "9.9.9.9, 8.8.8.8, 203.0.113.7"}
        client = None

    assert client_ip(_Req()) == "203.0.113.7"


def test_an_unauthenticated_flood_of_uploads_is_throttled():
    settings_limit = deps.upload_limiter.limit
    for _ in range(settings_limit):
        deps.upload_limiter.check("flooder")
    resp = client.post("/upload", files={"file": ("a.csv", b"date,amount\n", "text/csv")},
                       headers={"x-forwarded-for": "flooder"})
    assert resp.status_code == 429


# Report credits (the replacement for the per-day quota) are tested in
# tests/test_report_credits.py.


# ── PDF bug 2.1: notation leaking into prose ────────────────────────────────

def test_the_reported_leak_is_stripped():
    text = "на сумму не менее 60 000 000 UZS $(RO)=$ минимальные переменные затраты"
    cleaned, found = sanitize(text)
    assert "$" not in cleaned
    assert found == ["tex-math"]
    assert "60 000 000 UZS" in cleaned and "минимальные переменные затраты" in cleaned


@pytest.mark.parametrize("raw,gone", [
    ("Прибыль {PROFIT} за период", "{"),
    ("Формула \\(x\\) применена", "\\("),
    ("Итог $$TOTAL$$ за квартал", "$"),
    ("Значение {{ revenue }} тут", "{"),
])
def test_other_notation_shapes_are_stripped(raw, gone):
    cleaned, found = sanitize(raw)
    assert found, f"nothing detected in {raw!r}"
    assert gone not in cleaned


def test_a_price_in_dollars_is_left_alone():
    """The sanitiser must not eat real money written with a currency sign."""
    text = "Цена $5 и $7 за штуку"
    cleaned, found = sanitize(text)
    assert cleaned == text and found == []


def test_ordinary_prose_is_untouched():
    text = "Февральский минус 165 000 ₽ — классический кассовый разрыв."
    assert sanitize(text) == (text, [])


def test_the_whole_report_is_scrubbed_not_just_the_pdf():
    """
    Sanitising inside the PDF builder would leave the web page showing the raw
    text. It runs once, on the parsed object both surfaces share.
    """
    from app.models.report import AIReport

    payload = {
        "executive_summary": "Выручка $(REV)=$ выросла",
        "financial_health_score": {"score": 61, "status": "ok", "reasoning": "{WHY}"},
        "key_insights": [{"title": "A $(X)=$ B", "severity": "high", "explanation": "ok"}],
        "top_risks": [], "growth_opportunities": [],
        "expense_analysis": {"problem_categories": [], "efficient_categories": [], "notes": "ok"},
        "anomalies": [],
        "cash_flow_analysis": {"status": "ok", "summary": "ok", "warning_level": "low"},
        "forecast": {"outlook": "ok", "confidence": "low", "summary": "ok"},
        "priority_actions": [],
    }
    report = scrub_model(AIReport.model_validate(payload))
    assert "$" not in report.executive_summary
    assert "{" not in report.financial_health_score.reasoning
    assert "$" not in report.key_insights[0].title


def test_the_prompt_bans_the_notation():
    from app.core.prompts import BYTEREPORT_SYSTEM_PROMPT

    assert "ЗАПРЕТ НА НОТАЦИЮ" in BYTEREPORT_SYSTEM_PROMPT


# ── PDF bug 2.2: raw enum values instead of labels ──────────────────────────

@pytest.mark.parametrize("token,ru", [
    ("critical", "Критический дефицит"),
    ("deficit", "Дефицит"),
    ("negative", "Негативная"),
    ("high", "Высокая"),
    ("critical deficit", "Критический дефицит"),
    ("CRITICAL_DEFICIT", "Критический дефицит"),
])
def test_the_reported_tokens_become_labels(token, ru):
    assert humanize(token, "ru") == ru


@pytest.mark.parametrize("lang", ["ru", "uz", "en"])
def test_every_token_has_a_label_in_every_language(lang):
    from app.services.ai_text import _LABELS

    assert set(_LABELS[lang]) == set(_LABELS["ru"]), f"{lang} is missing tokens"
    assert all(_LABELS[lang].values()), f"{lang} has an empty label"


def test_real_prose_passes_through_unchanged():
    """These fields are meant to be sentences; only bare tokens get mapped."""
    prose = "Стабильный при условии предоплаты"
    assert humanize(prose, "ru") == prose


def test_a_bare_token_is_recognisable_as_one():
    assert looks_like_a_bare_token("critical")
    assert looks_like_a_bare_token("critical_deficit")
    assert not looks_like_a_bare_token("Стабильный при условии предоплаты")


def test_the_pdf_renders_labels_not_raw_values():
    import inspect

    from app.services import pdf_generator as pg

    for builder in (pg._build_cashflow, pg._build_forecast):
        src = inspect.getsource(builder)
        assert "humanize(" in src, f"{builder.__name__} still prints the raw field"
    assert "Paragraph(cf.status," not in inspect.getsource(pg._build_cashflow)
    assert "Paragraph(fc.outlook," not in inspect.getsource(pg._build_forecast)


def test_the_web_labels_match_the_pdf_labels():
    """
    Two copies of the same vocabulary, one per surface. They may be translated
    independently, but a token present on one side and missing on the other
    means one surface shows a raw enum again.
    """
    import io as _io
    import json as _json
    import os as _os

    from app.services.ai_text import _LABELS

    root = _os.path.normpath(_os.path.join(_os.path.dirname(__file__), "..", ".."))
    for lang in ("ru", "uz", "en"):
        path = _os.path.join(root, "bytereport-frontend", "src", "locales", f"{lang}.json")
        web = _json.load(_io.open(path, encoding="utf-8"))["report"]["enum"]
        assert set(web) == set(_LABELS[lang]), f"{lang}: web and PDF vocabularies differ"


# ── The accept path ─────────────────────────────────────────────────────────
#
# Refusing everything is easy and useless. These mint a genuinely signed token
# and prove a real user still gets through — and that each guard rejects for
# its own specific reason rather than everything collapsing into one 401.

TEST_SECRET = "test-only-signing-secret-not-a-real-key"


def _token(**claims) -> str:
    from jose import jwt

    payload = {
        "sub": "user-123", "aud": "authenticated", "email": "buhgalter@company.uz",
        "email_verified": True, "exp": int(time.time()) + 3600,
    }
    payload.update(claims)
    return jwt.encode(payload, TEST_SECRET, algorithm="HS256")


@pytest.fixture
def hs256(monkeypatch):
    """Verify against a local secret so no live Supabase project is needed."""
    monkeypatch.setattr(settings, "supabase_jwt_secret", TEST_SECRET)
    yield


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_a_real_user_gets_through(hs256):
    """/voice/excel is pure local work, so a valid caller must get a file."""
    resp = client.post(
        "/voice/excel",
        json={"transactions": [{
            "date": "2026-08-20", "amount": 500000, "direction": "income",
            "description": "Диван", "category": "Продажи",
        }], "currency": "UZS", "language": "ru"},
        headers=_auth(_token()),
    )
    assert resp.status_code == 200, resp.text
    assert resp.content[:4] == b"PK\x03\x04"


def test_an_expired_token_is_refused(hs256):
    resp = client.post("/voice/excel", json={"transactions": []},
                       headers=_auth(_token(exp=int(time.time()) - 60)))
    assert resp.status_code == 401


def test_a_token_signed_with_the_wrong_key_is_refused(hs256):
    from jose import jwt

    forged = jwt.encode(
        {"sub": "attacker", "aud": "authenticated", "email": "a@b.com",
         "email_verified": True, "exp": int(time.time()) + 3600},
        "a-different-secret", algorithm="HS256",
    )
    resp = client.post("/voice/excel", json={"transactions": []}, headers=_auth(forged))
    assert resp.status_code == 401


def test_a_token_without_a_confirmation_claim_is_accepted(monkeypatch, hs256):
    """
    The reported bug. A Supabase JWT has no `email_confirmed_at`, and
    `user_metadata.email_verified` is written at sign-up and is NOT updated by
    a manual `UPDATE auth.users SET email_confirmed_at = now()`. Reading it as
    the confirmation state refused a confirmed account.
    """
    from app.core.auth import _email_verified

    assert _email_verified({"sub": "u", "email": "a@b.com"}) is True
    assert _email_verified({"user_metadata": {"email_verified": False}}) is True
    assert _email_verified({"email_verified": True}) is True

    resp = client.post(
        "/voice/excel",
        json={"transactions": [{
            "date": "2026-08-20", "amount": 1, "direction": "income",
            "description": "x", "category": "y",
        }]},
        headers=_auth(_token()),
    )
    assert resp.status_code == 200, resp.text


def test_the_check_can_still_be_switched_on(monkeypatch, hs256):
    """Kept working for anyone whose provider does emit a reliable claim."""
    import app.core.auth as auth_mod

    monkeypatch.setattr(settings, "require_email_verification", True)
    monkeypatch.setattr(auth_mod, "_email_verified", lambda claims: False)
    resp = client.post("/voice/excel", json={"transactions": []},
                       headers=_auth(_token()))
    assert resp.status_code == 403


def test_a_throwaway_address_is_refused_with_its_own_reason(hs256):
    resp = client.post("/voice/parse", json={"text": "test"},
                       headers=_auth(_token(email="burner@mailinator.com")))
    assert resp.status_code == 403
    assert "одноразов" in resp.json()["detail"].lower()


def test_the_hourly_report_limit_is_enforced_per_address(hs256):
    for _ in range(deps.report_limiter.limit):
        deps.report_limiter.check("203.0.113.9")
    resp = client.post("/report/analyze", json={"metrics": {}},
                       headers={**_auth(_token()), "x-forwarded-for": "203.0.113.9"})
    assert resp.status_code == 429
    assert resp.headers.get("Retry-After")


def test_the_public_demo_can_still_download_its_pdf():
    """
    /demo is a public route and its download button is a marketing asset.
    Rendering a PDF spends no upstream money, so it stays open — throttled,
    not gated. Locking it would have broken the demo for every visitor.
    """
    from fastapi.routing import APIRoute

    route = next(r for r in app.routes
                 if isinstance(r, APIRoute) and r.path == "/report/pdf")
    names = {d.call.__name__ for d in route.dependant.dependencies if getattr(d, "call", None)}
    assert "throttled_anonymous" in names
    assert not (names & {"ai_caller", "report_caller", "require_verified_user"})


def test_the_risk_level_agrees_with_the_noun_above_it():
    """
    Russian agrees adjectives with their noun. "Уверенность" is feminine and
    "Уровень риска" is masculine, so one shared table printed
    "Уровень риска ВЫСОКАЯ" in a real PDF.
    """
    assert humanize("high", "ru") == "Высокая"                    # Уверенность
    assert humanize("high", "ru", kind="level") == "Высокий"      # Уровень риска
    # Languages without adjective agreement must be unaffected.
    assert humanize("high", "en", kind="level") == humanize("high", "en")
    assert humanize("high", "uz", kind="level") == humanize("high", "uz")


def test_the_web_carries_the_level_forms_too():
    import io as _io
    import json as _json
    import os as _os

    from app.services.ai_text import _LEVEL_OVERRIDES

    root = _os.path.normpath(_os.path.join(_os.path.dirname(__file__), "..", ".."))
    for lang in ("ru", "uz", "en"):
        path = _os.path.join(root, "bytereport-frontend", "src", "locales", f"{lang}.json")
        web = _json.load(_io.open(path, encoding="utf-8"))["report"]["enum_level"]
        assert set(web) == {"high", "medium", "low"}
    assert _LEVEL_OVERRIDES["ru"]["high"] == "Высокий"


# ── Errors must be visible where they happen ────────────────────────────────
#
# The API client used to answer any 401 with `window.location.href = "/auth"`.
# That was a silent full-page navigation on top of whatever the user was doing,
# and it did not even land on /auth: it cleared `br_token` but not the Supabase
# session, so the reload restored the user, /auth bounced a signed-in visitor
# onward, and the page landed on the Dashboard with no message. Recording a
# voice note looked like it navigated away at random. The reload also rewrote
# `br_token` from the same session, so the next attempt failed identically.
#
# Reproduced in a browser before the fix (ended on /dashboard, no error shown)
# and after (stayed put, note preserved, message and a sign-in link on screen).

import os as _os2

FRONT_SRC = _os2.path.join(
    _os2.path.normpath(_os2.path.join(_os2.path.dirname(__file__), "..", "..")),
    "bytereport-frontend", "src",
)


def _read_front(*parts: str) -> str:
    import io as _io2

    return _io2.open(_os2.path.join(FRONT_SRC, *parts), encoding="utf-8").read()


def _strip_comments(src: str) -> str:
    """
    Comments out, so the check reads CODE.

    The first version of this test failed on the comment that explains the
    bug — it was scanning prose. A guard that trips on its own
    documentation teaches people to delete the documentation.
    """
    import re as _re

    src = _re.sub(r"/\*.*?\*/", "", src, flags=_re.S)
    return chr(10).join(line.split("//")[0] for line in src.split(chr(10)))


def test_the_api_client_never_navigates_on_an_error():
    code = _strip_comments(_read_front("api", "client.ts"))
    body = code[code.index("interceptors.response"):]
    assert "window.location" not in body, "a failed request navigates the page again"
    assert "href =" not in body


def test_the_request_token_comes_from_the_live_session():
    """
    `br_token` is a hand-kept mirror and goes stale whenever Supabase refreshes
    without the auth listener writing back — a 401 on a request the user was
    entitled to make. getSession() refreshes as needed.
    """
    client_ts = _read_front("api", "client.ts")
    req = client_ts[client_ts.index("interceptors.request"):client_ts.index("interceptors.response")]
    assert "supabase.auth.getSession()" in req


def test_failures_carry_their_status_code():
    """
    Callers branch on "session gone" versus everything else. Matching the
    message text would mean pattern-matching translated Russian.
    """
    client_ts = _read_front("api", "client.ts")
    assert "class ApiError" in client_ts
    assert "readonly status?: number" in client_ts
    assert "export function isAuthError" in client_ts


def test_the_voice_page_shows_the_failure_in_place_with_a_way_back():
    page = _read_front("pages", "VoiceNote.tsx")
    assert "isAuthError(err)" in page
    assert 'to="/auth"' in page, "an expired session leaves the user with no action"
    # Every catch on the page routes through the one helper, so no path can
    # forget to set the flag.
    assert "setError(parseApiError(err))" not in page.replace(
        "setError(parseApiError(err));", "", 1
    ) or page.count("showError(err)") >= 4


def test_no_page_swallows_the_backend_reason():
    """
    Upload dug for `err.response`, which the interceptor no longer provides, so
    every failure collapsed into one generic line — hiding the actionable ones
    ("daily limit reached", "confirm your email").
    """
    for page in ("Upload.tsx", "Report.tsx", "Demo.tsx", "VoiceNote.tsx"):
        src = _read_front("pages", page)
        assert "parseApiError" in src, f"{page} discards the backend's reason"
