"""Tests for the cost model.

The cost model's contract is that every figure carries a provenance and
that an incomplete cost picture is never presented as a total.
"""

from __future__ import annotations

import pytest

from scoring.cost_model import (
    ESTIMATED,
    UNAVAILABLE,
    USER_PROVIDED,
    VERIFIED_LISTED,
    CostBudget,
    assess_site_costs,
    compare_budgets,
)


def test_a_listed_rent_is_reported_as_verified() -> None:
    assessment = assess_site_costs(
        site_id="site-1",
        attributes={"rent": 250_000},
        acquisition_mode="lease",
    )
    rent = next(line for line in assessment.lines if line.key == "rent_recurring")

    assert rent.amount == 250_000
    assert rent.provenance == VERIFIED_LISTED
    assert rent.source is not None


def test_a_user_supplied_value_is_reported_as_user_provided() -> None:
    assessment = assess_site_costs(
        site_id="site-1",
        attributes={},
        acquisition_mode="lease",
        financial={"monthly_rent": 180_000},
    )
    rent = next(line for line in assessment.lines if line.key == "rent_recurring")

    assert rent.amount == 180_000
    assert rent.provenance == USER_PROVIDED


def test_an_unknown_value_is_reported_as_unavailable_not_as_zero() -> None:
    assessment = assess_site_costs(
        site_id="site-1",
        attributes={},
        acquisition_mode="buy",
    )
    price = next(line for line in assessment.lines if line.key == "purchase_price")

    assert price.amount is None
    assert price.provenance == UNAVAILABLE


def test_an_incomplete_cost_picture_has_no_total() -> None:
    assessment = assess_site_costs(
        site_id="site-1",
        attributes={"purchase_price": 3_000_000},
        acquisition_mode="buy",
    )

    assert assessment.acquisition_total is None
    assert assessment.initial_investment_total is None
    # The known part is still reported, but only as a minimum.
    assert assessment.known_minimum_initial_investment > 0


def test_a_complete_cost_picture_produces_a_total() -> None:
    assessment = assess_site_costs(
        site_id="site-1",
        attributes={
            "purchase_price": 3_000_000,
            "brokerage": 60_000,
            "transaction_costs": 90_000,
            "other_acquisition": 0,
            "renovation": 400_000,
            "equipment": 200_000,
            "signage": 50_000,
            "parking_development": 0,
            "utility_setup": 100_000,
            "other_setup": 0,
            "maintenance": 10_000,
            "utilities": 20_000,
            "other_recurring": 0,
        },
        acquisition_mode="buy",
    )

    assert assessment.acquisition_total == pytest.approx(3_150_000)
    assert assessment.setup_total == pytest.approx(750_000)
    assert assessment.initial_investment_total == pytest.approx(3_900_000)
    assert assessment.recurring_monthly_total == pytest.approx(30_000)
    assert assessment.recurring_annual_total == pytest.approx(360_000)


def test_buy_and_lease_costs_are_not_mixed() -> None:
    assessment = assess_site_costs(
        site_id="site-1",
        attributes={"rent": 100_000, "purchase_price": 5_000_000},
        acquisition_mode="lease",
    )
    keys = {line.key for line in assessment.lines}
    assert "purchase_price" not in keys
    assert "rent_recurring" in keys


def test_either_mode_assesses_both() -> None:
    assessment = assess_site_costs(
        site_id="site-1",
        attributes={"rent": 100_000, "purchase_price": 5_000_000},
        acquisition_mode="either",
    )
    keys = {line.key for line in assessment.lines}
    assert "purchase_price" in keys
    assert "rent_recurring" in keys


# ---------------------------------------------------------------------------
# Budget comparison
# ---------------------------------------------------------------------------

def test_a_budget_within_the_limit_passes() -> None:
    assessment = assess_site_costs(
        site_id="site-1",
        attributes={"rent": 100_000},
        acquisition_mode="lease",
    )
    results = compare_budgets(
        assessment,
        [
            CostBudget(
                key="monthly_rent_budget",
                label="Monthly rent budget",
                limit=150_000,
                scope="rent",
            )
        ],
    )

    assert results[0]["status"] == "within_budget"
    assert results[0]["headroom"] == pytest.approx(50_000)


def test_a_budget_that_is_exceeded_fails() -> None:
    assessment = assess_site_costs(
        site_id="site-1",
        attributes={"rent": 200_000},
        acquisition_mode="lease",
    )
    results = compare_budgets(
        assessment,
        [
            CostBudget(
                key="monthly_rent_budget",
                label="Monthly rent budget",
                limit=150_000,
                scope="rent",
            )
        ],
    )

    assert results[0]["status"] == "over_budget"
    assert results[0]["headroom"] == pytest.approx(-50_000)


def test_a_breach_is_proven_from_the_known_components() -> None:
    """A budget can be shown to be exceeded even when other components are
    unknown, because the known components alone exceed the limit."""

    assessment = assess_site_costs(
        site_id="site-1",
        attributes={"purchase_price": 5_000_000},
        acquisition_mode="buy",
    )
    results = compare_budgets(
        assessment,
        [
            CostBudget(
                key="purchase_budget",
                label="Purchase budget",
                limit=1_000_000,
                scope="acquisition",
            )
        ],
    )

    assert results[0]["status"] == "over_budget"
    assert results[0]["known_minimum"] == pytest.approx(5_000_000)


def test_an_unassessable_budget_is_reported_as_partial_not_as_a_pass() -> None:
    assessment = assess_site_costs(
        site_id="site-1",
        attributes={},
        acquisition_mode="buy",
    )
    results = compare_budgets(
        assessment,
        [
            CostBudget(
                key="purchase_budget",
                label="Purchase budget",
                limit=1_000_000,
                scope="acquisition",
            )
        ],
    )

    assert results[0]["status"] == "partially_assessed"
    assert results[0]["observed"] is None


def test_a_budget_that_was_never_set_is_reported_as_not_set() -> None:
    assessment = assess_site_costs(site_id="site-1", attributes={})
    results = compare_budgets(
        assessment,
        [
            CostBudget(
                key="purchase_budget",
                label="Purchase budget",
                limit=None,
                scope="acquisition",
            )
        ],
    )

    assert results[0]["status"] == "not_set"


def test_the_serialised_assessment_names_the_missing_components() -> None:
    assessment = assess_site_costs(
        site_id="site-1",
        attributes={},
        acquisition_mode="buy",
    )
    payload = assessment.to_dict()

    assert payload["missing_components"]
    assert payload["totals"]["is_complete"] is False
