from typing import Optional

from fastapi import Depends, APIRouter, HTTPException, status
from pydantic import BaseModel

from app.api.deps import throttled_anonymous
from app.models.transaction import Transaction
from app.models.metrics import CashflowForecast, FinancialMetrics, WeeklyMetrics
from app.services.category_coverage import evaluate_categories
from app.services.financial_engine import calculate_cashflow_forecast, compute_metrics
from app.services.preprocessing import preprocess_transactions

router = APIRouter(prefix="/analyze", tags=["analyze"])


class AnalyzeRequest(BaseModel):
    transactions: list[Transaction]
    # Account balance at the end of the statement period, if the user knows
    # it. The only thing that turns the cash forecast into a BALANCE forecast;
    # without it the forecast is a trend of weekly net flow.
    closing_balance: Optional[float] = None


@router.post("", response_model=FinancialMetrics, status_code=status.HTTP_200_OK)
def analyze_transactions(
    body: AnalyzeRequest,
    _: None = Depends(throttled_anonymous),
) -> FinancialMetrics:
    if not body.transactions:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Transaction list is empty",
        )
    try:
        clean_txns, pre_meta = preprocess_transactions(body.transactions)
        if not clean_txns:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No valid transactions after removing future-dated rows",
            )
        metrics = compute_metrics(clean_txns, closing_balance=body.closing_balance)
        metrics.preprocessing_meta = pre_meta

        # Attached here, alongside preprocessing_meta, so financial_engine's
        # computation stays untouched. Measured on the transactions as parsed —
        # the signal is about the DATA, not the file format it arrived in.
        signal = evaluate_categories(clean_txns)
        metrics.category_coverage = signal.coverage
        metrics.category_reliability = signal.level

        return metrics
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )


class ForecastRequest(BaseModel):
    weekly_breakdown: list[WeeklyMetrics]
    period_end: str
    closing_balance: Optional[float] = None


@router.post("/forecast", response_model=CashflowForecast, status_code=status.HTTP_200_OK)
def recompute_forecast(
    body: ForecastRequest,
    _: None = Depends(throttled_anonymous),
) -> CashflowForecast:
    """
    Recompute only the cash forecast, e.g. after the user adds the balance on
    the report page. Pure arithmetic on figures the client already has: no AI
    call, so no report credit — adding a balance must not cost a second report.
    """
    try:
        return calculate_cashflow_forecast(
            weekly_breakdown=body.weekly_breakdown,
            closing_balance=body.closing_balance,
            period_end_str=body.period_end,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
