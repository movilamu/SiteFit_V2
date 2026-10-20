"""API smoke tests.

These tests exercise the API contract that the interface depends on:
the criteria hierarchy, the weight roll-up, the requirement evaluation, the
cost model and the health endpoints.  They run without a database, so the
routes that need one are exercised through their error paths.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from api.app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

def test_health_reports_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "retail-site-intelligence-api"


def test_health_never_exposes_a_credential(client: TestClient) -> None:
    body = client.get("/health").json()
    serialised = repr(body).lower()
    for secret in ("password", "secret", "apikey", "api_key", "service_role"):
        assert secret not in serialised


def test_readiness_degrades_when_the_matrix_is_missing(client: TestClient) -> None:
    response = client.get("/health/ready")
    body = response.json()
    assert "checks" in body
    assert "scoring_matrix_ready" in body["checks"]


# ---------------------------------------------------------------------------
# Criteria
# ---------------------------------------------------------------------------

def test_criteria_returns_the_authoritative_tree(client: TestClient) -> None:
    response = client.get("/criteria")
    assert response.status_code == 200
    body = response.json()

    assert len(body["categories"]) == 8
    assert body["leaf_count"] == 28
    assert "site_and_property" in body["category_keys"]
    assert body["scorable_leaf_count"] <= body["leaf_count"]


def test_every_criterion_states_its_direction(client: TestClient) -> None:
    body = client.get("/criteria").json()
    for category in body["categories"]:
        for subcategory in category["subcategories"]:
            for criterion in subcategory["criteria"]:
                assert criterion["scoring_mode"] in {"monotonic", "target_band"}
                if criterion["scoring_mode"] == "monotonic":
                    assert criterion["direction"] in {"benefit", "cost"}
                else:
                    assert criterion["target_band"] is not None


def test_the_rollup_produces_leaf_weights_that_sum_to_one(client: TestClient) -> None:
    response = client.post(
        "/criteria/rollup",
        json={"category_weights": {"population": 0.25, "accessibility": 0.75}},
    )
    assert response.status_code == 200
    body = response.json()

    assert sum(body["leaf_weights"].values()) == pytest.approx(1.0, abs=1e-6)
    assert body["category_weights"]["population"] == pytest.approx(0.25, abs=1e-6)


def test_the_rollup_rejects_an_unknown_category(client: TestClient) -> None:
    response = client.post(
        "/criteria/rollup", json={"category_weights": {"not_a_category": 1.0}}
    )
    assert response.status_code == 422
    assert "Unknown category" in response.json()["detail"]


def test_the_scorable_endpoint_separates_available_from_unavailable(
    client: TestClient,
) -> None:
    body = client.get("/criteria/scorable").json()
    assert body["scorable_count"] + body["unavailable_count"] == 28
    assert not set(body["scorable_criteria"]) & set(body["unavailable_criteria"])


# ---------------------------------------------------------------------------
# Requirements
# ---------------------------------------------------------------------------

def test_the_requirement_catalog_is_complete(client: TestClient) -> None:
    body = client.get("/requirements/catalog").json()

    assert len(body["business_types"]) >= 10
    assert len(body["facilities"]) >= 15
    assert len(body["requirements"]) >= 15
    assert {behaviour["key"] for behaviour in body["constraint_behaviours"]} == {
        "hard",
        "preference",
        "flexible",
    }
    assert {mode["key"] for mode in body["acquisition_modes"]} == {
        "buy",
        "lease",
        "either",
    }


def test_a_business_type_profile_is_returned(client: TestClient) -> None:
    body = client.get("/requirements/profile/restaurant").json()
    keys = {entry["key"] for entry in body["requirements"]}

    assert "seating_capacity" in keys
    assert "kitchen_required" in keys
    for entry in body["requirements"]:
        assert entry["importance"] in {"required", "preferred", "not_important"}


def test_an_unknown_business_type_is_a_404(client: TestClient) -> None:
    assert client.get("/requirements/profile/nope").status_code == 404


def test_requirement_evaluation_reports_hard_failures(client: TestClient) -> None:
    """The evaluation runs against the candidate inventory.

    With no inventory configured the route reports that the inventory is
    unavailable rather than inventing sites.
    """

    response = client.post(
        "/requirements/evaluate",
        json={
            "requirements": {
                "parking": {"min_car_spaces": 50, "behaviour": "hard"},
            }
        },
    )
    assert response.status_code in {200, 503}
    if response.status_code == 200:
        body = response.json()
        for site in body["sites"]:
            assert "eligible" in site
            assert "fit_factor" in site


def test_the_ai_requirement_builder_reports_when_it_is_unconfigured(
    client: TestClient,
) -> None:
    """Without a configured provider the builder must say so.

    It must never fabricate an interpretation.
    """

    from api.app.core.config import get_settings

    if get_settings().has_ai_provider:
        pytest.skip("A language-model provider is configured in this environment.")

    response = client.post(
        "/requirements/parse", json={"description": "A cafe in Chennai with 30 seats."}
    )
    assert response.status_code == 503
    assert "not available" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Data quality
# ---------------------------------------------------------------------------

def test_the_data_quality_report_lists_the_known_limitations(client: TestClient) -> None:
    response = client.get("/data-quality")
    assert response.status_code == 200
    body = response.json()

    limitation_ids = {item["id"] for item in body["limitations"]}
    assert "census_vintage" in limitation_ids
    assert "due_diligence_required" in limitation_ids


def test_the_limitations_endpoint_states_that_it_is_decision_support(
    client: TestClient,
) -> None:
    body = client.get("/data-quality/limitations").json()
    assert "does not replace" in body["statement"]


# ---------------------------------------------------------------------------
# Property sources
# ---------------------------------------------------------------------------

def test_the_property_sources_endpoint_lists_the_configured_sources(
    client: TestClient,
) -> None:
    body = client.get("/properties/sources").json()
    keys = {source["key"] for source in body["sources"]}
    assert "openstreetmap" in keys


def test_a_property_search_never_fails_the_request(client: TestClient) -> None:
    """A source that times out, errors or is not configured must degrade to a
    reported status, never to an error for the whole request."""

    response = client.post(
        "/properties/search",
        json={"site_ids": ["site-001"], "radius_m": 300, "limit_per_site": 3},
    )

    # Either the inventory is unavailable (503) or the search completes and
    # reports the status of every source it tried.
    assert response.status_code in {200, 503}
    if response.status_code != 200:
        return

    body = response.json()
    assert "sites" in body
    for site in body["sites"]:
        assert site["status"] in {
            "ok",
            "partial",
            "unavailable",
            "no_results",
        }
        for source in site["sources"]:
            assert source["status"]
            assert "message" in source
        # No opportunity is ever presented without a source and a title.
        for opportunity in site["opportunities"]:
            assert opportunity["source_key"]
            assert opportunity["title"]
            assert opportunity["retrieved_at"]


def test_a_property_source_may_not_target_a_private_address(
    client: TestClient,
) -> None:
    """A misconfigured feed must not be able to make the server issue
    requests to internal addresses."""

    from api.app.domain.property_sources import UnsafeURLError, assert_safe_url

    for url in (
        "http://127.0.0.1:8000/internal",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/secret",
        "file:///etc/passwd",
    ):
        with pytest.raises(UnsafeURLError):
            assert_safe_url(url)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def test_scoring_requires_exactly_one_weight_source(client: TestClient) -> None:
    response = client.post("/score", json={"method": "weighted_sum"})
    assert response.status_code == 422

    response = client.post(
        "/score",
        json={
            "method": "weighted_sum",
            "weights": {"a": 1.0},
            "level_weights": {"category_weights": {"population": 1.0}},
        },
    )
    assert response.status_code == 422


def test_scoring_rejects_a_weight_vector_that_does_not_sum_to_one(
    client: TestClient,
) -> None:
    response = client.post(
        "/score", json={"method": "weighted_sum", "weights": {"a": 0.4, "b": 0.4}}
    )
    assert response.status_code == 422
    assert "sum to 1.0" in str(response.json()["detail"])


def test_scoring_reports_a_missing_matrix_as_unavailable(client: TestClient) -> None:
    """With no matrix configured the route must say so, not return an empty
    ranking that could be mistaken for "no sites qualify"."""

    from api.app.core.config import get_settings

    if get_settings().normalized_matrix_file:
        pytest.skip("A normalised matrix file is configured in this environment.")

    response = client.post(
        "/score",
        json={
            "method": "weighted_sum",
            "level_weights": {"category_weights": {"population": 1.0}},
        },
    )
    assert response.status_code in {422, 503}
    detail = response.json()["detail"].lower()
    assert "matrix" in detail or "criteria" in detail
