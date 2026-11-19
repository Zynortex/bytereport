"""
Upload format handling for ByteReport.

Turns an uploaded file of any supported kind into a plain grid
(``list[list[str]]``) which `csv_parser` then normalises. Every format feeds the
SAME normalisation path — there is no parallel branch of transaction logic.

Supported inputs
----------------
* ``.xlsx``            — ZIP container, read via openpyxl
* legacy binary ``.xls`` — OLE2 container, read via xlrd
* HTML masquerading as ``.xls`` — what old 1C / bank-client exports produce
* CSV in UTF-8 (with or without BOM), Windows-1251 or CP866, with ``, ; \\t |``

Format is decided by CONTENT, never by the filename: these exports routinely
carry a misleading extension.
"""

from __future__ import annotations

import codecs
import io
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# ── Container signatures ────────────────────────────────────────────────────
ZIP_MAGIC = b"PK\x03\x04"                      # .xlsx (and .xls-named xlsx)
OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"  # genuine legacy .xls
PDF_MAGIC = b"%PDF-"                              # text-based bank statement

# Single-byte candidates. UTF-8 is handled separately because it is the only
# one of these that reliably RAISES on incompatible bytes.
SINGLE_BYTE_CANDIDATES = ("cp1251", "cp866", "koi8-r", "iso-8859-5")

# Cyrillic letters score positively; box-drawing/pseudographics score heavily
# negative — they are the tell-tale artefact of decoding CP866 text as CP1251
# (and vice versa), which is exactly the confusion we must resolve.
_CYR_LOWER_RE = re.compile(r"[а-яё]")
_CYR_UPPER_RE = re.compile(r"[А-ЯЁ]")
_BOX_DRAWING_RE = re.compile(r"[─-╿▀-▟]")
_ODD_SYMBOL_RE = re.compile(r"[†-⁀ -¿]")

# Detector libraries return various spellings and near-variants; fold them onto
# the canonical name so the reported encoding is stable. cp1125 is cp866 plus
# Ukrainian letters - identical for Russian text - so it normalises to cp866.
_ENCODING_ALIASES = {
    "windows-1251": "cp1251", "win-1251": "cp1251", "x-cp1251": "cp1251",
    "ibm866": "cp866", "cp1125": "cp866", "ibm-866": "cp866",
    "koi8r": "koi8-r", "iso8859-5": "iso-8859-5", "iso-ir-144": "iso-8859-5",
}


def _canonical_encoding(name: str) -> str:
    key = name.lower().replace("_", "-")
    return _ENCODING_ALIASES.get(key, key)


class UnsupportedFileError(ValueError):
    """Raised when a file is neither a readable table nor recognisable."""


# ── Encoding ────────────────────────────────────────────────────────────────

def _cyrillic_plausibility(text: str) -> float:
    """
    Score how much a decoded string looks like real Cyrillic prose.

    Used to choose BETWEEN single-byte encodings. They all "succeed" on any
    byte sequence, so try/except cannot separate them — only the shape of the
    resulting text can.
    """
    if not text:
        return 0.0
    lower = len(_CYR_LOWER_RE.findall(text))
    upper = len(_CYR_UPPER_RE.findall(text))
    box = len(_BOX_DRAWING_RE.findall(text))
    odd = len(_ODD_SYMBOL_RE.findall(text))
    # Real Russian prose is overwhelmingly lowercase; a mis-decode that happens
    # to land in the Cyrillic block reads as ALL-CAPS noise, so lowercase is the
    # discriminating signal, not raw letter count.
    return (lower + 0.15 * upper - 3.0 * box - 2.0 * odd) / len(text)


def _statistical_candidates(content: bytes) -> list[str]:
    """Ask a detector library first; fall back to the standard candidate set."""
    ordered: list[str] = []

    try:
        from charset_normalizer import from_bytes

        best = from_bytes(content).best()
        if best is not None and best.encoding:
            ordered.append(_canonical_encoding(best.encoding))
    except Exception:  # pragma: no cover - detector is advisory only
        logger.debug("charset-normalizer unavailable or failed", exc_info=True)

    try:
        import chardet

        guess = chardet.detect(content)
        enc = (guess or {}).get("encoding")
        if enc:
            ordered.append(_canonical_encoding(enc))
    except Exception:  # pragma: no cover
        logger.debug("chardet unavailable or failed", exc_info=True)

    for enc in SINGLE_BYTE_CANDIDATES:
        if enc not in ordered:
            ordered.append(enc)
    return ordered


def decode_bytes(content: bytes) -> tuple[str, str]:
    """
    Decode CSV bytes to text, returning ``(text, encoding_used)``.

    Order matters:
      1. UTF-8 (BOM, then strict). It is the only candidate here that fails
         loudly on incompatible bytes, so a success is trustworthy. This also
         keeps existing UTF-8 behaviour byte-for-byte identical.
      2. Otherwise pick among single-byte encodings STATISTICALLY. CP1251 and
         CP866 decode virtually any byte sequence without error — sequential
         try/except would always pick whichever was tried first and silently
         return mojibake. We score each candidate's decoded text for Cyrillic
         plausibility and take the winner.
    """
    if content.startswith(codecs.BOM_UTF8):
        return content[len(codecs.BOM_UTF8):].decode("utf-8"), "utf-8-sig"

    try:
        return content.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        pass

    scored: list[tuple[float, str, str]] = []
    for enc in _statistical_candidates(content):
        try:
            text = content.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
        scored.append((_cyrillic_plausibility(text), enc, text))

    if not scored:
        # Last resort: never lose the upload over an exotic encoding.
        return content.decode("utf-8", errors="replace"), "utf-8/replace"

    def _rank(item):
        score, enc, _ = item
        pref = SINGLE_BYTE_CANDIDATES.index(enc) if enc in SINGLE_BYTE_CANDIDATES else len(SINGLE_BYTE_CANDIDATES)
        # Round the score so near-identical variants (cp866 vs cp1125) tie and
        # are then settled by the canonical preference order.
        return (-round(score, 4), pref)

    scored.sort(key=_rank)
    score, enc, text = scored[0]
    logger.info(
        "CSV encoding chosen statistically: %s (score=%.4f; candidates=%s)",
        enc, score, [f"{e}:{s:.3f}" for s, e, _ in scored[:4]],
    )
    return text, enc


# ── Delimiter ───────────────────────────────────────────────────────────────

def sniff_delimiter(text: str, default: str = ",") -> str:
    """Detect , ; tab or | using csv.Sniffer, falling back to `default`."""
    import csv as _csv

    sample = text[:4096]
    try:
        return _csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except _csv.Error:
        # Sniffer is fragile on short/ragged samples — fall back to whichever
        # candidate appears most often on the first non-empty line.
        for line in sample.splitlines():
            if line.strip():
                counts = {d: line.count(d) for d in ",;\t|"}
                best = max(counts, key=counts.get)
                return best if counts[best] > 0 else default
        return default


# ── Format detection ────────────────────────────────────────────────────────

def detect_format(content: bytes) -> str:
    """
    Classify by content: ``xlsx`` | ``xls`` | ``html`` | ``csv``.

    The filename is deliberately ignored — 1C and bank clients habitually name
    an HTML table or an xlsx workbook ``.xls``.
    """
    if content.startswith(PDF_MAGIC):
        return "pdf"
    if content.startswith(ZIP_MAGIC):
        return "xlsx"
    if content.startswith(OLE2_MAGIC):
        return "xls"

    head = content[:4096].lstrip()
    lowered = head[:1024].lower()
    if lowered.startswith(b"<") or b"<table" in lowered or b"<html" in lowered:
        return "html"
    return "csv"


# ── Grid extraction ─────────────────────────────────────────────────────────

def _df_to_grid(df) -> list[list[str]]:
    """DataFrame → grid of trimmed strings, dropping fully-empty rows."""
    import pandas as pd

    grid: list[list[str]] = []

    # read_html promotes a <th> row into df.columns even with header=None, which
    # would silently drop the header. If the columns carry real labels rather
    # than a default 0..n-1 range, put them back as the first row so the shared
    # header heuristic can find them.
    cols = list(df.columns)
    if not all(isinstance(c, int) for c in cols) or cols != list(range(len(cols))):
        header_cells = ["" if c is None or (isinstance(c, float) and pd.isna(c)) else str(c).strip()
                        for c in cols]
        if any(header_cells):
            grid.append(header_cells)
    for row in df.itertuples(index=False, name=None):
        cells = []
        for v in row:
            if v is None or (isinstance(v, float) and pd.isna(v)):
                cells.append("")
            elif hasattr(v, "strftime"):          # datetime from Excel
                cells.append(v.strftime("%Y-%m-%d"))
            elif isinstance(v, float) and v.is_integer():
                cells.append(str(int(v)))          # 1000.0 -> "1000"
            else:
                cells.append(str(v).strip())
        if any(c for c in cells):
            grid.append(cells)
    return grid


def _read_excel_grid(content: bytes, engine: str) -> list[list[str]]:
    import pandas as pd

    df = pd.read_excel(io.BytesIO(content), engine=engine, header=None, dtype=object)
    return _df_to_grid(df)


def _read_html_grid(content: bytes) -> list[list[str]]:
    """
    Parse an HTML export and return the table that looks like transactions.

    read_html yields every <table> on the page; 1C exports often wrap the data
    in layout tables, so pick by content rather than position.
    """
    import pandas as pd

    text, _ = decode_bytes(content)
    try:
        tables = pd.read_html(io.StringIO(text), header=None)
    except Exception as exc:
        raise UnsupportedFileError(
            "Файл выглядит как HTML, но таблицу с данными в нём найти не удалось."
        ) from exc

    if not tables:
        raise UnsupportedFileError("В HTML-файле не найдено ни одной таблицы.")

    best_grid: list[list[str]] = []
    best_score = -1
    for df in tables:
        grid = _df_to_grid(df)
        if not grid:
            continue
        # Score by how transaction-like the best header candidate row is.
        from app.services.csv_parser import score_header_row

        score = max((score_header_row(r) for r in grid[:10]), default=0)
        # Prefer a real header match; break ties by table size.
        weighted = score * 1000 + len(grid)
        if weighted > best_score:
            best_score, best_grid = weighted, grid

    if not best_grid:
        raise UnsupportedFileError("В HTML-файле не найдено таблиц с данными.")
    return best_grid


def read_grid(content: bytes, filename: Optional[str] = None) -> tuple[list[list[str]], str]:
    """
    Read any supported upload into ``(grid, format_label)``.

    Raises UnsupportedFileError with a user-facing message on anything that is
    not a readable table — callers surface it as 422, never a raw traceback.
    """
    if not content or not content.strip():
        raise UnsupportedFileError("Файл пуст или не содержит таблицы для анализа.")

    fmt = detect_format(content)
    logger.info("Upload format detected as %r (filename=%r)", fmt, filename)

    try:
        if fmt == "xlsx":
            return _read_excel_grid(content, "openpyxl"), fmt
        if fmt == "xls":
            return _read_excel_grid(content, "xlrd"), fmt
        if fmt == "html":
            return _read_html_grid(content), fmt
        if fmt == "pdf":
            from app.services.pdf_statement import read_pdf_grid
            return read_pdf_grid(content), fmt
    except UnsupportedFileError:
        raise
    except Exception as exc:
        from app.services.pdf_statement import PdfStatementError, PdfTooManyPages
        if isinstance(exc, PdfTooManyPages):
            # Kept as is: the route words it in the caller's language.
            raise
        if isinstance(exc, PdfStatementError):
            # Already a precise, user-facing reason (scan detected, no table...).
            raise UnsupportedFileError(str(exc)) from exc
        raise
    except ImportError as exc:
        raise UnsupportedFileError(
            f"Не удалось прочитать файл: не установлена библиотека для формата {fmt}."
        ) from exc
    except Exception as exc:
        logger.warning("Failed to read %s upload: %s", fmt, exc, exc_info=True)
        raise UnsupportedFileError(
            "Не удалось прочитать файл. Проверьте, что это таблица "
            "(CSV, XLSX или XLS) и что файл не повреждён."
        ) from exc

    # CSV
    text, encoding = decode_bytes(content)
    text = text.lstrip("﻿")
    if not text.strip():
        raise UnsupportedFileError("Файл пуст или не содержит таблицы для анализа.")

    import csv as _csv

    delimiter = sniff_delimiter(text)
    try:
        grid = [
            row for row in _csv.reader(io.StringIO(text), delimiter=delimiter)
            if any(c.strip() for c in row)
        ]
    except _csv.Error as exc:
        # Binary noise that survived decoding is not a table.
        raise UnsupportedFileError(
            "Не удалось прочитать файл. Проверьте, что это таблица "
            "(CSV, XLSX или XLS) и что файл не повреждён."
        ) from exc
    logger.info("CSV read: encoding=%s delimiter=%r rows=%d", encoding, delimiter, len(grid))
    if not grid:
        raise UnsupportedFileError("Файл пуст или не содержит таблицы для анализа.")
    return grid, fmt
