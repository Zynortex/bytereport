import pytest
from datetime import date
from app.models.transaction import Transaction, TransactionType
from app.services.financial_engine import compute_metrics


def make_tx(d: str, amount: float, tx_type: str, category: str) -> Transaction:
    return Transaction(
        date=date.fromisoformat(d),
        description=category,
        amount=amount,
        type=TransactionType(tx_type),
        category=category,
    )


TRANSACTIONS = [
    # January
    make_tx("2024-01-05", 10000, "income",  "sales"),
    make_tx("2024-01-10", 2000,  "expense", "marketing"),
    make_tx("2024-01-15", 1000,  "expense", "software"),
    make_tx("2024-01-20", 3000,  "income",  "services"),
    # February
    make_tx("2024-02-05", 12000, "income",  "sales"),
    make_tx("2024-02-10", 4000,  "expense", "marketing"),   # +100% spike
    make_tx("2024-02-15", 1000,  "expense", "software"),
    make_tx("2024-02-20", 2000,  "income",  "services"),
    # March — marketing drops
    make_tx("2024-03-05", 11000, "income",  "sales"),
    make_tx("2024-03-10", 1000,  "expense", "marketing"),   # -75% drop
    make_tx("2024-03-15", 1500,  "expense", "rent"),        # new category
]


def test_totals():
    m = compute_metrics(TRANSACTIONS)
    assert m.total_revenue == 38000.0
    assert m.total_expenses == 10500.0   # 2000+1000+4000+1000+1000+1500
    assert m.profit == 27500.0


def test_profit_margin():
    m = compute_metrics(TRANSACTIONS)
    expected = round(27500 / 38000 * 100, 2)
    assert m.profit_margin == expected


def test_period():
    m = compute_metrics(TRANSACTIONS)
    assert m.period_start == "2024-01-05"
    assert m.period_end == "2024-03-15"


def test_monthly_breakdown_count():
    m = compute_metrics(TRANSACTIONS)
    assert len(m.monthly_breakdown) == 3


def test_monthly_january():
    m = compute_metrics(TRANSACTIONS)
    jan = next(mo for mo in m.monthly_breakdown if mo.month == "2024-01")
    assert jan.revenue == 13000.0
    assert jan.expenses == 3000.0
    assert jan.profit == 10000.0


def test_mom_growth():
    m = compute_metrics(TRANSACTIONS)
    feb_growth = next(g for g in m.mom_growth if g.month == "2024-02")
    # Revenue: 14000 vs 13000 → ~7.69%
    assert feb_growth.revenue_growth_pct is not None
    assert feb_growth.revenue_growth_pct > 0


def test_category_breakdown_sorted_by_amount():
    m = compute_metrics(TRANSACTIONS)
    amounts = [c.total for c in m.expense_by_category]
    assert amounts == sorted(amounts, reverse=True)


def test_anomaly_marketing_spike_february():
    m = compute_metrics(TRANSACTIONS)
    spikes = [a for a in m.anomalies if a.type == "spike" and a.category == "marketing"]
    assert len(spikes) == 1
    assert spikes[0].month == "2024-02"
    assert spikes[0].severity in ("high", "medium")


def test_anomaly_marketing_drop_march():
    m = compute_metrics(TRANSACTIONS)
    drops = [a for a in m.anomalies if a.type == "drop" and a.category == "marketing"]
    assert len(drops) == 1
    assert drops[0].month == "2024-03"


def test_anomaly_new_category_rent():
    m = compute_metrics(TRANSACTIONS)
    new_cats = [a for a in m.anomalies if a.type == "new_category" and a.category == "rent"]
    assert len(new_cats) == 1


def test_empty_transactions_raises():
    with pytest.raises(ValueError):
        compute_metrics([])


def test_percentages_sum_to_100():
    m = compute_metrics(TRANSACTIONS)
    total_pct = sum(c.percentage for c in m.expense_by_category)
    assert abs(total_pct - 100.0) < 0.1
