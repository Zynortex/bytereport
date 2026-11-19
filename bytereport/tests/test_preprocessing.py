"""
Tests for preprocessing and financing separation.
"""

from datetime import date, timedelta

import pytest

from app.models.transaction import Transaction, TransactionType
from app.services.financial_engine import compute_metrics
from app.services.preprocessing import preprocess_transactions

TODAY = date.today()


def make_tx(
    d: date,
    category: str,
    amount: float,
    tx_type: TransactionType = TransactionType.income,
    description: str = "test",
) -> Transaction:
    return Transaction(
        date=d,
        category=category,
        raw_category=category,
        amount=amount,
        type=tx_type,
        description=description,
    )


# ---------------------------------------------------------------------------
# 1. Future transactions excluded
# ---------------------------------------------------------------------------

def test_future_transactions_excluded():
    future_date = TODAY + timedelta(days=30)
    txns = [
        make_tx(TODAY, "sales", 100_000),
        make_tx(future_date, "prepayment", 25_000_000),
    ]
    clean, meta = preprocess_transactions(txns)

    assert len(clean) == 1
    assert clean[0].category == "sales"

    assert len(meta["future_transactions"]) == 1
    ft = meta["future_transactions"][0]
    assert ft["date"] == future_date.isoformat()
    assert ft["amount"] == 25_000_000.0
    assert ft["category"] == "prepayment"


def test_no_future_transactions():
    txns = [make_tx(TODAY, "sales", 1_000), make_tx(TODAY - timedelta(days=1), "consulting", 500)]
    clean, meta = preprocess_transactions(txns)
    assert len(clean) == 2
    assert meta["future_transactions"] == []


# ---------------------------------------------------------------------------
# 2. Duplicates preserved in list, detected in metadata
# ---------------------------------------------------------------------------

def test_duplicates_preserved_and_detected():
    d = date(2026, 3, 10)
    tx1 = make_tx(d, "subscription", 20_000_000, description="Оплата Beta Group март")
    tx2 = make_tx(d, "subscription", 20_000_000, description="Оплата Beta Group март")
    clean, meta = preprocess_transactions([tx1, tx2])

    assert len(clean) == 2  # both rows kept
    assert len(meta["possible_duplicates"]) == 1
    dup = meta["possible_duplicates"][0]
    assert dup["count"] == 2
    assert dup["amount"] == 20_000_000.0
    assert dup["category"] == "subscription"


def test_no_false_positive_duplicates():
    d = date(2026, 3, 10)
    # Same date/category/amount but different description — not a duplicate
    tx1 = make_tx(d, "sales", 10_000, description="Client A")
    tx2 = make_tx(d, "sales", 10_000, description="Client B")
    _, meta = preprocess_transactions([tx1, tx2])
    assert meta["possible_duplicates"] == []


# ---------------------------------------------------------------------------
# 3. Financing separation: kredit 150M + 3 × kredit qaytarish 8.5M
# ---------------------------------------------------------------------------

def test_financing_separation():
    txns = [
        make_tx(date(2026, 2, 1), "kredit", 150_000_000, TransactionType.income),
        make_tx(date(2026, 3, 1), "sales", 50_000_000, TransactionType.income),
        make_tx(date(2026, 2, 5),  "kredit qaytarish", 8_500_000, TransactionType.expense),
        make_tx(date(2026, 3, 5),  "kredit qaytarish", 8_500_000, TransactionType.expense),
        make_tx(date(2026, 4, 5),  "kredit qaytarish", 8_500_000, TransactionType.expense),
        make_tx(date(2026, 2, 10), "rent", 10_000_000, TransactionType.expense),
    ]
    m = compute_metrics(txns)

    assert m.financing_income == 150_000_000.0
    assert m.financing_expenses == 25_500_000.0
    assert m.operating_revenue == 50_000_000.0
    assert m.total_revenue == 200_000_000.0           # kredit included in total cash
    assert "kredit" in m.financing_income_categories


# ---------------------------------------------------------------------------
# 4. UZ tax limit calculated from operating_revenue, not total
# ---------------------------------------------------------------------------

def test_tax_limit_uses_operating_revenue():
    # 12 months, total operating revenue = 500M → projected annual = 500M → 50%
    # Plus kredit 400M → without fix, projected would be ~900M → ~90%
    monthly_op = 500_000_000 / 12
    txns = [
        make_tx(date(2025, m, 1), "sales", monthly_op, TransactionType.income)
        for m in range(1, 13)
    ] + [
        make_tx(date(2025, 7, 15), "kredit", 400_000_000, TransactionType.income)
    ]
    m = compute_metrics(txns)

    # Operating projected annual ≈ 500M → 50% of 1B limit
    assert m.operating_revenue == pytest.approx(500_000_000.0, rel=1e-6)
    assert m.tax_limit_usage_percent == pytest.approx(50.0, abs=1.0)
    # Ensure we're not near the 90% that total_revenue would give
    assert m.tax_limit_usage_percent < 60.0


# ---------------------------------------------------------------------------
# 5. Case-insensitive financing detection
# ---------------------------------------------------------------------------

def test_financing_categories_case_insensitive():
    txns = [
        make_tx(date(2026, 1, 1), "Kredit",   10_000_000, TransactionType.income),
        make_tx(date(2026, 2, 1), " KREDIT ", 20_000_000, TransactionType.income),
        make_tx(date(2026, 3, 1), "кредит",   30_000_000, TransactionType.income),
    ]
    m = compute_metrics(txns)

    assert m.financing_income == 60_000_000.0
    assert m.operating_revenue == 0.0
    assert len(m.financing_income_categories) == 3


# ---------------------------------------------------------------------------
# 6. Clean CSV without financing → operating == total
# ---------------------------------------------------------------------------

def test_clean_csv_no_financing():
    txns = [
        make_tx(date(2026, 1, 1),  "sales",      100_000, TransactionType.income),
        make_tx(date(2026, 1, 15), "consulting",  50_000, TransactionType.income),
        make_tx(date(2026, 1, 20), "rent",         30_000, TransactionType.expense),
    ]
    m = compute_metrics(txns)

    assert m.financing_income == 0.0
    assert m.financing_expenses == 0.0
    assert m.operating_revenue == m.total_revenue
    assert m.financing_income_categories == []
