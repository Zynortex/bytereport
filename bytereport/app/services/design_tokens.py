"""
Design tokens, loaded from the repo-root design-tokens.json.

That file is the single source shared with the web app, so a colour changed
there moves the dashboard and the PDF together. Falling back to a baked-in copy
keeps PDF generation working if the file is missing from a deploy artifact.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_TOKENS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "design-tokens.json"
)

# Mirrors design-tokens.json (colour groups; a test pins it to the file). Only
# used when the file cannot be read.
_FALLBACK: dict[str, Any] = {
    "theme": {
        "bg_base": "#04060B", "bg_header": "#070B14",
        "surface": "#0A101C", "surface_hover": "#0E1524",
        "border_default": "rgb(148 172 205 / 0.11)", "border_strong": "rgb(148 172 205 / 0.20)",
        "text_primary": "#E8EEF6", "text_secondary": "#97A5B9", "text_dim": "#66758B",
        "accent": "#3DE6D6", "accent_text": "#3DE6D6", "accent_soft": "#8FF3E9",
        "accent_ink": "#04201D", "negative": "#FF7A6B", "radius": "3px",
    },
    "charts": {
        "ramp": ["#1B2A40", "#22314A", "#2E4360", "#3E5578",
                 "#527098", "#6D8CAE", "#8CA0BC", "#B7C4D6"],
        "series": {"revenue": "#5B9DFF", "expenses": "#66758B", "profit": "#3DE6D6"},
        "cash_gap": "#FF7A6B",
        "categories": ["#2CC4B5", "#5B9DFF", "#4FC3F7", "#6FCF97",
                       "#A8C97F", "#F2C14E", "#F29E7B", "#66758B"],
    },
    "severity": {"high": "#FF7A6B", "medium": "#F2C14E", "low": "#66758B",
                 "high_fg": "#FF7A6B", "medium_fg": "#F2C14E", "low_fg": "#97A5B9"},
    "zones": {"critical": "#FF7A6B", "unstable": "#F2C14E",
              "stable": "#6FCF97", "excellent": "#3DE6D6"},
    "pdf": {
        "page_bg": "#FFFFFF", "page_ink": "#1E293B", "page_muted": "#5B6472",
        "page_grid": "#E2E5EA", "header_bg": "#070B14",
        "accent": "#0D7D75", "accent_tint": "#E8F5F3", "negative_tint": "#FBEDEB",
        "warning_tint": "#FBF5E6", "neutral_tint": "#F1F3F5", "negative": "#B94A3A",
        "severity": {"high": "#B94A3A", "medium": "#8C6508", "low": "#5B6472"},
        "zones": {"critical": "#B94A3A", "unstable": "#8C6508",
                  "stable": "#2B7C4C", "excellent": "#0D7D75"},
    },
}


def _load() -> dict[str, Any]:
    try:
        with open(os.path.normpath(_TOKENS_PATH), encoding="utf-8") as f:
            data = json.load(f)
        logger.debug("Design tokens loaded from %s", _TOKENS_PATH)
        return data
    except Exception:
        logger.warning(
            "design-tokens.json not readable at %s — using the baked-in copy",
            _TOKENS_PATH,
        )
        return _FALLBACK


TOKENS: dict[str, Any] = _load()

THEME: dict[str, str] = TOKENS.get("theme", _FALLBACK["theme"])
CHARTS: dict[str, Any] = TOKENS.get("charts", _FALLBACK["charts"])
SEVERITY: dict[str, str] = TOKENS.get("severity", _FALLBACK["severity"])
# Health Score zones — same single source as the rest of the palette.
ZONES: dict[str, str] = TOKENS.get("zones", _FALLBACK["zones"])
PDF: dict[str, str] = TOKENS.get("pdf", _FALLBACK["pdf"])

# Convenience aliases used across the PDF pipeline.
RAMP: list[str] = [c for c in CHARTS.get("ramp", []) if isinstance(c, str)]
# Hue-varied palette for categorical charts. The monochrome RAMP above is kept
# for anything genuinely ordinal; category slices need distinguishable hues.
CATEGORY_COLORS: list[str] = [
    c for c in CHARTS.get("categories", _FALLBACK["charts"]["categories"])
    if isinstance(c, str)
]


def category_color_index(name: str, slots: int) -> int:
    """
    Preferred palette slot for a category name.

    Deterministic and implemented identically in TypeScript
    (chartTokens.categoryColorIndex) so the web donut and the PDF donut give a
    category the same colour. Position in the sorted list is deliberately NOT
    used: that would repaint every category whenever shares reorder.
    """
    h = 0
    for ch in name.strip().lower():
        h = (h * 31 + ord(ch)) % 4294967296
    return h % slots


# Names that mean "everything else". The last palette entry (neutral grey) is
# reserved for them so the residual bucket never borrows a category's hue.
OTHER_NAMES = {"прочее", "other", "бошқа", "прочие", "остальное"}


def assign_category_colors(names: list[str]) -> list[str]:
    """
    Colour per category, stable by name.

    Real categories hash over the hued slots; an "other" bucket always takes the
    reserved neutral grey. On collision the next free slot is taken, scanning
    upwards, so two categories never share a colour inside one chart. For a
    given set of categories the result is fully deterministic — the usual case
    is the same business re-analysed, where nothing moves.
    """
    palette = CATEGORY_COLORS or RAMP
    if not palette:
        return []
    hued, neutral = palette[:-1], palette[-1]

    # Collisions are resolved in NAME order, not in the order given: otherwise
    # two categories hashing to one slot would swap colours whenever their
    # shares swapped places. Same rule in chartTokens.assignCategoryColors.
    order = sorted(range(len(names)), key=lambda i: names[i].strip().lower())
    taken: set[int] = set()
    out: list[str] = [neutral] * len(names)
    for i in order:
        name = names[i]
        if name.strip().lower() in OTHER_NAMES:
            continue
        probe = category_color_index(name, len(hued))
        while probe in taken and len(taken) < len(hued):
            probe = (probe + 1) % len(hued)
        taken.add(probe)
        out[i] = hued[probe]
    return out
SERIES: dict[str, str] = CHARTS.get("series", _FALLBACK["charts"]["series"])
CASH_GAP: str = CHARTS.get("cash_gap", _FALLBACK["charts"]["cash_gap"])
# The web accent. On white paper use PRINT_ACCENT: this one is near-invisible there.
ACCENT: str = THEME.get("accent", _FALLBACK["theme"]["accent"])

# ── Print (PDF and Excel) ───────────────────────────────────────────────────
# Darker relatives of the web colours that clear WCAG AA (4.5:1) on white, as
# text and under white text. Headings, table headers, the main chart series.
PRINT_ACCENT: str = PDF.get("accent", _FALLBACK["pdf"]["accent"])
PRINT_ACCENT_TINT: str = PDF.get("accent_tint", _FALLBACK["pdf"]["accent_tint"])
PRINT_NEGATIVE_TINT: str = PDF.get("negative_tint", _FALLBACK["pdf"]["negative_tint"])
PRINT_WARNING_TINT: str = PDF.get("warning_tint", _FALLBACK["pdf"]["warning_tint"])
PRINT_NEUTRAL_TINT: str = PDF.get("neutral_tint", _FALLBACK["pdf"]["neutral_tint"])
PRINT_NEGATIVE: str = PDF.get("negative", _FALLBACK["pdf"]["negative"])
PRINT_SEVERITY: dict[str, str] = PDF.get("severity", _FALLBACK["pdf"]["severity"])
PRINT_ZONES: dict[str, str] = PDF.get("zones", _FALLBACK["pdf"]["zones"])
