"""
Category-coverage signal.

Single source of truth for "how far can we trust the category breakdown in this
data?". The answer depends on the PARSED DATA, never on the file format: a CSV
can have an empty category column, and a PDF statement could in principle carry
categories if a parser ever extracts them.

Computed once and attached to FinancialMetrics; the AI prompt, the PDF report
and the web UI all read the same fields rather than re-deriving anything.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Iterable, Literal

logger = logging.getLogger(__name__)

# Marker written by parsers that have no category information at all.
UNCATEGORIZED = "uncategorized"

CategoryReliability = Literal["full", "partial", "none"]

# Thresholds on the share of transactions carrying a real category.
#   coverage >= FULL_THRESHOLD                      -> "full"
#   PARTIAL_THRESHOLD <= coverage < FULL_THRESHOLD  -> "partial"
#   coverage <  PARTIAL_THRESHOLD                   -> "none"
#
# "partial" exists because a single 30% cut-off was too blunt: at 40% coverage a
# breakdown is genuinely useful, but presenting it as if it described all the
# money would be misleading. That band gets the breakdown WITH the real
# percentage stated.
FULL_THRESHOLD = 0.70
PARTIAL_THRESHOLD = 0.30

# Values that mean "no category", beyond empty/None.
_EMPTY_MARKERS = {UNCATEGORIZED, "", "-", "—", "n/a", "na", "none", "null",
                  "без категории", "не указано"}


def classify_coverage(
    coverage: float,
    full_threshold: float = FULL_THRESHOLD,
    partial_threshold: float = PARTIAL_THRESHOLD,
) -> CategoryReliability:
    """Map a coverage ratio onto the three-level scale."""
    if coverage >= full_threshold:
        return "full"
    if coverage >= partial_threshold:
        return "partial"
    return "none"


@dataclass(frozen=True)
class CategorySignal:
    """Outcome of one coverage evaluation."""

    coverage: float          # 0.0 – 1.0
    level: CategoryReliability
    categorized: int
    total: int

    @property
    def reliable(self) -> bool:
        """
        Backwards-compatible boolean: anything other than "none" shows a
        breakdown. Kept so existing callers of the old bool keep working.
        """
        return self.level != "none"

    @property
    def coverage_percent(self) -> int:
        """Whole-percent figure for user-facing copy."""
        return int(round(self.coverage * 100))

    def as_dict(self) -> dict[str, Any]:
        return {
            "category_coverage": self.coverage,
            "category_reliability": self.level,
            "has_reliable_categories": self.reliable,
            "categorized_count": self.categorized,
            "transaction_count": self.total,
        }


def is_real_category(value: Any) -> bool:
    """True when a transaction carries a genuine, usable category."""
    if value is None:
        return False
    text = str(value).strip().lower()
    return bool(text) and text not in _EMPTY_MARKERS


def evaluate_categories(
    transactions: Iterable[Any],
    full_threshold: float = FULL_THRESHOLD,
    partial_threshold: float = PARTIAL_THRESHOLD,
) -> CategorySignal:
    """
    Measure category coverage across parsed transactions.

    Accepts Transaction models or plain dicts so it can run at any stage of the
    pipeline. An empty transaction list is reported as "none" — there is no
    evidence of categories either way, and suppressing category output is the
    safe direction.
    """
    total = 0
    categorized = 0
    for tx in transactions:
        total += 1
        raw = getattr(tx, "raw_category", None)
        cat = getattr(tx, "category", None)
        if raw is None and cat is None and isinstance(tx, dict):
            raw = tx.get("raw_category")
            cat = tx.get("category")
        # A transaction counts as categorised if either the original label or
        # the normalised one is meaningful.
        if is_real_category(raw) or is_real_category(cat):
            categorized += 1

    coverage = (categorized / total) if total else 0.0
    level = classify_coverage(coverage, full_threshold, partial_threshold) if total else "none"

    logger.info(
        "Category coverage: %d/%d = %.1f%% -> %s (full>=%.0f%%, partial>=%.0f%%)",
        categorized, total, coverage * 100, level.upper(),
        full_threshold * 100, partial_threshold * 100,
    )
    return CategorySignal(
        coverage=round(coverage, 4),
        level=level,
        categorized=categorized,
        total=total,
    )
