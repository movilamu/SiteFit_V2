"""Deterministic explanation of why a site received its ranking.

Every statement produced here is assembled from values that the scoring
engine computed.  No language model is involved, and nothing is asserted
that the underlying data does not support.

The narrative is written in a fixed order:

1. the position (rank and score),
2. the factors that separate it from the site immediately below it,
3. its requirement, parking and facility position,
4. its cost position,
5. the limits of the evidence behind all of the above.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

from scoring.criteria_hierarchy import CRITERIA_TREE, iter_leaves
from scoring.requirement_fit import (
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_UNKNOWN,
    RequirementEvaluation,
)

# --- Label lookups ---------------------------------------------------------

_CATEGORY_LABELS = {
    category.key: category.label for category in CRITERIA_TREE
}

_CRITERION_META: dict[str, dict[str, Any]] = {}
for _category, _, _criterion in iter_leaves(CRITERIA_TREE):
    _CRITERION_META[_criterion.key] = {
        "label": _criterion.label,
        "category": _category.label,
        "direction": _criterion.direction.value if _criterion.direction else None,
    }


def criterion_label(key: str) -> str:
    return _CRITERION_META.get(key, {}).get("label") or key.replace("_", " ").title()


def criterion_category(key: str) -> str:
    return _CRITERION_META.get(key, {}).get("category") or ""


def _format_number(value: float, digits: int = 3) -> str:
    return f"{value:.{digits}f}"


def _format_money(value: Optional[float]) -> str:
    if value is None:
        return "unavailable"
    if abs(value) >= 10_000_000:
        return f"{value / 10_000_000:,.2f} crore"
    if abs(value) >= 100_000:
        return f"{value / 100_000:,.2f} lakh"
    return f"{value:,.0f}"


# ---------------------------------------------------------------------------
# Comparison of two sites
# ---------------------------------------------------------------------------

@dataclass
class FactorComparison:
    """A criterion compared between the focal site and a reference site."""

    criterion: str
    label: str
    category: str
    focal_value: float
    reference_value: Optional[float]
    focal_weight: float
    contribution_delta: float
    direction: Optional[str]

    @property
    def advantage(self) -> float:
        """Positive when the focal site performs better on this criterion."""

        if self.reference_value is None:
            return 0.0
        return self.focal_value - self.reference_value

    def to_dict(self) -> dict[str, Any]:
        return {
            "criterion": self.criterion,
            "label": self.label,
            "category": self.category,
            "focal_value": round(self.focal_value, 6),
            "reference_value": (
                None if self.reference_value is None else round(self.reference_value, 6)
            ),
            "focal_weight": round(self.focal_weight, 6),
            "contribution_delta": round(self.contribution_delta, 6),
            "advantage": round(self.advantage, 6),
            "direction": self.direction,
        }


def compare_criteria(
    focal: Mapping[str, float],
    focal_weights: Mapping[str, float],
    reference: Optional[Mapping[str, float]] = None,
) -> list[FactorComparison]:
    """Compare the focal site's criterion values against a reference site."""

    comparisons: list[FactorComparison] = []

    for criterion, focal_value in focal.items():
        weight = float(focal_weights.get(criterion, 0.0))
        reference_value = (
            float(reference[criterion]) if reference and criterion in reference else None
        )
        meta = _CRITERION_META.get(criterion, {})
        comparisons.append(
            FactorComparison(
                criterion=criterion,
                label=str(meta.get("label") or criterion.replace("_", " ").title()),
                category=str(meta.get("category") or ""),
                focal_value=float(focal_value),
                reference_value=reference_value,
                focal_weight=weight,
                contribution_delta=float(focal_value) * weight
                - (reference_value or 0.0) * weight,
                direction=meta.get("direction"),
            )
        )

    comparisons.sort(key=lambda item: item.contribution_delta, reverse=True)
    return comparisons


# ---------------------------------------------------------------------------
# Narrative composition
# ---------------------------------------------------------------------------

def _describe_requirement_section(
    name: str,
    section: Optional[Mapping[str, Any]],
) -> str:
    if not section:
        return f"No {name} requirements were specified."

    required_total = int(section.get("required_total") or 0)
    required_met = int(section.get("required_met") or 0)
    required_failed = int(section.get("required_failed") or 0)
    preferred_total = int(section.get("preferred_total") or 0)
    preferred_met = int(section.get("preferred_met") or 0)

    if required_total == 0 and preferred_total == 0:
        return f"No {name} requirements were specified."

    parts: list[str] = []
    if required_total:
        if required_failed:
            parts.append(
                f"{required_met} of {required_total} required {name} requirements are met "
                f"and {required_failed} are not"
            )
        else:
            parts.append(
                f"all {required_total} required {name} requirements are met"
            )
    if preferred_total:
        parts.append(
            f"{preferred_met} of {preferred_total} preferred {name} requirements are met"
        )
    return "; ".join(parts) + "."


def _describe_cost(cost: Any) -> str:
    if not cost:
        return "No cost information was available for this site."

    # The requirement evaluation keeps the cost assessment as an object, so
    # that the configured estimation rules can be applied to it before the
    # result is serialised.  The description is written from the
    # serialised form.
    payload = cost.to_dict() if hasattr(cost, "to_dict") else cost
    if not isinstance(payload, Mapping):
        return "No cost information was available for this site."

    totals = payload.get("totals") or {}
    initial = totals.get("initial_investment_total")
    monthly = totals.get("recurring_monthly_total")

    if initial is None and monthly is None:
        missing = payload.get("missing_components") or []
        if missing:
            return (
                "The cost position could not be completed because these "
                "components are unavailable: "
                + ", ".join(missing)
                + "."
            )
        return "Cost information is unavailable for this site."

    parts: list[str] = []
    if initial is not None:
        parts.append(f"the estimated initial investment is {_format_money(initial)}")
    if monthly is not None:
        parts.append(f"the estimated monthly cost is {_format_money(monthly)}")

    sentence = "; ".join(parts).capitalize() if parts else ""
    if sentence:
        sentence += "."

    over_budget = [
        result
        for result in (payload.get("budget_results") or [])
        if result.get("status") == "over_budget"
    ]
    if over_budget:
        labels = ", ".join(str(result.get("label")) for result in over_budget)
        sentence += f" It exceeds the budget set for: {labels}."
    elif any(
        result.get("status") == "within_budget"
        for result in (payload.get("budget_results") or [])
    ):
        sentence += " It is within the budgets that were set."

    return sentence


def build_explanation(
    site_id: str,
    site_name: Optional[str],
    rank: Optional[int],
    total_sites: int,
    base_score: float,
    adjusted_score: Optional[float],
    fit_factor: float,
    focal_criteria: Mapping[str, float],
    focal_weights: Mapping[str, float],
    reference_criteria: Optional[Mapping[str, float]] = None,
    reference_label: Optional[str] = None,
    evaluation: Optional[RequirementEvaluation] = None,
    stability: Optional[Mapping[str, Any]] = None,
    coverage: float = 1.0,
    dropped_criteria: Optional[Sequence[str]] = None,
) -> dict[str, Any]:
    """Assemble the full explanation payload for one site."""

    comparisons = compare_criteria(focal_criteria, focal_weights, reference_criteria)

    strengths = [item for item in comparisons if item.advantage > 0][:4]
    weaknesses = [item for item in comparisons if item.advantage < 0][-4:]
    weaknesses.reverse()

    if reference_criteria is not None and reference_label:
        separating = [item for item in comparisons if abs(item.contribution_delta) > 1e-9]
        separating.sort(key=lambda item: abs(item.contribution_delta), reverse=True)
        top = separating[:3]
        if top:
            drivers = "; ".join(
                f"{item.label.lower()} "
                f"({_format_number(item.focal_value)} vs "
                f"{_format_number(item.reference_value or 0.0)}, "
                f"weight {_format_number(item.focal_weight * 100, 1)}%)"
                for item in top
            )
            comparison_sentence = (
                f"It is separated from {reference_label} mainly by {drivers}."
            )
        else:
            comparison_sentence = (
                f"It scores marginally ahead of {reference_label} on the criteria "
                "that carry the weight."
            )
    else:
        comparison_sentence = ""

    # --- Requirement, parking, facility position ----------------------
    requirement_sentence = ""
    parking_sentence = ""
    facility_sentence = ""
    if evaluation is not None:
        requirement_sentence = _describe_requirement_section(
            "business", evaluation.business_requirements.to_dict()
            if evaluation.business_requirements
            else None
        )
        parking_sentence = _describe_requirement_section(
            "parking", evaluation.parking.to_dict() if evaluation.parking else None
        )
        facility_sentence = _describe_requirement_section(
            "facility", evaluation.facilities.to_dict() if evaluation.facilities else None
        )

    cost_sentence = _describe_cost(evaluation.cost if evaluation else None)

    # --- Headline and summary ----------------------------------------
    label = site_name or f"Site {site_id}"
    if rank and total_sites:
        headline = f"Ranks #{rank} of {total_sites} candidate sites"
    else:
        headline = "Not currently ranked"

    summary_parts: list[str] = []
    summary_parts.append(
        f"{label} has a multi-criteria score of {_format_number(base_score)}."
    )
    if adjusted_score is not None and abs(adjusted_score - base_score) > 1e-9:
        summary_parts.append(
            f"After the requirement penalty it scores {_format_number(adjusted_score)} "
            f"(a fit factor of {_format_number(fit_factor)})."
        )
    if comparison_sentence:
        summary_parts.append(comparison_sentence)
    if requirement_sentence:
        summary_parts.append(requirement_sentence)
    if parking_sentence:
        summary_parts.append(parking_sentence)
    if facility_sentence:
        summary_parts.append(facility_sentence)
    if cost_sentence:
        summary_parts.append(cost_sentence)

    summary = " ".join(summary_parts)

    # --- Evidence and caveats -----------------------------------------
    caveats: list[str] = []
    if coverage < 0.999:
        caveats.append(
            f"Only {coverage * 100:.0f}% of the requested criterion weight could be "
            "scored with the current data release."
        )
    if dropped_criteria:
        caveats.append(
            "These criteria had no data and did not contribute to the score: "
            + ", ".join(criterion_label(key) for key in list(dropped_criteria)[:6])
            + ("." if len(dropped_criteria) <= 6 else ".")
        )
    if stability is not None:
        stability_percentage = stability.get("stability_percentage")
        if isinstance(stability_percentage, (int, float)):
            if stability_percentage >= 90:
                caveats.append(
                    f"The ranking is stable: it holds under {stability_percentage:.0f}% "
                    "of the weight perturbations tested."
                )
            elif stability_percentage >= 60:
                caveats.append(
                    f"The ranking is moderately sensitive: it holds under "
                    f"{stability_percentage:.0f}% of the weight perturbations tested."
                )
            else:
                caveats.append(
                    f"High sensitivity: the ranking holds under only "
                    f"{stability_percentage:.0f}% of the weight perturbations tested."
                )

    caveats.append(
        "Scores express relative fit against the stated weights and requirements. "
        "They are not a forecast of trading performance."
    )

    return {
        "site_id": site_id,
        "site_name": site_name,
        "headline": headline,
        "rank": rank,
        "total_sites": total_sites,
        "base_score": round(base_score, 6),
        "adjusted_score": None if adjusted_score is None else round(adjusted_score, 6),
        "fit_factor": round(fit_factor, 6),
        "summary": summary,
        "comparison_sentence": comparison_sentence,
        "strengths": [item.to_dict() for item in strengths],
        "weaknesses": [item.to_dict() for item in weaknesses],
        "requirements": {
            "business": requirement_sentence,
            "parking": parking_sentence,
            "facilities": facility_sentence,
        },
        "cost": cost_sentence,
        "caveats": caveats,
        "coverage": round(coverage, 6),
        "dropped_criteria": list(dropped_criteria or []),
    }


__all__ = [
    "FactorComparison",
    "build_explanation",
    "compare_criteria",
    "criterion_category",
    "criterion_label",
]
