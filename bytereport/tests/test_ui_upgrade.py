"""
The interface pass: mobile shell, honest wait, score breakdown, dashboard
actions, link previews, report language.

Backend behaviour is tested directly; the web parts are pinned by reading the
source, the same way the earlier web/PDF single-source tests do.
"""

import asyncio
import io
import json
import pathlib
import re
from datetime import date, timedelta

import pdfplumber
import pytest

from app.models.report import AIReport
from app.models.transaction import Transaction, TransactionType
from app.services import ai_analyst
from app.services.financial_engine import compute_metrics, score_from_breakdown
from app.services.pdf_generator import generate_pdf
from app.services.report_copy import breakdown_lines, copy_text, format_points
from tests.test_report_layout import REPORT

ROOT = pathlib.Path(__file__).resolve().parents[2]
WEB = ROOT / "bytereport-frontend"
SRC = WEB / "src"
COPY = json.loads((ROOT / "report-copy.json").read_text(encoding="utf-8"))


def _read(rel: str) -> str:
    return (SRC / rel).read_text(encoding="utf-8")


def _txns(weeks=10, base_exp=700_000, step=60_000, income=1_000_000):
    out = []
    start = date(2024, 1, 1)
    for w in range(weeks):
        d = start + timedelta(weeks=w)
        out.append(Transaction(date=d, description="Продажи", amount=income,
                               type=TransactionType.income, category="sales"))
        out.append(Transaction(date=d + timedelta(days=2), description="Материалы",
                               amount=base_exp + step * w, type=TransactionType.expense, category="materials"))
    return out


# ── Health Score breakdown ──────────────────────────────────────────────────

@pytest.mark.parametrize("kwargs", [
    {},                                              # falling, thin margin
    {"base_exp": 200_000, "step": 0},                # healthy, flat
    {"base_exp": 1_200_000, "step": 0},              # loss-making
    {"weeks": 3},                                    # one month only
    {"base_exp": 100_000, "step": -5_000},           # growing margin
])
def test_the_breakdown_adds_up_to_the_score(kwargs):
    m = compute_metrics(_txns(**kwargs))
    assert len(m.health_breakdown) == 5
    assert score_from_breakdown(m.health_breakdown)[0] == m.health_score


def test_every_check_has_a_sentence_in_every_language():
    variants = {
        "margin": ["negative", "below", "ok"], "cash_gaps": ["some", "none"],
        "revenue_trend": ["down", "up", "flat", "na"], "tax_limit": ["over", "ok"],
        "volatility": ["high", "ok", "na"],
    }
    block = COPY["score_breakdown"]
    for key, vs in variants.items():
        for v in vs:
            entry = block[f"{key}_{v}"]
            assert set(entry) == {"ru", "uz", "en"} and all(entry.values()), f"{key}_{v}"


def test_the_engine_only_produces_variants_that_have_text():
    for kwargs in ({}, {"base_exp": 200_000, "step": 0}, {"base_exp": 1_200_000, "step": 0}, {"weeks": 3}):
        for item in compute_metrics(_txns(**kwargs)).health_breakdown:
            assert f"{item['key']}_{item['variant']}" in COPY["score_breakdown"]


def test_sentences_carry_the_engine_numbers():
    m = compute_metrics(_txns())
    lines = dict((i["key"], t) for i, (_, t) in zip(m.health_breakdown, breakdown_lines(m.health_breakdown, "ru")))
    margin = next(i for i in m.health_breakdown if i["key"] == "margin")["values"]["margin"]
    assert f"{margin:.1f}%" in lines["margin"]
    assert "{" not in " ".join(lines.values()), "a placeholder was left unfilled"


def test_points_are_signed_like_the_web():
    assert (format_points(-15), format_points(3), format_points(0)) == ("−15", "+3", "0")
    ts = _read("lib/scoreBreakdown.ts")
    assert 'const MINUS = "\\u2212"' in ts and ".toFixed(1)" in ts and "\\u00a0" in ts


def test_the_pdf_prints_the_same_lines():
    m = compute_metrics(_txns()).model_dump(mode="json")
    r = REPORT.model_copy(deep=True)
    r.financial_health_score.score = m["health_score"]
    data = generate_pdf(report=r, metrics=m, language="ru")
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        text = " ".join((p.extract_text() or "") for p in pdf.pages).replace("\n", " ").replace(" ", " ")
    text = " ".join(text.split())
    for points, line in breakdown_lines(m["health_breakdown"], "ru"):
        assert " ".join(line.replace(" ", " ").split()) in text, line


def test_an_old_report_without_a_breakdown_still_renders():
    m = compute_metrics(_txns()).model_dump(mode="json")
    m.pop("health_breakdown")
    assert generate_pdf(report=REPORT, metrics=m, language="ru")[:4] == b"%PDF"


def test_the_web_card_reads_the_shared_copy_not_the_ai():
    card = _read("components/report/HealthScoreCard.tsx")
    assert "breakdownLines(" in card and "score_breakdown.title" in card
    assert "aria-expanded" in card, "the block is collapsible"
    assert "breakdown={metrics.health_breakdown}" in _read("pages/Report.tsx")


# ── Report language ─────────────────────────────────────────────────────────

def test_the_report_carries_the_language_it_was_written_in(monkeypatch, provider_stub):
    monkeypatch.setitem(ai_analyst._PROVIDERS, "openai", lambda u, s: REPORT.model_dump_json())
    monkeypatch.setattr(ai_analyst.settings, "ai_provider", "openai")
    metrics = compute_metrics(_txns()).model_dump(mode="json")
    report = asyncio.run(ai_analyst.get_ai_analysis(metrics=metrics, language="en"))
    assert report.language == "en"
    assert AIReport.model_validate({**REPORT.model_dump(), "language": None}).language is None


def test_the_badge_appears_only_on_a_mismatch():
    badge = _read("components/report/ReportLanguageBadge.tsx")
    assert "language === ui" in badge and "return null" in badge
    for page in ("pages/Report.tsx", "pages/Demo.tsx"):
        assert "<ReportLanguageBadge" in _read(page), page


# ── Dashboard: rename / delete ──────────────────────────────────────────────

POLICIES = next((ROOT / "supabase" / "migrations").glob("*_reports_owner_rename_delete.sql")).read_text(encoding="utf-8")


def test_the_policies_only_add_and_never_toggle_rls():
    assert "row level security" not in POLICIES.lower().replace("-- ", "")  .split("drop policy")[1]
    assert "disable row level security" not in POLICIES and "enable row level security" not in POLICIES
    assert POLICIES.count("create policy") == 3


def test_owners_only():
    for stmt in re.findall(r"create policy .*?;", POLICIES, re.S):
        assert "to authenticated" in stmt and "(select auth.uid())::text" in stmt


def test_zero_rows_is_a_failure_not_a_success():
    db = _read("api/db.ts")
    assert db.count('.select("id")') >= 2 and "(data?.length ?? 0) > 0" in db


def test_delete_asks_first():
    dash = _read("pages/Dashboard.tsx")
    assert "<ConfirmDialog" in dash and "deleteReport(toDelete.id)" in dash


# ── Mobile shell and tap targets ────────────────────────────────────────────

def test_the_sidebar_becomes_a_drawer_below_md():
    shell = _read("components/layout/AppLayout.tsx")
    assert 'className="hidden md:flex h-full"' in shell
    assert 'aria-controls="mobile-nav"' in shell and "anim-drawer-in" in shell


def test_new_motion_is_switched_off_for_reduced_motion():
    css = _read("index.css")
    reduced = css[css.index("@media (prefers-reduced-motion: reduce)"):]
    for cls in (".anim-drawer-in", ".anim-drawer-out"):
        assert cls in reduced


def test_controls_are_44px_on_a_phone():
    assert "max-md:h-11" in _read("components/ui/button.tsx")
    assert "max-md:h-11" in _read("components/ui/input.tsx")
    assert "max-md:min-h-11" in _read("components/ui/tabs.tsx")


def test_tables_become_cards_on_a_phone():
    assert 'className="md:hidden space-y-2"' in _read("components/report/RisksTable.tsx")
    assert 'className="md:hidden space-y-3"' in _read("components/voice/DraftTable.tsx")


def test_drag_is_only_offered_to_a_fine_pointer():
    assert '"(pointer: fine)"' in _read("components/report/LayoutControls.tsx")


# ── The wait is honest ──────────────────────────────────────────────────────

def test_no_made_up_percentage():
    upload = _read("pages/Upload.tsx")
    assert "<Progress" not in upload and "Math.round(progress)" not in upload
    wait = _read("components/upload/AnalysisWait.tsx")
    assert "metrics.total_revenue" in wait and "metrics.transaction_count" in wait


# ── Link previews, favicon, titles ──────────────────────────────────────────

def test_index_carries_static_preview_tags():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    for tag in ("og:title", "og:description", "og:image", "og:url", "twitter:card", 'name="description"'):
        assert tag in html, tag
    for img in ("og-image.png", "og-demo.png", "apple-touch-icon.png", "favicon.svg"):
        assert (WEB / "public" / img).exists(), img


def test_the_demo_gets_its_own_card():
    cfg = (WEB / "vite.config.ts").read_text(encoding="utf-8")
    assert '"demo", "index.html"' in cfg and "og-demo.png" in cfg


def test_the_favicon_uses_only_token_colours():
    tokens = json.loads((ROOT / "design-tokens.json").read_text(encoding="utf-8"))
    allowed = {v.lower() for v in tokens["theme"].values() if isinstance(v, str) and v.startswith("#")}
    allowed.add("#9478b0")   # accent-fg, index.css
    svg = (WEB / "public" / "favicon.svg").read_text(encoding="utf-8")
    used = {c.lower() for c in re.findall(r"#[0-9a-fA-F]{6}", svg)}
    assert used <= allowed, used - allowed


def test_every_page_sets_a_tab_title():
    hook = _read("lib/useDocumentTitle.ts")
    for route in ("/auth", "/dashboard", "/upload", "/report", "/voice-note", "/pricing", "/demo"):
        assert f'"{route}"' in hook, route
    assert "useDocumentTitle()" in _read("App.tsx")


def test_new_charts_stop_animating_for_reduced_motion():
    """Recharts runs its own animation clock and ignores the CSS media query."""
    for rel in ("components/dashboard/ScoreTrend.tsx", "components/report/CashForecastCard.tsx"):
        code = _read(rel)
        assert "useReducedMotion()" in code and "isAnimationActive={!reduced}" in code, rel
