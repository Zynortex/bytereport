"""
The design language is defined once, in /design-tokens.json, and both the web
app and the PDF/Excel pipeline consume it. These tests pin that contract: a
colour may only change by editing the JSON, no framework default may creep
back in, the old violet palette is gone, and every text colour clears WCAG AA
on the ground it sits on.

The palette is ByteForge's: a dark navy ground, a cyan accent, a blue second
series and a coral for negatives. Paper (PDF, Excel) gets darker relatives of
the same colours, because the web cyan is near-invisible on white.
"""

import colorsys
import io
import json
import os
import pathlib
import re

import pytest

from app.services import chart_renderer as cr
from app.services import design_tokens as dt
from app.services import excel_generator as xg
from app.services import pdf_generator as pg

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
TOKENS_FILE = os.path.join(REPO_ROOT, "design-tokens.json")
WEB = pathlib.Path(REPO_ROOT) / "bytereport-frontend"
WEB_TOKENS_TS = os.path.join(REPO_ROOT, "bytereport-frontend", "src", "lib", "chartTokens.ts")
WEB_CSS = os.path.join(REPO_ROOT, "bytereport-frontend", "src", "index.css")

# The palette this replaced. None of it may survive anywhere.
OLD_PALETTE = ("#6B5482", "#9478B0", "#121016", "#0D0B11", "#241F2B", "#F1EEF3", "#736C7E",
               "#8C8494", "#2E2836", "#B3AAC0", "#5A4569", "#16121C", "#F7F6F8", "#7C3AED")


def _raw_tokens() -> dict:
    with io.open(TOKENS_FILE, encoding="utf-8") as f:
        return json.load(f)


def _rgb(colour: str) -> tuple[int, int, int]:
    if colour.startswith("#"):
        return tuple(int(colour[i:i + 2], 16) for i in (1, 3, 5))
    return tuple(int(float(v)) for v in re.findall(r"[\d.]+", colour)[:3])


def _luminance(colour: str) -> float:
    parts = [c / 255 for c in _rgb(colour)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in parts]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _hue_sat(colour: str) -> tuple[float, float]:
    r, g, b = (c / 255 for c in _rgb(colour))
    h, _l, s = colorsys.rgb_to_hls(r, g, b)
    return h * 360, s


def _is_violet(colour: str) -> bool:
    hue, sat = _hue_sat(colour)
    return sat > 0.15 and 250 <= hue <= 320


def _all_colours(node) -> list[str]:
    if isinstance(node, str):
        return [node] if re.match(r"#[0-9A-Fa-f]{6}$|rgba?\(", node) else []
    if isinstance(node, dict):
        return [c for k, v in node.items() if not k.startswith("_") for c in _all_colours(v)]
    if isinstance(node, list):
        return [c for v in node for c in _all_colours(v)]
    return []


# ── The file is the source ──────────────────────────────────────────────────

def test_tokens_file_exists_and_parses():
    assert os.path.isfile(TOKENS_FILE), "design-tokens.json is the shared source"
    _raw_tokens()


def test_python_reads_the_file_not_the_fallback():
    """If this fails the fallback copy silently diverged from the JSON."""
    raw = _raw_tokens()
    assert dt.RAMP == raw["charts"]["ramp"]
    assert dt.SERIES["revenue"] == raw["charts"]["series"]["revenue"]
    assert dt.CASH_GAP == raw["charts"]["cash_gap"]
    assert dt.ACCENT == raw["theme"]["accent"]
    assert dt.PRINT_ACCENT == raw["pdf"]["accent"]


def _strip_comments(node):
    if isinstance(node, dict):
        return {k: _strip_comments(v) for k, v in node.items() if not k.startswith("_")}
    return node


@pytest.mark.parametrize("group", ["theme", "charts", "severity", "zones", "pdf"])
def test_fallback_matches_the_file(group):
    """The baked-in copy is a deploy safety net — it must not drift, in any colour."""
    assert dt._FALLBACK[group] == _strip_comments(_raw_tokens()[group])


def test_web_imports_the_same_file():
    """The TS module must import the JSON, not re-declare hexes."""
    src = io.open(WEB_TOKENS_TS, encoding="utf-8").read()
    assert 'from "../../../design-tokens.json"' in src
    hexes = re.findall(r"#[0-9A-Fa-f]{6}", src)
    assert hexes == [], f"chartTokens.ts must not hardcode colours, found {hexes}"


# ── The palette: ByteForge navy and cyan, no violet ────────────────────────

def test_the_agreed_palette():
    t = _raw_tokens()["theme"]
    assert (t["bg_base"], t["bg_header"], t["surface"], t["surface_hover"]) == (
        "#04060B", "#070B14", "#0A101C", "#0E1524")
    assert (t["border_default"], t["border_strong"]) == (
        "rgb(148 172 205 / 0.11)", "rgb(148 172 205 / 0.20)")
    assert (t["text_primary"], t["text_secondary"], t["text_dim"]) == ("#E8EEF6", "#97A5B9", "#66758B")
    assert (t["accent"], t["accent_text"], t["accent_soft"], t["accent_ink"]) == (
        "#3DE6D6", "#3DE6D6", "#8FF3E9", "#04201D")
    assert t["negative"] == "#FF7A6B"
    assert _raw_tokens()["charts"]["series"]["revenue"] == "#5B9DFF"


def test_no_violet_left_in_the_tokens():
    for colour in _all_colours(_raw_tokens()):
        assert not _is_violet(colour), f"{colour} is violet"
        assert colour.upper() not in OLD_PALETTE


def _source_files():
    for p in (WEB / "src").rglob("*"):
        if p.suffix in (".ts", ".tsx", ".css") and p.is_file():
            yield p
    yield WEB / "index.html"
    yield from (WEB / "public").glob("*.svg")
    for p in (pathlib.Path(REPO_ROOT) / "bytereport" / "app").rglob("*.py"):
        yield p


def test_no_old_palette_value_survives_anywhere():
    for path in _source_files():
        text = path.read_text(encoding="utf-8").upper()
        for old in OLD_PALETTE:
            assert old not in text, f"{path.name} still carries {old}"
        assert "VIOLET" not in text and "PURPLE" not in text, f"{path.name} mentions violet/purple"


def _code(path: pathlib.Path) -> str:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"\{/\*.*?\*/\}", "", text, flags=re.S)
    return re.sub(r"(^|\s)//[^\n]*", r"\1", text)


def test_no_hardcoded_colour_in_the_components():
    """Every colour comes through a token: no hex, no rgb(), no framework palette class."""
    framework = re.compile(
        r"\b(?:bg|text|border|ring|fill|stroke|from|to|via|outline|decoration|divide|placeholder|caret)-"
        r"(?:white|black|gray|slate|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|"
        r"cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)\b")
    for path in (WEB / "src").rglob("*.tsx"):
        code = _code(path)
        assert not re.search(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b", code), f"{path.name}: hex colour"
        assert not re.search(r"\brgba?\(", code), f"{path.name}: rgb() colour"
        found = framework.findall(code)
        assert not found, f"{path.name}: framework colour {found}"


# ── The web theme mirrors the tokens, value for value ──────────────────────

def _theme_block() -> str:
    css = io.open(WEB_CSS, encoding="utf-8").read()
    start = css.index("@theme")
    depth, i = 0, css.index("{", start)
    for j in range(i, len(css)):
        if css[j] == "{":
            depth += 1
        elif css[j] == "}":
            depth -= 1
            if depth == 0:
                return css[i:j]
    raise AssertionError("unterminated @theme block")


def _css_colours() -> dict[str, str]:
    return {k: v.strip() for k, v in re.findall(r"--color-([a-z0-9-]+)\s*:\s*([^;]+);", _theme_block())}


def _expected_css() -> dict[str, str]:
    t, sev, z = _raw_tokens()["theme"], _raw_tokens()["severity"], _raw_tokens()["zones"]
    return {
        "ground": t["bg_base"], "header": t["bg_header"],
        "surface": t["surface"], "surface-hover": t["surface_hover"],
        "line": t["border_default"], "line-strong": t["border_strong"],
        "accent": t["accent"], "accent-fg": t["accent_text"], "accent-soft": t["accent_soft"],
        "accent-ink": t["accent_ink"], "ring": t["accent"],
        "fg": t["text_primary"], "fg-subtle": t["text_secondary"], "fg-muted": t["text_dim"],
        "negative": t["negative"],
        "brand-dark": t["text_primary"], "brand-border": t["border_default"],
        "brand-muted": t["text_secondary"], "brand-blue": t["accent"],
        "sev-high": sev["high"], "sev-medium": sev["medium"], "sev-low": sev["low"],
        "sev-high-fg": sev["high_fg"], "sev-medium-fg": sev["medium_fg"], "sev-low-fg": sev["low_fg"],
        "success": z["excellent"], "zone-stable": z["stable"],
        "warning": z["unstable"], "danger": z["critical"],
    }


def test_every_css_colour_is_the_token_value():
    assert _css_colours() == _expected_css()


def test_effects_and_static_files_carry_the_tokens():
    css = io.open(WEB_CSS, encoding="utf-8").read()
    fx, t = _raw_tokens()["effects"], _raw_tokens()["theme"]
    for var, key in (("--fx-glow", "glow"), ("--fx-glow-2", "glow_secondary"),
                     ("--fx-selection", "selection"), ("--fx-spotlight", "spotlight")):
        assert re.search(rf"{re.escape(var)}:\s*{re.escape(fx[key])};", css), var
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert f'<meta name="theme-color" content="{t["bg_header"]}" />' in html
    svg = (WEB / "public" / "favicon.svg").read_text(encoding="utf-8")
    assert set(re.findall(r"#[0-9A-Fa-f]{6}", svg)) == {t["bg_header"], t["accent"]}


def test_shadcn_variables_are_the_same_palette():
    css = io.open(WEB_CSS, encoding="utf-8").read()
    t = _raw_tokens()["theme"]

    def hsl(hex_):
        r, g, b = (c / 255 for c in _rgb(hex_))
        h, l, s = colorsys.rgb_to_hls(r, g, b)
        return f"{round(h * 360)} {round(s * 100)}% {round(l * 100)}%"

    for var, key in (("--background", "bg_base"), ("--foreground", "text_primary"),
                     ("--ring", "accent"), ("--primary", "accent"), ("--card", "surface")):
        assert re.search(rf"{var}:\s*{re.escape(hsl(t[key]))};", css), var


def test_selection_focus_and_scrollbar_use_the_tokens():
    css = io.open(WEB_CSS, encoding="utf-8").read()
    assert re.search(r"::selection\s*\{[^}]*var\(--fx-selection\)", css)
    assert re.search(r":focus-visible\s*\{[^}]*var\(--color-accent\)", css)
    assert re.search(r"::-webkit-scrollbar-thumb\s*\{[^}]*var\(--color-line-strong\)", css)


# ── Fills: the primary button and the cards, nothing else ──────────────────

def test_the_primary_button_is_filled_and_the_rest_are_strokes():
    src = (WEB / "src" / "components" / "ui" / "button.tsx").read_text(encoding="utf-8")
    block = src[src.index("variant: {"):src.index("size: {")]
    variants = dict(re.findall(r"^\s*(\w+):\s*\"([^\"]+)\",", block, re.M))
    assert "bg-accent" in variants["default"].split() and "text-accent-ink" in variants["default"].split()
    for name in ("outline", "secondary", "destructive", "danger"):
        assert "bg-transparent" in variants[name].split(), f"{name} must stay a stroke"


def test_cards_carry_the_surface_fill():
    src = (WEB / "src" / "components" / "ui" / "card.tsx").read_text(encoding="utf-8")
    assert "bg-surface" in src and "bg-transparent" not in src


def test_accent_fills_carry_dark_ink():
    """White on the cyan accent is unreadable (1.5:1); accent fills take accent-ink."""
    for path in (WEB / "src").rglob("*.tsx"):
        for cls in re.findall(r'"([^"]*\bbg-(?:accent|brand-blue)\b(?!/)[^"]*)"', _code(path)):
            assert "text-white" not in cls and "text-fg" not in cls.split(), f"{path.name}: {cls}"


# ── Contrast (WCAG AA, 4.5:1 for body text) ─────────────────────────────────

AA = 4.5


@pytest.mark.parametrize("text", ["text_primary", "text_secondary", "accent_text"])
@pytest.mark.parametrize("ground", ["bg_base", "surface", "surface_hover"])
def test_text_clears_aa_on_the_ground_and_on_a_card(text, ground):
    t = _raw_tokens()["theme"]
    assert _contrast(t[text], t[ground]) >= AA, (text, ground, round(_contrast(t[text], t[ground]), 2))


@pytest.mark.parametrize("fill", ["accent", "accent_soft"])
def test_the_primary_button_label_clears_aa(fill):
    t = _raw_tokens()["theme"]
    assert _contrast(t["accent_ink"], t[fill]) >= AA


def test_the_print_accent_clears_aa_on_white_both_ways():
    """As text on the page and under the white header text of a table."""
    p = _raw_tokens()["pdf"]
    assert _contrast(p["accent"], p["page_bg"]) >= AA
    assert _contrast(p["accent"], "#FFFFFF") >= AA
    # And the web accent really is unusable there - otherwise the split is pointless.
    assert _contrast(_raw_tokens()["theme"]["accent"], p["page_bg"]) < 3


@pytest.mark.parametrize("key", ["negative", "page_ink", "page_muted"])
def test_print_text_colours_clear_aa(key):
    p = _raw_tokens()["pdf"]
    assert _contrast(p[key], p["page_bg"]) >= AA


@pytest.mark.parametrize("group", ["severity", "zones"])
def test_print_risk_and_zone_colours_clear_aa_on_white(group):
    p = _raw_tokens()["pdf"]
    for key, colour in p[group].items():
        assert _contrast(colour, p["page_bg"]) >= AA, (group, key, colour)


def test_web_severity_labels_clear_aa():
    t, sev = _raw_tokens()["theme"], _raw_tokens()["severity"]
    for key in ("high_fg", "medium_fg", "low_fg"):
        for ground in ("bg_base", "surface"):
            assert _contrast(sev[key], t[ground]) >= AA, (key, ground)


# ── Ramp and categories ────────────────────────────────────────────────────

def test_ramp_is_exactly_the_agreed_eight():
    assert dt.RAMP == [
        "#1B2A40", "#22314A", "#2E4360", "#3E5578",
        "#527098", "#6D8CAE", "#8CA0BC", "#B7C4D6",
    ]


def test_ramp_runs_dark_to_light():
    values = [sum(_rgb(c)) for c in dt.RAMP]
    assert values == sorted(values), "ramp must go dark → light for descending shares"


def test_donut_uses_the_shared_category_palette():
    """Categorical slices use the hue-varied palette, not the ordinal ramp."""
    assert cr.DONUT_COLORS == dt.CATEGORY_COLORS
    assert dt.CATEGORY_COLORS == _raw_tokens()["charts"]["categories"]
    assert 6 <= len(dt.CATEGORY_COLORS) - 1 <= 8, "6-8 hues plus the neutral for 'Other'"


def test_category_palette_hues_are_distinguishable():
    """These must differ in HUE, not just lightness, and none may be violet."""
    hues = []
    for c in dt.CATEGORY_COLORS[:-1]:          # last slot is the neutral grey
        hue, sat = _hue_sat(c)
        assert sat > 0.10, f"{c} is too desaturated to read as its own hue"
        assert not _is_violet(c)
        hues.append(hue)
    hues.sort()
    gaps = [b - a for a, b in zip(hues, hues[1:])]
    assert min(gaps) > 15, f"two category hues are within {min(gaps):.0f}deg"


def test_category_colours_are_stable_by_name():
    """A category keeps its colour when shares reorder between reports."""
    first = dict(zip(["Материалы", "Зарплата", "Реклама"],
                     dt.assign_category_colors(["Материалы", "Зарплата", "Реклама"])))
    names = ["Реклама", "Материалы", "Зарплата"]
    second = dict(zip(names, dt.assign_category_colors(names)))
    for k in first:
        assert first[k] == second[k], f"{k} changed colour when the order changed"


def test_category_colours_survive_any_order_even_on_a_hash_collision():
    import itertools

    names = ["Материалы", "Зарплата", "Аренда цеха", "Логистика", "Инструмент", "Реклама"]
    reference = dict(zip(names, dt.assign_category_colors(names)))
    for perm in itertools.permutations(names):
        assert dict(zip(perm, dt.assign_category_colors(list(perm)))) == reference


def test_category_colours_are_distinct_within_one_chart():
    names = ["Материалы", "Зарплата", "Аренда цеха", "Логистика",
             "Инструмент", "Реклама", "Прочее"]
    assigned = dt.assign_category_colors(names)
    assert len(set(assigned)) == len(names)


def test_other_bucket_takes_the_reserved_neutral():
    neutral = dt.CATEGORY_COLORS[-1]
    for name in ("Прочее", "прочее", "Other", " Бошқа "):
        assert dt.assign_category_colors([name]) == [neutral]


def test_python_and_typescript_assign_colours_the_same_way():
    """Both surfaces must colour a category identically: same hash, same name order."""
    ts = io.open(WEB_TOKENS_TS, encoding="utf-8").read()
    assert "h * 31 + ch.codePointAt(0)" in ts, "TS hash diverged from the Python one"
    assert "% 4294967296" in ts
    assert "const order = names.map((_, i) => i).sort(" in ts, "TS no longer resolves collisions in name order"
    assert dt.category_color_index("a", 6) == (ord("a") % 6)
    assert dt.category_color_index("", 6) == 0


def test_ramp_carries_no_semantic_hue():
    """Categorical data must never imply risk."""
    banned = {"#DC2626", "#D97706", "#16A34A", "#65A30D", "#1D6FED"}
    assert not ({c.upper() for c in dt.RAMP} & banned)


# ── Series: main = accent, second = blue, negative = coral ─────────────────

def test_web_series():
    s, t = _raw_tokens()["charts"]["series"], _raw_tokens()["theme"]
    assert s["profit"] == t["accent"], "the main series is the accent"
    assert s["revenue"] == "#5B9DFF", "the second series is blue"
    assert _raw_tokens()["charts"]["cash_gap"] == t["negative"] == "#FF7A6B"


def test_print_series():
    """matplotlib draws on white: the main series and negatives take the print palette."""
    assert cr.C_PROFIT == dt.PRINT_ACCENT
    assert cr.C_CASH_GAP == dt.PRINT_NEGATIVE
    assert cr.C_REVENUE == dt.SERIES["revenue"]
    assert cr.C_EXPENSE == dt.SERIES["expenses"]


def test_expenses_series_is_not_red():
    r, g, b = _rgb(cr.C_EXPENSE)
    assert not (r > g + 60 and r > b + 60), "expenses must not read as a red alert"


def test_negative_is_coral_on_screen_and_brick_on_paper():
    web, paper = _rgb(_raw_tokens()["theme"]["negative"]), _rgb(dt.PRINT_NEGATIVE)
    for r, g, b in (web, paper):
        assert r > g and r > b, "negatives must read warm"
        assert g > 0x30 and b > 0x30, "a pure red has near-zero green/blue"


def test_no_stray_framework_defaults_left_in_chart_renderer():
    src = io.open(cr.__file__, encoding="utf-8").read()
    body = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
    for stale in ("#1D6FED", "#DC2626", "#16A34A", "#0F3D8C", "#4B8BF4", "#CFE0FD"):
        assert stale not in body, f"stale colour {stale} still in chart_renderer"
    assert not re.search(r"#[0-9A-Fa-f]{6}", body), "chart_renderer must take colours from the tokens"


# ── Paper: PDF and Excel ────────────────────────────────────────────────────

def _hex(colour) -> str:
    return "#" + colour.hexval()[2:].upper()


def test_pdf_takes_the_print_palette():
    p = _raw_tokens()["pdf"]
    assert _hex(pg.BRAND_BLUE) == p["accent"]
    assert _hex(pg.BRAND_DARK) == p["header_bg"] == "#070B14"
    assert _hex(pg.BRAND_LIGHT) == p["accent_tint"]
    assert (_hex(pg.SEV_HIGH), _hex(pg.SEV_MEDIUM), _hex(pg.SEV_LOW)) == (
        p["severity"]["high"], p["severity"]["medium"], p["severity"]["low"])


def test_pdf_and_excel_hardcode_no_colour():
    for mod in (pg, xg):
        src = io.open(mod.__file__, encoding="utf-8").read()
        code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
        code = re.sub(r'""".*?"""', "", code, flags=re.S)
        assert not re.search(r'HexColor\("#|_rgb\("#|"#[0-9A-Fa-f]{6}"', code), mod.__name__


def test_excel_header_is_the_print_accent():
    assert xg._HEADER_BG == "FF" + dt.PRINT_ACCENT[1:].upper()


# ── Severity ────────────────────────────────────────────────────────────────

def test_severity_is_separable():
    sev = [dt.SEVERITY["high"], dt.SEVERITY["medium"], dt.SEVERITY["low"]]
    assert len(set(sev)) == 3
    assert len(set(dt.PRINT_SEVERITY.values())) == 3


def test_severity_is_not_part_of_the_ramp():
    assert not ({c.upper() for c in dt.SEVERITY.values()} & {c.upper() for c in dt.RAMP})


# ── Radius, shadows, namespaces ─────────────────────────────────────────────

def test_radius_is_three_pixels_everywhere():
    css = io.open(WEB_CSS, encoding="utf-8").read()
    radii = re.findall(r"--radius-[a-z0-9]+:\s*([^;]+);", css)
    assert radii, "no radius tokens found"
    assert all(r.strip() == "3px" for r in radii), f"non-3px radius present: {radii}"


def test_cards_have_no_shadow():
    css = io.open(WEB_CSS, encoding="utf-8").read()
    assert re.search(r"--shadow-card:\s*none;", css)


@pytest.mark.parametrize("stale", ["#F4F7FC", "#DDE3EE", "#0F1B2D"])
def test_old_light_theme_values_are_gone_from_css(stale):
    css = io.open(WEB_CSS, encoding="utf-8").read()
    assert stale not in css, f"light-theme value {stale} still in index.css"


# Tailwind v4 derives utilities from the token PREFIX, so a name reused across
# two namespaces silently rewrites an existing utility. `--color-base` did
# exactly that: it turned `text-base` from a font size into
# `color: var(--color-base)`, and every element carrying that very common class
# painted its text in the app ground.
_FONT_SIZE_NAMES = {
    "xs", "sm", "base", "lg", "xl",
    "2xl", "3xl", "4xl", "5xl", "6xl", "7xl", "8xl", "9xl",
}


def test_no_colour_token_shadows_a_font_size():
    clash = set(_css_colours()) & _FONT_SIZE_NAMES
    assert not clash, (
        f"--color-{{{','.join(sorted(clash))}}} rewrites text-<name> from a font "
        "size into a colour; rename the token"
    )


def test_the_ground_token_is_not_named_base():
    block = _theme_block()
    assert "--color-ground:" in block, "the app ground token was renamed again"
    assert "--color-base:" not in block


def test_no_component_points_at_a_colour_variable_that_does_not_exist():
    """PulseLine's peak dot stroked `var(--color-base)`, removed long ago: no ring drawn."""
    declared = set(_css_colours())
    for path in (WEB / "src").rglob("*.tsx"):
        for name in re.findall(r"var\(--color-([a-z0-9-]+)\)", path.read_text(encoding="utf-8")):
            assert name in declared, f"{path.name}: var(--color-{name}) is not a token"


# ── Motion stays inside the design language ─────────────────────────────────

def _keyframe_css() -> str:
    css = io.open(WEB_CSS, encoding="utf-8").read()
    return " ".join(re.findall(r"@keyframes[^{]+\{(?:[^{}]|\{[^{}]*\})*\}", css))


def test_no_animation_overshoots_its_resting_state():
    """A value may approach 1 but never pass it and come back: 0.97 -> 1 arrives."""
    scales = [float(v) for v in re.findall(r"scale\(([\d.]+)\)", _keyframe_css())]
    assert scales, "no scaled keyframes — update this test if that is deliberate"
    assert max(scales) <= 1.0, f"a keyframe scales past its resting size: {scales}"
    assert min(scales) >= 0.9, f"a keyframe shrinks far enough to read as a pop: {scales}"


def test_no_springy_easing():
    """cubic-bezier with a y outside [0,1] is how overshoot sneaks back in."""
    css = io.open(WEB_CSS, encoding="utf-8").read()
    assert "cubic-bezier" not in css, "hand-rolled easing — ease-out is the house curve"


def test_every_animation_is_disabled_under_reduced_motion():
    css = io.open(WEB_CSS, encoding="utf-8").read()
    declared = set(re.findall(r"\.(anim-[a-z-]+|skeleton)\s*\{", css))
    assert declared, "no motion utilities found"
    block = css[css.index("prefers-reduced-motion"):]
    for name in declared:
        assert name in block, f".{name} is not switched off under reduced motion"


# ── Health Score zones ──────────────────────────────────────────────────────

def test_zones_come_from_the_shared_file():
    raw = _raw_tokens()
    assert dt.ZONES["critical"] == raw["zones"]["critical"]
    assert dt.ZONES["excellent"] == raw["zones"]["excellent"]
    assert dt.PRINT_ZONES == raw["pdf"]["zones"]


def test_pdf_zone_colours_are_the_print_zones():
    """The score is printed on white, so the PDF takes the print zones."""
    src = io.open(pg.__file__, encoding="utf-8").read()
    for stale in ("#dc2626", "#d97706", "#65a30d", "#16a34a"):
        assert stale not in src, f"raw zone colour {stale} still hardcoded in pdf_generator"
    for key in ("critical", "unstable", "stable", "excellent"):
        assert _hex(pg._ZONE_COLORS[key]) == dt.PRINT_ZONES[key]


def test_web_scorecolor_reads_the_tokens_not_a_copy():
    src = (WEB / "src" / "lib" / "utils.ts").read_text(encoding="utf-8")
    assert "ZONES" in src, "scoreColor must use the shared ZONES export"
    assert not re.search(r"#[0-9A-Fa-f]{6}", src)


@pytest.mark.parametrize("zones", ["web", "print"])
def test_zones_keep_their_meaning(zones):
    """critical -> excellent stays coral, amber, green, cyan-green: four separable steps."""
    z = dt.ZONES if zones == "web" else dt.PRINT_ZONES
    vals = [z[k] for k in ("critical", "unstable", "stable", "excellent")]
    assert len(set(vals)) == 4
    (cr_r, cr_g, cr_b), (un_r, un_g, un_b), (st_r, st_g, st_b), (ex_r, ex_g, _ex_b) = map(_rgb, vals)
    assert cr_r > cr_g and cr_r > cr_b, "critical should read warm"
    assert un_r > un_b and un_g > un_b, "unstable should read amber"
    assert st_g > st_r and st_g > st_b, "stable should read green"
    assert ex_g > ex_r, "excellent should read cool/green"


def test_web_zones_are_legible_as_text():
    """The score number is painted in its zone colour."""
    t = _raw_tokens()["theme"]
    for key, colour in dt.ZONES.items():
        if not key.startswith("_"):
            assert _contrast(colour, t["surface"]) >= AA, (key, colour)


def test_css_zone_tokens_match_the_file():
    """PulseLine's segment colours ride on these, so they must agree."""
    css = _css_colours()
    assert css["success"] == dt.ZONES["excellent"]
    assert css["danger"] == dt.ZONES["critical"]
    assert css["warning"] == dt.ZONES["unstable"]


# ── PulseLine glow + PDF severity column ────────────────────────────────────

def test_pulseline_glow_is_softened():
    src = (WEB / "src" / "components" / "ui" / "PulseLine.tsx").read_text(encoding="utf-8")
    m = re.search(r'stdDeviation="([\d.]+)"', src)
    assert m, "glow filter missing"
    assert float(m.group(1)) <= 2.0, f"glow blur {m.group(1)} is still heavy"
    assert re.search(r'slope="0\.\d+"', src), "glow alpha is not attenuated"


def test_pdf_severity_column_is_wide_enough_for_one_line():
    src = io.open(pg.__file__, encoding="utf-8").read()
    m = re.search(r"_sev_w = (\d+) \* mm", src)
    assert m, "severity column width not parameterised"
    assert int(m.group(1)) >= 22, "column still too narrow for 'Серьёзность'"
