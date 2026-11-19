"""
Two text defects found in live reports.

  1. "КечкиUtilities" — two words welded across scripts, in the Uzbek PDF.
  2. "личные расходы" left in Russian in the English and Uzbek reports, while
     every other category showed its canonical key.

Both are about text a person reads, and both are fixed where the report is
parsed rather than where it is rendered, so the web page and the PDF get the
same result.
"""

import io
import os

import pytest

from app.services.ai_text import _GLUED, sanitize, scrub_model, split_glued
from app.utils.category_mapper import (
    CATEGORY_LABELS,
    EXACT_CATEGORIES,
    category_label,
    normalize_category,
)

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))


# ── 1. Words welded across scripts ──────────────────────────────────────────

def test_the_reported_string_is_repaired():
    text = "КечкиUtilities ва software аниқ тартибда, оптимал даражада."
    fixed, joins = split_glued(text)
    assert fixed.startswith("Кечки Utilities ва software")
    assert len(joins) == 1


def test_the_sanitizer_cannot_weld_words_itself():
    """
    The mechanism, and it was ours. `\\(\\)` and `{}` have an EMPTY inner group,
    so substituting the group removed the delimiters AND the gap between the
    neighbours — this sanitizer could manufacture the defect it exists to
    remove.
    """
    welded, _ = sanitize("Кечки" + chr(92) + "(" + chr(92) + ")Utilities ва software")
    assert welded.startswith("Кечки Utilities")
    assert "КечкиUtilities" not in welded


@pytest.mark.parametrize("text,expected", [
    ("МаркетингPayroll харажатлари", "Маркетинг Payroll харажатлари"),
    ("softwareВа тартибда", "software Ва тартибда"),
])
def test_other_run_togethers_are_split(text, expected):
    assert split_glued(text)[0] == expected


@pytest.mark.parametrize("text", [
    "PDFга юклаш",        # Uzbek case ending on a Latin term
    "Excelда очиш",
    "CSVдан импорт",
    "softwareни созлаш",
    "IT-компания",
    "2024-03 ойида",
    "Outsource ва маркетинг харажатлари",
])
def test_correct_uzbek_text_is_left_alone(text):
    """
    The restraint is the design. Uzbek attaches Cyrillic case endings straight
    onto Latin terms, and splitting those would break correct writing. Only a
    lowercase letter followed by a CAPITAL in the other script is treated as a
    lost word boundary.
    """
    assert split_glued(text) == (text, [])


def test_the_detector_only_fires_on_lower_to_upper():
    assert _GLUED.search("кечкиUtilities")      # lower Cyrillic -> upper Latin
    assert _GLUED.search("softwareВа")          # lower Latin -> upper Cyrillic
    assert not _GLUED.search("PDFга")           # upper Latin -> lower Cyrillic
    assert not _GLUED.search("softwareни")      # lower -> lower


def test_the_repair_runs_on_the_whole_report():
    """Same single boundary as the notation sanitizer, so the web page benefits."""
    from app.models.report import AIReport

    payload = {
        "executive_summary": "КечкиUtilities ва software",
        "financial_health_score": {"score": 61, "status": "ok", "reasoning": "ok"},
        "key_insights": [{"title": "МаркетингPayroll", "severity": "high", "explanation": "ok"}],
        "top_risks": [], "growth_opportunities": [],
        "expense_analysis": {"problem_categories": [], "efficient_categories": [],
                             "notes": "Кечки Utilities"},
        "anomalies": [],
        "cash_flow_analysis": {"status": "ok", "summary": "ok", "warning_level": "low"},
        "forecast": {"outlook": "ok", "confidence": "low", "summary": "ok"},
        "priority_actions": [],
    }
    report = scrub_model(AIReport.model_validate(payload))
    assert report.executive_summary == "Кечки Utilities ва software"
    assert report.key_insights[0].title == "Маркетинг Payroll"
    # Already correct text is untouched.
    assert report.expense_analysis.notes == "Кечки Utilities"


# ── 2. Categories that stayed in the wrong language ─────────────────────────

@pytest.mark.parametrize("spelling", [
    "личные расходы", "Личные расходы", "ЛИЧНЫЕ РАСХОДЫ",
    "личные_расходы", "личные-расходы", "  личные   расходы  ",
    "personal expenses", "Personal Expenses",
])
def test_the_reported_category_now_normalises(spelling):
    assert normalize_category(spelling, "expense") == "personal"


@pytest.mark.parametrize("lang,expected", [
    ("ru", "Личные расходы"),
    ("uz", "Шахсий харажатлар"),
    ("en", "Personal expenses"),
])
def test_it_is_labelled_in_every_language(lang, expected):
    assert category_label("personal", lang) == expected


@pytest.mark.parametrize("cash", [
    "наличные", "наличные расходы", "оплата наличными", "приход наличными",
])
def test_cash_is_not_mistaken_for_a_personal_expense(cash):
    """
    The reason the exact-name table exists. The keyword pass is a SUBSTRING
    search and "личные" sits inside "наличные" — a keyword entry would have
    filed every cash transaction as a personal expense.
    """
    assert normalize_category(cash, "expense") != "personal"


def test_the_categories_that_fell_through_on_the_test_dataset():
    """
    Not just the one reported case: these were silently kept as raw values by
    the same branch.
    """
    assert normalize_category("freelance", "income") == "services"
    assert normalize_category("consulting", "income") == "services"
    assert normalize_category("outsource", "expense") == "contractors"


@pytest.mark.parametrize("raw,expected", [
    ("зарплата", "payroll"), ("реклама", "marketing"), ("аренда офиса", "rent"),
    ("оборудование", "equipment"), ("продажа", "income-sales"),
])
def test_existing_classification_is_unchanged(raw, expected):
    """The exact-name table is consulted first; it must not shadow the keywords."""
    kind = "income" if expected.startswith("income-") else "expense"
    assert normalize_category(raw, kind) == expected.replace("income-", "")


def test_an_unknown_category_is_still_kept_verbatim():
    """It came from the user's file; inventing a translation would be worse."""
    raw = "Кофе для бариста навынос"
    assert normalize_category(raw, "expense") == raw
    assert category_label(raw, "en") == raw


def test_every_canonical_key_has_a_label_in_every_language():
    keys = set(CATEGORY_LABELS["ru"])
    for lang in ("ru", "uz", "en"):
        assert set(CATEGORY_LABELS[lang]) == keys, f"{lang} is missing labels"
        assert all(CATEGORY_LABELS[lang].values())


def test_every_exact_name_maps_to_a_key_that_has_a_label():
    unlabelled = {v for v in EXACT_CATEGORIES.values() if v not in CATEGORY_LABELS["ru"]}
    assert not unlabelled, f"no display label for: {unlabelled}"


def test_the_web_carries_the_same_labels():
    """
    Two copies, one per surface. A key labelled on one side and missing on the
    other means that surface shows a raw key again.
    """
    import json

    for lang in ("ru", "uz", "en"):
        path = os.path.join(REPO_ROOT, "bytereport-frontend", "src", "locales", f"{lang}.json")
        report_block = json.load(io.open(path, encoding="utf-8"))["report"]
        assert report_block["category"] == CATEGORY_LABELS[lang], (
            f"{lang}: web and PDF category labels differ"
        )
        # The web needs the same name -> key resolution the PDF does, or the
        # anomalies table shows whatever the model wrote.
        assert report_block["category_alias"] == EXACT_CATEGORIES


def test_the_pdf_prints_the_label_not_the_key():
    import inspect

    from app.services import chart_renderer as cr
    from app.services import pdf_generator as pg

    assert "category_label(a.category" in inspect.getsource(pg._build_anomalies)
    assert "category_label(" in inspect.getsource(cr.render_expense_donut)


@pytest.mark.parametrize("name,lang,expected", [
    ("Зарплата", "en", "Payroll"),
    ("Реклама", "uz", "Маркетинг"),
    ("Материалы", "en", "Inventory & materials"),
    ("Аренда", "en", "Rent"),
    ("налоги", "en", "Taxes"),
])
def test_russian_category_names_are_labelled_too(name, lang, expected):
    """
    Not only the reported one. category_label() cannot run the keyword pass —
    that would relabel a display value on a coincidental substring — so every
    name a person actually types has to be in the exact table, or it stays
    Russian in the English report exactly as "личные расходы" did.
    """
    assert category_label(name, lang) == expected


@pytest.mark.parametrize("name,kind,expected", [
    ("зарплата", "expense", "payroll"), ("реклама", "expense", "marketing"),
    ("материалы", "expense", "inventory"), ("доставка", "expense", "logistics"),
    ("оборудование", "expense", "equipment"), ("налоги", "expense", "taxes"),
    ("аренда", "expense", "rent"), ("услуги", "income", "services"),
])
def test_the_exact_table_agrees_with_the_keyword_pass(name, kind, expected):
    """
    The exact table is consulted FIRST, so a disagreement would change how
    transactions are classified, not merely how they are displayed.
    """
    assert normalize_category(name, kind) == expected
