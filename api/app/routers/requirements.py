"""Site-selection requirements: catalogue, deterministic evaluation and the
AI-assisted requirement builder.

The AI builder is deliberately *advisory*.  It converts natural language
into a structured, editable draft that the user must confirm; it never
applies a requirement on the user's behalf and it never produces a site
score, a cost or a property fact.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Mapping, Optional

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator

from app.core.config import get_settings
from app.domain.catalog import (
    ACQUISITION_MODES,
    CONSTRAINT_BEHAVIOURS,
    business_type_catalog,
    facility_catalog,
    requirement_catalog,
    requirements_for_business_type,
)
from app.routers.sites import get_sites_dataframe
from scoring.cost_estimation import apply_estimations, total_cost_of_ownership
from scoring.requirement_fit import (
    DEFAULT_PENALTY_RATE,
    apply_fit_penalty,
    evaluate_site_requirements,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/requirements", tags=["Requirements"])


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------

@router.get("/catalog", summary="Business types, requirements and facilities")
def get_catalog() -> dict[str, Any]:
    """Return the configurable requirement catalogue.

    The interface renders every business-specific question, facility list
    and constraint behaviour from this response so that the client never
    has to hard-code product rules.
    """

    return {
        "business_types": business_type_catalog(),
        "requirements": requirement_catalog(),
        "facilities": facility_catalog(),
        "constraint_behaviours": [
            {
                "key": "hard",
                "label": "Hard requirement",
                "description": "Sites that fail the requirement are excluded from the shortlist.",
            },
            {
                "key": "preference",
                "label": "Preference",
                "description": "Sites are retained; the requirement reduces their suitability score.",
            },
            {
                "key": "flexible",
                "label": "Flexible",
                "description": "Sites are retained and the shortfall is shown as a warning only.",
            },
        ],
        "acquisition_modes": [
            {
                "key": "buy",
                "label": "Buy",
                "description": "Purchase the property outright.",
            },
            {
                "key": "lease",
                "label": "Lease",
                "description": "Take the property on a lease.",
            },
            {
                "key": "either",
                "label": "Buy or lease",
                "description": "Compare both economics where the data allows.",
            },
        ],
        "budget_definitions": [
            {
                "key": "purchase_budget",
                "label": "Purchase budget",
                "scope": "acquisition",
                "applies_to": ["buy", "either"],
            },
            {
                "key": "monthly_rent_budget",
                "label": "Monthly rent budget",
                "scope": "rent",
                "applies_to": ["lease", "either"],
            },
            {
                "key": "security_deposit_budget",
                "label": "Security deposit budget",
                "scope": "acquisition",
                "applies_to": ["lease", "either"],
            },
            {
                "key": "brokerage_budget",
                "label": "Brokerage budget",
                "scope": "acquisition",
                "applies_to": ["buy", "lease", "either"],
            },
            {
                "key": "renovation_budget",
                "label": "Renovation budget",
                "scope": "setup",
                "applies_to": ["buy", "lease", "either"],
            },
            {
                "key": "initial_investment_budget",
                "label": "Total initial investment budget",
                "scope": "initial_investment",
                "applies_to": ["buy", "lease", "either"],
            },
            {
                "key": "monthly_operating_budget",
                "label": "Monthly operating cost budget",
                "scope": "recurring_monthly",
                "applies_to": ["buy", "lease", "either"],
            },
        ],
        "parking_fields": [
            {
                "key": "min_car_spaces",
                "label": "Minimum car parking spaces",
                "unit": "spaces",
            },
            {
                "key": "min_two_wheeler_spaces",
                "label": "Minimum two-wheeler parking spaces",
                "unit": "spaces",
            },
            {
                "key": "min_parking_area_sqft",
                "label": "Minimum parking area",
                "unit": "sq ft",
            },
        ],
        "default_penalty_rate": DEFAULT_PENALTY_RATE,
    }


@router.get(
    "/profile/{business_type}",
    summary="Default requirement profile for a business type",
)
def get_business_profile(business_type: str) -> dict[str, Any]:
    """Return the default REQUIRED / PREFERRED / NOT IMPORTANT profile.

    The user is always able to change these before the analysis runs.
    """

    entries = requirements_for_business_type(business_type)
    if not entries:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown business type: {business_type!r}.",
        )
    return {"business_type": business_type, "requirements": entries}


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

class EvaluateRequest(BaseModel):
    requirements: dict[str, Any] = Field(
        default_factory=dict,
        description="The confirmed requirement block.",
    )
    penalty_rate: float = Field(
        default=DEFAULT_PENALTY_RATE,
        ge=0.0,
        le=1.0,
        description="Maximum proportional penalty applied when a preference is not met.",
    )
    site_ids: Optional[list[str]] = Field(
        default=None,
        description="Restrict the evaluation to these site identifiers.",
    )


class SiteEvaluation(BaseModel):
    site_id: str
    name: Optional[str] = None
    eligible: bool
    fit_ratio: float
    fit_factor: float
    evaluation: dict[str, Any]


class EvaluateResponse(BaseModel):
    sites: list[SiteEvaluation]
    evaluated_count: int
    eligible_count: int
    excluded_count: int
    penalty_rate: float
    notes: list[str] = Field(default_factory=list)


def _enrich_requirements(requirements: Mapping[str, Any]) -> dict[str, Any]:
    """Attach the catalogue's attribute aliases to the requirement block.

    A facility is recorded on a site under any one of several attribute
    names (for example ``parking``, ``parking_capacity`` or
    ``has_parking``).  The catalogue is the single source of truth for
    those aliases, so they are attached here rather than being required
    from the client.
    """

    from app.domain.catalog import FACILITY_BY_KEY, REQUIREMENT_BY_KEY

    enriched = dict(requirements)

    facilities = list(enriched.get("facilities") or [])
    for facility in facilities:
        if not isinstance(facility, dict):
            continue
        key = str(facility.get("key") or "")
        definition = FACILITY_BY_KEY.get(key)
        if definition is not None and not facility.get("site_attributes"):
            facility["site_attributes"] = list(definition.site_attributes)
        if definition is not None and not facility.get("label"):
            facility["label"] = definition.label
    enriched["facilities"] = facilities

    business = list(enriched.get("business_requirements") or [])
    for requirement in business:
        if not isinstance(requirement, dict):
            continue
        key = str(requirement.get("key") or "")
        definition = REQUIREMENT_BY_KEY.get(key)
        if definition is not None and not requirement.get("site_attributes"):
            requirement["site_attributes"] = list(definition.site_attributes)
        if definition is not None and not requirement.get("label"):
            requirement["label"] = definition.label
    enriched["business_requirements"] = business

    return enriched


@router.post(
    "/evaluate",
    response_model=EvaluateResponse,
    summary="Evaluate confirmed requirements against the candidate inventory",
)
def evaluate_requirements(payload: EvaluateRequest, request: Request) -> EvaluateResponse:
    """Evaluate every candidate site against the confirmed requirements.

    The response reports, per site: hard-constraint failures, parking,
    facility and business-requirement match, the cost position, the fit
    ratio and the resulting penalty factor.  The fit factor is returned
    separately from the score so the interface can apply it transparently.
    """

    try:
        sites_df = get_sites_dataframe(request)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Candidate site inventory is unavailable: {exc}",
        ) from exc

    requirements = _enrich_requirements(payload.requirements)
    requested_ids = set(payload.site_ids or [])
    results: list[SiteEvaluation] = []
    notes: list[str] = []
    excluded = 0

    for _, row in sites_df.iterrows():
        site_id = str(row.get("site_id") or row.get("id") or row.name)
        if requested_ids and site_id not in requested_ids:
            continue

        attributes = _row_attributes(row)
        evaluation = evaluate_site_requirements(
            site_id=site_id,
            attributes=attributes,
            requirements=requirements,
            penalty_rate=payload.penalty_rate,
        )

        # Apply the configured estimation rules and report the cost of
        # ownership over the configured horizon.  The estimations are
        # applied to the assessment itself, so that the estimated lines
        # carry their provenance into the response.
        if evaluation.cost is not None:
            rules = get_settings().cost_estimation_rules()
            if rules.enabled:
                apply_estimations(evaluation.cost, rules)
            horizon = int(
                (payload.requirements.get("financial") or {}).get("horizon_months")
                or get_settings().cost_horizon_months
            )
            evaluation.cost.notes.append(
                f"Cost of ownership is reported over {horizon} months."
            )
            evaluation.cost.cost_of_ownership = total_cost_of_ownership(
                evaluation.cost, horizon
            )

        if not evaluation.eligible:
            excluded += 1

        results.append(
            SiteEvaluation(
                site_id=site_id,
                name=str(row.get("name")) if row.get("name") else None,
                eligible=evaluation.eligible,
                fit_ratio=evaluation.fit_ratio,
                fit_factor=evaluation.fit_factor,
                evaluation=evaluation.to_dict(),
            )
        )

    if not results:
        notes.append("No candidate sites matched the requested selection.")

    return EvaluateResponse(
        sites=results,
        evaluated_count=len(results),
        eligible_count=len(results) - excluded,
        excluded_count=excluded,
        penalty_rate=payload.penalty_rate,
        notes=notes,
    )


def _row_attributes(row: Any) -> dict[str, Any]:
    """Flatten a site row into a plain attribute mapping."""

    attributes: dict[str, Any] = {}
    for key, value in row.items():
        if value is None:
            continue
        try:
            if value != value:  # NaN
                continue
        except Exception:  # pragma: no cover - non-scalar values
            pass
        attributes[str(key)] = value
    return attributes


# ---------------------------------------------------------------------------
# AI-assisted requirement builder
# ---------------------------------------------------------------------------

class ParseRequest(BaseModel):
    description: str = Field(
        ...,
        min_length=3,
        max_length=4000,
        description="The user's description of the site they are looking for.",
    )
    business_type: Optional[str] = None
    known_requirements: dict[str, Any] = Field(default_factory=dict)


class ParsedRequirement(BaseModel):
    key: str
    label: str
    importance: str
    value: Any = None
    unit: str = ""
    value_type: str = "number"
    confidence: str = "inferred"
    source_quote: str = ""


class ParseResponse(BaseModel):
    interpretation_summary: str
    business_type: Optional[str] = None
    acquisition_mode: str = "either"
    requirements: list[ParsedRequirement]
    parking: dict[str, Any] = Field(default_factory=dict)
    facilities: list[dict[str, Any]] = Field(default_factory=list)
    financial: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    requires_confirmation: bool = True
    provider: Optional[str] = None


def _normalise_parsed(payload: Mapping[str, Any]) -> ParseResponse:
    from app.domain.catalog import REQUIREMENT_BY_KEY, FACILITY_BY_KEY

    known_requirement_keys = set(REQUIREMENT_BY_KEY)
    known_facility_keys = set(FACILITY_BY_KEY)

    requirements: list[ParsedRequirement] = []
    for entry in payload.get("requirements") or []:
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("key") or "")
        if key not in known_requirement_keys:
            continue
        definition = REQUIREMENT_BY_KEY[key]
        importance = str(entry.get("importance") or "preferred")
        if importance not in {"required", "preferred", "not_important"}:
            importance = "preferred"
        requirements.append(
            ParsedRequirement(
                key=key,
                label=definition.label,
                importance=importance,
                value=entry.get("value", definition.default),
                unit=definition.unit,
                value_type=definition.value_type,
                confidence="inferred",
                source_quote=str(entry.get("source_quote") or ""),
            )
        )

    facilities: list[dict[str, Any]] = []
    for entry in payload.get("facilities") or []:
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("key") or "")
        if key not in known_facility_keys:
            continue
        importance = str(entry.get("importance") or "preferred")
        if importance not in {"required", "preferred"}:
            importance = "preferred"
        facilities.append(
            {
                "key": key,
                "label": FACILITY_BY_KEY[key].label,
                "importance": importance,
            }
        )

    parking = payload.get("parking") or {}
    if not isinstance(parking, dict):
        parking = {}
    parking = {str(k): v for k, v in parking.items() if v is not None}
    if parking.get("behaviour") not in CONSTRAINT_BEHAVIOURS:
        parking["behaviour"] = "preference"

    financial = payload.get("financial") or {}
    if not isinstance(financial, dict):
        financial = {}

    acquisition_mode = str(payload.get("acquisition_mode") or "either")
    if acquisition_mode not in ACQUISITION_MODES:
        acquisition_mode = "either"

    return ParseResponse(
        interpretation_summary=str(payload.get("interpretation_summary") or ""),
        business_type=payload.get("business_type"),
        acquisition_mode=acquisition_mode,
        requirements=requirements,
        parking=parking,
        facilities=facilities,
        financial=financial,
        warnings=[str(item) for item in (payload.get("warnings") or [])],
        requires_confirmation=True,
    )


@router.post(
    "/parse",
    response_model=ParseResponse,
    summary="Interpret a natural-language brief into editable requirements",
)
async def parse_requirements(payload: ParseRequest) -> ParseResponse:
    """Convert a natural-language brief into a structured requirement draft.

    The response is a **draft**: it is displayed to the user as
    "AI interpreted your requirements as:", the user edits it, and only
    after explicit confirmation are the requirements used to filter or
    score sites.

    The provider (Groq) is only used to read the brief.  It never applies a
    requirement, never changes a weight, never produces a cost and never
    writes to the database.

    If no provider is configured, or the provider fails, the endpoint
    returns a typed error and the interface falls back to the manual
    requirement form.
    """

    from app.domain.ai import (
        AIInvalidResponseError,
        AINotConfiguredError,
        AIProviderError,
        AIRateLimitError,
        AITimeoutError,
        parse_requirements as run_parser,
    )

    try:
        brief, _response = await run_parser(
            payload.description, payload.business_type
        )
    except AINotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except AITimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)
        ) from exc
    except AIRateLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)
        ) from exc
    except AIInvalidResponseError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc
    except AIProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc

    result = _normalise_parsed(brief.model_dump())
    result.provider = get_settings().groq_model
    return result


__all__ = ["router"]

