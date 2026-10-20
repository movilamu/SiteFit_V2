"""Supabase access helpers.

The API talks to Supabase in two ways:

* via the PostgREST HTTP API using ``requests`` (used by the ingestion-side
  and read-heavy routes), and
* via the official ``supabase`` Python client (used where the query builder
  is more convenient).

Both paths read credentials from :mod:`api.app.core.config`; no credential
is ever accepted from a request payload.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from api.app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

try:  # pragma: no cover - optional dependency
    from supabase import Client, create_client
except ImportError:  # pragma: no cover
    Client = None  # type: ignore[assignment]
    create_client = None  # type: ignore[assignment]


class SupabaseNotConfiguredError(RuntimeError):
    """Raised when Supabase credentials are missing at the point of use."""


def is_supabase_configured(settings: Optional[Settings] = None) -> bool:
    settings = settings or get_settings()
    return settings.has_supabase


def get_supabase_client(settings: Optional[Settings] = None) -> "Client":
    """Return a Supabase client built from server-side configuration.

    Raises:
        SupabaseNotConfiguredError: when credentials are missing or the
            ``supabase`` package is not installed.
    """

    settings = settings or get_settings()
    if not settings.has_supabase:
        raise SupabaseNotConfiguredError(
            "Supabase is not configured. Set SUPABASE_URL and "
            "SUPABASE_KEY (or SUPABASE_SERVICE_ROLE_KEY)."
        )
    if create_client is None:  # pragma: no cover - optional dependency
        raise SupabaseNotConfiguredError(
            "The 'supabase' Python package is not installed."
        )

    return create_client(settings.supabase_url, settings.supabase_service_key)


def rest_get(
    path: str,
    params: Optional[dict[str, Any]] = None,
    *,
    settings: Optional[Settings] = None,
    timeout: float = 30.0,
) -> Optional[Any]:
    """Perform a read-only PostgREST request.

    Returns ``None`` when Supabase is not configured or the request fails,
    so callers can degrade to an explicit "data unavailable" state rather
    than raising an opaque error to the user.
    """

    settings = settings or get_settings()
    if not settings.has_supabase:
        return None

    try:
        import requests
    except ImportError:  # pragma: no cover
        logger.warning("requests is not installed; cannot query Supabase REST API")
        return None

    key = settings.supabase_service_key
    base = (settings.supabase_url or "").rstrip("/")
    endpoint = f"{base}/rest/v1/{path.lstrip('/')}"
    headers = {
        "apikey": key or "",
        "Authorization": f"Bearer {key or ''}",
        "Accept": "application/json",
    }

    try:
        response = requests.get(endpoint, headers=headers, params=params, timeout=timeout)
    except Exception as exc:  # pragma: no cover - network failure
        logger.warning("Supabase REST request to %s failed: %s", path, exc)
        return None

    if response.status_code != 200:
        logger.warning(
            "Supabase REST request to %s returned HTTP %s", path, response.status_code
        )
        return None

    try:
        return response.json()
    except ValueError:  # pragma: no cover
        logger.warning("Supabase REST request to %s returned non-JSON", path)
        return None


__all__ = [
    "SupabaseNotConfiguredError",
    "get_supabase_client",
    "is_supabase_configured",
    "rest_get",
]
