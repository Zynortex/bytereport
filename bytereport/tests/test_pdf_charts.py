"""Tests for PDF chart rendering (chart_renderer + pdf_generator wiring)."""

import re

import pytest

from app.services import chart_renderer as cr
from app.services.pdf_generator import PDF_LABELS, _build_charts, _styles

LABELS = PDF_LABELS["ru"]

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _metrics() -> dict:
    return {
        "monthly_breakdown": [
            {"month": "2024-01", "revenue": 1_240_000, "expenses": 1_090_000, "profit": 150_000},
            {"month": "2024-02", "revenue": 1_015_000, "expenses": 1_180_000, "profit": -165_000},
            {"month": "2024-03", "revenue": 1_890_000, "expenses": 1_210_000, "profit": 680_000},
        ],
        "expense_by_category": [
            {"category": "Материалы", "total": 1_520_000, "transaction_count": 47},
            {"category": "Зарплата", "total": 980_000, "transaction_count": 12},
        ],
        "mom_growth": [
            {"month": "2024-02", "revenue_growth_pct": -18.1, "expense_growth_pct": 8.3, "profit_growth_pct": -210.0},
            {"month": "2024-03", "revenue_growth_pct": 86.2, "expense_growth_pct": 2.5, "profit_growth_pct": None},
        ],
        "cashflow_forecast": {
            "has_risk": True,
            "weekly_projection": [
                {"week": 1, "projected_balance": 420_000},
                {"week": 2, "projected_balance": -180_000},
            ],
        },
    }


# ── Each renderer produces a real PNG ───────────────────────────────────────

@pytest.mark.parametrize("fn_name", [
    "render_monthly_bars",
    "render_expense_donut",
    "render_growth_lines",
    "render_cashflow_forecast",
])
def test_renderer_returns_png(fn_name):
    png = getattr(cr, fn_name)(_metrics(), LABELS)
    assert png is not None, f"{fn_name} returned None for full metrics"
    assert png.startswith(PNG_MAGIC), f"{fn_name} did not return PNG bytes"
    assert len(png) > 1000


# ── Missing data is skipped, not crashed on ─────────────────────────────────

@pytest.mark.parametrize("fn_name", [
    "render_monthly_bars",
    "render_expense_donut",
    "render_growth_lines",
    "render_cashflow_forecast",
])
def test_renderer_returns_none_on_empty_metrics(fn_name):
    assert getattr(cr, fn_name)({}, LABELS) is None


def test_growth_lines_none_when_all_series_null():
    """Every growth value null → no chart, rather than a flat line at zero."""
    m = {"mom_growth": [
        {"month": "2024-02", "revenue_growth_pct": None,
         "expense_growth_pct": None, "profit_growth_pct": None},
    ]}
    assert cr.render_growth_lines(m, LABELS) is None


# ── Задача 2.3: category case normalization ─────────────────────────────────

def test_merge_categories_folds_case_variants():
    rows = [
        {"category": "marketing",  "total": 50_000, "transaction_count": 4},
        {"category": "Marketing",  "total": 30_000, "transaction_count": 3},
        {"category": "MARKETING ", "total": 16_000, "transaction_count": 2},
    ]
    merged = cr.merge_categories_by_case(rows)
    assert len(merged) == 1
    assert merged[0]["total"] == 96_000
    assert merged[0]["transaction_count"] == 9


def test_merge_categories_keeps_distinct_categories_separate():
    rows = [
        {"category": "Материалы", "total": 100},
        {"category": "Зарплата", "total": 200},
    ]
    assert len(cr.merge_categories_by_case(rows)) == 2


def test_merge_categories_folds_cyrillic_case():
    rows = [
        {"category": "Материалы", "total": 1_200_000},
        {"category": "материалы", "total": 320_000},
    ]
    merged = cr.merge_categories_by_case(rows)
    assert len(merged) == 1
    assert merged[0]["total"] == 1_520_000


def test_merge_categories_uses_same_key_as_category_mapper():
    """Folding key must match normalize_category()'s `raw.lower().strip()`."""
    from app.utils.category_mapper import normalize_category
    raw = "  MARKETING  "
    # normalize_category lowercases+strips before matching keywords; an unmapped
    # value falls through to raw.strip(). Our fold key is the lowercase form.
    assert normalize_category(raw, "expense") == raw.strip()
    merged = cr.merge_categories_by_case([
        {"category": raw, "total": 1}, {"category": "marketing", "total": 1},
    ])
    assert len(merged) == 1


def test_merge_categories_ignores_blank_names():
    rows = [{"category": "", "total": 10}, {"category": "   ", "total": 20},
            {"category": "Аренда", "total": 30}]
    merged = cr.merge_categories_by_case(rows)
    assert len(merged) == 1
    assert merged[0]["category"] == "Аренда"


def test_donut_merges_case_variants_into_one_wedge():
    """End-to-end: three spellings must not become three wedges."""
    m = {"expense_by_category": [
        {"category": "marketing", "total": 50_000},
        {"category": "Marketing", "total": 30_000},
        {"category": "MARKETING", "total": 16_000},
    ]}
    assert len(cr.merge_categories_by_case(m["expense_by_category"])) == 1
    assert cr.render_expense_donut(m, LABELS) is not None


# ── pdf_generator wiring ────────────────────────────────────────────────────

def test_build_charts_returns_empty_without_metrics():
    assert _build_charts(None, _styles(), LABELS) == []
    assert _build_charts({}, _styles(), LABELS) == []


def test_build_charts_produces_flowables():
    elements = _build_charts(_metrics(), _styles(), LABELS)
    assert elements, "expected chart flowables for full metrics"


def test_build_charts_survives_a_failing_renderer(monkeypatch, caplog):
    """One broken chart must not take down the whole PDF."""
    def boom(metrics, labels):
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(cr, "render_monthly_bars", boom)
    with caplog.at_level("ERROR"):
        elements = _build_charts(_metrics(), _styles(), LABELS)

    # The other three charts still render...
    assert elements
    # ...and the failure is logged loudly, not swallowed.
    assert any("failed to render" in r.message for r in caplog.records)


# ── Labels present in every language ────────────────────────────────────────

@pytest.mark.parametrize("lang", ["ru", "uz", "en"])
def test_chart_labels_present(lang):
    required = {
        "charts_section", "chart_monthly", "chart_expenses_by_cat",
        "chart_growth", "chart_forecast", "chart_revenue",
        "chart_expenses", "chart_profit", "chart_other", "chart_cash_gap",
    }
    missing = required - set(PDF_LABELS[lang])
    assert not missing, f"{lang} missing chart labels: {missing}"


def test_uz_chart_labels_are_cyrillic():
    """Uzbek labels must be Cyrillic, matching the rest of the uz PDF."""
    for key in ("chart_revenue", "chart_expenses", "chart_profit", "charts_section"):
        value = PDF_LABELS["uz"][key]
        assert re.search(r"[А-Яа-яЎўҒғҚқҲҳ]", value), f"uz {key!r} is not Cyrillic: {value!r}"


# ── Full PDF integration ────────────────────────────────────────────────────

def _min_report():
    from app.models.report import AIReport
    return AIReport(**{
        "executive_summary": "Тест",
        "financial_health_score": {"score": 61, "status": "СТАБИЛЬНОЕ", "reasoning": "Тест"},
        "key_insights": [], "top_risks": [], "growth_opportunities": [],
        "expense_analysis": {"problem_categories": [], "efficient_categories": [], "notes": ""},
        "anomalies": [],
        "cash_flow_analysis": {"status": "OK", "summary": "Тест", "warning_level": "low"},
        "forecast": {"outlook": "OK", "confidence": "medium", "summary": "Тест"},
        "priority_actions": [],
    })


def test_pdf_with_metrics_embeds_images():
    from app.services.pdf_generator import generate_pdf
    pdf = generate_pdf(report=_min_report(), business_name="Тест",
                       metrics=_metrics(), language="ru")
    assert pdf.startswith(b"%PDF")
    assert len(re.findall(rb"/Subtype\s*/Image", pdf)) >= 4, \
        "expected at least 4 embedded chart images"


def test_pdf_without_metrics_still_builds():
    """Backward compatibility: no metrics → text-only PDF, no crash."""
    from app.services.pdf_generator import generate_pdf
    pdf = generate_pdf(report=_min_report(), business_name="Тест", metrics=None)
    assert pdf.startswith(b"%PDF")
    assert not re.findall(rb"/Subtype\s*/Image", pdf)
