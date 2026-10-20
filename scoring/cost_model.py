"""Cost analysis with explicit provenance for every monetary figure.

Design rules
------------
1. **Nothing is invented.** A cost line only exists when a value is
   available from a real source (a listed rent, a user-provided budget) or
   is a pure arithmetic derivation of such values.  Where a value cannot
   be established the line is reported with the ``unavailable``
   provenance and a ``null`` amount.
2. **Every amount carries its provenance.** The interface must never show
   an estimate as if it were a verified fact.
3. **Incompleteness is explicit.** A total is only reported as an
   *estimated total* when every component of that total is known;
   otherwise the partial figure is labelled as such and the missing
   components are listed.

Provenance values
-----------------
``verified_listed``  the value is published by the source (e.g. a listed
                     monthly rent) and has not been altered.
``user_provided``    the value was entered by the user.
``estimated``        the value is a modelled estimate and must be treated
                     as indicative only.
``calculated``       the value is arithmetic over other known values.
``unavailable``      no defensible value could be established.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

VERIFIED_LISTED = "verified_listed"
USER_PROVIDED = "user_provided"
ESTIMATED = "estimated"
CALCULATED = "calculated"
UNAVAILABLE = "unavailable"

PROVENANCE_LABELS = {
    VERIFIED_LISTED: "Verified / listed",
    USER_PROVIDED: "User provided",
    ESTIMATED: "Estimated",
    CALCULATED: "Calculated",
    UNAVAILABLE: "Unavailable",
}


@dataclass
class CostLine:
    """One monetary line in a cost breakdown."""

    key: str
    label: str
    amount: Optional[float]
    provenance: str
    category: str  # acquisition | setup | recurring
    source: Optional[str] = None
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "amount": self.amount,
            "provenance": self.provenance,
            "provenance_label": PROVENANCE_LABELS.get(self.provenance, self.provenance),
            "category": self.category,
            "source": self.source,
            "note": self.note,
        }


@dataclass
class CostBudget:
    """A user-defined budget and the behaviour applied when it is exceeded."""

    key: str
    label: str
    limit: Optional[float]
    behaviour: str = "penalise"  # penalise | hard
    scope: str = ""  # acquisition | recurring | initial_investment

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "limit": self.limit,
            "behaviour": self.behaviour,
            "scope": self.scope,
        }


@dataclass
class CostAssessment:
    """The result of assessing a site's cost position."""

    site_id: str
    acquisition_mode: str
    lines: list[CostLine] = field(default_factory=list)
    budget_results: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    #: The cost of ownership over the configured horizon.
    cost_of_ownership: Optional[dict[str, Any]] = None

    # --- derived figures ---------------------------------------------
    def _known(self, category: str) -> float:
        return sum(
            line.amount
            for line in self.lines
            if line.category == category
            and line.amount is not None
            and line.provenance != UNAVAILABLE
        )

    def _known_for(self, categories: tuple[str, ...]) -> float:
        return sum(self._known(category) for category in categories)

    def _complete(self, categories: tuple[str, ...]) -> bool:
        return all(
            line.amount is not None
            for line in self.lines
            if line.category in categories
        )

    @property
    def acquisition_total(self) -> Optional[float]:
        if not self._complete(("acquisition",)):
            return None
        return self._known("acquisition")

    @property
    def setup_total(self) -> Optional[float]:
        if not self._complete(("setup",)):
            return None
        return self._known("setup")

    @property
    def monthly_rent(self) -> Optional[float]:
        """The monthly rent, where it is known.

        This is the figure a "monthly rent budget" is compared against.  It
        is separate from the total recurring cost, which also includes
        maintenance, utilities and other recurring expenses.
        """

        for line in self.lines:
            if line.key == "rent_recurring":
                return line.amount
        return None

    @property
    def recurring_monthly_total(self) -> Optional[float]:
        if not self._complete(("recurring",)):
            return None
        return self._known("recurring")

    @property
    def recurring_annual_total(self) -> Optional[float]:
        monthly = self.recurring_monthly_total
        return None if monthly is None else monthly * 12

    @property
    def initial_investment_total(self) -> Optional[float]:
        """Initial investment = acquisition + setup.

        Returns ``None`` when any component is unknown, so the interface
        never presents a partial total as if it were complete.
        """

        acquisition = self.acquisition_total
        setup = self.setup_total
        if acquisition is None or setup is None:
            return None
        return acquisition + setup

    @property
    def known_minimum_initial_investment(self) -> float:
        """Sum of the components that *are* known (never presented as a total)."""

        return self._known("acquisition") + self._known("setup")

    def to_dict(self) -> dict[str, Any]:
        missing = [line.label for line in self.lines if line.amount is None]
        return {
            "site_id": self.site_id,
            "acquisition_mode": self.acquisition_mode,
            "lines": [line.to_dict() for line in self.lines],
            "budget_results": self.budget_results,
            "totals": {
                "acquisition_total": self.acquisition_total,
                "setup_total": self.setup_total,
                "recurring_monthly_total": self.recurring_monthly_total,
                "recurring_annual_total": self.recurring_annual_total,
                "initial_investment_total": self.initial_investment_total,
                "known_minimum_initial_investment": self.known_minimum_initial_investment,
                "is_complete": not missing,
            },
            "missing_components": missing,
            "notes": self.notes,
            "cost_of_ownership": self.cost_of_ownership,
        }


# ---------------------------------------------------------------------------
# Attribute lookup helpers
# ---------------------------------------------------------------------------

def _lookup(attributes: Mapping[str, Any], names: tuple[str, ...]) -> tuple[Optional[Any], Optional[str]]:
    """Return the first present, non-null attribute and its name."""

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


# ---------------------------------------------------------------------------
# Cost assembly
# ---------------------------------------------------------------------------

_ACQUISITION_SOURCES = {
    "purchase_price": (
        "purchase_price",
        "price",
        "sale_price",
        "property_price",
        "asking_price",
    ),
    "rent": ("rent", "monthly_rent", "lease_rent", "rent_per_month"),
    "deposit": (
        "deposit",
        "security_deposit",
        "advance_rent",
        "security_deposit_amount",
    ),
    "brokerage": ("brokerage", "brokerage_fee", "commission", "brokerage_cost"),
    "transaction_costs": (
        "transaction_costs",
        "registration_cost",
        "registration_charges",
        "stamp_duty",
        "transaction_cost",
    ),
    "other_acquisition": ("other_acquisition_costs", "other_costs", "other_acquisition"),
}

_SETUP_SOURCES = {
    "renovation": ("renovation_cost", "fit_out_cost", "interior_cost", "renovation"),
    "equipment": (
        "equipment_cost",
        "furniture_cost",
        "kitchen_equipment_cost",
        "equipment",
    ),
    "signage": ("signage_cost", "signage"),
    "parking_development": (
        "parking_development_cost",
        "parking_cost",
        "parking_development",
    ),
    "utility_setup": (
        "utility_setup_cost",
        "electrical_cost",
        "plumbing_cost",
        "utility_setup",
    ),
    "other_setup": ("other_setup_costs", "other_setup"),
}

_RECURRING_SOURCES = {
    "maintenance": (
        "maintenance_cost",
        "property_maintenance",
        "cam_charges",
        "maintenance",
    ),
    "utilities": (
        "utilities_cost",
        "utility_cost",
        "electricity_cost",
        "utilities",
    ),
    "other_recurring": ("other_recurring_costs", "other_recurring"),
}


def _line(
    key: str,
    label: str,
    category: str,
    attributes: Mapping[str, Any],
    sources: tuple[str, ...],
    user_value: Any = None,
    default: Optional[float] = None,
) -> CostLine:
    """Build a single cost line from site attributes, then user input, then defaults."""

    observed, source_name = _lookup(attributes, sources)
    if observed is not None:
        amount = _as_float(observed)
        if amount is not None:
            return CostLine(
                key=key,
                label=label,
                amount=amount,
                provenance=VERIFIED_LISTED,
                category=category,
                source=source_name,
                note="Published value taken from the site record.",
            )

    if user_value is not None:
        amount = _as_float(user_value)
        if amount is not None:
            return CostLine(
                key=key,
                label=label,
                amount=amount,
                provenance=USER_PROVIDED,
                category=category,
                source="user_input",
                note="Value supplied by the user.",
            )

    if default is not None:
        return CostLine(
            key=key,
            label=label,
            amount=float(default),
            provenance=ESTIMATED,
            category=category,
            source="model_default",
            note="Indicative placeholder. Replace with a quoted figure before commitment.",
        )

    return CostLine(
        key=key,
        label=label,
        amount=None,
        provenance=UNAVAILABLE,
        category=category,
        note="No value could be established from the available data.",
    )


def assess_site_costs(
    site_id: str,
    attributes: Mapping[str, Any],
    acquisition_mode: str = "either",
    financial: Optional[Mapping[str, Any]] = None,
) -> CostAssessment:
    """Assemble the cost position for a single candidate site.

    Args:
        site_id: The site identifier.
        attributes: The site's attribute mapping (may contain listed values).
        acquisition_mode: One of ``buy``, ``lease`` or ``either``.
        financial: The user's financial requirement block.  Recognised keys:
            ``purchase_price``, ``deposit``, ``brokerage``,
            ``transaction_costs``, ``renovation``, ``equipment``,
            ``other_setup_costs``, ``monthly_rent``, ``maintenance``,
            ``utilities``, ``other_recurring_costs``.

    Returns:
        A :class:`CostAssessment` whose every line carries a provenance.
    """

    financial = financial or {}
    assessment = CostAssessment(site_id=site_id, acquisition_mode=acquisition_mode)

    wants_buy = acquisition_mode in {"buy", "either"}
    wants_lease = acquisition_mode in {"lease", "either"}

    # --- Acquisition -------------------------------------------------
    if wants_buy:
        assessment.lines.append(
            _line(
                "purchase_price",
                "Purchase price",
                "acquisition",
                attributes,
                _ACQUISITION_SOURCES["purchase_price"],
                user_value=financial.get("purchase_price"),
            )
        )
    if wants_lease:
        assessment.lines.append(
            _line(
                "deposit",
                "Security deposit",
                "acquisition",
                attributes,
                _ACQUISITION_SOURCES["deposit"],
                user_value=financial.get("deposit"),
            )
        )

    assessment.lines.append(
        _line(
            "brokerage",
            "Brokerage",
            "acquisition",
            attributes,
            _ACQUISITION_SOURCES["brokerage"],
            user_value=financial.get("brokerage"),
        )
    )
    assessment.lines.append(
        _line(
            "transaction_costs",
            "Registration / transaction costs",
            "acquisition",
            attributes,
            _ACQUISITION_SOURCES["transaction_costs"],
            user_value=financial.get("transaction_costs"),
        )
    )
    assessment.lines.append(
        _line(
            "other_acquisition",
            "Other acquisition costs",
            "acquisition",
            attributes,
            _ACQUISITION_SOURCES["other_acquisition"],
            user_value=financial.get("other_acquisition_costs"),
        )
    )

    # --- Setup -------------------------------------------------------
    assessment.lines.append(
        _line(
            "renovation",
            "Renovation / fit-out",
            "setup",
            attributes,
            _SETUP_SOURCES["renovation"],
            user_value=financial.get("renovation"),
        )
    )
    assessment.lines.append(
        _line(
            "equipment",
            "Equipment & furniture",
            "setup",
            attributes,
            _SETUP_SOURCES["equipment"],
            user_value=financial.get("equipment"),
        )
    )
    assessment.lines.append(
        _line(
            "signage",
            "Signage",
            "setup",
            attributes,
            _SETUP_SOURCES["signage"],
            user_value=financial.get("signage"),
        )
    )
    assessment.lines.append(
        _line(
            "parking_development",
            "Parking development",
            "setup",
            attributes,
            _SETUP_SOURCES["parking_development"],
            user_value=financial.get("parking_development"),
        )
    )
    assessment.lines.append(
        _line(
            "utility_setup",
            "Utility setup",
            "setup",
            attributes,
            _SETUP_SOURCES["utility_setup"],
            user_value=financial.get("utility_setup"),
        )
    )
    assessment.lines.append(
        _line(
            "other_setup",
            "Other setup costs",
            "setup",
            attributes,
            _SETUP_SOURCES["other_setup"],
            user_value=financial.get("other_setup_costs"),
        )
    )

    # --- Recurring ---------------------------------------------------
    if wants_lease:
        assessment.lines.append(
            _line(
                "rent_recurring",
                "Rent",
                "recurring",
                attributes,
                _ACQUISITION_SOURCES["rent"],
                user_value=financial.get("monthly_rent"),
            )
        )
    assessment.lines.append(
        _line(
            "maintenance",
            "Maintenance",
            "recurring",
            attributes,
            _RECURRING_SOURCES["maintenance"],
            user_value=financial.get("maintenance"),
        )
    )
    assessment.lines.append(
        _line(
            "utilities",
            "Utilities",
            "recurring",
            attributes,
            _RECURRING_SOURCES["utilities"],
            user_value=financial.get("utilities"),
        )
    )
    assessment.lines.append(
        _line(
            "other_recurring",
            "Other recurring costs",
            "recurring",
            attributes,
            _RECURRING_SOURCES["other_recurring"],
            user_value=financial.get("other_recurring_costs"),
        )
    )

    if not wants_buy and not wants_lease:
        assessment.notes.append(
            "No acquisition mode was selected, so acquisition costs are not assessed."
        )

    return assessment


# ---------------------------------------------------------------------------
# Budget comparison
# ---------------------------------------------------------------------------

def compare_budgets(
    assessment: CostAssessment,
    budgets: list[CostBudget],
) -> list[dict[str, Any]]:
    """Compare a cost assessment against the user's budgets.

    A budget is only reported as breached when the relevant total is fully
    known.  Otherwise the result is ``partially_assessed`` and the missing
    components are named, so the user is never shown a false pass.
    """

    results: list[dict[str, Any]] = []

    for budget in budgets:
        if budget.limit is None:
            results.append(
                {
                    **budget.to_dict(),
                    "status": "not_set",
                    "observed": None,
                    "headroom": None,
                    "detail": "No budget was set for this item.",
                }
            )
            continue

        if budget.scope == "acquisition":
            observed = assessment.acquisition_total
            known = assessment._known_for(("acquisition",))
            complete = observed is not None
        elif budget.scope == "setup":
            observed = assessment.setup_total
            known = assessment._known_for(("setup",))
            complete = observed is not None
        elif budget.scope == "rent":
            observed = assessment.monthly_rent
            known = observed or 0.0
            complete = observed is not None
        elif budget.scope == "recurring_monthly":
            observed = assessment.recurring_monthly_total
            known = assessment._known_for(("recurring",))
            complete = observed is not None
        elif budget.scope == "recurring_annual":
            observed = assessment.recurring_annual_total
            known = assessment._known_for(("recurring",)) * 12
            complete = observed is not None
        elif budget.scope == "initial_investment":
            observed = assessment.initial_investment_total
            known = assessment._known_for(("acquisition", "setup"))
            complete = observed is not None
        else:
            observed = None
            known = 0.0
            complete = False

        # A breach can be *proven* from a lower bound: if the parts that
        # are already known exceed the budget on their own, the site is over
        # budget whatever the unknown components turn out to be.
        if not complete and known > budget.limit:
            results.append(
                {
                    **budget.to_dict(),
                    "status": "over_budget",
                    "observed": None,
                    "known_minimum": known,
                    "headroom": budget.limit - known,
                    "detail": (
                        f"Over budget by at least {known - budget.limit:,.0f} based on the "
                        "components that are known."
                    ),
                }
            )
            continue

        if not complete:
            results.append(
                {
                    **budget.to_dict(),
                    "status": "partially_assessed",
                    "observed": None,
                    "known_minimum": known,
                    "headroom": None,
                    "detail": (
                        "Some cost components are unavailable, so this budget "
                        "could not be assessed in full."
                    ),
                }
            )
            continue

        assert observed is not None
        headroom = budget.limit - observed
        status = "within_budget" if headroom >= 0 else "over_budget"
        results.append(
            {
                **budget.to_dict(),
                "status": status,
                "observed": observed,
                "headroom": headroom,
                "detail": (
                    f"Within budget by {abs(headroom):,.0f}."
                    if headroom >= 0
                    else f"Over budget by {abs(headroom):,.0f}."
                ),
            }
        )

    return results


__all__ = [
    "CALCULATED",
    "CostAssessment",
    "CostBudget",
    "CostLine",
    "ESTIMATED",
    "PROVENANCE_LABELS",
    "UNAVAILABLE",
    "USER_PROVIDED",
    "VERIFIED_LISTED",
    "assess_site_costs",
    "compare_budgets",
]
