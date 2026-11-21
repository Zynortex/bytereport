"""
PDF Generator for ByteReport.

Accepts an AIReport + optional FinancialMetrics dict and produces
a branded executive-level PDF report using ReportLab Platypus.

Font setup
----------
ReportLab built-in fonts (Helvetica, Times) support latin-1 only — Cyrillic
will render as squares. This module registers a TTF font with Cyrillic support.

Search order:
  1. <project_root>/fonts/  — bundle DejaVuSans.ttf + DejaVuSans-Bold.ttf here
  2. /usr/share/fonts/truetype/dejavu/  — Linux: apt install fonts-dejavu
  3. C:\\Windows\\Fonts\\  — Windows: Arial always present
  4. /Library/Fonts/, /System/Library/Fonts/  — macOS

Fastest setup:
  cp /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf       fonts/
  cp /usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf  fonts/
"""

import io
import logging
import os
from datetime import date
from typing import Any, Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    Image,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.flowables import KeepTogether

from app.models.report import AIReport
from app.services.ai_text import humanize
from app.services.report_copy import breakdown_lines, copy_text, format_points, score_copy
from app.services.report_layout import LIST_BLOCKS, ReportLayout
from app.utils.category_mapper import category_label
from app.services.design_tokens import (
    PDF as PDF_TOKENS,
    PRINT_ACCENT,
    PRINT_ACCENT_TINT,
    PRINT_NEGATIVE_TINT,
    PRINT_NEUTRAL_TINT,
    PRINT_SEVERITY,
    PRINT_ZONES,
    THEME,
)
from app.services.financial_engine import score_to_status_key

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Font registration
# ---------------------------------------------------------------------------

_PROJECT_FONTS = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "fonts"
)



def _matplotlib_fonts() -> Optional[str]:
    """matplotlib (a pinned requirement) ships DejaVuSans.ttf and
    DejaVuSans-Bold.ttf in mpl-data. A bare Python image (Render) has no system
    fonts at all, so without this the PDF fell back to Helvetica and every
    Cyrillic letter came out as a square. Found by path, without importing
    matplotlib."""
    import importlib.util

    spec = importlib.util.find_spec("matplotlib")
    if spec is None or not spec.submodule_search_locations:
        return None
    return os.path.join(list(spec.submodule_search_locations)[0], "mpl-data", "fonts", "ttf")


_SEARCH_DIRS = [
    _PROJECT_FONTS,
    # Before the system folders, so a local PDF uses the same face as production.
    *([d] if (d := _matplotlib_fonts()) else []),
    "/usr/share/fonts/truetype/dejavu",
    "/usr/share/fonts/dejavu",
    r"C:\Windows\Fonts",
    "/Library/Fonts",
    "/System/Library/Fonts",
]

_REGULAR_CANDIDATES = [
    "DejaVuSans.ttf",
    "arial.ttf", "Arial.ttf",
    "LiberationSans-Regular.ttf",
    "FreeSans.ttf",
]
_BOLD_CANDIDATES = [
    "DejaVuSans-Bold.ttf",
    "arialbd.ttf", "Arial Bold.ttf",
    "LiberationSans-Bold.ttf",
    "FreeSansBold.ttf",
]


def _find_font(candidates: list[str]) -> Optional[str]:
    for directory in _SEARCH_DIRS:
        for name in candidates:
            path = os.path.join(directory, name)
            if os.path.isfile(path):
                return path
    return None


def _register_fonts() -> tuple[str, str]:
    reg_path  = _find_font(_REGULAR_CANDIDATES)
    bold_path = _find_font(_BOLD_CANDIDATES)

    if not reg_path:
        logger.warning(
            "No Cyrillic-capable font found — Russian text will show as squares. "
            "Place DejaVuSans.ttf and DejaVuSans-Bold.ttf in the 'fonts/' directory, "
            "or run: apt-get install fonts-dejavu"
        )
        return "Helvetica", "Helvetica-Bold"

    pdfmetrics.registerFont(TTFont("BR-Regular", reg_path))
    pdfmetrics.registerFont(TTFont("BR-Bold", bold_path or reg_path))
    logger.debug("PDF fonts registered: regular=%s bold=%s", reg_path, bold_path)
    return "BR-Regular", "BR-Bold"


FONT_REGULAR, FONT_BOLD = _register_fonts()

# ---------------------------------------------------------------------------
# Brand palette
# ---------------------------------------------------------------------------

# All from design-tokens.json — the same file the web app reads.
# Paper gets the print palette (design-tokens.json -> pdf): the web accent is
# near-invisible on white, so headings and table headers use its darker
# relative, which clears 4.5:1 against white both as text and under white text.
BRAND_DARK   = colors.HexColor(PDF_TOKENS["header_bg"])   # dark band on a light page
BRAND_BLUE   = colors.HexColor(PRINT_ACCENT)              # the single accent, print strength
BRAND_LIGHT  = colors.HexColor(PRINT_ACCENT_TINT)         # faint tint of the accent
BRAND_BORDER = colors.HexColor(PDF_TOKENS["page_grid"])
# Text on the dark cover band: the web's secondary and dim text, made for a dark ground.
ON_DARK_SECONDARY = colors.HexColor(THEME["text_secondary"])
ON_DARK_DIM       = colors.HexColor(THEME["text_dim"])

# Severity is the ONE place a semantic colour earns its keep. Muted so it does
# not shout, but still three clearly separable hues — and deliberately outside
# the categorical ramp, which must never imply risk.
SEV_HIGH   = colors.HexColor(PRINT_SEVERITY["high"])     # brick
SEV_MEDIUM = colors.HexColor(PRINT_SEVERITY["medium"])   # dark ochre
SEV_LOW    = colors.HexColor(PRINT_SEVERITY["low"])      # slate

# 4-zone score colours. Both this and the web scoreColor() now read the SAME
# entry in design-tokens.json, so the two can no longer drift — they were
# previously two independent hardcoded copies.
_ZONE_COLORS: dict[str, colors.Color] = {
    key: colors.HexColor(PRINT_ZONES[key])
    for key in ("critical", "unstable", "stable", "excellent")
}

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm

# ---------------------------------------------------------------------------
# Multilanguage labels
# ---------------------------------------------------------------------------

PDF_LABELS: dict[str, dict[str, str]] = {
    "ru": {
        # Which language this block is. The builders receive only `labels`,
        # and humanize() needs to know which label table to use.
        "_lang": "ru",
        "cover_subtitle":     "Отчёт финансового анализа AI",
        "financial_health":   "Финансовое здоровье",
        "health_label":       "ФИНАНСОВОЕ ЗДОРОВЬЕ",
        "executive_summary":  "Резюме директора",
        "key_insights":       "Ключевые инсайты",
        "top_risks":          "Топ риски",
        "growth_opps":        "Возможности роста",
        "expense_analysis":   "Анализ расходов",
        "problem_cats":       "Проблемные категории",
        "efficient_cats":     "Эффективные категории",
        "anomalies":          "Обнаруженные аномалии",
        "cashflow":           "Анализ денежного потока",
        "forecast":           "Прогноз 30–90 дней",
        "priority_actions":   "Приоритетные действия",
        "col_risk":           "Риск",
        "col_impact":         "Влияние на бизнес",
        "col_recommendation": "Рекомендация",
        "col_opportunity":    "Возможность",
        "col_pot_impact":     "Потенциальное влияние",
        "col_action":         "Действие",
        "col_severity":       "Серьёзность",
        "col_category":       "Категория",
        "col_issue":          "Проблема",
        "col_explanation":    "Объяснение",
        "label_status":       "Статус",
        "label_warn_level":   "Уровень риска",
        "label_outlook":      "Перспектива",
        "label_confidence":   "Уверенность",
        "label_expected":     "Ожидаемый результат",
        "generated_by":       "Создано ByteReport AI",
        "charts_section":     "Графики и динамика",
        "chart_monthly":       "Выручка, расходы и прибыль по месяцам",
        "chart_expenses_by_cat": "Структура расходов по категориям",
        "chart_growth":        "Рост месяц к месяцу",
        "chart_forecast":      "Прогноз денежного потока по неделям",
        "chart_revenue":       "Выручка",
        "chart_expenses":      "Расходы",
        "chart_profit":        "Прибыль",
        "chart_other":         "Прочее",
        "chart_cash_gap":      "кассовый разрыв",
        "no_categories_note": "Категории расходов недоступны для этого источника данных. Для детального анализа загрузите файл с категориями.",
        "partial_categories_note": "Разбивка построена на основе {percent}% транзакций с указанной категорией — не всех данных.",
        "chart_growth_outlier": "{month}: {metric} — рост с {previous} до {current}. В процентах не показан: база предыдущего месяца близка к нулю.",
        "page":               "Стр.",
    },
    "uz": {
        # Which language this block is. The builders receive only `labels`,
        # and humanize() needs to know which label table to use.
        "_lang": "uz",
        "cover_subtitle":     "AI Молиявий Таҳлил Ҳисоботи",
        "financial_health":   "Молиявий соғлиқ",
        "health_label":       "МОЛИЯВИЙ СОҒЛИҚ",
        "executive_summary":  "Раҳбар хулосаси",
        "key_insights":       "Муҳим топилмалар",
        "top_risks":          "Асосий хавфлар",
        "growth_opps":        "Ўсиш имкониятлари",
        "expense_analysis":   "Харажатлар таҳлили",
        "problem_cats":       "Муаммоли категориялар",
        "efficient_cats":     "Самарали категориялар",
        "anomalies":          "Аниқланган аномалиялар",
        "cashflow":           "Нақд пул оқими таҳлили",
        "forecast":           "30–90 кунлик прогноз",
        "priority_actions":   "Устувор чора-тадбирлар",
        "col_risk":           "Хавф",
        "col_impact":         "Бизнесга таъсири",
        "col_recommendation": "Тавсия",
        "col_opportunity":    "Имконият",
        "col_pot_impact":     "Потенциал таъсир",
        "col_action":         "Чора",
        "col_severity":       "Жиддийлик",
        "col_category":       "Категория",
        "col_issue":          "Муаммо",
        "col_explanation":    "Изоҳ",
        "label_status":       "Ҳолат",
        "label_warn_level":   "Хавф даражаси",
        "label_outlook":      "Истиқбол",
        "label_confidence":   "Ишончлилик",
        "label_expected":     "Кутилаётган натижа",
        "generated_by":       "ByteReport AI томонидан яратилган",
        "charts_section":     "Графиклар ва динамика",
        "chart_monthly":       "Ойлар бўйича тушум, харажат ва фойда",
        "chart_expenses_by_cat": "Харажатларнинг категориялар бўйича тузилиши",
        "chart_growth":        "Ойма-ой ўсиш",
        "chart_forecast":      "Ҳафталар бўйича пул оқими прогнози",
        "chart_revenue":       "Тушум",
        "chart_expenses":      "Харажатлар",
        "chart_profit":        "Фойда",
        "chart_other":         "Бошқа",
        "chart_cash_gap":      "нақд пул тақчиллиги",
        "no_categories_note": "Ушбу маълумот манбаи учун харажат категориялари мавжуд эмас. Батафсил таҳлил учун категориялари белгиланган файлни юкланг.",
        "partial_categories_note": "Тақсимот категорияси кўрсатилган операцияларнинг {percent}% асосида тузилган — барча маълумотлар асосида эмас.",
        "chart_growth_outlier": "{month}: {metric} — {previous} дан {current} гача ўсди. Фоизда кўрсатилмади: олдинги ой базаси нолга яқин.",
        "page":               "Бет",
    },
    "en": {
        # Which language this block is. The builders receive only `labels`,
        # and humanize() needs to know which label table to use.
        "_lang": "en",
        "cover_subtitle":     "AI Financial Analysis Report",
        "financial_health":   "Financial Health Score",
        "health_label":       "FINANCIAL HEALTH SCORE",
        "executive_summary":  "Executive Summary",
        "key_insights":       "Key Insights",
        "top_risks":          "Top Risks",
        "growth_opps":        "Growth Opportunities",
        "expense_analysis":   "Expense Analysis",
        "problem_cats":       "Problem Categories",
        "efficient_cats":     "Efficient Categories",
        "anomalies":          "Anomalies Detected",
        "cashflow":           "Cash Flow Analysis",
        "forecast":           "30–90 Day Forecast",
        "priority_actions":   "Priority Actions",
        "col_risk":           "Risk",
        "col_impact":         "Business Impact",
        "col_recommendation": "Recommendation",
        "col_opportunity":    "Opportunity",
        "col_pot_impact":     "Potential Impact",
        "col_action":         "Action",
        "col_severity":       "Severity",
        "col_category":       "Category",
        "col_issue":          "Issue",
        "col_explanation":    "Explanation",
        "label_status":       "Status",
        "label_warn_level":   "Warning Level",
        "label_outlook":      "Outlook",
        "label_confidence":   "Confidence",
        "label_expected":     "Expected",
        "generated_by":       "Generated by ByteReport AI",
        "charts_section":     "Charts and trends",
        "chart_monthly":       "Revenue, expenses and profit by month",
        "chart_expenses_by_cat": "Expense structure by category",
        "chart_growth":        "Month-over-month growth",
        "chart_forecast":      "Weekly cash flow forecast",
        "chart_revenue":       "Revenue",
        "chart_expenses":      "Expenses",
        "chart_profit":        "Profit",
        "chart_other":         "Other",
        "chart_cash_gap":      "cash gap",
        "no_categories_note": "Expense categories are unavailable for this data source. Upload a file that includes categories for a detailed breakdown.",
        "partial_categories_note": "This breakdown is based on {percent}% of transactions that carry a category — not on the full dataset.",
        "chart_growth_outlier": "{month}: {metric} — grew from {previous} to {current}. Percentage omitted: the prior-month base is near zero.",
        "page":               "Page",
    },
}


# ---------------------------------------------------------------------------
# Style helpers
# ---------------------------------------------------------------------------

def _styles() -> dict:
    def ps(name, bold=False, **kw) -> ParagraphStyle:
        return ParagraphStyle(name, fontName=FONT_BOLD if bold else FONT_REGULAR, **kw)

    return {
        "cover_title": ps("cover_title", bold=True,
            fontSize=28, textColor=colors.white, alignment=TA_LEFT, leading=34),
        "cover_sub": ps("cover_sub",
            fontSize=12, textColor=ON_DARK_SECONDARY, alignment=TA_LEFT, leading=16),
        "cover_meta": ps("cover_meta",
            fontSize=9, textColor=ON_DARK_DIM, alignment=TA_LEFT),
        "section_header": ps("section_header", bold=True,
            fontSize=13, textColor=BRAND_DARK, spaceBefore=14, spaceAfter=6, leading=16),
        "body": ps("body",
            fontSize=9, textColor=colors.HexColor(PDF_TOKENS["page_ink"]), leading=14, spaceAfter=4),
        "body_bold": ps("body_bold", bold=True,
            fontSize=9, textColor=BRAND_DARK, leading=14),
        "small": ps("small",
            fontSize=8, textColor=colors.HexColor(PDF_TOKENS["page_muted"]), leading=12),
        "table_header": ps("table_header", bold=True,
            fontSize=8.5, textColor=colors.white, alignment=TA_LEFT, leading=11),
        "table_cell": ps("table_cell",
            fontSize=8.5, textColor=BRAND_DARK, leading=12),
        "priority_num": ps("priority_num", bold=True,
            fontSize=18, textColor=BRAND_BLUE, alignment=TA_CENTER, leading=22),
    }


# ---------------------------------------------------------------------------
# Inline style factory (for one-off ParagraphStyles inside builders)
# ---------------------------------------------------------------------------

def _ps(name: str, bold: bool = False, **kw) -> ParagraphStyle:
    return ParagraphStyle(name, fontName=FONT_BOLD if bold else FONT_REGULAR, **kw)


# ---------------------------------------------------------------------------
# Severity / score helpers
# ---------------------------------------------------------------------------

def _sev_color(severity: str) -> colors.Color:
    return {"high": SEV_HIGH, "medium": SEV_MEDIUM, "low": SEV_LOW}.get(
        severity.lower(), SEV_LOW
    )


def _score_color(score: int) -> colors.Color:
    return _ZONE_COLORS[score_to_status_key(score)]


# ---------------------------------------------------------------------------
# Page template (header + footer on every page)
# ---------------------------------------------------------------------------

class _BrandedPage(PageTemplate):
    def __init__(self, doc_ref):
        frame = Frame(
            MARGIN, MARGIN + 8 * mm,
            PAGE_W - 2 * MARGIN, PAGE_H - 2 * MARGIN - 20 * mm,
            id="main", leftPadding=0, bottomPadding=0, rightPadding=0, topPadding=0,
        )
        super().__init__("branded", [frame])

    def beforeDrawPage(self, canvas, doc):
        canvas.saveState()
        labels = getattr(doc, "pdf_labels", PDF_LABELS["ru"])

        # Top bar
        canvas.setFillColor(BRAND_DARK)
        canvas.rect(0, PAGE_H - 14 * mm, PAGE_W, 14 * mm, fill=1, stroke=0)

        canvas.setFillColor(colors.white)
        canvas.setFont(FONT_BOLD, 10)
        canvas.drawString(MARGIN, PAGE_H - 9.5 * mm, "ByteReport")
        canvas.setFont(FONT_REGULAR, 8)
        canvas.setFillColor(ON_DARK_SECONDARY)
        canvas.drawRightString(
            PAGE_W - MARGIN, PAGE_H - 9.5 * mm,
            f"AI Financial Report  •  {doc.report_meta.get('business_name', '')}",
        )

        # Footer
        canvas.setFillColor(colors.HexColor(PDF_TOKENS["page_muted"]))
        canvas.setFont(FONT_REGULAR, 7.5)
        canvas.drawCentredString(
            PAGE_W / 2, 9 * mm,
            f"{labels['generated_by']}  •  {doc.report_meta.get('generated_date', '')}  •  {labels['page']} {doc.page}",
        )
        canvas.setStrokeColor(BRAND_BORDER)
        canvas.setLineWidth(0.5)
        canvas.line(MARGIN, 13 * mm, PAGE_W - MARGIN, 13 * mm)

        canvas.restoreState()


# ---------------------------------------------------------------------------
# Section helpers
# ---------------------------------------------------------------------------

def _divider() -> HRFlowable:
    return HRFlowable(width="100%", thickness=0.5, color=BRAND_BORDER, spaceAfter=8, spaceBefore=2)


def _section_title(text: str, st: dict) -> list:
    return [Paragraph(text.upper(), st["section_header"]), _divider()]


def _base_table_style(header_bg: colors.Color) -> TableStyle:
    return TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  header_bg),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, BRAND_LIGHT]),
        ("GRID",          (0, 0), (-1, -1), 0.3, BRAND_BORDER),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 7),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 7),
        ("ROUNDEDCORNERS", [3]),
    ])


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _build_cover(report: AIReport, meta: dict, st: dict, labels: dict) -> list:
    business = meta.get("business_name") or "Financial Report"
    period   = meta.get("period") or meta.get("generated_date", "")
    btype    = meta.get("business_type") or ""

    rows = [
        [Paragraph("BYTEREPORT", _ps("br_logo", bold=True, fontSize=11, textColor=BRAND_BLUE))],
        [Spacer(1, 6 * mm)],
        [Paragraph(labels["cover_subtitle"], st["cover_sub"])],
        [Paragraph(business, st["cover_title"])],
        [Spacer(1, 3 * mm)],
        [Paragraph(f"{btype}{'  •  ' if btype else ''}{period}", st["cover_meta"])],
    ]
    table = Table(rows, colWidths=[PAGE_W - 2 * MARGIN])
    table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), BRAND_DARK),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING",   (0, 0), (-1, -1), 14),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 14),
        ("ROUNDEDCORNERS", [4]),
    ]))
    return [table, Spacer(1, 8 * mm)]


def _build_health_score(report: AIReport, st: dict, labels: dict, metrics: Optional[dict] = None) -> list:
    score = report.financial_health_score
    color = _score_color(score.score)

    lang = labels["_lang"]
    muted = colors.HexColor(PDF_TOKENS["page_muted"])
    score_cell = Table([
        [Paragraph(str(score.score), _ps("sc_num", bold=True, fontSize=44, textColor=color, alignment=TA_CENTER, leading=50))],
        [Paragraph(score.status.upper(), _ps("sc_st", bold=True, fontSize=11, textColor=color, alignment=TA_CENTER, leading=14))],
        [Spacer(1, 2)],
        [Paragraph(labels["health_label"], _ps("sc_lb", fontSize=7.5, textColor=muted, alignment=TA_CENTER))],
        # The zone reads as a verdict on its own. This line, directly under it,
        # says what the verdict is drawn from — a cash-flow signal, not an
        # audit — and it is the same text the web card shows.
        [Paragraph(score_copy("caption", lang), _ps("sc_cap", fontSize=7, textColor=muted, alignment=TA_CENTER, leading=9))],
    ], colWidths=[50 * mm])
    score_cell.setStyle(TableStyle([
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("BACKGROUND",    (0, 0), (-1, -1), BRAND_LIGHT),
        ("BOX",           (0, 0), (-1, -1), 1.5, color),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("ROUNDEDCORNERS", [4]),
    ]))

    row = Table(
        [[score_cell, Paragraph(score.reasoning, st["body"])]],
        colWidths=[54 * mm, PAGE_W - 2 * MARGIN - 60 * mm],
    )
    row.setStyle(TableStyle([
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",  (1, 0), (1, 0),   12),
        ("RIGHTPADDING", (0, 0), (0, 0),   0),
    ]))

    # Scope, stated next to the score rather than in a footnote. A statement-
    # based analysis cannot see receivables, payables, cash outside the account
    # or accruals; that is its coverage, not a flaw, and saying so here is what
    # keeps the number from being read with an authority it does not claim.
    scope = Table([[
        Paragraph(score_copy("scope_title", lang), _ps("sc_sct", bold=True, fontSize=7.5, textColor=muted)),
        Paragraph(score_copy("scope", lang), _ps("sc_sc", fontSize=8, textColor=muted, leading=10.5)),
    ]], colWidths=[34 * mm, PAGE_W - 2 * MARGIN - 34 * mm])
    scope.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("LINEABOVE",     (0, 0), (-1, 0),  0.5, colors.HexColor(PDF_TOKENS["page_grid"])),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING",   (0, 0), (0, 0),   0),
    ]))
    breakdown = _score_breakdown_table(metrics, score.score, lang, muted)
    return [*_section_title(labels["financial_health"], st), row, Spacer(1, 3 * mm),
            *breakdown, scope, Spacer(1, 6 * mm)]


def _score_breakdown_table(metrics: Optional[dict], score: int, lang: str, muted) -> list:
    """
    The five checks behind the score, as the engine computed them — the same
    sentences the web card shows (report-copy.json). Nothing here comes from
    the AI. Absent for reports saved before the engine kept the breakdown.
    """
    items = (metrics or {}).get("health_breakdown") or []
    if not items:
        return []
    ink = colors.HexColor(PDF_TOKENS["page_ink"])
    rows = [[
        Paragraph(copy_text("score_breakdown", "title", lang), _ps("sb_t", bold=True, fontSize=8.5, textColor=ink)),
        Paragraph(copy_text("score_breakdown", "intro", lang).format(score=score),
                  _ps("sb_i", fontSize=8, textColor=muted, leading=10.5)),
    ]]
    for points, text in breakdown_lines(items, lang):
        rows.append([
            Paragraph(format_points(points), _ps("sb_p", bold=True, fontSize=9, textColor=ink if points else muted, alignment=TA_LEFT)),
            Paragraph(text, _ps("sb_x", fontSize=8.5, textColor=ink, leading=11)),
        ])
    from app.services.financial_engine import score_from_breakdown
    if score_from_breakdown(items)[1]:
        rows.append(["", Paragraph(copy_text("score_breakdown", "capped", lang), _ps("sb_c", fontSize=8, textColor=muted))])
    table = Table(rows, colWidths=[34 * mm, PAGE_W - 2 * MARGIN - 34 * mm])
    table.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("LINEABOVE",     (0, 0), (-1, 0),  0.5, colors.HexColor(PDF_TOKENS["page_grid"])),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (0, -1),  0),
    ]))
    return [table, Spacer(1, 3 * mm)]


def _build_executive_summary(report: AIReport, st: dict, labels: dict) -> list:
    return [
        *_section_title(labels["executive_summary"], st),
        Paragraph(report.executive_summary, st["body"]),
        Spacer(1, 6 * mm),
    ]


def _build_key_insights(report: AIReport, st: dict, labels: dict) -> list:
    if not report.key_insights:
        return []

    col_w = (PAGE_W - 2 * MARGIN - 4 * mm) / 3
    rows, chunk = [], []

    for i, ins in enumerate(report.key_insights):
        sev_color = _sev_color(ins.severity)
        cell = Table([
            [Paragraph(ins.severity.upper(), _ps("ins_tag", bold=True, fontSize=7, textColor=sev_color))],
            [Paragraph(ins.title, st["body_bold"])],
            [Spacer(1, 2)],
            [Paragraph(ins.explanation, st["small"])],
        ], colWidths=[col_w - 8])
        cell.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), BRAND_LIGHT),
            ("LEFTPADDING",   (0, 0), (-1, -1), 8),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
            ("TOPPADDING",    (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("LINEABOVE",     (0, 0), (-1, 0),  2.5, sev_color),
            ("ROUNDEDCORNERS", [3]),
        ]))
        chunk.append(cell)
        if len(chunk) == 3 or i == len(report.key_insights) - 1:
            while len(chunk) < 3:
                chunk.append(Spacer(col_w, 1))
            rows.append(chunk[:])
            chunk = []

    elements = [*_section_title(labels["key_insights"], st)]
    for row in rows:
        t = Table([row], colWidths=[col_w, col_w, col_w])
        t.setStyle(TableStyle([
            ("VALIGN",       (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING",  (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ]))
        elements += [t, Spacer(1, 4)]
    elements.append(Spacer(1, 6 * mm))
    return elements


def _build_risks(report: AIReport, st: dict, labels: dict) -> list:
    if not report.top_risks:
        return []
    col_w = PAGE_W - 2 * MARGIN
    header = ["#", labels["col_risk"], labels["col_impact"], labels["col_recommendation"]]
    data = [[Paragraph(h, st["table_header"]) for h in header]]
    for i, r in enumerate(report.top_risks, 1):
        data.append([
            Paragraph(str(i), st["body_bold"]),
            Paragraph(r.risk, st["table_cell"]),
            Paragraph(r.impact, st["table_cell"]),
            Paragraph(r.recommendation, st["table_cell"]),
        ])
    t = Table(data, colWidths=[8 * mm, col_w * 0.22, col_w * 0.28, col_w * 0.44])
    t.setStyle(_base_table_style(header_bg=BRAND_DARK))
    return [*_section_title(labels["top_risks"], st), t, Spacer(1, 6 * mm)]


def _build_opportunities(report: AIReport, st: dict, labels: dict) -> list:
    if not report.growth_opportunities:
        return []
    col_w = PAGE_W - 2 * MARGIN
    header = [labels["col_opportunity"], labels["col_pot_impact"], labels["col_action"]]
    data = [[Paragraph(h, st["table_header"]) for h in header]]
    for o in report.growth_opportunities:
        data.append([
            Paragraph(o.opportunity, st["table_cell"]),
            Paragraph(o.potential_impact, st["table_cell"]),
            Paragraph(o.action, st["table_cell"]),
        ])
    t = Table(data, colWidths=[col_w * 0.28, col_w * 0.22, col_w * 0.5])
    t.setStyle(_base_table_style(header_bg=BRAND_BLUE))
    return [*_section_title(labels["growth_opps"], st), t, Spacer(1, 6 * mm)]


def _category_level(metrics: Optional[dict]) -> str:
    """
    Read the three-level category signal off the metrics dict.

    Falls back to the legacy boolean, then to "full", so PDFs generated from
    older stored payloads keep rendering exactly as they used to.
    """
    if not metrics:
        return "full"
    level = metrics.get("category_reliability")
    if level in ("full", "partial", "none"):
        return level
    return "full" if metrics.get("has_reliable_categories", True) else "none"


def _coverage_percent(metrics: Optional[dict]) -> int:
    return int(round(float((metrics or {}).get("category_coverage", 1.0)) * 100))


def _build_expense_analysis(
    report: AIReport, st: dict, labels: dict, metrics: Optional[dict] = None
) -> list:
    """
    Category breakdown, or an honest note when categories are unusable.

    Reads the same has_reliable_categories flag as the AI prompt, the donut
    chart and the web UI — the condition is evaluated once upstream, not
    re-derived per surface.
    """
    level = _category_level(metrics)
    if level == "none":
        logger.info("PDF: expense-analysis section replaced with no-category note")
        return [
            *_section_title(labels["expense_analysis"], st),
            Paragraph(labels["no_categories_note"], st["small"]),
            Spacer(1, 6 * mm),
        ]

    partial_note: list = []
    if level == "partial":
        percent = _coverage_percent(metrics)
        logger.info("PDF: expense-analysis shown with partial caveat (%d%%)", percent)
        partial_note = [
            Paragraph(
                labels["partial_categories_note"].format(percent=percent),
                _ps("partial_cat", fontSize=8, textColor=SEV_MEDIUM, leading=11),
            ),
            Spacer(1, 3 * mm),
        ]

    ea = report.expense_analysis
    col_w = (PAGE_W - 2 * MARGIN - 8 * mm) / 2

    def _pill_list(items: list, bg: colors.Color) -> Table:
        rows = [[Paragraph(f"• {item}", st["small"])] for item in items] or \
               [[Paragraph("—", st["small"])]]
        t = Table(rows, colWidths=[col_w - 10])
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), bg),
            ("LEFTPADDING",   (0, 0), (-1, -1), 8),
            ("TOPPADDING",    (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("ROUNDEDCORNERS", [3]),
        ]))
        return t

    grid = Table([
        [
            Paragraph(labels["problem_cats"],  _ps("hdr_r", bold=True, fontSize=8.5, textColor=SEV_HIGH)),
            Paragraph(labels["efficient_cats"], _ps("hdr_g", bold=True, fontSize=8.5, textColor=SEV_LOW)),
        ],
        [
            _pill_list(ea.problem_categories,  colors.HexColor(PRINT_NEGATIVE_TINT)),
            _pill_list(ea.efficient_categories, colors.HexColor(PRINT_NEUTRAL_TINT)),
        ],
    ], colWidths=[col_w, col_w])
    grid.setStyle(TableStyle([
        ("VALIGN",       (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING",   (0, 0), (-1, -1), 0),
    ]))

    elements = [*_section_title(labels["expense_analysis"], st), *partial_note, grid]
    if ea.notes:
        elements += [Spacer(1, 4), Paragraph(ea.notes, st["small"])]
    elements.append(Spacer(1, 6 * mm))
    return elements


def _build_anomalies(report: AIReport, st: dict, labels: dict) -> list:
    if not report.anomalies:
        return []
    col_w = PAGE_W - 2 * MARGIN
    header = [labels["col_severity"], labels["col_category"], labels["col_issue"], labels["col_explanation"]]
    data = [[Paragraph(h, st["table_header"]) for h in header]]
    for a in report.anomalies:
        sev_color = _sev_color(a.severity)
        badge = Table([[Paragraph(
            a.severity.upper(),
            _ps("a_sev", bold=True, fontSize=7.5, textColor=sev_color, alignment=TA_CENTER),
        )]])
        badge.setStyle(TableStyle([
            ("BOX",           (0, 0), (-1, -1), 1, sev_color),
            ("TOPPADDING",    (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("ROUNDEDCORNERS", [3]),
        ]))
        data.append([
            badge,
            # The reader gets the category NAME; the key stays the identity
            # used in code and in the charts.
            Paragraph(category_label(a.category, labels["_lang"]), st["table_cell"]),
            Paragraph(a.issue,    st["table_cell"]),
            Paragraph(a.explanation, st["small"]),
        ])
    # 16 mm forced 'Серьёзность' and 'MEDIUM' to wrap mid-word. The header is
    # the binding constraint: 19.3 mm of text at 8.5 pt bold plus 14 pt of cell
    # padding needs 24.2 mm, so 26 mm leaves a little slack for the Uzbek and
    # English headers too. The width comes off the explanation column, which is
    # free-flowing prose and absorbs it without reflowing awkwardly.
    _sev_w = 26 * mm
    t = Table(data, colWidths=[_sev_w, col_w * 0.18, col_w * 0.22,
                               col_w * 0.5 - (_sev_w - 16 * mm)])
    # The print accent, like every other table header (not a library default).
    t.setStyle(_base_table_style(header_bg=BRAND_BLUE))
    return [*_section_title(labels["anomalies"], st), t, Spacer(1, 6 * mm)]


def _build_cashflow(report: AIReport, st: dict, labels: dict) -> list:
    cf = report.cash_flow_analysis
    warn_color = _sev_color(cf.warning_level)
    lang = labels["_lang"]
    # humanize(), not the raw field: the model sometimes answers these prose
    # fields with a bare token, and "Статус: critical" reached a real report.
    # A value it does not recognise is passed through as the sentence it is.
    block = Table([[
        Paragraph(labels["label_status"],     st["small"]),
        Paragraph(humanize(cf.status, lang),  _ps("cf_st", bold=True, fontSize=11, textColor=warn_color)),
        Paragraph(labels["label_warn_level"], st["small"]),
        Paragraph(humanize(cf.warning_level, lang, kind="level").upper(),
                                              _ps("cf_wl", bold=True, fontSize=10, textColor=warn_color)),
    ]], colWidths=[22 * mm, 50 * mm, 30 * mm, 30 * mm])
    block.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND",    (0, 0), (-1, -1), BRAND_LIGHT),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LINEABOVE",     (0, 0), (-1, 0),  2.5, warn_color),
        ("ROUNDEDCORNERS", [3]),
    ]))
    return [
        *_section_title(labels["cashflow"], st),
        block, Spacer(1, 4),
        Paragraph(cf.summary, st["body"]),
        Spacer(1, 6 * mm),
    ]


def _build_forecast(report: AIReport, st: dict, labels: dict) -> list:
    fc = report.forecast
    conf_color = {"high": SEV_LOW, "medium": SEV_MEDIUM, "low": SEV_HIGH}.get(
        fc.confidence.lower(), SEV_MEDIUM
    )
    lang = labels["_lang"]
    header_row = Table([[
        Paragraph(labels["label_outlook"],    st["small"]),
        Paragraph(humanize(fc.outlook, lang), _ps("fc_out",  bold=True, fontSize=10, textColor=BRAND_BLUE)),
        Paragraph(labels["label_confidence"], st["small"]),
        Paragraph(humanize(fc.confidence, lang).upper(),
                                              _ps("fc_conf", bold=True, fontSize=9, textColor=conf_color)),
    ]], colWidths=[28 * mm, 59 * mm, 25 * mm, 30 * mm])
    header_row.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND",    (0, 0), (-1, -1), BRAND_LIGHT),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LINEABOVE",     (0, 0), (-1, 0),  2.5, BRAND_BLUE),
        ("ROUNDEDCORNERS", [3]),
    ]))
    return [
        *_section_title(labels["forecast"], st),
        header_row, Spacer(1, 4),
        Paragraph(fc.summary, st["body"]),
        Spacer(1, 6 * mm),
    ]


def _build_priority_actions(report: AIReport, st: dict, labels: dict) -> list:
    if not report.priority_actions:
        return []
    col_w = PAGE_W - 2 * MARGIN
    elements = [*_section_title(labels["priority_actions"], st)]

    for action in sorted(report.priority_actions, key=lambda a: a.priority):
        content = Table([
            [Paragraph(action.action, st["body_bold"])],
            [Paragraph(f"{labels['label_expected']}: {action.expected_result}", st["small"])],
        ], colWidths=[col_w - 22 * mm])
        content.setStyle(TableStyle([
            ("TOPPADDING",    (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        row = Table(
            [[Paragraph(str(action.priority), st["priority_num"]), content]],
            colWidths=[18 * mm, col_w - 22 * mm],
        )
        row.setStyle(TableStyle([
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("BACKGROUND",    (0, 0), (-1, -1), BRAND_LIGHT),
            ("LEFTPADDING",   (0, 0), (-1, -1), 8),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 12),
            ("TOPPADDING",    (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LINEBEFORE",    (0, 0), (0, -1),  3, BRAND_BLUE),
            ("ROUNDEDCORNERS", [3]),
        ]))
        elements.append(KeepTogether([row, Spacer(1, 4)]))

    elements.append(Spacer(1, 4 * mm))
    return elements


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

# Usable content width, so a chart never overflows the frame.
_CHART_W = PAGE_W - 2 * MARGIN


def _chart_flowable(png: bytes, title: str, st: dict, caption: Optional[str] = None) -> list:
    """Wrap PNG bytes in a titled, width-fitted Image flowable, with an optional note."""
    reader = ImageReader(io.BytesIO(png))
    iw, ih = reader.getSize()
    height = _CHART_W * ih / iw
    img = Image(io.BytesIO(png), width=_CHART_W, height=height)
    parts = [Paragraph(title, st["body_bold"]), Spacer(1, 2 * mm), img]
    if caption:
        parts += [Spacer(1, 2 * mm), Paragraph(caption, st["small"])]
    parts.append(Spacer(1, 6 * mm))
    return [KeepTogether(parts)]


def _forecast_copy(metrics: dict, labels: dict) -> tuple[str, str]:
    """
    Title and note for the cash forecast — the same lines the web shows, from
    report-copy.json. Without a balance the chart is a net-flow TREND and the
    note says why there is no date or amount.
    """
    lang = labels["_lang"]
    cf = metrics.get("cashflow_forecast") or {}
    if cf.get("balance_known"):
        amount = f"{float(cf.get('closing_balance') or 0):,.0f}".replace(",", "\u00a0")
        return (copy_text("cash_forecast", "title_balance", lang),
                copy_text("cash_forecast", "from_balance", lang).format(amount=amount))
    return (copy_text("cash_forecast", "title_trend", lang),
            copy_text("cash_forecast", "needs_balance", lang) + " "
            + copy_text("cash_forecast", "needs_balance_action", lang))


# Each chart is its own section so a layout can place or hide it on its own.
# The old single _build_charts() rendered all four under one heading in a fixed
# spot, which is exactly the constraint the layout feature removes.
_CHART_SPECS: dict[str, tuple[str, str]] = {
    # block id -> (chart_renderer function name, label key)
    "chart_monthly":    ("render_monthly_bars",      "chart_monthly"),
    "chart_categories": ("render_expense_donut",     "chart_expenses_by_cat"),
    "chart_growth":     ("render_growth_lines",      "chart_growth"),
    "chart_forecast":   ("render_cashflow_forecast", "chart_forecast"),
}


def _build_chart(block_id: str, metrics: Optional[dict], st: dict, labels: dict) -> list:
    """
    One chart, or nothing.

    A chart with no data is skipped silently — that is a legitimate state (a
    single-month report has no month-over-month growth). A chart that *fails*
    is logged with a traceback and skipped, so a broken chart degrades the PDF
    by one image instead of failing the whole download.
    """
    if not metrics:
        return []
    fn_name, label_key = _CHART_SPECS[block_id]

    # Same flag the AI prompt and the web UI use — computed once in
    # category_coverage.py, never re-derived here.
    if block_id == "chart_categories" and _category_level(metrics) == "none":
        logger.info("PDF: expense donut skipped - categories unreliable")
        return []

    from app.services import chart_renderer as cr

    try:
        png = getattr(cr, fn_name)(metrics, labels)
    except Exception:
        logger.exception("PDF chart %r failed to render", block_id)
        return []
    if not png:
        logger.info("PDF chart %r skipped: no data for it in metrics", block_id)
        return []
    logger.debug("PDF chart %r rendered (%d bytes)", block_id, len(png))
    if block_id == "chart_forecast":
        title, caption = _forecast_copy(metrics, labels)
        return _chart_flowable(png, title, st, caption)
    return _chart_flowable(png, labels[label_key], st)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _build_charts(metrics: Optional[dict], st: dict, labels: dict) -> list:
    """
    All four charts in default order under one heading.

    Kept for callers that want the old behaviour; generate_pdf itself no longer
    uses it — each chart is placed by the layout individually.
    """
    if not metrics:
        logger.info("PDF charts skipped: no metrics supplied")
        return []
    elements: list = []
    for block_id in _CHART_SPECS:
        elements += _build_chart(block_id, metrics, st, labels)
    if elements:
        elements = [*_section_title(labels["charts_section"], st), *elements]
    return elements


def _apply_hidden_items(report: AIReport, layout: ReportLayout) -> AIReport:
    """
    A copy of the report with the layout's hidden list entries removed.

    Copy, not mutation: the same report object is what the caller keeps and
    may render again with a different layout.
    """
    if not layout.hidden_items:
        return report
    data = report.model_dump()
    for block_id, field in LIST_BLOCKS.items():
        if block_id in layout.hidden_items and isinstance(data.get(field), list):
            data[field] = layout.keep_items(block_id, data[field])
    return AIReport.model_validate(data)


def generate_pdf(
    report: AIReport,
    business_name: Optional[str] = None,
    business_type: Optional[str] = None,
    period: Optional[str] = None,
    metrics: Optional[dict] = None,
    language: str = "ru",
    layout: Optional[ReportLayout] = None,
) -> bytes:
    """
    Generate a branded PDF. Returns raw bytes for StreamingResponse.

    `layout` decides which sections appear and in what order. There is no
    order baked into this function any more: the accountant's arrangement on
    the web IS the PDF, which is the entire reason the arrangement exists.
    """
    labels = PDF_LABELS.get(language, PDF_LABELS["ru"])
    buf  = io.BytesIO()
    meta = {
        "business_name":  business_name or "Business Report",
        "business_type":  business_type or "",
        "period":         period or "",
        "generated_date": date.today().strftime("%d %B %Y"),
    }

    doc = BaseDocTemplate(
        buf, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN + 14 * mm, bottomMargin=MARGIN + 14 * mm,
    )
    doc.report_meta = meta
    doc.pdf_labels  = labels
    doc.addPageTemplates([_BrandedPage(doc)])

    st = _styles()
    layout = layout or ReportLayout.default()

    # Hidden ITEMS are applied to a copy of the report before any section is
    # built, so a section builder never has to know about layouts — it renders
    # whatever list it is given.
    shown = _apply_hidden_items(report, layout)

    builders: dict[str, Any] = {
        "health_score":         lambda: _build_health_score(shown, st, labels, metrics),
        "executive_summary":    lambda: _build_executive_summary(shown, st, labels),
        "key_insights":         lambda: _build_key_insights(shown, st, labels),
        "top_risks":            lambda: _build_risks(shown, st, labels),
        "growth_opportunities": lambda: _build_opportunities(shown, st, labels),
        "expense_analysis":     lambda: _build_expense_analysis(shown, st, labels, metrics),
        "anomalies":            lambda: _build_anomalies(shown, st, labels),
        "cash_flow_analysis":   lambda: _build_cashflow(shown, st, labels),
        "forecast":             lambda: _build_forecast(shown, st, labels),
        "priority_actions":     lambda: _build_priority_actions(shown, st, labels),
        **{cid: (lambda c=cid: _build_chart(c, metrics, st, labels)) for cid in _CHART_SPECS},
    }

    story: list = _build_cover(report, meta, st, labels)
    for block_id in layout.visible_ids(for_pdf=True):
        build = builders.get(block_id)
        if build is None:
            # A web-only section, or one this generator has not learnt yet.
            continue
        story += build()
    logger.info(
        "PDF built with %d visible section(s): %s",
        len(layout.visible_ids(for_pdf=True)), ", ".join(layout.visible_ids(for_pdf=True)),
    )

    doc.build(story)
    return buf.getvalue()
