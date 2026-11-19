"""
Test-wide setup.

Report credits live in Supabase in production. No test may reach a live
project, so every test runs against a fresh in-memory store with the same
rules as the SQL functions.

Failed AI responses are dumped to logs/raw_ai_responses so a real failure can
be read later. Tests that feed deliberately broken JSON used to write there
too — 65 copies of "not valid json" burying the real ones — so every test
dumps into its own temporary directory instead.

AI runs with AI_MOCK on: every report, chat answer, note, photo and
transcription comes from app/fixtures/ai_mock.json. The provider keys are
blanked as well, so even a code path that slipped past the mock could not
spend money. Tests that check what happens around a provider call stub that
call themselves and ask for `provider_stub`, which turns the mock off for
them (their own stub answers instead).
"""

import pytest

from app.core.config import settings
from app.services import credits
from app.utils import json_repair


@pytest.fixture(autouse=True)
def _ai_mock(monkeypatch):
    monkeypatch.setattr(settings, "ai_mock", True)
    monkeypatch.setattr(settings, "openai_api_key", "")
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    yield


@pytest.fixture
def provider_stub(monkeypatch):
    """For a test that replaces the provider call with its own stub."""
    monkeypatch.setattr(settings, "ai_mock", False)
    yield


@pytest.fixture(autouse=True)
def _memory_credits(monkeypatch):
    store = credits.MemoryCredits()
    monkeypatch.setattr(credits, "credit_store", store)
    yield store


@pytest.fixture(autouse=True)
def _raw_dumps_to_tmp(monkeypatch, tmp_path):
    target = tmp_path / "raw_ai_responses"
    monkeypatch.setattr(json_repair, "RAW_DUMP_DIR", target)
    yield target
