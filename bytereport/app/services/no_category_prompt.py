"""
Prompt block used when the source data has no trustworthy categories.

Kept separate from ai_analyst so the wording is reviewable on its own and the
disclaimer translations sit next to each other.

Grounding for rule 2 (do not cite Health Score sub-metrics): `calculate_health_score`
in financial_engine returns `tuple[int, str]` — one score and one status key.
Its five internal deductions (margin, cash gaps, revenue trend, tax-limit risk,
expense volatility) are transient locals: never stored, never returned, never
sent to the model. No "liquidity" or "stability" figure exists anywhere in the
codebase, so any such number in a report would be invented.
"""

from __future__ import annotations

# Disclaimer that must appear in the executive summary, in the report language.
# Uzbek is Cyrillic, matching PDF_LABELS["uz"] and the rest of the product.
NO_CATEGORY_DISCLAIMER = {
    "ru": (
        "Данный источник данных не содержит разметки по категориям расходов. "
        "Детальный категорийный анализ доступен при загрузке файла с категориями "
        "(1С/банк-клиент с разметкой)."
    ),
    "uz": (
        "Ушбу маълумот манбаи харажат категориялари бўйича белгиларни ўз ичига олмайди. "
        "Батафсил категориявий таҳлил категориялари белгиланган файл юкланганда "
        "(1С/банк-клиент) мумкин бўлади."
    ),
    "en": (
        "This data source contains no expense category labels. Detailed category "
        "analysis is available when uploading a file that includes categories "
        "(1C / bank client with labels)."
    ),
}


def build_no_category_block(language: str, coverage: float) -> str:
    """Constraints injected into the system prompt when categories are unusable."""
    disclaimer = NO_CATEGORY_DISCLAIMER.get(language, NO_CATEGORY_DISCLAIMER["ru"])
    return (
        "═══ ИСТОЧНИК БЕЗ КАТЕГОРИЙ ═══\n"
        f"В этих данных категории расходов отсутствуют или ненадёжны "
        f"(покрытие {coverage * 100:.0f}%).\n\n"
        "СТРОГИЕ ЗАПРЕТЫ:\n"
        "1. НЕ выдумывай названия категорий расходов и НЕ давай процентных "
        "разбивок по категориям. Категорийных данных нет — любая разбивка "
        "будет вымыслом.\n"
        "2. НЕ упоминай компоненты Health Score (ликвидность, стабильность, "
        "рентабельность и т.п.) как отдельные числа или под-оценки. Такие "
        "под-показатели НЕ рассчитываются: есть только один Health Score "
        "(число) и его статус. Ссылайся только на них.\n"
        "3. НЕ упоминай динамику 'день к дню' и любую детализацию по времени "
        "тоньше переданной: в данных есть ПОМЕСЯЧНЫЕ агрегаты и ПОНЕДЕЛЬНЫЙ "
        "кассовый поток. Дневных данных нет.\n"
        "4. Категорийные поля JSON заполняй ПУСТЫМИ СПИСКАМИ, не null: "
        "expense_analysis.problem_categories = [], "
        "expense_analysis.efficient_categories = []. "
        "В expense_analysis.notes напиши осмысленное пояснение, почему "
        "категорийный разбор недоступен (не оставляй пустую строку).\n\n"
        "ОБЯЗАТЕЛЬНЫЕ ДЕЙСТВИЯ:\n"
        f"1. В executive_summary включи ДОСЛОВНО эту фразу: «{disclaimer}»\n"
        "2. Сосредоточься ТОЛЬКО на реально доступных метриках:\n"
        "   - динамика выручки/расходов/прибыли по месяцам;\n"
        "   - кассовые разрывы по неделям;\n"
        "   - аномалии по суммам и датам (дубли, скачки, будущие операции);\n"
        "   - Health Score как единое число со статусом.\n"
        "   Анализ по этим данным должен быть таким же содержательным — "
        "меньше измерений, но не меньше пользы.\n\n"
    )


# ── Partial coverage ────────────────────────────────────────────────────────

# Caveat that must accompany any category breakdown built from incomplete data.
# {percent} is substituted with the real measured coverage — never a vague
# "some transactions".
PARTIAL_CATEGORY_CAVEAT = {
    "ru": (
        "Разбивка построена на основе {percent}% транзакций с указанной "
        "категорией — не всех данных."
    ),
    "uz": (
        "Тақсимот категорияси кўрсатилган операцияларнинг {percent}% "
        "асосида тузилган — барча маълумотлар асосида эмас."
    ),
    "en": (
        "This breakdown is based on {percent}% of transactions that carry a "
        "category — not on the full dataset."
    ),
}


def build_partial_category_block(
    language: str, coverage: float, income_cats: list, expense_cats: list
) -> str:
    """
    Constraints for the middle band: the breakdown IS shown, but every
    conclusion drawn from it must be qualified with the real coverage figure.
    """
    percent = int(round(coverage * 100))
    caveat = PARTIAL_CATEGORY_CAVEAT.get(language, PARTIAL_CATEGORY_CAVEAT["ru"])
    caveat = caveat.format(percent=percent)
    return (
        "═══ ЧАСТИЧНОЕ ПОКРЫТИЕ КАТЕГОРИЙ ═══\n"
        f"Категория указана только у {percent}% транзакций. Разбивку по "
        "категориям делать МОЖНО, но она описывает лишь эту часть данных.\n\n"
        "СТРОГИЕ НАЗВАНИЯ КАТЕГОРИЙ — ИСПОЛЬЗОВАТЬ ТОЛЬКО ЭТИ СЛОВА:\n"
        f"Категории доходов: {income_cats}\n"
        f"Категории расходов: {expense_cats}\n"
        "Любое другое название категории = ОШИБКА.\n\n"
        "ОБЯЗАТЕЛЬНЫЕ ДЕЙСТВИЯ:\n"
        f"1. В executive_summary включи ДОСЛОВНО эту фразу: «{caveat}»\n"
        "2. Любой вывод, опирающийся на категории, сопровождай указанием, "
        "что он построен на неполных данных.\n"
        "3. НЕ экстраполируй долю категории на весь оборот: если категория "
        f"составляет X% от размеченных {percent}%, это НЕ X% всех расходов.\n\n"
        "СТРОГИЕ ЗАПРЕТЫ:\n"
        "1. НЕ упоминай компоненты Health Score (ликвидность, стабильность и "
        "т.п.) как отдельные числа — такие под-показатели НЕ рассчитываются. "
        "Есть только Health Score и его статус.\n"
        "2. НЕ упоминай динамику 'день к дню': в данных помесячные агрегаты и "
        "понедельный кассовый поток, дневных данных нет.\n\n"
    )
