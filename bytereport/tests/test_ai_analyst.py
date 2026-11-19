"""
Tests for AI analyst service.
Uses unittest.mock to avoid real API calls.
"""

import json
import pytest
from pydantic import ValidationError
from unittest.mock import patch, MagicMock

from app.models.report import AIReport, AIReportRequest
from app.services.ai_analyst import _parse_ai_response, _build_user_message

# These tests replace the provider call with their own stub to check what
# happens around it, so the AI_MOCK fixture answer is switched off here.
pytestmark = pytest.mark.usefixtures("provider_stub")


VALID_REPORT_JSON = {
    "executive_summary": "Business shows stable growth.",
    "financial_health_score": {"score": 72, "status": "Stable", "reasoning": "Positive profit margin."},
    "key_insights": [{"title": "Revenue growth", "severity": "low", "explanation": "Up 8% MoM."}],
    "top_risks": [{"risk": "Marketing efficiency", "impact": "CAC rising", "recommendation": "Audit campaigns."}],
    "growth_opportunities": [{"opportunity": "Services", "potential_impact": "High", "action": "Expand offering."}],
    "expense_analysis": {"problem_categories": ["marketing"], "efficient_categories": ["payroll"], "notes": ""},
    "anomalies": [{"category": "marketing", "issue": "Spike +100%", "severity": "high", "explanation": "Doubled spend."}],
    "cash_flow_analysis": {"status": "Stable", "summary": "Positive cash flow.", "warning_level": "low"},
    "forecast": {"outlook": "Moderate growth", "confidence": "medium", "summary": "Next 30 days stable."},
    "priority_actions": [{"priority": 1, "action": "Audit marketing spend", "expected_result": "Reduce CAC by 15%."}],
}


def test_parse_ai_response_clean_json():
    raw = json.dumps(VALID_REPORT_JSON)
    report = _parse_ai_response(raw)
    assert isinstance(report, AIReport)
    assert report.financial_health_score.score == 72


def test_parse_ai_response_strips_markdown_fences():
    raw = f"```json\n{json.dumps(VALID_REPORT_JSON)}\n```"
    report = _parse_ai_response(raw)
    assert report.executive_summary == "Business shows stable growth."


def test_parse_ai_response_invalid_json_raises():
    # safe_json_loads exhausts all repair levels then raises ValueError
    with pytest.raises((json.JSONDecodeError, ValueError)):
        _parse_ai_response("not valid json")


def test_build_user_message_includes_context():
    msg = _build_user_message(
        metrics={"total_revenue": 50000},
        business_type="retail",
        business_name="Мой магазин",
        currency="RUB",
    )
    assert "retail" in msg
    assert "Мой магазин" in msg
    assert "RUB" in msg
    assert "50000" in msg


def test_build_user_message_without_optional_fields():
    msg = _build_user_message(
        metrics={"total_revenue": 1000},
        business_type=None,
        business_name=None,
        currency="USD",
    )
    assert "USD" in msg
    assert "Business name" not in msg
    assert "Business type" not in msg


@pytest.mark.asyncio
async def test_get_ai_analysis_openai_called(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.ai_provider", "openai")
    monkeypatch.setattr("app.core.config.settings.openai_api_key", "test-key")

    mock_fn = MagicMock(return_value=json.dumps(VALID_REPORT_JSON))
    with patch.dict("app.services.ai_analyst._PROVIDERS", {"openai": mock_fn}):
        from app.services.ai_analyst import get_ai_analysis
        result = await get_ai_analysis({"total_revenue": 1000})
        mock_fn.assert_called_once()
        assert isinstance(result, AIReport)


@pytest.mark.asyncio
async def test_get_ai_analysis_unknown_provider_raises(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.ai_provider", "groq")
    from app.services.ai_analyst import get_ai_analysis
    with pytest.raises(ValueError, match="Unknown AI_PROVIDER"):
        await get_ai_analysis({"total_revenue": 1000})


# ---------------------------------------------------------------------------
# Language support tests
# ---------------------------------------------------------------------------

def test_ai_report_request_language_default():
    req = AIReportRequest(metrics={})
    assert req.language == "ru"


@pytest.mark.parametrize("lang", ["uz", "ru", "en"])
def test_ai_report_request_valid_languages(lang):
    req = AIReportRequest(metrics={}, language=lang)
    assert req.language == lang


def test_ai_report_request_invalid_language_raises():
    with pytest.raises(ValidationError):
        AIReportRequest(metrics={}, language="fr")


@pytest.mark.asyncio
async def test_get_ai_analysis_uz_prompt_contains_cyrillic(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.ai_provider", "openai")
    captured = []

    def mock_call(user_msg, system_prompt):
        captured.append(system_prompt)
        return json.dumps(VALID_REPORT_JSON)

    with patch.dict("app.services.ai_analyst._PROVIDERS", {"openai": mock_call}):
        from app.services.ai_analyst import get_ai_analysis
        await get_ai_analysis({"total_revenue": 1000}, language="uz")

    assert len(captured) == 1
    assert "ўзбек тили" in captured[0]
    assert "КИРИЛЛИЦА" in captured[0]
    assert "ў" in captured[0]  # Uzbek Cyrillic character


@pytest.mark.asyncio
async def test_get_ai_analysis_en_prompt_contains_english_instruction(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.ai_provider", "openai")
    captured = []

    def mock_call(user_msg, system_prompt):
        captured.append(system_prompt)
        return json.dumps(VALID_REPORT_JSON)

    with patch.dict("app.services.ai_analyst._PROVIDERS", {"openai": mock_call}):
        from app.services.ai_analyst import get_ai_analysis
        await get_ai_analysis({"total_revenue": 1000}, language="en")

    assert "English" in captured[0]
    assert "Excellent" in captured[0]


def test_json_keys_are_always_english():
    report = _parse_ai_response(json.dumps(VALID_REPORT_JSON))
    data = json.loads(report.model_dump_json())
    for key in ["executive_summary", "financial_health_score", "key_insights", "top_risks", "priority_actions"]:
        assert key in data


def test_pdf_generates_for_all_languages():
    from app.services.pdf_generator import generate_pdf
    report = AIReport.model_validate(VALID_REPORT_JSON)
    for lang in ["ru", "uz", "en"]:
        pdf = generate_pdf(report, business_name="Test Co", language=lang)
        assert isinstance(pdf, bytes)
        assert len(pdf) > 1000, f"PDF for lang={lang} looks empty"


# ---------------------------------------------------------------------------
# safe_json_loads tests
# ---------------------------------------------------------------------------

def test_safe_json_loads_invalid_escape():
    from app.utils.json_repair import safe_json_loads
    # \% is not a valid JSON escape — should be repaired
    raw = '{"a": "19\\%"}'
    result = safe_json_loads(raw)
    assert result["a"] == "19%"


def test_safe_json_loads_markdown_fence():
    from app.utils.json_repair import safe_json_loads
    raw = f'```json\n{json.dumps({"x": 1})}\n```'
    result = safe_json_loads(raw)
    assert result["x"] == 1


def test_safe_json_loads_preamble():
    from app.utils.json_repair import safe_json_loads
    raw = 'Вот анализ: {"answer": 42} — надеюсь помог!'
    result = safe_json_loads(raw)
    assert result["answer"] == 42


def test_safe_json_loads_trailing_comma():
    from app.utils.json_repair import safe_json_loads
    raw = '{"a": 1,}'
    result = safe_json_loads(raw)
    assert result["a"] == 1


def test_safe_json_loads_broken_raises_and_dumps(tmp_path, monkeypatch):
    from app.utils import json_repair
    monkeypatch.setattr(json_repair, "RAW_DUMP_DIR", tmp_path)
    with pytest.raises(ValueError, match="некорректный JSON"):
        json_repair.safe_json_loads("{abc")
    dumps = list(tmp_path.glob("failed_*.txt"))
    assert len(dumps) == 1
    dumps[0].unlink()  # clean up


# ---------------------------------------------------------------------------
# _collect_str_values() helper tests
# ---------------------------------------------------------------------------

def test_collect_str_values_flat_dict():
    from app.services.ai_analyst import _collect_str_values
    result = _collect_str_values({"a": "hello", "b": "world"})
    assert set(result) == {"hello", "world"}


def test_collect_str_values_nested():
    from app.services.ai_analyst import _collect_str_values
    result = _collect_str_values({"x": {"y": ["one", "two"]}})
    assert "one" in result and "two" in result


def test_collect_str_values_ignores_numbers():
    from app.services.ai_analyst import _collect_str_values
    result = _collect_str_values({"n": 42, "s": "text", "f": 3.14})
    assert result == ["text"]


def test_collect_str_values_returns_string_leaf():
    from app.services.ai_analyst import _collect_str_values
    result = _collect_str_values("bare string")
    assert result == ["bare string"]


# ---------------------------------------------------------------------------
# _uz_lint() mechanism tests
# ---------------------------------------------------------------------------

def test_uz_lint_no_violation_no_file(tmp_path, monkeypatch):
    """No BLACKLIST_UZ words → no log file created."""
    monkeypatch.chdir(tmp_path)
    from app.services.ai_analyst import _uz_lint
    _uz_lint({"executive_summary": "Бизнес барқарор ривожланмоқда"}, "raw")
    log_dir = tmp_path / "logs" / "raw_ai_responses"
    assert not log_dir.exists() or not list(log_dir.glob("uz_lint_*.txt"))


def test_uz_lint_creates_log_on_violation(tmp_path, monkeypatch):
    """BLACKLIST_UZ word in data → log file created with word and raw response."""
    monkeypatch.chdir(tmp_path)
    from app.services.ai_analyst import _uz_lint
    dirty_data = {"executive_summary": "This is an operational report for future periods"}
    _uz_lint(dirty_data, "raw_response_text_here")
    log_files = list((tmp_path / "logs" / "raw_ai_responses").glob("uz_lint_*.txt"))
    assert len(log_files) == 1
    content = log_files[0].read_text(encoding="utf-8")
    assert "operational" in content
    assert "future" in content
    assert "raw_response_text_here" in content


def test_uz_lint_detects_all_blacklist_words(tmp_path, monkeypatch):
    """Every word in BLACKLIST_UZ triggers a violation entry in the log."""
    monkeypatch.chdir(tmp_path)
    from app.services.ai_analyst import _uz_lint, BLACKLIST_UZ
    data = {f"field_{i}": word for i, word in enumerate(BLACKLIST_UZ)}
    _uz_lint(data, "raw")
    log_files = list((tmp_path / "logs" / "raw_ai_responses").glob("uz_lint_*.txt"))
    assert len(log_files) == 1
    content = log_files[0].read_text(encoding="utf-8")
    for word in BLACKLIST_UZ:
        assert word in content, f"Expected {word!r} in lint log"


def test_uz_lint_case_insensitive(tmp_path, monkeypatch):
    """BLACKLIST_UZ matching is case-insensitive (OPERATIONAL matches 'operational')."""
    monkeypatch.chdir(tmp_path)
    from app.services.ai_analyst import _uz_lint
    _uz_lint({"summary": "OPERATIONAL costs are rising"}, "raw")
    log_files = list((tmp_path / "logs" / "raw_ai_responses").glob("uz_lint_*.txt"))
    assert len(log_files) == 1


def test_uz_lint_nested_structure(tmp_path, monkeypatch):
    """_uz_lint scans deeply nested dicts and lists recursively."""
    monkeypatch.chdir(tmp_path)
    from app.services.ai_analyst import _uz_lint
    data = {
        "level1": {
            "items": [
                {"text": "тоза ўзбек матни"},
                {"text": "нақд пул тақчиллиги — trend йўналиши кузатилди"},
            ]
        }
    }
    _uz_lint(data, "raw")
    log_files = list((tmp_path / "logs" / "raw_ai_responses").glob("uz_lint_*.txt"))
    assert len(log_files) == 1
    content = log_files[0].read_text(encoding="utf-8")
    assert "trend" in content


def test_uz_lint_log_contains_uz_lint_header(tmp_path, monkeypatch):
    """Log file starts with 'UZ LINT' header."""
    monkeypatch.chdir(tmp_path)
    from app.services.ai_analyst import _uz_lint
    _uz_lint({"f": "разовый доход"}, "raw")
    log_files = list((tmp_path / "logs" / "raw_ai_responses").glob("uz_lint_*.txt"))
    content = log_files[0].read_text(encoding="utf-8")
    assert content.startswith("UZ LINT")


def test_uz_lint_does_not_raise_on_violation(tmp_path, monkeypatch):
    """_uz_lint never blocks — it must not raise even with many violations."""
    monkeypatch.chdir(tmp_path)
    from app.services.ai_analyst import _uz_lint, BLACKLIST_UZ
    data = {"text": " ".join(BLACKLIST_UZ)}
    _uz_lint(data, "raw")  # must not raise


def test_a_test_failure_dump_never_reaches_the_real_log_folder(_raw_dumps_to_tmp):
    """The dump goes to the per-test temp dir; logs/raw_ai_responses is untouched."""
    import pathlib

    real = pathlib.Path(__file__).resolve().parents[1] / "logs" / "raw_ai_responses"
    before = set(real.glob("*")) if real.exists() else set()
    with pytest.raises(ValueError):
        _parse_ai_response("not valid json")
    after = set(real.glob("*")) if real.exists() else set()
    assert after == before
    assert len(list(_raw_dumps_to_tmp.glob("failed_*.txt"))) == 1
