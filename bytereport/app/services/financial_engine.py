"""
Financial Engine for ByteReport.

Computes from a list of Transaction objects:
  - total revenue / expenses / profit / margin
  - per-category breakdowns (revenue and expense)
  - monthly breakdown
  - month-over-month growth rates
  - anomaly flags (spikes, drops, new/missing categories)
"""

import logging
from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

from app.models.transaction import Transaction, TransactionType

from app.services.growth_display import collect_outliers, display_value
from app.models.metrics import (
    AnomalyFlag,
    CashflowForecast,
    CategoryBreakdown,
    FinancialMetrics,
    MoMGrowth,
    MoMOutlier,
    MonthMetrics,
    TopTransaction,
    WeeklyMetrics,
)

logger = logging.getLogger(__name__)

# Anomaly detection thresholds
SPIKE_THRESHOLD_PCT = 50.0   # >50% increase vs prior month → spike
DROP_THRESHOLD_PCT = 40.0    # >40% decrease vs prior month → drop
HIGH_SEVERITY_PCT = 100.0    # >100% change → high severity
MEDIUM_SEVERITY_PCT = 50.0   # 50-100% change → medium

STATUS_LABELS: dict[str, dict[str, str]] = {
    "critical":  {"ru": "КРИТИЧЕСКОЕ",  "uz": "КРИТИК ҲОЛАТ", "en": "CRITICAL"},
    "unstable":  {"ru": "НЕСТАБИЛЬНОЕ", "uz": "БЕҚАРОР",       "en": "UNSTABLE"},
    "stable":    {"ru": "СТАБИЛЬНОЕ",   "uz": "БАРҚАРОР",      "en": "STABLE"},
    "excellent": {"ru": "ОТЛИЧНОЕ",     "uz": "АЪЛО",          "en": "EXCELLENT"},
}


def score_to_status_key(score: int) -> str:
    if score >= 70:
        return "excellent"
    if score >= 55:
        return "stable"
    if score >= 40:
        return "unstable"
    return "critical"


# Financing categories — these are loans/credits, NOT operating revenue.
# Comparison is always done after .strip().lower() on the raw category.
FINANCING_INCOME_CATEGORIES: frozenset[str] = frozenset({
    "kredit", "кредит", "credit", "loan", "заём", "займ", "qarz", "кредит банка",
})
FINANCING_EXPENSE_KEYWORDS: frozenset[str] = frozenset({
    "kredit qaytarish", "погашение кредита", "loan repayment",
    "выплата кредита", "кредит қайтариш",
})


def _raw(t: Transaction) -> str:
    """Return the original category label, stripped of whitespace."""
    return (t.raw_category or t.category).strip()


def _month_key(d: date) -> str:
    return d.strftime("%Y-%m")


def _week_of_month(d: date) -> int:
    """Returns 1-5: which week of the month a date falls in (days 1-7 → W1, etc.)."""
    return (d.day - 1) // 7 + 1


def _week_key(d: date) -> str:
    """Returns e.g. '2024-01-W2' — stable sort key for weekly breakdown."""
    return f"{_month_key(d)}-W{_week_of_month(d)}"


def _pct_change(current: float, previous: float) -> Optional[float]:
    if previous == 0:
        return None
    return round((current - previous) / previous * 100, 2)


def _severity(change_pct: float) -> str:
    abs_pct = abs(change_pct)
    if abs_pct >= HIGH_SEVERITY_PCT:
        return "high"
    if abs_pct >= MEDIUM_SEVERITY_PCT:
        return "medium"
    return "low"


def _cat_key(value: str) -> str:
    """
    Grouping key for a category name.

    "Marketing", "marketing" and "MARKETING " are one category. Keying the
    totals on the literal string made them three: three wedges in the donut,
    three rows in the breakdown, three separate series for anomaly detection,
    and three entries in the category list handed to the model. Case and
    surrounding whitespace carry no meaning here, so neither may split a total.
    """
    return " ".join(value.split()).lower()


def _build_category_breakdown(
    totals: dict[str, float],
    counts: dict[str, int],
    grand_total: float,
    display: dict[str, str] | None = None,
) -> list[CategoryBreakdown]:
    """`display` maps the grouping key back to the spelling first seen."""
    result = []
    for cat, amount in sorted(totals.items(), key=lambda x: -x[1]):
        pct = round(amount / grand_total * 100, 2) if grand_total else 0.0
        result.append(
            CategoryBreakdown(
                category=(display or {}).get(cat, cat),
                total=round(amount, 2),
                percentage=pct,
                transaction_count=counts[cat],
            )
        )
    return result


def _detect_anomalies(
    monthly_by_category: dict[str, dict[str, float]],  # {month: {category: amount}}
    tx_type: str,
) -> list[AnomalyFlag]:
    """
    Compare each category's monthly value to the previous month.
    Detect spikes, drops, new appearances, and disappearances.
    """
    anomalies: list[AnomalyFlag] = []
    sorted_months = sorted(monthly_by_category.keys())

    if len(sorted_months) < 2:
        return anomalies

    # Collect all categories ever seen
    all_categories: set[str] = set()
    for month_data in monthly_by_category.values():
        all_categories.update(month_data.keys())

    for i in range(1, len(sorted_months)):
        prev_month = sorted_months[i - 1]
        curr_month = sorted_months[i]
        prev_data = monthly_by_category[prev_month]
        curr_data = monthly_by_category[curr_month]

        for cat in all_categories:
            prev_val = prev_data.get(cat, 0.0)
            curr_val = curr_data.get(cat, 0.0)

            # New category appeared (first time in data)
            if prev_val == 0 and curr_val > 0:
                # Only flag if it appeared after the very first month
                first_month_with_any = sorted_months[0]
                if curr_month != first_month_with_any:
                    anomalies.append(
                        AnomalyFlag(
                            category=cat,
                            month=curr_month,
                            type="new_category",
                            severity="low",
                            value=round(curr_val, 2),
                            previous_value=None,
                            change_pct=None,
                            description=(
                                f"Category '{cat}' ({tx_type}) appeared for the first time "
                                f"in {curr_month} with {curr_val:,.2f}."
                            ),
                        )
                    )
                continue

            # Category disappeared
            if prev_val > 0 and curr_val == 0:
                anomalies.append(
                    AnomalyFlag(
                        category=cat,
                        month=curr_month,
                        type="missing_category",
                        severity="low",
                        value=0.0,
                        previous_value=round(prev_val, 2),
                        change_pct=-100.0,
                        description=(
                            f"Category '{cat}' ({tx_type}) had no transactions in {curr_month} "
                            f"after {prev_val:,.2f} in {prev_month}."
                        ),
                    )
                )
                continue

            if prev_val == 0:
                continue

            change_pct = _pct_change(curr_val, prev_val)
            if change_pct is None:
                continue

            if change_pct >= SPIKE_THRESHOLD_PCT:
                anomalies.append(
                    AnomalyFlag(
                        category=cat,
                        month=curr_month,
                        type="spike",
                        severity=_severity(change_pct),
                        value=round(curr_val, 2),
                        previous_value=round(prev_val, 2),
                        change_pct=change_pct,
                        description=(
                            f"{tx_type.capitalize()} category '{cat}' spiked +{change_pct:.1f}% "
                            f"in {curr_month} ({prev_val:,.2f} → {curr_val:,.2f})."
                        ),
                    )
                )
            elif change_pct <= -DROP_THRESHOLD_PCT:
                anomalies.append(
                    AnomalyFlag(
                        category=cat,
                        month=curr_month,
                        type="drop",
                        severity=_severity(change_pct),
                        value=round(curr_val, 2),
                        previous_value=round(prev_val, 2),
                        change_pct=change_pct,
                        description=(
                            f"{tx_type.capitalize()} category '{cat}' dropped {change_pct:.1f}% "
                            f"in {curr_month} ({prev_val:,.2f} → {curr_val:,.2f})."
                        ),
                    )
                )

    return anomalies


def _linear_trend(values: list[float]) -> float:
    """OLS slope — returns per-period change in `values`."""
    n = len(values)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2.0
    y_mean = sum(values) / n
    num = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    den = sum((i - x_mean) ** 2 for i in range(n))
    return num / den if den else 0.0


def calculate_cashflow_forecast(
    weekly_breakdown: list[WeeklyMetrics],
    closing_balance: Optional[float],
    period_end_str: str,
) -> CashflowForecast:
    """
    Projects the next 4 weeks from the recent weekly trend.

    With `closing_balance` (the account balance at the end of the statement,
    entered by the user) it projects the BALANCE and flags the first week it
    goes negative. Without it, it projects only the weekly NET flow: there is
    no starting point, so no date or amount of a shortfall can be derived.
    This used to start from the period's profit, which made up a balance the
    data does not contain.
    """
    balance_known = closing_balance is not None
    n = len(weekly_breakdown)
    if n == 0:
        return CashflowForecast(
            balance_known=balance_known,
            closing_balance=closing_balance,
            has_risk=False,
            risk_date=None,
            risk_amount=None,
            weekly_projection=[],
            confidence="LOW",
        )

    # Use the most recent 4 weeks (or all if fewer)
    recent = weekly_breakdown[-min(n, 4):]
    revenues = [w.revenue for w in recent]
    expenses = [w.expenses for w in recent]

    avg_rev = sum(revenues) / len(revenues)
    avg_exp = sum(expenses) / len(expenses)
    rev_trend = _linear_trend(revenues)
    exp_trend = _linear_trend(expenses)

    period_end = date.fromisoformat(period_end_str)
    balance = closing_balance if balance_known else 0.0
    has_risk = False
    risk_date: Optional[str] = None
    risk_amount: Optional[float] = None
    weekly_projection: list[dict] = []

    for i in range(1, 5):
        proj_rev = round(max(0.0, avg_rev + rev_trend * i), 2)
        proj_exp = round(max(0.0, avg_exp + exp_trend * i), 2)
        net = round(proj_rev - proj_exp, 2)
        balance = round(balance + net, 2)
        proj_date = (period_end + timedelta(weeks=i)).isoformat()

        weekly_projection.append({
            "week": i,
            "projected_date": proj_date,
            "projected_revenue": proj_rev,
            "projected_expenses": proj_exp,
            "projected_net": net,
            "projected_balance": balance if balance_known else None,
        })

        if balance_known and balance < 0 and not has_risk:
            has_risk = True
            risk_date = proj_date
            risk_amount = round(abs(balance), 2)

    if n >= 6:
        confidence = "HIGH"
    elif n >= 4:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    result = CashflowForecast(
        balance_known=balance_known,
        closing_balance=closing_balance,
        has_risk=has_risk,
        risk_date=risk_date,
        risk_amount=risk_amount,
        weekly_projection=weekly_projection,
        confidence=confidence,
    )
    logger.info("cashflow_forecast result: balance_known=%s has_risk=%s confidence=%s weeks=%d",
                result.balance_known, result.has_risk, result.confidence,
                len(result.weekly_projection))
    return result


def health_score_breakdown(
    operating_revenue: float,
    operating_expenses: float,
    operating_monthly_revenues: list[float],
    monthly_data: list,
    negative_weeks: dict,
    tax_limit_warning: bool,
    projected_annual_revenue: float = 0.0,
) -> list[dict]:
    """
    The five checks behind the Health Score, each with the points it moved.

    Every entry is {"key", "variant", "points", "values"}: `variant` picks the
    sentence in report-copy.json (score_breakdown), `values` fills it. The
    score is computed FROM this list (calculate_health_score), so what the
    user reads as the explanation is, by construction, the arithmetic that
    produced the number. The AI never writes or sees any of it.
    """
    items: list[dict] = []

    # 1. Profit margin on operating figures (max -30)
    op_profit = operating_revenue - operating_expenses
    margin = (op_profit / operating_revenue * 100) if operating_revenue > 0 else 0
    if margin < 0:
        items.append({"key": "margin", "variant": "negative", "points": -30, "values": {"margin": round(margin, 1)}})
    else:
        for threshold, points in ((10, -25), (20, -15), (30, -5)):
            if margin < threshold:
                items.append({"key": "margin", "variant": "below", "points": points,
                              "values": {"margin": round(margin, 1), "threshold": threshold}})
                break
        else:
            items.append({"key": "margin", "variant": "ok", "points": 0, "values": {"margin": round(margin, 1)}})

    # 2. Cash-flow gaps (max -25) — weeks whose net flow was negative
    num_gaps = len(negative_weeks)
    points = -25 if num_gaps >= 4 else -15 if num_gaps >= 2 else -8 if num_gaps == 1 else 0
    items.append({"key": "cash_gaps", "variant": "some" if num_gaps else "none", "points": points,
                  "values": {"weeks": num_gaps}})

    # 3. Operating revenue trend (max -20, +3 bonus for growth)
    if len(operating_monthly_revenues) >= 2:
        last = operating_monthly_revenues[-1]
        prev = operating_monthly_revenues[-2]
        trend = ((last - prev) / prev * 100) if prev > 0 else 0
        if trend < -30:
            points = -20
        elif trend < -15:
            points = -12
        elif trend < -5:
            points = -5
        elif trend > 10:
            points = 3
        else:
            points = 0
        variant = "down" if points < 0 else "up" if points > 0 else "flat"
        items.append({"key": "revenue_trend", "variant": variant, "points": points,
                      "values": {"change": round(trend, 1)}})
    else:
        items.append({"key": "revenue_trend", "variant": "na", "points": 0, "values": {}})

    # 4. UZ tax limit risk (max -15)
    items.append({"key": "tax_limit", "variant": "over" if tax_limit_warning else "ok",
                  "points": -15 if tax_limit_warning else 0,
                  "values": {"amount": round(projected_annual_revenue)}})

    # 5. Expense volatility (max -10) — total expenses per month
    if len(monthly_data) >= 2:
        expenses_list = [abs(m.expenses) for m in monthly_data]
        avg_exp = sum(expenses_list) / len(expenses_list)
        max_exp = max(expenses_list)
        volatility = ((max_exp - avg_exp) / avg_exp * 100) if avg_exp > 0 else 0
        points = -10 if volatility > 50 else -5 if volatility > 25 else 0
        items.append({"key": "volatility", "variant": "high" if points else "ok", "points": points,
                      "values": {"pct": round(volatility, 1)}})
    else:
        items.append({"key": "volatility", "variant": "na", "points": 0, "values": {}})

    return items


def score_from_breakdown(items: list[dict]) -> tuple[int, bool]:
    """100 plus every item's points, held to 0-100. Second value: was it held."""
    raw = 100 + sum(i["points"] for i in items)
    score = max(0, min(100, raw))
    return score, score != raw


def calculate_health_score(
    operating_revenue: float,
    operating_expenses: float,
    operating_monthly_revenues: list[float],
    monthly_data: list,
    negative_weeks: dict,
    tax_limit_warning: bool,
) -> tuple[int, str]:
    items = health_score_breakdown(
        operating_revenue, operating_expenses, operating_monthly_revenues,
        monthly_data, negative_weeks, tax_limit_warning,
    )
    score, _ = score_from_breakdown(items)
    return score, score_to_status_key(score)


def compute_metrics(
    transactions: list[Transaction],
    closing_balance: Optional[float] = None,
) -> FinancialMetrics:
    """
    Main entry point. Accepts a validated list of Transaction objects
    and returns a fully populated FinancialMetrics instance.
    """
    if not transactions:
        raise ValueError("No transactions provided")

    # -----------------------------------------------------------------------
    # 1. Aggregate totals
    # -----------------------------------------------------------------------
    total_revenue = 0.0
    total_expenses = 0.0
    _financing_income = 0.0
    _financing_expenses = 0.0
    _financing_income_cats: set[str] = set()

    rev_by_cat: dict[str, float] = defaultdict(float)
    exp_by_cat: dict[str, float] = defaultdict(float)
    # Grouping key -> the first spelling seen, so output keeps the user's
    # capitalisation while the totals stay merged.
    cat_display: dict[str, str] = {}
    raw_display: dict[str, str] = {}
    rev_cat_count: dict[str, int] = defaultdict(int)
    exp_cat_count: dict[str, int] = defaultdict(int)

    # For monthly breakdown (total, incl. financing — used for charts)
    monthly_revenue: dict[str, float] = defaultdict(float)
    monthly_expenses: dict[str, float] = defaultdict(float)
    # Operating-only monthly revenue (excludes financing income)
    operating_monthly_revenue: dict[str, float] = defaultdict(float)

    # For weekly breakdown: {week_key: amount}
    weekly_revenue: dict[str, float] = defaultdict(float)
    weekly_expenses: dict[str, float] = defaultdict(float)
    # Metadata per week_key: (month, week_number) — stable, set once
    weekly_meta: dict[str, tuple[str, int]] = {}

    # For anomaly detection: {month: {category: amount}}
    monthly_rev_by_cat: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    monthly_exp_by_cat: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    dates: list[date] = []

    income_count = 0
    expense_count = 0

    for tx in transactions:
        month = _month_key(tx.date)
        wk    = _week_key(tx.date)
        dates.append(tx.date)

        ckey = _cat_key(tx.category)
        cat_display.setdefault(ckey, " ".join(tx.category.split()))
        rkey = _cat_key(_raw(tx))
        raw_display.setdefault(rkey, " ".join(_raw(tx).split()))

        raw_lower = _raw(tx).lower()
        is_fin_income   = tx.type == TransactionType.income  and raw_lower in FINANCING_INCOME_CATEGORIES
        is_fin_expense  = tx.type == TransactionType.expense and raw_lower in FINANCING_EXPENSE_KEYWORDS

        weekly_meta.setdefault(wk, (month, _week_of_month(tx.date)))

        if tx.type == TransactionType.income:
            total_revenue += tx.amount
            rev_by_cat[ckey] += tx.amount
            rev_cat_count[ckey] += 1
            monthly_revenue[month] += tx.amount
            monthly_rev_by_cat[month][ckey] += tx.amount
            weekly_revenue[wk] += tx.amount
            income_count += 1
            if is_fin_income:
                _financing_income += tx.amount
                _financing_income_cats.add(_raw(tx))
            else:
                operating_monthly_revenue[month] += tx.amount
        else:
            total_expenses += tx.amount
            exp_by_cat[ckey] += tx.amount
            exp_cat_count[ckey] += 1
            monthly_expenses[month] += tx.amount
            monthly_exp_by_cat[month][ckey] += tx.amount
            weekly_expenses[wk] += tx.amount
            expense_count += 1
            if is_fin_expense:
                _financing_expenses += tx.amount

    total_revenue = round(total_revenue, 2)
    total_expenses = round(total_expenses, 2)
    financing_income   = round(_financing_income, 2)
    financing_expenses = round(_financing_expenses, 2)
    operating_revenue  = round(total_revenue - financing_income, 2)
    operating_expenses = round(total_expenses - financing_expenses, 2)

    profit = round(total_revenue - total_expenses, 2)  # total cash (incl. financing)
    operating_profit = round(operating_revenue - operating_expenses, 2)
    profit_margin = round(operating_profit / operating_revenue * 100, 2) if operating_revenue else 0.0

    period_start = min(dates).isoformat()
    period_end = max(dates).isoformat()
    total_days = (max(dates) - min(dates)).days + 1

    # -----------------------------------------------------------------------
    # 2. Category breakdowns
    # -----------------------------------------------------------------------
    revenue_breakdown = _build_category_breakdown(
        rev_by_cat, rev_cat_count, total_revenue, cat_display)
    expense_breakdown = _build_category_breakdown(
        exp_by_cat, exp_cat_count, total_expenses, cat_display)

    # -----------------------------------------------------------------------
    # 3. Weekly breakdown
    # -----------------------------------------------------------------------
    weekly_breakdown: list[WeeklyMetrics] = []
    for wk in sorted(weekly_meta.keys()):
        month_k, wnum = weekly_meta[wk]
        rev = round(weekly_revenue.get(wk, 0.0), 2)
        exp = round(weekly_expenses.get(wk, 0.0), 2)
        weekly_breakdown.append(WeeklyMetrics(
            week_key=wk,
            month=month_k,
            week_number=wnum,
            revenue=rev,
            expenses=exp,
            profit=round(rev - exp, 2),
        ))

    # -----------------------------------------------------------------------
    # 4. Monthly breakdown
    # -----------------------------------------------------------------------
    all_months = sorted(set(list(monthly_revenue.keys()) + list(monthly_expenses.keys())))
    monthly_breakdown: list[MonthMetrics] = []

    for month in all_months:
        rev = round(monthly_revenue.get(month, 0.0), 2)
        exp = round(monthly_expenses.get(month, 0.0), 2)
        pft = round(rev - exp, 2)
        margin = round(pft / rev * 100, 2) if rev else 0.0
        monthly_breakdown.append(
            MonthMetrics(
                month=month,
                revenue=rev,
                expenses=exp,
                profit=pft,
                profit_margin=margin,
            )
        )

    # -----------------------------------------------------------------------
    # 5. Month-over-month growth
    # -----------------------------------------------------------------------
    mom_growth: list[MoMGrowth] = []
    mom_outliers: list[MoMOutlier] = []
    for i in range(1, len(monthly_breakdown)):
        prev = monthly_breakdown[i - 1]
        curr = monthly_breakdown[i]

        pcts = {
            "revenue":  _pct_change(curr.revenue, prev.revenue),
            "expenses": _pct_change(curr.expenses, prev.expenses),
            "profit":   _pct_change(curr.profit, prev.profit),
        }

        # Raw percentages are kept as-is; the *_display copies are what charts
        # plot. A near-zero base yields a mathematically valid but unreadable
        # number (profit 1 000 -> 220 000 is +21 900%), which would stretch the
        # axis and flatten every real trend. growth_display decides, once.
        mom_growth.append(
            MoMGrowth(
                month=curr.month,
                revenue_growth_pct=pcts["revenue"],
                expense_growth_pct=pcts["expenses"],
                profit_growth_pct=pcts["profit"],
                revenue_growth_display=display_value(pcts["revenue"]),
                expense_growth_display=display_value(pcts["expenses"]),
                profit_growth_display=display_value(pcts["profit"]),
            )
        )
        mom_outliers += [
            MoMOutlier(**o.as_dict())
            for o in collect_outliers(
                curr.month, pcts,
                {"revenue": prev.revenue, "expenses": prev.expenses, "profit": prev.profit},
                {"revenue": curr.revenue, "expenses": curr.expenses, "profit": curr.profit},
            )
        ]

    # -----------------------------------------------------------------------
    # 6. Anomaly detection
    # -----------------------------------------------------------------------
    # Convert defaultdict to plain dict for the detector
    plain_rev = {m: dict(cats) for m, cats in monthly_rev_by_cat.items()}
    plain_exp = {m: dict(cats) for m, cats in monthly_exp_by_cat.items()}

    anomalies = (
        _detect_anomalies(plain_rev, "income")
        + _detect_anomalies(plain_exp, "expense")
    )
    # The detector works on grouping keys; report the spelling the user wrote.
    for a in anomalies:
        a.category = cat_display.get(a.category, a.category)
    # Sort by month then severity
    severity_order = {"high": 0, "medium": 1, "low": 2}
    anomalies.sort(key=lambda a: (a.month, severity_order.get(a.severity, 3)))

    # -----------------------------------------------------------------------
    # 7. Top-10 transactions by amount
    # -----------------------------------------------------------------------
    top_transactions: list[TopTransaction] = [
        TopTransaction(
            date=tx.date.isoformat(),
            amount=tx.amount,
            type=tx.type.value,
            category=tx.category,
            description=tx.description,
        )
        for tx in sorted(transactions, key=lambda t: t.amount, reverse=True)[:10]
    ]

    # -----------------------------------------------------------------------
    # 8. Averages — based on operating figures (financing excluded)
    # -----------------------------------------------------------------------
    month_count = len(all_months) or 1
    avg_monthly_revenue  = round(operating_revenue  / month_count, 2)
    avg_monthly_expenses = round(operating_expenses / month_count, 2)
    avg_monthly_profit   = round(operating_profit   / month_count, 2)
    operating_monthly_revenues = [operating_monthly_revenue.get(m, 0.0) for m in all_months]

    # -----------------------------------------------------------------------
    # 9. Pre-computed analytics for AI analyst
    # -----------------------------------------------------------------------
    # Real categories — what the user actually wrote in their CSV
    # Deduplicated case-insensitively for the same reason the totals are: the
    # model is handed this list as the ONLY category names it may use, and
    # three spellings of one category invited it to treat them as three.
    real_income_categories = [
        raw_display[k] for k in
        {_cat_key(_raw(t)) for t in transactions if t.type == TransactionType.income}
    ]
    real_expense_categories = [
        raw_display[k] for k in
        {_cat_key(_raw(t)) for t in transactions if t.type == TransactionType.expense}
    ]

    # Income by category with shares. Keyed the same way, or one category's
    # share was reported split across its spellings.
    income_by_category: dict[str, float] = {}
    for t in transactions:
        if t.type == TransactionType.income:
            key = raw_display[_cat_key(_raw(t))]
            income_by_category[key] = round(income_by_category.get(key, 0.0) + t.amount, 2)
    income_category_share = (
        {cat: round(amt / total_revenue * 100, 2) for cat, amt in income_by_category.items()}
        if total_revenue > 0 else {}
    )

    # Payroll vs outsource (matched against raw category)
    _PAYROLL_KW = {"payroll", "зарплата", "salary", "фот"}
    _OUTSOURCE_KW = {"outsource", "субподряд", "подрядчики", "фриланс"}
    payroll_total = round(sum(
        t.amount for t in transactions
        if t.type == TransactionType.expense and _raw(t).lower() in _PAYROLL_KW
    ), 2)
    outsource_total = round(sum(
        t.amount for t in transactions
        if t.type == TransactionType.expense and _raw(t).lower() in _OUTSOURCE_KW
    ), 2)
    _total_labor = payroll_total + outsource_total
    outsource_ratio = round(outsource_total / _total_labor * 100, 2) if _total_labor > 0 else 0.0

    # Marketing Fee %: share of marketing spend in same-month revenue
    _MARKETING_KW = {"marketing", "реклама", "advertising", "маркетинг"}
    _marketing_by_month: dict[str, float] = {}
    for t in transactions:
        if t.type == TransactionType.expense and _raw(t).lower() in _MARKETING_KW:
            mk = _month_key(t.date)
            _marketing_by_month[mk] = _marketing_by_month.get(mk, 0.0) + t.amount
    marketing_roi: dict = {}
    for _mon in sorted(monthly_revenue.keys()):
        if _mon in _marketing_by_month:
            _spend = round(abs(_marketing_by_month[_mon]), 2)
            _revenue = monthly_revenue[_mon]
            _fee_pct = round(_spend / _revenue * 100, 2) if _revenue > 0 else 0.0
            marketing_roi[_mon] = {
                "spend": _spend,
                "revenue": round(_revenue, 2),
                "marketing_fee_percent": _fee_pct,
                "is_healthy": _fee_pct <= 5,
                "benchmark": "2-5% норма для ресторана/ритейла",
            }

    # Weeks with negative net cash flow (intra-period cashflow gaps)
    _weekly_net: dict[str, float] = {}
    for t in transactions:
        _iso = t.date.isocalendar()
        _wk_iso = f"{_iso[0]}-W{_iso[1]:02d}"
        _delta = t.amount if t.type == TransactionType.income else -t.amount
        _weekly_net[_wk_iso] = _weekly_net.get(_wk_iso, 0.0) + _delta
    negative_weeks = {wk: round(bal, 2) for wk, bal in _weekly_net.items() if bal < 0}

    # UZ tax limit monitoring — operating revenue only (loans are NOT turnover for UZS USN)
    projected_annual_revenue = round(avg_monthly_revenue * 12, 2)
    _uz_tax_limit = 1_000_000_000
    tax_limit_usage_percent = round(projected_annual_revenue / _uz_tax_limit * 100, 2)
    tax_limit_warning = projected_annual_revenue > _uz_tax_limit * 0.8

    # -----------------------------------------------------------------------
    # 10. Deterministic health score (uses operating figures)
    # -----------------------------------------------------------------------
    health_breakdown = health_score_breakdown(
        operating_revenue=operating_revenue,
        operating_expenses=operating_expenses,
        operating_monthly_revenues=operating_monthly_revenues,
        monthly_data=monthly_breakdown,
        negative_weeks=negative_weeks,
        tax_limit_warning=tax_limit_warning,
        projected_annual_revenue=projected_annual_revenue,
    )
    health_score, _ = score_from_breakdown(health_breakdown)
    health_score_label = score_to_status_key(health_score)

    # -----------------------------------------------------------------------
    # 11. Cashflow forecast (30-day projection from period end)
    # -----------------------------------------------------------------------
    cashflow_forecast = calculate_cashflow_forecast(
        weekly_breakdown=weekly_breakdown,
        closing_balance=closing_balance,
        period_end_str=period_end,
    )

    return FinancialMetrics(
        period_start=period_start,
        period_end=period_end,
        total_days=total_days,
        total_revenue=total_revenue,
        total_expenses=total_expenses,
        profit=profit,
        profit_margin=profit_margin,
        avg_monthly_revenue=avg_monthly_revenue,
        avg_monthly_expenses=avg_monthly_expenses,
        avg_monthly_profit=avg_monthly_profit,
        revenue_by_category=revenue_breakdown,
        expense_by_category=expense_breakdown,
        top_transactions=top_transactions,
        cashflow_forecast=cashflow_forecast,
        weekly_breakdown=weekly_breakdown,
        monthly_breakdown=monthly_breakdown,
        mom_growth=mom_growth,
        mom_outliers=mom_outliers,
        anomalies=anomalies,
        transaction_count=len(transactions),
        income_count=income_count,
        expense_count=expense_count,
        income_by_category=income_by_category,
        income_category_share=income_category_share,
        payroll_total=payroll_total,
        outsource_total=outsource_total,
        outsource_ratio=outsource_ratio,
        marketing_roi=marketing_roi,
        negative_weeks=negative_weeks,
        projected_annual_revenue=projected_annual_revenue,
        tax_limit_usage_percent=tax_limit_usage_percent,
        tax_limit_warning=tax_limit_warning,
        real_income_categories=real_income_categories,
        real_expense_categories=real_expense_categories,
        health_score=health_score,
        health_score_label=health_score_label,
        health_breakdown=health_breakdown,
        operating_revenue=operating_revenue,
        financing_income=financing_income,
        financing_income_categories=sorted(_financing_income_cats),
        financing_expenses=financing_expenses,
    )
