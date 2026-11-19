"""
Regression tests for /chat: the provider call must not block the event loop,
and each message must be cost-logged.

The blocking test is the unit-level equivalent of the /health probing used to
diagnose this in production: run a deliberately slow, *synchronous* provider
call and check that an unrelated coroutine still gets scheduled while it runs.
If someone drops the `asyncio.to_thread` wrapper, the heartbeat stops and this
fails.
"""

import asyncio
import logging
import time
from types import SimpleNamespace

import pytest

from app.services import ai_chat
from app.services.cost import log_chat_usage

# These tests replace the provider call with their own stub to check what
# happens around it, so the AI_MOCK fixture answer is switched off here.
pytestmark = pytest.mark.usefixtures("provider_stub")

BLOCK_SECONDS = 0.6


def _args() -> dict:
    return dict(
        message="Что с моими финансами?",
        history=[],
        metrics={"total_revenue": 1_000_000, "total_expenses": 800_000},
        ai_report=None,
        business_name="Nova Digital",
        business_type="IT agency",
        currency="UZS",
    )


async def _heartbeat(stop: asyncio.Event, ticks: list) -> None:
    """Tick every 10 ms. Cannot advance if the event loop is blocked."""
    while not stop.is_set():
        ticks.append(time.perf_counter())
        await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_chat_does_not_block_event_loop(monkeypatch):
    """A slow synchronous provider call must leave the loop free."""
    def slow_blocking_call(system, history, message):
        time.sleep(BLOCK_SECONDS)          # blocking on purpose
        return "ответ"

    monkeypatch.setattr(ai_chat.settings, "ai_provider", "openai")
    monkeypatch.setattr(ai_chat, "_openai_chat", slow_blocking_call)

    stop = asyncio.Event()
    ticks: list = []
    hb = asyncio.create_task(_heartbeat(stop, ticks))

    answer = await ai_chat.get_chat_response(**_args())

    stop.set()
    await hb

    assert answer == "ответ"
    # ~60 ticks are possible in 0.6 s; anything well above a handful proves the
    # loop kept running. A blocked loop yields 0-1.
    assert len(ticks) > 10, (
        f"event loop appears blocked: only {len(ticks)} heartbeat ticks during "
        f"a {BLOCK_SECONDS}s provider call"
    )


@pytest.mark.asyncio
async def test_chat_runs_provider_off_the_main_thread(monkeypatch):
    """The provider call must execute on a worker thread, not the loop thread."""
    import threading
    main_thread = threading.current_thread().name
    seen = {}

    def capture_thread(system, history, message):
        seen["thread"] = threading.current_thread().name
        return "ok"

    monkeypatch.setattr(ai_chat.settings, "ai_provider", "openai")
    monkeypatch.setattr(ai_chat, "_openai_chat", capture_thread)

    await ai_chat.get_chat_response(**_args())
    assert seen["thread"] != main_thread


@pytest.mark.asyncio
async def test_chat_propagates_cancellation(monkeypatch, caplog):
    """
    Client disconnect must unwind cleanly as CancelledError.

    This is about the handler not dying with an unhandled error — it does NOT
    abort the upstream request and does NOT save tokens; the worker thread runs
    to completion and is billed either way.
    """
    def slow(system, history, message):
        time.sleep(BLOCK_SECONDS)
        return "too late"

    monkeypatch.setattr(ai_chat.settings, "ai_provider", "openai")
    monkeypatch.setattr(ai_chat, "_openai_chat", slow)

    task = asyncio.create_task(ai_chat.get_chat_response(**_args()))
    await asyncio.sleep(0.05)
    task.cancel()

    with caplog.at_level(logging.INFO, logger="app.services.ai_chat"):
        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_chat_provider_error_propagates(monkeypatch):
    def boom(system, history, message):
        raise RuntimeError("provider exploded")

    monkeypatch.setattr(ai_chat.settings, "ai_provider", "openai")
    monkeypatch.setattr(ai_chat, "_openai_chat", boom)

    with pytest.raises(RuntimeError, match="provider exploded"):
        await ai_chat.get_chat_response(**_args())


@pytest.mark.asyncio
async def test_chat_unknown_provider_raises(monkeypatch):
    monkeypatch.setattr(ai_chat.settings, "ai_provider", "gemini")
    with pytest.raises(ValueError, match="Unknown AI_PROVIDER"):
        await ai_chat.get_chat_response(**_args())


# ── Client hardening ────────────────────────────────────────────────────────

def test_openai_chat_client_has_timeout_and_no_retries(monkeypatch):
    """Explicit timeout + max_retries=0, mirroring the report path."""
    captured = {}

    class FakeCompletions:
        def create(self, **kw):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="hi"))],
                usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5,
                                      total_tokens=15, prompt_tokens_details=None),
            )

    class FakeOpenAI:
        def __init__(self, **kw):
            captured.update(kw)
            self.chat = SimpleNamespace(completions=FakeCompletions())

    import openai
    monkeypatch.setattr(openai, "OpenAI", FakeOpenAI)
    monkeypatch.setattr(ai_chat.settings, "ai_timeout_seconds", 120.0)

    ai_chat._openai_chat("sys", [], "hello")

    assert captured["max_retries"] == 0, "silent SDK retries bill tokens per attempt"
    assert captured["timeout"] == 120.0


# ── Cost logging ────────────────────────────────────────────────────────────

def _resp(prompt=1962, completion=347, cached=None):
    details = SimpleNamespace(cached_tokens=cached) if cached is not None else None
    return SimpleNamespace(usage=SimpleNamespace(
        prompt_tokens=prompt, completion_tokens=completion,
        total_tokens=prompt + completion, prompt_tokens_details=details,
    ))


def test_log_chat_usage_emits_tokens_and_cost(caplog):
    with caplog.at_level(logging.INFO, logger="app.services.cost"):
        usage = log_chat_usage(_resp(), "gpt-4.1")
    text = " ".join(r.getMessage() for r in caplog.records)
    assert "AI chat usage:" in text
    assert "prompt_tokens=1962" in text
    assert "completion_tokens=347" in text
    assert "AI chat cost:" in text
    assert usage is not None


def test_log_chat_usage_matches_measured_run():
    """Measured production chat message: 1962 in / 347 out, uncached."""
    usage = log_chat_usage(_resp(1962, 347), "gpt-4.1")
    assert usage.cost_usd == pytest.approx(0.006700, abs=1e-6)


def test_log_chat_usage_labelled_distinctly_from_reports(caplog):
    """Chat lines must be greppable apart from report lines on a bill review."""
    with caplog.at_level(logging.INFO, logger="app.services.cost"):
        log_chat_usage(_resp(), "gpt-4.1")
    text = " ".join(r.getMessage() for r in caplog.records)
    assert "for this message" in text
    assert "for this report" not in text


def test_log_chat_usage_warns_without_usage_block(caplog):
    with caplog.at_level(logging.WARNING, logger="app.services.cost"):
        assert log_chat_usage(SimpleNamespace(usage=None), "gpt-4.1") is None
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_report_logging_untouched(caplog):
    """log_usage must keep its original wording — ai_analyst depends on it."""
    from app.services.cost import log_usage
    with caplog.at_level(logging.INFO, logger="app.services.cost"):
        log_usage(_resp(7757, 2343), "gpt-4.1")
    text = " ".join(r.getMessage() for r in caplog.records)
    assert "AI usage:" in text
    assert "for this report" in text
