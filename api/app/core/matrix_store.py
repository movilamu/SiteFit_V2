"""Loading and caching of the precomputed normalised decision matrix.

The scoring engine works on a *precomputed* matrix (one row per candidate
site, one column per criterion leaf, values in [0, 1]).  Producing it is an
offline batch job; this module is the single read path for the API.

Resolution order
----------------
1. An in-process matrix assigned to :data:`IN_MEMORY_MATRIX` (used by
   tests and by a deployment that loads the matrix at start-up).
2. A file referenced by ``NORMALIZED_MATRIX_FILE`` (CSV, Parquet or JSON).
3. The latest published matrix in Supabase Storage, discovered through the
   ``normalized_matrix_versions`` table.

Every path produces a frame whose index is the site identifier, so
``scoring.score.rank_sites`` reports meaningful site identifiers rather
than positional integers.
"""

from __future__ import annotations

import io
import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from app.core.config import get_settings

logger = logging.getLogger(__name__)

#: Optional in-process matrix.  Assigned by tests or by a start-up hook.
IN_MEMORY_MATRIX: Optional[pd.DataFrame] = None

_CACHE_LOCK = threading.Lock()
_CACHED_MATRIX: Optional[pd.DataFrame] = None
_CACHE_KEY: Optional[str] = None


class MatrixUnavailableError(RuntimeError):
    """Raised when no normalised matrix can be loaded."""


def set_in_memory_matrix(matrix: Optional[pd.DataFrame]) -> None:
    """Inject a matrix for the lifetime of the process (tests / start-up)."""

    global IN_MEMORY_MATRIX, _CACHED_MATRIX, _CACHE_KEY
    with _CACHE_LOCK:
        IN_MEMORY_MATRIX = matrix
        _CACHED_MATRIX = None
        _CACHE_KEY = None


def _normalise_index(matrix: pd.DataFrame) -> pd.DataFrame:
    """Ensure the frame is indexed by site identifier.

    Persisted matrices are written with the site identifier as the index.
    When such a frame is read back from CSV the index becomes an
    ``Unnamed: 0`` column, so it is restored here.
    """

    if "site_id" in matrix.columns:
        return matrix.set_index("site_id")

    unnamed = [column for column in matrix.columns if str(column).startswith("Unnamed: 0")]
    if unnamed:
        column = unnamed[0]
        values = matrix[column].astype(str)
        # A numeric index means the file was written without a meaningful
        # identifier; in that case the positional index is kept.
        if not values.str.fullmatch(r"\d+").all() or len(set(values)) != len(values):
            matrix = matrix.drop(columns=[column])
            matrix.index = pd.Index(values, name="site_id")
    return matrix


def _read_matrix_file(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        frame = pd.read_csv(path)
    elif suffix in {".parquet", ".pq"}:
        frame = pd.read_parquet(path)
    elif suffix == ".json":
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        frame = pd.DataFrame(payload)
    else:
        raise MatrixUnavailableError(
            f"Unsupported matrix file format {suffix!r}. Use CSV, Parquet or JSON."
        )
    return _normalise_index(frame)


def _load_from_supabase() -> Optional[pd.DataFrame]:
    """Download the most recent published matrix from Supabase Storage."""

    settings = get_settings()
    if not settings.has_supabase:
        return None

    try:
        from app.core.supabase_client import rest_get
    except Exception:  # pragma: no cover - defensive
        return None

    rows = rest_get(
        settings.matrix_versions_table,
        params={
            "select": "version_id,storage_path,data_release_at",
            "order": "data_release_at.desc",
            "limit": 1,
        },
    )
    if not rows or not isinstance(rows, list):
        return None

    row = rows[0]
    storage_path = row.get("storage_path")
    if not storage_path:
        return None

    bucket = os.getenv("SCORING_MATRIX_STORAGE_BUCKET", "scoring-matrices")
    url = f"{settings.supabase_url}/storage/v1/object/{bucket}/{storage_path}"

    try:
        import requests

        response = requests.get(
            url,
            headers={
                "apikey": settings.supabase_service_key or "",
                "Authorization": f"Bearer {settings.supabase_service_key or ''}",
            },
            timeout=60.0,
        )
        if response.status_code != 200:
            logger.warning(
                "Could not download the scoring matrix (%s HTTP %s).",
                storage_path,
                response.status_code,
            )
            return None

        buffer = io.BytesIO(response.content)
        if storage_path.endswith(".csv"):
            frame = pd.read_csv(buffer)
        else:
            frame = pd.read_parquet(buffer)
    except Exception as exc:
        logger.warning("Could not download the scoring matrix: %s", exc)
        return None

    logger.info("Loaded scoring matrix version %s.", row.get("version_id"))
    return _normalise_index(frame)


def load_normalized_matrix(use_cache: bool = True) -> pd.DataFrame:
    """Return the normalised decision matrix.

    Raises:
        MatrixUnavailableError: when no matrix can be resolved.  Callers
            translate this into a 503 with an actionable message.
    """

    global _CACHED_MATRIX, _CACHE_KEY

    settings = get_settings()

    if IN_MEMORY_MATRIX is not None:
        matrix = IN_MEMORY_MATRIX.copy()
        if "site_id" in matrix.columns:
            matrix = matrix.set_index("site_id")
        return matrix

    configured_path = settings.normalized_matrix_file
    cache_key = configured_path or f"supabase:{settings.matrix_versions_table}"

    if use_cache:
        with _CACHE_LOCK:
            if _CACHED_MATRIX is not None and _CACHE_KEY == cache_key:
                return _CACHED_MATRIX.copy()

    matrix: Optional[pd.DataFrame] = None

    if configured_path:
        path = Path(configured_path)
        if not path.exists():
            raise MatrixUnavailableError(
                f"The configured normalised matrix file does not exist: {path}"
            )
        matrix = _read_matrix_file(path)
    else:
        matrix = _load_from_supabase()
        if matrix is None:
            raise MatrixUnavailableError(
                "No normalised scoring matrix is available. Set "
                "NORMALIZED_MATRIX_FILE, publish a matrix to Supabase Storage, "
                "or inject one with set_in_memory_matrix(). Run the "
                "precompute job to produce it."
            )

    if matrix.empty:
        raise MatrixUnavailableError("The normalised scoring matrix contains no site rows.")

    if use_cache:
        with _CACHE_LOCK:
            _CACHED_MATRIX = matrix.copy()
            _CACHE_KEY = cache_key

    return matrix


def matrix_summary() -> dict[str, Any]:
    """Return a small, non-sensitive description of the loaded matrix."""

    try:
        matrix = load_normalized_matrix()
    except MatrixUnavailableError as exc:
        return {"available": False, "detail": str(exc)}

    return {
        "available": True,
        "site_count": int(matrix.shape[0]),
        "criterion_count": int(matrix.shape[1]),
        "criteria": [str(column) for column in matrix.columns],
        "index_name": matrix.index.name,
    }


__all__ = [
    "IN_MEMORY_MATRIX",
    "MatrixUnavailableError",
    "load_normalized_matrix",
    "matrix_summary",
    "set_in_memory_matrix",
]

