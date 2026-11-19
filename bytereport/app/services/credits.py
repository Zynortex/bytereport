"""
Report credits: how many full AI reports an account may still run.

The balance lives in Supabase (supabase/migrations/*_report_credits.sql), so a
restart or a second worker changes nothing. The backend talks to it through
four SQL functions over PostgREST, with the service-role key: spending and
refunding must never be possible with a user's own token, or a user could
refund themselves into unlimited reports.

Two stores, one interface:
  * SupabaseCredits — production;
  * MemoryCredits   — tests and local development (CREDITS_STORE=memory).
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Protocol

from app.core.config import settings
from app.services.pricing import FREE_REPORTS_ON_SIGNUP

logger = logging.getLogger(__name__)


class CreditsUnavailable(Exception):
    """The balance cannot be read or changed right now. Fail closed."""


@dataclass(frozen=True)
class SpendResult:
    ok: bool
    balance: int
    event_id: Optional[int] = None
    reason: Optional[str] = None      # "no_credits" | "daily_cap"
    # On a refusal: has this account ever been granted reports by hand? It
    # decides "free reports are used up" vs "your package is used up".
    paid: bool = False


@dataclass(frozen=True)
class CreditStatus:
    balance: int
    paid: bool


class CreditStore(Protocol):
    async def status(self, user_id: str) -> CreditStatus: ...
    async def consume(self, user_id: str) -> SpendResult: ...
    async def refund(self, event_id: int) -> None: ...


def is_unlimited(email: str) -> bool:
    """The owner's own accounts never run out (UNLIMITED_REPORT_EMAILS)."""
    allowed = {e.strip().lower() for e in settings.unlimited_report_emails.split(",") if e.strip()}
    return bool(email) and email.strip().lower() in allowed


# ── Supabase ────────────────────────────────────────────────────────────────

class SupabaseCredits:
    def __init__(self, url: str, service_key: str, timeout: float = 8.0) -> None:
        self._base = url.rstrip("/") + "/rest/v1/rpc/"
        self._key = service_key
        self._timeout = timeout

    async def _rpc(self, fn: str, args: dict):
        if not self._base.startswith("http") or not self._key:
            raise CreditsUnavailable("SUPABASE_URL / SUPABASE_SERVICE_KEY not configured")
        import httpx  # lazy: not needed for /health on a cold start

        headers = {
            "apikey": self._key,
            "Authorization": f"Bearer {self._key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(self._base + fn, json=args, headers=headers)
        except httpx.HTTPError as exc:
            raise CreditsUnavailable(f"{fn}: {type(exc).__name__}") from exc
        if resp.status_code >= 400:
            # The body names the problem (missing function = migration not run,
            # 401 = wrong key). Logged; never shown to the user.
            raise CreditsUnavailable(f"{fn}: HTTP {resp.status_code} {resp.text[:300]}")
        return resp.json()

    async def status(self, user_id: str) -> CreditStatus:
        data = await self._rpc("get_report_credit_status", {
            "p_user": user_id, "p_signup_bonus": FREE_REPORTS_ON_SIGNUP,
        })
        return CreditStatus(balance=int(data.get("balance") or 0), paid=bool(data.get("paid")))

    async def consume(self, user_id: str) -> SpendResult:
        data = await self._rpc("consume_report_credit", {
            "p_user": user_id,
            "p_signup_bonus": FREE_REPORTS_ON_SIGNUP,
            "p_daily_cap": settings.report_daily_cap,
        })
        return SpendResult(
            ok=bool(data.get("ok")),
            balance=int(data.get("balance") or 0),
            event_id=data.get("event_id"),
            reason=data.get("reason"),
            paid=bool(data.get("paid")),
        )

    async def refund(self, event_id: int) -> None:
        await self._rpc("refund_report_credit", {"p_event": event_id})


# ── In memory ───────────────────────────────────────────────────────────────

class MemoryCredits:
    """Same rules as the SQL functions, held in a dict. Not for production."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._balance: dict[str, int] = {}
        self._events: dict[int, tuple[str, datetime, bool]] = {}   # id -> (user, at, refunded)
        self._paid: set[str] = set()
        self._next = 1

    def _ensure(self, user_id: str) -> None:
        if user_id not in self._balance:
            self._balance[user_id] = FREE_REPORTS_ON_SIGNUP

    async def status(self, user_id: str) -> CreditStatus:
        with self._lock:
            self._ensure(user_id)
            return CreditStatus(balance=self._balance[user_id], paid=user_id in self._paid)

    async def consume(self, user_id: str) -> SpendResult:
        with self._lock:
            self._ensure(user_id)
            bal = self._balance[user_id]
            cap = settings.report_daily_cap
            if cap > 0:
                since = datetime.now(timezone.utc) - timedelta(hours=24)
                today = sum(1 for u, at, refunded in self._events.values()
                            if u == user_id and at > since and not refunded)
                if today >= cap:
                    return SpendResult(ok=False, balance=bal, reason="daily_cap", paid=user_id in self._paid)
            if bal <= 0:
                return SpendResult(ok=False, balance=bal, reason="no_credits", paid=user_id in self._paid)
            self._balance[user_id] = bal - 1
            event_id = self._next
            self._next += 1
            self._events[event_id] = (user_id, datetime.now(timezone.utc), False)
            return SpendResult(ok=True, balance=bal - 1, event_id=event_id)

    async def refund(self, event_id: int) -> None:
        with self._lock:
            ev = self._events.get(event_id)
            if not ev or ev[2]:
                return
            user_id, at, _ = ev
            self._events[event_id] = (user_id, at, True)
            self._balance[user_id] += 1

    # Test helpers
    def grant(self, user_id: str, amount: int) -> None:
        """A manual top-up, as grant_report_credits() records it."""
        with self._lock:
            self._ensure(user_id)
            self._balance[user_id] += amount
            if amount > 0:
                self._paid.add(user_id)

    def set_balance(self, user_id: str, value: int) -> None:
        with self._lock:
            self._balance[user_id] = value

    def reset(self) -> None:
        with self._lock:
            self._balance.clear()
            self._events.clear()
            self._paid.clear()


def _make_store() -> CreditStore:
    if settings.credits_store == "memory":
        logger.warning("credits: in-memory store — balances reset on restart (dev/test only)")
        return MemoryCredits()
    return SupabaseCredits(settings.supabase_url, settings.supabase_service_key)


credit_store: CreditStore = _make_store()
