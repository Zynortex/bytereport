"""
The support contact is one constant, used everywhere.

The pricing page and the dashboard both linked to t.me/mindset_materials_bot —
a different project. Every contact control now reads src/lib/support.ts, and
while that constant is empty the controls are hidden, not pointed elsewhere.
"""

import pathlib
import re

WEB = pathlib.Path(__file__).resolve().parents[2] / "bytereport-frontend" / "src"
SUPPORT = WEB / "lib" / "support.ts"


def _sources():
    for path in WEB.rglob("*"):
        if path.suffix in (".ts", ".tsx") and path.is_file():
            yield path, path.read_text(encoding="utf-8")


def test_the_unrelated_bot_is_gone():
    hits = [p.name for p, text in _sources() if "mindset_materials_bot" in text]
    assert not hits, hits


def test_no_page_hardcodes_a_telegram_link():
    hits = [str(p.relative_to(WEB)) for p, text in _sources()
            if p != SUPPORT and re.search(r"t\.me/", text)]
    assert not hits, f"use supportUrl from lib/support.ts instead: {hits}"


def test_every_contact_link_is_hidden_while_unset():
    for path, text in _sources():
        if path == SUPPORT:
            continue
        for match in re.finditer(r"href=\{support(Url)\}", text):
            before = text[max(0, match.start() - 400):match.start()]
            assert re.search(r"supportUrl\s*(&&|\?)", before), \
                f"{path.name}: link rendered without the guard"


# ── A2: no pricing links and no contact while sales are in person ───────────

def test_no_page_links_to_pricing():
    hits = []
    for path, text in _sources():
        if path.name in ("App.tsx", "Pricing.tsx", "useDocumentTitle.ts"):
            continue
        if re.search(r'''(to|href)=["'{]+/pricing''', text):
            hits.append(path.name)
    assert not hits, hits


def test_the_pricing_route_still_opens_by_direct_link():
    assert 'path="/pricing"' in (WEB / "App.tsx").read_text(encoding="utf-8")
    assert (WEB.parent.parent / "pricing.json").exists(), "the backend still reads its limits from it"


def test_the_contact_stays_empty_on_purpose():
    assert 'export const SUPPORT_TELEGRAM: string = "";' in SUPPORT.read_text(encoding="utf-8")
