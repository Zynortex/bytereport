"""
The AI-CFO chat follows the report's cash rule.

The report stopped naming a date and an amount of a future shortfall without
an account balance; the chat would still answer "when will the money run
out?" with figures of its own. Now:

  * no balance  → the context says so, and any dated or sized shortfall in
                  the answer is removed (same cash_claims rules as the report)
                  and replaced by "enter the balance to see a forecast";
  * a balance   → the answer may name only the engine's date and amounts;
                  anything else is replaced by the engine's own sentence —
                  the figures the forecast card shows.
"""

import asyncio
from datetime import date, timedelta

import pytest

from app.models.transaction import Transaction, TransactionType
from app.services import ai_chat
from app.services.financial_engine import compute_metrics
from app.services.report_copy import copy_text

# These tests replace the provider call with their own stub to check what
# happens around it, so the AI_MOCK fixture answer is switched off here.
pytestmark = pytest.mark.usefixtures("provider_stub")

QUESTION = "Когда у меня закончатся деньги?"


def _metrics(balance=None) -> dict:
    out = []
    for w in range(10):
        d = date(2024, 1, 1) + timedelta(weeks=w)
        out.append(Transaction(date=d, description="Продажи", amount=1_000_000,
                               type=TransactionType.income, category="sales"))
        out.append(Transaction(date=d + timedelta(days=2), description="Материалы",
                               amount=700_000 + 60_000 * w, type=TransactionType.expense, category="materials"))
    return compute_metrics(out, closing_balance=balance).model_dump(mode="json")


def _ask(monkeypatch, metrics: dict, model_answer: str) -> tuple[str, str]:
    seen = {}

    def fake(system, history, message):
        seen["system"] = system
        return model_answer

    monkeypatch.setattr(ai_chat, "_openai_chat", fake)
    monkeypatch.setattr(ai_chat.settings, "ai_provider", "openai")
    answer = asyncio.run(ai_chat.get_chat_response(
        message=QUESTION, history=[], metrics=metrics, ai_report=None,
        business_name="Тест", business_type=None, currency="UZS",
    ))
    return answer, seen["system"]


# ── No balance ──────────────────────────────────────────────────────────────

def test_without_a_balance_the_context_says_so(monkeypatch):
    _, system = _ask(monkeypatch, _metrics(), "Ок.")
    assert "остаток на счёте НЕ указан" in system


def test_without_a_balance_no_date_or_amount_survives(monkeypatch):
    m = _metrics()
    answer, _ = _ask(monkeypatch, m, "Деньги закончатся 20 апреля 2024: не хватит около 180 000 сум. "
                                     "Расходы растут каждую неделю.")
    assert "20 апреля" not in answer and "180 000" not in answer
    assert "Расходы растут каждую неделю." in answer
    assert copy_text("cash_forecast", "needs_balance_action", "ru") in answer


def test_a_plain_answer_is_left_alone(monkeypatch):
    text = "Для прогноза нужен остаток на счёте. Чистый поток падает третью неделю подряд."
    answer, _ = _ask(monkeypatch, _metrics(), text)
    assert answer == text


# ── With a balance ──────────────────────────────────────────────────────────

def test_with_a_balance_the_engine_figures_are_in_the_context(monkeypatch):
    m = _metrics(200_000)
    cf = m["cashflow_forecast"]
    _, system = _ask(monkeypatch, m, "Ок.")
    assert "остаток на счёте на конец периода указан" in system
    assert ai_chat._engine_cash_sentence(cf, "UZS") in system


def test_the_engine_figures_pass_through(monkeypatch):
    m = _metrics(200_000)
    cf = m["cashflow_forecast"]
    line = ai_chat._engine_cash_sentence(cf, "UZS")
    answer, _ = _ask(monkeypatch, m, line + " Советую ввести предоплату.")
    assert answer == line + " Советую ввести предоплату."


def test_the_models_own_figures_are_replaced_by_the_engines(monkeypatch):
    m = _metrics(200_000)
    cf = m["cashflow_forecast"]
    answer, _ = _ask(monkeypatch, m, "Кассовый разрыв ожидается 30 апреля 2024: не хватит 999 999 сум. "
                                     "Советую ввести предоплату.")
    assert "30 апреля" not in answer and "999" not in answer
    assert ai_chat._engine_cash_sentence(cf, "UZS") in answer
    assert "Советую ввести предоплату." in answer


def test_the_engine_sentence_is_what_the_card_shows():
    """Same date and amount as the forecast card (risk_date, risk_amount)."""
    cf = _metrics(200_000)["cashflow_forecast"]
    assert cf["has_risk"]
    line = ai_chat._engine_cash_sentence(cf, "UZS")
    y, mth, d = (int(x) for x in cf["risk_date"].split("-"))
    assert f"{d} " in line and str(y) in line
    assert f"{cf['risk_amount']:,.0f}".replace(",", " ") in line


def test_no_gap_is_said_plainly():
    cf = _metrics(50_000_000)["cashflow_forecast"]
    assert not cf["has_risk"]
    assert ai_chat._engine_cash_sentence(cf, "UZS") == copy_text("cash_forecast", "engine_no_gap", "ru")


def test_one_copy_of_the_rules():
    src = (ai_chat.__file__)
    text = open(src, encoding="utf-8").read()
    assert "from app.services.cash_claims import" in text
    assert "_SHORTAGE" not in text, "the chat must not carry its own copy of the patterns"
