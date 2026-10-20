"""Site-selection project persistence.

Every project is owned by the authenticated user.  The API never accepts
an owner identifier from the client: it is taken from the verified
session, and the row is written with that owner, so one user can never
read or modify another user's analysis even if they know the identifier.

The brief is stored relationally: the project row holds the parts that
are not lists (the name, the business type, the search area, the weights
and the notes), and the requirements, facilities, parking and financial
requirements are held in their own tables.  The API reassembles the
brief on the way out, so the client sees one consistent object.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from api.app.core.auth import AuthenticatedUser, get_current_user, require_user_id
from api.app.core.supabase_client import get_supabase_client, is_supabase_configured

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["Projects"])

PROJECT_TABLE = "site_selection_projects"
BUSINESS_REQUIREMENT_TABLE = "project_business_requirements"
FACILITY_REQUIREMENT_TABLE = "project_facility_requirements"
PARKING_TABLE = "project_parking_requirements"
FINANCIAL_TABLE = "project_financial_requirements"


class ProjectPayload(BaseModel):
    """The brief, as stored for one analysis."""

    id: Optional[str] = Field(
        default=None,
        description="Client-side identifier. A UUID is assigned when absent.",
    )
    name: str = Field(default="Untitled analysis", max_length=200)
    business_type: str = Field(default="", max_length=80)
    acquisition_mode: str = Field(default="either")
    location: dict[str, Any] = Field(default_factory=dict)
    requirements: list[dict[str, Any]] = Field(default_factory=list)
    parking: dict[str, Any] = Field(default_factory=dict)
    facilities: list[dict[str, Any]] = Field(default_factory=list)
    financial: dict[str, Any] = Field(default_factory=dict)
    weights: dict[str, Any] = Field(default_factory=dict)
    aggregation_method: str = Field(default="weighted_sum")
    criteria_coverage: dict[str, Any] = Field(default_factory=dict)
    notes: str = Field(default="", max_length=4000)
    confirmed: bool = Field(
        default=False,
        description="Whether the user has confirmed the requirements.",
    )


class ProjectResponse(BaseModel):
    project: ProjectPayload


class ProjectListResponse(BaseModel):
    projects: list[ProjectPayload]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require_supabase() -> None:
    if not is_supabase_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Saving analyses requires Supabase. Set SUPABASE_URL and "
                "SUPABASE_KEY (or SUPABASE_SERVICE_ROLE_KEY)."
            ),
        )


def _valid_project_id(project_id: str) -> bool:
    """True when the identifier is a UUID.

    The identifier is used in a PostgREST filter, where a malformed value
    raises a database error.  Validating it here turns that into a 404
    for an unknown project instead of a 500.
    """

    try:
        uuid.UUID(str(project_id))
    except (ValueError, AttributeError, TypeError):
        return False
    return True


def _numeric(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _integer(value: Any) -> Optional[int]:
    """Coerce a value to an integer for an integer column.

    The parking and horizon columns are integers in the database.  A
    float such as ``60.0`` is rejected by PostgREST with a syntax
    error, which would surface as a server error rather than as a
    rejected request.
    """

    number = _numeric(value)
    if number is None:
        return None
    return int(number)


def _text_value(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _parse_value(value: Any) -> Any:
    """Recover the original value type from the stored representation."""

    if value is None:
        return None
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "false"}:
            return lowered == "true"
        try:
            number = float(value)
        except ValueError:
            return value
        return int(number) if number.is_integer() else number
    return value


def _project_row_to_payload(row: dict[str, Any], children: dict[str, Any]) -> ProjectPayload:
    return ProjectPayload(
        id=str(row.get("id")),
        name=row.get("name") or "Untitled analysis",
        business_type=row.get("business_type") or "",
        acquisition_mode=row.get("acquisition_mode") or "either",
        location=row.get("location") or {},
        requirements=children.get("business_requirements") or [],
        parking=children.get("parking") or {},
        facilities=children.get("facility_requirements") or [],
        financial=children.get("financial") or {},
        weights=row.get("weights") or {},
        aggregation_method=row.get("aggregation_method") or "weighted_sum",
        criteria_coverage=row.get("criteria_coverage") or {},
        notes=row.get("notes") or "",
        confirmed=bool(row.get("confirmed_at")),
    )


# ---------------------------------------------------------------------------
# Row-to-payload mapping
# ---------------------------------------------------------------------------
# The mapping is defined once and used by both the single-project loader
# and the batched loader, so the two cannot drift apart.


def _business_requirement_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": row.get("requirement_key"),
        "label": row.get("label") or "",
        "importance": row.get("importance") or "not_important",
        "value": _parse_value(
            row.get("value") if row.get("value") is not None else row.get("value_text")
        ),
        "valueType": row.get("value_type") or "number",
        "unit": row.get("unit") or "",
        "minimum": _numeric(row.get("minimum")),
        "maximum": _numeric(row.get("maximum")),
        "options": row.get("options") or [],
        "helpText": row.get("help_text") or "",
    }


def _facility_requirement_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": row.get("facility_key"),
        "label": row.get("label") or "",
        "importance": row.get("importance") or "not_important",
    }


def _parking_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "minCarSpaces": _numeric(row.get("min_car_spaces")),
        "minTwoWheelerSpaces": _numeric(row.get("min_two_wheeler_spaces")),
        "minParkingAreaSqft": _numeric(row.get("min_parking_area_sqft")),
        "behaviour": row.get("behaviour") or "preference",
        "scope": row.get("scope") or "site",
    }


def _financial_payload(row: dict[str, Any]) -> dict[str, Any]:
    budgets = row.get("budgets") or []
    if not budgets:
        # Fall back to the individual limit columns.
        budgets = [
            {
                "key": column,
                "label": column.replace("_", " ").title(),
                "limit": _numeric(row.get(column)),
                "scope": "acquisition",
                "behaviour": row.get("budget_behaviour") or "penalise",
                "appliesTo": ["buy", "lease", "either"],
            }
            for column in (
                "purchase_budget",
                "monthly_rent_budget",
                "security_deposit_budget",
                "brokerage_budget",
                "renovation_budget",
                "initial_investment_budget",
                "monthly_operating_budget",
            )
            if row.get(column) is not None
        ]
    return {
        "budgets": budgets,
        "budgetBehaviour": row.get("budget_behaviour") or "penalise",
        "horizonMonths": _integer(row.get("horizon_months")) or 60,
    }


def _empty_children() -> dict[str, Any]:
    return {
        "business_requirements": [],
        "facility_requirements": [],
        "parking": {},
        "financial": {},
    }


def _load_children(client, project_id: str) -> dict[str, Any]:
    """Load the requirement rows for one project."""

    children = _empty_children()

    try:
        response = (
            client.table(BUSINESS_REQUIREMENT_TABLE)
            .select("*")
            .eq("project_id", project_id)
            .execute()
        )
        children["business_requirements"] = [
            _business_requirement_payload(row) for row in (response.data or [])
        ]
    except Exception as exc:
        logger.warning("Could not read the business requirements: %s", exc)

    try:
        response = (
            client.table(FACILITY_REQUIREMENT_TABLE)
            .select("*")
            .eq("project_id", project_id)
            .execute()
        )
        children["facility_requirements"] = [
            _facility_requirement_payload(row) for row in (response.data or [])
        ]
    except Exception as exc:
        logger.warning("Could not read the facility requirements: %s", exc)

    try:
        response = (
            client.table(PARKING_TABLE)
            .select("*")
            .eq("project_id", project_id)
            .limit(1)
            .execute()
        )
        if response.data:
            children["parking"] = _parking_payload(response.data[0])
    except Exception as exc:
        logger.warning("Could not read the parking requirements: %s", exc)

    try:
        response = (
            client.table(FINANCIAL_TABLE)
            .select("*")
            .eq("project_id", project_id)
            .limit(1)
            .execute()
        )
        if response.data:
            children["financial"] = _financial_payload(response.data[0])
    except Exception as exc:
        logger.warning("Could not read the financial requirements: %s", exc)

    return children


def _write_children(client, project_id: str, payload: ProjectPayload) -> None:
    """Replace the requirement rows for one project."""

    for table in (
        BUSINESS_REQUIREMENT_TABLE,
        FACILITY_REQUIREMENT_TABLE,
        PARKING_TABLE,
        FINANCIAL_TABLE,
    ):
        client.table(table).delete().eq("project_id", project_id).execute()

    if payload.requirements:
        client.table(BUSINESS_REQUIREMENT_TABLE).insert(
            [
                {
                    "project_id": project_id,
                    "requirement_key": item.get("key"),
                    "label": item.get("label") or "",
                    "importance": item.get("importance") or "not_important",
                    "value": _numeric(item.get("value")),
                    "value_text": _text_value(item.get("value")),
                    "value_type": item.get("valueType") or "number",
                    "unit": item.get("unit") or "",
                    "minimum": _numeric(item.get("minimum")),
                    "maximum": _numeric(item.get("maximum")),
                    "options": item.get("options") or [],
                    "help_text": item.get("helpText") or "",
                }
                for item in payload.requirements
            ]
        ).execute()

    if payload.facilities:
        client.table(FACILITY_REQUIREMENT_TABLE).insert(
            [
                {
                    "project_id": project_id,
                    "facility_key": item.get("key"),
                    "label": item.get("label") or "",
                    "importance": item.get("importance") or "not_important",
                }
                for item in payload.facilities
            ]
        ).execute()

    parking = payload.parking or {}
    client.table(PARKING_TABLE).insert(
        {
            "project_id": project_id,
            "min_car_spaces": _integer(parking.get("minCarSpaces")),
            "min_two_wheeler_spaces": _integer(parking.get("minTwoWheelerSpaces")),
            "min_parking_area_sqft": _numeric(parking.get("minParkingAreaSqft")),
            "behaviour": parking.get("behaviour") or "preference",
            "scope": parking.get("scope") or "site",
        }
    ).execute()

    financial = payload.financial or {}
    budgets = financial.get("budgets") or []
    limits = {
        budget.get("key"): _numeric(budget.get("limit"))
        for budget in budgets
        if isinstance(budget, dict) and budget.get("key")
    }
    client.table(FINANCIAL_TABLE).insert(
        {
            "project_id": project_id,
            "budgets": budgets,
            "budget_behaviour": financial.get("budgetBehaviour") or "penalise",
            "horizon_months": _integer(financial.get("horizonMonths")) or 60,
            # The individual limit columns are kept in step with the budget
            # list so that the financial requirement is queryable.
            "purchase_budget": limits.get("purchase_budget"),
            "monthly_rent_budget": limits.get("monthly_rent_budget"),
            "security_deposit_budget": limits.get("security_deposit_budget"),
            "brokerage_budget": limits.get("brokerage_budget"),
            "renovation_budget": limits.get("renovation_budget"),
            "initial_investment_budget": limits.get("initial_investment_budget"),
            "monthly_operating_budget": limits.get("monthly_operating_budget"),
        }
    ).execute()



def _load_children_batch(client, project_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Load the child rows of every project in four queries.

    Loading the children one project at a time costs four round trips
    per project.  The whole set is therefore fetched in one query per
    child table and grouped in memory.  The result has exactly the shape
    that :func:`_load_children` returns.
    """

    if not project_ids:
        return {}

    grouped: dict[str, dict[str, Any]] = {
        project_id: _empty_children() for project_id in project_ids
    }

    def _group(
        table: str,
        key: str,
        mapper: Any,
        limit: int | None = None,
    ) -> None:
        query = client.table(table).select("*").in_("project_id", project_ids)
        if limit is not None:
            query = query.limit(limit)
        response = query.execute()
        for row in response.data or []:
            bucket = grouped.get(str(row.get("project_id")))
            if bucket is None:
                continue
            if limit is None:
                bucket[key].append(mapper(row))
            else:
                bucket[key] = mapper(row)

    _group(BUSINESS_REQUIREMENT_TABLE, "business_requirements", _business_requirement_payload)
    _group(FACILITY_REQUIREMENT_TABLE, "facility_requirements", _facility_requirement_payload)
    _group(PARKING_TABLE, "parking", _parking_payload, limit=len(project_ids))
    _group(FINANCIAL_TABLE, "financial", _financial_payload, limit=len(project_ids))

    return grouped

def _project_row(payload: ProjectPayload, owner_id: str) -> dict[str, Any]:
    confirmed_at = (
        datetime.now(timezone.utc).isoformat(timespec="seconds")
        if payload.confirmed
        else None
    )
    return {
        "user_id": owner_id,
        "name": payload.name,
        "status": "analysed" if payload.confirmed else "draft",
        "business_type": payload.business_type or None,
        "acquisition_mode": payload.acquisition_mode,
        "location": payload.location or {},
        "weights": payload.weights or {},
        "aggregation_method": payload.aggregation_method,
        "criteria_coverage": payload.criteria_coverage or {},
        "notes": payload.notes or "",
        "confirmed_at": confirmed_at,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("", response_model=ProjectListResponse, summary="List your analyses")
def list_projects(user: AuthenticatedUser = Depends(get_current_user)) -> ProjectListResponse:
    """Return every analysis owned by the signed-in user, newest first."""

    _require_supabase()
    owner_id = require_user_id(user)

    client = get_supabase_client()

    response = (
        client.table(PROJECT_TABLE)
        .select("*")
        .eq("user_id", owner_id)
        .order("updated_at", desc=True)
        .execute()
    )

    project_ids = [str(row.get("id")) for row in (response.data or [])]
    children_by_project = _load_children_batch(client, project_ids)

    projects: list[ProjectPayload] = []
    for row in response.data or []:
        children = children_by_project.get(str(row.get("id"))) or {}
        projects.append(_project_row_to_payload(row, children))

    return ProjectListResponse(projects=projects)


@router.post(
    "", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED,
    summary="Save an analysis",
)
def create_project(
    payload: ProjectPayload, user: AuthenticatedUser = Depends(get_current_user)
) -> ProjectResponse:
    """Create an analysis owned by the signed-in user."""

    _require_supabase()
    owner_id = require_user_id(user)

    client = get_supabase_client()

    row = _project_row(payload, owner_id)
    if payload.id:
        try:
            uuid.UUID(str(payload.id))
            row["id"] = str(payload.id)
        except (ValueError, AttributeError):
            pass

    response = client.table(PROJECT_TABLE).insert(row).execute()
    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The analysis could not be saved.",
        )
    saved = response.data[0]
    _write_children(client, str(saved["id"]), payload)
    children = _load_children(client, str(saved["id"]))
    return ProjectResponse(project=_project_row_to_payload(saved, children))


@router.get("/{project_id}", response_model=ProjectResponse, summary="Open an analysis")
def get_project(
    project_id: str, user: AuthenticatedUser = Depends(get_current_user)
) -> ProjectResponse:
    """Return one analysis owned by the signed-in user."""

    _require_supabase()
    owner_id = require_user_id(user)

    if not _valid_project_id(project_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    client = get_supabase_client()

    response = (
        client.table(PROJECT_TABLE)
        .select("*")
        .eq("id", project_id)
        .eq("user_id", owner_id)
        .limit(1)
        .execute()
    )
    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="That analysis was not found.",
        )
    row = response.data[0]
    children = _load_children(client, project_id)
    return ProjectResponse(project=_project_row_to_payload(row, children))


@router.patch("/{project_id}", response_model=ProjectResponse, summary="Update an analysis")
def update_project(
    project_id: str,
    payload: ProjectPayload,
    user: AuthenticatedUser = Depends(get_current_user),
) -> ProjectResponse:
    """Update an analysis owned by the signed-in user."""

    _require_supabase()
    owner_id = require_user_id(user)

    if not _valid_project_id(project_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    client = get_supabase_client()

    row = _project_row(payload, owner_id)
    row.pop("user_id", None)

    response = (
        client.table(PROJECT_TABLE)
        .update(row)
        .eq("id", project_id)
        .eq("user_id", owner_id)
        .execute()
    )
    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="That analysis was not found.",
        )
    saved = response.data[0]
    _write_children(client, project_id, payload)
    children = _load_children(client, project_id)
    return ProjectResponse(project=_project_row_to_payload(saved, children))


@router.delete(
    "/{project_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete an analysis"
)
def delete_project(
    project_id: str, user: AuthenticatedUser = Depends(get_current_user)
) -> None:
    """Delete an analysis owned by the signed-in user."""

    _require_supabase()
    owner_id = require_user_id(user)

    if not _valid_project_id(project_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    client = get_supabase_client()

    response = (
        client.table(PROJECT_TABLE)
        .delete()
        .eq("id", project_id)
        .eq("user_id", owner_id)
        .execute()
    )
    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="That analysis was not found.",
        )


__all__ = ["router"]
