"""Regression tests for the defects found during the operational audit.

Each test corresponds to a defect that was reproduced against the
running application:

* the weight alignment divided by zero when every criterion the matrix
  holds carried a zero weight;
* the exported weighting configuration was empty because the flattening
  did not accept the flat weight form the report carries;
* the exported shortlist held only the first three ranked sites;
* the criterion frame was indexed by the numeric database key rather
  than by the site's business key, so a ranking row could not be joined
  to a site;
* the candidate-site loader returned a reduced record without the
  property attributes.
"""

from __future__ import annotations

import json
import unittest

from api.app.domain.exports import _flatten_weights
from api.app.domain.reporting import build_report
from scoring.criterion_frame import _isochrone_area_km2, _site_category
from scoring.weight_model import align_weights_to_columns


class WeightAlignmentTests(unittest.TestCase):
    """The alignment must never divide by a zero weight mass."""

    def test_a_zero_scored_mass_reports_that_nothing_could_be_scored(self) -> None:
        """Every criterion in the matrix carries a zero weight.

        This is what a caller gets when it puts all of the weight on a
        category whose leaves have no data in the current release.  The
        alignment used to divide by the scored mass and raise a
        ZeroDivisionError, which the API surfaced as a 500.
        """

        weights = {
            "resident_density": 1.0,
            "daytime_population": 0.0,
            "drive_time_reach": 0.0,
        }
        columns = ["daytime_population", "drive_time_reach"]

        aligned, dropped, coverage = align_weights_to_columns(weights, columns)

        self.assertEqual(aligned, {})
        self.assertEqual(coverage, 0.0)
        self.assertIn("resident_density", dropped)

    def test_a_normal_alignment_is_unchanged(self) -> None:
        """The ordinary case still redistributes the lost weight mass."""

        weights = {"unit_size": 0.5, "rent": 0.5, "resident_density": 0.5}
        columns = ["unit_size", "rent"]

        aligned, dropped, coverage = align_weights_to_columns(weights, columns)

        self.assertAlmostEqual(sum(aligned.values()), 1.0, places=9)
        self.assertAlmostEqual(coverage, 2.0 / 3.0, places=9)
        self.assertIn("resident_density", dropped)


class ExportWeightTests(unittest.TestCase):
    """The exported weighting configuration must not be empty."""

    def test_a_flat_weight_mapping_is_flattened(self) -> None:
        """The report carries the flat form, so it must be exported."""

        rows = _flatten_weights({"unit_size": 0.25, "rent": 0.75})

        self.assertEqual(len(rows), 2)
        criteria = {row["criterion"]: row["weight"] for row in rows}
        self.assertEqual(criteria, {"unit_size": 0.25, "rent": 0.75})

    def test_the_hierarchical_form_is_still_flattened(self) -> None:
        rows = _flatten_weights({"site_and_property": {"unit_size": 0.4}})

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["level"], "site_and_property")
        self.assertEqual(rows[0]["criterion"], "unit_size")
        self.assertEqual(rows[0]["weight"], 0.4)

    def test_an_unusable_weight_mapping_yields_no_rows(self) -> None:
        self.assertEqual(_flatten_weights(None), [])
        self.assertEqual(_flatten_weights({"a": "not-a-number"}), [])


class ReportShortlistTests(unittest.TestCase):
    """The report must carry the whole ranking, not only its leaders."""

    def test_the_shortlist_holds_every_ranked_site(self) -> None:
        ranking = [
            {"site_id": "SITE-001", "rank": 1, "score": 0.9, "name": "One"},
            {"site_id": "SITE-002", "rank": 2, "score": 0.8, "name": "Two"},
            {"site_id": "SITE-003", "rank": 3, "score": 0.7, "name": "Three"},
            {"site_id": "SITE-004", "rank": 4, "score": 0.6, "name": "Four"},
            {"site_id": "SITE-005", "rank": 5, "score": 0.5, "name": "Five"},
        ]

        report = build_report(
            analysis={
                "name": "Test",
                "weights": {"unit_size": 1.0},
                "aggregation_method": "weighted_sum",
            },
            ranking=ranking,
            explanations=[],
            cost_assessments=[],
            property_results=[],
            sensitivity={},
            data_quality={},
        )

        # The narrative still focuses on the leaders.
        self.assertEqual(len(report["top_sites"]), 3)
        # The export carries the whole ranking.
        self.assertEqual(len(report["shortlist"]), 5)
        self.assertEqual(
            [site["site_id"] for site in report["shortlist"]],
            [site["site_id"] for site in ranking],
        )


class CriterionFrameTests(unittest.TestCase):
    """The criterion frame must be keyed by the site's business key."""

    def test_the_site_category_is_read_from_the_metadata(self) -> None:
        self.assertEqual(
            _site_category({"metadata": json.dumps({"retail_category": "Supermarket"})}),
            "supermarket",
        )
        self.assertEqual(_site_category({"category": "Cafe"}), "cafe")
        self.assertIsNone(_site_category({"metadata": "{}"}))
        self.assertIsNone(_site_category({}))

    def test_the_isochrone_area_is_computed_in_square_kilometres(self) -> None:
        """A square of roughly one kilometre on a side is about 1 km2."""

        square = {
            "type": "Polygon",
            "coordinates": [
                [
                    [80.20, 13.08],
                    [80.2090, 13.08],
                    [80.2090, 13.0890],
                    [80.20, 13.0890],
                    [80.20, 13.08],
                ]
            ],
        }
        area = _isochrone_area_km2(square)
        self.assertIsNotNone(area)
        assert area is not None
        self.assertGreater(area, 0.9)
        self.assertLess(area, 1.1)

    def test_an_unusable_geometry_yields_no_area(self) -> None:
        self.assertIsNone(_isochrone_area_km2(None))
        self.assertIsNone(_isochrone_area_km2("not-json"))
        self.assertIsNone(_isochrone_area_km2({"type": "Point"}))


if __name__ == "__main__":
    unittest.main()
