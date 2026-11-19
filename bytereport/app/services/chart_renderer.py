"""
Chart rendering for the PDF report.

Renders the same four charts the web report shows, straight from the
FinancialMetrics dict the frontend already computes — nothing is recalculated
here. Each renderer returns PNG bytes, or None when the data needed for that
chart is absent, so the PDF can simply skip a chart it cannot draw.

Colours come from design-tokens.json (shared with the web app), never from
matplotlib defaults:
    revenue  → muted slate-blue
    expenses → warm neutral (deliberately not red)
    profit   → accent violet (the one accent in the chart)
"""

from __future__ import annotations

import io
import logging
from typing import Optional

import matplotlib

# Must be selected before pyplot is imported: the PDF is generated on a
# server with no display, and the default interactive backend would fail.
matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

logger = logging.getLogger(__name__)

# ── Palette: read from the shared design-tokens.json ────────────────────────
# Both the dashboard and this PDF pipeline consume the same file, so a colour
# changed there moves both surfaces together.
from app.utils.category_mapper import category_label
from app.services.design_tokens import (
    CASH_GAP,
    CATEGORY_COLORS,
    PDF as PDF_TOKENS,
    RAMP,
    SERIES,
    assign_category_colors,
)

C_REVENUE  = SERIES["revenue"]     # muted slate-blue, base of the ramp
C_EXPENSE  = SERIES["expenses"]    # warm neutral - deliberately NOT red
C_PROFIT   = SERIES["profit"]      # the accent violet: the number that matters
C_CASH_GAP = CASH_GAP              # muted terracotta, not pillar-box red

C_INK      = PDF_TOKENS["page_ink"]
C_MUTED    = PDF_TOKENS["page_muted"]
C_GRID     = PDF_TOKENS["page_grid"]
C_SURFACE  = PDF_TOKENS["page_bg"]

# Donut segments: hue-varied categorical palette, assigned by category NAME.
# A purely monochrome ramp was indistinguishable past about four slices, and
# assigning by sort position repainted every category whenever shares moved.
DONUT_COLORS = list(CATEGORY_COLORS)

DPI = 200
FIG_BG = C_SURFACE


def _use_document_font() -> None:
    """
    Render chart text in the same face as the rest of the PDF.

    pdf_generator resolves a Cyrillic-capable TTF (DejaVu Sans, or Arial as a
    fallback) and registers it with ReportLab; matplotlib does not know about
    that, so without this the charts silently used matplotlib's own default and
    looked pasted in from another document.
    """
    try:
        from matplotlib import font_manager

        from app.services.pdf_generator import _REGULAR_CANDIDATES, _find_font

        path = _find_font(_REGULAR_CANDIDATES)
        if not path:
            logger.info("Chart font: no document TTF found, keeping matplotlib default")
            return
        font_manager.fontManager.addfont(path)
        name = font_manager.FontProperties(fname=path).get_name()
        plt.rcParams["font.family"] = name
        plt.rcParams["axes.unicode_minus"] = False   # keep a real minus glyph
        logger.debug("Chart font set to %r (%s)", name, path)
    except Exception:
        logger.warning("Could not apply document font to charts", exc_info=True)


_use_document_font()


def _fmt_money(value: float) -> str:
    """Compact axis labels: 1 240 000 → '1.24M', 890 000 → '890K'."""
    a = abs(value)
    if a >= 1_000_000:
        return f"{value / 1_000_000:.2f}".rstrip("0").rstrip(".") + "M"
    if a >= 1_000:
        return f"{value / 1_000:.0f}K"
    return f"{value:.0f}"


def _finish(fig) -> bytes:
    """Serialise a figure to PNG bytes and release it."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=DPI, bbox_inches="tight",
                facecolor=FIG_BG, edgecolor="none")
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def _style_axes(ax) -> None:
    """Flat axes: horizontal grid only, no top/right spines."""
    ax.set_facecolor(C_SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(C_GRID)
    ax.tick_params(colors=C_MUTED, labelsize=8, length=0)
    ax.yaxis.grid(True, color=C_GRID, linewidth=0.7)
    ax.set_axisbelow(True)


# ── 1. Monthly revenue / expenses / profit ──────────────────────────────────

def render_monthly_bars(metrics: dict, labels: dict) -> Optional[bytes]:
    rows = metrics.get("monthly_breakdown") or []
    if not rows:
        return None

    months   = [str(r.get("month", "")) for r in rows]
    revenue  = [float(r.get("revenue", 0) or 0) for r in rows]
    expenses = [float(r.get("expenses", 0) or 0) for r in rows]
    profit   = [float(r.get("profit", 0) or 0) for r in rows]

    x = range(len(months))
    width = 0.27
    fig, ax = plt.subplots(figsize=(7.2, 3.0))
    ax.bar([i - width for i in x], revenue,  width, label=labels["chart_revenue"],  color=C_REVENUE)
    ax.bar(list(x),                expenses, width, label=labels["chart_expenses"], color=C_EXPENSE)
    ax.bar([i + width for i in x], profit,   width, label=labels["chart_profit"],   color=C_PROFIT)

    # Profit can be negative (a cash-gap month) — keep the zero line visible.
    if min(profit, default=0) < 0:
        ax.axhline(0, color=C_INK, linewidth=0.9)

    ax.set_xticks(list(x))
    ax.set_xticklabels(months, fontsize=8)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: _fmt_money(v)))
    _style_axes(ax)
    ax.legend(frameon=False, fontsize=8, labelcolor=C_MUTED, ncol=3, loc="upper center",
              bbox_to_anchor=(0.5, 1.16))
    return _finish(fig)


# ── 2. Expenses by category (donut) ─────────────────────────────────────────

def render_expense_donut(metrics: dict, labels: dict) -> Optional[bytes]:
    rows = metrics.get("expense_by_category") or []
    if not rows:
        return None

    # Label BEFORE merging. Merging on the raw name alone is not enough:
    # "Реклама" and "marketing" are different raw strings that both render as
    # "Marketing", and the legend showed two identical entries. Anything a
    # reader cannot tell apart has to be one wedge.
    lang = labels.get("_lang", "ru")
    labelled_rows = [
        {**r, "category": category_label(str(r.get("category", "")), lang)}
        for r in rows
    ]
    merged = merge_categories_by_case(labelled_rows)
    if not merged:
        return None

    # Largest first, with a long tail folded into "Прочее" so the donut stays legible.
    merged.sort(key=lambda r: r["total"], reverse=True)
    if len(merged) > 8:
        head, tail = merged[:7], merged[7:]
        merged = head + [{"category": labels["chart_other"],
                          "total": sum(r["total"] for r in tail)}]

    # Already labelled above; assign_category_colors keys off the displayed
    # name, so a category keeps its colour across both surfaces.
    names  = [r["category"] for r in merged]
    values = [r["total"] for r in merged]
    total  = sum(values) or 1.0

    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    wedges, _ = ax.pie(
        values, startangle=90, counterclock=False,
        colors=assign_category_colors(names),
        wedgeprops={"width": 0.42, "edgecolor": C_SURFACE, "linewidth": 1.5},
    )
    ax.axis("equal")
    ax.legend(
        wedges,
        [f"{n} — {v / total * 100:.1f}%" for n, v in zip(names, values)],
        frameon=False, fontsize=8, labelcolor=C_MUTED,
        loc="center left", bbox_to_anchor=(0.98, 0.5),
    )
    return _finish(fig)


def merge_categories_by_case(rows: list[dict]) -> list[dict]:
    """
    Fold category rows that differ only by case/whitespace into one segment.

    "marketing", "Marketing" and "MARKETING " are the same category and must
    not render as three wedges. Matching uses `raw.lower().strip()` — the same
    key `category_mapper.normalize_category()` derives its lookups from — so
    the two stay consistent. The first spelling encountered is kept for display.
    """
    out: dict[str, dict] = {}
    for r in rows:
        raw = str(r.get("category", "") or "")
        key = raw.lower().strip()
        if not key:
            continue
        amount = float(r.get("total", 0) or 0)
        count  = int(r.get("transaction_count", 0) or 0)
        if key in out:
            out[key]["total"] += amount
            out[key]["transaction_count"] += count
        else:
            out[key] = {"category": raw.strip(), "total": amount,
                        "transaction_count": count}
    return list(out.values())


# ── 3. Month-over-month growth (%) ──────────────────────────────────────────

def render_growth_lines(metrics: dict, labels: dict) -> Optional[bytes]:
    rows = metrics.get("mom_growth") or []
    if not rows:
        return None

    months = [str(r.get("month", "")) for r in rows]
    # *_display, not *_pct: the backend has already withheld percentages taken
    # from a near-zero base (growth_display.py). Falls back to the raw value for
    # older stored payloads that predate the display fields.
    series = [
        ("revenue_growth_display", "revenue_growth_pct", labels["chart_revenue"],  C_REVENUE),
        ("expense_growth_display", "expense_growth_pct", labels["chart_expenses"], C_EXPENSE),
        ("profit_growth_display",  "profit_growth_pct",  labels["chart_profit"],   C_PROFIT),
    ]

    fig, ax = plt.subplots(figsize=(7.2, 2.8))
    drew = False
    for key, legacy_key, label, color in series:
        # A null growth entry (no prior month, or a swing off a near-zero base)
        # must break the line, not be silently plotted as zero.
        ys = []
        for r in rows:
            v = r.get(key, r.get(legacy_key)) if key in r else r.get(legacy_key)
            ys.append(None if v is None else float(v))
        if all(y is None for y in ys):
            continue
        ax.plot(range(len(months)), ys, marker="o", markersize=4, linewidth=1.8,
                color=color, label=label)
        drew = True

    if not drew:
        plt.close(fig)
        return None

    ax.axhline(0, color=C_GRID, linewidth=1)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0f}%"))
    # Keep every month on the axis even when all of its series were withheld,
    # so a suppressed month reads as a visible gap rather than disappearing.
    ax.set_xticks(range(len(months)))
    ax.set_xticklabels(months, fontsize=8)
    ax.set_xlim(-0.35, len(months) - 0.65)
    _style_axes(ax)
    ax.legend(frameon=False, fontsize=8, labelcolor=C_MUTED, ncol=3,
              loc="upper center", bbox_to_anchor=(0.5, 1.18))

    # Points withheld from the line are reported underneath with real amounts —
    # "15 000 -> 280 000" is informative where "+1 767%" is not.
    notes = _outlier_notes(metrics, labels)
    if notes:
        fig.text(0.0, -0.06 - 0.055 * (len(notes) - 1), "\n".join(notes),
                 fontsize=7, color=C_MUTED, ha="left", va="top")
    return _finish(fig)


# ── 4. Cash-gap forecast (weekly projected balance) ─────────────────────────

def render_cashflow_forecast(metrics: dict, labels: dict) -> Optional[bytes]:
    cf = metrics.get("cashflow_forecast") or {}
    weeks = cf.get("weekly_projection") or []
    if not weeks:
        return None
    if not cf.get("balance_known"):
        # No balance, no balance line: drawing one from zero is what made a
        # trend look like a dated shortfall. Weekly net flow, as bars.
        return _render_net_flow_trend(weeks)

    xs = [f"W{w.get('week', i + 1)}" for i, w in enumerate(weeks)]
    ys = [float(w.get("projected_balance", 0) or 0) for w in weeks]

    has_risk = bool(cf.get("has_risk")) or any(y < 0 for y in ys)
    line_color = C_CASH_GAP if has_risk else C_PROFIT

    fig, ax = plt.subplots(figsize=(7.2, 2.8))
    ax.plot(xs, ys, marker="o", markersize=4, linewidth=1.8, color=line_color)
    ax.fill_between(range(len(xs)), ys, 0, color=line_color, alpha=0.10)
    ax.axhline(0, color=C_INK, linewidth=0.9)

    # The cash gap is called out in the legend, NOT next to the crossing point.
    # An inline annotation sat directly on the data line wherever the balance
    # happened to cross zero, and no offset avoids that for all shapes.
    if any(y < 0 for y in ys):
        from matplotlib.lines import Line2D

        ax.legend(
            handles=[Line2D([0], [0], color=C_CASH_GAP, linewidth=1.8,
                            label=labels["chart_cash_gap"])],
            frameon=False, fontsize=7.5, labelcolor=C_MUTED,
            loc="upper right", bbox_to_anchor=(1.0, 1.16),
        )

    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: _fmt_money(v)))
    _style_axes(ax)
    return _finish(fig)


def _render_net_flow_trend(weeks: list) -> bytes:
    """Projected weekly net flow (money in minus money out), one bar a week."""
    xs = [f"W{w.get('week', i + 1)}" for i, w in enumerate(weeks)]
    ys = []
    for w in weeks:
        net = w.get("projected_net")
        if net is None:
            net = float(w.get("projected_revenue", 0) or 0) - float(w.get("projected_expenses", 0) or 0)
        ys.append(float(net))

    fig, ax = plt.subplots(figsize=(7.2, 2.8))
    colors_ = [C_PROFIT if y >= 0 else C_CASH_GAP for y in ys]
    ax.bar(xs, ys, color=colors_, width=0.55)
    ax.axhline(0, color=C_INK, linewidth=0.9)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: _fmt_money(v)))
    _style_axes(ax)
    return _finish(fig)


def _fmt_amount(value: float) -> str:
    """Full amount with thin thousands spacing: 280000 -> '280 000'."""
    return f"{value:,.0f}".replace(",", "\u00a0")


def _outlier_notes(metrics: dict, labels: dict) -> list[str]:
    """
    One line per growth point withheld from the chart.

    Reads metrics["mom_outliers"], produced once by growth_display.py — the
    threshold rule is not re-applied here.
    """
    outliers = metrics.get("mom_outliers") or []
    metric_label = {
        "revenue":  labels["chart_revenue"],
        "expenses": labels["chart_expenses"],
        "profit":   labels["chart_profit"],
    }
    notes: list[str] = []
    for o in outliers:
        name = metric_label.get(o.get("metric", ""), o.get("metric", ""))
        notes.append(
            labels["chart_growth_outlier"].format(
                month=o.get("month", ""),
                metric=name,
                previous=_fmt_amount(float(o.get("previous", 0) or 0)),
                current=_fmt_amount(float(o.get("current", 0) or 0)),
            )
        )
    return notes
