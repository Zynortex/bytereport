"""
Programmatic upload fixtures.

Everything is generated in code — no binary blobs checked in. Each builder
returns raw bytes so tests can feed them straight to `parse_upload`.

The dataset carries the same traps as the hardcore CSV set:
  * a `kredit` financing row (must not count as operating revenue)
  * a duplicated Beta Group payment (must be flagged as a possible duplicate)
  * a future-dated row (must be excluded by preprocessing)
"""

from __future__ import annotations

import io
from datetime import date, timedelta

HEADERS = ["date", "amount", "type", "category", "description"]

# (date, amount, type, category, description)
ROWS: list[tuple[str, int, str, str, str]] = [
    ("2026-01-05",  50_000_000, "income",  "sales",      "Продажа услуг клиенту А"),
    ("2026-02-07",  60_000_000, "income",  "consulting", "Консультация по стратегии"),
    ("2026-03-10",  55_000_000, "income",  "sales",      "Продажа услуг клиенту Б"),
    ("2026-02-15", 150_000_000, "income",  "kredit",     "Кредит банка"),          # financing
    ("2026-01-10",  20_000_000, "expense", "payroll",    "Зарплата за январь"),
    ("2026-02-10",  22_000_000, "expense", "payroll",    "Зарплата за февраль"),
    ("2026-03-08",  25_000_000, "expense", "payroll",    "Зарплата за март"),
    ("2026-01-20",  10_000_000, "expense", "marketing",  "Реклама в соцсетях"),
    ("2026-02-20",  11_000_000, "expense", "marketing",  "Реклама в соцсетях"),
    ("2026-03-20",  12_000_000, "expense", "marketing",  "Реклама в соцсетях"),
    ("2026-03-10",  20_000_000, "expense", "beta_group", "Оплата Beta Group"),     # duplicate
    ("2026-03-10",  20_000_000, "expense", "beta_group", "Оплата Beta Group"),     # duplicate
]


def _future_row() -> tuple[str, int, str, str, str]:
    """A row dated well past today, whatever 'today' is when tests run."""
    d = (date.today() + timedelta(days=60)).isoformat()
    return (d, 5_000_000, "income", "sales", "Будущая продажа")


def all_rows() -> list[tuple[str, int, str, str, str]]:
    return [*ROWS, _future_row()]


# ── CSV variants ────────────────────────────────────────────────────────────

def csv_text(delimiter: str = ",", junk_header: bool = False) -> str:
    lines: list[str] = []
    if junk_header:
        # Typical 1C preamble: free text before the real header row.
        lines += [
            "Выгрузка операций из системы учёта",
            "Организация: ООО «Нова Диджитал»",
            "Период: 01.01.2026 — 31.03.2026",
            "",
        ]
    lines.append(delimiter.join(HEADERS))
    for r in all_rows():
        lines.append(delimiter.join(str(c) for c in r))
    return "\n".join(lines) + "\n"


def csv_utf8(delimiter: str = ",") -> bytes:
    return csv_text(delimiter).encode("utf-8")


def csv_utf8_bom(delimiter: str = ",") -> bytes:
    return b"\xef\xbb\xbf" + csv_text(delimiter).encode("utf-8")


def csv_cp1251() -> bytes:
    return csv_text().encode("cp1251")


def csv_cp866() -> bytes:
    return csv_text().encode("cp866")


def csv_with_header_junk() -> bytes:
    return csv_text(junk_header=True).encode("utf-8")


# ── Excel variants ──────────────────────────────────────────────────────────

def xlsx_bytes(junk_header: bool = False) -> bytes:
    """Modern .xlsx via openpyxl (ZIP container)."""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Операции"
    if junk_header:
        ws.append(["Выгрузка операций из системы учёта"])
        ws.append(["Период: 01.01.2026 — 31.03.2026"])
        ws.append([])
    ws.append(HEADERS)
    for r in all_rows():
        ws.append(list(r))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def xls_legacy_bytes() -> bytes:
    """Genuine legacy binary .xls (OLE2 container) via xlwt."""
    import xlwt

    wb = xlwt.Workbook()
    ws = wb.add_sheet("Operations")
    for c, h in enumerate(HEADERS):
        ws.write(0, c, h)
    for r_i, row in enumerate(all_rows(), start=1):
        for c_i, val in enumerate(row):
            ws.write(r_i, c_i, val)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def html_as_xls_bytes() -> bytes:
    """
    HTML table saved with an .xls name — what old 1C / bank clients emit.

    Includes a decorative layout table first, so the reader has to choose the
    right one rather than blindly taking table[0].
    """
    body = [
        "<html><head><meta charset='utf-8'></head><body>",
        "<table><tr><td>Отчёт по операциям</td></tr>",
        "<tr><td>Организация: ООО «Нова Диджитал»</td></tr></table>",
        "<table border='1'>",
        "<tr>" + "".join(f"<th>{h}</th>" for h in HEADERS) + "</tr>",
    ]
    for r in all_rows():
        body.append("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>")
    body.append("</table></body></html>")
    return "\n".join(body).encode("utf-8")


def broken_bytes() -> bytes:
    """Not a table at all — random binary noise."""
    return bytes(range(256)) * 8


def empty_bytes() -> bytes:
    return b"   \n  \n"


# ── Bank-statement PDF fixtures (Part B) ────────────────────────────────────

_BANK_HEADER = ["Дата операции", "Описание операции", "Дебет", "Кредит", "Остаток"]


def _bank_rows() -> list[list[str]]:
    """
    Statement rows derived from the same dataset, in bank shape:
    debit/credit columns instead of a type column, and no category at all.
    Dates deliberately use two different formats to exercise the parser.
    """
    rows: list[list[str]] = []
    balance = 0
    for i, (d, amount, kind, _cat, desc) in enumerate(all_rows()):
        y, m, day = d.split("-")
        shown = f"{day}.{m}.{y}" if i % 2 == 0 else d          # dd.mm.yyyy vs ISO
        if kind == "income":
            balance += amount
            rows.append([shown, desc, "", f"{amount:,.2f}".replace(",", " "),
                         f"{balance:,.2f}".replace(",", " ")])
        else:
            balance -= amount
            rows.append([shown, desc, f"{amount:,.2f}".replace(",", " "), "",
                         f"{balance:,.2f}".replace(",", " ")])
    return rows


def _statement_pdf(rows: list[list[str]], rows_per_page: int = 6) -> bytes:
    """
    Build a multi-page statement PDF with the header repeated on every page,
    plus bank letterhead and page numbers as noise.
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas as _canvas
    from reportlab.platypus import Table, TableStyle

    from app.services.pdf_generator import FONT_BOLD, FONT_REGULAR

    buf = io.BytesIO()
    c = _canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    pages = [rows[i:i + rows_per_page] for i in range(0, len(rows), rows_per_page)] or [[]]
    for page_no, chunk in enumerate(pages, start=1):
        # Letterhead / account noise the parser must discard.
        c.setFont(FONT_BOLD, 11)
        c.drawString(20 * mm, height - 18 * mm, "АО «ДЕМО БАНК»")
        c.setFont(FONT_REGULAR, 8)
        c.drawString(20 * mm, height - 24 * mm, "Выписка по счёту за период 01.01.2026 — 31.03.2026")
        c.drawString(20 * mm, height - 29 * mm, "Расчётный счёт: 20208000900001234567   ИНН: 302123456")

        data = [list(_BANK_HEADER)] + [list(r) for r in chunk]
        t = Table(data, colWidths=[26 * mm, 62 * mm, 28 * mm, 28 * mm, 28 * mm])
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), FONT_REGULAR),
            ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        t.wrapOn(c, width, height)
        t.drawOn(c, 20 * mm, height - 40 * mm - len(data) * 9 * mm)

        c.setFont(FONT_REGULAR, 7)
        c.drawString(20 * mm, 12 * mm, f"Страница {page_no} из {len(pages)}")
        c.showPage()

    c.save()
    return buf.getvalue()


def bank_statement_pdf() -> bytes:
    """Multi-page statement, repeated headers, mixed date formats."""
    return _statement_pdf(_bank_rows())


def bank_statement_pdf_with_traps() -> bytes:
    """
    Same statement — it already carries the hardcore traps, because _bank_rows()
    is built from all_rows(): the Beta Group duplicate and the future-dated row.
    Kept as a separate named fixture so the intent is explicit in tests.
    """
    return _statement_pdf(_bank_rows(), rows_per_page=5)


def scanned_pdf() -> bytes:
    """
    Scan imitation: a PDF whose pages contain only an embedded image and no
    text layer, so extract_text() returns nothing.
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas as _canvas

    # Minimal 8x8 PNG generated in-memory (no external asset).
    import struct
    import zlib

    def _png(w: int, h: int) -> bytes:
        raw = b"".join(b"\x00" + bytes([(x * 32) % 256] * 3 * w) for x in range(h))
        def chunk(tag: bytes, data: bytes) -> bytes:
            return (struct.pack(">I", len(data)) + tag + data
                    + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))
        return (b"\x89PNG\r\n\x1a\n"
                + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw))
                + chunk(b"IEND", b""))

    buf = io.BytesIO()
    c = _canvas.Canvas(buf, pagesize=A4)
    img = ImageReader(io.BytesIO(_png(8, 8)))
    c.drawImage(img, 40, 400, width=500, height=300)
    c.showPage()
    c.save()
    return buf.getvalue()


def bank_statement_pdf_no_table() -> bytes:
    """
    Statement with NO table structure — plain text lines only.

    The ruled fixture above always satisfies extract_tables(), so the
    extract_text() fallback in pdf_statement.py was never exercised. This one
    draws each transaction as a single text line (date, description, amount)
    with no cells, borders or column rules, which is what some bank exports and
    "print to PDF" statements actually look like.

    Deliberately has NO running-balance column, so it also probes the
    "last number on the line is the balance" heuristic.
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas as _canvas

    from app.services.pdf_generator import FONT_BOLD, FONT_REGULAR

    buf = io.BytesIO()
    c = _canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    y = height - 20 * mm
    c.setFont(FONT_BOLD, 11)
    c.drawString(20 * mm, y, "АО «ДЕМО БАНК»")
    y -= 6 * mm
    c.setFont(FONT_REGULAR, 8)
    c.drawString(20 * mm, y, "Выписка по счёту за период 01.01.2026 — 31.03.2026")
    y -= 5 * mm
    c.drawString(20 * mm, y, "Расчётный счёт: 20208000900001234567")
    y -= 10 * mm

    c.setFont(FONT_REGULAR, 8)
    for i, (d, amount, kind, _cat, desc) in enumerate(all_rows()):
        yy, mm_, dd = d.split("-")
        shown = f"{dd}.{mm_}.{yy}"
        # Expenses carry a leading minus; no balance column at all.
        sign = "-" if kind == "expense" else ""
        line = f"{shown}    {desc}    {sign}{amount:,.2f}".replace(",", " ")
        if y < 25 * mm:
            c.setFont(FONT_REGULAR, 7)
            c.drawString(20 * mm, 12 * mm, "Страница 1")
            c.showPage()
            c.setFont(FONT_REGULAR, 8)
            y = height - 20 * mm
        c.drawString(20 * mm, y, line)
        y -= 6 * mm

    c.showPage()
    c.save()
    return buf.getvalue()
