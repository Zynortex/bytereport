"""
Free-hosting readiness: AI_MOCK, the two health checks, CORS from the
environment, and a cold start that does not load what /health never needs.

The host (Render Free) sleeps after 15 minutes and wakes on the next request,
so everything here is about that first request: it must not wait for
reportlab to import, and it must never be the one that spends OpenAI money
during a test or a layout check.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import time

import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.api.routes import health as health_route
from app.core.config import Settings, settings
from app.services import mock_ai
from main import app, cors_options, parse_origins
from tests import fixtures_gen

ROOT = pathlib.Path(__file__).resolve().parents[1]
client = TestClient(app)
SECRET = "test-only-signing-secret-not-a-real-key"


def _auth() -> dict:
    from jose import jwt

    token = jwt.encode({"sub": "mock-user", "aud": "authenticated", "email": "qa@biznes.uz",
                        "exp": int(time.time()) + 3600}, SECRET, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setattr(settings, "supabase_jwt_secret", SECRET)
    limiters = (deps.report_limiter, deps.ai_limiter, deps.upload_limiter)
    for lim in limiters:
        lim.reset()
    health_route.reset_cache()
    yield
    for lim in limiters:
        lim.reset()
    health_route.reset_cache()


@pytest.fixture
def no_provider(monkeypatch):
    """Any attempt to build a provider client fails the test."""
    import anthropic
    import openai

    def refuse(*a, **kw):
        raise AssertionError("a provider client was built under AI_MOCK")

    monkeypatch.setattr(openai, "OpenAI", refuse)
    monkeypatch.setattr(anthropic, "Anthropic", refuse)
    yield


def _metrics() -> dict:
    up = client.post("/upload", files={"file": ("q.csv", fixtures_gen.csv_utf8(), "text/csv")})
    assert up.status_code == 200, up.text
    an = client.post("/analyze", json={"transactions": up.json()["transactions"]})
    assert an.status_code == 200, an.text
    return an.json()


# ── AI_MOCK ─────────────────────────────────────────────────────────────────

def test_the_mock_is_off_unless_asked_for():
    assert Settings.model_fields["ai_mock"].default is False


@pytest.mark.parametrize("lang", ["ru", "uz", "en"])
def test_a_full_report_runs_end_to_end_without_a_provider(lang, no_provider):
    metrics = _metrics()
    before = mock_ai.calls["report"]
    resp = client.post("/report/analyze", headers=_auth(), json={
        "metrics": metrics, "business_name": "QA", "currency": "UZS", "language": lang,
    })
    assert resp.status_code == 200, resp.text
    report = resp.json()
    assert mock_ai.calls["report"] == before + 1
    assert report["language"] == lang
    # It says it is a test answer, so it can never pass for a real one...
    assert "AI_MOCK=1" in report["executive_summary"]
    # ...and the figures in it are the engine's own.
    revenue = f"{metrics['total_revenue']:,.0f}".replace(",", " ")
    assert revenue in report["executive_summary"]
    assert report["financial_health_score"]["score"] == metrics["health_score"]
    assert report["weekly_cash_flow"], "the engine's weekly rows are attached as usual"

    pdf = client.post("/report/pdf", json={"report": report, "business_name": "QA",
                                           "metrics": metrics, "language": lang})
    assert pdf.status_code == 200 and pdf.content[:5] == b"%PDF-"


def test_the_mock_report_has_no_unfilled_placeholders():
    for lang in ("ru", "uz", "en"):
        raw = mock_ai.report_json(_metrics(), lang, "UZS")
        assert "{" not in "".join(_strings(json.loads(raw))), lang


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


def test_chat_answers_from_the_fixture(no_provider):
    metrics = _metrics()
    resp = client.post("/chat", headers=_auth(), json={
        "message": "What is my profit?", "metrics": metrics, "currency": "UZS",
    })
    assert resp.status_code == 200, resp.text
    assert "AI_MOCK=1" in resp.json()["answer"]


def test_note_photo_and_voice_answer_from_the_fixture(no_provider):
    note = client.post("/voice/parse", headers=_auth(),
                       json={"text": "продал диван за 500 тысяч", "language": "ru", "currency": "UZS"})
    assert note.status_code == 200, note.text
    assert [t["direction"] for t in note.json()["transactions"]] == ["income", "expense"]
    assert any("AI_MOCK=1" in w for w in note.json()["warnings"])

    jpeg = bytes([0xFF, 0xD8, 0xFF, 0xE0]) + b"0" * 64
    photo = client.post("/voice/photo", headers=_auth(), data={"language": "en", "currency": "USD"},
                        files={"file": ("r.jpg", jpeg, "image/jpeg")})
    assert photo.status_code == 200, photo.text
    assert {t["currency"] for t in photo.json()["transactions"]} == {"USD"}

    voice = client.post("/voice/transcribe", headers=_auth(), data={"language": "uz"},
                        files={"file": ("n.webm", b"\x1a\x45\xdf\xa3" + b"0" * 64, "audio/webm")})
    assert voice.status_code == 200, voice.text
    assert voice.json()["text"]


def test_the_test_suite_itself_runs_with_the_mock_and_without_keys():
    # conftest turns the mock on and blanks the keys for every test, so a code
    # path that slipped past the mock still could not reach a paid API.
    assert settings.ai_mock is True
    assert settings.openai_api_key == "" and settings.anthropic_api_key == ""


# ── /health ─────────────────────────────────────────────────────────────────

class _FakeClient:
    """Stands in for httpx.AsyncClient and records the one request."""

    seen: list = []
    status = 200
    fail = False

    def __init__(self, *a, **kw):
        self.timeout = kw.get("timeout")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def head(self, url, params=None, headers=None):
        import httpx

        _FakeClient.seen.append(("HEAD", url, params, headers))
        if _FakeClient.fail:
            raise httpx.ConnectTimeout("paused")
        return httpx.Response(_FakeClient.status, request=httpx.Request("HEAD", url))


@pytest.fixture
def fake_supabase(monkeypatch):
    import httpx

    _FakeClient.seen, _FakeClient.status, _FakeClient.fail = [], 200, False
    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)
    monkeypatch.setattr(settings, "supabase_url", "https://project-ref.supabase.co")
    monkeypatch.setattr(settings, "supabase_service_key", "service-key-for-tests")
    yield _FakeClient


def test_health_answers_without_touching_the_database(fake_supabase):
    resp = client.get("/health")
    assert resp.status_code == 200 and resp.json()["status"] == "ok"
    assert fake_supabase.seen == []


def test_deep_health_runs_one_real_query(fake_supabase):
    resp = client.get("/health/deep")
    assert resp.status_code == 200
    assert resp.json()["database"] == "ok"
    [(method, url, params, headers)] = fake_supabase.seen
    # HEAD: Postgres runs the select, the body never carries a row.
    assert method == "HEAD"
    assert url == "https://project-ref.supabase.co/rest/v1/report_credits"
    assert params == {"select": "user_id", "limit": "1"}


def test_deep_health_leaks_nothing(fake_supabase):
    fake_supabase.status = 401
    resp = client.get("/health/deep")
    assert resp.status_code == 503
    body = resp.json()
    assert set(body) == {"status", "database", "database_ms", "cached"}
    text = resp.text
    for secret in ("project-ref", "supabase.co", "service-key-for-tests", "401"):
        assert secret not in text


def test_deep_health_reports_an_unreachable_database(fake_supabase):
    fake_supabase.fail = True
    resp = client.get("/health/deep")
    assert resp.status_code == 503 and resp.json()["database"] == "unavailable"


def test_deep_health_is_cached_so_it_cannot_be_used_to_hammer_supabase(fake_supabase):
    for _ in range(5):
        assert client.get("/health/deep").status_code == 200
    assert len(fake_supabase.seen) == 1
    assert client.get("/health/deep").json()["cached"] is True


def test_deep_health_without_configuration_is_degraded_not_a_crash(monkeypatch, fake_supabase):
    monkeypatch.setattr(settings, "supabase_url", "")
    resp = client.get("/health/deep")
    assert resp.status_code == 503
    assert fake_supabase.seen == []


# ── CORS ────────────────────────────────────────────────────────────────────

def _allows(environment: str, allowed: str, origin: str) -> bool:
    from starlette.middleware.cors import CORSMiddleware

    mw = CORSMiddleware(app=None, **cors_options(environment, allowed))
    return mw.is_allowed_origin(origin)


def test_origins_come_from_the_environment():
    assert parse_origins(" https://a.vercel.app/ ,https://b.example.com,,") == [
        "https://a.vercel.app", "https://b.example.com"]
    assert _allows("production", "https://a.vercel.app/", "https://a.vercel.app")


def test_development_lets_in_any_local_port():
    """Vite moved to 5174 when 5173 was taken, and every request was blocked."""
    for origin in ("http://localhost:5173", "http://localhost:5174", "http://127.0.0.1:5177",
                   "http://localhost:3000", "http://localhost", "http://[::1]:5173"):
        assert _allows("development", "", origin), origin
    for origin in ("http://localhost.evil.com", "http://evil.com/localhost:5173",
                   "http://127.0.0.1.nip.io:5173", "https://evil.example"):
        assert not _allows("development", "", origin), origin


def test_production_lets_in_only_the_listed_origins():
    listed = "https://bytereport.vercel.app"
    assert _allows("production", listed, "https://bytereport.vercel.app")
    for origin in ("http://localhost:5173", "http://127.0.0.1:5174", "https://evil.example"):
        assert not _allows("production", listed, origin), origin


def test_development_is_the_default_and_render_sets_production():
    assert Settings.model_fields["environment"].default == "development"
    assert "key: ENVIRONMENT\n        value: production" in (ROOT.parent / "render.yaml").read_text(encoding="utf-8")


def test_an_unknown_environment_is_refused_at_start(monkeypatch):
    from pydantic import ValidationError

    monkeypatch.setenv("ENVIRONMENT", "prod")
    with pytest.raises(ValidationError):
        Settings()


def test_no_deployed_origin_is_hardcoded():
    src = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "vercel.app" not in src
    assert "https://" not in src


def test_an_allowed_origin_gets_the_cors_header():
    resp = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"
    other = client.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in other.headers


# ── Cold start ──────────────────────────────────────────────────────────────

HEAVY = ("matplotlib", "reportlab", "pdfplumber", "openpyxl", "numpy", "pandas",
         "openai", "anthropic", "httpx", "lxml", "xlrd")


def test_importing_the_app_loads_none_of_the_heavy_libraries():
    """Measured: import main 1.90 s -> 1.03 s, uvicorn -> first /health 2.67 s -> 1.63 s."""
    code = ("import sys, main; "
            f"print(','.join(m for m in {HEAVY!r} if m in sys.modules) or 'none')")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True,
                         text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-2000:]
    assert out.stdout.strip().splitlines()[-1] == "none"


# ── PDF fonts on a bare host ────────────────────────────────────────────────

def test_the_pdf_finds_a_cyrillic_font_without_any_system_fonts(monkeypatch):
    """Render's Python image has no /usr/share/fonts. The face must come from
    what pip installs, or Russian and Uzbek text prints as squares."""
    from app.services import pdf_generator as pg

    bare = [d for d in pg._SEARCH_DIRS
            if d == pg._PROJECT_FONTS or d == pg._matplotlib_fonts()]
    monkeypatch.setattr(pg, "_SEARCH_DIRS", bare)
    assert pathlib.Path(pg._find_font(pg._REGULAR_CANDIDATES)).name == "DejaVuSans.ttf"
    assert pathlib.Path(pg._find_font(pg._BOLD_CANDIDATES)).name == "DejaVuSans-Bold.ttf"


# ── Memory: a long PDF statement ────────────────────────────────────────────

def test_every_pdf_page_is_released_as_soon_as_it_is_read(monkeypatch):
    """pdfplumber holds each parsed page until it is closed. Reading all pages
    first and the tables second held a 150-page statement at ~640 MB, over the
    512 MB free host (measured; now ~85 MB). Each page must be read once and
    closed before the next one is parsed."""
    import pdfplumber.page

    from app.services.pdf_statement import read_pdf_grid

    open_now, most_open, closed = set(), [0], []
    real_close = pdfplumber.page.Page.close
    real_text = pdfplumber.page.Page.extract_text

    def text(self, *a, **kw):
        open_now.add(self.page_number)
        most_open[0] = max(most_open[0], len(open_now))
        return real_text(self, *a, **kw)

    def close(self):
        open_now.discard(self.page_number)
        closed.append(self.page_number)
        return real_close(self)

    monkeypatch.setattr(pdfplumber.page.Page, "extract_text", text)
    monkeypatch.setattr(pdfplumber.page.Page, "close", close)

    rows = [[f"{1 + i % 28:02d}.01.2026", f"Платёж {i}", "", "1 000.00", "1 000.00"] for i in range(120)]
    grid = read_pdf_grid(fixtures_gen._statement_pdf(rows, rows_per_page=4))   # 30 pages
    assert len(grid) - 1 == 120
    assert most_open[0] == 1
    assert sorted(set(closed)) == list(range(1, 31))


# ── .env.example is safe to copy as is ──────────────────────────────────────

def test_a_copied_env_example_starts_the_server(tmp_path, monkeypatch):
    """`AI_MOCK=` (empty) used to fail bool parsing and crash the start."""
    (tmp_path / ".env").write_text((ROOT / ".env.example").read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
    s = Settings()
    assert s.ai_mock is False and s.ai_provider == "openai" and s.report_daily_cap == 20


# ── A slow upload does not stop /health ─────────────────────────────────────

def test_health_answers_while_an_upload_is_being_parsed(monkeypatch):
    """Parsing ran on the event loop: a PDF that took 20 s to read froze the
    whole server, so /health went silent and a live server looked asleep."""
    import asyncio

    import httpx

    from app.api.routes import upload as upload_route

    real = upload_route.parse_upload

    def slow_parse(content, filename):
        time.sleep(0.8)                  # blocking, as pdfplumber is
        return real(content, filename)

    monkeypatch.setattr(upload_route, "parse_upload", slow_parse)

    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            t0 = time.perf_counter()

            async def upload():
                r = await ac.post("/upload", files={"file": ("q.csv", fixtures_gen.csv_utf8(), "text/csv")})
                return r.status_code, time.perf_counter() - t0

            async def health():
                await asyncio.sleep(0.1)
                r = await ac.get("/health")
                return r.status_code, time.perf_counter() - t0

            return await asyncio.gather(upload(), health())

    (up_status, up_done), (h_status, h_done) = asyncio.run(run())
    assert up_status == 200 and h_status == 200
    assert up_done >= 0.8
    assert h_done < 0.5, f"/health waited {h_done:.2f}s for the upload to finish"


# ── PDF page limit ──────────────────────────────────────────────────────────

def _statement(pages: int) -> bytes:
    rows = [[f"{1 + i % 28:02d}.01.2026", f"Платёж {i}", "", "1 000.00", "1 000.00"] for i in range(pages)]
    return fixtures_gen._statement_pdf(rows, rows_per_page=1)


@pytest.mark.parametrize("lang, words", [
    ("ru", ("51 стр.", "не больше 50")),
    ("uz", ("51 саҳифа", "50 саҳифа")),
    ("en", ("51 pages", "limit is 50")),
])
def test_a_pdf_over_50_pages_is_refused_in_the_callers_language(lang, words):
    resp = client.post("/upload", headers={"Accept-Language": lang},
                       files={"file": ("long.pdf", _statement(51), "application/pdf")})
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    for w in words:
        assert w in detail, (lang, detail)
    assert "{" not in detail


def test_a_pdf_of_exactly_50_pages_is_read():
    resp = client.post("/upload", files={"file": ("ok.pdf", _statement(50), "application/pdf")})
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["transactions"]) == 50


def test_the_page_count_is_checked_before_any_page_is_parsed(monkeypatch):
    import pdfplumber.page

    from app.services.pdf_statement import MAX_PAGES, PdfTooManyPages, read_pdf_grid

    def must_not_run(self, *a, **kw):
        raise AssertionError("a page was parsed before the limit check")

    monkeypatch.setattr(pdfplumber.page.Page, "extract_text", must_not_run)
    monkeypatch.setattr(pdfplumber.page.Page, "extract_tables", must_not_run)
    with pytest.raises(PdfTooManyPages) as exc:
        read_pdf_grid(_statement(MAX_PAGES + 1))
    assert (exc.value.pages, exc.value.limit) == (MAX_PAGES + 1, MAX_PAGES)
