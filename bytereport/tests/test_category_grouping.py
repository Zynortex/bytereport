"""
Two defects seen on the web dashboard.

  1. The donut showed "Marketing", "Marketing", "Marketing" — three wedges for
     one category, because the totals were keyed on the literal string.
  2. "ТОП РИСКОВ" stayed Russian on the English dashboard.

The first is a data bug and is fixed in the engine, not in the chart: the same
split reached the anomaly detector, the income shares and the category list
handed to the model.
"""

import io
import json
import os
from datetime import date

import pytest

from app.models.transaction import Transaction, TransactionType
from app.services.financial_engine import _cat_key, compute_metrics

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
LOCALES = os.path.join(REPO_ROOT, "bytereport-frontend", "src", "locales")


def _tx(day: str, amount: float, kind: str, category: str) -> Transaction:
    return Transaction(
        date=date.fromisoformat(day), description=category, amount=amount,
        type=TransactionType(kind), category=category, raw_category=category,
    )


# The reported shape: one category written three ways.
MIXED = [
    _tx("2026-01-10", 300_000, "expense", "Marketing"),
    _tx("2026-01-15", 200_000, "expense", "marketing"),
    _tx("2026-01-20", 100_000, "expense", "MARKETING "),
    _tx("2026-01-25", 400_000, "expense", "payroll"),
    _tx("2026-01-05", 2_000_000, "income", "Sales"),
    _tx("2026-02-05", 1_000_000, "income", "sales"),
]


# ── 1. The grouping key ─────────────────────────────────────────────────────

@pytest.mark.parametrize("a,b", [
    ("Marketing", "marketing"),
    ("MARKETING ", "marketing"),
    (" Marketing ", "Marketing"),
    ("personal  expenses", "Personal Expenses"),
])
def test_spellings_of_one_category_share_a_key(a, b):
    assert _cat_key(a) == _cat_key(b)


def test_different_categories_keep_different_keys():
    assert _cat_key("marketing") != _cat_key("payroll")


# ── The donut, which is where it was seen ───────────────────────────────────

def test_the_breakdown_has_one_row_per_category():
    m = compute_metrics(MIXED)
    names = [r.category for r in m.expense_by_category]
    assert len(names) == len(set(n.lower() for n in names))
    assert len(m.expense_by_category) == 2, names


def test_the_merged_row_carries_the_whole_total():
    m = compute_metrics(MIXED)
    marketing = next(r for r in m.expense_by_category if r.category.lower() == "marketing")
    assert marketing.total == 600_000
    assert marketing.transaction_count == 3
    assert marketing.percentage == 60.0


def test_the_first_spelling_is_kept_for_display():
    """
    Not lowercased. The palette is assigned by name, so the PDF and the page
    must land on the same string or a category changes colour between them.
    """
    m = compute_metrics(MIXED)
    assert [r.category for r in m.expense_by_category][0] == "Marketing"
    assert next(r.category for r in m.revenue_by_category) == "Sales"


def test_percentages_still_sum_to_a_hundred():
    m = compute_metrics(MIXED)
    assert round(sum(r.percentage for r in m.expense_by_category), 1) == 100.0


# ── The other metrics that grouped by category ──────────────────────────────

def test_the_model_is_given_one_name_per_category():
    """
    real_*_categories is handed to the prompt as the ONLY names the model may
    use. Three spellings invited it to treat one category as three.
    """
    m = compute_metrics(MIXED)
    assert sorted(n.lower() for n in m.real_expense_categories) == ["marketing", "payroll"]
    assert [n.lower() for n in m.real_income_categories] == ["sales"]


def test_income_shares_are_not_split_across_spellings():
    m = compute_metrics(MIXED)
    assert len(m.income_by_category) == 1
    assert list(m.income_by_category.values())[0] == 3_000_000
    assert round(sum(m.income_category_share.values())) == 100


def test_anomaly_detection_sees_one_series_not_three():
    """
    A category split across spellings looks like several small categories that
    appear and vanish between months — the detector's definition of an anomaly.
    """
    split = [
        _tx("2026-01-10", 100_000, "expense", "Marketing"),
        _tx("2026-02-10", 100_000, "expense", "marketing"),
        _tx("2026-03-10", 100_000, "expense", "MARKETING"),
        _tx("2026-01-11", 500_000, "expense", "payroll"),
        _tx("2026-02-11", 500_000, "expense", "payroll"),
        _tx("2026-03-11", 500_000, "expense", "payroll"),
    ]
    m = compute_metrics(split)
    # Steady spend, written three ways: nothing appeared and nothing vanished.
    invented = [a for a in m.anomalies if a.category.lower() == "marketing"]
    assert not invented, f"the case split invented anomalies: {invented}"


def test_anomalies_report_the_users_spelling():
    m = compute_metrics(MIXED)
    for a in m.anomalies:
        assert a.category == a.category.strip()
        assert not a.category.isupper() or a.category == "MARKETING"


def test_a_single_spelling_dataset_is_unaffected():
    """Regression: ordinary data must behave exactly as before."""
    plain = [
        _tx("2026-01-10", 300_000, "expense", "marketing"),
        _tx("2026-01-25", 400_000, "expense", "payroll"),
        _tx("2026-01-05", 1_000_000, "income", "sales"),
    ]
    m = compute_metrics(plain)
    assert {r.category for r in m.expense_by_category} == {"marketing", "payroll"}
    assert m.expense_by_category[0].total == 400_000


# ── 2. The untranslated section heading ─────────────────────────────────────

def _locale(lang: str) -> dict:
    return json.load(io.open(os.path.join(LOCALES, f"{lang}.json"), encoding="utf-8"))


NEW_KEYS = [
    "top_risks_title", "col_risk", "col_impact", "col_recommendation",
    "monthly_chart_title", "growth_chart_title",
]


@pytest.mark.parametrize("lang", ["ru", "uz", "en"])
@pytest.mark.parametrize("key", NEW_KEYS)
def test_every_new_label_exists_in_every_language(lang, key):
    assert _locale(lang)["report"].get(key), f"{lang}.report.{key} is missing"


def test_the_reported_heading_is_translated():
    assert _locale("en")["report"]["top_risks_title"] == "Top risks"
    assert _locale("ru")["report"]["top_risks_title"] == "Топ рисков"
    assert _locale("uz")["report"]["top_risks_title"] != _locale("ru")["report"]["top_risks_title"]


def test_no_report_component_still_hardcodes_russian():
    """
    The brief asked not to fix one label. These components had a whole cluster:
    the risks table's three column headers and both chart titles were in the
    same state and only the heading had been noticed.
    """
    import glob
    import re

    components = os.path.join(REPO_ROOT, "bytereport-frontend", "src", "components", "report")
    offenders = {}
    for path in glob.glob(os.path.join(components, "*.tsx")):
        src = io.open(path, encoding="utf-8").read()
        # Comments explain the bugs in Russian; they render nothing.
        src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
        src = "\n".join(line.split("//")[0] for line in src.split("\n"))
        hits = [
            m.group(1).strip()
            for m in re.finditer(r"[>\"'`]\s*([А-ЯЁа-яё][^<>{}\"'`\n]{2,60})", src)
        ]
        if hits:
            offenders[os.path.basename(path)] = hits
    assert not offenders, f"hardcoded Russian left in: {offenders}"


def test_two_raw_names_that_share_a_label_become_one_wedge():
    """
    Found while verifying the donut, and it is a second collision: "Реклама"
    and "marketing" are different raw strings that both render as "Marketing".
    Merging on the raw name alone left two legend entries reading identically —
    the same symptom the report described, from a different cause. Anything a
    reader cannot tell apart has to be one wedge, so the merge runs on the
    LABEL.
    """
    from app.services.chart_renderer import merge_categories_by_case
    from app.utils.category_mapper import category_label

    rows = [
        {"category": "Marketing", "total": 300_000},
        {"category": "marketing", "total": 200_000},
        {"category": "MARKETING ", "total": 100_000},
        {"category": "Реклама", "total": 150_000},
        {"category": "payroll", "total": 900_000},
    ]
    labelled = [{**r, "category": category_label(r["category"], "en")} for r in rows]
    merged = merge_categories_by_case(labelled)
    by_name = {r["category"]: r["total"] for r in merged}
    assert set(by_name) == {"Marketing", "Payroll"}
    assert by_name["Marketing"] == 750_000


def test_the_donut_labels_before_it_merges():
    """Order matters; merging first leaves the duplicate labels behind."""
    import inspect

    from app.services import chart_renderer as cr

    src = inspect.getsource(cr.render_expense_donut)
    assert src.index("category_label(") < src.index("merge_categories_by_case(")
