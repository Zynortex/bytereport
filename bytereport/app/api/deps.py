"""
Shared dependencies for the endpoints that cost money.

One place, so adding an AI endpoint means adding a dependency rather than
remembering five separate rules. The voice/photo feature was added while the
API had no auth at all; had this existed, it would have been protected on the
day it shipped.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, HTTPException, Request, status

from app.core.abuse import SlidingWindow, client_ip, enforce, is_disposable
from app.core.auth import AuthUser, require_verified_user
from app.core.config import settings
from app.services import credits
from app.services.report_copy import copy_text

logger = logging.getLogger(__name__)

# Two tiers. A full report is the expensive call; chat and note parsing are an
# order of magnitude cheaper and get a looser allowance.
# Both per IP and in process memory. The per-account rules (balance, daily
# cap) live in Supabase; these only blunt a flood from one address and are
# allowed to reset on a restart.
report_limiter = SlidingWindow(settings.rate_limit_report_per_hour, 3600.0)
ai_limiter = SlidingWindow(settings.rate_limit_ai_per_hour, 3600.0)

def request_language(request: Request) -> str:
    """ru / uz / en from Accept-Language (the web sends the interface language)."""
    header = (request.headers.get("accept-language") or "").lower()
    for part in header.split(","):
        code = part.split(";")[0].strip()[:2]
        if code in ("ru", "uz", "en"):
            return code
    return "ru"


def no_credits_detail(paid: bool, language: str) -> str:
    """Same sentence as the upload page shows (report-copy.json → credits_exhausted)."""
    return copy_text("credits_exhausted", "paid" if paid else "free", language)


def _reject_disposable(user: AuthUser) -> None:
    if not settings.block_disposable_email or not settings.auth_required:
        return
    if is_disposable(user.email):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Одноразовые почтовые адреса не поддерживаются. "
                   "Укажите постоянный email.",
        )


async def ai_caller(
    request: Request,
    user: AuthUser = Depends(require_verified_user),
) -> AuthUser:
    """
    A named, confirmed, non-throwaway caller, within the hourly IP allowance.

    The IP limit is checked as well as the account rules: an account farm has
    many accounts but usually few addresses, and the limit applies before any
    token is spent.
    """
    _reject_disposable(user)
    enforce(ai_limiter, client_ip(request), "ai")
    return user


@dataclass(frozen=True)
class ReportCaller:
    user: AuthUser
    # The spend to give back if the report fails. None for unlimited accounts.
    credit_event: Optional[int]
    balance: Optional[int]


async def report_caller(
    request: Request,
    user: AuthUser = Depends(require_verified_user),
) -> ReportCaller:
    """
    As `ai_caller`, plus the tighter report limit and one report credit.

    The credit is spent BEFORE the provider is called, so two simultaneous
    requests cannot both use the last report. The route refunds it if the
    analysis fails.
    """
    _reject_disposable(user)
    enforce(report_limiter, client_ip(request), "report")

    if credits.is_unlimited(user.email):
        return ReportCaller(user=user, credit_event=None, balance=None)

    try:
        spend = await credits.credit_store.consume(user.id)
    except credits.CreditsUnavailable as exc:
        # Fail closed: running a paid report we cannot account for is exactly
        # the cost this system exists to control.
        logger.error("credits: cannot spend for user=%s (%s)", user.id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Учёт отчётов временно недоступен. Попробуйте через минуту.",
        )

    if not spend.ok:
        if spend.reason == "daily_cap":
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Не больше {settings.report_daily_cap} отчётов за сутки. "
                       "Продолжить можно завтра.",
            )
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED,
                            detail=no_credits_detail(spend.paid, request_language(request)))

    return ReportCaller(user=user, credit_event=spend.event_id, balance=spend.balance)


async def refund_report(caller: ReportCaller) -> None:
    """Give the credit back. Never raises: the user is already getting an error."""
    if caller.credit_event is None:
        return
    try:
        await credits.credit_store.refund(caller.credit_event)
        logger.info("credits: refunded event=%s user=%s", caller.credit_event, caller.user.id)
    except Exception:  # noqa: BLE001
        # The user lost a report to our failure. Loud, with what is needed to
        # put it back by hand.
        logger.exception("credits: REFUND FAILED event=%s user=%s — restore by hand",
                         caller.credit_event, caller.user.id)


# Parsing a file and computing metrics costs no upstream money, so these stay
# open to keep every existing flow working — but they do burn CPU and memory,
# so a hammer still gets throttled.
upload_limiter = SlidingWindow(settings.rate_limit_ai_per_hour, 3600.0)


async def throttled_anonymous(request: Request) -> None:
    enforce(upload_limiter, client_ip(request), "upload")
