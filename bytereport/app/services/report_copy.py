"""
Reader-facing copy shared with the web app, loaded from repo-root
report-copy.json.

Same arrangement as design_tokens.py, and for the same reason: the frontend
imports the identical file, so the PDF and the page cannot drift apart on what
the analysis claims to be. A hand-kept copy on each side is how "Статус:
critical" and "личные расходы" happened.

The Health Score text lives here rather than in PDF_LABELS because it is not a
label. It is the product stating its own scope, and that statement has to be
word-for-word the same wherever the score appears.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_COPY_PATH = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "report-copy.json"
))

# Mirrors report-copy.json. Only used when the file cannot be read; a test
# pins the two together.
_FALLBACK: dict[str, Any] = {
    "score": {
        "caption": {
            "ru": "По движению денег в выписке за период",
            "uz": "Давр учун кўчирмадаги пул ҳаракати бўйича",
            "en": "Based on cash movement in the statement for the period",
        },
        "scope": {
            "ru": "Быстрый сигнал по денежному потоку из выписки — не замена полному "
                  "бухучёту. Не учитывает дебиторскую и кредиторскую задолженность, "
                  "наличные операции вне счёта и будущие обязательства.",
            "uz": "Кўчирмадаги пул оқими бўйича тезкор сигнал — тўлиқ бухгалтерия "
                  "ҳисобининг ўрнини босмайди. Дебиторлик ва кредиторлик қарздорлик, "
                  "ҳисобдан ташқари нақд операциялар ва келажакдаги мажбуриятлар "
                  "ҳисобга олинмайди.",
            "en": "A quick signal from the cash flow in your statement — not a "
                  "substitute for full bookkeeping. It does not see receivables and "
                  "payables, cash transactions outside the account, or future "
                  "obligations.",
        },
        "scope_title": {
            "ru": "Что охватывает анализ",
            "uz": "Таҳлил нимани қамраб олади",
            "en": "What this analysis covers",
        },
    },
    "cash_forecast": {
        "title_balance": {
            "ru": "Прогноз остатка на счёте по неделям",
            "uz": "Ҳафталар бўйича ҳисобдаги қолдиқ прогнози",
            "en": "Weekly account balance forecast"
        },
        "title_trend": {
            "ru": "Чистый поток по неделям — тренд",
            "uz": "Ҳафталар бўйича соф пул оқими — тенденция",
            "en": "Weekly net cash flow — trend"
        },
        "needs_balance": {
            "ru": "Остаток на счёте не указан, поэтому дата и сумма возможной нехватки денег не рассчитываются. Показан тренд чистого потока: поступления минус платежи за неделю.",
            "uz": "Ҳисобдаги қолдиқ кўрсатилмаган, шунинг учун пул етишмаслигининг санаси ва суммаси ҳисобланмайди. Соф пул оқимининг тенденцияси кўрсатилган: ҳафталик тушумлар минус тўловлар.",
            "en": "No account balance was given, so no date or amount of a possible shortfall is calculated. Shown is the trend of net flow: money in minus money out per week."
        },
        "needs_balance_action": {
            "ru": "Укажите остаток на счёте на конец периода, чтобы увидеть прогноз остатка.",
            "uz": "Қолдиқ прогнозини кўриш учун давр охиридаги ҳисобдаги қолдиқни киритинг.",
            "en": "Enter the account balance at the end of the period to see a balance forecast."
        },
        "from_balance": {
            "ru": "Расчёт от остатка на счёте на конец периода: {amount}.",
            "uz": "Ҳисоб-китоб давр охиридаги ҳисобдаги қолдиқдан: {amount}.",
            "en": "Calculated from the account balance at the end of the period: {amount}."
        },
        "ai_fallback": {
            "ru": "Остаток на счёте не указан, поэтому прогноз нехватки денег по датам и суммам не строится. Тренд чистого потока по неделям — в разделе прогноза денежного потока.",
            "uz": "Ҳисобдаги қолдиқ кўрсатилмаган, шунинг учун пул етишмаслигининг сана ва сумма бўйича прогнози тузилмайди. Ҳафталик соф пул оқими тенденцияси — пул оқими прогнози бўлимида.",
            "en": "No account balance was given, so no shortfall is forecast by date or amount. The weekly net-flow trend is in the cash flow forecast section."
        },
        "engine_gap": {
            "ru": "По расчёту прогноза остаток на счёте уйдёт в минус {date}: не хватит {amount}.",
            "uz": "Прогноз ҳисобига кўра ҳисобдаги қолдиқ {date} манфийга ўтади: {amount} етишмайди.",
            "en": "By the forecast's calculation the account balance goes negative on {date}: short by {amount}."
        },
        "engine_no_gap": {
            "ru": "По расчёту прогноза остаток на счёте не уходит в минус в ближайшие 4 недели.",
            "uz": "Прогноз ҳисобига кўра яқин 4 ҳафтада ҳисобдаги қолдиқ манфийга ўтмайди.",
            "en": "By the forecast's calculation the account balance does not go negative in the next 4 weeks."
        }
    },
    "score_breakdown": {
        "title": {
            "ru": "Из чего сложился балл",
            "uz": "Балл нимадан ташкил топди",
            "en": "How the score was built"
        },
        "intro": {
            "ru": "Старт — 100 баллов, пять проверок по выписке. Итог — {score}.",
            "uz": "Бошланиш — 100 балл, кўчирма бўйича бешта текширув. Якун — {score}.",
            "en": "Starts at 100; five checks on the statement. Result: {score}."
        },
        "margin_negative": {
            "ru": "Операционная маржа {margin}%: расходы больше выручки.",
            "uz": "Операцион маржа {margin}%: харажатлар тушумдан кўп.",
            "en": "Operating margin {margin}%: expenses exceed revenue."
        },
        "margin_below": {
            "ru": "Операционная маржа {margin}% — ниже {threshold}%.",
            "uz": "Операцион маржа {margin}% — {threshold}% дан паст.",
            "en": "Operating margin {margin}% — below {threshold}%."
        },
        "margin_ok": {
            "ru": "Операционная маржа {margin}% — 30% и выше.",
            "uz": "Операцион маржа {margin}% — 30% ва ундан юқори.",
            "en": "Operating margin {margin}% — 30% or more."
        },
        "cash_gaps_some": {
            "ru": "Недель, где платежи превысили поступления: {weeks}.",
            "uz": "Тўловлар тушумдан ошган ҳафталар: {weeks}.",
            "en": "Weeks where payments exceeded receipts: {weeks}."
        },
        "cash_gaps_none": {
            "ru": "Ни одной недели, где платежи превысили поступления.",
            "uz": "Тўловлар тушумдан ошган бирорта ҳафта йўқ.",
            "en": "No week where payments exceeded receipts."
        },
        "revenue_trend_down": {
            "ru": "Выручка последнего месяца {change}% к предыдущему.",
            "uz": "Охирги ой тушуми олдингисига нисбатан {change}%.",
            "en": "Last month's revenue {change}% vs the month before."
        },
        "revenue_trend_up": {
            "ru": "Выручка последнего месяца {change}% к предыдущему — рост больше 10%.",
            "uz": "Охирги ой тушуми олдингисига нисбатан {change}% — ўсиш 10% дан юқори.",
            "en": "Last month's revenue {change}% vs the month before — growth above 10%."
        },
        "revenue_trend_flat": {
            "ru": "Выручка последнего месяца {change}% к предыдущему — без существенных изменений.",
            "uz": "Охирги ой тушуми олдингисига нисбатан {change}% — сезиларли ўзгаришсиз.",
            "en": "Last month's revenue {change}% vs the month before — no significant change."
        },
        "revenue_trend_na": {
            "ru": "Меньше двух месяцев данных — тренд выручки не оценивается.",
            "uz": "Маълумот икки ойдан кам — тушум тенденцияси баҳоланмайди.",
            "en": "Less than two months of data — the revenue trend is not assessed."
        },
        "tax_limit_over": {
            "ru": "Годовой оборот по текущему темпу — {amount}: больше 80% лимита упрощённого налога (1 млрд сум).",
            "uz": "Жорий суръатда йиллик айланма — {amount}: соддалаштирилган солиқ лимитининг (1 млрд сўм) 80% идан кўп.",
            "en": "Annual turnover at the current pace — {amount}: above 80% of the simplified-tax limit (1 bn UZS)."
        },
        "tax_limit_ok": {
            "ru": "Годовой оборот по текущему темпу — {amount}: в пределах 80% лимита упрощённого налога.",
            "uz": "Жорий суръатда йиллик айланма — {amount}: соддалаштирилган солиқ лимитининг 80% и доирасида.",
            "en": "Annual turnover at the current pace — {amount}: within 80% of the simplified-tax limit."
        },
        "volatility_high": {
            "ru": "Самый дорогой по расходам месяц — на {pct}% выше среднего.",
            "uz": "Энг кўп харажатли ой — ўртачадан {pct}% юқори.",
            "en": "The costliest month was {pct}% above the monthly average."
        },
        "volatility_ok": {
            "ru": "Расходы по месяцам ровные: максимум на {pct}% выше среднего.",
            "uz": "Ойлик харажатлар бир текис: энг юқориси ўртачадан {pct}% юқори.",
            "en": "Monthly expenses are steady: the highest was {pct}% above average."
        },
        "volatility_na": {
            "ru": "Один месяц данных — колебания расходов не оцениваются.",
            "uz": "Бир ойлик маълумот — харажатлар тебраниши баҳоланмайди.",
            "en": "One month of data — expense swings are not assessed."
        },
        "capped": {
            "ru": "Итог удержан в пределах шкалы 0–100.",
            "uz": "Якун 0–100 шкаласи доирасида сақланди.",
            "en": "The result is held within the 0–100 scale."
        }
    },
    "credits_exhausted": {
        "free": {
            "ru": "Бесплатные отчёты закончились.",
            "uz": "Бепул ҳисоботлар тугади.",
            "en": "Your free reports are used up."
        },
        "paid": {
            "ru": "Отчёты в пакете закончились.",
            "uz": "Пакетдаги ҳисоботлар тугади.",
            "en": "The reports in your package are used up."
        }
    }
}


def _load() -> dict[str, Any]:
    try:
        with open(_COPY_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "score" in data:
            # A file from before a section existed still gets that section.
            for section, block in _FALLBACK.items():
                data.setdefault(section, block)
            return data
        logger.warning("report-copy.json has an unexpected shape; using fallback")
    except (OSError, ValueError) as exc:
        logger.warning("report-copy.json unavailable (%s); using fallback", exc)
    return _FALLBACK


COPY: dict[str, Any] = _load()


def score_copy(key: str, language: str = "ru") -> str:
    """
    One line of Health Score copy in the requested language.

    Falls back to Russian for an unknown language, never to an empty string: a
    missing scope note is exactly the omission this exists to prevent.
    """
    block = COPY.get("score", {}).get(key) or _FALLBACK["score"].get(key, {})
    return block.get(language) or block.get("ru") or ""


def copy_text(section: str, key: str, language: str = "ru") -> str:
    """Any line of shared copy, e.g. copy_text("cash_forecast", "needs_balance", "uz")."""
    block = COPY.get(section, {}).get(key) or _FALLBACK.get(section, {}).get(key, {})
    return block.get(language) or block.get("ru") or ""


# ── Health Score breakdown ─────────────────────────────────────────────────
# Number formatting lives here and in bytereport-frontend/src/lib/scoreBreakdown.ts,
# and the two are pinned together by a test, so the web and the PDF print the
# same sentence for the same check.

def _fmt_pct(v: float) -> str:
    return f"{float(v):.1f}"


def _fmt_signed(v: float) -> str:
    v = float(v)
    return f"+{v:.1f}" if v > 0 else (f"\u2212{abs(v):.1f}" if v < 0 else "0.0")


def _fmt_amount(v: float) -> str:
    return f"{float(v):,.0f}".replace(",", "\u00a0")


def format_points(points: int) -> str:
    """-15 -> "−15", 3 -> "+3", 0 -> "0"."""
    return f"+{points}" if points > 0 else (f"\u2212{abs(points)}" if points < 0 else "0")


def breakdown_lines(items: list[dict], language: str = "ru") -> list[tuple[int, str]]:
    """(points, sentence) for each check, in the engine's order."""
    out: list[tuple[int, str]] = []
    for item in items or []:
        values = dict(item.get("values") or {})
        if "margin" in values:
            values["margin"] = _fmt_pct(values["margin"])
        if "change" in values:
            values["change"] = _fmt_signed(values["change"])
        if "pct" in values:
            values["pct"] = _fmt_pct(values["pct"])
        if "amount" in values:
            values["amount"] = _fmt_amount(values["amount"])
        template = copy_text("score_breakdown", f"{item['key']}_{item['variant']}", language)
        try:
            text = template.format(**values)
        except (KeyError, IndexError):
            text = template
        out.append((int(item.get("points", 0)), text))
    return out
