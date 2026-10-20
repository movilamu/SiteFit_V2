"""Tests for the requirement evaluation and the fit-factor penalty.

The requirement layer is the part of the platform that turns a user's
stated requirements into a filter, a penalty and a set of disclosed checks.
These tests lock in that behaviour, including the rule that missing data is
never treated as a failure.
"""

from __future__ import annotations

import pytest

from scoring.requirement_fit import (
    BEHAVIOUR_FLEXIBLE,
    BEHAVIOUR_HARD,
    BEHAVIOUR_PREFERENCE,
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_UNKNOWN,
    apply_fit_penalty,
    combine_fit_ratio,
    compute_fit_factor,
    evaluate_business_requirements,
    evaluate_facilities,
    evaluate_parking,
    evaluate_site_requirements,
)


# ---------------------------------------------------------------------------
# Parking
# ---------------------------------------------------------------------------

def test_parking_passes_when_the_target_is_met() -> None:
    result = evaluate_parking(
        {"car_spaces": 60},
        {"min_car_spaces": 50, "behaviour": "preference"},
    )
    assert result.required_met == 1
    assert result.required_failed == 0
    assert result.checks[0].status == STATUS_PASS


def test_parking_fails_when_the_target_is_not_met() -> None:
    result = evaluate_parking(
        {"car_spaces": 20},
        {"min_car_spaces": 50, "behaviour": "preference"},
    )
    assert result.required_failed == 1
    assert result.checks[0].status == STATUS_FAIL


def test_missing_parking_data_is_unknown_not_failed() -> None:
    result = evaluate_parking(
        {},
        {"min_car_spaces": 50, "behaviour": "preference"},
    )
    assert result.required_failed == 0
    assert result.required_unknown == 1
    assert result.checks[0].status == STATUS_UNKNOWN


def test_the_parking_behaviour_is_echoed_back() -> None:
    for behaviour in (BEHAVIOUR_HARD, BEHAVIOUR_PREFERENCE, BEHAVIOUR_FLEXIBLE):
        result = evaluate_parking({}, {"min_car_spaces": 1, "behaviour": behaviour})
        assert result.behaviour == behaviour


# ---------------------------------------------------------------------------
# Facilities
# ---------------------------------------------------------------------------

def test_a_present_facility_is_met() -> None:
    result = evaluate_facilities(
        {"kitchen": True},
        [{"key": "kitchen", "label": "Kitchen", "importance": "required"}],
    )
    assert result.required_met == 1
    assert result.checks[0].status == STATUS_PASS


def test_an_absent_facility_fails() -> None:
    result = evaluate_facilities(
        {"kitchen": False},
        [{"key": "kitchen", "label": "Kitchen", "importance": "required"}],
    )
    assert result.required_failed == 1


def test_an_unrecorded_facility_is_unknown() -> None:
    result = evaluate_facilities(
        {},
        [{"key": "kitchen", "label": "Kitchen", "importance": "required"}],
    )
    assert result.required_unknown == 1
    assert result.required_failed == 0


def test_not_important_facilities_are_not_assessed() -> None:
    result = evaluate_facilities(
        {},
        [{"key": "kitchen", "label": "Kitchen", "importance": "not_important"}],
    )
    assert result.checks == []
    assert result.required_total == 0


def test_a_numeric_facility_attribute_counts_as_present() -> None:
    result = evaluate_facilities(
        {"parking_capacity": 40},
        [
            {
                "key": "parking",
                "label": "Parking",
                "importance": "required",
                "site_attributes": ("parking", "parking_capacity", "has_parking"),
            }
        ],
    )
    assert result.required_met == 1


# ---------------------------------------------------------------------------
# Business requirements
# ---------------------------------------------------------------------------

def test_a_numeric_requirement_below_the_target_fails() -> None:
    result = evaluate_business_requirements(
        {"seating_capacity": 20},
        [
            {
                "key": "seating_capacity",
                "label": "Seating capacity",
                "importance": "required",
                "value": 40,
                "value_type": "number",
            }
        ],
    )
    assert result.required_failed == 1


def test_a_select_requirement_compares_by_value() -> None:
    result = evaluate_business_requirements(
        {"visibility": "high"},
        [
            {
                "key": "visibility",
                "label": "Visibility",
                "importance": "preferred",
                "value": "high",
                "value_type": "select",
            }
        ],
    )
    assert result.preferred_met == 1


def test_a_boolean_requirement_is_checked_for_truthiness() -> None:
    result = evaluate_business_requirements(
        {"kitchen": True},
        [
            {
                "key": "kitchen",
                "label": "Kitchen",
                "importance": "required",
                "value": True,
                "value_type": "boolean",
            }
        ],
    )
    assert result.required_met == 1


# ---------------------------------------------------------------------------
# Fit factor
# ---------------------------------------------------------------------------

def test_a_perfect_fit_produces_no_penalty() -> None:
    assert compute_fit_factor(1.0, 0.25, BEHAVIOUR_PREFERENCE) == pytest.approx(1.0)


def test_the_penalty_is_bounded_by_the_penalty_rate() -> None:
    factor = compute_fit_factor(0.0, 0.25, BEHAVIOUR_PREFERENCE)
    assert factor == pytest.approx(0.75)


def test_a_flexible_requirement_never_penalises() -> None:
    assert compute_fit_factor(0.0, 0.25, BEHAVIOUR_FLEXIBLE) == pytest.approx(1.0)


def test_the_penalty_scales_the_base_score() -> None:
    assert apply_fit_penalty(0.8, 0.75) == pytest.approx(0.6)


def test_combining_sections_weights_by_the_number_of_known_checks() -> None:
    class _Section:
        def __init__(self, fit_ratio, known):
            self.fit_ratio = fit_ratio
            self.known = known

        @property
        def required_total(self):
            return self.known

        @property
        def required_unknown(self):
            return 0

        @property
        def preferred_total(self):
            return 0

        @property
        def preferred_unknown(self):
            return 0

    combined = combine_fit_ratio([_Section(1.0, 1), _Section(0.0, 9)])
    assert combined == pytest.approx(0.1)


# ---------------------------------------------------------------------------
# Site-level evaluation
# ---------------------------------------------------------------------------

def test_a_hard_requirement_failure_excludes_the_site() -> None:
    evaluation = evaluate_site_requirements(
        site_id="site-1",
        attributes={"car_spaces": 10},
        requirements={
            "parking": {"min_car_spaces": 50, "behaviour": "hard"},
        },
    )

    assert evaluation.eligible is False
    assert len(evaluation.hard_failures) == 1


def test_a_preference_failure_keeps_the_site_and_reduces_its_score() -> None:
    evaluation = evaluate_site_requirements(
        site_id="site-1",
        attributes={"car_spaces": 10},
        requirements={
            "parking": {"min_car_spaces": 50, "behaviour": "preference"},
        },
    )

    assert evaluation.eligible is True
    assert evaluation.hard_failures == []
    assert evaluation.fit_factor < 1.0


def test_a_flexible_failure_keeps_the_score_untouched() -> None:
    evaluation = evaluate_site_requirements(
        site_id="site-1",
        attributes={"car_spaces": 10},
        requirements={
            "parking": {"min_car_spaces": 50, "behaviour": "flexible"},
        },
    )

    assert evaluation.eligible is True
    assert evaluation.fit_factor == pytest.approx(1.0)


def test_a_hard_budget_breach_excludes_the_site() -> None:
    evaluation = evaluate_site_requirements(
        site_id="site-1",
        attributes={"purchase_price": 5_000_000},
        requirements={
            "acquisition_mode": "buy",
            "financial": {
                "acquisition_mode": "buy",
                "budgets": [
                    {
                        "key": "purchase_budget",
                        "label": "Purchase budget",
                        "limit": 1_000_000,
                        "behaviour": "hard",
                        "scope": "acquisition",
                    }
                ],
            },
        },
    )

    assert evaluation.eligible is False
    assert evaluation.hard_failures


def test_a_penalised_budget_breach_keeps_the_site() -> None:
    evaluation = evaluate_site_requirements(
        site_id="site-1",
        attributes={"purchase_price": 5_000_000},
        requirements={
            "acquisition_mode": "buy",
            "financial": {
                "acquisition_mode": "buy",
                "budgets": [
                    {
                        "key": "purchase_budget",
                        "label": "Purchase budget",
                        "limit": 1_000_000,
                        "behaviour": "penalise",
                        "scope": "acquisition",
                    }
                ],
            },
        },
    )

    assert evaluation.eligible is True


def test_unknown_data_is_disclosed_in_the_notes() -> None:
    evaluation = evaluate_site_requirements(
        site_id="site-1",
        attributes={},
        requirements={
            "parking": {"min_car_spaces": 50, "behaviour": "preference"},
        },
    )

    assert any("unavailable" in note.lower() for note in evaluation.notes)
