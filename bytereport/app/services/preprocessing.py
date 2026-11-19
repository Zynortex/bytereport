"""
Transaction pre-processing: remove future dates, detect duplicates.
Called by /analyze before compute_metrics so that financial_engine
never sees invalid data.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date

from app.models.transaction import Transaction

logger = logging.getLogger(__name__)


def preprocess_transactions(
    transactions: list[Transaction],
    today: date | None = None,
) -> tuple[list[Transaction], dict]:
    """
    Return (clean_list, metadata_dict).

    clean_list  — transactions with date <= today, same order.
    metadata    — {"future_transactions": [...], "possible_duplicates": [...]}

    `today` defaults to the real date. Tests pass a fixed one: "future" is a
    moving target, and a fixture written in July stops containing a future
    transaction once the calendar passes it.
    """
    today = today or date.today()

    # 1a. Split on date
    future: list[Transaction] = []
    clean: list[Transaction] = []
    for t in transactions:
        (future if t.date > today else clean).append(t)

    if future:
        logger.warning(
            "Excluded %d future transaction(s) (after %s)", len(future), today
        )

    future_meta = [
        {
            "date": t.date.isoformat(),
            "category": t.raw_category or t.category,
            "amount": t.amount,
        }
        for t in future
    ]

    # 1b. Detect full duplicates by (date, category, amount, description).
    # DO NOT remove — two identical real payments are possible.
    key_to_indices: dict[tuple, list[int]] = defaultdict(list)
    for i, t in enumerate(clean):
        key = (
            t.date,
            (t.raw_category or t.category).strip().lower(),
            t.amount,
            t.description.strip().lower(),
        )
        key_to_indices[key].append(i)

    possible_duplicates = []
    for indices in key_to_indices.values():
        if len(indices) >= 2:
            t = clean[indices[0]]
            possible_duplicates.append(
                {
                    "date": t.date.isoformat(),
                    "category": t.raw_category or t.category,
                    "amount": t.amount,
                    "count": len(indices),
                }
            )

    if possible_duplicates:
        logger.warning(
            "Detected %d possible duplicate group(s)", len(possible_duplicates)
        )

    return clean, {
        "future_transactions": future_meta,
        "possible_duplicates": possible_duplicates,
    }
