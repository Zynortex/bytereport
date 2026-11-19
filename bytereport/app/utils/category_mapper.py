"""
Maps raw transaction descriptions/categories to normalized business categories.
Handles Russian and English keywords.
"""

EXPENSE_KEYWORDS: dict[str, list[str]] = {
    "marketing": [
        "реклама", "маркетинг", "таргет", "smm", "google ads", "yandex", "яндекс",
        "facebook", "instagram", "promotion", "advertising",
    ],
    "payroll": [
        "зарплата", "оклад", "зп", "salary", "payroll", "wage", "персонал",
        "сотрудник", "премия", "бонус",
    ],
    "rent": [
        "аренда", "офис", "помещение", "rent", "office", "склад", "warehouse",
    ],
    "software": [
        "подписка", "saas", "software", "лицензия", "license", "облако", "cloud",
        "хостинг", "hosting", "сервис", "subscription",
    ],
    "logistics": [
        "доставка", "логистика", "транспорт", "курьер", "shipping", "logistics",
        "delivery", "топливо", "fuel",
    ],
    "taxes": [
        "налог", "ндс", "tax", "взнос", "пфр", "фсс", "есн", "усн",
    ],
    "utilities": [
        "коммунальн", "электричество", "вода", "интернет", "телефон",
        "utilities", "electricity", "internet",
    ],
    "inventory": [
        "товар", "закупка", "сырье", "материал", "inventory", "goods",
        "purchase", "stock", "продукт",
    ],
    "equipment": [
        "оборудование", "техника", "компьютер", "equipment", "hardware",
        "мебель", "furniture",
    ],
}

INCOME_KEYWORDS: dict[str, list[str]] = {
    "sales": [
        "продажа", "выручка", "sale", "revenue", "оплата", "payment",
        "заказ", "order", "клиент", "client",
    ],
    "services": [
        "услуга", "service", "консультация", "consultation", "проект", "project",
        "разработка", "development",
    ],
    "subscription": [
        "подписка клиента", "абонплата", "recurring", "subscription income",
    ],
    "refund": [
        "возврат", "refund", "компенсация",
    ],
}


def normalize_category(raw: str, transaction_type: str) -> str:
    lowered = raw.lower().strip()

    # Exact name first. The keyword pass below is a substring search, so a name
    # like "личные расходы" has to be recognised as a whole before "личные" can
    # be found inside "наличные".
    exact = EXACT_CATEGORIES.get(_normalise_name(raw))
    if exact:
        return exact

    keyword_map = INCOME_KEYWORDS if transaction_type == "income" else EXPENSE_KEYWORDS

    for category, keywords in keyword_map.items():
        for kw in keywords:
            if kw in lowered:
                return category

    # Genuinely unknown: keep what the user wrote rather than guessing.
    return raw.strip()


# ── Exact category names ────────────────────────────────────────────────────
#
# Matched BEFORE the keyword lists, on the whole normalised name, and that is
# not a style choice. The keyword loop is a substring search, and "личные" is a
# substring of "наличные" — a cash transaction would have been filed as a
# personal expense. A category NAME is a name, so it is compared as one.
#
# Everything here was previously returned verbatim, which is why "личные
# расходы" stayed Russian in the English and Uzbek reports while every other
# category showed its canonical key.

EXACT_CATEGORIES: dict[str, str] = {
    # personal
    "личные расходы": "personal", "личные траты": "personal",
    "личное потребление": "personal", "личный расход": "personal",
    "personal": "personal", "personal expenses": "personal",
    "шахсий харажатлар": "personal", "shaxsiy xarajatlar": "personal",
    # residual bucket
    "прочее": "other", "прочие": "other", "разное": "other", "другое": "other",
    "other": "other", "misc": "other", "miscellaneous": "other",
    "бошқа": "other", "boshqa": "other",
    # travel
    "командировки": "travel", "командировка": "travel", "поездки": "travel",
    "travel": "travel", "business trip": "travel", "сафар": "travel",
    # insurance
    "страхование": "insurance", "страховка": "insurance",
    "insurance": "insurance", "суғурта": "insurance",
    # banking
    "банковские комиссии": "banking", "комиссия банка": "banking",
    "банковская комиссия": "banking", "эквайринг": "banking",
    "bank fees": "banking", "banking": "banking", "банк": "banking",
    # education
    "обучение": "education", "курсы": "education", "тренинги": "education",
    "education": "education", "training": "education", "ўқитиш": "education",
    # contractors
    "аутсорсинг": "contractors", "подрядчики": "contractors",
    "outsource": "contractors", "outsourcing": "contractors",
    "contractors": "contractors", "фриланс": "contractors",
    # The canonical categories under the names a person actually types.
    # normalize_category() already reaches these through the keyword pass at
    # upload time, but category_label() does NOT run the keywords — it must not,
    # or a display value would be relabelled on a coincidental substring. So the
    # names need to be here, or a Russian category name written by the model
    # into a structured field stays Russian in the English report, which is the
    # same defect as "личные расходы" wearing a different word.
    "зарплата": "payroll", "заработная плата": "payroll", "оклад": "payroll",
    "иш ҳақи": "payroll",
    "реклама": "marketing", "маркетинг": "marketing",
    "аренда": "rent", "аренда офиса": "rent", "ижара": "rent",
    "материалы": "inventory", "закупки": "inventory", "сырьё": "inventory",
    "сырье": "inventory", "товары": "inventory",
    "оборудование": "equipment", "техника": "equipment", "ускуналар": "equipment",
    "налоги": "taxes", "солиқлар": "taxes",
    "коммунальные услуги": "utilities", "коммуналка": "utilities",
    "коммунал хизматлар": "utilities",
    "логистика": "logistics", "доставка": "logistics", "транспорт": "logistics",
    "программное обеспечение": "software", "по": "software",
    "подписки": "subscription", "обуналар": "subscription",
    "продажи": "sales", "выручка": "sales", "сотув": "sales",
    "услуги": "services", "хизматлар": "services",
    "возвраты": "refund", "возврат": "refund",
    # income names that were also falling through
    "freelance": "services", "consulting": "services",
    "консалтинг": "services", "фриланс-доход": "services",
    "инвестиции": "investment", "дивиденды": "investment",
    "investment": "investment", "dividends": "investment",
}


# Display names. Categories used to be printed as their raw key, so an Uzbek
# report said "payroll". The key stays the identity used in code and in the
# charts; this is only what a reader sees.
CATEGORY_LABELS: dict[str, dict[str, str]] = {
    "ru": {
        "marketing": "Маркетинг", "payroll": "Зарплата", "rent": "Аренда",
        "software": "Программы и сервисы", "logistics": "Логистика",
        "taxes": "Налоги", "utilities": "Коммунальные услуги",
        "inventory": "Закупки и материалы", "equipment": "Оборудование",
        "personal": "Личные расходы", "other": "Прочее", "travel": "Командировки",
        "insurance": "Страхование", "banking": "Банковские комиссии",
        "education": "Обучение", "contractors": "Подрядчики",
        "sales": "Продажи", "services": "Услуги",
        "subscription": "Подписки", "refund": "Возвраты",
        "investment": "Инвестиции и дивиденды",
    },
    "uz": {
        "marketing": "Маркетинг", "payroll": "Иш ҳақи", "rent": "Ижара",
        "software": "Дастур ва сервислар", "logistics": "Логистика",
        "taxes": "Солиқлар", "utilities": "Коммунал хизматлар",
        "inventory": "Хомашё ва материаллар", "equipment": "Ускуналар",
        "personal": "Шахсий харажатлар", "other": "Бошқа", "travel": "Хизмат сафарлари",
        "insurance": "Суғурта", "banking": "Банк комиссиялари",
        "education": "Ўқитиш", "contractors": "Пудратчилар",
        "sales": "Сотув", "services": "Хизматлар",
        "subscription": "Обуналар", "refund": "Қайтаришлар",
        "investment": "Инвестиция ва дивидендлар",
    },
    "en": {
        "marketing": "Marketing", "payroll": "Payroll", "rent": "Rent",
        "software": "Software & services", "logistics": "Logistics",
        "taxes": "Taxes", "utilities": "Utilities",
        "inventory": "Inventory & materials", "equipment": "Equipment",
        "personal": "Personal expenses", "other": "Other", "travel": "Travel",
        "insurance": "Insurance", "banking": "Bank fees",
        "education": "Training", "contractors": "Contractors",
        "sales": "Sales", "services": "Services",
        "subscription": "Subscriptions", "refund": "Refunds",
        "investment": "Investments & dividends",
    },
}


def _normalise_name(raw: str) -> str:
    """Fold the spellings a person might type into one comparable form."""
    import re

    return re.sub(r"[\s_\-]+", " ", raw.strip().lower()).strip()


def category_label(key: str | None, language: str = "ru") -> str:
    """
    Reader-facing name for a category.

    Resolves the name to a canonical key FIRST. Not every caller hands over a
    normalised value: the anomalies table carries whatever the model wrote, so
    it arrives as "личные расходы" rather than "personal" and a straight label
    lookup found nothing and printed the Russian through.

    Only the exact-name table is used for that, never the keyword pass — the
    keywords match against free-text descriptions, and running them on a
    display value would relabel a category on a coincidental substring.

    An unknown name is returned as-is: it came from the user's own file, and
    inventing a translation is worse than showing what they wrote.
    """
    if not key:
        return ""
    name = _normalise_name(key)
    canonical = EXACT_CATEGORIES.get(name, name)
    table = CATEGORY_LABELS.get(language, CATEGORY_LABELS["ru"])
    return table.get(canonical, key)
