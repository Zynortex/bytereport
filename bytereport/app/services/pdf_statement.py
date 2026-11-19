"""
Text-based bank-statement PDF reader.

Scope: PDFs whose text layer is real (selectable text). Scans and photos are
detected and rejected with an honest message — there is no OCR here.

Output is a grid (``list[list[str]]``) in the same shape every other upload
format produces, so it lands in `csv_parser.parse_grid` alongside CSV/XLSX/XLS/
HTML. Bank statements almost never carry expense categories, which naturally
drives `has_reliable_categories` to False via category_coverage.py.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# A page with a real text layer yields far more than this; a scan yields ~0.
MIN_CHARS_PER_PAGE = 20
MIN_TOTAL_CHARS = 60

# Canonical output header — matches the aliases csv_parser already understands,
# so no auto-mapping work is duplicated here.
OUT_HEADER = ["date", "amount", "type", "category", "description"]

# Column synonyms. Bank wording varies wildly between institutions.
DATE_HINTS = ("дата", "date", "сана", "дата операции", "дата проводки", "дата документа")
DEBIT_HINTS = ("дебет", "расход", "списание", "списано", "debit", "выдача", "чиқим")
CREDIT_HINTS = ("кредит", "приход", "поступление", "зачислено", "credit", "кирим")
AMOUNT_HINTS = ("сумма", "amount", "оборот", "сумма операции", "миқдор")
DESC_HINTS = ("описание", "назначение", "назначение платежа", "описание операции",
              "контрагент", "получатель", "detail", "description", "narrative",
              "изоҳ", "операция")
BALANCE_HINTS = ("остаток", "balance", "сальдо", "қолдиқ")

# Noise rows: bank letterhead, account numbers, page markers, totals.
NOISE_PATTERNS = [
    re.compile(r"^\s*стр(аница)?\.?\s*\d+", re.I),
    re.compile(r"^\s*page\s*\d+", re.I),
    re.compile(r"^\s*(итого|всего|оборот[ыи]? за период|total|жами)\b", re.I),
    re.compile(r"(расчётный|расчетный)\s+счёт|л/с|account\s*(no|number|#)", re.I),
    re.compile(r"^\s*(инн|кпп|бик|мфо|swift)\b", re.I),
    re.compile(r"^\s*выписка\b", re.I),
]

_DATE_RE = re.compile(
    r"\b(\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{4}[./-]\d{1,2}[./-]\d{1,2})\b"
)
# Money with thousands separators: 1 234 567,89 / 1,234,567.89 / 1234567.
# Anchored on explicit 3-digit groups, a decimal part, or a long digit run.
# The previous pattern was greedy across whitespace and swallowed two adjacent
# numbers ("20 000 000.00   130 000 000.00") as a SINGLE token, which silently
# defeated the amount-vs-balance choice below.
_MONEY_RE = re.compile(
    r"-?\d{1,3}(?:[\s ]\d{3})+(?:[.,]\d{1,2})?"
    r"|-?\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?"
    r"|-?\d+[.,]\d{1,2}"
    r"|-?\d{4,}"
)

# Date-shaped fragments that must NOT be read as money (e.g. 'от 04.01').
_DATE_FRAGMENT_RE = re.compile(r"\b\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?\b")


class PdfStatementError(ValueError):
    """Raised when a PDF cannot be turned into a transaction table."""


# A quarter of a busy account fits comfortably. Measured: a 150-page statement
# took 28 s on a desktop CPU and peaked at 140 MB; the free host has a tenth of
# a CPU, so a long statement would outlast the web's 3-minute request timeout.
MAX_PAGES = 50


class PdfTooManyPages(PdfStatementError):
    """More pages than MAX_PAGES. Checked before any page is parsed.

    Carries the numbers rather than a finished sentence: the upload route words
    it in the caller's language (report-copy.json → upload_errors)."""

    def __init__(self, pages: int, limit: int = MAX_PAGES) -> None:
        super().__init__(f"В PDF {pages} страниц, лимит {limit}.")
        self.pages = pages
        self.limit = limit


# ── Text layer ──────────────────────────────────────────────────────────────

def _extract_pages(content: bytes):
    """Open the PDF and return (pdfplumber pages, per-page text)."""
    try:
        import pdfplumber
    except ImportError as exc:  # pragma: no cover
        raise PdfStatementError(
            "Не удалось прочитать PDF: библиотека pdfplumber не установлена."
        ) from exc

    import io as _io

    try:
        pdf = pdfplumber.open(_io.BytesIO(content))
    except Exception as exc:
        raise PdfStatementError(
            "Не удалось открыть PDF — возможно, файл повреждён или защищён паролем."
        ) from exc
    return pdf


def _read_pages(pdf) -> tuple[list[str], list[tuple[int, list]]]:
    """
    One pass over the pages: each page's text and tables, then the page is let go.

    pdfplumber keeps every parsed page in memory until the file is closed. The
    reader used to walk the pages twice (text first, tables second), so all of
    them were held at once: a 150-page statement peaked at ~640 MB, more than
    the 512 MB a free host gives the whole server. Closing each page as soon as
    it is read keeps the peak flat whatever the page count, and each page is
    parsed once instead of twice.
    """
    texts: list[str] = []
    tables: list[tuple[int, list]] = []
    for page_no, page in enumerate(pdf.pages, start=1):
        try:
            texts.append(page.extract_text() or "")
            try:
                tables.append((page_no, page.extract_tables() or []))
            except Exception:
                logger.debug("extract_tables failed on page %d", page_no, exc_info=True)
        finally:
            page.close()
    return texts, tables


def assert_has_text_layer(texts: list[str]) -> str:
    """
    Reject scans before any table row is used.

    A scanned statement is an image with no text layer; extract_text returns
    nothing. We say so plainly rather than silently producing zero rows.
    """
    joined = "\n".join(texts)
    stripped = joined.strip()

    if len(stripped) < MIN_TOTAL_CHARS or all(
        len(t.strip()) < MIN_CHARS_PER_PAGE for t in texts
    ):
        logger.info(
            "PDF rejected as scanned: %d chars across %d page(s)",
            len(stripped), len(texts),
        )
        raise PdfStatementError(
            "Похоже, это отсканированное изображение. Пока поддерживаются "
            "только текстовые PDF (текст можно выделить мышкой)."
        )
    return joined


# ── Helpers ─────────────────────────────────────────────────────────────────

def _norm(cell: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (cell or "").replace("\n", " ")).strip()


def _is_noise(row: list[str]) -> bool:
    joined = " ".join(c for c in row if c).strip()
    if not joined:
        return True
    return any(p.search(joined) for p in NOISE_PATTERNS)


def _match(cell: str, hints: tuple[str, ...]) -> bool:
    low = cell.lower().strip()
    return any(h in low for h in hints)


def _classify_header(row: list[str]) -> Optional[dict[str, int]]:
    """Map a candidate header row to column indices, or None if it isn't one."""
    found: dict[str, int] = {}
    for idx, cell in enumerate(row):
        c = _norm(cell)
        if not c:
            continue
        if "date" not in found and _match(c, DATE_HINTS):
            found["date"] = idx
        elif "debit" not in found and _match(c, DEBIT_HINTS):
            found["debit"] = idx
        elif "credit" not in found and _match(c, CREDIT_HINTS):
            found["credit"] = idx
        elif "amount" not in found and _match(c, AMOUNT_HINTS):
            found["amount"] = idx
        elif "balance" not in found and _match(c, BALANCE_HINTS):
            found["balance"] = idx
        elif "desc" not in found and _match(c, DESC_HINTS):
            found["desc"] = idx

    has_money = ("debit" in found) or ("credit" in found) or ("amount" in found)
    if "date" in found and has_money:
        return found
    return None


def _clean_money(raw: str) -> str:
    """
    Normalise a money cell to a plain number string.

    The final numeric parsing is done by csv_parser._parse_amount — this only
    strips currency noise so that parser sees something it already handles.
    """
    t = _norm(raw)
    if not t:
        return ""
    t = t.replace(" ", " ")
    t = re.sub(r"[^\d\s.,-]", "", t)          # drop currency symbols/letters
    t = t.strip()
    if not re.search(r"\d", t):
        return ""
    return t


def _is_money(raw: str) -> bool:
    return bool(_clean_money(raw))


# ── Table extraction ────────────────────────────────────────────────────────

def _rows_from_tables(page_tables: list[tuple[int, list]]) -> list[list[str]]:
    """
    Collect table rows across all pages, keeping one header only.

    Banks repeat the column header on every page; those repeats must not become
    data rows, and must not be mistaken for a second table.
    """
    header_map: Optional[dict[str, int]] = None
    out: list[list[str]] = []

    for page_no, tables in page_tables:
        for table in tables:
            for raw_row in table:
                row = [_norm(c) for c in (raw_row or [])]
                if not any(row) or _is_noise(row):
                    continue

                candidate = _classify_header(row)
                if candidate:
                    # First header wins; later pages repeat it — skip those.
                    if header_map is None:
                        header_map = candidate
                        logger.info("PDF header found on page %d: %s", page_no, candidate)
                    continue

                if header_map is not None:
                    out.append(row)

    if header_map is None:
        return []
    return _map_rows(header_map, out)


def _map_rows(cols: dict[str, int], rows: list[list[str]]) -> list[list[str]]:
    """Turn bank columns into the canonical grid rows."""
    grid: list[list[str]] = [list(OUT_HEADER)]

    def cell(row: list[str], key: str) -> str:
        idx = cols.get(key)
        if idx is None or idx >= len(row):
            return ""
        return _norm(row[idx])

    for row in rows:
        date_raw = cell(row, "date")
        if not _DATE_RE.search(date_raw):
            # Continuation line of a wrapped description, or a stray row.
            continue

        debit = _clean_money(cell(row, "debit"))
        credit = _clean_money(cell(row, "credit"))
        amount = _clean_money(cell(row, "amount"))
        desc = cell(row, "desc")

        if debit:
            value, kind = debit, "expense"
        elif credit:
            value, kind = credit, "income"
        elif amount:
            # Single amount column: sign carries the direction.
            negative = amount.lstrip().startswith("-")
            value = amount.lstrip("-").strip()
            kind = "expense" if negative else "income"
        else:
            continue

        grid.append([
            _DATE_RE.search(date_raw).group(0),
            value,
            kind,
            "uncategorized",   # bank statements carry no categories
            desc or "—",
        ])

    return grid if len(grid) > 1 else []


# ── Text fallback ───────────────────────────────────────────────────────────

def _rows_from_text(text: str) -> list[list[str]]:
    """
    Line-by-line fallback when the PDF has no ruled table structure.

    Only lines that clearly carry a date AND a money value are accepted; a line
    we cannot read confidently is skipped, and if too few survive the caller
    raises rather than silently returning a partial statement.
    """
    grid: list[list[str]] = [list(OUT_HEADER)]
    for line in text.splitlines():
        line = line.strip()
        if not line or _is_noise([line]):
            continue
        dm = _DATE_RE.search(line)
        if not dm:
            continue

        rest = line[dm.end():]

        # Strip date fragments from the remainder first: a description such as
        # "по счёту №123 от 04.01" otherwise offers "04.01" as a money
        # candidate and the real amount gets misread.
        money_source = _DATE_FRAGMENT_RE.sub(" ", rest)

        monies = [m.group(0) for m in _MONEY_RE.finditer(money_source)]
        monies = [m for m in (_clean_money(x) for x in monies) if m]
        if not monies:
            continue

        # Heuristic: when a line carries two money values the last is usually a
        # running balance, so the amount is the one before it. With a single
        # value there is no balance column and that value IS the amount.
        # Verified against the no-table / no-balance fixture in fixtures_gen.
        value = monies[-2] if len(monies) >= 2 else monies[-1]
        negative = value.lstrip().startswith("-")
        value = value.lstrip("-").strip()

        desc = _MONEY_RE.sub(" ", money_source)
        desc = re.sub(r"\s+", " ", desc).strip(" .,-") or "—"

        grid.append([
            dm.group(0),
            value,
            "expense" if negative else "income",
            "uncategorized",
            desc,
        ])

    return grid if len(grid) > 1 else []


# ── Public API ──────────────────────────────────────────────────────────────

def read_pdf_grid(content: bytes) -> list[list[str]]:
    """
    Read a text-based bank statement PDF into the canonical grid.

    Raises PdfStatementError (a ValueError) with a user-facing message for
    scans, unreadable files, and statements whose structure we cannot resolve.
    """
    pdf = _extract_pages(content)
    try:
        # Counting pages reads the page tree only; nothing is parsed yet, so an
        # oversized statement is turned away at once, not after a minute.
        pages = len(pdf.pages)
        if pages > MAX_PAGES:
            raise PdfTooManyPages(pages)

        texts, page_tables = _read_pages(pdf)
        text = assert_has_text_layer(texts)

        grid = _rows_from_tables(page_tables)
        if grid:
            logger.info("PDF statement: %d rows via extract_tables", len(grid) - 1)
            return grid

        logger.info("PDF statement: no ruled table found, trying text fallback")
        grid = _rows_from_text(text)
        if grid:
            logger.info("PDF statement: %d rows via text fallback", len(grid) - 1)
            return grid

        raise PdfStatementError(
            "Не удалось распознать таблицу операций в этом PDF. "
            "Убедитесь, что это банковская выписка с таблицей транзакций."
        )
    finally:
        try:
            pdf.close()
        except Exception:  # pragma: no cover
            pass
