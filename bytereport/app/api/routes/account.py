"""The signed-in account's own state: for now, how many reports are left."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.auth import AuthUser, require_verified_user
from app.services import credits
from app.services.pricing import FREE_REPORTS_ON_SIGNUP

router = APIRouter(prefix="/account", tags=["account"])
logger = logging.getLogger(__name__)


class CreditsResponse(BaseModel):
    # None when the account is unlimited (the owner's own addresses).
    balance: Optional[int]
    unlimited: bool
    signup_bonus: int
    # Ever granted reports by hand — picks the "package used up" wording.
    paid: bool = False


@router.get("/credits", response_model=CreditsResponse)
async def get_credits(user: AuthUser = Depends(require_verified_user)) -> CreditsResponse:
    """
    Reports left on this account. The first call also pays the signup bonus,
    so a brand-new account sees its free reports before running anything.
    """
    if credits.is_unlimited(user.email):
        return CreditsResponse(balance=None, unlimited=True, signup_bonus=FREE_REPORTS_ON_SIGNUP)
    try:
        st = await credits.credit_store.status(user.id)
    except credits.CreditsUnavailable as exc:
        logger.error("credits: cannot read balance for user=%s (%s)", user.id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Учёт отчётов временно недоступен.",
        )
    return CreditsResponse(balance=st.balance, unlimited=False, signup_bonus=FREE_REPORTS_ON_SIGNUP, paid=st.paid)
