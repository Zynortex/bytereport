"""
Photo of a receipt / handwritten note -> the same draft rows as text or voice.

A third source, not a third data model. The vision model is asked for the exact
JSON the text parser asks for, and the result goes through the same
`voice_parser.finalize()`: same per-field uncertainty, same assumed-today
guard, same currency conversion. Anything that lived only here would be a rule
the photo path silently skips.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from datetime import date

from app.core.config import settings
from app.models.voice_note import DraftTransaction
from app.services import mock_ai
from app.services.cost import log_usage
from app.services.voice_parser import SYSTEM_PROMPT, _LANGUAGE_NAMES, finalize

logger = logging.getLogger(__name__)

# Photos of paper, not scans of ledgers. The project's upload ceiling already
# sits at 10 MB and a phone photo is well under it.
MAX_IMAGE_BYTES = 10 * 1024 * 1024

SUPPORTED_IMAGE_TYPES = {
    "image/jpeg": "jpeg",
    "image/jpg": "jpeg",
    "image/png": "png",
    "image/webp": "webp",
}

# Magic bytes, because a browser will happily label anything image/jpeg and the
# upstream model rejects a mislabelled payload with an opaque error.
_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", "jpeg"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"RIFF", "webp"),          # RIFF....WEBP
)

PHOTO_INSTRUCTIONS = """\

THIS INPUT IS A PHOTOGRAPH — of a receipt, an invoice, or a handwritten note.
The rules above apply unchanged. In addition:

- Read only what is legibly on the paper. A blurred digit is not a guess to be
  filled in confidently: transcribe your best reading AND flag that field.
- A receipt total and its line items are the SAME money. Record the total as
  one row; do not also add every line item, or the note doubles.
- A printed receipt date is the transaction date. Use it.
- If the image is too dark, too blurred or too cropped to read at all, return
  an empty transactions list and say so in `warnings` — do not invent rows to
  have something to show.
"""


def detect_image_type(data: bytes, content_type: str | None = None) -> str | None:
    """
    Image subtype from the bytes, and ONLY from the bytes.

    There is deliberately no fallback to the Content-Type header. An earlier
    version fell back when the magic bytes matched nothing, which meant a PDF
    labelled `image/jpeg` sailed past this check and was rejected by the vision
    API instead — a paid round trip to learn what the first four bytes already
    said. The three formats accepted here all have unambiguous signatures, so a
    non-match is an answer, not a gap.

    `content_type` is kept in the signature because callers have it and it is
    worth logging on a rejection; it does not influence the result.
    """
    for magic, kind in _SIGNATURES:
        if data.startswith(magic):
            if kind == "webp" and data[8:12] != b"WEBP":
                continue
            return kind
    if content_type:
        logger.info(
            "photo_parser: rejected an upload declared %s whose bytes match no "
            "supported image signature", content_type,
        )
    return None


def _call_openai_vision(data_url: str, user_text: str) -> str:
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError("openai package not installed. Run: pip install openai")

    client = OpenAI(
        api_key=settings.openai_api_key,
        timeout=settings.ai_timeout_seconds,
        max_retries=0,   # same rationale as every other provider call here
    )
    response = client.chat.completions.create(
        model=settings.vision_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT + PHOTO_INSTRUCTIONS},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    # "high" detail: a receipt's small print is the whole point,
                    # and the low-detail path downsamples it past legibility.
                    {"type": "image_url",
                     "image_url": {"url": data_url, "detail": "high"}},
                ],
            },
        ],
        max_completion_tokens=2000,
        response_format={"type": "json_object"},
    )
    log_usage(response, settings.vision_model)
    return response.choices[0].message.content or ""


async def parse_photo(
    image: bytes,
    content_type: str | None = None,
    language: str = "ru",
    currency: str = "UZS",
    today: date | None = None,
) -> tuple[list[DraftTransaction], list[str]]:
    """Photo -> draft rows, identical in shape to a parsed text note."""
    if not image:
        raise ValueError("Пустой файл изображения.")
    if len(image) > MAX_IMAGE_BYTES:
        raise ValueError(
            f"Изображение больше {MAX_IMAGE_BYTES // (1024 * 1024)} МБ. "
            "Сожмите фото и попробуйте ещё раз."
        )
    if not settings.openai_api_key and not settings.ai_mock:
        raise RuntimeError("OPENAI_API_KEY не настроен — разбор фото недоступен.")

    kind = detect_image_type(image, content_type)
    if kind is None:
        raise ValueError("Не похоже на изображение. Поддерживаются JPG, PNG и WebP.")

    today = today or date.today()
    lang_name = _LANGUAGE_NAMES.get(language, _LANGUAGE_NAMES["ru"])
    user_text = (
        f"TODAY: {today.isoformat()}\n"
        f"Business currency: {currency}\n"
        f"Write `description`, `category`, `warnings` and `notes` in {lang_name}.\n"
        "Read the photograph and return the JSON object now."
    )

    data_url = f"data:image/{kind};base64,{base64.b64encode(image).decode('ascii')}"

    _t0 = time.perf_counter()
    try:
        vision = (
            mock_ai.photo_caller(language, currency, today.isoformat())
            if settings.ai_mock else _call_openai_vision
        )
        raw = await asyncio.to_thread(vision, data_url, user_text)
    except Exception:
        logger.exception(
            "photo_parser: vision call failed after %.2fs (%d bytes, %s)",
            time.perf_counter() - _t0, len(image), kind,
        )
        raise
    logger.info(
        "photo_parser: %.2fs, %d bytes (%s) -> %d chars (model=%s)",
        time.perf_counter() - _t0, len(image), kind, len(raw), settings.vision_model,
    )

    # Same finalisation as the text path: guard, then convert.
    return await finalize(raw, today=today, language=language, currency=currency)
