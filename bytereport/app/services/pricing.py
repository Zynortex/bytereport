"""
Plan numbers, loaded from repo-root pricing.json.

The pricing page imports the same file. Before this, the page promised
"1 отчёт в месяц" while the backend allowed 3 a day — two hand-kept numbers
that had nothing to do with each other. Now there is one number per fact.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_PATH = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "pricing.json"
))

# Mirrors pricing.json; used only when the file cannot be read (a deploy that
# ships the backend folder alone). A test pins the two together.
_FALLBACK: dict[str, Any] = {
    "currency": "UZS",
    "free_reports_on_signup": 3,
    "plans": [
        {"id": "free", "price": 0, "reports": 3, "period": "once"},
        {"id": "owner", "price": 150000, "reports": 5, "period": "none"},
        {"id": "accountant", "price": 450000, "reports": 25, "period": "month"},
    ],
}


def _load() -> dict[str, Any]:
    try:
        with open(_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:  # noqa: BLE001
        logger.warning("pricing.json unreadable (%s); using the built-in copy", exc)
        return _FALLBACK


PRICING: dict[str, Any] = _load()
FREE_REPORTS_ON_SIGNUP: int = int(PRICING["free_reports_on_signup"])


def plan(plan_id: str) -> dict[str, Any]:
    return next(p for p in PRICING["plans"] if p["id"] == plan_id)
