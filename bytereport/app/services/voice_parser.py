"""
Free-form note -> draft transactions, via the configured LLM.

Mirrors the conventions ai_analyst.py already established: the provider SDK is
synchronous, so the call goes to a worker thread; retries are off so a stall
cannot occupy three timeouts behind a spinner; token usage is logged from the
provider's own `usage` object rather than estimated.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import date

from app.core.config import settings
from app.models.voice_note import DraftTransaction
from app.services import fx, mock_ai
from app.services.cost import log_usage
from app.utils.json_repair import safe_json_loads

logger = logging.getLogger(__name__)

# A note is a sentence or two, not a statement. Anything past this is either a
# pasted spreadsheet — which belongs in the ordinary upload flow — or an
# accident, and both would burn tokens for nothing.
MAX_NOTE_CHARS = 4000

_LANGUAGE_NAMES = {
    "uz": "Uzbek (Cyrillic script)",
    "ru": "Russian",
    "en": "English",
}

SYSTEM_PROMPT = """\
You turn a short spoken or hand-written note about money into structured rows.

Return ONLY valid JSON, no prose, no markdown fence:

{
  "transactions": [
    {
      "date": "YYYY-MM-DD" or null,
      "date_source": "stated" | "relative" | "assumed",
      "amount": number or null,
      "currency": "USD" | "EUR" | "RUB" | "KZT" | "UZS" or null,
      "direction": "income" | "expense",
      "description": "what this was, in the note's own words",
      "category": "short category" or null,
      "uncertain": ["date", "amount", "direction", "description", "category"],
      "notes": {"field": "one short clause on why you are unsure"}
    }
  ],
  "warnings": ["anything about the note as a whole"]
}

RULES

1. One row per movement of money. "Got 500 for the sofa and spent 80 on
   delivery" is TWO rows, not one net row.
2. `amount` is always positive. `direction` carries the sign.
3. Numbers spoken loosely are still numbers: "500 тысяч" -> 500000,
   "полтора миллиона" -> 1500000, "80к" -> 80000. If the scale is genuinely
   ambiguous, pick the most likely reading AND flag "amount".
3a. `currency` is the currency the NOTE names for that row ("двести долларов"
   -> "USD"). Resolve the scale first and report the amount in that currency —
   do NOT attempt any conversion yourself, and do not flag "amount" merely
   because the currency is foreign. When the note names no currency, use null:
   the caller supplies the business currency.
4. `date`: resolve relative expressions ("вчера", "kecha", "last Tuesday")
   against TODAY, given below. If the row's own words give NO date at all, use
   null and flag "date" — do NOT quietly substitute today. Today's date is
   context for arithmetic, never a default value.
   A vague reference ("в среду вроде") IS a date: resolve it to your best guess
   AND flag "date".
4a. `date_source` says where the date came from, and it is checked:
   "stated"   — a date was printed or spoken outright ("26.08.2026", "5 марта",
                "сегодня"). Use this ONLY when the source really carries one.
   "relative" — you derived it from words like "вчера" or "в среду".
   "assumed"  — you had nothing to go on. Then `date` must be null.
   Claiming "stated" for a date you inferred is the one error here that cannot
   be caught downstream.
5. `uncertain` lists FIELD NAMES you are not confident about, and only those.
   An empty list means every field is solid. Be honest: a guessed category, a
   misheard name, an implied direction all belong here. Flagging nothing on a
   vague note is worse than over-flagging.
6. `notes` is optional and keyed by the same field names. Keep each under 60
   characters — it is rendered inline next to the value.
7. `description` stays in the language of the note. Never invent detail the
   note does not contain.
8. If the note describes no money movement at all, return an empty
   transactions list and say so in `warnings`.

WORKED EXAMPLE — note: "получил от Азиза 500 тысяч за диван, вчера отдал
80 тысяч за доставку" with TODAY 2026-08-25:

{"transactions": [
  {"date": null, "amount": 500000, "direction": "income",
   "description": "от Азиза за диван", "category": "продажи",
   "uncertain": ["date"], "notes": {"date": "дата не названа"}},
  {"date": "2026-08-24", "amount": 80000, "direction": "expense",
   "description": "доставка", "category": "логистика",
   "uncertain": [], "notes": {}}
], "warnings": []}

Note what the first row does NOT do: it does not borrow 2026-08-25 from TODAY,
and it does not borrow "вчера" from the second half of the sentence. Each row
gets only the date its own words carry.
"""


def _build_user_message(text: str, language: str, currency: str, today: date) -> str:
    lang_name = _LANGUAGE_NAMES.get(language, _LANGUAGE_NAMES["ru"])
    return (
        f"TODAY: {today.isoformat()}\n"
        f"Currency: {currency}\n"
        f"Write `description`, `category`, `warnings` and `notes` in {lang_name}.\n\n"
        f"NOTE:\n{text}\n\n"
        "Return the JSON object now."
    )


def _call_openai(user_message: str, system_prompt: str) -> str:
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError("openai package not installed. Run: pip install openai")

    client = OpenAI(
        api_key=settings.openai_api_key,
        timeout=settings.ai_timeout_seconds,
        max_retries=0,   # same rationale as ai_analyst._call_openai
    )
    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        # A note yields a handful of rows; the report prompt's 16k ceiling would
        # only ever pay for headroom nothing uses.
        max_completion_tokens=2000,
        response_format={"type": "json_object"},
    )
    log_usage(response, settings.openai_model)
    return response.choices[0].message.content or ""


def _call_anthropic(user_message: str, system_prompt: str) -> str:
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic package not installed. Run: pip install anthropic")

    from app.services.cost import log_anthropic_usage

    client = anthropic.Anthropic(
        api_key=settings.anthropic_api_key,
        timeout=settings.ai_timeout_seconds,
        max_retries=0,
    )
    message = client.messages.create(
        model=settings.claude_model,
        max_tokens=2000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
        temperature=0.1,
    )
    log_anthropic_usage(message, settings.claude_model)
    return message.content[0].text


_PROVIDERS = {"openai": _call_openai, "anthropic": _call_anthropic}


# Note attached when the guard below fires, in the note's own language.
_TODAY_GUARD_NOTE = {
    "ru": "подставлена сегодняшняя дата — проверьте",
    "uz": "бугунги сана қўйилди — текширинг",
    "en": "today's date was assumed — please check",
}


def _flag_assumed_today(
    row: DraftTransaction, today: date, language: str
) -> DraftTransaction:
    """
    Flag a date that equals TODAY and was not flagged by the model.

    Rule 4 of the prompt forbids defaulting an undated row to today, and the
    model breaks it anyway — verified against the live API before and after
    strengthening the wording with a worked example. An undated row that comes
    back stamped with today's date and no flag looks exactly like a row the
    user actually dated, which is the one failure this feature cannot afford.

    Today's date is the single value the model can produce by defaulting rather
    than by reading, so equality with it is a usable signal. The cost of being
    wrong is asymmetric: over-flagging is cheap — the user glances at the cell
    and the flag clears — while a silent wrong date propagates into the
    workbook and into any later analysis.

    But cheap is not free. On a photographed receipt the printed date is very
    often today, so the bare heuristic fired on almost every same-day receipt
    and would have trained people to dismiss the flag — which costs exactly the
    cases it was built for. Hence `date_source`: the model must actively claim
    it read a date to suppress the flag, and a missing or "assumed" claim
    leaves the heuristic in charge. Requiring a positive assertion is stronger
    than requiring the model to remember a prohibition, which is what failed
    when this was prompt-only.
    """
    # A date the model says it actually read is evidence; the heuristic below
    # exists precisely because a silently defaulted date offers none.
    if row.date_source in ("stated", "relative"):
        return row
    if row.date != today.isoformat() or "date" in row.uncertain:
        return row
    return row.model_copy(update={
        "uncertain": [*row.uncertain, "date"],
        "notes": {
            **row.notes,
            "date": row.notes.get("date") or _TODAY_GUARD_NOTE.get(
                language, _TODAY_GUARD_NOTE["ru"]
            ),
        },
    })


def _coerce_rows(
    data: dict, today: date | None = None, language: str = "ru"
) -> tuple[list[DraftTransaction], list[str]]:
    """
    Turn the model's JSON into drafts, dropping only what cannot be a row.

    A single malformed entry must not lose the other four: the user would have
    to re-record the whole note. Each failure becomes a warning instead.
    """
    warnings = [w for w in data.get("warnings", []) if isinstance(w, str)]
    rows: list[DraftTransaction] = []

    raw_rows = data.get("transactions")
    if not isinstance(raw_rows, list):
        return [], warnings + ["Модель вернула ответ без списка операций."]

    for i, raw in enumerate(raw_rows, 1):
        if not isinstance(raw, dict):
            warnings.append(f"Строка {i} пропущена: неожиданный формат.")
            continue
        try:
            row = DraftTransaction.model_validate(raw)
        except Exception as exc:  # noqa: BLE001 - one bad row must not sink the rest
            logger.warning("voice_parser: dropped row %d: %s", i, exc)
            warnings.append(f"Строка {i} пропущена: {type(exc).__name__}.")
            continue
        if today is not None:
            row = _flag_assumed_today(row, today, language)
        rows.append(row)

    return rows, warnings


# ── Currency conversion ─────────────────────────────────────────────────────

_FX_NOTE = {
    "ru": "Конвертировано по курсу ЦБ на {d}: 1 {src} = {rate} {dst} — проверьте",
    "uz": "МБ курси бўйича {d} санасига конвертация: 1 {src} = {rate} {dst} — текширинг",
    "en": "Converted at the CBU rate for {d}: 1 {src} = {rate} {dst} — please check",
}
_FX_UNAVAILABLE_NOTE = {
    "ru": "Валюта {src}, курс недоступен — пересчитайте вручную",
    "uz": "Валюта {src}, курс мавjуд эмас — қўлда ҳисобланг",
    "en": "Currency {src}, rate unavailable — convert manually",
}


def _fmt_rate(rate: float) -> str:
    """Thin spaces for thousands, comma for the decimal — as the rate is quoted."""
    return f"{rate:,.2f}".replace(",", " ").replace(".", ",")


def _convert_row(
    row: DraftTransaction, business_ccy: str, today: date, language: str
) -> DraftTransaction:
    """
    Put the amount into the business currency, citing the rate.

    Runs AFTER the model has resolved the scale ("двести долларов" -> 200 USD),
    never before: converting an ambiguous figure would multiply the ambiguity by
    twelve thousand. The row stays flagged either way — the conversion replaces
    a dead end with a checkable number, it does not make the row certain.
    """
    src = (row.currency or business_ccy).strip().upper()
    dst = business_ccy.strip().upper()
    if row.amount is None or src == dst:
        # Nothing to convert; still stamp the currency so every row that
        # reaches the preview says what unit its number is in.
        return row.model_copy(update={"currency": dst})

    # The rate on the transaction's own date when we have one, today otherwise —
    # the same fallback the date handling already uses.
    on = _parse_iso_date(row.date) or today

    converted = fx.convert(row.amount, src, dst, on)
    if converted is None:
        # CBU unreachable, or an unsupported currency. Degrade to the previous
        # behaviour for THIS row only; the others convert normally.
        note = _FX_UNAVAILABLE_NOTE.get(language, _FX_UNAVAILABLE_NOTE["ru"]).format(src=src)
        return row.model_copy(update={
            "uncertain": row.uncertain if "amount" in row.uncertain else [*row.uncertain, "amount"],
            "notes": {**row.notes, "amount": row.notes.get("amount") or note},
        })

    amount, rate = converted
    note = _FX_NOTE.get(language, _FX_NOTE["ru"]).format(
        d=on.strftime("%d.%m.%Y"), src=src, rate=_fmt_rate(rate), dst=dst,
    )
    return row.model_copy(update={
        "amount": amount,
        "currency": dst,
        # Deliberately overwrites the model's own amount note: the number in the
        # cell is no longer the number the model produced, so a note about that
        # number would be describing something the user cannot see.
        "uncertain": row.uncertain if "amount" in row.uncertain else [*row.uncertain, "amount"],
        "notes": {**row.notes, "amount": note},
    })


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


async def parse_note(
    text: str,
    language: str = "ru",
    currency: str = "UZS",
    today: date | None = None,
) -> tuple[list[DraftTransaction], list[str]]:
    """
    Parse a free-form note into draft rows plus note-level warnings.

    `today` is injected so relative dates ("вчера") are reproducible in tests
    instead of depending on when the suite happens to run.
    """
    note = text.strip()
    if not note:
        raise ValueError("Пустая заметка — нечего разбирать.")
    if len(note) > MAX_NOTE_CHARS:
        raise ValueError(
            f"Заметка длиннее {MAX_NOTE_CHARS} символов. "
            "Для больших объёмов используйте загрузку файла."
        )

    today = today or date.today()
    provider = settings.ai_provider.lower()
    if settings.ai_mock:
        provider = "mock"
        caller = mock_ai.note_caller(language, currency, today.isoformat())
    else:
        caller = _PROVIDERS.get(provider)
    if caller is None:
        raise ValueError(
            f"Unknown AI_PROVIDER '{provider}'. Choose: {list(_PROVIDERS.keys())}"
        )

    user_message = _build_user_message(note, language, currency, today)

    _t0 = time.perf_counter()
    try:
        raw = await asyncio.to_thread(caller, user_message, SYSTEM_PROMPT)
    except Exception:
        logger.exception(
            "voice_parser: provider '%s' failed after %.2fs",
            provider, time.perf_counter() - _t0,
        )
        raise
    logger.info(
        "voice_parser: provider '%s' responded in %.2fs (note %d chars)",
        provider, time.perf_counter() - _t0, len(note),
    )

    return await finalize(raw, today=today, language=language, currency=currency)


async def finalize(
    raw: str, today: date, language: str, currency: str
) -> tuple[list[DraftTransaction], list[str]]:
    """
    Raw model output -> validated, guarded, currency-converted rows.

    Shared by every input mode. A photo and a spoken note produce the same JSON
    and must therefore get the same treatment — if this lived in the text path
    only, the photo path would quietly skip the assumed-today guard and the
    rate lookup, and nobody would notice until a user compared two drafts.
    """
    data = safe_json_loads(raw)
    if not isinstance(data, dict):
        raise ValueError("AI вернул некорректный JSON.")

    rows, warnings = _coerce_rows(data, today=today, language=language)

    # Rate lookups are blocking HTTP and there may be one per row, so they go to
    # a worker thread together rather than one at a time on the event loop.
    if rows:
        rows = await asyncio.to_thread(
            lambda: [_convert_row(r, currency, today, language) for r in rows]
        )

    logger.info(
        "note parse: %d row(s), %d flagged field(s), %d warning(s)",
        len(rows), sum(len(r.uncertain) for r in rows), len(warnings),
    )
    return rows, warnings


__all__ = ["parse_note", "finalize", "MAX_NOTE_CHARS", "SYSTEM_PROMPT"]
