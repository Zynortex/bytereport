"""
Liveness for the pinger, and a daily touch that keeps the free database awake.

  GET /health       answers at once: no database, no AI, nothing imported
                    that a cold start would have to wait for. cron-job.org
                    calls it every 10 minutes so the free host does not sleep.

  GET /health/deep  one real query against Supabase (a HEAD select on
                    report_credits, limit 1: the database runs it, nothing comes
                    back in the body). Called once a day so the free project is
                    never paused for inactivity. The answer says only "ok" or
                    "unavailable" and how long it took — no rows, no error text,
                    no project URL.

The deep check is public, so its result is cached for a minute: a script that
hammers it costs Supabase one query a minute, not one per request.
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])

DEEP_CACHE_SECONDS = 60.0
DEEP_TIMEOUT_SECONDS = 8.0

_deep_cache: dict = {"at": 0.0, "ok": False, "ms": 0}


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "service": settings.app_name}


async def _touch_database() -> bool:
    """One SELECT that Postgres really runs. True when it answered."""
    key = settings.supabase_service_key or settings.supabase_anon_key
    base = settings.supabase_url.rstrip("/")
    if not base.startswith("http") or not key:
        logger.warning("health/deep: SUPABASE_URL or a Supabase key is not set")
        return False

    import httpx  # lazy, like every other network client here

    try:
        async with httpx.AsyncClient(timeout=DEEP_TIMEOUT_SECONDS) as client:
            resp = await client.head(
                f"{base}/rest/v1/report_credits",
                params={"select": "user_id", "limit": "1"},
                headers={"apikey": key, "Authorization": f"Bearer {key}"},
            )
    except httpx.HTTPError as exc:
        logger.warning("health/deep: %s", type(exc).__name__)
        return False
    if resp.status_code >= 400:
        # Logged for the owner; never echoed to the caller.
        logger.warning("health/deep: Supabase answered HTTP %s", resp.status_code)
        return False
    return True


@router.get("/health/deep")
async def health_deep() -> JSONResponse:
    now = time.monotonic()
    cached = bool(_deep_cache["at"]) and now - _deep_cache["at"] < DEEP_CACHE_SECONDS
    if not cached:
        t0 = time.perf_counter()
        ok = await _touch_database()
        _deep_cache.update(at=now, ok=ok, ms=round((time.perf_counter() - t0) * 1000))
    ok, ms = _deep_cache["ok"], _deep_cache["ms"]

    body = {"status": "ok" if ok else "degraded",
            "database": "ok" if ok else "unavailable",
            "database_ms": ms,
            "cached": cached}
    return JSONResponse(body, status_code=200 if ok else 503)


def reset_cache() -> None:
    """Tests only."""
    _deep_cache.update(at=0.0, ok=False, ms=0)
