"""
AI-CFO Chat service.

Stateless multi-turn chat: each request receives the full conversation history
plus the current financial context. Trimmed metrics are embedded in the system
prompt to minimise token usage.
"""

import asyncio
import json
import logging
import time
from typing import Any

from app.core.config import settings
from app.models.chat import ChatMessage
from app.services import mock_ai
from app.services.cash_claims import enforce_engine_cash_figures, strip_unfounded_cash_text
from app.services.cost import log_anthropic_usage, log_chat_usage
from app.services.report_copy import copy_text

logger = logging.getLogger(__name__)

_SYSTEM_TEMPLATE = """\
Ты ByteReport AI-CFO — персональный финансовый советник. \
У тебя есть реальные финансовые данные бизнеса. \
Отвечай строго по этим данным — не придумывай цифры которых нет.

БИЗНЕС: {business_name} | {business_type} | Валюта: {currency}

ФИНАНСОВЫЕ ДАННЫЕ:
{metrics_json}
{report_block}
{cash_block}
ПРАВИЛА:
- Только русский язык
- Конкретные цифры из данных — никогда не придумывай
- 3–6 предложений если не просят подробнее
- Если данных недостаточно — скажи честно
- Вопросы не по финансам — мягко верни к теме
- Не повторяй уже сказанное в диалоге\
"""


def _trim_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    """Return only the fields needed for chat context (saves ~40% tokens)."""
    return {
        "period": f"{metrics.get('period_start')} — {metrics.get('period_end')}",
        "total_revenue": metrics.get("total_revenue"),
        "total_expenses": metrics.get("total_expenses"),
        "profit": metrics.get("profit"),
        "profit_margin": metrics.get("profit_margin"),
        "avg_monthly_revenue": metrics.get("avg_monthly_revenue"),
        "avg_monthly_expenses": metrics.get("avg_monthly_expenses"),
        "avg_monthly_profit": metrics.get("avg_monthly_profit"),
        "monthly_breakdown": metrics.get("monthly_breakdown", []),
        "expense_by_category": metrics.get("expense_by_category", []),
        "revenue_by_category": metrics.get("revenue_by_category", []),
        "anomalies": metrics.get("anomalies", []),
        "mom_growth": metrics.get("mom_growth", []),
        "top_transactions": (metrics.get("top_transactions") or [])[:5],
        "cashflow_forecast": metrics.get("cashflow_forecast"),
    }


_MONTHS_GEN = {
    "ru": ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
           "августа", "сентября", "октября", "ноября", "декабря"],
    "uz": ["январь", "февраль", "март", "апрель", "май", "июнь", "июль",
           "август", "сентябрь", "октябрь", "ноябрь", "декабрь"],
    "en": ["January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"],
}


def _fmt_date(iso: str, lang: str = "ru") -> str:
    y, m, d = (int(x) for x in iso.split("-"))
    month = _MONTHS_GEN.get(lang, _MONTHS_GEN["ru"])[m - 1]
    return f"{month} {d}, {y}" if lang == "en" else f"{d} {month} {y}"


def _fmt_money(value: float, currency: str) -> str:
    return f"{abs(float(value)):,.0f}".replace(",", "\u00a0") + f" {currency}"


def _engine_cash_sentence(forecast: dict, currency: str, lang: str = "ru") -> str:
    """The engine's own answer to "when does the money run out", in one line."""
    if forecast.get("has_risk") and forecast.get("risk_date") and forecast.get("risk_amount") is not None:
        return copy_text("cash_forecast", "engine_gap", lang).format(
            date=_fmt_date(forecast["risk_date"], lang),
            amount=_fmt_money(forecast["risk_amount"], currency),
        )
    return copy_text("cash_forecast", "engine_no_gap", lang)


def _cash_block(metrics: dict[str, Any], currency: str) -> str:
    """
    What the chat may say about running out of money.

    The report already follows this rule; without it the chat answered "when
    will the money run out?" with a date and an amount of its own making.
    """
    cf = metrics.get("cashflow_forecast") or {}
    if cf.get("balance_known"):
        return (
            "ПРОГНОЗ ОСТАТКА: остаток на счёте на конец периода указан "
            f"({_fmt_money(cf.get('closing_balance') or 0, currency)}). Если спрашивают, когда "
            "закончатся деньги, называй ТОЛЬКО то, что посчитал движок: "
            f"{_engine_cash_sentence(cf, currency)} Свои даты и суммы не считай.\n"
        )
    return (
        "ПРОГНОЗ ОСТАТКА: остаток на счёте НЕ указан. Выписка показывает движение денег, "
        "а не их остаток, поэтому дату и сумму будущей нехватки денег назвать нельзя. "
        "Если спрашивают, когда закончатся деньги, ответь, что для прогноза нужен остаток "
        "на счёте на конец периода (его можно ввести в карточке прогноза денежного потока "
        "в отчёте), и опиши только тренд чистого потока по неделям.\n"
    )


def guard_cash_answer(answer: str, metrics: dict[str, Any], currency: str) -> str:
    """
    The same deterministic guard as the report (cash_claims.py), on a chat
    answer. Without a balance: no dated or sized shortfall at all. With one:
    only the engine's date and amounts; a sentence with other figures is
    replaced by the engine's own line.
    """
    cf = metrics.get("cashflow_forecast") or {}
    period_end = metrics.get("period_end")
    if cf.get("balance_known"):
        cleaned, removed = enforce_engine_cash_figures(answer, cf, period_end)
        tail = _engine_cash_sentence(cf, currency)
    else:
        cleaned, removed = strip_unfounded_cash_text(answer, period_end)
        tail = copy_text("cash_forecast", "needs_balance_action", "ru")
    if not removed:
        return answer
    for sentence in removed:
        logger.warning("AI-CFO chat: removed a cash-shortfall claim: %r", sentence[:200])
    return f"{cleaned} {tail}".strip() if tail not in cleaned else cleaned


def _build_system(
    metrics: dict[str, Any],
    ai_report: dict[str, Any] | None,
    business_name: str | None,
    business_type: str | None,
    currency: str,
) -> str:
    metrics_json = json.dumps(_trim_metrics(metrics), ensure_ascii=False, indent=2)

    report_block = ""
    if ai_report:
        score = ai_report.get("financial_health_score") or {}
        actions = (ai_report.get("priority_actions") or [])[:3]
        report_block = (
            "\nКЛЮЧЕВЫЕ ВЫВОДЫ АНАЛИЗА:\n"
            f"Резюме: {ai_report.get('executive_summary', '')}\n"
            f"Здоровье: {score.get('score')} — {score.get('status')}\n"
            f"Топ-действия: {'; '.join(a.get('action', '') for a in actions)}\n"
        )

    return _SYSTEM_TEMPLATE.format(
        business_name=business_name or "не указано",
        business_type=business_type or "не указано",
        currency=currency,
        metrics_json=metrics_json,
        report_block=report_block,
        cash_block=_cash_block(metrics, currency),
    )


def _openai_chat(system: str, history: list[ChatMessage], message: str) -> str:
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError("openai package not installed. Run: pip install openai")

    # Same client settings as the report path (ai_analyst._call_openai):
    # an explicit timeout instead of the SDK's 600 s default, and no silent
    # retries — the SDK's default of 2 bills tokens for every attempt, so one
    # failing question could cost as much as three successful ones.
    client = OpenAI(
        api_key=settings.openai_api_key,
        timeout=settings.ai_timeout_seconds,
        max_retries=0,
    )
    msgs: list[dict] = [{"role": "system", "content": system}]
    for m in history:
        msgs.append({"role": m.role, "content": m.content})
    msgs.append({"role": "user", "content": message})

    resp = client.chat.completions.create(
        model=settings.openai_model,
        messages=msgs,
        temperature=0.4,
        max_tokens=800,
    )
    log_chat_usage(resp, settings.openai_model)
    return resp.choices[0].message.content or ""


def _anthropic_chat(system: str, history: list[ChatMessage], message: str) -> str:
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic package not installed. Run: pip install anthropic")

    client = anthropic.Anthropic(
        api_key=settings.anthropic_api_key,
        timeout=settings.ai_timeout_seconds,
        max_retries=0,   # same rationale as the OpenAI chat client above
    )
    msgs = [{"role": m.role, "content": m.content} for m in history]
    msgs.append({"role": "user", "content": message})

    resp = client.messages.create(
        model=settings.claude_model,
        system=system,
        messages=msgs,
        temperature=0.4,
        max_tokens=800,
    )
    log_anthropic_usage(resp, settings.claude_model)
    return resp.content[0].text


async def get_chat_response(
    message: str,
    history: list[ChatMessage],
    metrics: dict[str, Any],
    ai_report: dict[str, Any] | None,
    business_name: str | None,
    business_type: str | None,
    currency: str,
) -> str:
    system = _build_system(metrics, ai_report, business_name, business_type, currency)
    provider = settings.ai_provider.lower()
    logger.info("AI-CFO chat via provider='%s' history_len=%d", provider, len(history))

    if settings.ai_mock:
        provider = "mock"
        caller = mock_ai.chat_caller(metrics, ai_report, currency)
    elif provider == "openai":
        caller = _openai_chat
    elif provider == "anthropic":
        caller = _anthropic_chat
    else:
        raise ValueError(f"Unknown AI_PROVIDER '{provider}'. Choose: openai | anthropic")

    # Both SDKs are synchronous. Called directly from this `async def` the
    # blocking network IO ran on the event loop and froze the whole server for
    # the duration — /health stopped answering mid-request. Same fix as
    # ai_analyst.get_ai_analysis.
    _t0 = time.perf_counter()
    try:
        answer = await asyncio.to_thread(caller, system, history, message)
    except asyncio.CancelledError:
        # The client disconnected while we were waiting. Log it and re-raise so
        # the handler unwinds cleanly instead of surfacing an unhandled error.
        #
        # NOTE: this does NOT stop the upstream call or save any tokens. The
        # provider request is running on a real OS thread that cannot be
        # interrupted from here; it will finish and be billed regardless.
        # Cancelling the actual HTTP request would require threading
        # cancellation into the SDK's transport, which is out of scope here.
        logger.info(
            "AI-CFO chat cancelled by client after %.2fs; upstream call continues "
            "in its thread and will still be billed",
            time.perf_counter() - _t0,
        )
        raise
    except Exception:
        logger.exception(
            "AI-CFO chat provider '%s' failed after %.2fs",
            provider, time.perf_counter() - _t0,
        )
        raise

    logger.info(
        "AI-CFO chat provider '%s' responded in %.2fs",
        provider, time.perf_counter() - _t0,
    )
    return guard_cash_answer(answer, metrics, currency)
