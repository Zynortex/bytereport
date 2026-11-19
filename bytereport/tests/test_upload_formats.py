"""
Tests for multi-format upload parsing: xlsx, legacy xls, HTML-as-xls, and CSV
in UTF-8 / CP1251 / CP866 with assorted delimiters.

Column auto-mapping is deliberately out of scope here — fixtures use canonical
header names.
"""

import pytest

from app.services.csv_parser import (
    find_header_row,
    parse_csv,
    parse_grid,
    parse_upload,
    score_header_row,
)
from app.services.file_reader import (
    UnsupportedFileError,
    decode_bytes,
    detect_format,
    read_grid,
    sniff_delimiter,
)
from tests import fixtures_gen as F

EXPECTED_ROWS = len(F.all_rows())          # 12 base + 1 future
CYRILLIC_MARKER = "Оплата Beta Group"


def _descriptions(result) -> list[str]:
    return [t.description for t in result.transactions]


# ── Задача 2: format detection by content, not extension ────────────────────

@pytest.mark.parametrize("data,expected", [
    (F.xlsx_bytes(),        "xlsx"),
    (F.xls_legacy_bytes(),  "xls"),
    (F.html_as_xls_bytes(), "html"),
    (F.csv_utf8(),          "csv"),
    (F.csv_utf8_bom(),      "csv"),
])
def test_detect_format_by_signature(data, expected):
    assert detect_format(data) == expected


def test_xlsx_named_as_xls_is_still_detected_as_xlsx():
    """Extension is ignored — a ZIP container is xlsx whatever it's called."""
    assert detect_format(F.xlsx_bytes()) == "xlsx"
    result = parse_upload(F.xlsx_bytes(), "выгрузка.xls")
    assert len(result.transactions) == EXPECTED_ROWS


# ── Задача 4 + тесты 1-3: each format parses ────────────────────────────────

def test_xlsx_parses():
    r = parse_upload(F.xlsx_bytes(), "data.xlsx")
    assert len(r.transactions) == EXPECTED_ROWS
    assert CYRILLIC_MARKER in _descriptions(r)


def test_legacy_binary_xls_parses():
    r = parse_upload(F.xls_legacy_bytes(), "data.xls")
    assert len(r.transactions) == EXPECTED_ROWS
    assert CYRILLIC_MARKER in _descriptions(r)


def test_html_masquerading_as_xls_parses():
    r = parse_upload(F.html_as_xls_bytes(), "1c_export.xls")
    assert len(r.transactions) == EXPECTED_ROWS
    assert CYRILLIC_MARKER in _descriptions(r)


# ── Тесты 4-6: CSV encodings ────────────────────────────────────────────────

def test_csv_utf8_parses():
    r = parse_upload(F.csv_utf8(), "data.csv")
    assert len(r.transactions) == EXPECTED_ROWS


def test_csv_utf8_bom_parses():
    r = parse_upload(F.csv_utf8_bom(), "data.csv")
    assert len(r.transactions) == EXPECTED_ROWS
    assert CYRILLIC_MARKER in _descriptions(r)


def test_csv_cp1251_preserves_cyrillic():
    r = parse_upload(F.csv_cp1251(), "data.csv")
    assert len(r.transactions) == EXPECTED_ROWS
    descs = _descriptions(r)
    assert CYRILLIC_MARKER in descs
    assert "Зарплата за январь" in descs
    assert not any("�" in d for d in descs), "replacement chars — decoded wrong"


def test_csv_cp866_preserves_cyrillic():
    r = parse_upload(F.csv_cp866(), "data.csv")
    assert len(r.transactions) == EXPECTED_ROWS
    descs = _descriptions(r)
    assert CYRILLIC_MARKER in descs
    assert "Зарплата за январь" in descs
    assert not any("�" in d for d in descs)


# ── Задача 3: statistical, not sequential, encoding choice ──────────────────

def test_utf8_decoded_strictly_first():
    text, enc = decode_bytes(F.csv_utf8())
    assert enc == "utf-8"
    assert "Оплата Beta Group" in text


def test_bom_reported_separately():
    text, enc = decode_bytes(F.csv_utf8_bom())
    assert enc == "utf-8-sig"
    assert not text.startswith("﻿")


def test_cp1251_and_cp866_are_distinguished_statistically():
    """
    The core requirement: both encodings decode ANY bytes without error, so a
    sequential try/except cannot tell them apart. Each must resolve to itself.
    """
    _, enc1251 = decode_bytes(F.csv_cp1251())
    _, enc866 = decode_bytes(F.csv_cp866())
    assert enc1251.replace("-", "") == "cp1251", f"got {enc1251}"
    assert enc866.replace("-", "") == "cp866", f"got {enc866}"
    assert enc1251 != enc866


def test_both_encodings_decode_without_error_proving_try_except_insufficient():
    """Demonstrates WHY detection is statistical: neither raises on the other."""
    cp1251_bytes = F.csv_cp1251()
    # cp866 happily decodes cp1251 bytes — just into nonsense.
    wrong = cp1251_bytes.decode("cp866")
    assert "Оплата Beta Group" not in wrong
    right = cp1251_bytes.decode("cp1251")
    assert "Оплата Beta Group" in right


# ── Задача 3.3: delimiters ──────────────────────────────────────────────────

@pytest.mark.parametrize("delim", [",", ";", "\t", "|"])
def test_all_delimiters_parse(delim):
    r = parse_upload(F.csv_text(delim).encode("utf-8"), "data.csv")
    assert len(r.transactions) == EXPECTED_ROWS


@pytest.mark.parametrize("delim", [",", ";", "\t", "|"])
def test_sniff_delimiter(delim):
    assert sniff_delimiter(F.csv_text(delim)) == delim


# ── Задача 5: header junk + empty files ─────────────────────────────────────

def test_header_row_found_after_1c_preamble():
    grid, _ = read_grid(F.csv_with_header_junk())
    idx = find_header_row(grid)
    assert idx > 0, "preamble not skipped"
    assert "date" in [c.strip().lower() for c in grid[idx]]


def test_csv_with_header_junk_loses_no_rows():
    clean = parse_upload(F.csv_utf8(), "a.csv")
    junky = parse_upload(F.csv_with_header_junk(), "b.csv")
    assert len(junky.transactions) == len(clean.transactions) == EXPECTED_ROWS


def test_xlsx_with_header_junk_parses():
    r = parse_upload(F.xlsx_bytes(junk_header=True), "junk.xlsx")
    assert len(r.transactions) == EXPECTED_ROWS


def test_header_scan_is_heuristic_not_fixed_offset():
    """Row 0 stays the header for ordinary files — no blanket row skipping."""
    grid, _ = read_grid(F.csv_utf8())
    assert find_header_row(grid) == 0


def test_score_header_row_requires_both_required_fields():
    assert score_header_row(["Выгрузка за период"]) == 0
    assert score_header_row(["date", "category"]) == 0          # no amount
    assert score_header_row(["date", "amount"]) == 2
    assert score_header_row(["date", "amount", "type", "category"]) == 4


@pytest.mark.parametrize("data", [F.empty_bytes(), b"", b"\n\n\n"])
def test_empty_file_gives_clean_error(data):
    with pytest.raises(ValueError) as exc:
        parse_upload(data, "empty.csv")
    assert "пуст" in str(exc.value).lower()


def test_broken_binary_gives_clean_error_not_traceback():
    with pytest.raises(ValueError) as exc:
        parse_upload(F.broken_bytes(), "broken.xls")
    msg = str(exc.value)
    assert msg and "Traceback" not in msg


def test_table_without_required_columns_gives_clean_error():
    grid = [["foo", "bar"], ["1", "2"]]
    with pytest.raises(ValueError) as exc:
        parse_grid(grid)
    assert "not found" in str(exc.value).lower()


# ── Тест 9 + ограничение: existing CSV behaviour unchanged ──────────────────

def test_parse_csv_still_accepts_str_input():
    r = parse_csv(F.csv_text())
    assert len(r.transactions) == EXPECTED_ROWS


def test_parse_csv_bytes_matches_parse_upload():
    a = parse_csv(F.csv_utf8())
    b = parse_upload(F.csv_utf8(), "x.csv")
    assert len(a.transactions) == len(b.transactions)
    assert _descriptions(a) == _descriptions(b)


def test_explicit_encoding_argument_still_honoured():
    r = parse_csv(F.csv_cp1251(), encoding="cp1251")
    assert CYRILLIC_MARKER in _descriptions(r)


# ── Every format converges on the same normalisation ────────────────────────

def test_all_formats_produce_identical_transactions():
    """
    The strongest guarantee that there is no parallel branch of logic: xlsx,
    legacy xls, HTML and every CSV encoding must yield the same transactions.
    """
    results = {
        "csv-utf8":   parse_upload(F.csv_utf8(), "a.csv"),
        "csv-bom":    parse_upload(F.csv_utf8_bom(), "b.csv"),
        "csv-cp1251": parse_upload(F.csv_cp1251(), "c.csv"),
        "csv-cp866":  parse_upload(F.csv_cp866(), "d.csv"),
        "csv-junk":   parse_upload(F.csv_with_header_junk(), "e.csv"),
        "xlsx":       parse_upload(F.xlsx_bytes(), "f.xlsx"),
        "xls":        parse_upload(F.xls_legacy_bytes(), "g.xls"),
        "html":       parse_upload(F.html_as_xls_bytes(), "h.xls"),
    }
    baseline = [
        (t.date, t.amount, t.type, t.category, t.description)
        for t in results["csv-utf8"].transactions
    ]
    for label, res in results.items():
        got = [
            (t.date, t.amount, t.type, t.category, t.description)
            for t in res.transactions
        ]
        assert got == baseline, f"{label} diverged from the CSV baseline"


# ── Тест 1: preprocessing traps survive the xlsx path ───────────────────────

def test_xlsx_traps_behave_like_csv():
    """kredit / duplicate / future-date traps must fire identically."""
    from app.services.financial_engine import compute_metrics
    from app.services.preprocessing import preprocess_transactions

    for label, data in (("csv", F.csv_utf8()), ("xlsx", F.xlsx_bytes()),
                        ("xls", F.xls_legacy_bytes()), ("html", F.html_as_xls_bytes())):
        parsed = parse_upload(data, f"x.{label}")
        clean, meta = preprocess_transactions(parsed.transactions)

        assert len(meta["future_transactions"]) == 1, f"{label}: future row not excluded"
        dupes = meta["possible_duplicates"]
        assert len(dupes) == 1, f"{label}: duplicate not detected"
        assert dupes[0]["count"] == 2

        m = compute_metrics(clean)
        assert m.financing_income == pytest.approx(150_000_000.0), f"{label}: kredit misclassified"
        assert m.operating_revenue == pytest.approx(165_000_000.0), f"{label}"


# ── read_grid contract ──────────────────────────────────────────────────────

def test_read_grid_reports_format():
    for data, fmt in ((F.csv_utf8(), "csv"), (F.xlsx_bytes(), "xlsx"),
                      (F.xls_legacy_bytes(), "xls"), (F.html_as_xls_bytes(), "html")):
        _, got = read_grid(data)
        assert got == fmt


def test_read_grid_raises_unsupported_on_noise():
    with pytest.raises(UnsupportedFileError):
        read_grid(F.broken_bytes(), "noise.xls")


# ── End-to-end through the HTTP route ───────────────────────────────────────

def _client():
    from fastapi.testclient import TestClient
    from main import app
    return TestClient(app)


@pytest.mark.parametrize("filename,data,ctype", [
    ("data.csv",       F.csv_utf8(),          "text/csv"),
    ("bom.csv",        F.csv_utf8_bom(),      "text/csv"),
    ("cp1251.csv",     F.csv_cp1251(),        "text/csv"),
    ("cp866.csv",      F.csv_cp866(),         "text/csv"),
    ("junk.csv",       F.csv_with_header_junk(), "text/csv"),
    ("book.xlsx",      F.xlsx_bytes(),        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ("legacy.xls",     F.xls_legacy_bytes(),  "application/vnd.ms-excel"),
    ("1c_export.xls",  F.html_as_xls_bytes(), "application/vnd.ms-excel"),
    ("unknown.xls",    F.xlsx_bytes(),        "application/octet-stream"),
], ids=["csv-utf8", "csv-bom", "csv-cp1251", "csv-cp866", "csv-junk-header",
        "xlsx", "xls-legacy", "html-as-xls", "xlsx-as-octet-stream"])
def test_upload_route_accepts_every_format(filename, data, ctype):
    resp = _client().post("/upload", files={"file": (filename, data, ctype)})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["transactions"]) == EXPECTED_ROWS


def test_upload_route_rejects_empty_file_with_400():
    resp = _client().post("/upload", files={"file": ("empty.csv", b"", "text/csv")})
    assert resp.status_code == 400
    assert "detail" in resp.json()


def test_upload_route_returns_422_not_500_on_garbage():
    resp = _client().post(
        "/upload", files={"file": ("noise.xls", F.broken_bytes(), "application/vnd.ms-excel")}
    )
    assert resp.status_code == 422, f"expected clean 422, got {resp.status_code}"
    detail = resp.json()["detail"]
    assert detail and "Traceback" not in detail


def test_upload_route_rejects_unsupported_extension_with_415():
    resp = _client().post("/upload", files={"file": ("photo.png", b"\x89PNG\r\n\x1a\n", "image/png")})
    assert resp.status_code == 415
