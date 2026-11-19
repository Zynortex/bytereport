"""Tests for per-report API cost accounting."""

import logging
from types import SimpleNamespace

import pytest

from app.services.cost import (
    PRICE_CACHED_INPUT_PER_1M,
    PRICE_INPUT_PER_1M,
    PRICE_OUTPUT_PER_1M,
    Usage,
    calculate_report_cost,
    extract_usage,
    log_usage,
)


# ── Rates ───────────────────────────────────────────────────────────────────

def test_rates_are_july_2026_gpt41():
    assert PRICE_INPUT_PER_1M == 2.00
    assert PRICE_CACHED_INPUT_PER_1M == 0.50
    assert PRICE_OUTPUT_PER_1M == 8.00


# ── calculate_report_cost ───────────────────────────────────────────────────

def test_cost_zero_tokens():
    assert calculate_report_cost(0, 0) == 0.0


def test_cost_input_only():
    # 1M input tokens at $2.00
    assert calculate_report_cost(1_000_000, 0) == pytest.approx(2.00)


def test_cost_output_only():
    assert calculate_report_cost(0, 1_000_000) == pytest.approx(8.00)


def test_cost_all_cached_input():
    assert calculate_report_cost(1_000_000, 0, cached_tokens=1_000_000) == pytest.approx(0.50)


def test_cached_tokens_are_subtracted_not_added():
    """cached_tokens is a SUBSET of prompt_tokens, not extra tokens on top."""
    full = calculate_report_cost(1000, 0, cached_tokens=0)
    half = calculate_report_cost(1000, 0, cached_tokens=500)
    # 500 @ $2/1M + 500 @ $0.50/1M  ==  0.001 + 0.00025
    assert half == pytest.approx(500 * 2.00 / 1e6 + 500 * 0.50 / 1e6)
    assert half < full


def test_cost_cached_exceeding_prompt_does_not_go_negative():
    """Defensive: a malformed usage block must not produce a negative charge."""
    assert calculate_report_cost(100, 0, cached_tokens=500) == pytest.approx(500 * 0.50 / 1e6)


# ── Measured production runs (real usage captured 2026-07-30) ───────────────

MEASURED = [
    # (prompt, completion, cached, expected_usd)
    (7757, 2343, 0,    0.034258),
    (7757, 2456, 7552, 0.023834),
    (7757, 2233, 7552, 0.022050),
]


@pytest.mark.parametrize("prompt,completion,cached,expected", MEASURED)
def test_measured_runs_match_expected_cost(prompt, completion, cached, expected):
    assert calculate_report_cost(prompt, completion, cached) == pytest.approx(expected, abs=1e-6)


def test_measured_average_cost_per_report():
    avg = sum(calculate_report_cost(*r[:3]) for r in MEASURED) / len(MEASURED)
    assert avg == pytest.approx(0.026714, abs=1e-5)


def test_prompt_caching_materially_reduces_cost():
    """Cached run must be cheaper than the identical uncached one."""
    uncached = calculate_report_cost(7757, 2343, 0)
    cached   = calculate_report_cost(7757, 2343, 7552)
    assert cached < uncached
    assert (uncached - cached) == pytest.approx(7552 * (2.00 - 0.50) / 1e6)


# ── extract_usage ───────────────────────────────────────────────────────────

def _resp(prompt=100, completion=50, total=None, cached=None):
    details = SimpleNamespace(cached_tokens=cached) if cached is not None else None
    usage = SimpleNamespace(
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=total if total is not None else prompt + completion,
        prompt_tokens_details=details,
    )
    return SimpleNamespace(usage=usage)


def test_extract_usage_reads_fields():
    u = extract_usage(_resp(7757, 2343, cached=7552))
    assert (u.prompt_tokens, u.completion_tokens, u.cached_tokens) == (7757, 2343, 7552)


def test_extract_usage_without_cache_details():
    """Older API shapes omit prompt_tokens_details entirely."""
    u = extract_usage(_resp(100, 50))
    assert u.cached_tokens == 0


def test_extract_usage_returns_none_when_absent():
    """No usage block → None, so we log a gap rather than report $0.00."""
    assert extract_usage(SimpleNamespace(usage=None)) is None
    assert extract_usage(SimpleNamespace()) is None


def test_usage_cost_property():
    assert Usage(7757, 2343, 10100, 0).cost_usd == pytest.approx(0.034258, abs=1e-6)


# ── log_usage ───────────────────────────────────────────────────────────────

def test_log_usage_emits_tokens_and_cost(caplog):
    with caplog.at_level(logging.INFO, logger="app.services.cost"):
        u = log_usage(_resp(7757, 2343, cached=7552), "gpt-4.1")
    text = " ".join(r.getMessage() for r in caplog.records)
    assert "prompt_tokens=7757" in text
    assert "completion_tokens=2343" in text
    assert "cached=7552" in text
    assert "AI cost:" in text
    assert u is not None


def test_log_usage_warns_when_provider_omits_usage(caplog):
    with caplog.at_level(logging.WARNING, logger="app.services.cost"):
        assert log_usage(SimpleNamespace(usage=None), "gpt-4.1") is None
    assert any(r.levelno == logging.WARNING for r in caplog.records)
