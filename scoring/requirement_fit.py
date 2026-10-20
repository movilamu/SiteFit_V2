"""Deterministic evaluation of user requirements against candidate sites.

This module is the requirement layer that sits alongside the
multi-criteria analysis.  It never produces a "site score" on its own: it
produces **check results** and a **fit ratio**, and the fit ratio is
applied to the multi-criteria score by a single, documented penalty rule.

Behaviour model
---------------
Each requirement carries one of three behaviours:

``hard``        a site that fails the requirement is excluded from the
                shortlist.  The exclusion and its reasons are reported.
``preference``  the site is retained and its fit ratio is reduced, which
                lowers the final score through the penalty rule.
``flexible``    the site is retained, the shortfall is reported as a
                warning, and the fit ratio is *not* reduced.

The fit ratio
-------------
``fit_ratio`` is the share of the user's stated requirements that the site
satisfies::

    fit_ratio = (required_met + 0.5 * preferred_met)
                / (required_total + preferred_total)

Requirements that are marked *not important* are excluded from the ratio
entirely.  Requirements whose underlying data is unavailable for a site are
counted as *unknown* and are removed from both the numerator and the
denominator, so missing data can never masquerade as a failure.

The penalty rule
----------------
The final score for a site is::

    final_score = base_score * fit_factor
    fit_factor  = 1 - penalty_rate * (1 - fit_ratio)

``penalty_rate`` defaults to 0.25 and is configurable, so a site that
satisfies no preference loses at most 25 % of its multi-criteria score.
Both the base score and the factor are always reported, so the effect of
the penalty is fully transparent and reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

from scoring.cost_model import (
    CostBudget,
    assess_site_costs,
    compare_budgets,
)

# Statuses
STATUS_PASS = "pass"
STATUS_FAIL = "fail"
STATUS_WARNING = "warning"
STATUS_UNKNOWN = "unknown"
STATUS_NOT_APPLICABLE = "not_applicable"

# Importance levels (mirrors api.app.domain.catalog)
REQUIRED = "required"
PREFERRED = "preferred"
NOT_IMPORTANT = "not_important"

BEHAVIOUR_HARD = "hard"
BEHAVIOUR_PREFERENCE = "preference"
BEHAVIOUR_FLEXIBLE = "flexible"

DEFAULT_PENALTY_RATE = 0.25


@dataclass
class CheckResult:
    """The outcome of evaluating one requirement against one site."""

    key: str
    label: str
    status: str
    importance: str = REQUIRED
    detail: str = ""
    observed: Any = None
    expected: Any = None
    source: Optional[str] = None

    @property
    def is_met(self) -> bool:
        return self.status == STATUS_PASS

    @property
    def is_unknown(self) -> bool:
        return self.status == STATUS_UNKNOWN

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "status": self.status,
            "importance": self.importance,
            "detail": self.detail,
            "observed": self.observed,
            "expected": self.expected,
            "source": self.source,
        }


@dataclass
class SectionEvaluation:
    """Aggregated results for one requirement section."""

    section: str
    behaviour: str = BEHAVIOUR_PREFERENCE
    checks: list[CheckResult] = field(default_factory=list)
    required_total: int = 0
    required_met: int = 0
    required_failed: int = 0
    required_unknown: int = 0
    preferred_total: int = 0
    preferred_met: int = 0
    preferred_unknown: int = 0
    fit_ratio: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "section": self.section,
            "behaviour": self.behaviour,
            "checks": [check.to_dict() for check in self.checks],
            "required_total": self.required_total,
            "required_met": self.required_met,
            "required_failed": self.required_failed,
            "required_unknown": self.required_unknown,
            "preferred_total": self.preferred_total,
            "preferred_met": self.preferred_met,
            "preferred_unknown": self.preferred_unknown,
            "fit_ratio": round(self.fit_ratio, 6),
            "status": self.status,
        }

    @property
    def status(self) -> str:
        if self.required_failed:
            return STATUS_FAIL
        if self.required_unknown:
            return STATUS_UNKNOWN
        if self.preferred_failed:
            return STATUS_WARNING
        return STATUS_PASS

    @property
    def preferred_failed(self) -> int:
        return self.preferred_total - self.preferred_met - self.preferred_unknown


@dataclass
class RequirementEvaluation:
    """The full requirement evaluation for a single site."""

    site_id: str
    eligible: bool = True
    hard_failures: list[CheckResult] = field(default_factory=list)
    parking: Optional[SectionEvaluation] = None
    facilities: Optional[SectionEvaluation] = None
    business_requirements: Optional[SectionEvaluation] = None
    #: The cost assessment.  It is kept as the object rather than a
    #: dictionary so that the caller can apply the configured estimation
    #: rules to it before the result is serialised.
    cost: Optional[CostAssessment] = None
    fit_ratio: float = 1.0
    fit_factor: float = 1.0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "site_id": self.site_id,
            "eligible": self.eligible,
            "hard_failures": [check.to_dict() for check in self.hard_failures],
            "parking": self.parking.to_dict() if self.parking else None,
            "facilities": self.facilities.to_dict() if self.facilities else None,
            "business_requirements": (
                self.business_requirements.to_dict() if self.business_requirements else None
            ),
            "cost": self.cost.to_dict() if self.cost is not None else None,
            "fit_ratio": round(self.fit_ratio, 6),
            "fit_factor": round(self.fit_factor, 6),
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _lookup(attributes: Mapping[str, Any], names: Sequence[str]) -> tuple[Optional[Any], Optional[str]]:
    for name in names:
        if name in attributes:
            value = attributes[name]
            if value is None:
                continue
            if isinstance(value, str) and value.strip() == "":
                continue
            return value, name
    return None, None


def _as_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _is_truthy(value: Any) -> bool:
    """Interpret a site attribute as a present/absent capability."""

    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value > 0
    if isinstance(value, str):
        return value.strip().lower() not in {"", "no", "false", "none", "unavailable", "0"}
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    return bool(value)


def _finalize(section: SectionEvaluation) -> SectionEvaluation:
    """Compute the section fit ratio from its checks."""

    required_known = section.required_total - section.required_unknown
    preferred_known = section.preferred_total - section.preferred_unknown

    denominator = required_known + preferred_known
    if denominator <= 0:
        section.fit_ratio = 1.0
        return section

    numerator = section.required_met + 0.5 * section.preferred_met
    section.fit_ratio = max(0.0, min(1.0, numerator / denominator))
    return section


# ---------------------------------------------------------------------------
# Parking
# ---------------------------------------------------------------------------

_PARKING_CHECKS = (
    ("car_spaces", "Car parking spaces", ("car_spaces", "car_parking", "parking_capacity_cars", "parking_capacity")),
    ("two_wheeler_spaces", "Two-wheeler parking spaces", ("two_wheeler_spaces", "two_wheeler_parking", "bike_parking", "parking_capacity_two_wheeler")),
    ("parking_area_sqft", "Parking area", ("parking_area_sqft", "parking_area", "parking_space_area")),
)


def evaluate_parking(
    attributes: Mapping[str, Any],
    parking: Optional[Mapping[str, Any]],
) -> SectionEvaluation:
    """Evaluate the parking requirement for one site.

    The behaviour is never chosen silently: it is read from the user's
    explicit selection and echoed back in the result.
    """

    parking = parking or {}
    behaviour = str(parking.get("behaviour") or BEHAVIOUR_PREFERENCE)
    section = SectionEvaluation(section="parking", behaviour=behaviour)

    if not parking:
        return _finalize(section)

    for key, label, sources in _PARKING_CHECKS:
        required = parking.get(f"min_{key}")
        if required is None:
            continue

        observed, source_name = _lookup(attributes, sources)
        if observed is None:
            section.checks.append(
                CheckResult(
                    key=key,
                    label=label,
                    status=STATUS_UNKNOWN,
                    importance=REQUIRED,
                    detail="Parking data is not available for this site.",
                    expected=required,
                )
            )
            section.required_total += 1
            section.required_unknown += 1
            continue

        observed_value = _as_float(observed)
        if observed_value is None:
            section.checks.append(
                CheckResult(
                    key=key,
                    label=label,
                    status=STATUS_UNKNOWN,
                    importance=REQUIRED,
                    detail="The recorded parking value could not be interpreted.",
                    observed=observed,
                    expected=required,
                    source=source_name,
                )
            )
            section.required_total += 1
            section.required_unknown += 1
            continue

        required_value = _as_float(required) or 0.0
        met = observed_value >= required_value
        section.checks.append(
            CheckResult(
                key=key,
                label=label,
                status=STATUS_PASS if met else STATUS_FAIL,
                importance=REQUIRED,
                detail=(
                    f"{observed_value:,.0f} available against {required_value:,.0f} required."
                ),
                observed=observed_value,
                expected=required_value,
                source=source_name,
            )
        )
        section.required_total += 1
        if met:
            section.required_met += 1
        else:
            section.required_failed += 1

    return _finalize(section)


# ---------------------------------------------------------------------------
# Facilities
# ---------------------------------------------------------------------------

def evaluate_facilities(
    attributes: Mapping[str, Any],
    facilities: Sequence[Mapping[str, Any]],
) -> SectionEvaluation:
    """Evaluate the facility requirements for one site."""

    section = SectionEvaluation(section="facilities", behaviour=BEHAVIOUR_PREFERENCE)

    for entry in facilities or []:
        key = str(entry.get("key") or "")
        if not key:
            continue
        label = str(entry.get("label") or key.replace("_", " ").title())
        importance = str(entry.get("importance") or NOT_IMPORTANT)
        if importance == NOT_IMPORTANT:
            continue

        sources = entry.get("site_attributes") or (key,)
        observed, source_name = _lookup(attributes, tuple(sources))

        if observed is None:
            status = STATUS_UNKNOWN
            detail = "Facility data is not available for this site."
        elif _is_truthy(observed):
            status = STATUS_PASS
            detail = "Facility is present at this site."
        else:
            status = STATUS_FAIL
            detail = "Facility is not present at this site."

        section.checks.append(
            CheckResult(
                key=key,
                label=label,
                status=status,
                importance=importance,
                detail=detail,
                observed=observed,
                source=source_name,
            )
        )

        if importance == REQUIRED:
            section.required_total += 1
            if status == STATUS_PASS:
                section.required_met += 1
            elif status == STATUS_FAIL:
                section.required_failed += 1
            else:
                section.required_unknown += 1
        else:
            section.preferred_total += 1
            if status == STATUS_PASS:
                section.preferred_met += 1
            elif status == STATUS_UNKNOWN:
                section.preferred_unknown += 1

    return _finalize(section)


# ---------------------------------------------------------------------------
# Business requirements
# ---------------------------------------------------------------------------

def evaluate_business_requirements(
    attributes: Mapping[str, Any],
    requirements: Sequence[Mapping[str, Any]],
) -> SectionEvaluation:
    """Evaluate the business-specific requirements for one site."""

    section = SectionEvaluation(section="business_requirements", behaviour=BEHAVIOUR_PREFERENCE)

    for entry in requirements or []:
        key = str(entry.get("key") or "")
        if not key:
            continue
        label = str(entry.get("label") or key.replace("_", " ").title())
        importance = str(entry.get("importance") or NOT_IMPORTANT)
        if importance == NOT_IMPORTANT:
            continue

        expected = entry.get("value")
        value_type = str(entry.get("value_type") or "number")
        sources = entry.get("site_attributes") or (key,)

        observed, source_name = _lookup(attributes, tuple(sources))

        if observed is None:
            status = STATUS_UNKNOWN
            detail = "This property attribute is not recorded for this site."
        elif value_type == "boolean":
            met = _is_truthy(observed)
            status = STATUS_PASS if met else STATUS_FAIL
            detail = (
                "Requirement is satisfied at this site."
                if met
                else "Requirement is not satisfied at this site."
            )
        elif value_type == "select":
            met = str(observed).strip().lower() == str(expected).strip().lower()
            status = STATUS_PASS if met else STATUS_FAIL
            detail = (
                f"Recorded value '{observed}' matches the required '{expected}'."
                if met
                else f"Recorded value '{observed}' does not meet the required '{expected}'."
            )
        else:
            observed_value = _as_float(observed)
            expected_value = _as_float(expected)
            if observed_value is None or expected_value is None:
                status = STATUS_UNKNOWN
                detail = "The recorded value could not be interpreted."
            else:
                met = observed_value >= expected_value
                status = STATUS_PASS if met else STATUS_FAIL
                detail = (
                    f"{observed_value:,.0f} recorded against {expected_value:,.0f} required."
                )

        section.checks.append(
            CheckResult(
                key=key,
                label=label,
                status=status,
                importance=importance,
                detail=detail,
                observed=observed,
                expected=expected,
                source=source_name,
            )
        )

        if importance == REQUIRED:
            section.required_total += 1
            if status == STATUS_PASS:
                section.required_met += 1
            elif status == STATUS_FAIL:
                section.required_failed += 1
            else:
                section.required_unknown += 1
        else:
            section.preferred_total += 1
            if status == STATUS_PASS:
                section.preferred_met += 1
            elif status == STATUS_UNKNOWN:
                section.preferred_unknown += 1

    return _finalize(section)


# ---------------------------------------------------------------------------
# Fit factor
# ---------------------------------------------------------------------------

def combine_fit_ratio(sections: Sequence[Optional[SectionEvaluation]]) -> float:
    """Combine the section fit ratios into a single site fit ratio.

    Sections are weighted by how many *known* requirements they contain, so
    a section with a single check does not dominate a section with ten.
    """

    numerator = 0.0
    denominator = 0.0
    for section in sections:
        if section is None:
            continue
        known = (
            (section.required_total - section.required_unknown)
            + (section.preferred_total - section.preferred_unknown)
        )
        if known <= 0:
            continue
        numerator += section.fit_ratio * known
        denominator += known

    if denominator <= 0:
        return 1.0
    return max(0.0, min(1.0, numerator / denominator))


def compute_fit_factor(
    fit_ratio: float,
    penalty_rate: float = DEFAULT_PENALTY_RATE,
    behaviour: str = BEHAVIOUR_PREFERENCE,
) -> float:
    """Convert a fit ratio into the multiplier applied to the base score.

    ``flexible`` behaviour never penalises.  ``preference`` applies the
    configured penalty rate.  ``hard`` behaviour is handled by exclusion,
    so the factor stays at 1.0 for surviving sites.
    """

    if behaviour == BEHAVIOUR_FLEXIBLE:
        return 1.0
    rate = max(0.0, min(1.0, float(penalty_rate)))
    ratio = max(0.0, min(1.0, float(fit_ratio)))
    return 1.0 - rate * (1.0 - ratio)


def apply_fit_penalty(base_score: float, fit_factor: float) -> float:
    """Apply the fit factor to a base multi-criteria score."""

    return float(base_score) * float(fit_factor)


# ---------------------------------------------------------------------------
# Top-level evaluation
# ---------------------------------------------------------------------------

def _budget_from_mapping(raw: Mapping[str, Any]) -> CostBudget:
    """Build a cost budget from a requirement payload.

    The budget entries come from the requirement catalogue, which uses
    camelCase keys and carries extra fields such as ``appliesTo``.  Only
    the fields the cost model uses are read, so an extra field in the
    payload never breaks the evaluation.
    """

    limit = raw.get("limit")
    try:
        numeric_limit = float(limit) if limit is not None else None
    except (TypeError, ValueError):
        numeric_limit = None

    scope = raw.get("scope")
    if not isinstance(scope, str) or not scope.strip():
        applies_to = raw.get("appliesTo") or raw.get("applies_to") or []
        if isinstance(applies_to, (list, tuple)):
            applies_to = [str(item).strip().lower() for item in applies_to]
            scope = "acquisition" if "buy" in applies_to else "rent"
        else:
            scope = "acquisition"

    behaviour = raw.get("behaviour")
    return CostBudget(
        key=str(raw.get("key") or ""),
        label=str(raw.get("label") or raw.get("key") or ""),
        limit=numeric_limit,
        behaviour=str(behaviour or "penalise"),
        scope=str(scope).strip(),
    )


def evaluate_site_requirements(
    site_id: str,
    attributes: Mapping[str, Any],
    requirements: Mapping[str, Any],
    penalty_rate: float = DEFAULT_PENALTY_RATE,
) -> RequirementEvaluation:
    """Evaluate every requirement block for one candidate site.

    Args:
        site_id: The site identifier.
        attributes: The site's attribute mapping.
        requirements: The user's requirement block, with optional keys
            ``parking``, ``facilities``, ``business_requirements``,
            ``financial`` and ``acquisition_mode``.
        penalty_rate: The maximum proportional penalty applied when a
            preference is not met.
    """

    requirements = requirements or {}
    evaluation = RequirementEvaluation(site_id=site_id)

    evaluation.parking = evaluate_parking(attributes, requirements.get("parking"))
    evaluation.facilities = evaluate_facilities(
        attributes, requirements.get("facilities") or []
    )
    evaluation.business_requirements = evaluate_business_requirements(
        attributes, requirements.get("business_requirements") or []
    )

    # --- Financial --------------------------------------------------
    financial = requirements.get("financial") or {}
    acquisition_mode = str(
        requirements.get("acquisition_mode") or financial.get("acquisition_mode") or "either"
    )
    assessment = assess_site_costs(
        site_id=site_id,
        attributes=attributes,
        acquisition_mode=acquisition_mode,
        financial=financial,
    )
    budgets = [
        _budget_from_mapping(budget)
        for budget in (financial.get("budgets") or [])
        if isinstance(budget, Mapping)
    ]
    assessment.budget_results = compare_budgets(assessment, budgets)
    evaluation.cost = assessment

    # --- Hard requirements -------------------------------------------
    for section in (evaluation.parking, evaluation.facilities, evaluation.business_requirements):
        if section is None:
            continue
        if section.behaviour != BEHAVIOUR_HARD:
            continue
        for check in section.checks:
            if check.status == STATUS_FAIL and check.importance == REQUIRED:
                evaluation.hard_failures.append(check)
                evaluation.eligible = False

    # A hard-budget breach also excludes the site.
    for result in assessment.budget_results:
        if result.get("behaviour") == BEHAVIOUR_HARD and result.get("status") == "over_budget":
            evaluation.hard_failures.append(
                CheckResult(
                    key=str(result.get("key")),
                    label=str(result.get("label")),
                    status=STATUS_FAIL,
                    importance=REQUIRED,
                    detail=str(result.get("detail")),
                    observed=result.get("observed"),
                    expected=result.get("limit"),
                )
            )
            evaluation.eligible = False

    # --- Fit ratio ---------------------------------------------------
    # Flexible sections are advisory: they are reported but excluded from
    # the ratio so that an accepted shortfall cannot reduce the score.
    # Hard sections that failed have already excluded the site.
    scored_sections = [
        section
        for section in (
            evaluation.parking,
            evaluation.facilities,
            evaluation.business_requirements,
        )
        if section is not None and section.behaviour != BEHAVIOUR_FLEXIBLE
    ]
    fit_ratio = combine_fit_ratio(scored_sections)
    evaluation.fit_ratio = fit_ratio
    evaluation.fit_factor = compute_fit_factor(
        fit_ratio, penalty_rate, BEHAVIOUR_PREFERENCE
    )

    if not evaluation.eligible:
        evaluation.notes.append(
            "This site is excluded because it fails one or more hard requirements."
        )

    unknown_sections = [
        section.section
        for section in (
            evaluation.parking,
            evaluation.facilities,
            evaluation.business_requirements,
        )
        if section is not None and section.required_unknown
    ]
    if unknown_sections:
        evaluation.notes.append(
            "Data is unavailable for parts of: " + ", ".join(unknown_sections) + "."
        )

    return evaluation


__all__ = [
    "BEHAVIOUR_FLEXIBLE",
    "BEHAVIOUR_HARD",
    "BEHAVIOUR_PREFERENCE",
    "CheckResult",
    "DEFAULT_PENALTY_RATE",
    "NOT_IMPORTANT",
    "PREFERRED",
    "REQUIRED",
    "RequirementEvaluation",
    "STATUS_FAIL",
    "STATUS_NOT_APPLICABLE",
    "STATUS_PASS",
    "STATUS_UNKNOWN",
    "STATUS_WARNING",
    "SectionEvaluation",
    "apply_fit_penalty",
    "combine_fit_ratio",
    "compute_fit_factor",
    "evaluate_business_requirements",
    "evaluate_facilities",
    "evaluate_parking",
    "evaluate_site_requirements",
]
