"""Regression tests for the project-children loader.

The list endpoint loads the requirement rows of every project in four
queries rather than four queries per project.  The batched loader
returned the raw database rows under different keys, so the project
payload lost every requirement: an analysis was reported with no
requirements, no facilities, no parking and no budgets.

These tests pin the shape of the batched loader to the shape of the
single-project loader, and they check that the payload carries the
requirements through.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.app.routers.projects import (  # noqa: E402
    _business_requirement_payload,
    _empty_children,
    _facility_requirement_payload,
    _financial_payload,
    _load_children_batch,
    _parking_payload,
    _project_row_to_payload,
)

BUSINESS_ROW: Dict[str, Any] = {
    "id": 1,
    "project_id": "11111111-1111-1111-1111-111111111111",
    "requirement_key": "storage_area_sqft",
    "label": "Storage area",
    "importance": "required",
    "value": 500,
    "value_text": None,
    "value_type": "number",
    "unit": "sq ft",
    "minimum": 0,
    "maximum": None,
    "options": [],
    "help_text": "",
}

FACILITY_ROW: Dict[str, Any] = {
    "id": 1,
    "project_id": "11111111-1111-1111-1111-111111111111",
    "facility_key": "parking",
    "label": "Parking",
    "importance": "required",
}

PARKING_ROW: Dict[str, Any] = {
    "id": 1,
    "project_id": "11111111-1111-1111-1111-111111111111",
    "min_car_spaces": 20,
    "min_two_wheeler_spaces": None,
    "min_parking_area_sqft": None,
    "behaviour": "preference",
    "scope": "site",
}

FINANCIAL_ROW: Dict[str, Any] = {
    "id": 1,
    "project_id": "11111111-1111-1111-1111-111111111111",
    "budgets": [
        {
            "key": "monthly_rent_budget",
            "label": "Monthly rent budget",
            "limit": 200000,
            "scope": "rent",
            "behaviour": "penalise",
            "appliesTo": ["lease", "either"],
        }
    ],
    "budget_behaviour": "penalise",
    "horizon_months": 60,
    "purchase_budget": None,
    "monthly_rent_budget": 200000,
}


class _FakeQuery:
    """A minimal stand-in for the supabase query builder."""

    def __init__(self, rows: List[Dict[str, Any]]) -> None:
        self._rows = rows

    def select(self, *_args: Any) -> "_FakeQuery":
        return self

    def in_(self, _column: str, _values: Any) -> "_FakeQuery":
        return self

    def limit(self, _count: int) -> "_FakeQuery":
        return self

    def execute(self) -> "_FakeResponse":
        return _FakeResponse(self._rows)


class _FakeResponse:
    def __init__(self, rows: List[Dict[str, Any]]) -> None:
        self.data = rows


class _FakeTable:
    def __init__(self, rows: List[Dict[str, Any]]) -> None:
        self._rows = rows

    def select(self, *_args: Any) -> _FakeQuery:
        return _FakeQuery(self._rows)


class _FakeClient:
    """A client that returns the rows it was given for each table."""

    def __init__(self, rows: Dict[str, List[Dict[str, Any]]]) -> None:
        self._rows = rows

    def table(self, name: str) -> _FakeTable:
        return _FakeTable(self._rows.get(name, []))


def test_the_batched_loader_returns_the_same_shape_as_the_single_loader() -> None:
    """The batched loader must produce the payload shape, not raw rows."""

    project_id = "11111111-1111-1111-1111-111111111111"
    client = _FakeClient(
        {
            "project_business_requirements": [BUSINESS_ROW],
            "project_facility_requirements": [FACILITY_ROW],
            "project_parking_requirements": [PARKING_ROW],
            "project_financial_requirements": [FINANCIAL_ROW],
        }
    )

    batched = _load_children_batch(client, [project_id])

    assert project_id in batched
    children = batched[project_id]
    assert set(children) == set(_empty_children())
    assert children["business_requirements"] == [
        _business_requirement_payload(BUSINESS_ROW)
    ]
    assert children["facility_requirements"] == [
        _facility_requirement_payload(FACILITY_ROW)
    ]
    assert children["parking"] == _parking_payload(PARKING_ROW)
    assert children["financial"] == _financial_payload(FINANCIAL_ROW)


def test_the_project_payload_carries_the_requirements() -> None:
    """The payload must not lose the requirements on the way out."""

    project_id = "11111111-1111-1111-1111-111111111111"
    client = _FakeClient(
        {
            "project_business_requirements": [BUSINESS_ROW],
            "project_facility_requirements": [FACILITY_ROW],
            "project_parking_requirements": [PARKING_ROW],
            "project_financial_requirements": [FINANCIAL_ROW],
        }
    )

    children = _load_children_batch(client, [project_id])[project_id]
    row = {
        "id": project_id,
        "name": "Test analysis",
        "business_type": "supermarket",
        "acquisition_mode": "either",
        "location": {"city": "Chennai"},
        "weights": {"unit_size": 1.0},
        "aggregation_method": "weighted_sum",
        "criteria_coverage": {},
        "notes": "",
        "confirmed_at": "2026-01-01T00:00:00+00:00",
    }

    payload = _project_row_to_payload(row, children)

    assert payload.name == "Test analysis"
    assert payload.confirmed is True
    assert len(payload.requirements) == 1
    assert payload.requirements[0]["key"] == "storage_area_sqft"
    assert payload.requirements[0]["value"] == 500
    assert len(payload.facilities) == 1
    assert payload.parking["minCarSpaces"] == 20
    assert len(payload.financial["budgets"]) == 1
    assert payload.financial["horizonMonths"] == 60


def test_a_financial_row_without_a_budget_list_falls_back_to_the_columns() -> None:
    """The individual limit columns are used when the list is empty."""

    row = dict(FINANCIAL_ROW)
    row["budgets"] = []

    payload = _financial_payload(row)

    assert [budget["key"] for budget in payload["budgets"]] == [
        "monthly_rent_budget"
    ]
    assert payload["budgets"][0]["limit"] == 200000


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__]))
