"""Tests for the demographic crosswalk.

The crosswalk is the point where the Census of India 2011 is joined onto
the canonical H3 grid.  These tests cover the three cases that matter:

* a direct 1:1 match,
* a Census unit that spans several cells (areal interpolation), and
* a record that cannot be allocated at all.

They also lock in the rule that the allocated shares sum to one, so no
population is created or lost by the allocation.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ingestion.demographic_etl import (  # noqa: E402
    allocate_record_to_analysis_units,
    map_record_to_analysis_unit,
)

shapely = pytest.importorskip("shapely")
from shapely.geometry import Polygon  # noqa: E402


def _record(raw_id: str = "ward-1", population: float = 1000.0) -> dict:
    return {
        "raw_geo_id": raw_id,
        "population": population,
        "household_count": 200.0,
        "literacy_rate": 82.5,
        "workforce_participation": 47.0,
        "age_bands": {"0_6": 100.0, "7_plus": 900.0},
    }


# ---------------------------------------------------------------------------
# Direct matching
# ---------------------------------------------------------------------------

def test_a_direct_id_match_is_used_as_is() -> None:
    unit_id, confidence = map_record_to_analysis_unit(
        _record("ward-1"), {"ward-1": "cell-a"}
    )
    assert unit_id == "cell-a"
    assert confidence == pytest.approx(1.0)


def test_a_h3_index_is_accepted_directly() -> None:
    h3_index = "8f2a1b2c3d4e5f6"
    assert len(h3_index) == 15
    unit_id, confidence = map_record_to_analysis_unit(_record(h3_index), {})
    assert unit_id == h3_index
    assert confidence == pytest.approx(1.0)


def test_an_unmatched_record_without_geometry_is_not_allocated() -> None:
    allocations = allocate_record_to_analysis_units(_record("ward-1"), {}, None, None)
    assert allocations == []


# ---------------------------------------------------------------------------
# Areal interpolation
# ---------------------------------------------------------------------------

def test_a_ward_spanning_two_cells_is_allocated_across_both() -> None:
    source = Polygon([(0, 0), (2, 0), (2, 1), (0, 1)])
    left = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    right = Polygon([(1, 0), (2, 0), (2, 1), (1, 1)])

    allocations = allocate_record_to_analysis_units(
        _record("ward-1", 1000.0),
        {},
        {"ward-1": source},
        {"cell-left": left, "cell-right": right},
    )

    assert len(allocations) == 2
    unit_ids = {unit_id for unit_id, _, _ in allocations}
    assert unit_ids == {"cell-left", "cell-right"}

    # The shares account for the whole ward.
    assert sum(share for _, share, _ in allocations) == pytest.approx(1.0)

    # Each cell receives half of the population.
    for _, share, _ in allocations:
        assert share == pytest.approx(0.5)

    # The confidence is lower than a direct match.
    for _, _, confidence in allocations:
        assert 0.0 < confidence < 1.0


def test_an_allocation_only_covers_the_cells_that_overlap() -> None:
    source = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    overlapping = Polygon([(0.25, 0.25), (0.75, 0.25), (0.75, 0.75), (0.25, 0.75)])
    distant = Polygon([(5, 5), (6, 5), (6, 6), (5, 6)])

    allocations = allocate_record_to_analysis_units(
        _record("ward-1", 500.0),
        {},
        {"ward-1": source},
        {"cell-near": overlapping, "cell-far": distant},
    )

    assert [unit_id for unit_id, _, _ in allocations] == ["cell-near"]
    assert allocations[0][1] == pytest.approx(1.0)


def test_a_record_with_no_overlap_is_not_allocated() -> None:
    source = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    distant = Polygon([(5, 5), (6, 5), (6, 6), (5, 6)])

    allocations = allocate_record_to_analysis_units(
        _record("ward-1", 500.0),
        {},
        {"ward-1": source},
        {"cell-far": distant},
    )

    assert allocations == []


def test_a_direct_match_takes_priority_over_the_interpolation() -> None:
    source = Polygon([(0, 0), (2, 0), (2, 1), (0, 1)])
    left = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])

    allocations = allocate_record_to_analysis_units(
        _record("ward-1", 1000.0),
        {"ward-1": "cell-direct"},
        {"ward-1": source},
        {"cell-left": left},
    )

    assert allocations == [("cell-direct", 1.0, pytest.approx(1.0))]
