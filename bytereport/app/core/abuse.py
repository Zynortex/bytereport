"""
Per-IP rate limits and throwaway-address blocking.

Both are in-process and cost nothing to run. That is also their limit: the
counters live in one worker's memory, so N workers means roughly N times the
stated allowance, and a restart forgets everything. That is acceptable for a
flood brake. What an account may spend is NOT kept here: report credits and
the per-account daily cap live in Supabase (app/services/credits.py).
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

logger = logging.getLogger(__name__)


# ── Throwaway email domains ─────────────────────────────────────────────────
#
# Not exhaustive and never will be — new domains appear daily. It closes the
# cheapest path (the handful of services that show up first in a search) and
# raises the cost of the rest. Kept deliberately short: a giant list is a
# maintenance burden that adds little over the head of the distribution.

DISPOSABLE_DOMAINS: frozenset[str] = frozenset({
    "10minutemail.com", "10minutemail.net", "20minutemail.com",
    "guerrillamail.com", "guerrillamail.net", "guerrillamail.org", "sharklasers.com",
    "mailinator.com", "mailinator.net", "maildrop.cc", "mailnesia.com",
    "temp-mail.org", "tempmail.com", "tempmailo.com", "tempr.email",
    "throwawaymail.com", "trashmail.com", "trashmail.de", "wegwerfmail.de",
    "yopmail.com", "yopmail.fr", "yopmail.net",
    "getnada.com", "nada.email", "dispostable.com", "fakeinbox.com",
    "mohmal.com", "emailondeck.com", "spamgourmet.com", "mytemp.email",
    "moakt.com", "tempail.com", "burnermail.io", "mailsac.com",
    "inboxkitten.com", "linshiyouxiang.net", "1secmail.com", "1secmail.org",
})


def is_disposable(email: str) -> bool:
    """True for an address whose domain is a known throwaway service."""
    if not email or "@" not in email:
        return False
    domain = email.rsplit("@", 1)[1].strip().lower().rstrip(".")
    if domain in DISPOSABLE_DOMAINS:
        return True
    # mail.tm and friends hand out many subdomains off one parent.
    parts = domain.split(".")
    for i in range(1, len(parts) - 1):
        if ".".join(parts[i:]) in DISPOSABLE_DOMAINS:
            return True
    return False


# ── IP rate limiting ────────────────────────────────────────────────────────

class SlidingWindow:
    """
    Per-key request timestamps in a fixed window.

    A sliding window rather than a fixed bucket: a fixed bucket lets a caller
    spend the whole allowance at 11:59 and the whole allowance again at 12:00,
    which is exactly the burst this is meant to stop.
    """

    def __init__(self, limit: int, window_seconds: float) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> tuple[bool, float]:
        """(allowed, seconds until a slot frees up)."""
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return False, max(0.0, self.window - (now - hits[0]))
            hits.append(now)
            # Keys accumulate; drop the empty ones occasionally so a long-lived
            # process does not grow a dict entry per IP that ever called.
            if len(self._hits) > 4096:
                for k in [k for k, v in self._hits.items() if not v]:
                    del self._hits[k]
            return True, 0.0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


def client_ip(request: Request) -> str:
    """
    The caller's address, honouring one proxy hop.

    X-Forwarded-For is client-controlled, so the LAST entry is taken: on Railway
    or any single reverse proxy the platform appends the real peer, and reading
    the first entry instead would let a caller spoof a new identity per request.
    """
    xff = request.headers.get("x-forwarded-for")
    if xff:
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        if parts:
            return parts[-1]
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()
    return request.client.host if request.client else "unknown"


def enforce(window: SlidingWindow, key: str, what: str) -> None:
    allowed, retry_after = window.check(key)
    if allowed:
        return
    logger.warning("rate limit hit: %s key=%s", what, key)
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Слишком много запросов. Попробуйте позже.",
        headers={"Retry-After": str(int(retry_after) + 1)},
    )
