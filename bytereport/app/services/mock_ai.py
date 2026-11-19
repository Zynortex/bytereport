"""
AI_MOCK=1: canned AI answers, no provider call, no key, no spend.

For local runs, the test suite and layout checks. Each builder returns a
caller with the same signature as the real provider function it stands in
for, and produces the same raw shape the model would — so everything after
the call (JSON repair, validation, scrubbing, cash-claim guards, stamping the
language and the health label) still runs on it. Only the network is skipped.

Numbers come from the user's own computed metrics and are the engine's, as in
a real report; the prose around them is a template from
app/fixtures/ai_mock.json, and every piece of it says it is a test answer, so
a mocked report can never be mistaken for a real one.
"""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "ai_mock.json"
LANGS = ("ru", "uz", "en")

# Counted so tests (and a curious developer) can see the mock was the one
# that answered. Never reset in production code; tests read the delta.
calls: dict[str, int] = {"report": 0, "chat": 0, "note": 0, "photo": 0, "transcribe": 0}


@lru_cache(maxsize=1)
def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _lang(language: str | None) -> str:
    return language if language in LANGS else "ru"


def _money(value: float, currency: str) -> str:
    sign = "−" if float(value) < 0 else ""
    return sign + f"{abs(float(value)):,.0f}".replace(",", " ") + f" {currency}"


class _Blank(dict):
    """str.format_map that leaves an unknown {key} visible instead of raising."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _fill(template: str, values: dict) -> str:
    return template.format_map(_Blank(values))


def _top(rows: list, fallback: str) -> dict:
    rows = [r for r in rows or [] if isinstance(r, dict) and r.get("category")]
    if not rows:
        return {"category": fallback, "total": 0.0, "percentage": 0.0}
    return max(rows, key=lambda r: float(r.get("total") or 0))


def _values(metrics: dict, currency: str, lang: str) -> dict:
    none = {"ru": "нет данных", "uz": "маълумот йўқ", "en": "no data"}[lang]
    top_exp = _top(metrics.get("expense_by_category"), none)
    top_inc = _top(metrics.get("revenue_by_category"), none)
    anomalies = [a for a in metrics.get("anomalies") or [] if isinstance(a, dict)]
    first = anomalies[0] if anomalies else {}
    change = first.get("change_pct")
    return {
        "period": f"{metrics.get('period_start', '')} — {metrics.get('period_end', '')}",
        "revenue": _money(metrics.get("total_revenue", 0), currency),
        "expenses": _money(metrics.get("total_expenses", 0), currency),
        "profit": _money(metrics.get("profit", 0), currency),
        "margin": f"{float(metrics.get('profit_margin', 0)):.1f}",
        "top_expense": top_exp["category"],
        "top_expense_total": _money(top_exp.get("total", 0), currency),
        "top_expense_share": f"{float(top_exp.get('percentage') or 0):.0f}",
        "top_income": top_inc["category"],
        "top_income_total": _money(top_inc.get("total", 0), currency),
        "five_pct": _money(float(top_exp.get("total") or 0) * 0.05, currency),
        "anomaly_category": first.get("category", none),
        "anomaly_month": first.get("month", ""),
        "anomaly_change": f"{change:+.0f}%" if isinstance(change, (int, float)) else "—",
        "_has_anomaly": bool(anomalies),
        "_anomaly_severity": first.get("severity", "low"),
    }


# ── Full report ─────────────────────────────────────────────────────────────

def report_json(metrics: dict, language: str, currency: str) -> str:
    """The raw JSON the model would return for this report."""
    lang = _lang(language)
    t = _fixture()["report"][lang]
    v = _values(metrics, currency, lang)
    f = lambda key: _fill(t[key], v)  # noqa: E731
    neg = float(metrics.get("profit", 0)) < 0

    data: dict[str, Any] = {
        "executive_summary": f("executive_summary"),
        "financial_health_score": {
            "score": int(metrics.get("health_score", 0)),
            # Overwritten by the backend with the engine's own label.
            "status": "",
            "reasoning": f("reasoning"),
        },
        "key_insights": [
            {"title": f("insight_title"), "severity": "medium", "explanation": f("insight_text")},
            {"title": f("insight2_title"), "severity": "low", "explanation": f("insight2_text")},
        ],
        "top_risks": [
            {"risk": f("risk"), "impact": f("risk_impact"), "recommendation": f("risk_rec")},
        ],
        "growth_opportunities": [
            {"opportunity": f("opportunity"), "potential_impact": f("opportunity_impact"),
             "action": f("opportunity_action")},
        ],
        "expense_analysis": {
            "problem_categories": [v["top_expense"]] if metrics.get("expense_by_category") else [],
            "efficient_categories": [],
            "notes": f("expense_notes"),
        },
        "anomalies": (
            [{"category": v["anomaly_category"], "issue": f("anomaly_issue"),
              "severity": v["_anomaly_severity"], "explanation": f("anomaly_text")}]
            if v["_has_anomaly"] else []
        ),
        "cash_flow_analysis": {
            "status": f("cash_status"),
            "summary": f("cash_summary"),
            "warning_level": "high" if neg else "low",
        },
        "forecast": {"outlook": f("outlook"), "confidence": "low", "summary": f("forecast_summary")},
        "priority_actions": [
            {"priority": 1, "action": f("action1"), "expected_result": f("action1_result")},
            {"priority": 2, "action": f("action2"), "expected_result": f("action2_result")},
        ],
    }
    return json.dumps(data, ensure_ascii=False)


def report_caller(metrics: dict, language: str, currency: str) -> Callable[[str, str], str]:
    """Stands in for ai_analyst._call_openai(user_message, system_prompt)."""

    def call(_user_message: str, _system_prompt: str) -> str:
        calls["report"] += 1
        logger.info("AI_MOCK: report answered from the fixture (%s)", language)
        return report_json(metrics, language, currency)

    return call


# ── Chat ────────────────────────────────────────────────────────────────────

_UZ_LETTERS = re.compile(r"[ўғқҳЎҒҚҲ]")
_CYRILLIC = re.compile(r"[а-яёА-ЯЁ]")


def guess_language(text: str, fallback: str | None = None) -> str:
    if _UZ_LETTERS.search(text or ""):
        return "uz"
    if _CYRILLIC.search(text or ""):
        return "ru"
    if re.search(r"[A-Za-z]", text or ""):
        return "en"
    return _lang(fallback)


def chat_caller(metrics: dict, ai_report: dict | None, currency: str) -> Callable[..., str]:
    """Stands in for ai_chat._openai_chat(system, history, message)."""
    report_lang = (ai_report or {}).get("language")

    def call(_system: str, _history: list, message: str) -> str:
        calls["chat"] += 1
        lang = guess_language(message, report_lang)
        return _fill(_fixture()["chat"][lang], _values(metrics, currency, lang))

    return call


# ── Note / photo / voice ────────────────────────────────────────────────────

def note_json(language: str, currency: str, today_iso: str) -> str:
    """Two rows in the voice-parser schema, in the business currency (no FX call)."""
    lang = _lang(language)
    n = _fixture()["note"][lang]
    row = lambda amount, direction, desc, cat: {  # noqa: E731
        "date": today_iso, "date_source": "stated", "amount": amount, "currency": currency,
        "direction": direction, "description": desc, "category": cat,
        "uncertain": [], "notes": {},
    }
    return json.dumps({
        "transactions": [
            row(500000, "income", n["income"], n["income_cat"]),
            row(80000, "expense", n["expense"], n["expense_cat"]),
        ],
        "warnings": [n["warning"]],
    }, ensure_ascii=False)


def note_caller(language: str, currency: str, today_iso: str) -> Callable[[str, str], str]:
    def call(_user_message: str, _system_prompt: str) -> str:
        calls["note"] += 1
        return note_json(language, currency, today_iso)

    return call


def photo_caller(language: str, currency: str, today_iso: str) -> Callable[[str, str], str]:
    """Stands in for photo_parser._call_openai_vision(data_url, user_text)."""

    def call(_data_url: str, _user_text: str) -> str:
        calls["photo"] += 1
        return note_json(language, currency, today_iso)

    return call


def transcribe_caller(language: str | None) -> Callable[..., tuple[str, str | None]]:
    """Stands in for transcription._transcribe_sync(audio, suffix, language)."""

    def call(_audio: bytes, _suffix: str, _language: str | None) -> tuple[str, str | None]:
        calls["transcribe"] += 1
        lang = _lang(language)
        return _fixture()["transcript"][lang], lang

    return call
