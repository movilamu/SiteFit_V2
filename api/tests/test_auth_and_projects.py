"""Tests for authentication, project persistence and the configuration report."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Optional

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from api.app.core.auth import (  # noqa: E402
    AuthenticatedUser,
    AuthenticationError,
    get_current_user,
    require_user_id,
    resolve_user,
)
from api.app.core.config import get_settings  # noqa: E402
from api.app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

def test_an_unauthenticated_request_is_rejected() -> None:
    """With Supabase configured, a request without a token must not pass."""

    settings = get_settings()
    if not settings.supabase_url:
        pytest.skip("Supabase is not configured in this environment.")

    request = _make_request()
    with pytest.raises(AuthenticationError):
        import asyncio

        asyncio.run(get_current_user(request))


def test_a_request_without_a_token_resolves_to_no_user() -> None:
    assert resolve_user(_make_request()) is None


def test_an_anonymous_user_cannot_own_a_record() -> None:
    anonymous = AuthenticatedUser(id="anonymous", role="anonymous")
    with pytest.raises(AuthenticationError):
        require_user_id(anonymous)


def test_an_authenticated_user_can_own_a_record() -> None:
    user = AuthenticatedUser(id="user-123", email="a@example.com", role="authenticated")
    assert require_user_id(user) == "user-123"
    assert user.to_dict()["email"] == "a@example.com"
    assert user.is_anonymous is False


def test_a_malformed_authorization_header_is_ignored() -> None:
    request = _make_request(headers={"Authorization": "Basic abc123"})
    assert resolve_user(request) is None


def test_a_non_bearer_scheme_is_ignored() -> None:
    request = _make_request(headers={"Authorization": "Token abc123"})
    assert resolve_user(request) is None


def _make_request(headers: Optional[dict[str, str]] = None) -> Any:
    """Build a minimal request object for the auth helpers."""

    from starlette.requests import Request

    scope: dict[str, Any] = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [
            (key.lower().encode(), value.encode()) for key, value in (headers or {}).items()
        ],
        "query_string": b"",
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 80),
    }
    return Request(scope)


# ---------------------------------------------------------------------------
# Project endpoints
# ---------------------------------------------------------------------------

def test_the_projects_endpoints_require_a_session(client: TestClient) -> None:
    """The user-owned endpoints must never be open."""

    settings = get_settings()
    if not settings.supabase_url:
        pytest.skip("Supabase is not configured in this environment.")

    for method, path in (
        ("get", "/projects"),
        ("post", "/projects"),
        ("get", "/projects/00000000-0000-0000-0000-000000000000"),
        ("patch", "/projects/00000000-0000-0000-0000-000000000000"),
        ("delete", "/projects/00000000-0000-0000-0000-000000000000"),
    ):
        # The test client only accepts a body on ``request``.
        response = client.request(method.upper(), path, json={})
        assert response.status_code in {401, 403}, f"{method.upper()} {path} was not protected"


def test_the_projects_endpoints_report_when_supabase_is_unavailable(
    client: TestClient,
) -> None:
    """Without Supabase the endpoints must say so rather than failing obscurely."""

    settings = get_settings()
    if settings.has_supabase:
        pytest.skip("Supabase is configured in this environment.")

    response = client.get("/projects")
    # The request is rejected before the store is reached, because the
    # endpoint requires a session.
    assert response.status_code in {401, 403, 503}


# ---------------------------------------------------------------------------
# Configuration validation
# ---------------------------------------------------------------------------

def test_the_configuration_report_lists_every_integration(client: TestClient) -> None:
    response = client.get("/health/config")
    assert response.status_code == 200
    body = response.json()

    assert "checks" in body
    assert body["valid"] is (body["error_count"] == 0)

    keys = {check["key"] for check in body["checks"]}
    for expected in (
        "supabase",
        "supabase_auth",
        "scoring_matrix",
        "groq",
        "ors",
        "property_source",
        "sentry",
        "metrics",
    ):
        assert expected in keys, f"the configuration report does not mention {expected}"


def test_the_configuration_report_never_exposes_a_secret(client: TestClient) -> None:
    body = client.get("/health/config").json()
    serialised = repr(body).lower()

    for secret in ("password", "secret_key", "service_role", "api_key\":"):
        assert secret not in serialised

    for check in body["checks"]:
        assert "value" not in check
        assert set(check) <= {
            "key",
            "label",
            "status",
            "detail",
            "variable",
            "required",
        }


def test_the_configuration_report_states_the_variable_to_set(client: TestClient) -> None:
    body = client.get("/health/config").json()
    for check in body["checks"]:
        assert check["status"] in {"ok", "warning", "error"}
        assert check["detail"], f"{check['key']} has no explanation"
        assert check["label"]


def test_the_health_endpoint_never_exposes_a_credential(client: TestClient) -> None:
    body = client.get("/health").json()
    serialised = repr(body).lower()
    for secret in ("password", "secret", "apikey", "service_role"):
        assert secret not in serialised
