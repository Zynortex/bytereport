"""
The pricing page states what the code does.

Before: ₽ and $ prices, "1 отчёт в месяц" (the backend gave 3 a day), a
"choose plan" button that implied an online payment that does not exist,
and not one call to t(). Now the numbers come from pricing.json — the file
the backend enforces — and every word is translated.
"""

import json
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
WEB = ROOT / "bytereport-frontend" / "src"
PAGE = (WEB / "pages" / "Pricing.tsx").read_text(encoding="utf-8")
LOCALES = {lang: json.loads((WEB / "locales" / f"{lang}.json").read_text(encoding="utf-8"))
           for lang in ("ru", "uz", "en")}


def _flat(d, prefix=""):
    for k, v in d.items():
        if isinstance(v, dict):
            yield from _flat(v, f"{prefix}{k}.")
        else:
            yield f"{prefix}{k}", v


def test_numbers_come_from_the_shared_file():
    lib = (WEB / "lib" / "pricing.ts").read_text(encoding="utf-8")
    assert 'from "../../../pricing.json"' in lib
    assert "PLANS" in PAGE
    for n in ("150000", "150 000", "450000", "450 000", "19"):
        assert not re.search(rf"\b{n}\b", PAGE), f"hardcoded number {n!r} on the page"


def test_no_rubles_dollars_or_untranslated_text():
    assert "₽" not in PAGE and "$" not in PAGE.replace("${", "")
    # No Cyrillic outside comments: every visible word goes through t().
    code = re.sub(r"/\*.*?\*/|//[^\n]*|\{/\*.*?\*/\}", "", PAGE, flags=re.S)
    assert not re.search(r"[А-Яа-яЁёЎўҚқҒғҲҳ]", code)
    assert PAGE.count("t(") >= 10


def test_paid_plans_do_not_pretend_to_take_payment():
    assert "/checkout" not in PAGE and not re.search(r"\bpayme\b|\bclick\.uz", PAGE, re.I)
    assert "early_access" in PAGE
    for lang, loc in LOCALES.items():
        note = loc["pricing"]["early_access_note"].lower()
        assert any(w in note for w in ("онлайн", "online")), lang


@pytest.mark.parametrize("lang", ["uz", "en"])
def test_every_language_has_the_same_keys(lang):
    def bases(loc):
        return {re.sub(r"_(one|few|many|other)$", "", k) for k, _ in _flat(loc["pricing"])}
    assert bases(LOCALES[lang]) == bases(LOCALES["ru"])


@pytest.mark.parametrize("lang", ["ru", "uz", "en"])
def test_every_plural_has_an_other_form(lang):
    keys = {k for k, _ in _flat(LOCALES[lang]["pricing"])}
    plural_bases = {re.sub(r"_(one|few|many|other)$", "", k) for k in keys
                    if re.search(r"_(one|few|many|other)$", k)}
    for base in plural_bases:
        assert f"{base}_other" in keys, f"{lang}: {base}_other missing"


def test_every_plan_is_named_in_every_language():
    plans = json.loads((ROOT / "pricing.json").read_text(encoding="utf-8"))["plans"]
    for lang, loc in LOCALES.items():
        for p in plans:
            assert loc["pricing"]["plan"][p["id"]]["name"], (lang, p["id"])


def test_notes_are_included_everywhere():
    for lang, loc in LOCALES.items():
        assert loc["pricing"]["included"]["notes"], lang
        assert loc["pricing"]["notes_free"], lang


def test_the_default_currency_is_the_som():
    store = (WEB / "store" / "reportStore.ts").read_text(encoding="utf-8")
    assert 'currency: "UZS" }' in store
    from app.models.report import AIReportRequest

    assert AIReportRequest(metrics={}).currency == "UZS"
    upload = (WEB / "pages" / "Upload.tsx").read_text(encoding="utf-8")
    assert '["UZS",' in upload, "the som is listed first"
