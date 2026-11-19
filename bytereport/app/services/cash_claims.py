"""
No dated or sized cash shortfall without an account balance.

A bank statement shows money moving, not money held. Without the balance at
the end of the period nobody can say WHEN the money runs out or by HOW MUCH —
yet the model would happily write "к 20 мая кассовый разрыв около 180 000",
which a banker reads as a calculated fact. The prompt asks it not to; this
module makes sure, the same way the voice-note guard makes sure about dates.

The rule, applied sentence by sentence when the balance is unknown:

    remove a sentence that talks about running short of money
      AND names a date or an amount
      AND points to the future (a future marker, or a date after the period).

What stays: past facts from the statement ("в феврале расходы превысили
поступления на 165 000"), and forward-looking warnings that name neither a
date nor an amount ("при следующем крупном заказе возможен кассовый разрыв").
"""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import Any, Optional

from pydantic import BaseModel

from app.services.report_copy import copy_text

logger = logging.getLogger(__name__)

# ── What counts as "running short of money" ─────────────────────────────────
_SHORTAGE = re.compile(
    r"кассов\w*\s+разрыв\w*"
    r"|нехватк\w*\s+(?:денег|средств|денежных\s+средств)"
    r"|не\s+хват\w*\s+(?:денег|средств)"
    r"|дефицит\w*\s+(?:денег|средств|ликвидност\w*|денежн\w*)"
    r"|уйд[её]т\w*\s+в\s+минус|окаж\w*\s+в\s+минусе|минусов\w*\s+остат\w*"
    r"|отрицательн\w+\s+(?:остат\w*|баланс\w*)"
    r"|закончатся\s+деньги|деньги\s+закончатся"
    r"|cash\s+(?:gap|shortfall|crunch|shortage)|shortfall"
    r"|run\s+(?:out\s+of|short\s+of)\s+(?:cash|money)"
    r"|negative\s+(?:balance|cash)|go(?:es)?\s+negative"
    r"|пул\s+(?:оқими\s+)?узилиш\w*|нақд\s+пул\s+тақчиллиг\w*|тақчиллик\w*"
    r"|пул\s+етишмовчилиг\w*|пул\s+етишмаслиг\w*|пул\s+етмай\w*"
    r"|манфий\s+(?:қолдиқ|баланс)\w*",
    re.I,
)

# ── What counts as "a date" ─────────────────────────────────────────────────
_MONTHS = {
    # ru / uz Cyrillic stems
    "январ": 1, "феврал": 2, "март": 3, "апрел": 4, "ма": 5, "май": 5, "июн": 6,
    "июл": 7, "август": 8, "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12,
    # en
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_MONTH_WORD = (
    r"(?:январ\w*|феврал\w*|март\w*|апрел\w*|ма[йяе]\w*|июн\w*|июл\w*|август\w*"
    r"|сентябр\w*|октябр\w*|ноябр\w*|декабр\w*"
    r"|jan(?:uary)?|feb(?:ruary)?|march|apr(?:il)?|may|june?|july?|aug(?:ust)?"
    r"|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
)
_RE_DAY_MONTH = re.compile(rf"\b(\d{{1,2}})(?:-?(?:го|e|й))?\s+({_MONTH_WORD})\b", re.I)
_RE_MONTH_DAY = re.compile(rf"\b({_MONTH_WORD})\s+(\d{{1,2}})\b", re.I)
_RE_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
# Two-digit month only ("20.05"), so an amount like "1.5 млн" is not a date.
_RE_DOTTED = re.compile(r"\b(\d{1,2})\.(\d{2})(?:\.(\d{2,4}))?\b")
_RE_MONTH_ALONE = re.compile(rf"\b{_MONTH_WORD}\b", re.I)
_RE_RELATIVE = re.compile(
    r"через\s+(?:\d+|одну|две|два|три|четыре|пять|неделю|месяц)"
    r"|на\s+\d+[-‑]?(?:й|ой)?\s+недел\w*"
    r"|within\s+\d+|in\s+\d+\s+(?:weeks?|days?|months?)|week\s+\d+"
    r"|\d+\s+ҳафта\w*|ҳафтадан\s+кейин",
    re.I,
)

# ── What counts as "an amount" ──────────────────────────────────────────────
_RE_AMOUNT = re.compile(
    r"\d{1,3}(?:[\s  ,]\d{3})+(?:[.,]\d+)?"   # 180 000 / 1,200,000
    r"|\d{4,}"                                           # 180000
    r"|\d+(?:[.,]\d+)?\s*(?:тыс\w*|млн\w*|млрд\w*|минг|миллион\w*|k\b|K\b|mln|million|thousand)",
    re.I,
)

# ── What counts as "the future" ─────────────────────────────────────────────
_RE_FUTURE = re.compile(
    r"прогноз\w*|ожида\w*|будет|будут|станет|возникн\w*|наступ\w*|произойд\w*"
    r"|случит\w*|грозит\w*|не\s+хватит|закончатся|уйд[её]т|окажется"
    r"|может\s+(?:возникнуть|наступить|уйти|случиться|образоваться|оказаться)"
    r"|\bк\s+(?:\d|концу|началу|середине)|в\s+(?:следующ|ближайш)\w*|на\s+следующ\w*"
    r"|\bwill\b|\bwould\b|expected|projected|forecast\w*|likely"
    r"|\bby\s+(?:the\s+)?(?:end|\d|" + _MONTH_WORD + r")|next\s+(?:week|month)"
    r"|кутил\w*|бўлади|юзага\s+кел\w*|келгуси\w*|кейинги\w*|\w+гача\b",
    re.I,
)

_RE_SENTENCES = re.compile(r"(?<=[.!?])\s+(?=[^\s])")


def _period_end(value: Optional[str]) -> Optional[date]:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def _month_of(word: str) -> Optional[int]:
    w = word.lower()
    for stem, n in sorted(_MONTHS.items(), key=lambda kv: -len(kv[0])):
        if w.startswith(stem):
            return n
    return None


def _dates_in(sentence: str, end: Optional[date]) -> list[date]:
    """Calendar dates the sentence names, resolved against the period's year."""
    year = end.year if end else date.today().year
    found: list[date] = []

    def add(y: int, m: int, d: int) -> None:
        try:
            found.append(date(y, m, d))
        except ValueError:
            pass

    for m in _RE_ISO.finditer(sentence):
        add(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    for m in _RE_DOTTED.finditer(sentence):
        y = m.group(3)
        add(int(y) + (2000 if y and len(y) == 2 else 0) if y else year, int(m.group(2)), int(m.group(1)))
    for m in _RE_DAY_MONTH.finditer(sentence):
        month = _month_of(m.group(2))
        if month:
            add(year, month, int(m.group(1)))
    for m in _RE_MONTH_DAY.finditer(sentence):
        month = _month_of(m.group(1))
        if month:
            add(year, month, int(m.group(2)))
    return found


def is_unfounded_cash_claim(sentence: str, period_end: Optional[str] = None) -> bool:
    """True for a dated or sized FUTURE shortfall — what needs a balance to say."""
    if not _SHORTAGE.search(sentence):
        return False
    end = _period_end(period_end)
    dates = _dates_in(sentence, end)
    has_when = bool(dates) or bool(_RE_MONTH_ALONE.search(sentence)) or bool(_RE_RELATIVE.search(sentence))
    has_size = bool(_RE_AMOUNT.search(sentence))
    if not (has_when or has_size):
        return False
    after_period = bool(end) and any(d > end for d in dates)
    return after_period or bool(_RE_FUTURE.search(sentence))


def _clean(text: str, period_end: Optional[str], removed: list[str]) -> str:
    if not text or not _SHORTAGE.search(text):
        return text
    kept: list[str] = []
    for sentence in _RE_SENTENCES.split(text):
        if is_unfounded_cash_claim(sentence, period_end):
            removed.append(sentence)
        else:
            kept.append(sentence)
    return " ".join(kept).strip()


def _walk(obj: BaseModel, period_end: Optional[str], fallback: str,
          removed: list[str], in_list: bool) -> bool:
    """Clean every string; True when a list entry lost a whole field."""
    emptied = False
    for name in type(obj).model_fields:
        value = getattr(obj, name, None)
        if isinstance(value, str):
            new = _clean(value, period_end, removed)
            if new != value:
                if new:
                    setattr(obj, name, new)
                elif in_list:
                    emptied = True
                else:
                    setattr(obj, name, fallback)
        elif isinstance(value, BaseModel):
            _walk(value, period_end, fallback, removed, in_list=False)
        elif isinstance(value, list):
            kept: list[Any] = []
            for item in value:
                if isinstance(item, BaseModel):
                    if not _walk(item, period_end, fallback, removed, in_list=True):
                        kept.append(item)
                elif isinstance(item, str):
                    new = _clean(item, period_end, removed)
                    if new:
                        kept.append(new)
                else:
                    kept.append(item)
            if len(kept) != len(value):
                setattr(obj, name, kept)
    return emptied


def strip_unfounded_cash_claims(
    report: BaseModel, *, language: str = "ru", period_end: Optional[str] = None,
) -> list[str]:
    """
    Remove dated or sized future-shortfall sentences from a report, in place.

    A list entry (insight, risk, action...) whose field is emptied entirely is
    dropped — it was about the claim. A single field emptied entirely (e.g. the
    cash-flow summary) gets the shared explanation instead. Returns what was
    removed; each removal is logged, since it means the prompt was ignored.
    """
    removed: list[str] = []
    fallback = copy_text("cash_forecast", "ai_fallback", language)
    _walk(report, period_end, fallback, removed, in_list=False)
    for sentence in removed:
        logger.warning("AI report: removed an unfounded cash-shortfall claim: %r", sentence[:200])
    return removed


# ── Plain text (the AI-CFO chat) ────────────────────────────────────────────
#
# The report is a model with fields; a chat answer is one string. Same rules,
# same patterns — no second copy of them.

def strip_unfounded_cash_text(text: str, period_end: Optional[str] = None) -> tuple[str, list[str]]:
    """Remove dated or sized future-shortfall sentences from a plain string."""
    removed: list[str] = []
    cleaned = _clean(text, period_end, removed)
    return cleaned, removed


_UNITS = {"тыс": 1e3, "минг": 1e3, "k": 1e3, "thousand": 1e3,
          "млн": 1e6, "миллион": 1e6, "mln": 1e6, "m": 1e6, "million": 1e6,
          "млрд": 1e9, "billion": 1e9, "bn": 1e9}
_RE_NUM = re.compile(
    r"(?<![\d.,])(\d{1,3}(?:[\s\u00a0\u202f]\d{3})+|\d{1,3}(?:,\d{3})+(?![\d])|\d+(?:[.,]\d+)?)"
    r"\s*(тыс\w*|минг|млн\w*|миллион\w*|млрд\w*|thousand|million|billion|mln|bn|k\b|m\b)?",
    re.I,
)
_RE_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_RE_PCT = re.compile(r"\d+(?:[.,]\d+)?\s*%")


def _amounts_in(sentence: str) -> list[float]:
    """Money-looking numbers in a sentence, with тыс/млн/k/m units applied."""
    text = sentence
    for pattern in (_RE_ISO, _RE_DOTTED, _RE_DAY_MONTH, _RE_MONTH_DAY, _RE_PCT, _RE_YEAR):
        text = pattern.sub(" ", text)
    text = re.sub(r"(?:week|недел\w*|ҳафта\w*)\s*\d+|\d+\s*(?:-?й|-?ой)?\s*(?:недел\w*|week\w*|ҳафта\w*)", " ", text, flags=re.I)
    out: list[float] = []
    for m in _RE_NUM.finditer(text):
        raw, unit = m.group(1), (m.group(2) or "").lower()
        digits = re.sub(r"[\s\u00a0\u202f]", "", raw)
        if re.fullmatch(r"\d{1,3}(?:,\d{3})+", digits):
            value = float(digits.replace(",", ""))
        else:
            value = float(digits.replace(",", "."))
        for stem, mult in _UNITS.items():
            if unit.startswith(stem):
                value *= mult
                break
        if value >= 1000 or unit:   # small bare numbers are counts, not money
            out.append(value)
    return out


def enforce_engine_cash_figures(text: str, forecast: dict, period_end: Optional[str] = None) -> tuple[str, list[str]]:
    """
    With a known balance: a future-shortfall sentence may name only the date
    and the amounts the engine computed (risk_date / projected dates, the
    shortfall, projected balances, the opening balance). Anything else is the
    model's own arithmetic and is removed.
    """
    end = _period_end(period_end)
    allowed_dates: set[date] = set()
    for value in [forecast.get("risk_date")] + [w.get("projected_date") for w in forecast.get("weekly_projection") or []]:
        d = _period_end(value)
        if d:
            allowed_dates.add(d)
    allowed_amounts = [abs(float(v)) for v in
                       [forecast.get("risk_amount"), forecast.get("closing_balance")]
                       + [w.get("projected_balance") for w in forecast.get("weekly_projection") or []]
                       if v is not None]

    def matches(amount: float) -> bool:
        return any(abs(amount - a) <= max(1.0, 0.01 * a) for a in allowed_amounts)

    removed: list[str] = []
    kept: list[str] = []
    for sentence in _RE_SENTENCES.split(text):
        if is_unfounded_cash_claim(sentence, period_end):
            dates = _dates_in(sentence, end)
            amounts = _amounts_in(sentence)
            bad_date = any(d not in allowed_dates for d in dates)
            bad_amount = any(not matches(a) for a in amounts)
            if bad_date or bad_amount:
                removed.append(sentence)
                continue
        kept.append(sentence)
    return " ".join(kept).strip(), removed
