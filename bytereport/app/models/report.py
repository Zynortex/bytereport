from pydantic import BaseModel, Field, field_validator
from typing import Any, Optional


class HealthScore(BaseModel):
    score: int
    status: str
    reasoning: str


class WeeklyCashFlow(BaseModel):
    week: str       # e.g. "2024-01-W1"
    revenue: float
    expenses: float
    net: float      # revenue - expenses; includes financing transactions (raw cash position)


class KeyInsight(BaseModel):
    title: str
    severity: str   # low | medium | high
    explanation: str


class TopRisk(BaseModel):
    risk: str
    impact: str
    recommendation: str


class GrowthOpportunity(BaseModel):
    opportunity: str
    potential_impact: str
    action: str


class ExpenseAnalysis(BaseModel):
    problem_categories: list[Any]
    efficient_categories: list[Any]
    notes: str


class AnomalyReport(BaseModel):
    category: str
    issue: str
    severity: str   # low | medium | high
    explanation: str


class CashFlowAnalysis(BaseModel):
    status: str
    summary: str
    warning_level: str


class Forecast(BaseModel):
    outlook: str
    confidence: str   # low | medium | high
    summary: str


class PriorityAction(BaseModel):
    priority: int
    action: str
    expected_result: str


class AIReport(BaseModel):
    executive_summary: str
    financial_health_score: HealthScore
    key_insights: list[KeyInsight]
    top_risks: list[TopRisk]
    growth_opportunities: list[GrowthOpportunity]
    expense_analysis: ExpenseAnalysis
    anomalies: list[AnomalyReport]
    cash_flow_analysis: CashFlowAnalysis
    forecast: Forecast
    priority_actions: list[PriorityAction]
    # Structured weekly cash flow — populated from FinancialMetrics by ai_analyst after AI parse.
    # Includes financing transactions (raw cash position, not operating-only).
    weekly_cash_flow: list[WeeklyCashFlow] = Field(default_factory=list)
    # The language the text was generated in ("ru" | "uz" | "en"). Stamped by
    # the backend, not by the model, so the web can say "this report is in
    # English" when the interface is not. None on reports saved before.
    language: Optional[str] = None


class AIReportRequest(BaseModel):
    metrics: dict                      # FinancialMetrics as dict
    business_type: Optional[str] = None
    business_name: Optional[str] = None
    currency: str = "UZS"
    language: str = "ru"

    @field_validator("language")
    @classmethod
    def validate_language(cls, v: str) -> str:
        allowed = {"uz", "ru", "en"}
        if v not in allowed:
            raise ValueError(f"language must be one of {allowed}, got '{v}'")
        return v
