"""
The design language is defined once, in /design-tokens.json, and both the web
app and the PDF pipeline consume it. These tests pin that contract: a colour
may only change by editing the JSON, and no framework default may creep back in.
"""

import io
import json
import os
import re

import pytest

from app.services import chart_renderer as cr
from app.services import design_tokens as dt
from app.services import pdf_generator as pg

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
TOKENS_FILE = os.path.join(REPO_ROOT, "design-tokens.json")
WEB_TOKENS_TS = os.path.join(REPO_ROOT, "bytereport-frontend", "src", "lib", "chartTokens.ts")
WEB_CSS = os.path.join(REPO_ROOT, "bytereport-frontend", "src", "index.css")


def _raw_tokens() -> dict:
    with io.open(TOKENS_FILE, encoding="utf-8") as f:
        return json.load(f)


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


def test_fallback_matches_the_file():
    """The baked-in copy is a deploy safety net — it must not drift."""
    raw = _raw_tokens()
    assert dt._FALLBACK["charts"]["ramp"] == raw["charts"]["ramp"]
    assert dt._FALLBACK["charts"]["series"] == raw["charts"]["series"]
    assert dt._FALLBACK["theme"]["accent"] == raw["theme"]["accent"]
    assert dt._FALLBACK["severity"]["high"] == raw["severity"]["high"]


def test_web_imports_the_same_file():
    """The TS module must import the JSON, not re-declare hexes."""
    src = io.open(WEB_TOKENS_TS, encoding="utf-8").read()
    assert 'from "../../../design-tokens.json"' in src
    hexes = re.findall(r"#[0-9A-Fa-f]{6}", src)
    assert hexes == [], f"chartTokens.ts must not hardcode colours, found {hexes}"


# ── Ramp ────────────────────────────────────────────────────────────────────

def test_ramp_is_exactly_the_agreed_eight():
    assert dt.RAMP == [
        "#1B2A40", "#22314A", "#2E4360", "#3E5578",
        "#527098", "#6D8CAE", "#8CA0BC", "#B7C4D6",
    ]


def test_ramp_runs_dark_to_light():
    def lum(c: str) -> int:
        r, g, b = int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)
        return r + g + b
    values = [lum(c) for c in dt.RAMP]
    assert values == sorted(values), "ramp must go dark → light for descending shares"


def test_donut_uses_the_shared_category_palette():
    """Categorical slices use the hue-varied palette, not the ordinal ramp."""
    assert cr.DONUT_COLORS == dt.CATEGORY_COLORS
    assert dt.CATEGORY_COLORS == _raw_tokens()["charts"]["categories"]


def test_category_palette_hues_are_distinguishable():
    """The monochrome ramp blurred past ~4 slices; these must differ in HUE."""
    import colorsys
    hues = []
    for c in dt.CATEGORY_COLORS[:-1]:          # last slot is the neutral grey
        r, g, b = (int(c[i:i + 2], 16) / 255 for i in (1, 3, 5))
        h, _l, sat = colorsys.rgb_to_hls(r, g, b)
        assert sat > 0.10, f"{c} is too desaturated to read as its own hue"
        hues.append(h * 360)
    hues.sort()
    gaps = [b - a for a, b in zip(hues, hues[1:])]
    assert min(gaps) > 15, f"two category hues are within {min(gaps):.0f}deg"


def test_category_colours_are_stable_by_name():
    """A category keeps its colour when shares reorder between reports."""
    first = dict(zip(["Материалы", "Зарплата", "Реклама"],
                     dt.assign_category_colors(["Материалы", "Зарплата", "Реклама"])))
    # same categories, different order and one extra
    names = ["Реклама", "Материалы", "Зарплата"]
    second = dict(zip(names, dt.assign_category_colors(names)))
    for k in first:
        assert first[k] == second[k], f"{k} changed colour when the order changed"


def test_category_colours_are_distinct_within_one_chart():
    names = ["Материалы", "Зарплата", "Аренда цеха", "Логистика",
             "Инструмент", "Реклама", "Прочее"]
    assigned = dt.assign_category_colors(names)
    assert len(set(assigned)) == len(names)


def test_other_bucket_takes_the_reserved_neutral():
    neutral = dt.CATEGORY_COLORS[-1]
    for name in ("Прочее", "прочее", "Other", " Бошқа "):
        assert dt.assign_category_colors([name]) == [neutral]


def test_python_and_typescript_hash_agree():
    """
    Both surfaces must colour a category identically. The TS implementation is
    a literal port; this pins the arithmetic so a change to one is caught.
    """
    ts = io.open(WEB_TOKENS_TS, encoding="utf-8").read()
    assert "h * 31 + ch.codePointAt(0)" in ts, "TS hash diverged from the Python one"
    assert "% 4294967296" in ts
    # spot-check the Python side against hand-computed values
    assert dt.category_color_index("a", 6) == (ord("a") % 6)
    assert dt.category_color_index("", 6) == 0


def test_ramp_carries_no_semantic_hue():
    """Categorical data must never imply risk."""
    banned = {"#DC2626", "#D97706", "#16A34A", "#65A30D", "#1D6FED"}
    assert not ({c.upper() for c in dt.RAMP} & banned)


# ── Three-series charts ─────────────────────────────────────────────────────

def test_series_colours():
    assert cr.C_REVENUE == "#3E5578"
    assert cr.C_EXPENSE == "#6B5F55"     # warm neutral, deliberately not red
    assert cr.C_PROFIT == "#6B5482"      # the accent: the number that matters


def test_expenses_series_is_not_red():
    r, g, b = (int(cr.C_EXPENSE[i:i + 2], 16) for i in (1, 3, 5))
    assert not (r > g + 60 and r > b + 60), "expenses must not read as a red alert"


def test_profit_series_is_the_accent():
    assert cr.C_PROFIT.upper() == dt.ACCENT.upper()


def test_cash_gap_is_muted_terracotta_not_pure_red():
    assert cr.C_CASH_GAP == "#8B5A50"
    r, g, b = (int(cr.C_CASH_GAP[i:i + 2], 16) for i in (1, 3, 5))
    assert r < 0xC0, "cash-gap colour is still shouting"
    assert g > 0x40 and b > 0x40, "a pure red has near-zero green/blue"


# ── PDF chrome ──────────────────────────────────────────────────────────────

def test_anomalies_table_header_uses_the_accent():
    """Regression: it used #7C3AED, a library default tied to nothing."""
    src = io.open(pg.__file__, encoding="utf-8").read()
    assert "#7C3AED" not in src.replace("# was #7C3AED", "")
    assert pg.BRAND_BLUE.hexval()[2:] .lower().endswith(dt.ACCENT[1:].lower())


def test_no_stray_framework_defaults_left_in_chart_renderer():
    """§5: nothing may remain from the old bright palette."""
    src = io.open(cr.__file__, encoding="utf-8").read()
    body = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
    for stale in ("#1D6FED", "#DC2626", "#16A34A", "#0F3D8C", "#4B8BF4", "#CFE0FD"):
        assert stale not in body, f"stale colour {stale} still in chart_renderer"


def test_severity_is_muted_but_separable():
    """The one justified semantic scale — three distinct, non-shouting hues."""
    sev = [dt.SEVERITY["high"], dt.SEVERITY["medium"], dt.SEVERITY["low"]]
    assert len(set(sev)) == 3
    for c in sev:
        r, g, b = (int(c[i:i + 2], 16) for i in (1, 3, 5))
        assert max(r, g, b) < 0xA0, f"{c} is too saturated for a muted scale"


def test_severity_is_not_part_of_the_ramp():
    assert not ({c.upper() for c in dt.SEVERITY.values()} & {c.upper() for c in dt.RAMP})


# ── Web theme mirrors the tokens ────────────────────────────────────────────

def test_css_carries_the_agreed_theme_values():
    css = io.open(WEB_CSS, encoding="utf-8").read()
    theme = _raw_tokens()["theme"]
    for key in ("bg_base", "bg_header", "border_default", "accent", "text_primary"):
        assert theme[key] in css, f"{key} ({theme[key]}) missing from index.css"


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


# ── Token namespaces must not collide ───────────────────────────────────────
#
# Tailwind v4 derives utilities from the token PREFIX, so a name reused across
# two namespaces silently rewrites an existing utility. `--color-base` did
# exactly that: it turned `text-base` from a font size into
# `color: var(--color-base)`, and every element carrying that very common class
# painted its text in the app ground. The landing page's primary CTA read as an
# empty box for as long as the token existed.

# Tailwind's built-in font-size scale. A colour token may not take one of these
# names, or `text-<name>` stops being a size.
_FONT_SIZE_NAMES = {
    "xs", "sm", "base", "lg", "xl",
    "2xl", "3xl", "4xl", "5xl", "6xl", "7xl", "8xl", "9xl",
}


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


def _declared(prefix: str) -> set[str]:
    return set(re.findall(rf"--{prefix}-([a-z0-9-]+)\s*:", _theme_block()))


def test_no_colour_token_shadows_a_font_size():
    clash = _declared("color") & _FONT_SIZE_NAMES
    assert not clash, (
        f"--color-{{{','.join(sorted(clash))}}} rewrites text-<name> from a font "
        "size into a colour; rename the token"
    )


def test_the_ground_token_is_not_named_base():
    """The specific regression: #121016 must not be reachable as text-base."""
    block = _theme_block()
    assert "--color-ground:" in block, "the app ground token was renamed again"
    assert "--color-base:" not in block


def test_accent_has_a_legible_text_variant():
    """
    The stroke accent is too dark to serve as text on the ground. Both values
    must exist, and the -fg variant must actually clear WCAG AA (4.5:1).
    """
    block = _theme_block()
    accent = re.search(r"--color-accent:\s*(#[0-9A-Fa-f]{6})", block)
    accent_fg = re.search(r"--color-accent-fg:\s*(#[0-9A-Fa-f]{6})", block)
    assert accent and accent_fg, "accent needs a base and an -fg variant"

    ground = re.search(r"--color-ground:\s*(#[0-9A-Fa-f]{6})", block).group(1)
    assert _contrast(accent_fg.group(1), ground) >= 4.5
    # And the base really is the unusable one — otherwise the split is pointless.
    assert _contrast(accent.group(1), ground) < 4.5


def _luminance(hex_colour: str) -> float:
    parts = [int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in parts]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


# ── Motion stays inside the design language ─────────────────────────────────

def _keyframe_css() -> str:
    css = io.open(WEB_CSS, encoding="utf-8").read()
    return " ".join(re.findall(r"@keyframes[^{]+\{(?:[^{}]|\{[^{}]*\})*\}", css))


def test_no_animation_overshoots_its_resting_state():
    """
    The rule is overshoot, not scale.

    This test used to ban `scale(` outright. Overlays now settle in from
    0.97 -> 1, which is the same restrained register as a 6px slide, so the
    check moved to what actually distinguishes the two looks: a value may
    approach 1 but never pass it and come back. 1 -> 1.05 -> 1 performs;
    0.97 -> 1 arrives.
    """
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
    assert dt._FALLBACK["zones"] == {k: v for k, v in raw["zones"].items()
                                     if not k.startswith("_")}


def test_pdf_zone_colours_read_the_tokens_not_a_copy():
    """These were two independent hardcoded palettes before."""
    src = io.open(pg.__file__, encoding="utf-8").read()
    for stale in ("#dc2626", "#d97706", "#65a30d", "#16a34a"):
        assert stale not in src, f"raw zone colour {stale} still hardcoded in pdf_generator"
    for key in ("critical", "unstable", "stable", "excellent"):
        assert pg._ZONE_COLORS[key].hexval()[2:].lower() == dt.ZONES[key][1:].lower()


def test_web_scorecolor_reads_the_tokens_not_a_copy():
    utils = os.path.join(REPO_ROOT, "bytereport-frontend", "src", "lib", "utils.ts")
    src = io.open(utils, encoding="utf-8").read()
    assert "ZONES" in src, "scoreColor must use the shared ZONES export"
    for stale in ("#dc2626", "#d97706", "#65a30d", "#16a34a"):
        assert stale not in src, f"raw zone colour {stale} still hardcoded in utils.ts"


def test_zones_are_muted_like_the_severity_scale():
    for key, hexv in dt.ZONES.items():
        if key.startswith("_"):
            continue
        r, g, b = (int(hexv[i:i + 2], 16) for i in (1, 3, 5))
        assert max(r, g, b) < 0xA0, f"zone {key} ({hexv}) is louder than the interface"


def test_zone_order_is_preserved_and_distinct():
    """critical → excellent must stay four separable steps after muting."""
    vals = [dt.ZONES[k] for k in ("critical", "unstable", "stable", "excellent")]
    assert len(set(vals)) == 4
    # Red-leaning at the critical end, green-leaning at the excellent end.
    cr_r, _cg, _cb = (int(vals[0][i:i + 2], 16) for i in (1, 3, 5))
    ex_r, ex_g, _b = (int(vals[3][i:i + 2], 16) for i in (1, 3, 5))
    assert cr_r > int(vals[0][3:5], 16), "critical should still read warm"
    assert ex_g > ex_r, "excellent should still read cool/green"


def test_css_zone_tokens_match_the_file():
    """PulseLine's segment colours ride on these, so they must agree."""
    css = io.open(WEB_CSS, encoding="utf-8").read()
    assert dt.ZONES["excellent"] in css       # --color-success
    assert dt.ZONES["critical"] in css        # --color-danger
    assert dt.ZONES["unstable"] in css        # --color-warning


# ── PulseLine glow + PDF severity column ────────────────────────────────────

def test_pulseline_glow_is_softened():
    p = os.path.join(REPO_ROOT, "bytereport-frontend", "src",
                     "components", "ui", "PulseLine.tsx")
    src = io.open(p, encoding="utf-8").read()
    m = re.search(r'stdDeviation="([\d.]+)"', src)
    assert m, "glow filter missing"
    assert float(m.group(1)) <= 2.0, f"glow blur {m.group(1)} is still heavy"
    assert re.search(r'slope="0\.\d+"', src), "glow alpha is not attenuated"


def test_pdf_severity_column_is_wide_enough_for_one_line():
    src = io.open(pg.__file__, encoding="utf-8").read()
    m = re.search(r"_sev_w = (\d+) \* mm", src)
    assert m, "severity column width not parameterised"
    assert int(m.group(1)) >= 22, "column still too narrow for 'Серьёзность'"
