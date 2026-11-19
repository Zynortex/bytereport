import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.routes import upload, analyze, report, chat, voice, account, health

# Without this the root logger has no handler, so every logger.info/debug in the
# app is discarded and only uvicorn's access lines reach the console — which is
# why a stalled request looked like "arrived, never answered" with no clue why.
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Development only: a web app on this machine, any port. Vite takes the next
# free port when 5173 is busy (5174, 5175...), and a fixed list of ports
# blocked every request the moment it did. Matched whole (Starlette uses
# fullmatch), so "http://localhost.evil.com" does not pass.
DEV_ORIGIN_REGEX = r"https?://(localhost|127\.0\.0\.1|\[::1\])(:\d{1,5})?"


def parse_origins(raw: str) -> list[str]:
    """ALLOWED_ORIGINS -> list. A trailing slash never matches a browser's
    Origin header, so it is dropped rather than left to fail silently."""
    return [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]


def cors_options(environment: str, allowed_origins: str) -> dict:
    """The CORSMiddleware arguments for a given ENVIRONMENT / ALLOWED_ORIGINS."""
    return {
        "allow_origins": parse_origins(allowed_origins),
        "allow_origin_regex": DEV_ORIGIN_REGEX if environment == "development" else None,
    }


CORS = cors_options(settings.environment, settings.allowed_origins)
logger.info("Environment: %s. CORS origins: %s%s", settings.environment,
            ", ".join(CORS["allow_origins"]) or "none",
            " + any localhost port" if CORS["allow_origin_regex"] else "")
if settings.ai_mock:
    logger.warning("AI_MOCK=1: AI answers come from a fixture, no provider is called")

app.add_middleware(
    CORSMiddleware,
    **CORS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(upload.router)
app.include_router(analyze.router)
app.include_router(report.router)
app.include_router(chat.router)
app.include_router(voice.router)
app.include_router(account.router)


@app.on_event("startup")
async def _log_routes() -> None:
    for route in app.routes:
        logger.info("Registered route: %s", getattr(route, "path", route))
