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

# Mirrors design-tokens.json. Only used when the file cannot be read.
_FALLBACK: dict[str, Any] = {
    "theme": {
        "bg_base": "#121016", "bg_header": "#0D0B11", "border_default": "#241F2B",
        "accent": "#6B5482", "text_primary": "#F1EEF3",
        "text_muted": "#736C7E", "text_subtle": "#8C8494", "radius": "3px",
    },
    "charts": {
        "ramp": ["#1B2A40", "#22314A", "#2E4360", "#3E5578",
                 "#527098", "#6D8CAE", "#8CA0BC", "#B7C4D6"],
        "categories": ["#3E5578", "#3E6B6B", "#5A4569", "#7A5A28",
                       "#7A4A3E", "#5A6B3E", "#6B6670"],
        "series": {"revenue": "#3E5578", "expenses": "#6B5F55", "profit": "#6B5482"},
        "cash_gap": "#8B5A50",
    },
    "severity": {"high": "#7A2E35", "medium": "#7A5A2E", "low": "#4A5560"},
    "zones": {"critical": "#7A2E2E", "unstable": "#7A5A28",
              "stable": "#5A6B3E", "excellent": "#3E6B52"},
    "pdf": {
        "page_bg": "#FFFFFF", "page_ink": "#1E293B", "page_muted": "#5B6472",
        "page_grid": "#E2E5EA", "header_bg": "#0D0B11", "table_header_bg": "#6B5482",
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

    taken: dict[int, str] = {}
    out: list[str] = []
    for name in names:
        if name.strip().lower() in OTHER_NAMES:
            out.append(neutral)
            continue
        probe = category_color_index(name, len(hued))
        while probe in taken and len(taken) < len(hued):
            probe = (probe + 1) % len(hued)
        taken[probe] = name
        out.append(hued[probe])
    return out
SERIES: dict[str, str] = CHARTS.get("series", _FALLBACK["charts"]["series"])
CASH_GAP: str = CHARTS.get("cash_gap", _FALLBACK["charts"]["cash_gap"])
ACCENT: str = THEME.get("accent", "#6B5482")
