import asyncio
import logging

from fastapi import Depends, APIRouter, Request, UploadFile, File, HTTPException, status

from app.api.deps import request_language, throttled_anonymous
from app.models.transaction import ParseResult
from app.services.csv_parser import parse_upload
from app.services.pdf_statement import PdfTooManyPages
from app.services.report_copy import copy_text

router = APIRouter(prefix="/upload", tags=["upload"])
logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = (".csv", ".xlsx", ".xls", ".txt", ".pdf")

ALLOWED_CONTENT_TYPES = {
    "text/csv",
    "application/csv",
    "text/plain",
    "application/vnd.ms-excel",                                             # .xls
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",    # .xlsx
    "application/octet-stream",   # browsers send this for unknown extensions
    "text/html",                  # HTML export misnamed .xls
    "application/pdf",            # text-based bank statement
}


@router.post("", response_model=ParseResult, status_code=status.HTTP_200_OK)
async def upload_transactions(
    request: Request,
    file: UploadFile = File(...),
    _: None = Depends(throttled_anonymous),
) -> ParseResult:
    name = (file.filename or "").lower()
    if file.content_type not in ALLOWED_CONTENT_TYPES and not name.endswith(ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Поддерживаются файлы CSV, XLSX, XLS и текстовые PDF-выписки.",
        )

    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Загруженный файл пуст.",
        )

    try:
        # Actual format is decided by content signature inside parse_upload —
        # 1C and bank clients routinely mislabel the extension.
        #
        # On a worker thread: parsing is synchronous and a PDF statement takes
        # seconds. Run on the event loop, it froze the whole server for that
        # long — /health included, so a slow but live upload looked exactly
        # like a sleeping server to the web's wake check and to the host's
        # health check.
        result = await asyncio.to_thread(parse_upload, content, file.filename)
    except PdfTooManyPages as exc:
        logger.info("Rejected upload %r: %d PDF pages (limit %d)", file.filename, exc.pages, exc.limit)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=copy_text("upload_errors", "pdf_too_many_pages", request_language(request))
            .format(pages=exc.pages, limit=exc.limit),
        )
    except ValueError as exc:
        # Readable, user-facing reason; the traceback stays in the server log.
        logger.info("Rejected upload %r: %s", file.filename, exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except Exception:
        logger.exception("Unexpected failure parsing upload %r", file.filename)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Не удалось прочитать файл. Проверьте формат и попробуйте снова.",
        )

    return result
