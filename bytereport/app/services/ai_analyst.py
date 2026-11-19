"""
AI Analyst service for ByteReport.

Provider-agnostic interface — switch between OpenAI and Anthropic
by setting AI_PROVIDER in .env:
  AI_PROVIDER=openai     → uses OpenAI (default, gpt-4o-mini)
  AI_PROVIDER=anthropic  → uses Anthropic Claude

Both providers use the same system prompt and return the same AIReport schema.
"""

import asyncio
import json
import logging
import time
from typing import Any

from app.core.config import settings
from app.core.prompts import BYTEREPORT_SYSTEM_PROMPT
from app.models.report import AIReport, WeeklyCashFlow
from app.services import mock_ai
from app.services.ai_text import scrub_model
from app.services.cost import log_anthropic_usage, log_usage
from app.services.no_category_prompt import (
    build_no_category_block,
    build_partial_category_block,
)
from app.services.cash_claims import strip_unfounded_cash_claims
from app.services.financial_engine import STATUS_LABELS, score_to_status_key
from app.utils.json_repair import safe_json_loads

logger = logging.getLogger(__name__)

# Words that must not appear in Uzbek analysis prose (CSV category names are exempt).
BLACKLIST_UZ: list[str] = [
    "operational", "future", "one-time", "trend",
    "martalik",           # Latin-Cyrillic mix (correct: бир марталик)
    "разовый",            # Russian word banned by ҚАТЪИЙ ҚОИДА
    "кассовый разрыв",    # Russian phrase banned by ҚАТЪИЙ ҚОИДА
]


def _collect_str_values(obj: Any) -> list[str]:
    """Recursively extract all string leaf values from a parsed JSON object."""
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        out: list[str] = []
        for v in obj.values():
            out.extend(_collect_str_values(v))
        return out
    if isinstance(obj, list):
        out = []
        for item in obj:
            out.extend(_collect_str_values(item))
        return out
    return []


def _uz_lint(data: dict, raw_response: str) -> None:
    """Scan a parsed uz AI response for blacklisted words; log violations (never blocks)."""
    import os
    from datetime import datetime

    texts = _collect_str_values(data)
    violations: list[str] = []
    for text in texts:
        tl = text.lower()
        for word in BLACKLIST_UZ:
            if word.lower() in tl:
                violations.append(f"  [{word!r}] in: {text[:120]!r}")

    if not violations:
        return

    os.makedirs("logs/raw_ai_responses", exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    log_path = f"logs/raw_ai_responses/uz_lint_{ts}.txt"
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(f"UZ LINT — {ts}\n\n")
        f.write("\n".join(violations))
        f.write("\n\n=== RAW RESPONSE ===\n")
        f.write(raw_response)
    logger.warning("uz_lint: %d violation(s) — see %s", len(violations), log_path)


_LANGUAGE_NAMES = {
    "uz": "ўзбек тили (кирилл ёзуви)",
    "ru": "русский",
    "en": "English",
}


def _build_user_message(
    metrics: dict,
    business_type: str | None,
    business_name: str | None,
    currency: str,
) -> str:
    context_lines = [f"Currency: {currency}"]
    if business_name:
        context_lines.append(f"Business name: {business_name}")
    if business_type:
        context_lines.append(f"Business type: {business_type}")

    context_block = "\n".join(context_lines)
    metrics_json = json.dumps(metrics, ensure_ascii=False, indent=2)

    return (
        f"Business context:\n{context_block}\n\n"
        f"Financial metrics:\n{metrics_json}\n\n"
        "Generate the financial analysis report as valid JSON only."
    )


def _parse_ai_response(raw: str) -> AIReport:
    """Parse raw LLM response into AIReport using multi-level JSON repair."""
    data = safe_json_loads(raw)
    return AIReport.model_validate(data)


# ---------------------------------------------------------------------------
# OpenAI provider
# ---------------------------------------------------------------------------

def _call_openai(user_message: str, system_prompt: str) -> str:
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError("openai package not installed. Run: pip install openai")

    # max_retries=0: the SDK defaults to 2 silent retries, so a stalled call
    # could occupy 3 x timeout (~360 s) behind a spinner and blow past the
    # client's ceiling. The UI already offers an explicit "retry" button, so a
    # user-initiated retry is preferable to an invisible one. Hard ceiling for
    # this call is now ai_timeout_seconds.
    client = OpenAI(
        api_key=settings.openai_api_key,
        timeout=settings.ai_timeout_seconds,
        max_retries=0,
    )
    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        max_completion_tokens=16000,
    )
    # Exact billed token counts from the provider — logged rather than
    # estimated from character counts, which are badly off for Cyrillic.
    log_usage(response, settings.openai_model)
    return response.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# Anthropic provider
# ---------------------------------------------------------------------------

def _call_anthropic(user_message: str, system_prompt: str) -> str:
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic package not installed. Run: pip install anthropic")

    client = anthropic.Anthropic(
        api_key=settings.anthropic_api_key,
        timeout=settings.ai_timeout_seconds,
        max_retries=0,   # same rationale as the OpenAI client above
    )
    message = client.messages.create(
        model=settings.claude_model,
        max_tokens=4000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
        temperature=0.3,
    )
    log_anthropic_usage(message, settings.claude_model)
    return message.content[0].text


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_PROVIDERS: dict[str, Any] = {
    "openai": _call_openai,
    "anthropic": _call_anthropic,
}


async def get_ai_analysis(
    metrics: dict,
    business_type: str | None = None,
    business_name: str | None = None,
    currency: str = "UZS",
    language: str = "ru",
) -> AIReport:
    """
    Send financial metrics to the configured AI provider and return AIReport.

    Raises:
        ValueError:  unknown provider in config
        RuntimeError: provider SDK not installed
        json.JSONDecodeError: model returned malformed JSON
        pydantic.ValidationError: model returned JSON with wrong schema
    """
    provider = settings.ai_provider.lower()
    if settings.ai_mock:
        # Only the network call is replaced; everything after it still runs.
        provider = "mock"
        caller = mock_ai.report_caller(metrics, language, currency)
    else:
        caller = _PROVIDERS.get(provider)
    if caller is None:
        raise ValueError(
            f"Unknown AI_PROVIDER '{provider}'. Choose: {list(_PROVIDERS.keys())}"
        )

    user_message = _build_user_message(metrics, business_type, business_name, currency)

    # Use pre-computed categories from financial_engine (avoids hallucinated categories)
    income_cats = metrics.get("real_income_categories", [])
    expense_cats = metrics.get("real_expense_categories", [])

    category_strict = (
        f"СТРОГИЕ НАЗВАНИЯ КАТЕГОРИЙ — ИСПОЛЬЗОВАТЬ ТОЛЬКО ЭТИ СЛОВА:\n"
        f"Категории доходов: {income_cats}\n"
        f"Категории расходов: {expense_cats}\n"
        f"Любое другое название категории = ОШИБКА. "
        f"Особо запрещено: other, прочее, разное, logistics, себестоимость, зал, доставка — "
        f"если этих слов нет в списках выше.\n\n"
    )

    _proj_rev    = metrics.get("avg_monthly_revenue", 0)
    _proj_exp    = metrics.get("avg_monthly_expenses", 0)
    _proj_profit = round(_proj_rev - _proj_exp, 2)
    _profit_label = "УБЫТОК" if _proj_profit < 0 else "прибыль"

    _health_key = score_to_status_key(metrics.get("health_score", 0))
    _health_status_label = STATUS_LABELS[_health_key].get(language, STATUS_LABELS[_health_key]["ru"])

    # ── Preprocessing block ──────────────────────────────────────────────────
    _pre_meta       = metrics.get("preprocessing_meta", {})
    _future_txns    = _pre_meta.get("future_transactions", [])
    _dupes          = _pre_meta.get("possible_duplicates", [])
    _fin_income     = metrics.get("financing_income", 0)
    _fin_income_cats = metrics.get("financing_income_categories", [])
    _fin_expenses   = metrics.get("financing_expenses", 0)
    _op_revenue     = metrics.get("operating_revenue") or metrics.get("total_revenue", 0)

    _future_str = (
        ", ".join(
            f"{f['category']} {f['date']} {f['amount']:,.0f}"
            for f in _future_txns
        ) if _future_txns else "нет"
    )
    _dupes_str = (
        "; ".join(
            f"{d['category']} {d['date']} x{d['count']}"
            for d in _dupes
        ) if _dupes else "не обнаружены"
    )
    _fin_cats_str = ", ".join(_fin_income_cats) if _fin_income_cats else "нет"

    preprocessing_context = (
        "ПРЕДОБРАБОТКА ДАННЫХ (выполнена Python, факты не требуют пересчёта):\n"
        f"- Операционная выручка: {_op_revenue:,.0f}\n"
        f"- Заёмные средства (НЕ выручка): {_fin_income:,.0f} ({_fin_cats_str})\n"
        f"- Платежи по кредитам: {_fin_expenses:,.0f}\n"
        f"- Исключено будущих транзакций: {len(_future_txns)} ({_future_str})\n"
        f"- Возможные дубли: {_dupes_str}\n\n"
    )

    precomputed_context = (
        "ПРЕДРАССЧИТАННЫЕ ДАННЫЕ (используй эти цифры — они точные, посчитаны Python):\n\n"
        f"Доходы по категориям: {metrics.get('income_by_category', {})}\n"
        f"Доля каждой категории в выручке: {metrics.get('income_category_share', {})}\n\n"
        "Аутсорс vs штат:\n"
        f"- Штатный ФОТ: {metrics.get('payroll_total', 0):,.0f}\n"
        f"- Аутсорс расходы: {metrics.get('outsource_total', 0):,.0f}\n"
        f"- Доля аутсорса: {metrics.get('outsource_ratio', 0)}%\n\n"
        f"ROI маркетинга по месяцам: {metrics.get('marketing_roi', {})}\n\n"
        f"Недели, в которых платежи превысили поступления (чистый поток меньше нуля; это НЕ остаток на счёте): {metrics.get('negative_weeks', {})}\n\n"
        "Налоговый контроль УЗ (только операционная выручка, без заёмных средств):\n"
        f"- Прогнозируемый годовой оборот (operating): {metrics.get('projected_annual_revenue', 0):,.0f}\n"
        f"- Использование лимита УСН (1 млрд): {metrics.get('tax_limit_usage_percent', 0)}%\n"
        f"- Требует внимания: {metrics.get('tax_limit_warning', False)}\n\n"
        "Прогноз на следующий месяц (рассчитан Python, используй ЭТИ цифры):\n"
        f"- projected_revenue:  {_proj_rev:,.0f}\n"
        f"- projected_expenses: {_proj_exp:,.0f}\n"
        f"- projected_profit:   {_proj_profit:,.0f}  ← {_profit_label}"
        + (" (отрицательное — расходы превышают доходы)\n\n" if _proj_profit < 0 else "\n\n")
        + f"Категории доходов в данных: {income_cats}\n"
        f"Категории расходов в данных: {expense_cats}\n\n"
        f"Статус здоровья бизнеса (health_status_label — вставить ДОСЛОВНО в financial_health_score.status): {_health_status_label}\n\n"
    )

    language_name = _LANGUAGE_NAMES.get(language, "русский")
    language_block = (
        f"\n\nЯЗЫК ОТВЕТА: {language_name}\n"
        "Пиши весь текст ТОЛЬКО на этом языке.\n"
        "JSON ключи всегда на английском (executive_summary, key_insights и т.д.).\n"
        "Значения enum ('severity', 'confidence', 'warning_level') — ТОЛЬКО на английском: 'low', 'medium', 'high'.\n"
        "Названия категорий из CSV НЕ переводить — используй ровно так, как в данных.\n"
        "Числа форматировать с пробелом как разделитель тысяч: 10 000 000\n"
        f"Поле financial_health_score.status: вставь ДОСЛОВНО '{_health_status_label}' — не придумывай и не переводи.\n"
    )
    if language == "uz":
        language_block += (
            "КИРИЛЛИЦА ОБЯЗАТЕЛЬНА. Запрещено: oʻ gʻ — используй: ў ғ\n"
            "Словарь: выручка=тушум, расходы=харажатлар, прибыль=фойда, убыток=зарар\n"
            "кассовый разрыв=нақд пул тақчиллиги ёки пул оқими узилиши, аренда=ижара, зарплата=иш ҳақи\n"
            "прогноз=прогноз, риск=хавф, рекомендация=тавсия, анализ=таҳлил\n"
            "разовый доход=бир марталик даромад, оборот=айланма, налоговый лимит=солиқ лимити\n"
            "ҚАТЪИЙ ҚОИДА: русча сўзларни ишлатма. Тақиқланган: 'разовый' (тўғриси: 'бир марталик'), "
            "'кассовый разрыв' (тўғриси: 'пул оқими узилиши' ёки 'нақд пул тақчиллиги'). "
            "Фақат кирилл ҳарфлари — лотин ҳарфи аралаштирма. Ҳар бир жумла тоза ўзбек тилида бўлсин.\n"
            "ҚЎШИМЧА ҚОИДА: таҳлил матнида (сарлавҳа, хулоса, insight'лар, тавсиялар) "
            "инглизча ёки бошқа лотин ёзувидаги СЎЗЛАРНИ (категория номларидан ташқари) ишлатма. "
            "МУҲИМ: CSV файлидаги категория номлари (masalan 'marketing', 'outsource', 'subscription', "
            "'kredit qaytarish') ўзгармасдан қолиши КЕРАК — уларни таржима қилма, лекин ҳам уларни "
            "бошқа инглизча сўзлар билан аралаштирма. "
            "Тақиқланган хизматчи сўзлар мисоллари (тўғри вариант билан): "
            "- operational → операцион / асосий фаолият бўйича "
            "- future → келажакдаги / режалаштирилган "
            "- one-time → бир марталик (кирилл ҳарфларида, ҳеч қачон 'martalik' эмас) "
            "- trend → тенденция / йўналиш "
            "Ҳар бир сўзни тўлиқ кирилл ёзувида ёз, лотин ва кирилл ҳарфларини битта сўз ичида АРАЛАШТИРМА.\n"
        )
    elif language == "en":
        language_block += (
            "Write everything in English.\n"
            "Health Score statuses: 0-39=Critical, 40-54=Unstable, 55-69=Stable, 70-100=Excellent\n"
        )

    # Category-coverage signal computed once upstream (category_coverage.py) and
    # carried on the metrics dict. When categories are unusable, swap the
    # "use exactly these category names" instruction for the constraints block —
    # telling the model to stick to a category list AND that categories don't
    # exist would be contradictory.
    _coverage = float(metrics.get("category_coverage", 1.0))
    _level = metrics.get("category_reliability")
    if _level is None:
        # Older payloads carry only the boolean; map it onto the scale.
        _level = "full" if metrics.get("has_reliable_categories", True) else "none"

    if _level == "full":
        category_block = category_strict
    elif _level == "partial":
        category_block = build_partial_category_block(
            language, _coverage, income_cats, expense_cats
        )
    else:
        category_block = build_no_category_block(language, _coverage)
    logger.info(
        "AI prompt: category reliability=%s (coverage %.0f%%)", _level, _coverage * 100
    )

    # What the cash forecast may claim depends on whether the user gave the
    # account balance. The prompt says so; strip_unfounded_cash_claims below
    # makes sure, because a prompt is a request, not a guarantee.
    _cf = metrics.get("cashflow_forecast") or {}
    _balance_known = bool(_cf.get("balance_known"))
    if _balance_known:
        cash_block = (
            "ОСТАТОК НА СЧЁТЕ НА КОНЕЦ ПЕРИОДА указан пользователем: "
            f"{float(_cf.get('closing_balance') or 0):,.0f}. Прогноз остатка "
            "(cashflow_forecast.weekly_projection.projected_balance) рассчитан от него — "
            "дату и сумму возможной нехватки бери только оттуда.\n\n"
        )
    else:
        cash_block = (
            "ОСТАТОК НА СЧЁТЕ НЕ УКАЗАН. Выписка показывает движение денег, а не их остаток, "
            "поэтому НЕЛЬЗЯ называть дату или сумму будущей нехватки денег / кассового разрыва "
            "и писать, что баланс «уйдёт в минус» к какой-то дате или на какую-то сумму. "
            "Можно: описать тренд чистого потока по неделям (поступления минус платежи), "
            "прошлые недели с отрицательным чистым потоком как факт из выписки, и сказать, "
            "что для прогноза остатка нужен остаток на счёте на конец периода.\n\n"
        )

    dynamic_system_prompt = category_block + preprocessing_context + precomputed_context + cash_block + BYTEREPORT_SYSTEM_PROMPT + language_block

    logger.info("Calling AI provider '%s' model '%s' language '%s'", provider,
                settings.openai_model if provider == "openai" else settings.claude_model,
                language)

    # Both provider SDKs are synchronous. Calling one directly from this
    # `async def` ran blocking network IO on the event loop, freezing the whole
    # server for the duration of the request (~30-45 s) — even /health stopped
    # answering. Hand it to a worker thread so the loop stays free.
    _t0 = time.perf_counter()
    try:
        raw_response = await asyncio.to_thread(
            caller, user_message, dynamic_system_prompt
        )
    except Exception:
        logger.exception(
            "AI provider '%s' failed after %.2fs", provider, time.perf_counter() - _t0
        )
        raise
    _elapsed = time.perf_counter() - _t0
    logger.info(
        "AI provider '%s' responded in %.2fs (sent %d chars, received %d chars)",
        provider, _elapsed, len(user_message) + len(dynamic_system_prompt),
        len(raw_response),
    )
    logger.debug("Raw AI response length: %d chars", len(raw_response))

    data = safe_json_loads(raw_response)
    if language == "uz":
        _uz_lint(data, raw_response)
    report = AIReport.model_validate(data)
    # Strip formula/placeholder notation from every string before anything
    # renders it. Done here rather than in the PDF builder: the web report
    # reads the same object and would otherwise still show the raw text.
    scrub_model(report, where=f"AI report ({language})")
    if not _balance_known:
        strip_unfounded_cash_claims(
            report, language=language, period_end=metrics.get("period_end"),
        )
    report.financial_health_score.status = _health_status_label
    report.language = language

    # Populate structured weekly cash flow from metrics (includes financing transactions).
    report.weekly_cash_flow = [
        WeeklyCashFlow(
            week=w["week_key"],
            revenue=w["revenue"],
            expenses=w["expenses"],
            net=w["profit"],
        )
        for w in metrics.get("weekly_breakdown", [])
        if isinstance(w, dict) and "week_key" in w
    ]

    return report
