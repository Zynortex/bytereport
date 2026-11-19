"""
Confirmed draft rows -> a styled .xlsx workbook.

Not a data dump: the sheet carries real formulas, so the totals stay correct
when the user edits an amount in Excel afterwards — which they will, because
this file is the deliverable of a flow whose whole premise is "the model got
most of it and you fix the rest".

Colours come from design-tokens.json, the same source the PDF and the web app
read, so the workbook belongs to the same document family as the PDF report.
"""

from __future__ import annotations

import io
from datetime import date, datetime
from typing import Optional

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from app.models.voice_note import MIN_RECORDS_FOR_ANALYSIS, DraftTransaction
from app.services.design_tokens import ACCENT, PDF

LABELS: dict[str, dict[str, str]] = {
    "ru": {
        "sheet": "Операции",
        "title": "Операции из заметки",
        "generated": "Составлено",
        "currency": "Валюта",
        "col_date": "Дата",
        "col_description": "Описание",
        "col_category": "Категория",
        "col_income": "Приход",
        "col_expense": "Расход",
        "col_check": "Проверить",
        "total": "ИТОГО",
        "net": "Чистый результат",
        "no_date": "не указана",
        "flagged": "требует проверки",
        "footnote": (
            "Разовый снимок по одной заметке. Для Health Score и анализа трендов "
            "нужно не менее {n} записей за период."
        ),
    },
    "uz": {
        "sheet": "Операциялар",
        "title": "Эслатмадан операциялар",
        "generated": "Тузилди",
        "currency": "Валюта",
        "col_date": "Сана",
        "col_description": "Тавсиф",
        "col_category": "Категория",
        "col_income": "Кирим",
        "col_expense": "Чиқим",
        "col_check": "Текшириш",
        "total": "ЖАМИ",
        "net": "Соф натижа",
        "no_date": "кўрсатилмаган",
        "flagged": "текширилсин",
        "footnote": (
            "Битта эслатма бўйича бир марталик кесим. Health Score ва тренд таҳлили "
            "учун давр бўйича камида {n} та ёзув керак."
        ),
    },
    "en": {
        "sheet": "Transactions",
        "title": "Transactions from a note",
        "generated": "Generated",
        "currency": "Currency",
        "col_date": "Date",
        "col_description": "Description",
        "col_category": "Category",
        "col_income": "Income",
        "col_expense": "Expense",
        "col_check": "Check",
        "total": "TOTAL",
        "net": "Net result",
        "no_date": "not given",
        "flagged": "needs review",
        "footnote": (
            "A one-off snapshot from a single note. A Health Score and trend "
            "analysis need at least {n} records over a period."
        ),
    },
}

def _rgb(hex_colour: str) -> str:
    """
    '#6B5482' -> 'FF6B5482'.

    OOXML colours are ARGB, and the alpha byte is load-bearing. Handing
    openpyxl a bare six-digit RGB makes it pad to eight with a LEADING ZERO
    byte, so every colour in the file was written as alpha 00 — fully
    transparent. Excel is lenient enough to paint them anyway; LibreOffice,
    Google Sheets and most preview renderers are not, and drew nothing: the
    header read as white bold text on white paper and the hairline borders
    vanished, which is exactly how the sheet was reported.

    'FF' is opaque. Every colour handed to openpyxl goes through here.
    """
    return "FF" + hex_colour.lstrip("#").upper()[-6:]


_INK = _rgb(PDF.get("page_ink", "#1E293B"))
_MUTED = _rgb(PDF.get("page_muted", "#5B6472"))
_GRID = _rgb(PDF.get("page_grid", "#E2E5EA"))
_HEADER_BG = _rgb(ACCENT)

_HAIRLINE = Side(style="thin", color=_GRID)
_BORDER = Border(left=_HAIRLINE, right=_HAIRLINE, top=_HAIRLINE, bottom=_HAIRLINE)

# Uzbek sums have no decimal part in practice and a thousands separator is what
# makes a six-figure number readable at a glance.
_MONEY_FORMAT = "#,##0"

_COLUMNS = ("col_date", "col_description", "col_category", "col_income", "col_expense", "col_check")
_WIDTHS = (14, 46, 22, 16, 16, 30)


def _parse_iso(value: Optional[str]) -> Optional[date]:
    """ISO string -> date, or None. Anything unparseable stays text in the cell."""
    if not value:
        return None
    try:
        return datetime.strptime(value.strip()[:10], "%Y-%m-%d").date()
    except (ValueError, AttributeError):
        return None


def _review_note(row: DraftTransaction, labels: dict[str, str]) -> str:
    """
    The 'Check' column: which fields the model was unsure about, and why.

    This is the uncertainty surviving into the file. A user who exports the
    sheet and comes back to it a week later still knows which numbers were
    guessed — otherwise the flag would exist only in a preview they closed.
    """
    if not row.uncertain:
        return ""
    field_names = {
        "date": labels["col_date"],
        "amount": labels["col_income"],
        "direction": labels["col_expense"],
        "description": labels["col_description"],
        "category": labels["col_category"],
    }
    parts: list[str] = []
    for field in row.uncertain:
        why = row.notes.get(field, "")
        label = field_names.get(field, field)
        parts.append(f"{label}: {why}" if why else label)
    return "; ".join(parts)


def generate_excel(
    transactions: list[DraftTransaction],
    business_name: Optional[str] = None,
    currency: str = "UZS",
    language: str = "ru",
    today: Optional[date] = None,
) -> bytes:
    """Build the workbook and return it as bytes."""
    labels = LABELS.get(language, LABELS["ru"])
    wb = Workbook()
    ws = wb.active
    ws.title = labels["sheet"]

    ncols = len(_COLUMNS)
    last_col = get_column_letter(ncols)

    # ── Title block ────────────────────────────────────────────────────────
    ws.merge_cells(f"A1:{last_col}1")
    title = ws["A1"]
    title.value = business_name.strip() if business_name and business_name.strip() else labels["title"]
    title.font = Font(bold=True, size=15, color=_INK)
    title.alignment = Alignment(vertical="center")
    ws.row_dimensions[1].height = 26

    ws.merge_cells(f"A2:{last_col}2")
    meta = ws["A2"]
    stamp = (today or date.today()).isoformat()
    meta.value = f"{labels['generated']}: {stamp}  ·  {labels['currency']}: {currency}"
    meta.font = Font(size=9, color=_MUTED)

    # ── Header row ─────────────────────────────────────────────────────────
    header_row = 4
    for i, key in enumerate(_COLUMNS, start=1):
        cell = ws.cell(row=header_row, column=i, value=labels[key])
        cell.font = Font(bold=True, size=10, color=_rgb("#FFFFFF"))
        cell.fill = PatternFill("solid", fgColor=_HEADER_BG)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = _BORDER
    ws.row_dimensions[header_row].height = 22

    # ── Data rows ──────────────────────────────────────────────────────────
    first_data = header_row + 1
    for offset, row in enumerate(transactions):
        r = first_data + offset
        parsed = _parse_iso(row.date)

        c_date = ws.cell(row=r, column=1)
        if parsed is not None:
            c_date.value = parsed
            c_date.number_format = "DD.MM.YYYY"
        else:
            # Keep whatever the note said. An unresolved fragment is
            # information; replacing it with a blank throws it away.
            c_date.value = row.date or labels["no_date"]
            c_date.font = Font(size=10, italic=True, color=_MUTED)

        ws.cell(row=r, column=2, value=row.description or "")
        ws.cell(row=r, column=3, value=row.category or "")

        # Income and expense are separate columns so the totals below are two
        # plain SUMs rather than a signed column needing SUMIF.
        income = ws.cell(row=r, column=4)
        expense = ws.cell(row=r, column=5)
        if row.amount is not None:
            target = income if row.direction == "income" else expense
            target.value = row.amount
        income.number_format = _MONEY_FORMAT
        expense.number_format = _MONEY_FORMAT

        check = ws.cell(row=r, column=6, value=_review_note(row, labels))
        if row.uncertain:
            check.font = Font(size=9, color=_rgb("#7A5A28"))
            for col in range(1, ncols + 1):
                ws.cell(row=r, column=col).fill = PatternFill("solid", fgColor=_rgb("#FBF6EC"))

        for col in range(1, ncols + 1):
            cell = ws.cell(row=r, column=col)
            cell.border = _BORDER
            cell.alignment = Alignment(
                vertical="top",
                wrap_text=col in (2, 6),
                horizontal="right" if col in (4, 5) else "left",
            )

    last_data = first_data + len(transactions) - 1

    # ── Totals: real formulas, not baked numbers ───────────────────────────
    total_row = (last_data if transactions else header_row) + 2
    ws.cell(row=total_row, column=3, value=labels["total"]).font = Font(bold=True, color=_INK)
    for col in (4, 5):
        letter = get_column_letter(col)
        cell = ws.cell(row=total_row, column=col)
        # An empty range would make SUM() a #REF!, so guard the no-rows case.
        cell.value = f"=SUM({letter}{first_data}:{letter}{last_data})" if transactions else 0
        cell.number_format = _MONEY_FORMAT
        cell.font = Font(bold=True, color=_INK)
        cell.border = Border(top=Side(style="medium", color=_HEADER_BG))

    net_row = total_row + 1
    ws.cell(row=net_row, column=3, value=labels["net"]).font = Font(bold=True, color=_INK)
    net = ws.cell(row=net_row, column=4)
    net.value = f"=D{total_row}-E{total_row}"
    # Red only when negative — the one place a semantic colour is justified,
    # matching the severity rule the rest of the product follows.
    net.number_format = "#,##0;[RED]-#,##0"
    net.font = Font(bold=True, size=12, color=_INK)

    # ── Honest footnote ────────────────────────────────────────────────────
    note_row = net_row + 2
    ws.merge_cells(start_row=note_row, start_column=1, end_row=note_row, end_column=ncols)
    foot = ws.cell(row=note_row, column=1)
    foot.value = labels["footnote"].format(n=MIN_RECORDS_FOR_ANALYSIS)
    foot.font = Font(size=9, italic=True, color=_MUTED)
    foot.alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[note_row].height = 30

    # ── Sheet furniture ────────────────────────────────────────────────────
    for i, width in enumerate(_WIDTHS, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width
    # Freeze below the header so the columns stay named while scrolling.
    ws.freeze_panes = ws.cell(row=first_data, column=1)
    if transactions:
        ws.auto_filter.ref = f"A{header_row}:{last_col}{last_data}"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
