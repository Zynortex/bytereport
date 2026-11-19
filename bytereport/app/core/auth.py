"""
Who is calling, verified.

Before this module the backend had NO authentication of any kind. The frontend
sent `Authorization: Bearer <supabase token>` and nothing read it: every
endpoint that spends OpenAI money — /report/analyze, /chat, /voice/parse,
/voice/photo, /voice/transcribe — answered anyone on the internet.

That matters for the whole abuse discussion. Email confirmation, disposable
domain blocking and per-account limits all live at the sign-up layer, and a
script skips that layer entirely by POSTing to the API. None of them do
anything until the API knows who is calling. This is the load-bearing one.

Verification is local and free. The Supabase project publishes a JWKS, so
tokens are checked against a cached public key with no round trip and no new
secret. HS256 projects can set SUPABASE_JWT_SECRET instead.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

from fastapi import Depends, Header, HTTPException, status

from app.core.config import settings

logger = logging.getLogger(__name__)

# A signing key rotates rarely; an hour of caching costs nothing and removes
# the network from the hot path entirely.
_JWKS_TTL_SECONDS = 3600.0
_jwks_cache: dict[str, Any] = {}
_jwks_fetched_at = 0.0


class UnverifiableToken(Exception):
    """The token is bad. Distinct from being unable to verify ANY token."""


class VerificationUnavailable(Exception):
    """No signing key at all — our problem, not the caller's."""


# Signature algorithms we will accept. "none" is the classic forgery: a
# well-formed token with an empty signature. An allowlist checked before the
# key lookup means such a token is rejected as a bad token, never as a server
# fault, and never reaches the decoder.
_ALLOWED_ALGS = frozenset({"HS256", "RS256", "ES256"})


@dataclass(frozen=True)
class AuthUser:
    id: str
    email: str
    email_verified: bool
    claims: dict[str, Any]


def _jwks_url() -> str:
    return f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"


def _fetch_jwks() -> Optional[dict[str, Any]]:
    global _jwks_cache, _jwks_fetched_at
    if _jwks_cache and (time.monotonic() - _jwks_fetched_at) < _JWKS_TTL_SECONDS:
        return _jwks_cache
    try:
        import httpx

        resp = httpx.get(_jwks_url(), timeout=8.0)
        resp.raise_for_status()
        keys = resp.json()
    except Exception as exc:  # noqa: BLE001 - a failure must not 500 the request
        logger.warning("auth: JWKS fetch failed: %s", exc)
        # Serve a stale copy rather than locking every user out over a blip.
        return _jwks_cache or None
    if isinstance(keys, dict) and keys.get("keys"):
        _jwks_cache = keys
        _jwks_fetched_at = time.monotonic()
        return keys
    return _jwks_cache or None


def _decode(token: str) -> dict[str, Any]:
    """Verify the signature and standard claims. Raises jose exceptions."""
    from jose import jwt

    # audience: Supabase issues "authenticated" for a signed-in user.
    options = {"verify_aud": False}   # checked explicitly below, with a clearer error

    # Read and vet the header before touching keys, so an alg=none token is
    # refused on its own terms rather than falling through to a key lookup.
    try:
        header = jwt.get_unverified_header(token)
    except Exception as exc:  # noqa: BLE001 - malformed token
        raise UnverifiableToken(f"unreadable header: {type(exc).__name__}")
    if header.get("alg") not in _ALLOWED_ALGS:
        raise UnverifiableToken(f"refused algorithm {header.get('alg')!r}")

    if settings.supabase_jwt_secret:
        return jwt.decode(
            token, settings.supabase_jwt_secret, algorithms=["HS256"], options=options
        )

    jwks = _fetch_jwks()
    if not jwks:
        raise VerificationUnavailable("no signing keys could be loaded")

    kid = header.get("kid")
    key = next((k for k in jwks["keys"] if k.get("kid") == kid), None)
    if key is None:
        # Either the key rotated since the cache was filled, or the token names
        # a key that never existed. Refetch once to tell the two apart.
        _jwks_cache.clear()
        jwks = _fetch_jwks()
        key = next((k for k in (jwks or {}).get("keys", []) if k.get("kid") == kid), None)
    if key is None:
        # A token naming an unknown key is a BAD TOKEN, not a broken server.
        # Classifying it as a server fault let anyone force a 503 by sending a
        # token with no kid at all.
        raise UnverifiableToken(f"no key for kid={kid!r}")

    alg = key.get("alg", "ES256")
    if alg not in _ALLOWED_ALGS:
        raise UnverifiableToken(f"unsupported key algorithm {alg!r}")
    return jwt.decode(token, key, algorithms=[alg], options=options)


def _is_token_error(exc: Exception) -> bool:
    """
    True when jose rejected the token itself: bad signature, expired, wrong
    claims, malformed key material. Every such error derives from JOSEError.

    If jose cannot be imported, nothing it could have raised reached us, so
    the answer is False and the caller treats the failure as a server fault.
    """
    try:
        from jose.exceptions import JOSEError
    except Exception:  # noqa: BLE001 - jose missing is exactly the fault case
        return False
    return isinstance(exc, JOSEError)


def _email_verified(claims: dict[str, Any]) -> bool:
    """
    Whether the token says the address is confirmed.

    Absence is treated as CONFIRMED, and that is the important part. A Supabase
    JWT does not carry `email_confirmed_at` — the authoritative column lives on
    the user row and never reaches the token. What the token has is
    `user_metadata.email_verified`, which is written at sign-up from the
    identity provider and is not updated by a manual
    `UPDATE auth.users SET email_confirmed_at = now()`. Reading it as the
    confirmation state rejects accounts that are genuinely confirmed.

    The real gate is Supabase's own: with "Confirm email" enabled, an
    unconfirmed user cannot obtain a session at all, so a valid token IS the
    proof. Re-deriving that from an unreliable claim only adds false refusals.
    """
    for source in (claims, claims.get("app_metadata") or {}, claims.get("user_metadata") or {}):
        value = source.get("email_verified")
        if value is True:
            return True
    if claims.get("email_confirmed_at"):
        return True
    # No claim we can trust either way. Supabase already decided by issuing the
    # token; second-guessing it here is what produced the false 403.
    return True


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def optional_user(
    authorization: Optional[str] = Header(default=None),
) -> Optional[AuthUser]:
    """The caller if the token is valid, None if there is no token at all."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        return None

    try:
        claims = _decode(token)
    except UnverifiableToken as exc:
        logger.info("auth: rejected a token (%s)", exc)
        raise _unauthorized("Недействительный или истёкший токен.")
    except VerificationUnavailable as exc:
        # A configuration problem, not the caller's fault. Fail CLOSED anyway:
        # answering while unable to check identity is how the bill happens.
        logger.error("auth: cannot verify tokens (%s)", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Проверка авторизации временно недоступна.",
        )
    except Exception as exc:  # noqa: BLE001 - classified below
        if _is_token_error(exc):
            logger.info("auth: rejected a token (%s)", type(exc).__name__)
            raise _unauthorized("Недействительный или истёкший токен.")
        # Anything that is not jose judging the token — a missing package, a
        # bug, a broken key object — is OUR fault. Reporting it as "invalid
        # token" sent every signed-in user to the login screen on a deploy
        # that lacked python-jose, and hid the cause from the log entirely.
        logger.exception("auth: token verification crashed (server fault, not a bad token)")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Внутренняя ошибка проверки авторизации.",
        )

    if claims.get("aud") not in (None, "authenticated"):
        raise _unauthorized("Токен выдан не для этого приложения.")

    email = (claims.get("email") or "").strip().lower()
    verified = _email_verified(claims)
    return AuthUser(
        id=str(claims.get("sub") or ""), email=email,
        email_verified=verified, claims=claims,
    )


async def require_user(user: Optional[AuthUser] = Depends(optional_user)) -> AuthUser:
    """Reject anonymous callers. Use on anything that spends money."""
    if not settings.auth_required:
        # An explicit local-development escape hatch, logged loudly so it is
        # never mistaken for the deployed configuration.
        if user is None:
            logger.warning("auth: AUTH_REQUIRED is off — serving an anonymous caller")
            return AuthUser(id="anonymous", email="", email_verified=True, claims={})
        return user
    if user is None:
        raise _unauthorized("Требуется вход в аккаунт.")
    if not user.id:
        raise _unauthorized("Токен без идентификатора пользователя.")
    return user


async def require_verified_user(user: AuthUser = Depends(require_user)) -> AuthUser:
    """
    As require_user, plus a confirmed email address.

    This is what makes an account farm cost something: a throwaway address has
    to be reachable before it can spend a single token.
    """
    if settings.auth_required and settings.require_email_verification and not user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Подтвердите email — мы отправили письмо со ссылкой.",
        )
    return user
