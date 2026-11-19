"""
Part A — category-coverage signal, and Part B — PDF bank statements.

Three-level scale (category_coverage.py):
  coverage >= 0.70            -> "full"     breakdown as-is
  0.30 <= coverage < 0.70     -> "partial"  breakdown + measured-% caveat
  coverage <  0.30            -> "none"     breakdown suppressed
"""

import re

import pytest

from app.models.transaction import Transaction, TransactionType
from app.services.category_coverage import (
    FULL_THRESHOLD,
    PARTIAL_THRESHOLD,
    UNCATEGORIZED,
    classify_coverage,
    evaluate_categories,
    is_real_category,
)
from app.services.csv_parser import parse_upload
from app.services.no_category_prompt import NO_CATEGORY_DISCLAIMER, build_no_category_block
from app.services.pdf_statement import PdfStatementError, read_pdf_grid
from tests import fixtures_gen as F

from datetime import date


def _tx(category: str, raw: str | None = None) -> Transaction:
    return Transaction(
        date=date(2026, 1, 5), description="x", amount=100.0,
        type=TransactionType.expense, category=category, raw_category=raw,
    )


# ── A1: the signal itself ───────────────────────────────────────────────────

def test_thresholds_are_70_and_30():
    """Documented in the report; change here if the policy changes."""
    assert FULL_THRESHOLD == 0.70
    assert PARTIAL_THRESHOLD == 0.30


@pytest.mark.parametrize("value,expected", [
    ("payroll", True), ("Зарплата", True),
    (UNCATEGORIZED, False), ("", False), ("   ", False),
    (None, False), ("—", False), ("n/a", False), ("без категории", False),
])
def test_is_real_category(value, expected):
    assert is_real_category(value) is expected


def test_full_categories_are_reliable():
    signal = evaluate_categories([_tx("payroll") for _ in range(10)])
    assert signal.coverage == 1.0
    assert signal.level == "full"
    assert signal.reliable is True


def test_all_uncategorized_is_unreliable():
    signal = evaluate_categories([_tx(UNCATEGORIZED) for _ in range(10)])
    assert signal.coverage == 0.0
    assert signal.level == "none"
    assert signal.reliable is False


def test_empty_transaction_list_is_unreliable():
    """No evidence of categories → suppress category output (safe direction)."""
    assert evaluate_categories([]).level == "none"


def test_raw_category_counts_even_if_normalised_is_empty():
    signal = evaluate_categories([_tx("", raw="Аренда цеха")])
    assert signal.coverage == 1.0


@pytest.mark.parametrize("categorized,total,expected_level", [
    (0, 100, "none"),
    (29, 100, "none"),      # 29% — just below partial
    (30, 100, "partial"),   # 30% — partial boundary, inclusive
    (40, 100, "partial"),   # 40% — the brief's intermediate case
    (69, 100, "partial"),   # 69% — just below full
    (70, 100, "full"),      # 70% — full boundary, inclusive
    (100, 100, "full"),
])
def test_three_level_boundaries(categorized, total, expected_level):
    txs = ([_tx("payroll")] * categorized) + ([_tx(UNCATEGORIZED)] * (total - categorized))
    signal = evaluate_categories(txs)
    assert signal.level == expected_level
    assert signal.coverage == pytest.approx(categorized / total)


def test_intermediate_40_percent_is_partial():
    """40% coverage → breakdown shown, but flagged with the real percentage."""
    txs = ([_tx("payroll")] * 4) + ([_tx(UNCATEGORIZED)] * 6)
    signal = evaluate_categories(txs)
    assert signal.coverage == pytest.approx(0.4)
    assert signal.level == "partial"
    assert signal.coverage_percent == 40
    assert signal.reliable is True   # legacy alias still truthy


@pytest.mark.parametrize("coverage,level", [
    (0.0, "none"), (0.2999, "none"), (0.30, "partial"),
    (0.6999, "partial"), (0.70, "full"), (1.0, "full"),
])
def test_classify_coverage_directly(coverage, level):
    assert classify_coverage(coverage) == level


def test_legacy_bool_alias_matches_level():
    for cat, expected in ((0, False), (30, True), (100, True)):
        txs = ([_tx("payroll")] * cat) + ([_tx(UNCATEGORIZED)] * (100 - cat))
        assert evaluate_categories(txs).reliable is expected


def test_signal_is_computed_once_and_shared():
    """The flag reaching every surface comes from this one function."""
    import app.api.routes.analyze as analyze_route
    import app.services.category_coverage as cc
    assert analyze_route.evaluate_categories is cc.evaluate_categories


# ── A1: regression — categorised CSV keeps working ──────────────────────────

def test_categorised_csv_is_reliable():
    parsed = parse_upload(F.csv_utf8(), "a.csv")
    signal = evaluate_categories(parsed.transactions)
    assert signal.coverage == 1.0
    assert signal.level == "full"


def test_metrics_defaults_preserve_existing_behaviour():
    """A FinancialMetrics built without the new fields still looks categorised."""
    from app.services.financial_engine import compute_metrics
    from app.services.preprocessing import preprocess_transactions
    clean, _ = preprocess_transactions(parse_upload(F.csv_utf8(), "a.csv").transactions)
    m = compute_metrics(clean)
    assert m.category_reliability == "full"
    assert m.has_reliable_categories is True      # legacy alias
    assert m.category_coverage == 1.0
    # the alias must survive serialisation — PDF/frontend read the dict
    assert m.model_dump()["has_reliable_categories"] is True


# ── A2: prompt behaviour ────────────────────────────────────────────────────

def test_no_category_block_forbids_invented_categories():
    block = build_no_category_block("ru", 0.0)
    assert "НЕ выдумывай" in block
    assert "процентных" in block


def test_no_category_block_forbids_health_score_submetrics():
    block = build_no_category_block("ru", 0.0)
    assert "ликвидность" in block.lower()
    assert "НЕ рассчитываются" in block or "не рассчитываются" in block.lower()


def test_no_category_block_forbids_daily_granularity():
    block = build_no_category_block("ru", 0.0)
    assert "день к дню" in block
    assert "ПОМЕСЯЧНЫЕ" in block and "ПОНЕДЕЛЬНЫЙ" in block


def test_no_category_block_requires_empty_lists_not_null():
    """Schema check: ExpenseAnalysis lists are required, so [] not null."""
    block = build_no_category_block("ru", 0.0)
    assert "ПУСТЫМИ СПИСКАМИ" in block
    assert "не null" in block


def test_expense_analysis_schema_accepts_empty_lists():
    """Confirms the instruction above is actually valid against the model."""
    from app.models.report import ExpenseAnalysis
    ea = ExpenseAnalysis(problem_categories=[], efficient_categories=[], notes="нет категорий")
    assert ea.problem_categories == []


@pytest.mark.parametrize("lang", ["ru", "uz", "en"])
def test_disclaimer_present_in_every_language(lang):
    block = build_no_category_block(lang, 0.0)
    assert NO_CATEGORY_DISCLAIMER[lang] in block


def test_uzbek_disclaimer_is_cyrillic():
    text = NO_CATEGORY_DISCLAIMER["uz"]
    assert re.search(r"[А-Яа-яЎўҒғҚқҲҳ]", text)
    # No Latin words leaking into Uzbek prose (1С/bank-client brand names aside).
    assert not re.search(r"\b[a-z]{4,}\b", text.replace("1С", ""))


def test_prompt_switches_on_the_flag():
    """Category-free mode replaces the strict category-name list, not adds to it."""
    import app.services.ai_analyst as aa
    src = __import__("inspect").getsource(aa.get_ai_analysis)
    assert "has_reliable_categories" in src
    assert "build_no_category_block" in src


# ── A3: PDF report rendering ────────────────────────────────────────────────

def _minimal_report():
    from app.models.report import AIReport
    return AIReport(**{
        "executive_summary": "Тест",
        "financial_health_score": {"score": 61, "status": "СТАБИЛЬНОЕ", "reasoning": "Тест"},
        "key_insights": [], "top_risks": [], "growth_opportunities": [],
        "expense_analysis": {"problem_categories": [], "efficient_categories": [], "notes": "нет"},
        "anomalies": [],
        "cash_flow_analysis": {"status": "OK", "summary": "Тест", "warning_level": "low"},
        "forecast": {"outlook": "OK", "confidence": "medium", "summary": "Тест"},
        "priority_actions": [],
    })


def _metrics_dict(reliable: bool) -> dict:
    return {
        "monthly_breakdown": [
            {"month": "2026-01", "revenue": 100, "expenses": 60, "profit": 40},
            {"month": "2026-02", "revenue": 120, "expenses": 80, "profit": 40},
        ],
        "expense_by_category": [{"category": "payroll", "total": 60, "transaction_count": 2}],
        "mom_growth": [{"month": "2026-02", "revenue_growth_pct": 20.0,
                        "expense_growth_pct": 33.0, "profit_growth_pct": 0.0}],
        "cashflow_forecast": {"has_risk": False, "weekly_projection": [
            {"week": 1, "projected_balance": 100}, {"week": 2, "projected_balance": 90}]},
        "category_reliability": "full" if reliable else "none",
        "category_coverage": 1.0 if reliable else 0.0,
    }


def test_pdf_hides_donut_when_categories_unreliable():
    from app.services.pdf_generator import PDF_LABELS, _build_charts, _styles
    st, labels = _styles(), PDF_LABELS["ru"]
    with_cats = _build_charts(_metrics_dict(True), st, labels)
    without = _build_charts(_metrics_dict(False), st, labels)
    # One fewer chart flowable group when the donut is suppressed.
    assert len(without) < len(with_cats)


def test_pdf_expense_section_replaced_with_note():
    from app.services.pdf_generator import PDF_LABELS, _build_expense_analysis, _styles
    st, labels = _styles(), PDF_LABELS["ru"]
    elements = _build_expense_analysis(_minimal_report(), st, labels, _metrics_dict(False))
    rendered = " ".join(getattr(e, "text", "") for e in elements if hasattr(e, "text"))
    assert labels["no_categories_note"] in rendered


def test_pdf_expense_section_intact_when_reliable():
    from app.services.pdf_generator import PDF_LABELS, _build_expense_analysis, _styles
    st, labels = _styles(), PDF_LABELS["ru"]
    elements = _build_expense_analysis(_minimal_report(), st, labels, _metrics_dict(True))
    rendered = " ".join(getattr(e, "text", "") for e in elements if hasattr(e, "text"))
    assert labels["no_categories_note"] not in rendered


@pytest.mark.parametrize("lang", ["ru", "uz", "en"])
def test_no_categories_note_localised(lang):
    from app.services.pdf_generator import PDF_LABELS
    assert PDF_LABELS[lang]["no_categories_note"].strip()


def test_full_pdf_builds_without_categories():
    from app.services.pdf_generator import generate_pdf
    pdf = generate_pdf(report=_minimal_report(), business_name="Тест",
                       metrics=_metrics_dict(False), language="ru")
    assert pdf.startswith(b"%PDF")


# ── B: PDF statement parsing ────────────────────────────────────────────────

EXPECTED = len(F.all_rows())


def test_pdf_statement_detected_by_signature():
    from app.services.file_reader import detect_format
    assert detect_format(F.bank_statement_pdf()) == "pdf"


def test_pdf_statement_parses_all_rows():
    r = parse_upload(F.bank_statement_pdf(), "statement.pdf")
    assert len(r.transactions) == EXPECTED


def test_pdf_multipage_headers_not_duplicated_as_data():
    """The header repeats on every page; none may become a transaction."""
    grid = read_pdf_grid(F.bank_statement_pdf())
    header_like = [r for r in grid[1:] if "дата" in " ".join(r).lower()]
    assert not header_like, f"header leaked into data rows: {header_like}"
    assert len(grid) - 1 == EXPECTED


def test_pdf_bank_noise_removed():
    grid = read_pdf_grid(F.bank_statement_pdf())
    joined = " ".join(" ".join(r) for r in grid).lower()
    for noise in ("демо банк", "расчётный счёт", "страница", "инн"):
        assert noise not in joined, f"noise survived: {noise}"


def test_pdf_debit_credit_mapped_to_expense_income():
    r = parse_upload(F.bank_statement_pdf(), "s.pdf")
    kinds = {t.type.value for t in r.transactions}
    assert kinds == {"income", "expense"}
    salary = [t for t in r.transactions if "Зарплата" in t.description]
    assert salary and all(t.type.value == "expense" for t in salary)


def test_pdf_mixed_date_formats_parsed():
    r = parse_upload(F.bank_statement_pdf(), "s.pdf")
    dates = {t.date.isoformat() for t in r.transactions}
    assert "2026-01-05" in dates      # came in as 05.01.2026
    assert "2026-02-07" in dates      # came in as ISO


def test_pdf_amounts_with_space_separators_parsed():
    r = parse_upload(F.bank_statement_pdf(), "s.pdf")
    amounts = {t.amount for t in r.transactions}
    assert 50_000_000.0 in amounts
    assert 150_000_000.0 in amounts


def test_pdf_transactions_are_uncategorized():
    r = parse_upload(F.bank_statement_pdf(), "s.pdf")
    assert all(t.category == UNCATEGORIZED for t in r.transactions)


def test_pdf_source_drives_signal_false():
    """Part B naturally triggers Part A — the whole point of the pairing."""
    r = parse_upload(F.bank_statement_pdf(), "s.pdf")
    signal = evaluate_categories(r.transactions)
    assert signal.coverage == 0.0
    assert signal.level == "none"


def test_pdf_traps_caught_by_preprocessing_like_csv():
    """Duplicate and future-dated rows must behave exactly as in the CSV path."""
    from app.services.preprocessing import preprocess_transactions
    pdf = parse_upload(F.bank_statement_pdf_with_traps(), "s.pdf")
    csv = parse_upload(F.csv_utf8(), "a.csv")

    p_clean, p_meta = preprocess_transactions(pdf.transactions)
    c_clean, c_meta = preprocess_transactions(csv.transactions)

    assert len(p_meta["future_transactions"]) == len(c_meta["future_transactions"]) == 1
    assert len(p_meta["possible_duplicates"]) == len(c_meta["possible_duplicates"]) == 1
    assert p_meta["possible_duplicates"][0]["count"] == 2
    assert len(p_clean) == len(c_clean)


def test_scanned_pdf_rejected_with_clear_message():
    with pytest.raises(ValueError) as exc:
        parse_upload(F.scanned_pdf(), "scan.pdf")
    msg = str(exc.value)
    assert "отсканированное" in msg
    assert "Traceback" not in msg


def test_scanned_pdf_raises_specific_error_type():
    with pytest.raises(PdfStatementError):
        read_pdf_grid(F.scanned_pdf())


def test_non_statement_pdf_gives_clean_error():
    """A PDF with text but no transaction table is refused, not half-parsed."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas as _canvas
    import io as _io
    from app.services.pdf_generator import FONT_REGULAR

    buf = _io.BytesIO()
    c = _canvas.Canvas(buf, pagesize=A4)
    c.setFont(FONT_REGULAR, 12)
    for i in range(20):
        c.drawString(60, 700 - i * 18, "Это обычный текстовый документ без таблицы операций.")
    c.showPage()
    c.save()

    with pytest.raises(ValueError) as exc:
        parse_upload(buf.getvalue(), "letter.pdf")
    assert "Traceback" not in str(exc.value)


# ── Constraint: existing formats untouched ──────────────────────────────────

@pytest.mark.parametrize("data,name", [
    (F.csv_utf8(), "a.csv"),
    (F.csv_cp1251(), "b.csv"),
    (F.xlsx_bytes(), "c.xlsx"),
    (F.xls_legacy_bytes(), "d.xls"),
    (F.html_as_xls_bytes(), "e.xls"),
])
def test_existing_formats_still_parse_and_stay_categorised(data, name):
    r = parse_upload(data, name)
    assert len(r.transactions) == EXPECTED
    assert evaluate_categories(r.transactions).level == "full"


# ── Partial branch: prompt + PDF ────────────────────────────────────────────

def test_partial_block_states_real_percentage_not_vague_phrase():
    from app.services.no_category_prompt import build_partial_category_block
    block = build_partial_category_block("ru", 0.42, ["sales"], ["payroll"])
    assert "42%" in block
    assert "некоторых" not in block and "части транзакций" not in block


def test_partial_block_still_lists_allowed_category_names():
    from app.services.no_category_prompt import build_partial_category_block
    block = build_partial_category_block("ru", 0.42, ["sales"], ["payroll"])
    assert "sales" in block and "payroll" in block
    assert "СТРОГИЕ НАЗВАНИЯ КАТЕГОРИЙ" in block


def test_partial_block_keeps_submetric_and_daily_bans():
    from app.services.no_category_prompt import build_partial_category_block
    block = build_partial_category_block("ru", 0.42, [], [])
    assert "ликвидность" in block.lower()
    assert "день к дню" in block


def test_partial_block_forbids_extrapolation():
    from app.services.no_category_prompt import build_partial_category_block
    block = build_partial_category_block("ru", 0.42, [], [])
    assert "НЕ экстраполируй" in block


@pytest.mark.parametrize("lang", ["ru", "uz", "en"])
def test_partial_caveat_localised_with_percent(lang):
    from app.services.no_category_prompt import PARTIAL_CATEGORY_CAVEAT, build_partial_category_block
    assert "{percent}" in PARTIAL_CATEGORY_CAVEAT[lang]
    block = build_partial_category_block(lang, 0.55, [], [])
    assert "55%" in block


def _metrics_level(level: str, coverage: float) -> dict:
    m = _metrics_dict(True)
    m.pop("has_reliable_categories", None)
    m["category_reliability"] = level
    m["category_coverage"] = coverage
    return m


def test_pdf_partial_shows_breakdown_with_caveat():
    from app.services.pdf_generator import PDF_LABELS, _build_expense_analysis, _styles
    st, labels = _styles(), PDF_LABELS["ru"]
    els = _build_expense_analysis(_minimal_report(), st, labels, _metrics_level("partial", 0.42))
    txt = " ".join(getattr(e, "text", "") for e in els if hasattr(e, "text"))
    assert "42%" in txt
    assert labels["no_categories_note"] not in txt


def test_pdf_partial_keeps_donut_chart():
    from app.services.pdf_generator import PDF_LABELS, _build_charts, _styles
    st, labels = _styles(), PDF_LABELS["ru"]
    partial = _build_charts(_metrics_level("partial", 0.42), st, labels)
    none_ = _build_charts(_metrics_level("none", 0.0), st, labels)
    full = _build_charts(_metrics_level("full", 1.0), st, labels)
    assert len(partial) == len(full) > len(none_)


def test_pdf_full_has_no_caveat():
    from app.services.pdf_generator import PDF_LABELS, _build_expense_analysis, _styles
    st, labels = _styles(), PDF_LABELS["ru"]
    els = _build_expense_analysis(_minimal_report(), st, labels, _metrics_level("full", 1.0))
    txt = " ".join(getattr(e, "text", "") for e in els if hasattr(e, "text"))
    assert "%" not in txt or "100%" not in txt


def test_pdf_legacy_bool_payload_still_renders():
    """A stored payload with only the old boolean must not break rendering."""
    from app.services.pdf_generator import _category_level
    assert _category_level({"has_reliable_categories": False}) == "none"
    assert _category_level({"has_reliable_categories": True}) == "full"
    assert _category_level({}) == "full"
    assert _category_level(None) == "full"


@pytest.mark.parametrize("lang", ["ru", "uz", "en"])
def test_pdf_partial_note_localised(lang):
    from app.services.pdf_generator import PDF_LABELS
    note = PDF_LABELS[lang]["partial_categories_note"]
    assert "{percent}" in note
    assert note.format(percent=42).count("42%") == 1


# ── Task 2: the extract_text() fallback is genuinely reached ────────────────

def test_no_table_fixture_defeats_extract_tables():
    """Guards the premise: if this ever yields tables, the fallback is dead code."""
    import io as _io
    import pdfplumber
    with pdfplumber.open(_io.BytesIO(F.bank_statement_pdf_no_table())) as pdf:
        tables = [t for p in pdf.pages for t in (p.extract_tables() or [])]
    assert tables == [], "fixture gained a table structure; fallback no longer exercised"


def test_fallback_extracts_all_transactions():
    r = parse_upload(F.bank_statement_pdf_no_table(), "plain.pdf")
    assert len(r.transactions) == EXPECTED


def test_fallback_amounts_and_types_exact():
    r = parse_upload(F.bank_statement_pdf_no_table(), "plain.pdf")
    got = [(t.amount, t.type.value) for t in r.transactions]
    expected = [(float(a), k) for _d, a, k, _c, _x in F.all_rows()]
    assert got == expected


def test_fallback_rows_are_uncategorized():
    r = parse_upload(F.bank_statement_pdf_no_table(), "plain.pdf")
    assert all(t.category == UNCATEGORIZED for t in r.transactions)
    assert evaluate_categories(r.transactions).level == "none"


def test_fallback_traps_still_caught():
    from app.services.preprocessing import preprocess_transactions
    r = parse_upload(F.bank_statement_pdf_no_table(), "plain.pdf")
    _, meta = preprocess_transactions(r.transactions)
    assert len(meta["future_transactions"]) == 1
    assert len(meta["possible_duplicates"]) == 1


# Balance heuristic — the cases that the ruled fixture could not expose.
@pytest.mark.parametrize("line,amount,kind", [
    ("05.01.2026  Оплата аренды  -20 000 000.00", "20 000 000.00", "expense"),
    ("05.01.2026  Оплата по счёту №123 от 04.01  -20 000 000.00", "20 000 000.00", "expense"),
    ("05.01.2026  Оплата аренды  -20 000 000.00  130 000 000.00", "20 000 000.00", "expense"),
    ("05.01.2026  Счёт 456  -20 000 000.00  130 000 000.00", "20 000 000.00", "expense"),
    ("07.02.2026  Поступление  60 000 000.00", "60 000 000.00", "income"),
    ("07.02.2026  Поступление  60 000 000.00  190 000 000.00", "60 000 000.00", "income"),
])
def test_balance_heuristic_edge_cases(line, amount, kind):
    """
    Two defects the clean fixture hid:
      * a date inside the description ("от 04.01") was read as the amount;
      * the money regex spanned whitespace and merged amount+balance into one
        token, so the amount-vs-balance choice never actually ran.
    """
    from app.services.pdf_statement import _rows_from_text
    grid = _rows_from_text(line)
    assert len(grid) == 2, f"line not parsed: {line!r}"
    assert grid[1][1] == amount
    assert grid[1][2] == kind
