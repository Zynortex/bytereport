"""
Per-report API cost accounting.

Token counts come from the provider's own `usage` object (exact, billed
figures) — never estimated from character counts, which are off by a wide and
language-dependent margin for Cyrillic text.

Rates below are GPT-4.1 list prices as of July 2026, in USD per 1M tokens.
Verify against the billing dashboard before relying on these in production:
https://platform.openai.com/settings/organization/limits
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)

# USD per 1,000,000 tokens — GPT-4.1, July 2026.
PRICE_INPUT_PER_1M = 2.00
PRICE_CACHED_INPUT_PER_1M = 0.50
PRICE_OUTPUT_PER_1M = 8.00


def calculate_report_cost(
    prompt_tokens: int,
    completion_tokens: int,
    cached_tokens: int = 0,
) -> float:
    """
    Cost in USD for a single completion.

    `cached_tokens` is the subset of `prompt_tokens` served from the provider's
    prompt cache and billed at the reduced rate, so it is subtracted from the
    full-price portion rather than added on top.
    """
    billable_input = max(prompt_tokens - cached_tokens, 0)
    return (
        billable_input * PRICE_INPUT_PER_1M / 1_000_000
        + cached_tokens * PRICE_CACHED_INPUT_PER_1M / 1_000_000
        + completion_tokens * PRICE_OUTPUT_PER_1M / 1_000_000
    )


@dataclass(frozen=True)
class Usage:
    """Normalised token usage for one provider call."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cached_tokens: int = 0

    @property
    def cost_usd(self) -> float:
        return calculate_report_cost(
            self.prompt_tokens, self.completion_tokens, self.cached_tokens
        )


def extract_usage(response: Any) -> Optional[Usage]:
    """
    Pull the usage block off an OpenAI chat-completion response.

    Returns None when the provider omitted usage, so callers can log the gap
    instead of silently reporting a $0.00 report.
    """
    usage = getattr(response, "usage", None)
    if usage is None:
        return None

    # Cached-prompt tokens live in a nested detail object that older API
    # versions omit entirely.
    cached = 0
    details = getattr(usage, "prompt_tokens_details", None)
    if details is not None:
        cached = getattr(details, "cached_tokens", 0) or 0

    prompt = getattr(usage, "prompt_tokens", 0) or 0
    completion = getattr(usage, "completion_tokens", 0) or 0
    total = getattr(usage, "total_tokens", 0) or (prompt + completion)

    return Usage(
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=total,
        cached_tokens=cached,
    )


def log_chat_usage(response: Any, model: str) -> Optional[Usage]:
    """
    Same accounting as `log_usage`, labelled for the AI-CFO chat.

    A thin wrapper rather than a parameter on `log_usage`, so the report path's
    logging keeps its exact existing signature and output. Chat is the second
    variable OpenAI cost, and it needs to be distinguishable from report
    generation when reading a bill.
    """
    usage = extract_usage(response)
    if usage is None:
        logger.warning("AI chat usage: provider returned no usage block (model=%s)", model)
        return None

    logger.info(
        "AI chat usage: prompt_tokens=%d completion_tokens=%d total=%d cached=%d",
        usage.prompt_tokens, usage.completion_tokens,
        usage.total_tokens, usage.cached_tokens,
    )
    logger.info(
        "AI chat cost: $%.6f for this message (model=%s)", usage.cost_usd, model
    )
    return usage


def log_anthropic_usage(message: Any, model: str) -> None:
    """
    Log Claude token counts.

    Deliberately does NOT price them: the rates in this module are GPT-4.1's,
    and Claude bills differently. Reporting a dollar figure here would be a
    made-up number, so we log the tokens and say the cost is unpriced.
    """
    usage = getattr(message, "usage", None)
    if usage is None:
        logger.warning("AI usage: provider returned no usage block (model=%s)", model)
        return
    inp = getattr(usage, "input_tokens", 0) or 0
    out = getattr(usage, "output_tokens", 0) or 0
    logger.info(
        "AI usage: prompt_tokens=%d completion_tokens=%d total=%d cached=0",
        inp, out, inp + out,
    )
    logger.info(
        "AI cost: not priced for model=%s (this module carries GPT-4.1 rates only)",
        model,
    )


def log_usage(response: Any, model: str) -> Optional[Usage]:
    """Log exact token usage and the resulting cost for one call."""
    usage = extract_usage(response)
    if usage is None:
        logger.warning("AI usage: provider returned no usage block (model=%s)", model)
        return None

    logger.info(
        "AI usage: prompt_tokens=%d completion_tokens=%d total=%d cached=%d",
        usage.prompt_tokens, usage.completion_tokens,
        usage.total_tokens, usage.cached_tokens,
    )
    logger.info(
        "AI cost: $%.6f for this report (model=%s)", usage.cost_usd, model
    )
    return usage
