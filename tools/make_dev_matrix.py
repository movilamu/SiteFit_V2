"""Generate a local development matrix for visual verification.

This script is a **development tool**.  It produces a synthetic normalised
matrix so that the interface can be exercised without a populated database.
The output is written under ``data/`` which is git-ignored, and the file it
produces must never be used as a production artefact.

    python tools/make_dev_matrix.py

The generated values are random.  They carry no analytical meaning and are
not derived from any real site.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scoring.criteria_hierarchy import CRITERIA_TREE, iter_leaves  # noqa: E402

SITES = [
    ("site-001", "Anna Salai", 13.0698, 80.2870),
    ("site-002", "T. Nagar", 13.0418, 80.2340),
    ("site-003", "Velachery", 12.9756, 80.2210),
    ("site-004", "Adyar", 13.0067, 80.2570),
    ("site-005", "Porur", 13.0370, 80.1580),
    ("site-006", "Mylapore", 13.0333, 80.2686),
    ("site-007", "Nungambakkam", 13.0569, 80.2425),
    ("site-008", "Guindy", 13.0067, 80.2206),
    ("site-009", "Perungudi", 12.9698, 80.2430),
    ("site-010", "Chrompet", 12.9516, 80.1462),
    ("site-011", "K.K. Nagar", 13.0779, 80.2090),
    ("site-012", "Royapettah", 13.0339, 80.2773),
]

#: The criteria that have backing data in a realistic release.
SCORABLE = [
    "resident_density",
    "projected_growth",
    "household_formation_rate",
    "age_band_representation",
    "household_size_composition",
    "drive_time_reach",
    "competitor_density_in_catchment",
    "format_overlap",
    "distance_to_nearest_direct_competitor",
]


def main() -> int:
    rng = np.random.default_rng(20260119)

    leaves = [criterion.key for _, _, criterion in iter_leaves(CRITERIA_TREE)]
    unknown = [key for key in SCORABLE if key not in leaves]
    if unknown:
        print(f"Unknown criterion keys: {unknown}", file=sys.stderr)
        return 1

    data: dict[str, list[float]] = {}
    for key in SCORABLE:
        data[key] = np.round(rng.uniform(0.05, 0.95, size=len(SITES)), 6).tolist()

    frame = pd.DataFrame(data, index=[site for site, *_ in SITES])
    frame.index.name = "site_id"

    destination = ROOT / "data" / "dev"
    destination.mkdir(parents=True, exist_ok=True)
    output = destination / "normalized_matrix_dev.csv"
    frame.to_csv(output)

    print(f"Wrote {len(SITES)} development rows to {output}")
    print("This is synthetic development data and must not be used in production.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
