"""Health and readiness endpoints.

These are the endpoints a load balancer or uptime monitor should poll.  They
never expose credentials; only a coarse fingerprint of which integrations
are configured.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Response, status

from api.app.core.config import get_settings
from api.app.core.supabase_client import is_supabase_configured

router = APIRouter(tags=["Health"])

_STARTED_AT = time.time()


@router.get("/health", summary="Liveness probe")
def health() -> dict[str, Any]:
    """Return process liveness information.

    Always 200 while the process is running; it does not depend on any
    external service so that a database outage does not cause the platform
    to be killed and restarted.
    """

    settings = get_settings()
    return {
        "status": "ok",
        "service": "retail-site-intelligence-api",
        "version": "2.0.0",
        "environment": settings.environment,
        "uptime_seconds": round(time.time() - _STARTED_AT, 1),
    }


@router.get("/health/ready", summary="Readiness probe")
def readiness(response: Response) -> dict[str, Any]:
    """Report which dependencies are available.

    The HTTP status is 200 when the API can serve analytical requests and
    503 only when the normalised scoring matrix is missing, because every
    ranking endpoint depends on it.
    """

    settings = get_settings()
    fingerprint = settings.public_fingerprint()

    # The matrix is resolved through the same path the ranking endpoints
    # use, so the probe reports the service as ready exactly when a
    # ranking can actually be produced.
    matrix_ready, matrix_detail = _matrix_ready()

    fingerprint["scoring_matrix_ready"] = matrix_ready
    fingerprint["scoring_matrix"] = matrix_detail
    if not matrix_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ready" if matrix_ready else "degraded",
        "checks": fingerprint,
    }


def _matrix_ready() -> tuple[bool, str]:
    """Report whether a normalised scoring matrix can be resolved.

    The check goes through the same resolution path the ranking
    endpoints use: an injected matrix, a configured file, or the latest
    matrix published to Supabase Storage.
    """

    try:
        from api.app.core.matrix_store import (
            MatrixUnavailableError,
            load_normalized_matrix,
        )
    except Exception as exc:  # pragma: no cover - defensive
        return False, f"the matrix store could not be loaded: {exc}"

    try:
        matrix = load_normalized_matrix()
    except MatrixUnavailableError as exc:
        return False, str(exc)
    except Exception as exc:  # pragma: no cover - defensive
        return False, f"the matrix could not be loaded: {exc}"

    return (
        True,
        f"{int(matrix.shape[0])} sites and {int(matrix.shape[1])} criteria",
    )


@router.get("/health/integrations", summary="Integration fingerprint")
def integrations() -> dict[str, Any]:
    """List which external integrations are configured (never their secrets)."""

    settings = get_settings()
    return {
        "supabase_configured": is_supabase_configured(settings),
        "checks": settings.public_fingerprint(),
    }

@router.get("/health/config", summary="Configuration validation")
def configuration() -> dict[str, Any]:
    """Report the configuration state of every integration.

    The response states whether each integration is configured, what
    happens if it is not, and which environment variable must be set.  No
    credential value is ever included.
    """

    settings = get_settings()
    checks = settings.validation_report()
    return {
        "environment": settings.environment,
        "valid": settings.configuration_is_valid,
        "checks": checks,
        "error_count": sum(1 for check in checks if check["status"] == "error"),
        "warning_count": sum(1 for check in checks if check["status"] == "warning"),
    }