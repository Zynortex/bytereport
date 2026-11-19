from pydantic import BaseModel, Field, computed_field
from typing import Any, Optional

from app.services.category_coverage import CategoryReliability


class TopTransaction(BaseModel):
    date: str
    amount: float
    type: str        # "income" | "expense"
    category: str
    description: str


class CategoryBreakdown(BaseModel):
    category: str
    total: float
    percentage: float
    transaction_count: int


class WeeklyMetrics(BaseModel):
    week_key: str       # "2024-01-W1"  (year-month-weekOfMonth)
    month: str          # "2024-01"
    week_number: int    # 1-5 within the month
    revenue: float
    expenses: float
    profit: float


class MonthMetrics(BaseModel):
    month: str          # "2024-01"
    revenue: float
    expenses: float
    profit: float
    profit_margin: float


class MoMGrowth(BaseModel):
    month: str
    revenue_growth_pct: Optional[float]
    expense_growth_pct: Optional[float]
    profit_growth_pct: Optional[float]

    # Chart-safe copies: identical to the raw values, except that a percentage
    # from a near-zero base is None so the line breaks instead of blowing up the
    # axis. Decided once in growth_display.py; both the web chart and the PDF
    # renderer plot THESE and neither re-applies the rule.
    revenue_growth_display: Optional[float] = None
    expense_growth_display: Optional[float] = None
    profit_growth_display: Optional[float] = None


class MoMOutlier(BaseModel):
    """A growth percentage withheld from the chart, with the real amounts."""

    month: str
    metric: str          # "revenue" | "expenses" | "profit"
    previous: float
    current: float
    pct: float


class AnomalyFlag(BaseModel):
    category: str
    month: str
    type: str           # "spike" | "drop" | "new_category" | "missing_category"
    severity: str       # "low" | "medium" | "high"
    value: float
    previous_value: Optional[float]
    change_pct: Optional[float]
    description: str


class CashflowForecast(BaseModel):
    """
    Four weeks forward from the end of the statement.

    The statement shows money moving, not money held. Without the account
    balance at the end of the period there is no starting point, so there is no
    date or amount at which the money runs out — only the trend of the weekly
    net flow. `balance_known` says which of the two this is, and every surface
    (web, PDF, AI text) branches on it.

    Defaults are the conservative case: a forecast saved before this field
    existed was computed from the period's profit, not from a balance, and
    must not be read as a balance forecast.
    """
    balance_known: bool = False
    closing_balance: Optional[float] = None   # the user's figure the projection starts from
    has_risk: bool
    risk_date: Optional[str]    # ISO date the balance first goes negative (balance_known only)
    risk_amount: Optional[float]  # absolute deficit amount (balance_known only)
    # list of dicts: {week, projected_date, projected_revenue, projected_expenses,
    #                 projected_net, projected_balance (None unless balance_known)}
    weekly_projection: list[Any]
    confidence: str             # "LOW" | "MEDIUM" | "HIGH"


class FinancialMetrics(BaseModel):
    period_start: str
    period_end: str
    total_days: int

    total_revenue: float
    total_expenses: float
    profit: float
    profit_margin: float

    avg_monthly_revenue: float
    avg_monthly_expenses: float
    avg_monthly_profit: float

    revenue_by_category: list[CategoryBreakdown]
    expense_by_category: list[CategoryBreakdown]

    weekly_breakdown: list[WeeklyMetrics]
    monthly_breakdown: list[MonthMetrics]
    mom_growth: list[MoMGrowth]
    # Points removed from the growth chart because the base was near zero.
    mom_outliers: list[MoMOutlier] = Field(default_factory=list)
    anomalies: list[AnomalyFlag]

    top_transactions: list[TopTransaction]
    cashflow_forecast: CashflowForecast

    transaction_count: int
    income_count: int
    expense_count: int

    # Pre-computed analytics for AI analyst
    income_by_category: dict = Field(default_factory=dict)
    income_category_share: dict = Field(default_factory=dict)
    payroll_total: float = 0.0
    outsource_total: float = 0.0
    outsource_ratio: float = 0.0
    marketing_roi: dict = Field(default_factory=dict)
    negative_weeks: dict = Field(default_factory=dict)
    projected_annual_revenue: float = 0.0
    tax_limit_usage_percent: float = 0.0
    tax_limit_warning: bool = False
    real_income_categories: list = Field(default_factory=list)
    real_expense_categories: list = Field(default_factory=list)
    health_score: int = 0
    health_score_label: str = ""
    # The five checks behind health_score, as computed — see
    # financial_engine.health_score_breakdown. Empty on reports saved before
    # it existed; the UI then simply shows no breakdown.
    health_breakdown: list[dict] = Field(default_factory=list)

    # Financing vs operating split (populated by financial_engine)
    operating_revenue: float = 0.0
    financing_income: float = 0.0
    financing_income_categories: list = Field(default_factory=list)
    financing_expenses: float = 0.0

    # Attached by /analyze endpoint after preprocessing
    preprocessing_meta: dict = Field(default_factory=dict)

    # Category-coverage signal, computed once by category_coverage.py and read
    # by the AI prompt, the PDF report and the web UI. Defaults describe the
    # historical case (categorised CSV/Excel), so existing behaviour is
    # unchanged for callers that never set them.
    category_coverage: float = 1.0
    category_reliability: CategoryReliability = "full"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def has_reliable_categories(self) -> bool:
        """
        Backwards-compatible alias for the previous boolean field.

        Derived rather than stored so it can never drift from
        `category_reliability`, and declared as a computed_field so it still
        appears in model_dump() — the PDF generator and the frontend read the
        serialised dict, and dropping the key would silently default them back
        to "categories are fine".
        """
        return self.category_reliability != "none"
