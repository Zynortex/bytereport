"""
Which sections a report shows, and in what order.

The block registry is repo-root report-blocks.json, imported by the web the same
way. A `ReportLayout` is an ordering of those ids with a visible flag each, plus
per-block lists of hidden ITEMS for the list-shaped sections (an accountant
hides the one insight that is wrong for this client, not the whole section).

The PDF generator takes a layout and builds from it. It has no order of its own
any more — a fixed order in the generator is exactly what made the web
arrangement cosmetic, and the feature is the PDF.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

logger = logging.getLogger(__name__)

_BLOCKS_PATH = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "report-blocks.json"
))

# Mirrors report-blocks.json. Only used when the file cannot be read.
_FALLBACK_IDS = [
    "health_score", "executive_summary", "kpi_strip",
    "chart_monthly", "chart_categories", "chart_growth", "chart_forecast",
    "key_insights", "top_risks", "anomalies", "expense_analysis",
    "growth_opportunities", "priority_actions", "cash_flow_analysis", "forecast",
]


def _load_registry() -> list[dict[str, Any]]:
    try:
        with open(_BLOCKS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        blocks = data.get("blocks")
        if isinstance(blocks, list) and all("id" in b for b in blocks):
            return blocks
        logger.warning("report-blocks.json has an unexpected shape; using fallback")
    except (OSError, ValueError) as exc:
        logger.warning("report-blocks.json unavailable (%s); using fallback", exc)
    return [{"id": i, "kind": "text", "label": {}} for i in _FALLBACK_IDS]


REGISTRY: list[dict[str, Any]] = _load_registry()
BLOCK_IDS: list[str] = [b["id"] for b in REGISTRY]
_BY_ID: dict[str, dict[str, Any]] = {b["id"]: b for b in REGISTRY}

# Sections whose entries can be hidden one at a time, and the AIReport field
# each one draws from.
LIST_BLOCKS: dict[str, str] = {
    b["id"]: b["items"] for b in REGISTRY if b.get("items")
}


def block_label(block_id: str, language: str = "ru") -> str:
    labels = _BY_ID.get(block_id, {}).get("label", {})
    return labels.get(language) or labels.get("ru") or block_id


def in_pdf(block_id: str) -> bool:
    """Some sections exist only on the web (the KPI strip); the PDF skips them."""
    return _BY_ID.get(block_id, {}).get("pdf", True) is not False


class LayoutBlock(BaseModel):
    id: str
    visible: bool = True

    @field_validator("id")
    @classmethod
    def known(cls, v: str) -> str:
        if v not in _BY_ID:
            raise ValueError(f"unknown report block {v!r}")
        return v


class ReportLayout(BaseModel):
    """
    Order and visibility. `blocks` is the order; anything missing from it is
    appended in default order and hidden, so a layout saved before a new
    section was added never makes that section vanish silently — it shows up,
    switched off, where the accountant can find it.
    """

    blocks: list[LayoutBlock] = Field(default_factory=list)
    # block id -> indices of items to leave out of that section.
    hidden_items: dict[str, list[int]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def complete_and_dedupe(self) -> "ReportLayout":
        # No order given at all means the default order with everything shown
        # — not "every section appended hidden", which is what the completion
        # below would otherwise produce from an empty list. A caller passing
        # only hidden_items wants the default arrangement minus those entries.
        if not self.blocks:
            self.blocks = [LayoutBlock(id=b) for b in BLOCK_IDS]

        seen: set[str] = set()
        ordered: list[LayoutBlock] = []
        for b in self.blocks:
            if b.id in seen:
                continue           # a duplicate would render the section twice
            seen.add(b.id)
            ordered.append(b)
        for bid in BLOCK_IDS:
            if bid not in seen:
                # A section this layout has never heard of: present but off.
                ordered.append(LayoutBlock(id=bid, visible=False))
        self.blocks = ordered

        cleaned: dict[str, list[int]] = {}
        for bid, idxs in self.hidden_items.items():
            if bid in LIST_BLOCKS:
                cleaned[bid] = sorted({int(i) for i in idxs if int(i) >= 0})
        self.hidden_items = cleaned
        return self

    @classmethod
    def default(cls) -> "ReportLayout":
        return cls(blocks=[LayoutBlock(id=b) for b in BLOCK_IDS])

    def visible_ids(self, *, for_pdf: bool = False) -> list[str]:
        return [
            b.id for b in self.blocks
            if b.visible and (not for_pdf or in_pdf(b.id))
        ]

    def is_visible(self, block_id: str) -> bool:
        return any(b.id == block_id and b.visible for b in self.blocks)

    def keep_items(self, block_id: str, items: list[Any]) -> list[Any]:
        """The section's entries with the hidden ones removed, order kept."""
        hidden = set(self.hidden_items.get(block_id, []))
        return [it for i, it in enumerate(items) if i not in hidden]


def coerce_layout(raw: Optional[dict[str, Any] | ReportLayout]) -> ReportLayout:
    """A layout from the request body, or the default when none was sent."""
    if raw is None:
        return ReportLayout.default()
    if isinstance(raw, ReportLayout):
        return raw
    return ReportLayout.model_validate(raw)


LayoutKind = Literal["text", "chart", "list", "metrics"]
