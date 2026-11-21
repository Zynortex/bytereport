"""Tests for deterministic health score status system and WeeklyCashFlow schema."""

import pytest
from datetime import date
from app.services.financial_engine import STATUS_LABELS, score_to_status_key, compute_metrics
from app.models.transaction import Transaction, TransactionType
from app.models.report import WeeklyCashFlow


def _tx(d: str, amount: float, tx_type: str, category: str) -> Transaction:
    return Transaction(
        date=date.fromisoformat(d),
        description=category,
        amount=amount,
        type=TransactionType(tx_type),
        category=category,
    )


# ── score_to_status_key boundary tests ───────────────────────────────────────

def test_score_critical_low():
    assert score_to_status_key(0) == "critical"

def test_score_critical_given():
    assert score_to_status_key(20) == "critical"

def test_score_critical_boundary():
    assert score_to_status_key(39) == "critical"

def test_score_unstable_boundary_low():
    assert score_to_status_key(40) == "unstable"

def test_score_unstable_mid():
    assert score_to_status_key(47) == "unstable"

def test_score_unstable_boundary_high():
    assert score_to_status_key(54) == "unstable"

def test_score_stable_boundary_low():
    assert score_to_status_key(55) == "stable"

def test_score_stable_given():
    # Required by spec
    assert score_to_status_key(55) == "stable"

def test_score_stable_mid():
    assert score_to_status_key(62) == "stable"

def test_score_stable_boundary_high():
    assert score_to_status_key(69) == "stable"

def test_score_excellent_boundary():
    assert score_to_status_key(70) == "excellent"

def test_score_excellent_high():
    assert score_to_status_key(100) == "excellent"


# ── STATUS_LABELS multilingual lookup ────────────────────────────────────────

def test_uz_critical_exact():
    """Uzbek critical label must be exactly 'КРИТИК ҲОЛАТ' — not AI-generated text."""
    assert STATUS_LABELS["critical"]["uz"] == "КРИТИК ҲОЛАТ"

def test_uz_critical_not_ai_text():
    """If AI returned 'ТАНҚИДИЙ ҲОЛАТ', the deterministic dict must differ from it."""
    ai_hallucinated = "ТАНҚИДИЙ ҲОЛАТ"
    assert STATUS_LABELS["critical"]["uz"] != ai_hallucinated

def test_ru_labels():
    assert STATUS_LABELS["critical"]["ru"] == "КРИТИЧЕСКОЕ"
    assert STATUS_LABELS["unstable"]["ru"] == "НЕСТАБИЛЬНОЕ"
    assert STATUS_LABELS["stable"]["ru"] == "СТАБИЛЬНОЕ"
    assert STATUS_LABELS["excellent"]["ru"] == "ОТЛИЧНОЕ"

def test_en_labels():
    assert STATUS_LABELS["critical"]["en"] == "CRITICAL"
    assert STATUS_LABELS["unstable"]["en"] == "UNSTABLE"
    assert STATUS_LABELS["stable"]["en"] == "STABLE"
    assert STATUS_LABELS["excellent"]["en"] == "EXCELLENT"

def test_uz_labels():
    assert STATUS_LABELS["critical"]["uz"] == "КРИТИК ҲОЛАТ"
    assert STATUS_LABELS["unstable"]["uz"] == "БЕҚАРОР"
    assert STATUS_LABELS["stable"]["uz"] == "БАРҚАРОР"
    assert STATUS_LABELS["excellent"]["uz"] == "АЪЛО"


# ── Integration: score → key → label ─────────────────────────────────────────

@pytest.mark.parametrize("score,language,expected", [
    (20,  "uz", "КРИТИК ҲОЛАТ"),
    (20,  "ru", "КРИТИЧЕСКОЕ"),
    (20,  "en", "CRITICAL"),
    (55,  "uz", "БАРҚАРОР"),
    (55,  "ru", "СТАБИЛЬНОЕ"),
    (55,  "en", "STABLE"),
    (85,  "uz", "АЪЛО"),
    (85,  "en", "EXCELLENT"),
])
def test_score_to_localized_label(score: int, language: str, expected: str):
    key = score_to_status_key(score)
    label = STATUS_LABELS[key][language]
    assert label == expected


# ── scoreColor zone boundary verification (documents frontend⟷backend sync) ──
# Frontend scoreColor() thresholds must match score_to_status_key() exactly.
# critical: 0-39, unstable: 40-54, stable: 55-69, excellent: 70+

ZONE_BOUNDARY_CASES = [
    (39, "critical"),   # last score in critical zone
    (40, "unstable"),   # first score in unstable zone
    (54, "unstable"),   # last score in unstable zone
    (55, "stable"),     # first score in stable zone
    (69, "stable"),     # last score in stable zone
    (70, "excellent"),  # first score in excellent zone
    (100, "excellent"),
]

@pytest.mark.parametrize("score,expected_key", ZONE_BOUNDARY_CASES)
def test_zone_boundary(score: int, expected_key: str):
    assert score_to_status_key(score) == expected_key


# ── WeeklyCashFlow model ─────────────────────────────────────────────────────

def test_weekly_cash_flow_model():
    wc = WeeklyCashFlow(week="2024-01-W1", revenue=10000.0, expenses=6000.0, net=4000.0)
    assert wc.week == "2024-01-W1"
    assert wc.net == 4000.0


# ── Weekly breakdown includes financing transactions (raw cash position) ─────

def test_weekly_breakdown_includes_financing():
    """weekly_breakdown must include kredit (financing) income in revenue totals."""
    txns = [
        _tx("2024-01-01", 10000, "income", "sales"),
        _tx("2024-01-02", 50000, "income", "kredit"),   # financing — still real cash in
        _tx("2024-01-05", 2000,  "expense", "marketing"),
    ]
    m = compute_metrics(txns)
    # All are in the same ISO week, so only one WeeklyMetrics entry
    assert len(m.weekly_breakdown) == 1
    week = m.weekly_breakdown[0]
    assert week.revenue == 60000.0    # sales + kredit
    assert week.expenses == 2000.0
    assert week.profit == 58000.0     # net cash including financing


def test_weekly_breakdown_financing_excluded_from_operating():
    """Financing income is excluded from operating_revenue but stays in weekly_breakdown."""
    txns = [
        _tx("2024-01-01", 10000, "income", "sales"),
        _tx("2024-01-02", 50000, "income", "kredit"),
        _tx("2024-01-05", 2000,  "expense", "marketing"),
    ]
    m = compute_metrics(txns)
    # operating_revenue excludes kredit
    assert m.operating_revenue == 10000.0
    # but weekly_breakdown revenue = all transactions
    assert m.weekly_breakdown[0].revenue == 60000.0


# ── _score_color() 4-zone boundary tests (Задача 3.1) ────────────────────────
# Verify that _score_color() and score_to_status_key() agree on ALL 4 zones
# at every boundary value, and that the exact hex matches frontend scoreColor().

def _color_hex(c) -> str:
    """Convert a ReportLab Color to lowercase #rrggbb."""
    return "#{:02x}{:02x}{:02x}".format(
        round(c.red * 255), round(c.green * 255), round(c.blue * 255)
    )


# Expected: (score, status_key). The PDF prints the score on white, so its
# colour is the PRINT zone from design-tokens.json → pdf.zones (the web reads
# zones); the colour is looked up there, not mirrored here.
from app.services.design_tokens import PRINT_ZONES as _PZ

_SCORE_COLOR_CASES = [
    (0,   "critical",  _PZ["critical"].lower()),
    (39,  "critical",  _PZ["critical"].lower()),
    (40,  "unstable",  _PZ["unstable"].lower()),
    (54,  "unstable",  _PZ["unstable"].lower()),
    (55,  "stable",    _PZ["stable"].lower()),
    (69,  "stable",    _PZ["stable"].lower()),
    (70,  "excellent", _PZ["excellent"].lower()),
    (100, "excellent", _PZ["excellent"].lower()),
]

@pytest.mark.parametrize("score,expected_key,expected_hex", _SCORE_COLOR_CASES)
def test_score_color_key_and_hex(score: int, expected_key: str, expected_hex: str):
    """_score_color() and score_to_status_key() agree; color matches frontend."""
    from app.services.pdf_generator import _score_color
    assert score_to_status_key(score) == expected_key
    assert _color_hex(_score_color(score)) == expected_hex


def test_score_color_73_regression():
    """Regression: score=73 must be excellent/green, not old SCORE_STABLE amber."""
    from app.services.pdf_generator import _score_color
    # Before fix: _score_color(73) returned the amber SCORE_STABLE of the 5-zone system
    # After fix:  must return the excellent zone colour
    assert score_to_status_key(73) == "excellent"
    assert _color_hex(_score_color(73)) == _PZ["excellent"].lower()


def test_old_5zone_amber_no_longer_used():
    """score=68 (was SCORE_STABLE amber in old 5-zone) must now be stable/lime."""
    from app.services.pdf_generator import _score_color
    assert score_to_status_key(68) == "stable"
    assert _color_hex(_score_color(68)) == _PZ["stable"].lower()


# ── nova_digital fixture regression tests (Задача 3.2) ───────────────────────
# Programmatic fixture with the key data properties described in the task:
#   - kredit (150M) → financing, excluded from operating_revenue
#   - Beta Group duplicate (2026-03-10, 20M x2) → detected by preprocessing
#   - Future transaction (2026-09-15) → excluded by preprocessing
# No CSV file needed — health_score is computed entirely in Python.

def _nova_txns() -> list:
    """Return the nova_digital representative transaction set."""
    from app.models.transaction import Transaction, TransactionType
    def t(d, amount, tx_type, category):
        return Transaction(
            date=date.fromisoformat(d),
            description=category,
            amount=float(amount),
            type=TransactionType(tx_type),
            category=category,
        )
    return [
        # Operating income
        t("2026-01-05", 50_000_000, "income", "sales"),
        t("2026-02-07", 60_000_000, "income", "consulting"),
        t("2026-03-10", 55_000_000, "income", "sales"),
        # Financing — must NOT be in operating_revenue
        t("2026-02-15", 150_000_000, "income", "kredit"),
        # Regular expenses
        t("2026-01-10", 20_000_000, "expense", "payroll"),
        t("2026-02-10", 22_000_000, "expense", "payroll"),
        t("2026-03-08", 25_000_000, "expense", "payroll"),
        t("2026-01-20", 10_000_000, "expense", "marketing"),
        t("2026-02-20", 11_000_000, "expense", "marketing"),
        t("2026-03-20", 12_000_000, "expense", "marketing"),
        # Beta Group DUPLICATE: same (date, category, amount, description) × 2
        t("2026-03-10", 20_000_000, "expense", "beta_group"),
        t("2026-03-10", 20_000_000, "expense", "beta_group"),
        # Future transaction relative to NOVA_TODAY
        t("2026-09-15", 5_000_000, "income", "sales"),
    ]


# The day the Nova fixture describes as "today". Passed explicitly so the
# future-dated row stays in the future whatever the real date is.
NOVA_TODAY = date(2026, 7, 26)


def test_nova_kredit_excluded_from_operating():
    """kredit (150M) must not be counted in operating_revenue."""
    from app.services.preprocessing import preprocess_transactions
    clean, _ = preprocess_transactions(_nova_txns(), today=NOVA_TODAY)
    m = compute_metrics(clean)
    assert m.operating_revenue == pytest.approx(165_000_000.0)  # 50M+60M+55M
    assert m.financing_income == pytest.approx(150_000_000.0)


def test_nova_duplicate_detected():
    """Beta Group (2026-03-10, 20M x2) must be flagged as a possible duplicate."""
    from app.services.preprocessing import preprocess_transactions
    _, meta = preprocess_transactions(_nova_txns(), today=NOVA_TODAY)
    dupes = meta["possible_duplicates"]
    assert len(dupes) == 1
    assert dupes[0]["category"] == "beta_group"
    assert dupes[0]["count"] == 2
    assert dupes[0]["amount"] == pytest.approx(20_000_000.0)


def test_nova_future_transaction_excluded():
    """Transaction dated 2026-09-15 must be removed from clean list and recorded in meta."""
    from app.services.preprocessing import preprocess_transactions
    clean, meta = preprocess_transactions(_nova_txns(), today=NOVA_TODAY)
    future_cats = [f["category"] for f in meta["future_transactions"]]
    assert "sales" in future_cats  # the 2026-09-15 sales entry
    # All remaining transactions must be on or before the fixture's today
    for t in clean:
        assert t.date <= NOVA_TODAY


def test_nova_score_color_backend_pdf_agree():
    """For nova_digital score: score_to_status_key() and _score_color() must be in same zone."""
    from app.services.preprocessing import preprocess_transactions
    from app.services.pdf_generator import _score_color
    clean, _ = preprocess_transactions(_nova_txns(), today=NOVA_TODAY)
    m = compute_metrics(clean)
    score = m.health_score
    key = score_to_status_key(score)
    _ZONE_HEX = {k: v.lower() for k, v in _PZ.items()}
    assert _color_hex(_score_color(score)) == _ZONE_HEX[key], (
        f"score={score} key={key!r}: PDF color {_color_hex(_score_color(score))!r}"
        f" != expected {_ZONE_HEX[key]!r}"
    )
