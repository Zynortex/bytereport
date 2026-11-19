"""
Tests for PDF generator — verifies output is valid PDF bytes
and that all sections render without errors across edge cases.
"""

import pytest
from app.models.report import (
    AIReport, HealthScore, KeyInsight, TopRisk,
    GrowthOpportunity, ExpenseAnalysis, AnomalyReport,
    CashFlowAnalysis, Forecast, PriorityAction,
)
from app.services.pdf_generator import generate_pdf


def _make_report(**overrides) -> AIReport:
    defaults = dict(
        executive_summary="Бизнес демонстрирует стабильный рост выручки при умеренном контроле расходов.",
        financial_health_score=HealthScore(score=72, status="Stable", reasoning="Положительная маржа прибыли."),
        key_insights=[
            KeyInsight(title="Рост выручки", severity="low", explanation="Выручка выросла на 8% в феврале."),
            KeyInsight(title="Маркетинг", severity="high", explanation="Расходы на маркетинг выросли на 100%."),
            KeyInsight(title="Программное обеспечение", severity="medium", explanation="Подписки +29%."),
        ],
        top_risks=[
            TopRisk(risk="Эффективность маркетинга", impact="CAC растёт", recommendation="Аудит кампаний."),
        ],
        growth_opportunities=[
            GrowthOpportunity(
                opportunity="Расширение услуг",
                potential_impact="Высокий",
                action="Запустить новый продукт.",
            ),
        ],
        expense_analysis=ExpenseAnalysis(
            problem_categories=["marketing", "software"],
            efficient_categories=["payroll"],
            notes="Общие расходы в норме.",
        ),
        anomalies=[
            AnomalyReport(
                category="marketing",
                issue="Spike +100%",
                severity="high",
                explanation="Расходы удвоились в феврале.",
            ),
        ],
        cash_flow_analysis=CashFlowAnalysis(
            status="Stable",
            summary="Положительный денежный поток сохраняется.",
            warning_level="low",
        ),
        forecast=Forecast(
            outlook="Умеренный рост",
            confidence="medium",
            summary="Следующие 30 дней ожидается стабильность.",
        ),
        priority_actions=[
            PriorityAction(priority=1, action="Аудит маркетинга", expected_result="Снижение CAC на 15%."),
            PriorityAction(priority=2, action="Оптимизация подписок", expected_result="Экономия 5 000 ₽/мес."),
        ],
    )
    defaults.update(overrides)
    return AIReport(**defaults)


def test_pdf_returns_bytes():
    pdf = generate_pdf(_make_report())
    assert isinstance(pdf, bytes)
    assert len(pdf) > 1000


def test_pdf_starts_with_pdf_magic():
    pdf = generate_pdf(_make_report())
    assert pdf[:4] == b"%PDF"


def test_pdf_with_meta():
    pdf = generate_pdf(
        _make_report(),
        business_name="Мой Магазин",
        business_type="retail",
        period="Январь–Март 2024",
    )
    assert pdf[:4] == b"%PDF"


def test_pdf_empty_lists():
    """Should render without errors when optional lists are empty."""
    report = _make_report(
        key_insights=[],
        top_risks=[],
        growth_opportunities=[],
        anomalies=[],
        priority_actions=[],
    )
    pdf = generate_pdf(report)
    assert pdf[:4] == b"%PDF"


def test_pdf_high_score():
    report = _make_report(
        financial_health_score=HealthScore(score=92, status="Excellent", reasoning="Top performance."),
    )
    pdf = generate_pdf(report)
    assert pdf[:4] == b"%PDF"


def test_pdf_critical_score():
    report = _make_report(
        financial_health_score=HealthScore(score=22, status="Critical", reasoning="Losses accumulating."),
        cash_flow_analysis=CashFlowAnalysis(
            status="Dangerous", summary="Cash depleting fast.", warning_level="high"
        ),
    )
    pdf = generate_pdf(report)
    assert pdf[:4] == b"%PDF"


def test_pdf_many_actions():
    actions = [
        PriorityAction(priority=i, action=f"Action {i}", expected_result=f"Result {i}")
        for i in range(1, 8)
    ]
    pdf = generate_pdf(_make_report(priority_actions=actions))
    assert pdf[:4] == b"%PDF"


def test_pdf_no_business_name():
    pdf = generate_pdf(_make_report(), business_name=None)
    assert pdf[:4] == b"%PDF"
