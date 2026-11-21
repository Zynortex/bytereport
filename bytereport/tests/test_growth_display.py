"""
MoM growth display safety (near-zero base) and the PDF chart polish fixes.
"""

from datetime import date

import pytest

from app.models.transaction import Transaction, TransactionType
from app.services import chart_renderer as cr
from app.services.financial_engine import compute_metrics
from app.services.growth_display import (
    MOM_OUTLIER_THRESHOLD_PCT,
    collect_outliers,
    display_value,
    is_outlier,
)
from app.services.pdf_generator import PDF_LABELS

LABELS = PDF_LABELS["ru"]


def _tx(d: str, amount: float, kind: str, cat: str = "sales") -> Transaction:
    return Transaction(date=date.fromisoformat(d), description=cat, amount=amount,
                       type=TransactionType(kind), category=cat, raw_category=cat)


# Jan is tiny, Feb lands one big contract, Mar returns to normal.
# revenue 15 000 -> 280 000 (+1767%), profit 1 000 -> 220 000 (+21 900%).
OUTLIER_TXNS = [
    _tx("2026-01-10",  15_000, "income"),
    _tx("2026-01-15",  14_000, "expense", "payroll"),
    _tx("2026-02-10", 280_000, "income"),
    _tx("2026-02-15",  60_000, "expense", "payroll"),
    _tx("2026-03-10", 120_000, "income"),
    _tx("2026-03-15",  70_000, "expense", "payroll"),
]


# ── Threshold rule ──────────────────────────────────────────────────────────

def test_threshold_is_300_percent():
    assert MOM_OUTLIER_THRESHOLD_PCT == 300.0


@pytest.mark.parametrize("pct,expected", [
    (None, False), (0.0, False), (100.0, False), (-100.0, False),
    (300.0, False),      # exactly at the limit is still plottable
    (300.1, True), (-300.1, True), (1766.67, True), (21900.0, True),
])
def test_is_outlier(pct, expected):
    assert is_outlier(pct) is expected


@pytest.mark.parametrize("pct,expected", [
    (None, None), (50.0, 50.0), (-299.0, -299.0), (1766.67, None), (-9999.0, None),
])
def test_display_value(pct, expected):
    assert display_value(pct) == expected


def test_collect_outliers_carries_real_amounts():
    out = collect_outliers(
        "2026-02",
        {"revenue": 1766.67, "expenses": 10.0, "profit": 21900.0},
        {"revenue": 15_000, "expenses": 14_000, "profit": 1_000},
        {"revenue": 280_000, "expenses": 15_400, "profit": 220_000},
    )
    metrics = {o.metric for o in out}
    assert metrics == {"revenue", "profit"}          # expenses was in range
    rev = next(o for o in out if o.metric == "revenue")
    assert rev.previous == 15_000 and rev.current == 280_000


# ── One source: engine output ───────────────────────────────────────────────

def test_engine_keeps_raw_pct_and_nulls_display():
    m = compute_metrics(OUTLIER_TXNS)
    feb = m.mom_growth[0]
    assert feb.month == "2026-02"
    # raw values preserved — nothing downstream loses information
    assert feb.revenue_growth_pct == pytest.approx(1766.67)
    assert feb.profit_growth_pct == pytest.approx(21900.0)
    # display values withheld
    assert feb.revenue_growth_display is None
    assert feb.profit_growth_display is None


def test_engine_keeps_in_range_month_plottable():
    m = compute_metrics(OUTLIER_TXNS)
    mar = m.mom_growth[1]
    assert mar.month == "2026-03"
    assert mar.revenue_growth_display == mar.revenue_growth_pct
    assert mar.profit_growth_display == mar.profit_growth_pct


def test_engine_emits_structured_outliers():
    m = compute_metrics(OUTLIER_TXNS)
    assert len(m.mom_outliers) == 3      # revenue, expenses (+329%), profit
    by_metric = {o.metric: o for o in m.mom_outliers}
    assert by_metric["profit"].previous == 1_000
    assert by_metric["profit"].current == 220_000
    assert all(o.month == "2026-02" for o in m.mom_outliers)


def test_normal_dataset_has_no_outliers_and_display_equals_raw():
    """Regression: ordinary data behaves exactly as before."""
    txns = [
        _tx("2026-01-10", 100_000, "income"), _tx("2026-01-15", 60_000, "expense", "payroll"),
        _tx("2026-02-10", 120_000, "income"), _tx("2026-02-15", 70_000, "expense", "payroll"),
    ]
    m = compute_metrics(txns)
    assert m.mom_outliers == []
    for row in m.mom_growth:
        assert row.revenue_growth_display == row.revenue_growth_pct
        assert row.expense_growth_display == row.expense_growth_pct


def test_display_fields_survive_serialisation():
    """Both the PDF and the frontend read model_dump(), not the model."""
    d = compute_metrics(OUTLIER_TXNS).model_dump(mode="json")
    assert d["mom_growth"][0]["revenue_growth_display"] is None
    assert d["mom_growth"][0]["revenue_growth_pct"] == pytest.approx(1766.67)
    assert len(d["mom_outliers"]) == 3


# ── PDF chart survives and annotates ────────────────────────────────────────

def test_growth_chart_renders_on_outlier_dataset():
    d = compute_metrics(OUTLIER_TXNS).model_dump(mode="json")
    png = cr.render_growth_lines(d, LABELS)
    assert png is not None and png.startswith(b"\x89PNG")


def test_outlier_notes_use_real_amounts_not_percentages():
    d = compute_metrics(OUTLIER_TXNS).model_dump(mode="json")
    notes = cr._outlier_notes(d, LABELS)
    assert len(notes) == 3
    joined = " ".join(notes)
    assert "15" in joined and "280" in joined     # real before/after figures
    assert "1766" not in joined and "21900" not in joined


def test_no_notes_for_clean_dataset():
    assert cr._outlier_notes({"mom_outliers": []}, LABELS) == []


def test_growth_chart_falls_back_to_raw_for_legacy_payloads():
    """A stored report predating the display fields must still plot."""
    legacy = {"mom_growth": [
        {"month": "2026-02", "revenue_growth_pct": 12.0,
         "expense_growth_pct": 5.0, "profit_growth_pct": 20.0},
        {"month": "2026-03", "revenue_growth_pct": -8.0,
         "expense_growth_pct": 3.0, "profit_growth_pct": -15.0},
    ]}
    assert cr.render_growth_lines(legacy, LABELS) is not None


@pytest.mark.parametrize("lang", ["ru", "uz", "en"])
def test_outlier_label_localised(lang):
    tpl = PDF_LABELS[lang]["chart_growth_outlier"]
    for token in ("{month}", "{metric}", "{previous}", "{current}"):
        assert token in tpl


# ── Task 3.1: donut palette ─────────────────────────────────────────────────

def test_donut_palette_has_no_semantic_traffic_light_colours():
    """Categories are not risk levels — no red/amber/green in the ramp."""
    banned = {"#DC2626", "#D97706", "#16A34A", "#65A30D"}
    upper = {c.upper() for c in cr.DONUT_COLORS}
    assert not (upper & banned), f"semantic colours leaked in: {upper & banned}"


def test_donut_palette_is_the_token_palette_without_violet():
    """
    Hue-varied (a monochrome ramp was unreadable past ~4 slices), taken from
    design-tokens.json, and in tune with the cyan/blue palette: no violet.
    """
    import colorsys

    from app.services.design_tokens import CATEGORY_COLORS

    assert cr.DONUT_COLORS == CATEGORY_COLORS
    for c in cr.DONUT_COLORS:
        r, g, b = (int(c[i:i + 2], 16) / 255 for i in (1, 3, 5))
        h, _l, s = colorsys.rgb_to_hls(r, g, b)
        assert not (s > 0.15 and 250 <= h * 360 <= 320), f"{c} is violet"


def test_donut_still_renders():
    png = cr.render_expense_donut({"expense_by_category": [
        {"category": "Материалы", "total": 100}, {"category": "Зарплата", "total": 50},
    ]}, LABELS)
    assert png and png.startswith(b"\x89PNG")


# ── Task 3.2: cash-gap label off the data line ──────────────────────────────

def test_cash_gap_label_is_not_an_inline_annotation():
    """The label must live in the legend, never on the crossing point."""
    import inspect
    src = inspect.getsource(cr.render_cashflow_forecast)
    assert "ax.annotate" not in src, "inline annotation still present"
    assert "chart_cash_gap" in src and "legend" in src


def test_cash_gap_chart_renders_with_and_without_risk():
    for balances in ([420_000, -180_000], [420_000, 380_000]):
        png = cr.render_cashflow_forecast({"cashflow_forecast": {
            "has_risk": balances[-1] < 0,
            "weekly_projection": [{"week": i + 1, "projected_balance": b}
                                  for i, b in enumerate(balances)],
        }}, LABELS)
        assert png and png.startswith(b"\x89PNG")


# ── Task 3.3: document font ─────────────────────────────────────────────────

def test_charts_use_the_document_font():
    """matplotlib must not fall back to its own default face."""
    import matplotlib.pyplot as plt

    from app.services.pdf_generator import _REGULAR_CANDIDATES, _find_font

    path = _find_font(_REGULAR_CANDIDATES)
    if not path:
        pytest.skip("no document TTF available in this environment")

    from matplotlib import font_manager
    expected = font_manager.FontProperties(fname=path).get_name()
    family = plt.rcParams["font.family"]
    assert expected in (family if isinstance(family, list) else [family])
    # DejaVu Sans is matplotlib's built-in default; assert we set it explicitly
    # rather than merely inheriting it.
    assert plt.rcParams["axes.unicode_minus"] is False
