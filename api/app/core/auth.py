"""Authentication for the API.

The platform authenticates through Supabase Auth (Google provider).  The
browser holds a Supabase session; the frontend forwards the access token
as a bearer token on every API call, and the API verifies it here before
resolving the user.

Verification order:

1. **Local JWT verification.**  The token is verified against the
   project's signing keys.  Modern Supabase projects sign with RS256 and
   publish their keys at ``/auth/v1/.well-known/jwks.json``; older ones
   sign with HS256 using the project's JWT secret.  Both are supported.
   The key set is cached, so verification does not make a network call on
   every request.
2. **Supabase user lookup.**  If the token cannot be verified locally --
   for example because the project only publishes a shared secret that has
   not been configured -- the token is presented to Supabase's ``/user``
   endpoint instead.

If Supabase is not configured at all, the API refuses authenticated
requests.  Anonymous access is only permitted when
``ALLOW_ANONYMOUS_API`` is explicitly enabled, which is intended for
local development and for the read-only analytical endpoints.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional

from fastapi import HTTPException, Request, status

from api.app.core.config import get_settings

logger = logging.getLogger(__name__)

#: How long the signing keys are cached for, in seconds.
JWKS_CACHE_SECONDS = 3600

_JWKS_CACHE: dict[str, Any] = {"key": None, "fetched_at": 0.0, "keys": None}
_JWKS_LOCK = threading.Lock()


@dataclass(frozen=True)
class AuthenticatedUser:
    """A user resolved from a verified access token."""

    id: str
    email: Optional[str] = None
    provider: Optional[str] = None
    role: str = "authenticated"

    @property
    def is_anonymous(self) -> bool:
        return self.role == "anonymous"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "email": self.email,
            "provider": self.provider,
            "role": self.role,
        }


class AuthenticationError(HTTPException):
    """Raised when a request cannot be attributed to a valid session."""

    def __init__(self, detail: str, status_code: int = status.HTTP_401_UNAUTHORIZED):
        super().__init__(status_code=status_code, detail=detail)


def _bearer_token(request: Request) -> Optional[str]:
    header = request.headers.get("authorization") or request.headers.get("Authorization")
    if not header:
        return None
    parts = header.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token or None


def _jwks(settings) -> Optional[dict[str, Any]]:
    """Return the cached signing keys, refreshing them when they are stale."""

    global _JWKS_CACHE

    url = settings.supabase_url
    if not url:
        return None

    endpoint = f"{url.rstrip('/')}/auth/v1/.well-known/jwks.json"
    with _JWKS_LOCK:
        now = time.time()
        if _JWKS_CACHE["keys"] is not None and (
            _JWKS_CACHE["key"] == endpoint
            and now - _JWKS_CACHE["fetched_at"] < JWKS_CACHE_SECONDS
        ):
            return _JWKS_CACHE["keys"]

        try:
            import httpx

            response = httpx.get(endpoint, timeout=8.0)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            logger.warning("Could not fetch the Supabase signing keys: %s", exc)
            return _JWKS_CACHE["keys"]

        _JWKS_CACHE = {
            "key": endpoint,
            "fetched_at": now,
            "keys": payload,
        }
        return payload


def _decode_jwt(token: str, settings) -> Optional[dict[str, Any]]:
    """Verify and decode a JWT locally, or return ``None``."""

    try:
        import jwt
        from jwt import PyJWKClient
    except ImportError:  # pragma: no cover - optional dependency
        return None

    url = settings.supabase_url
    secret = settings.supabase_jwt_secret

    # RS256 via the published key set.
    if url:
        keys = _jwks(settings)
        if keys and keys.get("keys"):
            try:
                client = PyJWKClient(
                    f"{url.rstrip('/')}/auth/v1/.well-known/jwks.json",
                    cache_keys=True,
                    lifespan=300,
                )
                signing_key = client.get_signing_key_from_jwt(token)
                return jwt.decode(
                    token,
                    signing_key.key,
                    algorithms=["RS256", "ES256"],
                    audience="authenticated",
                    options={"verify_aud": False},
                )
            except Exception as exc:
                logger.debug("Local JWKS verification failed: %s", exc)

    # HS256 via the project's shared secret.
    if secret:
        try:
            return jwt.decode(
                token,
                secret,
                algorithms=["HS256"],
                audience="authenticated",
                options={"verify_aud": False},
            )
        except Exception as exc:
            logger.debug("Local shared-secret verification failed: %s", exc)

    return None


def _lookup_user(token: str, settings) -> Optional[dict[str, Any]]:
    """Resolve a user through Supabase's user endpoint."""

    url = settings.supabase_url
    key = settings.supabase_anon_key or settings.supabase_service_key
    if not url or not key:
        return None

    try:
        import httpx

        response = httpx.get(
            f"{url.rstrip('/')}/auth/v1/user",
            headers={
                "Authorization": f"Bearer {token}",
                "apikey": key,
            },
            timeout=10.0,
        )
        if response.status_code != 200:
            return None
        return response.json()
    except Exception as exc:
        logger.warning("Could not resolve the user through Supabase: %s", exc)
        return None


def _user_from_payload(payload: dict[str, Any]) -> Optional[AuthenticatedUser]:
    user_id = payload.get("sub") or payload.get("id")
    if not user_id:
        return None
    metadata = payload.get("user_metadata") or {}
    provider = payload.get("provider") or metadata.get("provider")
    return AuthenticatedUser(
        id=str(user_id),
        email=payload.get("email") or metadata.get("email"),
        provider=provider,
        role=payload.get("role") or "authenticated",
    )


def resolve_user(request: Request) -> Optional[AuthenticatedUser]:
    """Resolve the caller from the request's bearer token.

    Returns ``None`` when there is no token, when the token is invalid, or
    when Supabase is not configured.
    """

    token = _bearer_token(request)
    if not token:
        return None

    settings = get_settings()
    if not settings.supabase_url:
        return None

    payload = _decode_jwt(token, settings)
    if payload is not None:
        user = _user_from_payload(payload)
        if user is not None:
            return user

    profile = _lookup_user(token, settings)
    if profile is None:
        return None
    return _user_from_payload(profile)


async def get_current_user(request: Request) -> AuthenticatedUser:
    """FastAPI dependency that requires a valid session.

    Raises:
        AuthenticationError: when the request is unauthenticated or the
            token is not valid.
    """

    settings = get_settings()

    if not settings.supabase_url:
        if settings.allow_anonymous_api:
            return AuthenticatedUser(id="anonymous", role="anonymous")
        raise AuthenticationError(
            "Authentication is unavailable because Supabase is not configured. "
            "Set SUPABASE_URL and SUPABASE_ANON_KEY, or enable "
            "ALLOW_ANONYMOUS_API for local development."
        )

    user = resolve_user(request)
    if user is None:
        raise AuthenticationError(
            "Your session has expired or is invalid. Sign in again to continue."
        )
    return user


async def get_optional_user(request: Request) -> Optional[AuthenticatedUser]:
    """FastAPI dependency that resolves the caller when possible.

    Used by the read-only analytical endpoints, which are useful without a
    session but behave differently for an authenticated user.
    """

    try:
        return await get_current_user(request)
    except AuthenticationError:
        return None


def require_user_id(user: AuthenticatedUser) -> str:
    """Return the identifier to persist as the owner of a record."""

    if user.is_anonymous:
        raise AuthenticationError(
            "This operation requires an authenticated account."
        )
    return user.id


__all__ = [
    "AuthenticatedUser",
    "AuthenticationError",
    "get_current_user",
    "get_optional_user",
    "require_user_id",
    "resolve_user",
]
