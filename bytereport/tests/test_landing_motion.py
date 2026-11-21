"""
The landing comes alive without leaving the style: navy ground, cyan
lines, 3px radius, mono figures — and every new duration, curve and effect
colour written down once, in design-tokens.json.
"""

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
WEB = ROOT / "bytereport-frontend"
SRC = WEB / "src"
TOKENS = json.loads((ROOT / "design-tokens.json").read_text(encoding="utf-8"))
CSS = (SRC / "index.css").read_text(encoding="utf-8")
LANDING_FILES = [SRC / "pages" / "Landing.tsx", *(SRC / "components" / "landing").glob("*.tsx")]


def _rgba(value: str) -> tuple[int, int, int, float]:
    r, g, b, a = re.fullmatch(r"rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)", value).groups()
    return int(r), int(g), int(b), float(a)


# ── Tokens ──────────────────────────────────────────────────────────────────

def test_the_glows_are_the_accent_and_the_chart_blue_and_faint():
    """Cyan and blue, as in the ByteForge hero, at the old 11% opacity."""
    r, g, b, a = _rgba(TOKENS["effects"]["glow"])
    assert "#%02X%02X%02X" % (r, g, b) == TOKENS["theme"]["accent"].upper()
    assert a <= 0.12
    r, g, b, a2 = _rgba(TOKENS["effects"]["glow_secondary"])
    assert "#%02X%02X%02X" % (r, g, b) == TOKENS["charts"]["series"]["revenue"].upper()
    assert a2 == a


def test_the_grid_is_faint():
    _, _, _, a = _rgba(TOKENS["effects"]["grid_line"])
    assert 0.03 <= a <= 0.05


def test_the_curve_never_overshoots():
    x1, y1, x2, y2 = TOKENS["motion"]["ease"]
    assert TOKENS["motion"]["ease"] == [0.22, 1, 0.36, 1]
    assert all(0 <= v <= 1 for v in (x1, y1, x2, y2))


def test_durations_are_in_the_agreed_ranges():
    mo = TOKENS["motion"]
    assert 150 <= mo["hover_ms"] <= 250 and 150 <= mo["press_ms"] <= 250
    assert 400 <= mo["reveal_ms"] <= 700
    assert 60 <= mo["stagger_ms"] <= 80
    assert 12 <= mo["reveal_offset_px"] <= 16
    assert mo["press_scale"] == 0.98
    assert 6000 <= mo["hero_cycle_ms"] <= 8000


def test_the_css_mirror_matches_the_file():
    mo, fx = TOKENS["motion"], TOKENS["effects"]
    expected = {
        "--dur-hover": f"{mo['hover_ms']}ms", "--dur-press": f"{mo['press_ms']}ms",
        "--press-scale": str(mo["press_scale"]), "--fx-glow": fx["glow"],
        "--fx-glow-2": fx["glow_secondary"], "--fx-grid": fx["grid_line"],
        "--fx-selection": fx["selection"],
        "--fx-grid-size": f"{fx['grid_size_px']}px", "--fx-spotlight": fx["spotlight"],
        "--fx-spotlight-r": f"{fx['spotlight_radius_px']}px",
    }
    for var, value in expected.items():
        assert re.search(rf"{re.escape(var)}:\s*{re.escape(value)};", CSS), var


# ── No hardcoding in the new components ─────────────────────────────────────

def test_no_hardcoded_durations_or_colours_in_the_landing():
    for path in LANDING_FILES:
        code = re.sub(r"//[^\n]*|/\*.*?\*/|\{/\*.*?\*/\}", "", path.read_text(encoding="utf-8"), flags=re.S)
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b", code), f"{path.name}: hex colour"
        assert not re.search(r"rgba?\(", code), f"{path.name}: rgba colour"
        assert not re.search(r"\bduration:\s*\d", code), f"{path.name}: literal duration"
        assert not re.search(r"\b\d{2,4}ms\b", code), f"{path.name}: literal ms"
        assert "backdrop-blur" not in code, f"{path.name}: glass"
        assert not re.search(r"\bshadow-|box-shadow", code), f"{path.name}: shadow"


def test_no_bounce_or_spin():
    for path in LANDING_FILES:
        code = path.read_text(encoding="utf-8")
        assert not re.search(r"type:\s*[\"']spring[\"']|bounce|animate-spin|rotate:", code), path.name


# ── Library: Motion only, lazily ────────────────────────────────────────────

def test_only_motion_was_added():
    pkg = json.loads((WEB / "package.json").read_text(encoding="utf-8"))
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    assert "motion" in deps
    for banned in ("animejs", "anime", "framer-motion", "@kokonut", "kokonutui", "bklit", "shadcn"):
        assert not any(banned in d for d in deps), banned


def test_lazy_motion_with_reduced_motion_honoured():
    app = (SRC / "App.tsx").read_text(encoding="utf-8")
    assert "<LazyMotion features={domAnimation} strict>" in app
    assert 'reducedMotion="user"' in app
    for path in LANDING_FILES:
        assert "motion.div" not in path.read_text(encoding="utf-8"), "use m.* under LazyMotion"


def test_counting_shows_the_final_value_under_reduced_motion():
    code = (SRC / "lib" / "countUp.ts").read_text(encoding="utf-8")
    assert "useReducedMotion()" in code and "reduced ? target : 0" in code


def test_the_hero_figures_come_from_the_demo_report():
    hero = (SRC / "components" / "landing" / "HeroReport.tsx").read_text(encoding="utf-8")
    assert "getDemo(" in hero
    for figure in ("4145000", "3480000", "665000", "640000"):
        pattern = r"[\s_ ,]?".join(figure)
        assert not re.search(pattern, hero.replace(" ", " ")), f"{figure} typed into the hero"
    assert not re.search(r"\b61\b", hero), "the score comes from the report too"


def test_the_landing_cta_is_registration_not_pricing():
    landing = (SRC / "pages" / "Landing.tsx").read_text(encoding="utf-8")
    # A route to /pricing, not the "@/lib/pricing" import (the free-report count).
    assert '"/auth?tab=register"' in landing and '"/pricing' not in landing


def test_buttons_press_to_the_token_scale():
    btn = (SRC / "components" / "ui" / "button.tsx").read_text(encoding="utf-8")
    assert "active:scale-[var(--press-scale)]" in btn and "duration-[var(--dur-press)]" in btn
