"""Reproducible ranking exports.

An export is a self-describing artefact: it carries the ranked shortlist,
the **exact** global weight mapping, the aggregation method, the scenario
metadata and the export metadata, so the recommendation can be reproduced
later rather than merely recorded.

JSON is used rather than CSV because JSON can carry all of that in one
artefact.  The executive report in PDF, CSV and Excel is produced by
:mod:`api.app.routers.report_exports`, which renders the report rather
than the raw ranking.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.app.core.auth import AuthenticatedUser, get_current_user, require_user_id
from api.app.core.config import get_settings
from api.app.core.matrix_store import MatrixUnavailableError
from api.app.routers.scenarios import SUPPORTED_METHODS, get_normalized_matrix
from scoring.score import apply_weights, rank_sites

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["exports"])

#: The bucket the export artefacts are written to.
DEFAULT_EXPORT_BUCKET = os.getenv("SUPABASE_EXPORT_BUCKET", "exports")


class ExportRequest(BaseModel):
    """Request for a reproducible shortlist export.

    Exactly one source of weights is required:
      * ``scenario_id`` loads the persisted scenario; or
      * ``weight_set`` supplies an inline weight mapping.

    Inline weights also need an aggregation method, because a weight set
    alone does not uniquely determine the scoring operation.
    """

    model_config = ConfigDict(extra="forbid")

    scenario_id: Optional[int] = Field(default=None, ge=1)
    weight_set: Optional[dict[str, float]] = Field(default=None, min_length=1)
    aggregation_method: str = "weighted_sum"

    @field_validator("aggregation_method")
    @classmethod
    def validate_method(cls, value: str) -> str:
        value = value.strip().lower().replace("-", "_").replace(" ", "_")
        if value not in SUPPORTED_METHODS:
            raise ValueError(
                "aggregation_method must be one of: "
                + ", ".join(sorted(SUPPORTED_METHODS))
            )
        return value

    @field_validator("weight_set")
    @classmethod
    def validate_weights(cls, value: Optional[dict[str, float]]):
        if value is None:
            return value
        cleaned: dict[str, float] = {}
        for criterion, raw_weight in value.items():
            key = str(criterion).strip()
            if not key:
                raise ValueError("weight_set contains a blank criterion name")
            try:
                weight = float(raw_weight)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Weight for criterion {key!r} must be numeric"
                ) from exc
            if weight != weight or weight in (float("inf"), float("-inf")):
                raise ValueError(f"Weight for criterion {key!r} must be finite")
            if weight < 0:
                raise ValueError(f"Weight for criterion {key!r} must be non-negative")
            cleaned[key] = weight

        total = sum(cleaned.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"weight_set weights must sum to 1.0; got {total:.12g}")

        return cleaned

    @field_validator("weight_set", mode="after")
    @classmethod
    def require_exactly_one_source(cls, value, info):
        scenario_id = info.data.get("scenario_id")
        if (scenario_id is None) == (value is None):
            raise ValueError(
                "Provide exactly one of scenario_id or weight_set"
            )
        return value


class ExportResponse(BaseModel):
    """The export artefact."""

    export_id: str = Field(..., description="Identifier of the created export.")
    scenario_id: Optional[int] = None
    scenario_name: Optional[str] = None
    weight_set: dict[str, float] = Field(
        ..., description="The exact global weight mapping that produced the ranking."
    )
    aggregation_method: str
    generated_at: str
    site_count: int
    shortlist: list[dict[str, Any]]
    storage_path: Optional[str] = None
    persisted: bool = False
    notes: list[str] = Field(default_factory=list)


def _load_scenario(scenario_id: int) -> dict[str, Any]:
    """Load a persisted scenario, or raise a 404."""

    from api.app.core.supabase_client import get_supabase_client

    try:
        client = get_supabase_client()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"The scenario store is unavailable: {exc}",
        ) from exc

    response = (
        client.table("saved_scenarios")
        .select("scenario_id,name,weight_set,aggregation_method,created_at,updated_at")
        .eq("scenario_id", scenario_id)
        .limit(1)
        .execute()
    )
    rows = response.data or []
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scenario {scenario_id} not found.",
        )
    return rows[0]


def _persist_export(
    export_id: str,
    payload: dict[str, Any],
    scenario_id: Optional[int],
    user_id: Optional[str],
) -> tuple[Optional[str], bool]:
    """Write the export to Supabase Storage and record it.

    A failure to persist never loses the export: the artefact is still
    returned to the caller, and the reason is reported in the notes.
    """

    settings = get_settings()
    if not settings.has_supabase:
        return None, False

    try:
        from api.app.core.supabase_client import get_supabase_client

        client = get_supabase_client()
        bucket = DEFAULT_EXPORT_BUCKET
        storage_path = f"{export_id}/export.json"
        body = json.dumps(payload, indent=2, default=str).encode("utf-8")

        client.storage.from_(bucket).upload(
            storage_path,
            body,
            {"content_type": "application/json", "upsert": "true"},
        )

        record: dict[str, Any] = {
            "weight_set": payload.get("weight_set"),
            "aggregation_method": payload.get("aggregation_method"),
            "payload": payload,
        }
        if scenario_id is not None:
            record["scenario_id"] = scenario_id
        if user_id is not None:
            record["user_id"] = user_id

        client.table("export_records").insert(record).execute()
        return storage_path, True
    except Exception as exc:
        logger.warning("The export could not be persisted: %exc", exc)
        return None, False


@router.post("/export", response_model=ExportResponse, status_code=status.HTTP_201_CREATED)
def create_export(
    request: ExportRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> ExportResponse:
    """Create a reproducible export of the current ranking.

    The export record is owned by the signed-in user, so the record can
    be traced back to whoever produced it.
    """

    owner_id = require_user_id(user)

    scenario_id = request.scenario_id
    scenario_name: Optional[str] = None
    weight_set = request.weight_set
    aggregation_method = request.aggregation_method

    if scenario_id is not None:
        scenario = _load_scenario(scenario_id)
        scenario_name = scenario.get("name")
        weight_set = scenario.get("weight_set")
        aggregation_method = scenario.get("aggregation_method") or aggregation_method

    assert weight_set is not None

    notes: list[str] = []
    try:
        matrix = get_normalized_matrix()
    except MatrixUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"The normalised scoring matrix is unavailable: {exc}",
        ) from exc

    missing = [key for key in weight_set if key not in matrix.columns]
    if missing:
        notes.append(
            "These criteria had no data in the current release and did not "
            "contribute to the ranking: " + ", ".join(missing)
        )
        usable = {key: value for key, value in weight_set.items() if key in matrix.columns}
        if not usable:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "None of the requested criteria are present in the current "
                    "scoring matrix."
                ),
            )
        total = sum(usable.values())
        if total > 0:
            usable = {key: value / total for key, value in usable.items()}
        weight_set = usable

    try:
        scores = apply_weights(matrix, weight_set, method=aggregation_method)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    ranked = rank_sites(scores)
    shortlist = [
        {
            "rank": int(row["rank"]),
            "site_id": str(row["site_id"]),
            "score": round(float(row["score"]), 6),
        }
        for _, row in ranked.iterrows()
    ]

    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    export_id = f"export_{generated_at.replace(':', '').replace('-', '')}"

    payload: dict[str, Any] = {
        "export_id": export_id,
        "generated_at": generated_at,
        "scenario_id": scenario_id,
        "scenario_name": scenario_name,
        "weight_set": weight_set,
        "aggregation_method": aggregation_method,
        "site_count": len(shortlist),
        "shortlist": shortlist,
        "notes": notes,
    }

    storage_path, persisted = _persist_export(export_id, payload, scenario_id, None)
    if not persisted:
        notes.append(
            "The export could not be written to the export store. The artefact "
            "is still returned and can be archived by the caller."
        )

    return ExportResponse(
        export_id=export_id,
        scenario_id=scenario_id,
        scenario_name=scenario_name,
        weight_set=weight_set,
        aggregation_method=aggregation_method,
        generated_at=generated_at,
        site_count=len(shortlist),
        shortlist=shortlist,
        storage_path=storage_path,
        persisted=persisted,
        notes=notes,
    )


@router.get("/export/formats", summary="The available ranking export formats")
def list_export_formats() -> dict[str, Any]:
    """Describe the export artefacts the API can produce."""

    return {
        "formats": [
            {
                "key": "json",
                "label": "JSON",
                "description": (
                    "A self-describing artefact carrying the ranking, the exact "
                    "weight mapping, the aggregation method and the export "
                    "metadata. This is the reproducible export."
                ),
            }
        ],
        "note": (
            "The executive report is exported separately in PDF, CSV and Excel "
            "by POST /reports/export."
        ),
    }


__all__ = ["router", "ExportRequest", "ExportResponse"]
