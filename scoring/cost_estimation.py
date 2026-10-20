"""Cost estimation rules and total cost of ownership.

Estimation is **opt-in and always visible**.  Nothing is estimated by
default; when the operator enables estimation, the rules are applied only
to components that are genuinely unknown, every estimated line records
the rule that produced it, and the line is labelled ``ESTIMATED`` so the
interface can never present it as a source fact.

The default rules are deliberately conservative and are documented so that
a reviewer can see exactly what an estimated figure means:

``brokerage_percent``
    A percentage of the purchase price.  Applies only to a purchase, and
    only when the purchase price itself is known.

``registration_percent``
    A percentage of the purchase price covering the registration and
    transaction charges that apply to a purchase.

``setup_percent_of_rent``
    A multiple of the monthly rent, used to estimate the fit-out and setup
    cost of a leased site when no figure is available.

``maintenance_percent_of_rent``
    A multiple of the monthly rent, used to estimate the recurring
    maintenance of a leased site when no figure is available.

Every rule can be set to zero, which disables it.  The total cost of
ownership is then simply the sum of what is known.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from scoring.cost_model import ESTIMATED, CostAssessment, CostLine


@dataclass(frozen=True)
class EstimationRules:
    """The configurable rules used to estimate unknown cost components."""

    enabled: bool = False
    brokerage_percent: float = 2.0
    registration_percent: float = 5.0
    setup_multiple_of_rent: float = 1.5
    maintenance_multiple_of_rent: float = 0.10

    def describe(self) -> list[dict[str, Any]]:
        """Describe each active rule, so the interface can show the method."""

        if not self.enabled:
            return []

        rules: list[dict[str, Any]] = []
        if self.brokerage_percent > 0:
            rules.append(
                {
                    "key": "brokerage_percent",
                    "label": "Brokerage",
                    "method": (
                        f"{self.brokerage_percent:g}% of the purchase price"
                    ),
                }
            )
        if self.registration_percent > 0:
            rules.append(
                {
                    "key": "registration_percent",
                    "label": "Registration and transaction costs",
                    "method": (
                        f"{self.registration_percent:g}% of the purchase price"
                    ),
                }
            )
        if self.setup_multiple_of_rent > 0:
            rules.append(
                {
                    "key": "setup_multiple_of_rent",
                    "label": "Fit-out and setup",
                    "method": (
                        f"{self.setup_multiple_of_rent:g} times the monthly rent"
                    ),
                }
            )
        if self.maintenance_multiple_of_rent > 0:
            rules.append(
                {
                    "key": "maintenance_multiple_of_rent",
                    "label": "Recurring maintenance",
                    "method": (
                        f"{self.maintenance_multiple_of_rent:g} times the monthly rent"
                    ),
                }
            )
        return rules


def _find(assessment: CostAssessment, key: str) -> Optional[CostLine]:
    for line in assessment.lines:
        if line.key == key:
            return line
    return None


def _known_amount(assessment: CostAssessment, key: str) -> Optional[float]:
    line = _find(assessment, key)
    if line is None or line.amount is None:
        return None
    return float(line.amount)


def apply_estimations(
    assessment: CostAssessment,
    rules: EstimationRules,
) -> CostAssessment:
    """Fill unknown cost components using the configured rules.

    The assessment is returned with additional lines whose provenance is
    ``ESTIMATED`` and whose note records the rule that produced them.
    Components that are already known are never overwritten.
    """

    if not rules.enabled:
        return assessment

    purchase_price = _known_amount(assessment, "purchase_price")
    monthly_rent = _known_amount(assessment, "rent_recurring")

    if purchase_price is not None:
        if (
            rules.brokerage_percent > 0
            and _known_amount(assessment, "brokerage") is None
        ):
            assessment.lines.append(
                CostLine(
                    key="brokerage",
                    label="Brokerage",
                    amount=round(purchase_price * rules.brokerage_percent / 100.0, 2),
                    provenance=ESTIMATED,
                    category="acquisition",
                    source="cost_estimation_rules",
                    note=(
                        f"Estimated at {rules.brokerage_percent:g}% of the purchase "
                        "price. Replace with a quoted figure before commitment."
                    ),
                )
            )
        if (
            rules.registration_percent > 0
            and _known_amount(assessment, "transaction_costs") is None
        ):
            assessment.lines.append(
                CostLine(
                    key="transaction_costs",
                    label="Registration and transaction costs",
                    amount=round(
                        purchase_price * rules.registration_percent / 100.0, 2
                    ),
                    provenance=ESTIMATED,
                    category="acquisition",
                    source="cost_estimation_rules",
                    note=(
                        f"Estimated at {rules.registration_percent:g}% of the purchase "
                        "price. Replace with a quoted figure before commitment."
                    ),
                )
            )

    if monthly_rent is not None:
        if (
            rules.setup_multiple_of_rent > 0
            and _known_amount(assessment, "renovation") is None
        ):
            assessment.lines.append(
                CostLine(
                    key="renovation",
                    label="Renovation and fit-out",
                    amount=round(
                        monthly_rent * rules.setup_multiple_of_rent, 2
                    ),
                    provenance=ESTIMATED,
                    category="setup",
                    source="cost_estimation_rules",
                    note=(
                        f"Estimated at {rules.setup_multiple_of_rent:g} times the "
                        "monthly rent. Replace with a quoted figure before "
                        "commitment."
                    ),
                )
            )
        if (
            rules.maintenance_multiple_of_rent > 0
            and _known_amount(assessment, "maintenance") is None
        ):
            assessment.lines.append(
                CostLine(
                    key="maintenance",
                    label="Maintenance",
                    amount=round(
                        monthly_rent * rules.maintenance_multiple_of_rent, 2
                    ),
                    provenance=ESTIMATED,
                    category="recurring",
                    source="cost_estimation_rules",
                    note=(
                        f"Estimated at {rules.maintenance_multiple_of_rent:g} times "
                        "the monthly rent. Replace with a quoted figure before "
                        "commitment."
                    ),
                )
            )

    return assessment


def total_cost_of_ownership(
    assessment: CostAssessment,
    horizon_months: int = 60,
) -> dict[str, Any]:
    """Return the total cost of ownership over a period.

    The total is only reported when both the initial investment and the
    monthly recurring cost are known.  Otherwise the known part is reported
    as a minimum and the missing components are named.
    """

    months = max(1, int(horizon_months))
    initial = assessment.initial_investment_total
    monthly = assessment.recurring_monthly_total

    if initial is None or monthly is None:
        known = assessment.known_minimum_initial_investment
        if monthly is not None:
            known += monthly * months
        return {
            "horizon_months": months,
            "total_cost_of_ownership": None,
            "known_minimum": round(known, 2),
            "initial_investment": initial,
            "recurring_total": None if monthly is None else round(monthly * months, 2),
            "is_complete": False,
            "missing": [
                label
                for label, value in (
                    ("initial investment", initial),
                    ("recurring cost", monthly),
                )
                if value is None
            ],
        }

    return {
        "horizon_months": months,
        "total_cost_of_ownership": round(initial + monthly * months, 2),
        "known_minimum": round(initial + monthly * months, 2),
        "initial_investment": initial,
        "recurring_total": round(monthly * months, 2),
        "is_complete": True,
        "missing": [],
    }


__all__ = [
    "EstimationRules",
    "apply_estimations",
    "total_cost_of_ownership",
]
