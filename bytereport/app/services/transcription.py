"""
Speech -> text, via OpenAI's transcription endpoint.

Separate from voice_parser on purpose: transcription is provider-specific in a
way the parsing step is not (Anthropic has no audio endpoint), and keeping the
two apart means a note typed by hand never touches this module at all.
"""

from __future__ import annotations

import asyncio
import io
import logging
import time

from app.core.config import settings
from app.services import mock_ai

logger = logging.getLogger(__name__)

# Browser MediaRecorder produces webm/opus on Chrome and mp4/aac on Safari;
# both are accepted upstream. The extension matters because the API infers the
# container from the filename it is given.
SUPPORTED_SUFFIXES = {
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/mp4": "mp4",
    "audio/mpeg": "mp3",
    "audio/mpga": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/m4a": "m4a",
}

# The upstream limit is 25 MB. A note is seconds long, so anything near this is
# a mistake worth rejecting before it costs anything.
MAX_AUDIO_BYTES = 25 * 1024 * 1024


def suffix_for(content_type: str | None, filename: str | None) -> str:
    """Container extension to hand upstream, from the MIME type or the name."""
    if content_type:
        # "audio/webm;codecs=opus" -> "audio/webm"
        base = content_type.split(";")[0].strip().lower()
        if base in SUPPORTED_SUFFIXES:
            return SUPPORTED_SUFFIXES[base]
    if filename and "." in filename:
        ext = filename.rsplit(".", 1)[-1].lower()
        if ext in set(SUPPORTED_SUFFIXES.values()):
            return ext
    # webm is what the recorder in this app produces; a wrong guess surfaces as
    # a clear upstream error rather than a silent mistranscription.
    return "webm"


def _transcribe_sync(audio: bytes, suffix: str, language: str | None) -> tuple[str, str | None]:
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError("openai package not installed. Run: pip install openai")

    client = OpenAI(
        api_key=settings.openai_api_key,
        timeout=settings.ai_timeout_seconds,
        max_retries=0,   # same rationale as every other provider call here
    )

    buf = io.BytesIO(audio)
    buf.name = f"note.{suffix}"   # the SDK reads the container from this name

    kwargs: dict = {"model": settings.transcription_model, "file": buf}
    # A language hint materially improves Uzbek and Russian accuracy, but it is
    # only a hint: a user speaking Russian with the UI in English still gets
    # Russian back.
    if language:
        kwargs["language"] = language

    result = client.audio.transcriptions.create(**kwargs)
    text = getattr(result, "text", "") or ""
    detected = getattr(result, "language", None)
    return text, detected


async def transcribe(
    audio: bytes,
    content_type: str | None = None,
    filename: str | None = None,
    language: str | None = None,
) -> tuple[str, str | None]:
    """
    Transcribe recorded audio. Returns (text, detected_language).

    Raises ValueError for input the caller should fix, RuntimeError for a
    missing SDK — matching how the rest of the services signal the difference.
    """
    if not audio:
        raise ValueError("Пустая аудиозапись.")
    if len(audio) > MAX_AUDIO_BYTES:
        raise ValueError(
            f"Запись больше {MAX_AUDIO_BYTES // (1024 * 1024)} МБ. "
            "Наговорите заметку короче."
        )
    if not settings.openai_api_key and not settings.ai_mock:
        raise RuntimeError("OPENAI_API_KEY не настроен — распознавание речи недоступно.")

    suffix = suffix_for(content_type, filename)

    # Blocking upload on a worker thread, for the same reason as every other
    # provider call in this codebase: the event loop must stay answerable.
    _t0 = time.perf_counter()
    try:
        sync = mock_ai.transcribe_caller(language) if settings.ai_mock else _transcribe_sync
        text, detected = await asyncio.to_thread(sync, audio, suffix, language)
    except Exception:
        logger.exception(
            "transcription failed after %.2fs (%d bytes, .%s)",
            time.perf_counter() - _t0, len(audio), suffix,
        )
        raise
    logger.info(
        "transcription: %.2fs, %d bytes -> %d chars (model=%s, hint=%s, detected=%s)",
        time.perf_counter() - _t0, len(audio), len(text),
        settings.transcription_model, language, detected,
    )
    return text, detected
