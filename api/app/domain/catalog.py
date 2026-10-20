"""Configurable catalogue of business types, business requirements and facilities.

The catalogue is *configuration*, not scoring logic.  It defines:

* which business/site types a user can choose from,
* which business-specific requirements apply to each type,
* whether each requirement is REQUIRED, PREFERRED or NOT IMPORTANT for that
  type, and
* the standard facility list.

No importance weight is embedded here and nothing in this module influences
a site score.  A requirement only ever acts as a **filter** (hard
requirement) or a **penalty** (preference), both of which are applied
deterministically in :mod:`scoring.requirement_fit`.

The catalogue is deliberately moderate in size: a user should be able to
scan it in under a minute.  Anything genuinely bespoke belongs in the
"Other / custom type" path, where the user defines their own requirements.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Importance levels
# ---------------------------------------------------------------------------

REQUIRED = "required"
PREFERRED = "preferred"
NOT_IMPORTANT = "not_important"

IMPORTANCE_LEVELS = (REQUIRED, PREFERRED, NOT_IMPORTANT)

# ---------------------------------------------------------------------------
# Constraint behaviours
# ---------------------------------------------------------------------------

BEHAVIOUR_HARD = "hard"
BEHAVIOUR_PREFERENCE = "preference"
BEHAVIOUR_FLEXIBLE = "flexible"

CONSTRAINT_BEHAVIOURS = (BEHAVIOUR_HARD, BEHAVIOUR_PREFERENCE, BEHAVIOUR_FLEXIBLE)

# Acquisition modes
ACQUISITION_BUY = "buy"
ACQUISITION_LEASE = "lease"
ACQUISITION_EITHER = "either"

ACQUISITION_MODES = (ACQUISITION_BUY, ACQUISITION_LEASE, ACQUISITION_EITHER)


@dataclass(frozen=True)
class RequirementDefinition:
    """A business-specific requirement the user can be asked about."""

    key: str
    label: str
    value_type: str = "number"  # number | boolean | select
    unit: str = ""
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    options: tuple[str, ...] = ()
    default: Any = None
    help_text: str = ""
    #: Attribute names on a candidate site that can satisfy this requirement.
    site_attributes: tuple[str, ...] = ()


@dataclass(frozen=True)
class BusinessType:
    """A business / site type and its default requirement profile."""

    key: str
    label: str
    description: str = ""
    acquisition_modes: tuple[str, ...] = ACQUISITION_MODES
    #: requirement key -> importance for this business type
    requirements: dict[str, str] = field(default_factory=dict)
    #: Facilities that are typically required for this business type.
    required_facilities: tuple[str, ...] = ()
    preferred_facilities: tuple[str, ...] = ()
    typical_unit_size_sqft: tuple[int, int] = (0, 0)
    default_business_type: bool = False


# ---------------------------------------------------------------------------
# Business-specific requirement definitions
# ---------------------------------------------------------------------------

REQUIREMENT_DEFINITIONS: tuple[RequirementDefinition, ...] = (
    RequirementDefinition(
        key="seating_capacity",
        label="Seating capacity",
        unit="covers",
        minimum=0,
        default=40,
        site_attributes=("seating_capacity", "seats"),
    ),
    RequirementDefinition(
        key="kitchen_required",
        label="Kitchen required",
        value_type="boolean",
        default=True,
        site_attributes=("kitchen", "has_kitchen"),
    ),
    RequirementDefinition(
        key="service_counter",
        label="Service counter / billing area",
        value_type="boolean",
        default=True,
        site_attributes=("service_counter",),
    ),
    RequirementDefinition(
        key="storage_area_sqft",
        label="Storage area",
        unit="sq ft",
        minimum=0,
        default=500,
        site_attributes=("storage_area_sqft", "storage_area"),
    ),
    RequirementDefinition(
        key="warehouse_area_sqft",
        label="Warehouse area",
        unit="sq ft",
        minimum=0,
        default=2000,
        site_attributes=("warehouse_area_sqft", "warehouse_area"),
    ),
    RequirementDefinition(
        key="loading_unloading",
        label="Loading / unloading access",
        value_type="boolean",
        default=True,
        site_attributes=("loading_unloading", "loading_dock"),
    ),
    RequirementDefinition(
        key="vehicle_access",
        label="Vehicle access for deliveries",
        value_type="boolean",
        default=True,
        site_attributes=("vehicle_access",),
    ),
    RequirementDefinition(
        key="road_frontage_m",
        label="Road frontage",
        unit="m",
        minimum=0,
        default=10,
        site_attributes=("road_frontage_m", "frontage_meters", "frontage"),
    ),
    RequirementDefinition(
        key="visibility",
        label="Visibility from the main road",
        value_type="select",
        options=("high", "medium", "low"),
        default="medium",
        site_attributes=("visibility", "visibility_score"),
    ),
    RequirementDefinition(
        key="evening_accessibility",
        label="Accessible during evening trading hours",
        value_type="boolean",
        default=True,
        site_attributes=("evening_accessibility",),
    ),
    RequirementDefinition(
        key="power_capacity_kw",
        label="Power capacity",
        unit="kW",
        minimum=0,
        default=50,
        site_attributes=("power_capacity_kw", "power_capacity"),
    ),
    RequirementDefinition(
        key="water_supply",
        label="Water supply",
        value_type="boolean",
        default=True,
        site_attributes=("water_supply", "has_water"),
    ),
    RequirementDefinition(
        key="delivery_access",
        label="Delivery access / drop-off point",
        value_type="boolean",
        default=True,
        site_attributes=("delivery_access",),
    ),
    RequirementDefinition(
        key="cold_storage",
        label="Cold storage",
        value_type="boolean",
        default=False,
        site_attributes=("cold_storage",),
    ),
    RequirementDefinition(
        key="fitting_rooms",
        label="Fitting rooms",
        value_type="boolean",
        default=True,
        site_attributes=("fitting_rooms",),
    ),
    RequirementDefinition(
        key="display_area_sqft",
        label="Front-of-house display area",
        unit="sq ft",
        minimum=0,
        default=600,
        site_attributes=("display_area_sqft", "display_area"),
    ),
    RequirementDefinition(
        key="vault_security",
        label="High-security vault",
        value_type="boolean",
        default=True,
        site_attributes=("vault_security", "vault"),
    ),
    RequirementDefinition(
        key="prescription_storage",
        label="Prescription storage",
        value_type="boolean",
        default=True,
        site_attributes=("prescription_storage",),
    ),
    RequirementDefinition(
        key="stock_display",
        label="Stock display area",
        value_type="boolean",
        default=True,
        site_attributes=("stock_display",),
    ),
    RequirementDefinition(
        key="floor_load_kg_m2",
        label="Floor load capacity",
        unit="kg/mÂ²",
        minimum=0,
        default=1000,
        site_attributes=("floor_load_kg_m2", "floor_load"),
    ),
    RequirementDefinition(
        key="escalator_access",
        label="Escalator / lift access to the trading floor",
        value_type="boolean",
        default=False,
        site_attributes=("escalator_access", "lift"),
    ),
)

REQUIREMENT_BY_KEY = {definition.key: definition for definition in REQUIREMENT_DEFINITIONS}


# ---------------------------------------------------------------------------
# Facility definitions
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FacilityDefinition:
    key: str
    label: str
    category: str
    site_attributes: tuple[str, ...] = ()


FACILITY_DEFINITIONS: tuple[FacilityDefinition, ...] = (
    FacilityDefinition("parking", "Parking", "site", ("parking", "parking_capacity", "has_parking")),
    FacilityDefinition("loading_unloading", "Loading / unloading", "operations", ("loading_unloading", "loading_dock")),
    FacilityDefinition("storage", "Storage", "operations", ("storage", "storage_area_sqft")),
    FacilityDefinition("warehouse", "Warehouse", "operations", ("warehouse", "warehouse_area_sqft")),
    FacilityDefinition("kitchen", "Kitchen", "fit-out", ("kitchen", "has_kitchen")),
    FacilityDefinition("washrooms", "Washrooms", "fit-out", ("washrooms", "has_washrooms")),
    FacilityDefinition("power_supply", "Power supply", "utilities", ("power_supply", "power_capacity_kw")),
    FacilityDefinition("backup_power", "Backup power", "utilities", ("backup_power", "has_backup_power")),
    FacilityDefinition("water_supply", "Water supply", "utilities", ("water_supply", "has_water")),
    FacilityDefinition("air_conditioning", "Air conditioning", "fit-out", ("air_conditioning", "has_ac")),
    FacilityDefinition("lift", "Lift", "access", ("lift", "has_lift")),
    FacilityDefinition("fire_safety", "Fire safety compliance", "compliance", ("fire_safety", "fire_safety_compliant")),
    FacilityDefinition("security", "Security", "compliance", ("security", "has_security")),
    FacilityDefinition("signage", "Signage rights", "site", ("signage", "signage_rights")),
    FacilityDefinition("road_frontage", "Road frontage", "site", ("road_frontage", "frontage_meters", "frontage")),
    FacilityDefinition("internet_connectivity", "Internet connectivity", "utilities", ("internet_connectivity", "internet_available")),
    FacilityDefinition("waste_management", "Waste management", "operations", ("waste_management", "has_waste_management")),
    FacilityDefinition("public_transport_access", "Public transport access", "access", ("public_transport_access", "transit_access")),
)

FACILITY_BY_KEY = {definition.key: definition for definition in FACILITY_DEFINITIONS}


# ---------------------------------------------------------------------------
# Business types
# ---------------------------------------------------------------------------

def _profile(**importance: str) -> dict[str, str]:
    return {key: value for key, value in importance.items() if value in IMPORTANCE_LEVELS}


BUSINESS_TYPES: tuple[BusinessType, ...] = (
    BusinessType(
        key="restaurant",
        label="Restaurant",
        description="Full-service or casual dining venue.",
        requirements=_profile(
            seating_capacity=REQUIRED,
            kitchen_required=REQUIRED,
            service_counter=REQUIRED,
            storage_area_sqft=PREFERRED,
            loading_unloading=PREFERRED,
            road_frontage_m=REQUIRED,
            visibility=PREFERRED,
            evening_accessibility=REQUIRED,
            power_capacity_kw=REQUIRED,
            water_supply=REQUIRED,
            delivery_access=PREFERRED,
            vehicle_access=NOT_IMPORTANT,
        ),
        required_facilities=("kitchen", "washrooms", "power_supply", "water_supply", "fire_safety"),
        preferred_facilities=("parking", "air_conditioning", "signage", "public_transport_access", "waste_management"),
        typical_unit_size_sqft=(1500, 5000),
    ),
    BusinessType(
        key="cafe",
        label="CafÃ© / Coffee Shop",
        description="CafÃ©, coffee bar or quick-service beverage outlet.",
        requirements=_profile(
            seating_capacity=PREFERRED,
            kitchen_required=REQUIRED,
            service_counter=REQUIRED,
            storage_area_sqft=PREFERRED,
            road_frontage_m=REQUIRED,
            visibility=REQUIRED,
            evening_accessibility=PREFERRED,
            power_capacity_kw=PREFERRED,
            water_supply=REQUIRED,
            delivery_access=PREFERRED,
        ),
        required_facilities=("kitchen", "washrooms", "power_supply", "water_supply"),
        preferred_facilities=("parking", "air_conditioning", "internet_connectivity", "public_transport_access"),
        typical_unit_size_sqft=(400, 1800),
    ),
    BusinessType(
        key="supermarket",
        label="Supermarket / Hypermarket",
        description="Full-line grocery retail.",
        requirements=_profile(
            storage_area_sqft=REQUIRED,
            warehouse_area_sqft=REQUIRED,
            loading_unloading=REQUIRED,
            vehicle_access=REQUIRED,
            road_frontage_m=REQUIRED,
            visibility=REQUIRED,
            power_capacity_kw=REQUIRED,
            water_supply=REQUIRED,
            cold_storage=REQUIRED,
            stock_display=REQUIRED,
            parking=REQUIRED,
        ),
        required_facilities=("parking", "loading_unloading", "storage", "warehouse", "power_supply", "water_supply", "fire_safety"),
        preferred_facilities=("air_conditioning", "waste_management", "public_transport_access", "security"),
        typical_unit_size_sqft=(5000, 40000),
    ),
    BusinessType(
        key="hardware",
        label="Hardware / Building Materials",
        description="Hardware, building materials and trade supply.",
        requirements=_profile(
            storage_area_sqft=REQUIRED,
            warehouse_area_sqft=REQUIRED,
            loading_unloading=REQUIRED,
            vehicle_access=REQUIRED,
            road_frontage_m=REQUIRED,
            floor_load_kg_m2=REQUIRED,
            power_capacity_kw=PREFERRED,
            visibility=PREFERRED,
        ),
        required_facilities=("loading_unloading", "storage", "warehouse", "parking", "road_frontage"),
        preferred_facilities=("power_supply", "security", "waste_management"),
        typical_unit_size_sqft=(3000, 30000),
    ),
    BusinessType(
        key="pharmacy",
        label="Pharmacy",
        description="Retail pharmacy or chemist counter.",
        requirements=_profile(
            service_counter=REQUIRED,
            storage_area_sqft=REQUIRED,
            prescription_storage=REQUIRED,
            road_frontage_m=REQUIRED,
            visibility=REQUIRED,
            power_capacity_kw=REQUIRED,
            water_supply=PREFERRED,
        ),
        required_facilities=("power_supply", "washrooms", "fire_safety", "air_conditioning"),
        preferred_facilities=("parking", "security", "signage", "public_transport_access"),
        typical_unit_size_sqft=(400, 1800),
    ),
    BusinessType(
        key="electronics",
        label="Electronics Retail",
        description="Consumer electronics and appliance retail.",
        requirements=_profile(
            display_area_sqft=REQUIRED,
            storage_area_sqft=REQUIRED,
            power_capacity_kw=REQUIRED,
            road_frontage_m=REQUIRED,
            visibility=REQUIRED,
        ),
        required_facilities=("power_supply", "air_conditioning", "security", "fire_safety"),
        preferred_facilities=("parking", "signage", "internet_connectivity", "public_transport_access"),
        typical_unit_size_sqft=(800, 4000),
    ),
    BusinessType(
        key="clothing",
        label="Apparel / Clothing",
        description="Fashion, apparel and footwear retail.",
        requirements=_profile(
            display_area_sqft=REQUIRED,
            storage_area_sqft=REQUIRED,
            fitting_rooms=REQUIRED,
            road_frontage_m=REQUIRED,
            visibility=REQUIRED,
            air_conditioning=REQUIRED,
        ),
        required_facilities=("air_conditioning", "power_supply", "washrooms", "fire_safety"),
        preferred_facilities=("parking", "signage", "public_transport_access", "internet_connectivity"),
        typical_unit_size_sqft=(800, 4000),
    ),
    BusinessType(
        key="furniture",
        label="Furniture / Home Furnishing",
        description="Furniture, home dÃ©cor and furnishings retail.",
        requirements=_profile(
            display_area_sqft=REQUIRED,
            storage_area_sqft=REQUIRED,
            warehouse_area_sqft=REQUIRED,
            loading_unloading=REQUIRED,
            road_frontage_m=REQUIRED,
            vehicle_access=PREFERRED,
            visibility=PREFERRED,
        ),
        required_facilities=("storage", "loading_unloading", "power_supply", "parking"),
        preferred_facilities=("air_conditioning", "signage", "security", "waste_management"),
        typical_unit_size_sqft=(2000, 15000),
    ),
    BusinessType(
        key="jewellery",
        label="Jewellery",
        description="Jewellery, gem or watch retail with high-value stock.",
        requirements=_profile(
            display_area_sqft=REQUIRED,
            storage_area_sqft=REQUIRED,
            vault_security=REQUIRED,
            security=REQUIRED,
            road_frontage_m=REQUIRED,
            visibility=REQUIRED,
        ),
        required_facilities=("security", "power_supply", "air_conditioning", "fire_safety"),
        preferred_facilities=("parking", "lift", "signage", "public_transport_access"),
        typical_unit_size_sqft=(600, 3000),
    ),
    BusinessType(
        key="convenience",
        label="Convenience / General Retail",
        description="Neighbourhood convenience store or general retail.",
        requirements=_profile(
            storage_area_sqft=REQUIRED,
            service_counter=REQUIRED,
            road_frontage_m=REQUIRED,
            visibility=REQUIRED,
            power_capacity_kw=REQUIRED,
        ),
        required_facilities=("power_supply", "fire_safety", "washrooms"),
        preferred_facilities=("parking", "signage", "air_conditioning", "public_transport_access"),
        typical_unit_size_sqft=(300, 1500),
    ),
    BusinessType(
        key="speciality_food",
        label="Speciality Food & Beverage",
        description="Speciality grocery, deli or food retail.",
        requirements=_profile(
            storage_area_sqft=REQUIRED,
            cold_storage=REQUIRED,
            service_counter=REQUIRED,
            water_supply=REQUIRED,
            road_frontage_m=REQUIRED,
            power_capacity_kw=REQUIRED,
        ),
        required_facilities=("power_supply", "water_supply", "washrooms", "waste_management"),
        preferred_facilities=("parking", "air_conditioning", "public_transport_access"),
        typical_unit_size_sqft=(600, 3000),
    ),
    BusinessType(
        key="beauty",
        label="Beauty & Personal Care",
        description="Beauty, cosmetics and personal-care retail.",
        requirements=_profile(
            display_area_sqft=REQUIRED,
            storage_area_sqft=REQUIRED,
            road_frontage_m=REQUIRED,
            visibility=REQUIRED,
            air_conditioning=PREFERRED,
        ),
        required_facilities=("air_conditioning", "power_supply", "washrooms"),
        preferred_facilities=("parking", "signage", "public_transport_access"),
        typical_unit_size_sqft=(400, 2000),
    ),
    BusinessType(
        key="bank_branch",
        label="Bank Branch",
        description="Retail banking branch.",
        requirements=_profile(
            service_counter=REQUIRED,
            storage_area_sqft=REQUIRED,
            vault_security=REQUIRED,
            security=REQUIRED,
            road_frontage_m=REQUIRED,
            visibility=REQUIRED,
            power_capacity_kw=REQUIRED,
        ),
        required_facilities=("security", "power_supply", "air_conditioning", "fire_safety", "lift"),
        preferred_facilities=("parking", "public_transport_access", "backup_power"),
        typical_unit_size_sqft=(800, 3000),
    ),
    BusinessType(
        key="commercial",
        label="Commercial / Office",
        description="Office or commercial lease rather than consumer retail.",
        requirements=_profile(
            storage_area_sqft=PREFERRED,
            road_frontage_m=PREFERRED,
            power_capacity_kw=REQUIRED,
            visibility=PREFERRED,
        ),
        required_facilities=("power_supply", "fire_safety", "washrooms"),
        preferred_facilities=("lift", "air_conditioning", "internet_connectivity", "parking", "backup_power"),
        typical_unit_size_sqft=(1000, 20000),
    ),
    BusinessType(
        key="other",
        label="Other / Custom",
        description="A business type not covered above. Define your own requirements.",
        requirements={},
        required_facilities=(),
        preferred_facilities=(),
        typical_unit_size_sqft=(0, 0),
        default_business_type=True,
    ),
)

BUSINESS_TYPE_BY_KEY = {business_type.key: business_type for business_type in BUSINESS_TYPES}


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def requirement_catalog() -> list[dict[str, Any]]:
    """Return the business-requirement definitions as plain data."""

    return [
        {
            "key": definition.key,
            "label": definition.label,
            "value_type": definition.value_type,
            "unit": definition.unit,
            "minimum": definition.minimum,
            "maximum": definition.maximum,
            "options": list(definition.options),
            "default": definition.default,
            "help_text": definition.help_text,
            "site_attributes": list(definition.site_attributes),
        }
        for definition in REQUIREMENT_DEFINITIONS
    ]


def facility_catalog() -> list[dict[str, Any]]:
    """Return the standard facility list as plain data."""

    return [
        {
            "key": definition.key,
            "label": definition.label,
            "category": definition.category,
            "site_attributes": list(definition.site_attributes),
        }
        for definition in FACILITY_DEFINITIONS
    ]


def business_type_catalog() -> list[dict[str, Any]]:
    """Return the business-type list with its requirement profile."""

    payload: list[dict[str, Any]] = []
    for business_type in BUSINESS_TYPES:
        payload.append(
            {
                "key": business_type.key,
                "label": business_type.label,
                "description": business_type.description,
                "acquisition_modes": list(business_type.acquisition_modes),
                "requirements": dict(business_type.requirements),
                "required_facilities": list(business_type.required_facilities),
                "preferred_facilities": list(business_type.preferred_facilities),
                "typical_unit_size_sqft": list(business_type.typical_unit_size_sqft),
                "is_custom": business_type.key == "other",
            }
        )
    return payload


def requirements_for_business_type(business_type_key: str) -> list[dict[str, Any]]:
    """Return the requirement profile for one business type.

    Each entry carries the importance level, the definition and the
    default value, so the interface can render the form without duplicating
    catalogue logic.
    """

    business_type = BUSINESS_TYPE_BY_KEY.get(business_type_key)
    if business_type is None:
        return []

    entries: list[dict[str, Any]] = []
    for key, importance in business_type.requirements.items():
        definition = REQUIREMENT_BY_KEY.get(key)
        if definition is None:
            continue
        entries.append(
            {
                "key": definition.key,
                "label": definition.label,
                "importance": importance,
                "value_type": definition.value_type,
                "unit": definition.unit,
                "minimum": definition.minimum,
                "maximum": definition.maximum,
                "options": list(definition.options),
                "default": definition.default,
                "help_text": definition.help_text,
            }
        )
    return entries


__all__ = [
    "ACQUISITION_BUY",
    "ACQUISITION_EITHER",
    "ACQUISITION_LEASE",
    "ACQUISITION_MODES",
    "BEHAVIOUR_FLEXIBLE",
    "BEHAVIOUR_HARD",
    "BEHAVIOUR_PREFERENCE",
    "BUSINESS_TYPES",
    "BUSINESS_TYPE_BY_KEY",
    "CONSTRAINT_BEHAVIOURS",
    "FACILITY_BY_KEY",
    "FACILITY_DEFINITIONS",
    "IMPORTANCE_LEVELS",
    "NOT_IMPORTANT",
    "PREFERRED",
    "REQUIRED",
    "REQUIREMENT_BY_KEY",
    "REQUIREMENT_DEFINITIONS",
    "business_type_catalog",
    "facility_catalog",
    "requirement_catalog",
    "requirements_for_business_type",
]

