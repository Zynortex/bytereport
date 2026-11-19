"""
Voice / free-text note -> preview -> Excel.

Three endpoints, and the split between them is the product rule, not a
convenience: `/parse` produces a DRAFT and `/excel` consumes rows the client
sends back. There is deliberately no endpoint taking raw text straight to a
file, so "the preview cannot be skipped" is enforced by the shape of the API
rather than by frontend discipline alone.
"""

from __future__ import annotations

import io
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse

from app.api.deps import ai_caller
from app.core.auth import AuthUser, require_verified_user
from app.models.voice_note import (
    MIN_RECORDS_FOR_ANALYSIS,
    ExcelRequest,
    ParseNoteRequest,
    ParseNoteResponse,
    TranscriptionResponse,
)
from app.services.photo_parser import MAX_IMAGE_BYTES, parse_photo
from app.services.transcription import MAX_AUDIO_BYTES, transcribe
from app.services.voice_parser import parse_note

router = APIRouter(prefix="/voice", tags=["voice"])
logger = logging.getLogger(__name__)


@router.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe_note(
    file: UploadFile = File(...),
    language: str | None = Form(None),
    caller: AuthUser = Depends(ai_caller),
) -> TranscriptionResponse:
    """Recorded audio -> text. The text still has to go through /parse."""
    audio = await file.read()
    if len(audio) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Запись больше {MAX_AUDIO_BYTES // (1024 * 1024)} МБ.",
        )
    try:
        text, detected = await transcribe(
            audio,
            content_type=file.content_type,
            filename=file.filename,
            language=language or None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        )
    except Exception:
        logger.exception("transcription endpoint failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Не удалось распознать запись. Попробуйте ещё раз или наберите текст.",
        )

    return TranscriptionResponse(text=text, detected_language=detected)


@router.post("/parse", response_model=ParseNoteResponse)
async def parse_note_endpoint(
    body: ParseNoteRequest,
    caller: AuthUser = Depends(ai_caller),
) -> ParseNoteResponse:
    """
    Note -> draft rows for the preview.

    Nothing is generated or stored here. The response is what the user is about
    to see and edit; `analysis_available` stays False for this iteration
    because a single note cannot support a Health Score.
    """
    try:
        rows, warnings = await parse_note(
            text=body.text, language=body.language, currency=body.currency
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI provider error: {exc}",
        )
    except Exception:
        logger.exception("voice parse failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI вернул некорректный ответ, попробуйте ещё раз.",
        )

    return ParseNoteResponse(
        transactions=rows,
        warnings=warnings,
        source_text=body.text,
        analysis_available=False,
        records_needed=MIN_RECORDS_FOR_ANALYSIS,
    )


@router.post("/photo", response_model=ParseNoteResponse)
async def parse_photo_endpoint(
    file: UploadFile = File(...),
    language: str = Form("ru"),
    currency: str = Form("UZS"),
    caller: AuthUser = Depends(ai_caller),
) -> ParseNoteResponse:
    """
    Photo of a receipt or a handwritten note -> the same draft rows.

    Lives under /voice rather than a /photo router of its own: it is a third
    input to one flow, and the confirmed rows go to /voice/excel regardless of
    where they came from. A separate prefix would suggest a separate pipeline.
    """
    image = await file.read()
    if len(image) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Изображение больше {MAX_IMAGE_BYTES // (1024 * 1024)} МБ.",
        )
    try:
        rows, warnings = await parse_photo(
            image, content_type=file.content_type, language=language, currency=currency
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI provider error: {exc}",
        )
    except Exception:
        logger.exception("photo parse failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Не удалось прочитать фото. Попробуйте более чёткий снимок.",
        )

    return ParseNoteResponse(
        transactions=rows,
        warnings=warnings,
        source_text="",
        analysis_available=False,
        records_needed=MIN_RECORDS_FOR_ANALYSIS,
    )


@router.post("/excel")
def excel_endpoint(
    body: ExcelRequest,
    caller: AuthUser = Depends(require_verified_user),
) -> StreamingResponse:
    """Confirmed rows -> styled .xlsx."""
    # Imported here, not at module load: openpyxl costs ~0.6 s, and on a
    # free host that sleeps every cold start pays it before /health answers.
    from app.services.excel_generator import generate_excel

    if not body.transactions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нет подтверждённых операций для выгрузки.",
        )
    try:
        xlsx = generate_excel(
            transactions=body.transactions,
            business_name=body.business_name,
            currency=body.currency,
            language=body.language,
        )
    except Exception as exc:
        logger.exception("Excel generation failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Не удалось собрать Excel: {exc}",
        )

    filename = _safe_filename(body.business_name)
    return StreamingResponse(
        io.BytesIO(xlsx),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        # Same two-form Content-Disposition as the PDF route: filename= is
        # latin-1 only, filename*= carries the UTF-8 name (RFC 5987).
        headers={
            "Content-Disposition":
                f"attachment; filename=\"{filename}\"; filename*=UTF-8''{filename}"
        },
    )


def _safe_filename(business_name: str | None) -> str:
    if not business_name:
        return "bytereport_note.xlsx"
    ascii_only = "".join(
        c if (c.isascii() and (c.isalnum() or c in " -_")) else "_"
        for c in business_name
    )
    slug = ascii_only.strip("_").replace(" ", "_")[:40].strip("_")
    return f"bytereport_note_{slug}.xlsx" if slug else "bytereport_note.xlsx"
