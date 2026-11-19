"""
Report sections: show/hide, reorder, hide single list entries.

The feature is the PDF. An accountant arranges the report for one client and
hands over the file; if the generator kept its own fixed order the web
arrangement would be cosmetic. So the tests here build real PDFs and read the
section order back out of them.
"""

import io
import json
import os
import re

import pdfplumber
import pytest
from pydantic import ValidationError

from app.models.report import AIReport
from app.services.ai_text import strip_positional
from app.services.pdf_generator import PDF_LABELS, generate_pdf
from app.services.report_layout import (
    BLOCK_IDS,
    LIST_BLOCKS,
    REGISTRY,
    ReportLayout,
    block_label,
    coerce_layout,
    in_pdf,
)

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))

REPORT = AIReport.model_validate({
    "executive_summary": "Квартал закрыт с прибылью.",
    "financial_health_score": {"score": 61, "status": "Стабильно", "reasoning": "ок"},
    "key_insights": [
        {"title": "Первый инсайт", "severity": "high", "explanation": "a"},
        {"title": "Второй инсайт", "severity": "medium", "explanation": "b"},
        {"title": "Третий инсайт", "severity": "low", "explanation": "c"},
    ],
    "top_risks": [{"risk": "Кассовый разрыв", "impact": "высокий", "recommendation": "предоплата"}],
    "growth_opportunities": [{"opportunity": "Кухни", "potential_impact": "рост", "action": "запустить"}],
    "expense_analysis": {"problem_categories": ["marketing"], "efficient_categories": [], "notes": "ок"},
    "anomalies": [{"category": "marketing", "issue": "рост", "severity": "high", "explanation": "x"}],
    "cash_flow_analysis": {"status": "positive", "summary": "ок", "warning_level": "low"},
    "forecast": {"outlook": "stable", "confidence": "medium", "summary": "ок"},
    "priority_actions": [{"priority": 1, "action": "Ввести предоплату", "expected_result": "ровный поток"}],
})

METRICS = {
    "monthly_breakdown": [
        {"month": "2026-01", "revenue": 1000, "expenses": 800, "profit": 200},
        {"month": "2026-02", "revenue": 1200, "expenses": 900, "profit": 300},
    ],
    "expense_by_category": [{"category": "marketing", "total": 500, "percentage": 100, "transaction_count": 3}],
    "mom_growth": [{"month": "2026-02", "revenue_growth_pct": 20.0, "expense_growth_pct": 12.5, "profit_growth_pct": 50.0,
                    "revenue_growth_display": 20.0, "expense_growth_display": 12.5, "profit_growth_display": 50.0}],
    "cashflow_forecast": {"has_risk": False, "weekly_projection": [{"week": 1, "projected_balance": 100}, {"week": 2, "projected_balance": 200}]},
    "category_reliability": "full", "category_coverage": 1.0,
}

L = PDF_LABELS["ru"]


def _pdf_text(layout=None) -> str:
    """
    Upper-cased, because section headings are set in capitals by the PDF and
    chart captions are not; comparing everything in one case keeps the
    assertions about ORDER honest without caring about the styling.
    """
    data = generate_pdf(report=REPORT, metrics=METRICS, language="ru", layout=layout)
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        return "\n".join((pg.extract_text() or "") for pg in pdf.pages).upper()


def _positions(text: str, headings: list[str]) -> list[int]:
    """Character offset of each heading, -1 if absent."""
    return [text.find(h.upper()) for h in headings]


# ── The registry ────────────────────────────────────────────────────────────

def test_the_registry_is_the_shared_file():
    path = os.path.join(REPO_ROOT, "report-blocks.json")
    ids = [b["id"] for b in json.load(io.open(path, encoding="utf-8"))["blocks"]]
    assert ids == BLOCK_IDS


def test_the_web_imports_the_same_registry():
    ts = io.open(os.path.join(REPO_ROOT, "bytereport-frontend", "src", "lib", "reportBlocks.ts"),
                 encoding="utf-8").read()
    assert 'from "../../../report-blocks.json"' in ts


@pytest.mark.parametrize("lang", ["ru", "uz", "en"])
def test_every_block_is_labelled_in_every_language(lang):
    for b in REGISTRY:
        assert b["label"].get(lang), f"{b['id']} has no {lang} label"


def test_every_pdf_section_has_a_builder():
    """A registry entry the generator cannot build would be silently skipped."""
    import inspect

    from app.services import pdf_generator as pg

    src = inspect.getsource(pg.generate_pdf)
    for bid in BLOCK_IDS:
        if in_pdf(bid):
            assert f'"{bid}"' in src or bid.startswith("chart_"), f"no builder for {bid}"


# ── The layout model ────────────────────────────────────────────────────────

def test_the_default_layout_is_the_registry_order():
    assert [b.id for b in ReportLayout.default().blocks] == BLOCK_IDS
    assert all(b.visible for b in ReportLayout.default().blocks)


def test_an_unknown_block_id_is_rejected():
    with pytest.raises(ValidationError):
        ReportLayout(blocks=[{"id": "made_up_section"}])


def test_a_section_missing_from_an_old_layout_is_appended_hidden():
    """
    A layout saved before a section existed must not make that section vanish
    for good — it appears, switched off, where the accountant can find it.
    """
    layout = ReportLayout(blocks=[{"id": "health_score"}, {"id": "forecast"}])
    ids = [b.id for b in layout.blocks]
    assert ids[:2] == ["health_score", "forecast"]
    assert set(ids) == set(BLOCK_IDS)
    assert not layout.is_visible("key_insights")


def test_a_duplicated_block_renders_once():
    layout = ReportLayout(blocks=[{"id": "forecast"}, {"id": "forecast"}, {"id": "health_score"}])
    assert [b.id for b in layout.blocks][:2] == ["forecast", "health_score"]


def test_hidden_items_only_apply_to_list_sections():
    layout = ReportLayout(hidden_items={"key_insights": [1], "health_score": [0], "nope": [2]})
    assert layout.hidden_items == {"key_insights": [1]}


def test_keep_items_removes_by_index_and_keeps_order():
    layout = ReportLayout(hidden_items={"key_insights": [1]})
    assert layout.keep_items("key_insights", ["a", "b", "c"]) == ["a", "c"]


def test_coerce_accepts_none_dict_or_model():
    assert coerce_layout(None) == ReportLayout.default()
    assert coerce_layout({"blocks": [{"id": "forecast"}]}).blocks[0].id == "forecast"


def test_web_only_sections_are_skipped_for_the_pdf():
    assert "kpi_strip" in BLOCK_IDS
    assert not in_pdf("kpi_strip")
    assert "kpi_strip" not in ReportLayout.default().visible_ids(for_pdf=True)


# ── The PDF honours the layout ──────────────────────────────────────────────

def test_the_default_pdf_carries_every_section():
    text = _pdf_text()
    for key in ("financial_health", "executive_summary", "key_insights", "anomalies", "forecast"):
        assert L[key].upper() in text, f"default PDF lacks {key}"


def test_a_hidden_section_is_absent_from_the_pdf():
    layout = ReportLayout.default()
    for b in layout.blocks:
        if b.id == "anomalies":
            b.visible = False
    text = _pdf_text(layout)
    assert L["anomalies"].upper() not in text
    assert L["key_insights"].upper() in text            # neighbours untouched


def test_the_health_score_can_be_hidden_too():
    """Historically the headline block; the brief says it is not exempt."""
    layout = ReportLayout.default()
    for b in layout.blocks:
        if b.id == "health_score":
            b.visible = False
    text = _pdf_text(layout)
    assert L["financial_health"].upper() not in text
    assert "61" not in text.split(L["executive_summary"].upper())[0]


def test_reordering_sections_reorders_the_pdf():
    ids = list(BLOCK_IDS)
    ids.remove("forecast")
    ids.insert(1, "forecast")                    # forecast right after health score
    layout = ReportLayout(blocks=[{"id": i} for i in ids])
    text = _pdf_text(layout)
    pos = _positions(text, [L["financial_health"], L["forecast"], L["executive_summary"]])
    assert -1 not in pos
    assert pos[0] < pos[1] < pos[2], "PDF did not follow the requested order"


def test_a_chart_can_be_moved_to_the_end():
    """
    The brief's specific case: charts used to live in one fixed group. Each is
    now its own section, so one chart can sit after every text block.
    """
    ids = [i for i in BLOCK_IDS if i != "chart_monthly"] + ["chart_monthly"]
    layout = ReportLayout(blocks=[{"id": i} for i in ids])
    text = _pdf_text(layout)
    pos = _positions(text, [L["priority_actions"], L["forecast"], L["chart_monthly"]])
    assert -1 not in pos
    assert pos[2] > max(pos[:2]), "the chart was not moved after the text sections"


def test_charts_can_be_hidden_individually():
    layout = ReportLayout.default()
    for b in layout.blocks:
        if b.id == "chart_categories":
            b.visible = False
    text = _pdf_text(layout)
    assert L["chart_expenses_by_cat"].upper() not in text
    assert L["chart_monthly"].upper() in text


def test_a_single_insight_can_be_hidden():
    layout = ReportLayout(hidden_items={"key_insights": [1]})
    text = _pdf_text(layout)
    assert "ПЕРВЫЙ ИНСАЙТ" in text
    assert "ВТОРОЙ ИНСАЙТ" not in text
    assert "ТРЕТИЙ ИНСАЙТ" in text


def test_hiding_items_does_not_mutate_the_report():
    """The caller keeps the report and may render it again with another layout."""
    layout = ReportLayout(hidden_items={"key_insights": [0, 1, 2]})
    _pdf_text(layout)
    assert len(REPORT.key_insights) == 3


def test_the_briefs_verification_scenario():
    """
    Hide the Health Score, move a chart to the end, hide one insight — the
    file must reflect exactly that, not the default.
    """
    ids = [i for i in BLOCK_IDS if i != "chart_growth"] + ["chart_growth"]
    layout = ReportLayout(
        blocks=[{"id": i, "visible": i != "health_score"} for i in ids],
        hidden_items={"key_insights": [2]},
    )
    text = _pdf_text(layout)
    assert L["financial_health"].upper() not in text
    assert "ТРЕТИЙ ИНСАЙТ" not in text and "ПЕРВЫЙ ИНСАЙТ" in text
    pos = _positions(text, [L["forecast"], L["chart_growth"]])
    assert -1 not in pos and pos[1] > pos[0]


def test_the_route_accepts_a_layout_and_rejects_a_bad_one():
    from fastapi.testclient import TestClient

    from main import app

    client = TestClient(app)
    body = {"report": REPORT.model_dump(), "metrics": METRICS, "language": "ru"}
    ok = client.post("/report/pdf", json={**body, "layout": {"blocks": [{"id": "forecast"}]}})
    assert ok.status_code == 200 and ok.content[:5] == b"%PDF-"
    bad = client.post("/report/pdf", json={**body, "layout": {"blocks": [{"id": "nope"}]}})
    assert bad.status_code in (400, 422)


# ── Positional references in AI prose ───────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("Как видно на графике выше, расходы растут.", "Как видно на графике, расходы растут."),
    ("Подробнее в разделе ниже.", "Подробнее в разделе."),
    ("As shown above, the chart below confirms it (see below).",
     "As shown in the report, the chart confirms it."),
    ("Юқоридаги график буни тасдиқлайди.", "График буни тасдиқлайди."),
])
def test_positional_references_are_removed(text, expected):
    """A section can now be hidden or moved; 'above' would then be a lie."""
    assert strip_positional(text)[0] == expected


@pytest.mark.parametrize("text", [
    "Комиссия выше нормы — сократить.",
    "Fee ниже 2% — увеличить бюджет.",
    "Маржа ниже, чем в прошлом году.",
    "Revenue is above target.",
])
def test_comparisons_are_not_mistaken_for_positions(text):
    """'выше нормы' is a comparison; only section nouns and lead-ins count."""
    assert strip_positional(text) == (text, [])


def test_the_prompt_forbids_positional_references():
    from app.core.prompts import BYTEREPORT_SYSTEM_PROMPT

    assert "БЕЗ ССЫЛОК НА РАСПОЛОЖЕНИЕ" in BYTEREPORT_SYSTEM_PROMPT


def test_positional_cleanup_runs_at_the_parse_boundary():
    from app.services.ai_text import scrub_model

    r = AIReport.model_validate({**REPORT.model_dump(),
                                 "executive_summary": "Как видно на графике выше, всё хорошо."})
    scrub_model(r)
    assert "выше" not in r.executive_summary


def test_labels_fall_back_sanely():
    assert block_label("forecast", "en") == "Forecast"
    assert block_label("forecast", "xx") == block_label("forecast", "ru")
    assert block_label("unknown_id") == "unknown_id"
    assert set(LIST_BLOCKS) == {"key_insights", "top_risks", "anomalies",
                                "growth_opportunities", "priority_actions"}


def test_an_empty_block_list_means_the_default_not_everything_hidden():
    """
    Caught by the single-insight test: a layout carrying only hidden_items had
    every section appended switched off, and the PDF came out with nothing but
    a cover. Only sections MISSING from a non-empty list are appended hidden.
    """
    layout = ReportLayout(hidden_items={"key_insights": [1]})
    assert [b.id for b in layout.blocks] == BLOCK_IDS
    assert all(b.visible for b in layout.blocks)
