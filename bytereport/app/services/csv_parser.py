"""
CSV Parser for ByteReport.

Accepts a file-like object or bytes, auto-detects column names in Russian/English,
normalizes transactions, and returns a ParseResult.

Supported column name variants:
  date    : дата, date, дата транзакции, transaction date
  amount  : сумма, amount, сумма транзакции, transaction amount
  type    : тип, type, тип транзакции, transaction type
  category: категория, category
  description: описание, description, назначение, комментарий, comment, note
"""

import csv
import io
import logging
from datetime import date, datetime
from typing import Union

from app.models.transaction import ParseResult, Transaction, TransactionType
from app.utils.category_mapper import normalize_category

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Column alias maps  (lowercase → canonical field name)
# ---------------------------------------------------------------------------

DATE_ALIASES = {"дата", "date", "дата транзакции", "transaction date", "дата операции"}
AMOUNT_ALIASES = {"сумма", "amount", "сумма транзакции", "transaction amount", "стоимость", "итого"}
TYPE_ALIASES = {"тип", "type", "тип транзакции", "transaction type", "вид"}
CATEGORY_ALIASES = {"категория", "category", "раздел", "статья"}
DESCRIPTION_ALIASES = {
    "описание", "description", "назначение", "комментарий", "comment", "note",
    "наименование", "товар/услуга", "наименование операции",
}

# Accepted values that map to income/expense
INCOME_VALUES = {"income", "доход", "приход", "поступление", "+"}
EXPENSE_VALUES = {"expense", "расход", "трата", "списание", "-"}

DATE_FORMATS = [
    "%Y-%m-%d",
    "%d.%m.%Y",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%d-%m-%Y",
    "%Y/%m/%d",
]

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_ROWS = 50_000


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _detect_column(header: str, alias_set: set[str]) -> bool:
    return header.lower().strip() in alias_set


ALIAS_GROUPS = {
    "date": DATE_ALIASES,
    "amount": AMOUNT_ALIASES,
    "type": TYPE_ALIASES,
    "category": CATEGORY_ALIASES,
    "description": DESCRIPTION_ALIASES,
}


def _map_headers(fieldnames: list[str]) -> dict[str, str]:
    """Return {canonical_name: actual_csv_column} mapping."""
    mapping: dict[str, str] = {}
    for field in fieldnames:
        for canonical, aliases in ALIAS_GROUPS.items():
            if canonical not in mapping and _detect_column(field, aliases):
                mapping[canonical] = field
    return mapping


def score_header_row(cells: list[str]) -> int:
    """
    How many canonical fields this row's cells look like.

    A genuine header must name both required fields, so rows that fail to map
    `date` AND `amount` score 0 no matter how many other aliases they hit.
    """
    mapping = _map_headers([c for c in cells if c and c.strip()])
    if "date" not in mapping or "amount" not in mapping:
        return 0
    return len(mapping)


def find_header_row(grid: list[list[str]], max_scan: int = 10) -> int:
    """
    Locate the real header row inside the first `max_scan` rows.

    1C exports commonly prepend free text ("Выгрузка за период ...") before the
    actual header. Rather than skipping a fixed number of lines, scan for the
    row that actually names the columns. Falls back to row 0, which preserves
    the previous behaviour (and the existing "required columns not found"
    error) for ordinary files.
    """
    best_idx, best_score = 0, 0
    for idx, cells in enumerate(grid[:max_scan]):
        score = score_header_row(cells)
        if score > best_score:
            best_idx, best_score = idx, score
    if best_score and best_idx:
        logger.info("Header row found at index %d (score=%d)", best_idx, best_score)
    return best_idx


def _parse_date(value: str) -> date:
    value = value.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognized date format: '{value}'")


def _parse_amount(value: str) -> float:
    cleaned = (
        value.strip()
        .replace(" ", "")
        .replace("\xa0", "")   # non-breaking space
        .replace(",", ".")
        .replace("₽", "")
        .replace("$", "")
        .replace("€", "")
    )
    return float(cleaned)


def _parse_type(value: str) -> TransactionType:
    lowered = value.strip().lower()
    if lowered in INCOME_VALUES:
        return TransactionType.income
    if lowered in EXPENSE_VALUES:
        return TransactionType.expense
    raise ValueError(f"Unknown transaction type: '{value}'")


def _infer_type_from_amount(raw_amount: str) -> tuple[TransactionType, float]:
    """If CSV stores negative amounts for expenses, infer type automatically."""
    cleaned = raw_amount.strip().replace(" ", "").replace("\xa0", "").replace(",", ".")
    try:
        value = float(cleaned.replace("₽", "").replace("$", "").replace("€", ""))
    except ValueError:
        raise ValueError(f"Cannot parse amount: '{raw_amount}'")
    if value < 0:
        return TransactionType.expense, abs(value)
    return TransactionType.income, value


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_csv(
    content: Union[bytes, str],
    encoding: str = "utf-8",
    delimiter: str | None = None,
) -> ParseResult:
    """
    Parse CSV content and return a ParseResult.

    Args:
        content:   raw bytes or string content of the CSV file.
        encoding:  file encoding (default utf-8); also tries utf-8-sig for BOM.
        delimiter: force a specific delimiter; auto-detected if None.

    Returns:
        ParseResult with validated transactions, counts, and any warnings.
    """
    if isinstance(content, bytes):
        if len(content) > MAX_FILE_SIZE_BYTES:
            raise ValueError(f"File exceeds maximum allowed size of {MAX_FILE_SIZE_BYTES // 1024 // 1024} MB")
        if encoding == "utf-8":
            # Default path: detect the encoding properly. UTF-8 is still tried
            # first and strictly, so UTF-8 files behave exactly as before;
            # CP1251/CP866 files stop turning into replacement-character soup.
            from app.services.file_reader import decode_bytes
            text, _ = decode_bytes(content)
        else:
            # Caller pinned an explicit encoding — honour it.
            try:
                text = content.decode(encoding)
            except UnicodeDecodeError:
                text = content.decode("utf-8-sig", errors="replace")
    else:
        text = content

    # Remove BOM if present
    text = text.lstrip("﻿")

    # Auto-detect delimiter
    if delimiter is None:
        sample = text[:4096]
        sniffer = csv.Sniffer()
        try:
            dialect = sniffer.sniff(sample, delimiters=",;\t|")
            delimiter = dialect.delimiter
        except csv.Error:
            delimiter = ","

    grid = [
        row for row in csv.reader(io.StringIO(text), delimiter=delimiter)
        if any(c.strip() for c in row)
    ]
    if not grid:
        raise ValueError("CSV file is empty or has no headers")

    return parse_grid(grid)


def parse_grid(grid: list[list[str]]) -> ParseResult:
    """
    Normalise a table (from CSV, XLSX, XLS or HTML) into a ParseResult.

    Single shared path: the header row is located heuristically, then rows are
    validated and converted to Transactions. Every upload format funnels
    through here, so transaction handling cannot drift between formats.
    """
    if not grid:
        raise ValueError("CSV file is empty or has no headers")

    header_idx = find_header_row(grid)
    fieldnames: list[str] = [c.strip() for c in grid[header_idx]]
    data_rows = grid[header_idx + 1:]

    col_map = _map_headers(fieldnames)

    required = {"date", "amount"}
    missing = required - col_map.keys()
    if missing:
        raise ValueError(
            f"Required columns not found: {missing}. "
            f"Available headers: {fieldnames}"
        )

    has_type_col = "type" in col_map
    has_category_col = "category" in col_map
    has_description_col = "description" in col_map

    transactions: list[Transaction] = []
    warnings: list[str] = []
    skipped = 0
    row_num = 0

    for cells in data_rows:
        row_num += 1
        if row_num > MAX_ROWS:
            warnings.append(f"File truncated: only first {MAX_ROWS} rows processed")
            break

        # Pad/trim so a ragged row cannot raise IndexError.
        padded = list(cells) + [""] * (len(fieldnames) - len(cells))
        row = {name: (padded[i] or "") for i, name in enumerate(fieldnames)}

        try:
            raw_date = row[col_map["date"]]
            raw_amount = row[col_map["amount"]]

            if not raw_date or not raw_amount:
                warnings.append(f"Row {row_num + 1}: empty required field, skipped")
                skipped += 1
                continue

            # Determine type and amount
            if has_type_col:
                raw_type = row[col_map["type"]]
                tx_type = _parse_type(raw_type)
                amount = abs(_parse_amount(raw_amount))
            else:
                # Infer from signed amount
                tx_type, amount = _infer_type_from_amount(raw_amount)

            tx_date = _parse_date(raw_date)

            raw_category = row[col_map["category"]].strip() if has_category_col else ""
            description = row[col_map["description"]].strip() if has_description_col else raw_category

            # Normalize category using keyword mapping
            category_source = raw_category or description
            normalized_category = normalize_category(category_source, tx_type.value)

            transactions.append(
                Transaction(
                    date=tx_date,
                    description=description or raw_category or "—",
                    amount=amount,
                    type=tx_type,
                    category=normalized_category,
                    raw_category=raw_category or None,
                )
            )

        except (ValueError, KeyError) as exc:
            warnings.append(f"Row {row_num + 1}: {exc}, skipped")
            skipped += 1
            logger.debug("Skipped row %d: %s", row_num + 1, exc)
            continue

    return ParseResult(
        transactions=transactions,
        total_rows=row_num,
        skipped_rows=skipped,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Unified upload entry point
# ---------------------------------------------------------------------------

def parse_upload(content: bytes, filename: str | None = None) -> ParseResult:
    """
    Parse an uploaded file of any supported format into a ParseResult.

    Format is decided by content signature, not by the filename. XLSX, legacy
    binary XLS, HTML-masquerading-as-XLS and CSV (UTF-8 / CP1251 / CP866, with
    , ; tab or | delimiters) all converge on `parse_grid`, so there is exactly
    one implementation of transaction normalisation.

    Raises ValueError (surfaced as 422) with a user-facing message — never a
    raw traceback — when the file is not a readable table.
    """
    if content and len(content) > MAX_FILE_SIZE_BYTES:
        raise ValueError(
            f"File exceeds maximum allowed size of {MAX_FILE_SIZE_BYTES // 1024 // 1024} MB"
        )

    from app.services.file_reader import UnsupportedFileError, read_grid

    try:
        grid, fmt = read_grid(content, filename)
    except UnsupportedFileError as exc:
        raise ValueError(str(exc)) from exc

    logger.info("Parsing upload as %s: %d raw rows", fmt, len(grid))
    return parse_grid(grid)
