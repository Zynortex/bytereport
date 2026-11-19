from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # extra="ignore": a leftover line in an old .env (FRONTEND_URL, say) must
    # not stop the server from starting. env_ignore_empty: `AI_MOCK=` copied
    # from .env.example (or an empty variable on the host) means "not set",
    # not a value that fails to parse as a boolean and crashes the start.
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore",
                                      env_ignore_empty=True)

    app_name: str = "ByteReport API"
    debug: bool = False

    # Supabase
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_key: str = ""

    # AI provider: "openai" | "anthropic"
    # Switch with a single env var — no code changes needed
    ai_provider: str = "openai"

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1"
    # Speech-to-text for the voice-note flow. Separate from openai_model: the
    # chat model cannot transcribe, and the transcription model cannot reason.
    transcription_model: str = "gpt-4o-transcribe"
    # Reads photographed receipts and handwritten notes. Also separate from
    # openai_model: gpt-4.1 is the reasoning model, this one takes images.
    vision_model: str = "gpt-4o"

    # Anthropic (for future switch)
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-6"

    # Hard ceiling on a single AI provider call. The SDKs default to 600 s,
    # which would pin a worker thread for 10 minutes on a stalled upstream.
    # Typical observed latency for this prompt is 30-45 s.
    ai_timeout_seconds: float = 120.0

    # AI_MOCK=1: every AI call (report, chat, note, photo, transcription) is
    # answered from app/fixtures/ai_mock.json — no provider request, no key,
    # no cost. For local runs, tests and layout checks. Never on in production.
    ai_mock: bool = False

    # development | production. In development CORS also lets in a web app on
    # any localhost / 127.0.0.1 port (Vite moves to 5174, 5175... when 5173 is
    # taken). render.yaml sets production: there only ALLOWED_ORIGINS count.
    environment: Literal["development", "production"] = "development"

    # CORS: the web origins allowed to call this API, comma-separated, exactly
    # as the browser sends them (scheme + host, no trailing slash), e.g.
    # https://bytereport.vercel.app.
    allowed_origins: str = ""

    # ── Abuse protection ───────────────────────────────────────────────────
    # The backend had no authentication at all: every AI endpoint answered the
    # open internet. These default to ON because the safe default for "who may
    # spend our OpenAI budget" is "someone we can name".
    auth_required: bool = True
    # Verified locally against the project JWKS (no secret needed). Set this
    # only for a legacy HS256 project.
    supabase_jwt_secret: str = ""
    # Off by default, deliberately. The enforcement point for email
    # confirmation is Supabase's own "Confirm email" setting: with it on, an
    # unconfirmed user never gets a session, so a valid token already proves
    # it. The JWT carries no trustworthy confirmation claim to re-check against
    # (see auth._email_verified), and checking anyway rejected real accounts.
    require_email_verification: bool = False
    block_disposable_email: bool = True

    # ── Report credits ─────────────────────────────────────────────────────
    # Balances live in Supabase (supabase/migrations/*_report_credits.sql);
    # the signup bonus comes from pricing.json. "memory" is for tests and
    # local development only: balances vanish on restart.
    credits_store: str = "supabase"
    # The owner's own accounts, comma-separated. They never run out of reports
    # and are never charged; every other rule (auth, IP limits) still applies.
    unlimited_report_emails: str = ""
    # Second line of defence: at most this many reports per account in any
    # rolling 24 hours, whatever the balance. Set above an accountant's busy
    # day (25 a month), well below what a script would try. 0 disables it.
    report_daily_cap: int = 20
    # Cheap endpoints (chat, note parsing) get a looser allowance than a full
    # report, which is by far the most expensive call in the product.
    rate_limit_report_per_hour: int = 10
    rate_limit_ai_per_hour: int = 60

    # Upload
    upload_dir: str = "uploads"
    max_upload_size_mb: int = 10


settings = Settings()
