"""Run the API locally with the development matrix and a matching inventory.

This is a **development tool**.  It lets the interface be exercised without
a populated database by loading the development matrix from ``data/dev``
and registering a matching candidate-site inventory.

    python tools/dev_server.py --port 8000

The data it loads is synthetic and must never be used as a production
artefact.  When Supabase is configured the real inventory is used instead
and this script adds nothing to it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

#: The candidate sites that correspond to the development matrix.
DEV_SITES = [
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


def build_sites_frame() -> pd.DataFrame:
    """Return a candidate-site inventory that matches the development matrix."""

    records = []
    for index, (site_id, name, lat, lon) in enumerate(DEV_SITES):
        records.append(
            {
                "site_id": site_id,
                "name": name,
                "latitude": lat,
                "longitude": lon,
                "unit_size": 1200 + index * 180,
                "rent": 120_000 + index * 9_000,
                "tenure": "lease" if index % 3 else "freehold",
                "status": "active",
                "attractiveness": round(0.9 - index * 0.04, 3),
                "city": "Chennai",
                "locality": name,
                "car_spaces": 20 + index * 4,
                "two_wheeler_spaces": 30 + index * 5,
                "parking_area_sqft": 1500 + index * 200,
                "kitchen": index % 4 != 0,
                "washrooms": True,
                "power_supply": True,
                "water_supply": True,
                "fire_safety": True,
                "signage": index % 3 == 0,
                "parking": True,
                "loading_unloading": index % 2 == 0,
                "seating_capacity": 40 + index * 6,
            }
        )
    return pd.DataFrame(records)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the API with development data.")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    matrix_path = ROOT / "data" / "dev" / "normalized_matrix_dev.csv"
    if not matrix_path.exists():
        print(
            "The development matrix is missing. Run "
            "'python tools/make_dev_matrix.py' first.",
            file=sys.stderr,
        )
        return 1

    matrix = pd.read_csv(matrix_path, index_col=0)

    import uvicorn

    from api.app.core.matrix_store import set_in_memory_matrix
    from api.app.main import app

    set_in_memory_matrix(matrix)
    app.state.sites_df = build_sites_frame()

    print(f"Loaded {len(matrix)} development sites from {matrix_path}")
    print("This is synthetic development data; it is not a production artefact.")

    uvicorn.run(
        "api.app.main:app",
        host="127.0.0.1",
        port=args.port,
        reload=args.reload,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
