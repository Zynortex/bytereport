"""
Currency conversion against the Central Bank of Uzbekistan.

A note like "заказчик заплатил 200 долларов" used to end at a dead end: the row
was flagged "currency USD, rate unknown" and the user had to look the rate up
and do the arithmetic themselves. This turns that into a filled-in number plus
a citation of the rate it came from.

The conversion is a SUGGESTION, never a fact: the row stays flagged, and the
note says which rate on which date produced the figure, so the user can accept
it at a glance or overwrite it.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional

logger = logging.getLogger(__name__)

CBU_URL = "https://cbu.uz/ru/arkhiv-kursov-valyut/json"

# CBU quotes everything against the som, so UZS is the pivot for any pair.
BASE_CURRENCY = "UZS"

# What the note parser is allowed to convert. CBU publishes far more, but these
# are the currencies the business-currency chips offer.
SUPPORTED = frozenset({"USD", "EUR", "RUB", "KZT", "UZS"})

# Short on purpose. A rate lookup must never be what makes a note parse feel
# slow, and a miss is recoverable — the row simply keeps its "rate unknown"
# flag, which is the behaviour that existed before this module.
HTTP_TIMEOUT_SECONDS = 8.0

# (currency, iso date) -> rate to UZS. A published rate for a calendar day is
# immutable, so this never needs invalidating within a process.
_CACHE: dict[tuple[str, str], Optional[float]] = {}


def cache_clear() -> None:
    _CACHE.clear()


def _fetch_rate(currency: str, on: date) -> Optional[float]:
    """One CBU lookup. Returns UZS per 1 unit, or None if anything goes wrong."""
    try:
        import httpx
    except ImportError:  # pragma: no cover - httpx ships with the openai SDK
        logger.warning("fx: httpx not installed, conversion disabled")
        return None

    url = f"{CBU_URL}/{currency}/{on.isoformat()}/"
    try:
        resp = httpx.get(url, timeout=HTTP_TIMEOUT_SECONDS)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:  # noqa: BLE001 - any failure degrades, never raises
        logger.warning("fx: CBU lookup failed for %s on %s: %s", currency, on, exc)
        return None

    if not isinstance(payload, list) or not payload:
        # CBU answers 200 with an empty list for dates it has no data for —
        # weekends, holidays, and any date in the future.
        logger.info("fx: CBU has no rate for %s on %s", currency, on)
        return None

    entry = payload[0]
    try:
        rate = float(entry["Rate"])
        # Rate is quoted per `Nominal` units — 1 for USD, but 100 or 1000 for
        # the small-denomination currencies. Ignoring it is off by two orders
        # of magnitude and looks plausible enough to ship.
        nominal = float(entry.get("Nominal") or 1)
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning("fx: unexpected CBU payload for %s: %s", currency, exc)
        return None

    if nominal <= 0 or rate <= 0:
        return None
    return rate / nominal


def rate_to_uzs(currency: str, on: date) -> Optional[float]:
    """UZS per one unit of `currency`, cached per calendar day."""
    ccy = currency.strip().upper()
    if ccy == BASE_CURRENCY:
        return 1.0
    if ccy not in SUPPORTED:
        return None

    key = (ccy, on.isoformat())
    if key in _CACHE:
        return _CACHE[key]

    rate = _fetch_rate(ccy, on)
    # Failures are cached too. Without that, a note with five USD rows during a
    # CBU outage makes five doomed requests and stalls the parse by 40 seconds.
    _CACHE[key] = rate
    return rate


def convert(
    amount: float, from_ccy: str, to_ccy: str, on: date
) -> Optional[tuple[float, float]]:
    """
    Convert `amount` and report the single rate that did it.

    Returns (converted_amount, rate) where `rate` is how many units of `to_ccy`
    one unit of `from_ccy` buys — the number worth showing the user. Returns
    None when either leg is unavailable, so the caller keeps the original.
    """
    src, dst = from_ccy.strip().upper(), to_ccy.strip().upper()
    if src == dst:
        return None

    src_uzs = rate_to_uzs(src, on)
    dst_uzs = rate_to_uzs(dst, on)
    if not src_uzs or not dst_uzs:
        return None

    # Cross rate through the som: USD -> UZS -> RUB. Both legs come from the
    # same publication date, so the pair is internally consistent.
    rate = src_uzs / dst_uzs
    return round(amount * rate, 2), rate


def parse_cbu_date(value: str) -> Optional[date]:
    """CBU stamps its own responses DD.MM.YYYY."""
    try:
        return datetime.strptime(value.strip(), "%d.%m.%Y").date()
    except (ValueError, AttributeError):
        return None
