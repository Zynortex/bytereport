"""
The cash forecast claims only what the data supports.

The bug: the forecast started from `current_balance=profit` — the period's
profit standing in for an account balance the statement does not contain —
so "кассовый разрыв 20 мая на 180 000" was arithmetic on a made-up number.
A former banker's first objection to the product was exactly this: figures
that look more precise than the data allows.

Now:
  * with the account balance at the end of the period, the forecast is a
    balance forecast, from that balance;
  * without it, it is a TREND of weekly net flow — no date, no amount —
    on the web, in the PDF, and in the AI text (enforced in code, not only
    asked for in the prompt).
"""

import asyncio
import io
import json
import pathlib
from datetime import date, timedelta

import pdfplumber
import pytest
from fastapi.testclient import TestClient

from app.models.report import AIReport
from app.models.transaction import Transaction, TransactionType
from app.services import ai_analyst
from app.services.cash_claims import is_unfounded_cash_claim, strip_unfounded_cash_claims
from app.services.financial_engine import compute_metrics
from app.services.pdf_generator import generate_pdf
from app.services.report_copy import copy_text
from main import app
from tests.test_report_layout import REPORT

# These tests replace the provider call with their own stub to check what
# happens around it, so the AI_MOCK fixture answer is switched off here.
pytestmark = pytest.mark.usefixtures("provider_stub")

ROOT = pathlib.Path(__file__).resolve().parents[2]
WEB = ROOT / "bytereport-frontend" / "src"
client = TestClient(app)

START = date(2024, 1, 1)


def _txns() -> list[Transaction]:
    """Ten weeks: steady income, expenses climbing — a falling net flow."""
    out = []
    for week in range(10):
        day = START + timedelta(weeks=week)
        out.append(Transaction(date=day, description="Продажи", amount=1_000_000,
                               type=TransactionType.income, category="sales"))
        out.append(Transaction(date=day + timedelta(days=2), description="Материалы",
                               amount=700_000 + 60_000 * week,
                               type=TransactionType.expense, category="materials"))
    return out


# ── Engine ──────────────────────────────────────────────────────────────────

def test_without_a_balance_there_is_no_date_and_no_amount():
    cf = compute_metrics(_txns()).cashflow_forecast
    assert cf.balance_known is False
    assert cf.closing_balance is None
    assert (cf.has_risk, cf.risk_date, cf.risk_amount) == (False, None, None)
    assert all(w["projected_balance"] is None for w in cf.weekly_projection)
    assert all(isinstance(w["projected_net"], float) for w in cf.weekly_projection)


def test_the_period_profit_is_no_longer_used_as_a_balance():
    m = compute_metrics(_txns())
    assert m.profit != 0
    assert all(w["projected_balance"] is None for w in m.cashflow_forecast.weekly_projection)


def test_with_a_balance_the_forecast_starts_from_it():
    cf = compute_metrics(_txns(), closing_balance=500_000).cashflow_forecast
    assert cf.balance_known is True and cf.closing_balance == 500_000
    running = 500_000.0
    for w in cf.weekly_projection:
        running = round(running + w["projected_net"], 2)
        assert w["projected_balance"] == running


def test_a_balance_that_runs_out_is_dated_and_sized():
    cf = compute_metrics(_txns(), closing_balance=200_000).cashflow_forecast
    assert cf.has_risk is True
    first_negative = next(w for w in cf.weekly_projection if w["projected_balance"] < 0)
    assert cf.risk_date == first_negative["projected_date"]
    assert cf.risk_amount == abs(first_negative["projected_balance"])


def test_a_large_balance_has_no_risk():
    cf = compute_metrics(_txns(), closing_balance=50_000_000).cashflow_forecast
    assert cf.has_risk is False and cf.risk_date is None


def test_the_trend_is_the_same_either_way():
    a = compute_metrics(_txns()).cashflow_forecast.weekly_projection
    b = compute_metrics(_txns(), closing_balance=1).cashflow_forecast.weekly_projection
    assert [w["projected_net"] for w in a] == [w["projected_net"] for w in b]


def test_an_old_saved_forecast_reads_as_unknown_balance():
    from app.models.metrics import CashflowForecast

    old = CashflowForecast.model_validate({
        "has_risk": True, "risk_date": "2024-05-20", "risk_amount": 180000,
        "weekly_projection": [], "confidence": "LOW",
    })
    assert old.balance_known is False


# ── API ─────────────────────────────────────────────────────────────────────

def _payload(**extra):
    return {"transactions": [json.loads(t.model_dump_json()) for t in _txns()], **extra}


def test_analyze_accepts_the_balance():
    without = client.post("/analyze", json=_payload()).json()["cashflow_forecast"]
    with_ = client.post("/analyze", json=_payload(closing_balance=200_000)).json()["cashflow_forecast"]
    assert without["balance_known"] is False and without["risk_date"] is None
    assert with_["balance_known"] is True and with_["risk_date"]


def test_the_forecast_can_be_recomputed_without_a_new_report():
    m = client.post("/analyze", json=_payload()).json()
    resp = client.post("/analyze/forecast", json={
        "weekly_breakdown": m["weekly_breakdown"], "period_end": m["period_end"],
        "closing_balance": 200_000,
    })
    assert resp.status_code == 200
    cf = resp.json()
    assert cf["balance_known"] is True and cf["has_risk"] is True
    # Same arithmetic as a full run with the balance up front.
    full = client.post("/analyze", json=_payload(closing_balance=200_000)).json()["cashflow_forecast"]
    assert cf["weekly_projection"] == full["weekly_projection"]


def test_recomputing_needs_no_account_and_no_credit():
    """No auth dependency: it is arithmetic, and it must not cost a report."""
    m = client.post("/analyze", json=_payload()).json()
    resp = client.post("/analyze/forecast", json={
        "weekly_breakdown": m["weekly_breakdown"], "period_end": m["period_end"],
    })
    assert resp.status_code == 200 and resp.json()["balance_known"] is False


# ── The AI text guard ───────────────────────────────────────────────────────

END = "2024-03-31"


@pytest.mark.parametrize("sentence", [
    "К 20 мая ожидается кассовый разрыв около 180 000 сум.",
    "Через три недели возникнет нехватка денег на 1,2 млн.",
    "В мае баланс уйдёт в минус на 180 000.",
    "Прогноз: отрицательный остаток 40 000 на 13.05.",
    "A cash gap of about 180,000 is expected by May 20.",
    "The balance will go negative in week 3, short by 95,000.",
    "20 майгача тахминан 180 000 сўм нақд пул тақчиллиги кутилмоқда.",
])
def test_a_dated_or_sized_future_shortfall_is_removed(sentence):
    assert is_unfounded_cash_claim(sentence, END)


@pytest.mark.parametrize("sentence", [
    # A fact from the statement: past, not a forecast.
    "В феврале был кассовый разрыв: расходы превысили доходы на 165 000.",
    "In February there was a cash gap of 165,000 between payment and delivery.",
    # A warning with no date and no amount.
    "При следующем крупном заказе без предоплаты возможен кассовый разрыв.",
    # Not about running short at all.
    "Прогноз выручки на май: 1.3 млн.",
    "Сократить закупки на 15% = экономия 48 000 UZS/мес.",
])
def test_facts_and_plain_warnings_stay(sentence):
    assert not is_unfounded_cash_claim(sentence, END)


def _report_with_claims() -> AIReport:
    data = REPORT.model_dump()
    data["executive_summary"] = (
        "Квартал закрыт с прибылью 665 000. "
        "К 20 мая ожидается кассовый разрыв около 180 000 сум."
    )
    data["cash_flow_analysis"]["summary"] = "К 20 мая ожидается кассовый разрыв около 180 000."
    data["top_risks"] = [
        {"risk": "Кассовый разрыв 20 мая на 180 000 будет неизбежен.", "impact": "x", "recommendation": "y"},
        {"risk": "Зависимость от одного типа заказов", "impact": "71.9% выручки", "recommendation": "z"},
    ]
    return AIReport.model_validate(data)


def test_the_report_is_cleaned_field_by_field():
    r = _report_with_claims()
    removed = strip_unfounded_cash_claims(r, language="ru", period_end=END)
    assert len(removed) == 3
    assert r.executive_summary == "Квартал закрыт с прибылью 665 000."
    # A whole field gone: the shared explanation takes its place.
    assert r.cash_flow_analysis.summary == copy_text("cash_forecast", "ai_fallback", "ru")
    # A risk that WAS the claim is dropped; the other stays.
    assert [x.risk for x in r.top_risks] == ["Зависимость от одного типа заказов"]


def _run_analysis(monkeypatch, metrics: dict):
    seen = {}

    def fake(user_message, system_prompt):
        seen["system"] = system_prompt
        return _report_with_claims().model_dump_json()

    monkeypatch.setitem(ai_analyst._PROVIDERS, "openai", fake)
    monkeypatch.setattr(ai_analyst.settings, "ai_provider", "openai")
    report = asyncio.run(ai_analyst.get_ai_analysis(metrics=metrics, language="ru"))
    return report, seen["system"]


def test_without_a_balance_the_analysis_cannot_carry_the_claim(monkeypatch):
    metrics = compute_metrics(_txns()).model_dump(mode="json")
    report, system = _run_analysis(monkeypatch, metrics)
    assert "ОСТАТОК НА СЧЁТЕ НЕ УКАЗАН" in system
    assert "180 000" not in report.executive_summary
    assert all("20 мая" not in x.risk for x in report.top_risks)


def test_with_a_balance_the_analysis_is_left_alone(monkeypatch):
    metrics = compute_metrics(_txns(), closing_balance=200_000).model_dump(mode="json")
    report, system = _run_analysis(monkeypatch, metrics)
    assert "ОСТАТОК НА СЧЁТЕ НА КОНЕЦ ПЕРИОДА указан" in system
    assert "20 мая" in report.executive_summary


def test_negative_weeks_are_not_called_a_balance_in_the_prompt(monkeypatch):
    metrics = compute_metrics(_txns()).model_dump(mode="json")
    _, system = _run_analysis(monkeypatch, metrics)
    assert "Недели с отрицательным балансом" not in system
    assert "это НЕ остаток на счёте" in system


# ── PDF and web say the same thing ─────────────────────────────────────────

def _pdf(metrics: dict, lang="ru") -> str:
    data = generate_pdf(report=REPORT, metrics=metrics, language=lang)
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        return " ".join((p.extract_text() or "") for p in pdf.pages).replace("\n", " ")


def _norm(s: str) -> str:
    return " ".join(s.replace(" ", " ").split())


def test_the_pdf_without_a_balance_shows_the_trend_and_why():
    text = _norm(_pdf(compute_metrics(_txns()).model_dump(mode="json")))
    assert _norm(copy_text("cash_forecast", "title_trend", "ru")) in text
    assert "дата и сумма возможной нехватки денег не рассчитываются" in text
    assert _norm(copy_text("cash_forecast", "title_balance", "ru")) not in text


def test_the_pdf_with_a_balance_states_where_it_starts():
    text = _norm(_pdf(compute_metrics(_txns(), closing_balance=200_000).model_dump(mode="json")))
    assert _norm(copy_text("cash_forecast", "title_balance", "ru")) in text
    assert "200 000" in text


@pytest.mark.parametrize("lang", ["uz", "en"])
def test_the_pdf_note_is_translated(lang):
    text = _norm(_pdf(compute_metrics(_txns()).model_dump(mode="json"), lang))
    assert _norm(copy_text("cash_forecast", "title_trend", lang)) in text


def test_the_web_reads_the_same_lines():
    card = (WEB / "components" / "report" / "CashForecastCard.tsx").read_text(encoding="utf-8")
    for key in ("title_balance", "title_trend", "needs_balance", "needs_balance_action", "from_balance"):
        assert f'"cash_forecast.{key}"' in card, key
    i18n = (WEB / "i18n.ts").read_text(encoding="utf-8")
    assert "report-copy.json" in i18n


def test_every_line_exists_in_every_language():
    data = json.loads((ROOT / "report-copy.json").read_text(encoding="utf-8"))["cash_forecast"]
    for key, block in data.items():
        if key.startswith("_"):
            continue
        assert set(block) == {"ru", "uz", "en"} and all(block.values()), key


def test_the_web_hides_the_risk_banner_without_a_balance():
    card = (WEB / "components" / "report" / "CashForecastCard.tsx").read_text(encoding="utf-8")
    known_branch = card.index("{known ? (")
    risk = card.index("cashflow_risk_prefix")
    trend = card.index('"cash_forecast.needs_balance"')
    assert known_branch < risk < trend, "the dated warning must live only in the balance branch"
