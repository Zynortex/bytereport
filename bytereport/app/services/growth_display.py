"""
Display safety for month-over-month growth percentages.

Percentage change is mathematically unstable when the base period is near zero:
profit of 1 000 rising to 220 000 is "+21 900%", which is arithmetically correct
and analytically meaningless. Plotted as-is it stretches the axis by two orders
of magnitude and squashes every meaningful point into a flat line at zero.

This module is the single place that decides which points are safe to plot. It
runs once in financial_engine; the web chart and the PDF renderer both consume
its output and neither re-derives the rule. The raw percentages are preserved
untouched alongside the display values, so nothing downstream loses information.

Chosen approach (option "а" of the brief): an out-of-range point is REMOVED from
the plotted series and re-surfaced as a structured annotation carrying the real
before/after amounts, which say far more than "+21 900%" ever could.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# Beyond this magnitude a percentage stops being readable on a shared axis.
# 300% still comfortably fits a normal growth chart; anything past it is a
# near-zero-base artefact rather than a trend.
MOM_OUTLIER_THRESHOLD_PCT = 300.0

# Which metrics participate, and where their amounts live on a MonthMetrics row.
METRICS = ("revenue", "expenses", "profit")


@dataclass(frozen=True)
class GrowthOutlier:
    """One percentage that was withheld from the chart, with the real numbers."""

    month: str
    metric: str          # "revenue" | "expenses" | "profit"
    previous: float
    current: float
    pct: float

    def as_dict(self) -> dict:
        return {
            "month": self.month,
            "metric": self.metric,
            "previous": self.previous,
            "current": self.current,
            "pct": self.pct,
        }


def is_outlier(pct: Optional[float]) -> bool:
    """True when a percentage is too extreme to share an axis with the rest."""
    return pct is not None and abs(pct) > MOM_OUTLIER_THRESHOLD_PCT


def display_value(pct: Optional[float]) -> Optional[float]:
    """The value to plot: the percentage itself, or None to break the line."""
    return None if is_outlier(pct) else pct


def collect_outliers(
    month: str,
    pcts: dict[str, Optional[float]],
    previous: dict[str, float],
    current: dict[str, float],
) -> list[GrowthOutlier]:
    """
    Structured annotations for every metric whose growth was withheld.

    Returns data, not prose: the caller renders it in its own language using
    existing i18n, so the DECISION lives here while wording stays local.
    """
    out: list[GrowthOutlier] = []
    for metric in METRICS:
        pct = pcts.get(metric)
        if not is_outlier(pct):
            continue
        out.append(
            GrowthOutlier(
                month=month,
                metric=metric,
                previous=float(previous.get(metric, 0.0)),
                current=float(current.get(metric, 0.0)),
                pct=float(pct),
            )
        )
        logger.info(
            "MoM %s for %s withheld from chart: %.1f%% (%s -> %s)",
            metric, month, pct, previous.get(metric), current.get(metric),
        )
    return out
