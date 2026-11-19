import io
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

from app.api.deps import ReportCaller, refund_report, report_caller, throttled_anonymous
from app.models.report import AIReport, AIReportRequest
from app.services.ai_analyst import get_ai_analysis
from app.services.report_layout import coerce_layout

router = APIRouter(prefix="/report", tags=["report"])


# ---------------------------------------------------------------------------
# POST /report/analyze
# ---------------------------------------------------------------------------

@router.post("/analyze", response_model=AIReport, status_code=status.HTTP_200_OK)
async def generate_ai_report(
    body: AIReportRequest,
    caller: ReportCaller = Depends(report_caller),
) -> AIReport:
    """
    Send computed financial metrics to AI and get a structured CFO-level report.

    Costs one report credit, spent by `report_caller` before the provider is
    contacted. If the analysis fails for any reason the credit is given back.

    Body:
      - metrics:       output of POST /analyze (FinancialMetrics as dict)
      - business_type: optional, e.g. "retail", "saas", "restaurant"
      - business_name: optional
      - currency:      default "UZS"
    """
    try:
        return await _analyze(body)
    except BaseException:
        # A report the user did not get is a report they did not pay for —
        # whatever the failure, including a cancelled request.
        await refund_report(caller)
        raise


async def _analyze(body: AIReportRequest) -> AIReport:
    """The analysis itself, with provider failures mapped to HTTP errors."""
    try:
        return await get_ai_analysis(
            metrics=body.metrics,
            business_type=body.business_type,
            business_name=body.business_name,
            currency=body.currency,
            language=body.language,
        )

    except ValueError as exc:
        msg = str(exc)
        # safe_json_loads raises ValueError when all repair levels fail
        if "некорректный JSON" in msg or "AI вернул" in msg:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="AI вернул некорректный ответ, попробуйте ещё раз",
            )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI provider error: {exc}",
        )

    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI returned malformed JSON: {exc}",
        )

    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI response schema mismatch: {exc.error_count()} errors",
        )

    except Exception:
        logger.exception("Unhandled error in /report/analyze")
        raise


# ---------------------------------------------------------------------------
# POST /report/pdf
# ---------------------------------------------------------------------------

class PDFReportRequest(BaseModel):
    report: AIReport
    business_name: Optional[str] = None
    business_type: Optional[str] = None
    period: Optional[str] = None
    metrics: Optional[dict] = None
    language: str = "ru"
    # Which sections, in what order, and which list entries to leave out. None
    # means the default arrangement — the same one the web shows untouched.
    layout: Optional[dict] = None


@router.post("/pdf", status_code=status.HTTP_200_OK)
def generate_pdf_report(
    body: PDFReportRequest,
    _: None = Depends(throttled_anonymous),
) -> StreamingResponse:
    """
    Generate a branded PDF from an AIReport.

    Body:
      - report:        AIReport object (output of POST /report/analyze)
      - business_name: shown on cover and header
      - business_type: shown on cover
      - period:        reporting period label, e.g. "January–March 2024"
      - metrics:       optional FinancialMetrics dict (reserved for future use)

    Returns a PDF file as application/pdf.
    """
    # Lazy: reportlab (and matplotlib behind it) only when a PDF is asked for,
    # so a cold start answers /health without loading them.
    from app.services.pdf_generator import generate_pdf

    try:
        pdf_bytes = generate_pdf(
            report=body.report,
            business_name=body.business_name,
            business_type=body.business_type,
            period=body.period,
            metrics=body.metrics,
            language=body.language,
            layout=coerce_layout(body.layout),
        )
    except ValueError as exc:
        # An unknown block id in the layout is the caller's mistake.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.exception("PDF generation failed")   # full traceback → server logs
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"PDF generation failed: {exc}",
        )

    filename = _safe_filename(body.business_name)

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        # filename= accepts only ASCII (latin-1); filename*= carries the UTF-8 version (RFC 5987)
        headers={"Content-Disposition": f"attachment; filename=\"{filename}\"; filename*=UTF-8''{filename}"},
    )


def _safe_filename(business_name: Optional[str]) -> str:
    if not business_name:
        return "bytereport.pdf"
    # Keep only ASCII-safe chars: isalnum() matches unicode too, so add .isascii() guard
    ascii_only = "".join(
        c if (c.isascii() and (c.isalnum() or c in " -_")) else "_"
        for c in business_name
    )
    slug = ascii_only.strip("_").replace(" ", "_")[:40].strip("_")
    return f"bytereport_{slug}.pdf" if slug else "bytereport.pdf"
