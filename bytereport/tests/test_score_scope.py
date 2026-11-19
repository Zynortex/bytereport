"""
The Health Score states its own scope.

A statement-based analysis cannot see receivables and payables, cash outside
the account, or accruals. Presenting a score without saying so made it read as
an audit verdict. The copy lives in ONE file, repo-root report-copy.json, read
by the PDF and imported by the web — not two hand-kept copies.
"""

import io
import json
import os
import re

import pytest

from app.services import report_copy as rc
from app.services.report_copy import score_copy

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
COPY_FILE = os.path.join(REPO_ROOT, "report-copy.json")
FRONT = os.path.join(REPO_ROOT, "bytereport-frontend", "src")

LANGS = ("ru", "uz", "en")
KEYS = ("caption", "scope", "scope_title")


def _file() -> dict:
    return json.load(io.open(COPY_FILE, encoding="utf-8"))


# ── One source ──────────────────────────────────────────────────────────────

def test_the_shared_file_exists_and_is_what_python_reads():
    assert os.path.isfile(COPY_FILE)
    assert rc.COPY["score"]["scope"]["ru"] == _file()["score"]["scope"]["ru"]


def test_the_fallback_mirrors_the_file():
    """If the file is unreadable in production the words must not change."""
    for key in KEYS:
        for lang in LANGS:
            assert rc._FALLBACK["score"][key][lang] == _file()["score"][key][lang], (key, lang)


def test_the_web_imports_the_same_file_rather_than_copying_it():
    i18n = io.open(os.path.join(FRONT, "i18n.ts"), encoding="utf-8").read()
    assert 'from "../../report-copy.json"' in i18n
    # And the locale files carry NO copy of it — that would be the second
    # source this design exists to avoid.
    for lang in LANGS:
        locale = json.load(io.open(os.path.join(FRONT, "locales", f"{lang}.json"), encoding="utf-8"))
        assert "score" not in locale, f"{lang}.json duplicates the shared score copy"


# ── Every language, every line ──────────────────────────────────────────────

@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("key", KEYS)
def test_every_line_exists_in_every_language(lang, key):
    text = score_copy(key, lang)
    assert text and len(text) > 8, f"{key}/{lang} is empty"


@pytest.mark.parametrize("lang", LANGS)
def test_the_three_languages_are_actually_different(lang):
    others = [score_copy("scope", o) for o in LANGS if o != lang]
    assert score_copy("scope", lang) not in others


def test_an_unknown_language_falls_back_to_russian_never_to_nothing():
    assert score_copy("scope", "de") == score_copy("scope", "ru")
    assert score_copy("nonexistent-key", "ru") == ""


# ── What the copy says ──────────────────────────────────────────────────────

@pytest.mark.parametrize("lang,needles", [
    ("ru", ["дебитор", "кредитор", "наличн", "обязательств"]),
    ("uz", ["дебитор", "кредитор", "нақд", "мажбурият"]),
    ("en", ["receivable", "payable", "cash", "obligation"]),
])
def test_the_scope_names_the_three_blind_spots(lang, needles):
    """
    The point is specificity. "Not a substitute for bookkeeping" alone is a
    disclaimer; naming receivables, cash outside the account and future
    obligations is a description of coverage.
    """
    text = score_copy("scope", lang).lower()
    for n in needles:
        assert n in text, f"{lang}: scope does not mention {n!r}"


@pytest.mark.parametrize("lang", LANGS)
def test_the_scope_does_not_apologise(lang):
    """Coverage, not weakness. No 'unfortunately', no 'only', no 'sorry'."""
    text = score_copy("scope", lang).lower()
    banned = {
        "ru": ["к сожалению", "всего лишь", "извин", "лишь"],
        "uz": ["афсуски", "кечир", "фақатгина"],
        "en": ["unfortunately", "sorry", "merely", "just a"],
    }[lang]
    for b in banned:
        assert b not in text, f"{lang}: {b!r} reads as an apology"


@pytest.mark.parametrize("lang", LANGS)
def test_the_caption_is_one_short_line(lang):
    """It sits directly under the number; a paragraph there would bury it."""
    assert len(score_copy("caption", lang)) <= 70


# ── Where it renders ────────────────────────────────────────────────────────

def test_the_pdf_puts_both_lines_in_the_score_block():
    import inspect

    from app.services import pdf_generator as pg

    src = inspect.getsource(pg._build_health_score)
    assert 'score_copy("caption"' in src
    assert 'score_copy("scope"' in src


def test_the_web_card_puts_both_lines_in_the_score_card():
    card = io.open(os.path.join(FRONT, "components", "report", "HealthScoreCard.tsx"),
                   encoding="utf-8").read()
    assert 't("score.caption")' in card
    assert 't("score.scope")' in card


@pytest.mark.parametrize("lang", LANGS)
def test_a_generated_pdf_carries_the_scope_next_to_the_score(lang):
    """Rendered, not just wired: the words must survive layout and fonts."""
    import pdfplumber

    from app.models.report import AIReport
    from app.services.pdf_generator import generate_pdf

    payload = {
        "executive_summary": "ok",
        "financial_health_score": {"score": 35, "status": "critical", "reasoning": "ok"},
        "key_insights": [], "top_risks": [], "growth_opportunities": [],
        "expense_analysis": {"problem_categories": [], "efficient_categories": [], "notes": "ok"},
        "anomalies": [],
        "cash_flow_analysis": {"status": "ok", "summary": "ok", "warning_level": "low"},
        "forecast": {"outlook": "ok", "confidence": "low", "summary": "ok"},
        "priority_actions": [],
    }
    data = generate_pdf(report=AIReport.model_validate(payload), language=lang)
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        first_page = pdf.pages[0].extract_text() or ""

    def squash(s: str) -> str:
        return re.sub(r"\s+", " ", s)

    # On the FIRST page, with the score — not in a footer somewhere later.
    assert squash(score_copy("caption", lang)) in squash(first_page)
    # The scope wraps across lines in a narrow column; check its opening clause.
    opening = squash(score_copy("scope", lang))[:40]
    assert opening in squash(first_page), f"{lang}: scope not on the score page"
