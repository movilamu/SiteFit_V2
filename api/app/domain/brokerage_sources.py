"""Brokerage and agency intelligence.

Brokerage discovery uses the same source-adapter architecture as property
discovery: each source operates independently, a failing source degrades to
a reported status, and nothing is ever fabricated.

Two kinds of source are supported.

**Automated sources** retrieve what is genuinely published.  The built-in
adapter reads the operator and agency tags recorded in OpenStreetMap
around a recommended location.  That is map data, not a broker directory,
and it is labelled as such.

**Manual sources** are portals that cannot be queried automatically --
either because they publish no API, or because automating them would breach
their terms.  For these the platform provides a direct search link so a
user can look for an agent themselves, rather than pretending it looked.

Source status vocabulary
------------------------
``live_source``          the source was queried successfully in this request.
``recently_retrieved``    the source was queried successfully recently and
                          the result is being reused.
``source_date_available`` the listing carries a publication or listing date.
``source_date_unknown``   the listing carries no date.
``unavailable``           the source could not be reached or produced nothing.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Protocol

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# --- Source status vocabulary ---------------------------------------------

STATUS_LIVE = "live_source"
STATUS_RECENT = "recently_retrieved"
STATUS_DATE_AVAILABLE = "source_date_available"
STATUS_DATE_UNKNOWN = "source_date_unknown"
STATUS_UNAVAILABLE = "unavailable"

STATUS_LABELS = {
    STATUS_LIVE: "Live source",
    STATUS_RECENT: "Recently retrieved",
    STATUS_DATE_AVAILABLE: "Source date available",
    STATUS_DATE_UNKNOWN: "Source date unknown",
    STATUS_UNAVAILABLE: "Unavailable",
}

#: How long an automated result is considered fresh.
RESULT_TTL = timedelta(minutes=30)

EARTH_RADIUS_M = 6371000.0


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


# ---------------------------------------------------------------------------
# The result model
# ---------------------------------------------------------------------------

@dataclass
class BrokerageOpportunity:
    """An agency or operator found near a recommended location."""

    source_key: str
    source_label: str
    publisher: str
    name: str
    service_area: str = ""
    website: str = ""
    phone: str = ""
    email: str = ""
    source_url: str = ""
    listing_count: int = 0
    distance_m: Optional[float] = None
    retrieved_at: str = ""
    source_date: Optional[str] = None
    source_status: str = STATUS_LIVE
    kind: str = "automated"  # automated | manual
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_key": self.source_key,
            "source_label": self.source_label,
            "publisher": self.publisher,
            "name": self.name,
            "service_area": self.service_area,
            "website": self.website,
            "phone": self.phone,
            "email": self.email,
            "source_url": self.source_url,
            "listing_count": self.listing_count,
            "distance_m": (
                round(self.distance_m, 1) if self.distance_m is not None else None
            ),
            "retrieved_at": self.retrieved_at,
            "source_date": self.source_date,
            "source_status": self.source_status,
            "source_status_label": STATUS_LABELS.get(
                self.source_status, self.source_status
            ),
            "kind": self.kind,
            "notes": self.notes,
        }


@dataclass
class BrokerageSearchResult:
    """The outcome of searching one source for one location."""

    source_key: str
    source_label: str
    publisher: str
    status: str
    message: str = ""
    opportunities: list[BrokerageOpportunity] = field(default_factory=list)
    retrieved_at: str = ""
    kind: str = "automated"
    search_url: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_key": self.source_key,
            "source_label": self.source_label,
            "publisher": self.publisher,
            "status": self.status,
            "status_label": STATUS_LABELS.get(self.status, self.status),
            "message": self.message,
            "retrieved_at": self.retrieved_at,
            "kind": self.kind,
            "search_url": self.search_url,
            "opportunity_count": len(self.opportunities),
            "opportunities": [item.to_dict() for item in self.opportunities],
        }


# ---------------------------------------------------------------------------
# The adapter contract
# ---------------------------------------------------------------------------

class BrokerageSourceAdapter(Protocol):
    """The contract every brokerage source implements."""

    key: str
    label: str
    publisher: str

    def search(
        self,
        latitude: float,
        longitude: float,
        radius_m: int,
        limit: int,
    ) -> BrokerageSearchResult: ...


# ---------------------------------------------------------------------------
# Adapter: OpenStreetMap operators and agencies
# ---------------------------------------------------------------------------

_OVERPASS_QUERY = """
[out:json][timeout:{timeout}];
(
  nwr["office"~"^(estate_agent|property|commercial)$"](around:{radius},{lat},{lon});
  nwr["shop"="estate_agent"](around:{radius},{lat},{lon});
  nwr["craft"="estate_agent"](around:{radius},{lat},{lon});
);
out center tags;
"""


class OpenStreetMapBrokerageAdapter:
    """Discovers agents and operators tagged in OpenStreetMap.

    This is collaborative map data.  It identifies agencies that operate in
    the area, with whatever contact details the contributor recorded.  It
    is not a broker directory and it does not imply that an agency lists
    the specific premises.
    """

    key = "openstreetmap_brokerage"
    label = "OpenStreetMap (operators and agencies)"
    publisher = "OpenStreetMap contributors"

    def search(
        self,
        latitude: float,
        longitude: float,
        radius_m: int,
        limit: int,
    ) -> BrokerageSearchResult:
        settings = get_settings()
        retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

        body = _OVERPASS_QUERY.format(
            # Bounded by the property-search timeout so that a slow mirror
        # cannot hold the request open longer than the caller waits.
        timeout=int(max(5, min(30, settings.property_search_timeout_seconds))),
            radius=int(max(100, min(5000, radius_m))),
            lat=f"{latitude:.6f}",
            lon=f"{longitude:.6f}",
        )

        try:
            import requests

            response = requests.post(
                settings.overpass_url,
                data={"data": body},
                headers={"User-Agent": "RetailSiteIntelligence/2.0 (site selection)"},
                timeout=(
                min(5.0, settings.property_search_timeout_seconds),
                settings.property_search_timeout_seconds,
            ),
            )
        except Exception as exc:
            return BrokerageSearchResult(
                source_key=self.key,
                source_label=self.label,
                publisher=self.publisher,
                status=STATUS_UNAVAILABLE,
                message=f"The map data source could not be reached: {exc}",
                retrieved_at=retrieved_at,
            )

        if response.status_code == 429:
            return BrokerageSearchResult(
                source_key=self.key,
                source_label=self.label,
                publisher=self.publisher,
                status=STATUS_UNAVAILABLE,
                message="The map data source is rate limiting this client. Try again shortly.",
                retrieved_at=retrieved_at,
            )
        if response.status_code != 200:
            return BrokerageSearchResult(
                source_key=self.key,
                source_label=self.label,
                publisher=self.publisher,
                status=STATUS_UNAVAILABLE,
                message=f"The map data source returned HTTP {response.status_code}.",
                retrieved_at=retrieved_at,
            )

        try:
            payload = response.json()
        except ValueError:
            return BrokerageSearchResult(
                source_key=self.key,
                source_label=self.label,
                publisher=self.publisher,
                status=STATUS_UNAVAILABLE,
                message="The map data source returned a response that could not be parsed.",
                retrieved_at=retrieved_at,
            )

        opportunities: list[BrokerageOpportunity] = []
        seen: set[str] = set()

        for element in payload.get("elements") or []:
            if not isinstance(element, dict):
                continue
            tags = element.get("tags") or {}
            if not isinstance(tags, dict):
                continue
            name = str(tags.get("name") or tags.get("operator") or "").strip()
            if not name:
                continue

            lat = element.get("lat") or (element.get("center") or {}).get("lat")
            lon = element.get("lon") or (element.get("center") or {}).get("lon")
            try:
                lat = float(lat)
                lon = float(lon)
            except (TypeError, ValueError):
                continue

            osm_type = str(element.get("type") or "node")
            osm_id = str(element.get("id") or "")
            identity = f"{osm_type}/{osm_id}"
            if identity in seen:
                continue
            seen.add(identity)

            distance = _haversine_m(latitude, longitude, lat, lon)
            website = str(tags.get("website") or tags.get("contact:website") or "")
            phone = str(tags.get("phone") or tags.get("contact:phone") or "")
            email = str(tags.get("email") or tags.get("contact:email") or "")
            start_date = str(tags.get("start_date") or "") or None

            opportunities.append(
                BrokerageOpportunity(
                    source_key=self.key,
                    source_label=self.label,
                    publisher=self.publisher,
                    name=name,
                    service_area=_service_area(tags, distance),
                    website=website,
                    phone=phone,
                    email=email,
                    source_url=f"https://www.openstreetmap.org/{osm_type}/{osm_id}",
                    distance_m=distance,
                    retrieved_at=retrieved_at,
                    source_date=start_date,
                    source_status=(
                        STATUS_DATE_AVAILABLE if start_date else STATUS_DATE_UNKNOWN
                    ),
                    notes=(
                        "Identified from map data. Contact the agency directly "
                        "to confirm it handles premises in this area."
                    ),
                )
            )

        opportunities.sort(key=lambda item: item.distance_m or 0.0)
        opportunities = opportunities[: max(1, limit)]

        return BrokerageSearchResult(
            source_key=self.key,
            source_label=self.label,
            publisher=self.publisher,
            status=STATUS_LIVE if opportunities else STATUS_UNAVAILABLE,
            message=(
                f"{len(opportunities)} operator(s) or agency tagged in the area."
                if opportunities
                else "No agency or operator is tagged in the area in the map data."
            ),
            opportunities=opportunities,
            retrieved_at=retrieved_at,
        )


def _service_area(tags: dict[str, Any], distance_m: float) -> str:
    """Describe where an agency operates."""

    parts = [
        str(tags.get("addr:city") or ""),
        str(tags.get("addr:suburb") or ""),
        str(tags.get("addr:street") or ""),
    ]
    cleaned = [part for part in parts if part]
    if cleaned:
        return ", ".join(cleaned)
    if distance_m is not None:
        return f"Within {distance_m / 1000:.1f} km of the location"
    return "Not stated"


# ---------------------------------------------------------------------------
# Adapter: manual navigation
# ---------------------------------------------------------------------------

class ManualNavigationAdapter:
    """A source that cannot be queried automatically.

    The platform gives the user a direct search link and states plainly
    that the result was not retrieved automatically.  No listing, agency
    or contact detail is invented.
    """

    kind = "manual"

    def __init__(
        self,
        key: str,
        label: str,
        publisher: str,
        homepage: str = "",
        search_template: str = "",
        instructions: str = "",
    ) -> None:
        self.key = key
        self.label = label
        self.publisher = publisher
        self.homepage = homepage
        self.search_template = search_template
        self.instructions = instructions

    def build_search_url(
        self, latitude: float, longitude: float, query: str = ""
    ) -> Optional[str]:
        """Build the deep link for a location, when a template is configured."""

        if not self.search_template:
            return self.homepage or None
        return (
            self.search_template.replace("{lat}", f"{latitude:.5f}")
            .replace("{lon}", f"{longitude:.5f}")
            .replace("{q}", query.replace(" ", "+"))
        )

    def search(
        self,
        latitude: float,
        longitude: float,
        radius_m: int,
        limit: int,
    ) -> BrokerageSearchResult:
        retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        search_url = self.build_search_url(latitude, longitude)

        return BrokerageSearchResult(
            source_key=self.key,
            source_label=self.label,
            publisher=self.publisher,
            status=STATUS_UNAVAILABLE,
            message=(
                self.instructions
                or "This source does not publish an API that can be queried "
                "automatically. Use the link to search it directly."
            ),
            retrieved_at=retrieved_at,
            kind="manual",
            search_url=search_url,
        )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def _parse_manual_sources(raw: str) -> list[ManualNavigationAdapter]:
    """Parse the configured manual sources.

    Each entry is ``key|Name|Homepage|Search URL template|Instructions``,
    separated by ``||`` between entries.
    """

    adapters: list[ManualNavigationAdapter] = []
    for entry in raw.split("||"):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split("|")
        key = parts[0].strip() or "manual"
        label = parts[1].strip() if len(parts) > 1 else key
        homepage = parts[2].strip() if len(parts) > 2 else ""
        template = parts[3].strip() if len(parts) > 3 else ""
        instructions = parts[4].strip() if len(parts) > 4 else ""
        adapters.append(
            ManualNavigationAdapter(
                key=key,
                label=label,
                publisher=homepage or label,
                homepage=homepage,
                search_template=template,
                instructions=instructions,
            )
        )
    return adapters


def list_brokerage_sources() -> list[dict[str, Any]]:
    """Describe every brokerage source and whether it can be queried."""

    settings = get_settings()
    sources: list[dict[str, Any]] = [
        {
            "key": OpenStreetMapBrokerageAdapter.key,
            "label": OpenStreetMapBrokerageAdapter.label,
            "publisher": OpenStreetMapBrokerageAdapter.publisher,
            "kind": "automated",
            "enabled": True,
            "status": "enabled",
            "description": (
                "Operators and agencies recorded in OpenStreetMap near the "
                "recommended locations, with the contact details the "
                "contributor published. This is map data, not a broker "
                "directory."
            ),
        }
    ]

    for adapter in _parse_manual_sources(
        " || ".join(settings.brokerage_manual_sources)
    ):
        sources.append(
            {
                "key": adapter.key,
                "label": adapter.label,
                "publisher": adapter.publisher,
                "kind": "manual",
                "enabled": True,
                "status": "manual_navigation",
                "description": adapter.instructions
                or (
                    "This source cannot be queried automatically. The platform "
                    "provides a direct search link instead."
                ),
            }
        )

    return sources


def search_brokerages(
    latitude: float,
    longitude: float,
    radius_m: int = 5000,
    limit: int = 10,
) -> list[BrokerageSearchResult]:
    """Query every brokerage source, isolating failures per source."""

    settings = get_settings()
    results: list[BrokerageSearchResult] = []

    try:
        results.append(
            OpenStreetMapBrokerageAdapter().search(
                latitude, longitude, radius_m, limit
            )
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("The OpenStreetMap brokerage adapter failed: %s", exc)
        results.append(
            BrokerageSearchResult(
                source_key=OpenStreetMapBrokerageAdapter.key,
                source_label=OpenStreetMapBrokerageAdapter.label,
                publisher=OpenStreetMapBrokerageAdapter.publisher,
                status=STATUS_UNAVAILABLE,
                message=f"The source failed unexpectedly: {exc}",
                retrieved_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            )
        )

    for adapter in _parse_manual_sources(
        " || ".join(settings.brokerage_manual_sources)
    ):
        try:
            results.append(adapter.search(latitude, longitude, radius_m, limit))
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("The manual brokerage adapter %s failed: %s", adapter.key, exc)

    return results


__all__ = [
    "BrokerageOpportunity",
    "BrokerageSearchResult",
    "BrokerageSourceAdapter",
    "ManualNavigationAdapter",
    "OpenStreetMapBrokerageAdapter",
    "STATUS_DATE_AVAILABLE",
    "STATUS_DATE_UNKNOWN",
    "STATUS_LABELS",
    "STATUS_LIVE",
    "STATUS_RECENT",
    "STATUS_UNAVAILABLE",
    "list_brokerage_sources",
    "search_brokerages",
]

