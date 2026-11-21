"""
Voice / free-text note -> draft -> Excel.

The load-bearing rule of this feature is that a human sees the rows before
anything is generated, so several tests here pin the SHAPE of the API rather
than a behaviour: the preview step is enforceable only because no endpoint
accepts raw text and returns a file.
"""

import io
import os
from datetime import date

import openpyxl
import pytest
from pydantic import ValidationError

from app.models.voice_note import (
    MIN_RECORDS_FOR_ANALYSIS,
    DraftTransaction,
    ExcelRequest,
    ParseNoteResponse,
)
from app.services import voice_parser as vp
from app.services.excel_generator import LABELS, generate_excel
from app.services.transcription import suffix_for

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))

TODAY = date(2026, 8, 25)


def _rows() -> list[DraftTransaction]:
    return [
        DraftTransaction(
            date="2026-08-20", amount=500_000, direction="income",
            description="Диван Азизу", category="Продажи",
        ),
        DraftTransaction(
            date=None, amount=80_000, direction="expense",
            description="Доставка материалов", category="Логистика",
            uncertain=["date", "category"],
            notes={"date": "дата не названа", "category": "категория предположена"},
        ),
    ]


def _sheet(**kwargs):
    data = generate_excel(_rows(), today=TODAY, **kwargs)
    return openpyxl.load_workbook(io.BytesIO(data)), data


# ── The draft model ─────────────────────────────────────────────────────────

def test_direction_carries_the_sign_not_the_amount():
    """A negative amount plus direction='expense' would subtract twice."""
    row = DraftTransaction(amount=-80_000, direction="expense")
    assert row.amount == 80_000


def test_missing_fields_are_allowed():
    """A note may simply not say when, or how much — that is what flags are for."""
    row = DraftTransaction(direction="income", uncertain=["date", "amount"])
    assert row.date is None and row.amount is None


def test_unresolved_date_fragment_survives_as_text():
    """
    'прошлая среда' must reach the preview intact. Typing it as `date` would
    force the parser to either resolve it or throw it away.
    """
    row = DraftTransaction(date="прошлая среда", direction="expense")
    assert row.date == "прошлая среда"


def test_uncertain_is_deduped():
    row = DraftTransaction(direction="income", uncertain=["date", "date", "amount"])
    assert row.uncertain == ["date", "amount"]


def test_uncertain_rejects_a_field_that_does_not_exist():
    """The frontend renders a hint per known field; an invented name renders nowhere."""
    with pytest.raises(ValidationError):
        DraftTransaction(direction="income", uncertain=["vibes"])


# ── The preview cannot be skipped ───────────────────────────────────────────

def test_excel_request_takes_rows_not_text():
    """
    The API shape IS the guarantee. If ExcelRequest ever grows a `text` field,
    the preview becomes optional and this feature loses its point.
    """
    fields = set(ExcelRequest.model_fields)
    assert "transactions" in fields
    assert not fields & {"text", "note", "audio", "transcript"}


def test_no_route_goes_from_an_input_straight_to_a_file():
    """
    Every input mode produces a draft; only /excel makes a file, and it takes
    rows. Adding an input must not add a shortcut past the preview.
    """
    from app.api.routes import voice

    paths = {r.path for r in voice.router.routes}
    assert paths == {"/voice/transcribe", "/voice/parse", "/voice/photo", "/voice/excel"}


def test_parse_response_does_not_offer_analysis_this_iteration():
    """A single note cannot support a Health Score; the response must say so."""
    res = ParseNoteResponse(transactions=[])
    assert res.analysis_available is False
    assert res.records_needed == MIN_RECORDS_FOR_ANALYSIS


# ── Note-level guards ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_empty_note_is_rejected_before_any_api_call():
    with pytest.raises(ValueError):
        await vp.parse_note("   ")


@pytest.mark.asyncio
async def test_oversized_note_is_rejected_before_any_api_call():
    with pytest.raises(ValueError):
        await vp.parse_note("а" * (vp.MAX_NOTE_CHARS + 1))


def test_one_malformed_row_does_not_lose_the_others():
    """Re-recording a whole note because of one bad row would be unacceptable."""
    rows, warnings = vp._coerce_rows({
        "transactions": [
            {"direction": "income", "amount": 100, "description": "ok"},
            {"direction": "sideways", "amount": 5},          # invalid literal
            "not a dict",                                    # not an object
            {"direction": "expense", "amount": 50, "description": "also ok"},
        ],
        "warnings": ["дата не названа"],
    })
    assert len(rows) == 2
    assert [r.description for r in rows] == ["ok", "also ok"]
    assert len(warnings) == 3   # the original one, plus one per dropped row


def test_response_without_a_transactions_list_becomes_a_warning():
    rows, warnings = vp._coerce_rows({"result": "нет операций"})
    assert rows == []
    assert warnings


def test_prompt_forbids_substituting_today_for_a_missing_date():
    """
    The one prompt rule most likely to be softened by accident. Silently
    stamping today's date onto an undated row makes the flag disappear and the
    row look trustworthy.
    """
    assert "do NOT quietly substitute today" in vp.SYSTEM_PROMPT


def test_prompt_splits_compound_notes_into_separate_rows():
    assert "TWO rows, not one net row" in vp.SYSTEM_PROMPT


# ── Transcription input handling ────────────────────────────────────────────

@pytest.mark.parametrize("mime,expected", [
    ("audio/webm;codecs=opus", "webm"),   # Chrome
    ("audio/mp4", "mp4"),                 # Safari
    ("audio/ogg", "ogg"),
    ("audio/wav", "wav"),
])
def test_container_is_read_from_the_mime_type(mime, expected):
    assert suffix_for(mime, None) == expected


def test_container_falls_back_to_the_filename():
    assert suffix_for(None, "note.mp3") == "mp3"


def test_unknown_input_falls_back_to_what_the_recorder_produces():
    assert suffix_for("application/octet-stream", None) == "webm"


# ── The workbook ────────────────────────────────────────────────────────────

def test_workbook_is_a_real_xlsx():
    _, data = _sheet()
    assert data[:4] == b"PK\x03\x04"


def test_totals_are_formulas_not_baked_numbers():
    """
    The user will edit amounts in Excel after downloading. Frozen totals would
    quietly disagree with the rows above them.
    """
    wb, _ = _sheet()
    ws = wb.active
    formulas = [
        c.value for row in ws.iter_rows() for c in row
        if isinstance(c.value, str) and c.value.startswith("=")
    ]
    assert any(f.startswith("=SUM(D") for f in formulas)
    assert any(f.startswith("=SUM(E") for f in formulas)
    assert any("-E" in f for f in formulas), "net result is not derived from the totals"


def test_income_and_expense_land_in_separate_columns():
    wb, _ = _sheet()
    ws = wb.active
    income_row = [c.value for c in ws[5]]
    expense_row = [c.value for c in ws[6]]
    assert income_row[3] == 500_000 and income_row[4] is None
    assert expense_row[4] == 80_000 and expense_row[3] is None


def test_uncertainty_survives_into_the_file():
    """
    A flag that exists only in a preview the user closed is a flag they cannot
    act on a week later.
    """
    wb, _ = _sheet()
    check = wb.active.cell(row=6, column=6).value
    assert check and "дата не названа" in check and "категория предположена" in check


def test_a_confident_row_has_an_empty_check_column():
    wb, _ = _sheet()
    assert not wb.active.cell(row=5, column=6).value


def test_missing_date_keeps_what_the_note_said():
    wb, _ = _sheet()
    assert wb.active.cell(row=6, column=1).value == LABELS["ru"]["no_date"]


def test_unresolved_date_fragment_is_written_verbatim():
    data = generate_excel(
        [DraftTransaction(date="прошлая среда", amount=1, direction="expense")],
        today=TODAY,
    )
    ws = openpyxl.load_workbook(io.BytesIO(data)).active
    assert ws.cell(row=5, column=1).value == "прошлая среда"


def test_negative_net_is_the_only_semantic_colour():
    wb, _ = _sheet()
    ws = wb.active
    net = [
        c for row in ws.iter_rows() for c in row
        if isinstance(c.value, str) and c.value.startswith("=D") and "-E" in c.value
    ][0]
    assert "[RED]" in net.number_format


def test_empty_row_list_does_not_produce_a_broken_sum():
    """SUM over an empty range is a #REF!, which corrupts the whole sheet."""
    data = generate_excel([], today=TODAY)
    ws = openpyxl.load_workbook(io.BytesIO(data)).active
    formulas = [
        c.value for row in ws.iter_rows() for c in row
        if isinstance(c.value, str) and c.value.startswith("=SUM")
    ]
    assert formulas == []


@pytest.mark.parametrize("lang", ["ru", "uz", "en"])
def test_workbook_is_localised(lang):
    data = generate_excel(_rows(), currency="UZS", language=lang, today=TODAY)
    ws = openpyxl.load_workbook(io.BytesIO(data)).active
    assert ws.title == LABELS[lang]["sheet"]
    assert ws.cell(row=4, column=1).value == LABELS[lang]["col_date"]


@pytest.mark.parametrize("lang", ["ru", "uz", "en"])
def test_footnote_states_the_limitation_in_every_language(lang):
    data = generate_excel(_rows(), language=lang, today=TODAY)
    ws = openpyxl.load_workbook(io.BytesIO(data)).active
    text = " ".join(
        str(c.value) for row in ws.iter_rows() for c in row if isinstance(c.value, str)
    )
    assert str(MIN_RECORDS_FOR_ANALYSIS) in text
    assert "Health Score" in text


def test_business_name_becomes_the_title():
    data = generate_excel(_rows(), business_name="Мастерская «Контур»", today=TODAY)
    ws = openpyxl.load_workbook(io.BytesIO(data)).active
    assert ws.cell(row=1, column=1).value == "Мастерская «Контур»"


def test_workbook_colours_come_from_the_shared_token_file():
    """The sheet is paper: the header takes the PRINT accent (the web cyan is
    near-invisible on white)."""
    from app.services.design_tokens import PRINT_ACCENT

    wb, _ = _sheet()
    header_fill = wb.active.cell(row=4, column=1).fill.fgColor.rgb
    assert PRINT_ACCENT.lstrip("#").upper() in header_fill


# ── The "assumed today" guard ───────────────────────────────────────────────
#
# Verified against the live API: with rule 4 alone, and again after adding a
# worked example to the prompt, the model still stamped today's date onto a row
# whose text carried no date, and left it unflagged. The guard makes the
# invariant enforceable instead of requested.

def test_a_date_equal_to_today_is_flagged_when_the_model_did_not():
    rows, _ = vp._coerce_rows(
        {"transactions": [
            {"date": TODAY.isoformat(), "amount": 500_000, "direction": "income",
             "description": "от Азиза за диван"},
        ]},
        today=TODAY,
    )
    assert rows[0].uncertain == ["date"]
    assert rows[0].notes["date"] == vp._TODAY_GUARD_NOTE["ru"]


def test_the_guard_does_not_overwrite_the_models_own_reason():
    rows, _ = vp._coerce_rows(
        {"transactions": [
            {"date": TODAY.isoformat(), "direction": "income",
             "uncertain": ["date"], "notes": {"date": "«сегодня утром» — уточните"}},
        ]},
        today=TODAY,
    )
    assert rows[0].uncertain == ["date"]                       # not duplicated
    assert rows[0].notes["date"] == "«сегодня утром» — уточните"


def test_any_other_date_is_left_alone():
    """The guard keys on today specifically — it must not flag every date."""
    rows, _ = vp._coerce_rows(
        {"transactions": [
            {"date": "2026-08-19", "amount": 300_000, "direction": "expense"},
        ]},
        today=TODAY,
    )
    assert rows[0].uncertain == []


def test_a_null_date_is_left_to_the_models_own_flag():
    rows, _ = vp._coerce_rows(
        {"transactions": [{"date": None, "direction": "income", "uncertain": ["date"]}]},
        today=TODAY,
    )
    assert rows[0].uncertain == ["date"]


@pytest.mark.parametrize("lang", ["ru", "uz", "en"])
def test_the_guard_note_is_localised(lang):
    rows, _ = vp._coerce_rows(
        {"transactions": [{"date": TODAY.isoformat(), "direction": "income"}]},
        today=TODAY, language=lang,
    )
    assert rows[0].notes["date"] == vp._TODAY_GUARD_NOTE[lang]


# ── Colours must be OPAQUE ──────────────────────────────────────────────────
#
# OOXML colours are ARGB. openpyxl pads a bare six-digit RGB to eight with a
# leading ZERO byte, so every fill, font and border in this workbook was
# written as alpha 00. Excel paints them anyway; LibreOffice, Google Sheets and
# preview renderers do not — the header rendered as white bold text on white
# paper and the hairline borders disappeared entirely.

def _applied_colours(ws):
    """Every colour this generator actually put on a cell."""
    out: list[tuple[str, str]] = []
    for row in ws.iter_rows():
        for c in row:
            if c.fill is not None and c.fill.patternType:
                rgb = getattr(c.fill.fgColor, "rgb", None)
                if isinstance(rgb, str):
                    out.append((f"{c.coordinate} fill", rgb))
            if c.font is not None and c.font.color is not None:
                rgb = getattr(c.font.color, "rgb", None)
                if isinstance(rgb, str):
                    out.append((f"{c.coordinate} font", rgb))
            for side_name in ("left", "right", "top", "bottom"):
                side = getattr(c.border, side_name, None)
                if side is not None and side.style:
                    rgb = getattr(side.color, "rgb", None) if side.color else None
                    if isinstance(rgb, str):
                        out.append((f"{c.coordinate} {side_name}", rgb))
    return out


def test_every_colour_in_the_workbook_is_opaque():
    wb, _ = _sheet()
    transparent = [(w, rgb) for w, rgb in _applied_colours(wb.active) if rgb[:2].upper() == "00"]
    assert not transparent, f"alpha-00 (invisible) colours: {transparent[:6]}"


def test_the_header_is_not_white_on_white():
    """The reported symptom, pinned directly."""
    wb, _ = _sheet()
    head = wb.active.cell(row=4, column=1)
    assert head.fill.patternType == "solid"
    assert head.fill.fgColor.rgb.upper() != head.font.color.rgb.upper()
    # And the fill must be dark enough for white text to read on it.
    r, g, b = (int(head.fill.fgColor.rgb[i:i + 2], 16) for i in (2, 4, 6))
    assert max(r, g, b) < 0xA0, "header fill is too light for white text"


def test_hairline_borders_are_drawn_on_data_cells():
    wb, _ = _sheet()
    cell = wb.active.cell(row=5, column=2)
    assert cell.border.left.style == "thin"
    assert cell.border.left.color.rgb[:2].upper() == "FF"


def test_the_totals_row_is_weighted_more_than_the_data_rows():
    wb, _ = _sheet()
    total = [
        c for row in wb.active.iter_rows() for c in row
        if isinstance(c.value, str) and c.value.startswith("=SUM")
    ][0]
    assert total.border.top.style == "medium"
    assert total.font.bold


def test_real_dates_carry_a_date_format_and_placeholders_do_not():
    wb, _ = _sheet()
    ws = wb.active
    assert ws.cell(row=5, column=1).number_format == "DD.MM.YYYY"
    # The "не указана" placeholder is text; a date format on it would be a lie.
    assert ws.cell(row=6, column=1).number_format == "General"


def test_money_columns_carry_a_thousands_separator():
    wb, _ = _sheet()
    ws = wb.active
    assert ws.cell(row=5, column=4).number_format == "#,##0"
    assert ws.cell(row=5, column=5).number_format == "#,##0"


# ── Photo as a third input ──────────────────────────────────────────────────
#
# The photo path is a third SOURCE, not a third pipeline. Everything after the
# model call — the assumed-today guard, the currency conversion, the preview,
# the workbook — has to be the same code, or the two paths drift apart in ways
# nobody notices until a user compares two drafts.

# Byte literals built numerically: an escape-heavy source file is the one thing
# that has repeatedly gone wrong in this repo's tooling.
JPEG_MAGIC = bytes([0xFF, 0xD8, 0xFF, 0xE0])
PNG_MAGIC = bytes([0x89]) + b"PNG" + bytes([0x0D, 0x0A, 0x1A, 0x0A])
WEBP_MAGIC = b"RIFF" + bytes(4) + b"WEBP"
WAVE_MAGIC = b"RIFF" + bytes(4) + b"WAVE"


def test_photo_and_text_share_the_same_finalisation():
    import inspect

    from app.services import photo_parser as pp

    assert "finalize(" in inspect.getsource(pp.parse_photo)


def test_photo_shares_the_base_prompt():
    from app.services import photo_parser as pp

    assert pp.SYSTEM_PROMPT is vp.SYSTEM_PROMPT
    assert "THIS INPUT IS A PHOTOGRAPH" in pp.PHOTO_INSTRUCTIONS


def test_photo_prompt_forbids_double_counting_a_receipt():
    """A total plus every line item is the same money recorded twice."""
    from app.services import photo_parser as pp

    assert "do not also add every line item" in pp.PHOTO_INSTRUCTIONS


def test_photo_prompt_forbids_inventing_rows_from_an_unreadable_image():
    from app.services import photo_parser as pp

    assert "do not invent rows" in pp.PHOTO_INSTRUCTIONS


@pytest.mark.parametrize("data,expected", [
    (JPEG_MAGIC + b"0" * 20, "jpeg"),
    (PNG_MAGIC + b"0" * 20, "png"),
    (WEBP_MAGIC + b"0" * 8, "webp"),
])
def test_image_type_comes_from_the_bytes_not_the_header(data, expected):
    """A browser labels anything image/jpeg; the model rejects a mislabel."""
    from app.services.photo_parser import detect_image_type

    assert detect_image_type(data, "image/jpeg") == expected


def test_riff_that_is_not_webp_is_not_accepted_as_one():
    from app.services.photo_parser import detect_image_type

    assert detect_image_type(WAVE_MAGIC + b"0" * 8, None) is None


def test_a_non_image_is_rejected():
    from app.services.photo_parser import detect_image_type

    assert detect_image_type(b"%PDF-1.7", None) is None


def test_a_declared_content_type_cannot_override_the_bytes():
    """
    A PDF labelled image/jpeg used to reach the vision API and come back as a
    400 — a paid round trip to learn what the first four bytes already said.
    """
    from app.services.photo_parser import detect_image_type

    assert detect_image_type(b"%PDF-1.7", "image/jpeg") is None
    assert detect_image_type(b"unknown", "image/png") is None


@pytest.mark.asyncio
async def test_an_empty_image_is_rejected_before_any_api_call():
    from app.services.photo_parser import parse_photo

    with pytest.raises(ValueError):
        await parse_photo(b"")


@pytest.mark.asyncio
async def test_an_oversized_image_is_rejected_before_any_api_call():
    from app.services.photo_parser import MAX_IMAGE_BYTES, parse_photo

    with pytest.raises(ValueError):
        await parse_photo(JPEG_MAGIC + b"0" * MAX_IMAGE_BYTES)


@pytest.mark.asyncio
async def test_a_file_that_is_not_an_image_is_rejected_before_any_api_call():
    from app.services.photo_parser import parse_photo

    with pytest.raises(ValueError):
        await parse_photo(b"%PDF-1.7" + b"0" * 100, content_type="image/jpeg")


# ── date_source: evidence, not decoration ───────────────────────────────────
#
# The bare "equals today" heuristic fired on nearly every photographed receipt,
# because a same-day receipt's printed date IS today. A flag that cries wolf on
# the common case gets dismissed on the rare one it was built for. So the model
# now has to positively claim it read a date; a missing or "assumed" claim
# leaves the heuristic in charge.

def test_a_stated_date_equal_to_today_is_not_flagged():
    """A receipt printed today is a date the model read, not one it invented."""
    rows, _ = vp._coerce_rows(
        {"transactions": [{
            "date": TODAY.isoformat(), "date_source": "stated",
            "amount": 1_980_000, "direction": "expense", "description": "чек",
        }]},
        today=TODAY,
    )
    assert rows[0].uncertain == []


def test_a_relative_date_that_lands_on_today_is_not_flagged():
    rows, _ = vp._coerce_rows(
        {"transactions": [{
            "date": TODAY.isoformat(), "date_source": "relative",
            "direction": "income",
        }]},
        today=TODAY,
    )
    assert rows[0].uncertain == []


def test_an_assumed_date_equal_to_today_is_still_flagged():
    rows, _ = vp._coerce_rows(
        {"transactions": [{
            "date": TODAY.isoformat(), "date_source": "assumed", "direction": "income",
        }]},
        today=TODAY,
    )
    assert rows[0].uncertain == ["date"]


def test_a_missing_claim_leaves_the_heuristic_in_charge():
    """
    Silence is not evidence. The original failure was the model saying nothing
    and defaulting to today, which is exactly this case.
    """
    rows, _ = vp._coerce_rows(
        {"transactions": [{"date": TODAY.isoformat(), "direction": "income"}]},
        today=TODAY,
    )
    assert rows[0].uncertain == ["date"]


def test_an_invented_date_source_is_rejected():
    with pytest.raises(ValidationError):
        DraftTransaction(direction="income", date_source="vibes")


def test_the_prompt_asks_for_the_provenance_and_says_it_is_checked():
    assert "date_source" in vp.SYSTEM_PROMPT
    # The rule that matters: an inferred date must not be reported as read.
    assert "for a date you inferred" in vp.SYSTEM_PROMPT


# ── The recorder contract ───────────────────────────────────────────────────
#
# useRecorder is browser-only and this project has no JS test runner, so these
# read the source the way test_design_tokens.py reads index.css. Both guard a
# failure that produced NO error and NO visible symptom, which is exactly the
# kind that comes back.

import os as _os

RECORDER_TS = _os.path.join(
    REPO_ROOT, "bytereport-frontend", "src", "lib", "useRecorder.ts"
)
VOICE_PAGE_TSX = _os.path.join(
    REPO_ROOT, "bytereport-frontend", "src", "pages", "VoiceNote.tsx"
)


def _recorder_src() -> str:
    return io.open(RECORDER_TS, encoding="utf-8").read()


def test_stop_hands_the_recording_back_through_its_promise():
    """
    The original bug: stop() returned void and the caller polled `recorder.blob`
    on an interval. That callback closes over the blob from the render that
    created it, and React state is immutable per render — so the poll re-read
    the same stale null until it timed out and gave up in silence. Recording
    never once produced a request.
    """
    src = _recorder_src()
    assert "Promise<Take>" in src, "stop() must resolve with the take"
    assert "resolveRef" in src, "the resolver must be held in a ref, not in state"

    page = io.open(VOICE_PAGE_TSX, encoding="utf-8").read()
    assert "await recorder.stop()" in page
    # No polling loop waiting for a state value to appear.
    assert "recorder.blob" not in page, "the caller is reading the blob off state again"
    assert "setInterval" not in page


def test_the_silence_gate_fires_only_on_a_real_measurement():
    """
    An analyser can produce nothing at all — verified in headless Chrome, where
    one fed by a synthetic MediaStream reads zero forever. A peak of 0 from an
    analyser that never ran looks exactly like silence, and would refuse every
    take the user ever made. Unmeasured must read as loud, not as silent.
    """
    src = _recorder_src()
    assert "meterTicksRef" in src
    assert "meterTicksRef.current > 0 ? peakRef.current : Number.POSITIVE_INFINITY" in src


def test_the_silence_threshold_sits_between_noise_and_speech():
    """
    Measured on real hardware: an idle microphone peaks near 0.009, speech near
    0.52. The threshold has to sit inside that gap, nearer the noise end —
    refusing a take the user actually spoke breaks the feature, while accepting
    a quiet one only produces text they can see and delete.
    """
    import re

    src = _recorder_src()
    m = re.search(r"export const SILENCE_PEAK = ([\d.]+);", src)
    assert m, "SILENCE_PEAK is gone"
    threshold = float(m.group(1))
    measured_noise_floor = 0.009
    measured_speech_peak = 0.52
    assert threshold > measured_noise_floor, "would accept an idle microphone"
    assert threshold < measured_speech_peak / 5, "too close to speech; would refuse a quiet speaker"


def test_the_microphone_is_released_on_every_exit():
    """A live MediaStream keeps the browser's recording indicator lit."""
    src = _recorder_src()
    assert src.count("releaseStream()") >= 3   # stop, error, unmount
    assert "getTracks().forEach((t) => t.stop())" in src
