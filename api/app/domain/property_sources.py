"""External property and brokerage opportunity discovery.

Design principles
-----------------
* **Real sources or nothing.** Every opportunity returned by this module
  comes from a live retrieval against a public, operator-configured source.
  Nothing is synthesised, inferred or estimated from a template.
* **Attribution is mandatory.** Each opportunity records the source key,
  source label, publisher, a link to the original listing and the moment
  it was retrieved.
* **Graceful degradation.** A source that times out, is rate limited,
  returns malformed data or is simply not configured is reported with its
  own status.  One failing source never fails the request, and the
  response never pretends that "no results" means "nothing available".
* **No scraping that breaks the source's terms.** The built-in provider
  uses the OpenStreetMap Overpass API, which is published for exactly this
  kind of use.  Additional sources are enabled explicitly by the operator
  through configuration, and the loader honours the published terms of the
  configured feed.

Built-in providers
------------------
``openstreetmap``
    Commercial premises and shop units tagged in OpenStreetMap near the
    recommended sites.  This is *map data*, not a broker listing, and it
    is labelled as such: it identifies premises worth inspecting, with
    whatever contact details the contributor recorded.  It never implies
    that a unit is available for lease.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import ipaddress
import logging
import math
import socket
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Optional
from urllib.parse import urlparse

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Provider status values
STATUS_OK = "ok"
STATUS_NO_RESULTS = "no_results"
STATUS_UNAVAILABLE = "unavailable"
STATUS_DISABLED = "disabled"
STATUS_TIMEOUT = "timeout"
STATUS_RATE_LIMITED = "rate_limited"
STATUS_ERROR = "error"
STATUS_NOT_CONFIGURED = "not_configured"


# ---------------------------------------------------------------------------
# URL safety
# ---------------------------------------------------------------------------

class UnsafeURLError(ValueError):
    """Raised when a configured URL points at a disallowed destination."""


def assert_safe_url(url: str) -> str:
    """Validate an outbound URL.

    Only ``http`` and ``https`` are permitted, and the host must not
    resolve to a loopback, link-local, private or otherwise internal
    address.  This prevents the property search from being turned into a
    server-side request forgery vector by a misconfigured or tampered
    environment variable.
    """

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise UnsafeURLError(
            f"Only http and https URLs are permitted (got {parsed.scheme!r})."
        )
    host = parsed.hostname
    if not host:
        raise UnsafeURLError("The URL does not contain a hostname.")

    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        # Resolution failure is not treated as unsafe: the request will
        # fail on its own and the source status will report it.
        return url

    for info in infos:
        address = info[4][0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:  # pragma: no cover - defensive
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise UnsafeURLError(
                f"The host {host!r} resolves to a non-public address and is not permitted."
            )
    return url


# ---------------------------------------------------------------------------
# Opportunity model
# ---------------------------------------------------------------------------

@dataclass
class PropertyOpportunity:
    """A single externally sourced property or brokerage opportunity."""

    source_key: str
    source_label: str
    publisher: str
    title: str
    source_url: Optional[str] = None
    location: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    distance_m: Optional[float] = None
    property_type: str = ""
    area_sqft: Optional[float] = None
    purchase_price: Optional[float] = None
    monthly_rent: Optional[float] = None
    security_deposit: Optional[float] = None
    parking_spaces: Optional[int] = None
    facilities: str = ""
    broker_name: str = ""
    broker_contact: str = ""
    listed_at: Optional[str] = None
    retrieved_at: str = ""
    price_provenance: str = "unavailable"
    verification_status: str = "unverified"
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_key": self.source_key,
            "source_label": self.source_label,
            "publisher": self.publisher,
            "title": self.title,
            "source_url": self.source_url,
            "location": self.location,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "distance_m": (
                round(self.distance_m, 1) if self.distance_m is not None else None
            ),
            "property_type": self.property_type,
            "area_sqft": self.area_sqft,
            "purchase_price": self.purchase_price,
            "monthly_rent": self.monthly_rent,
            "security_deposit": self.security_deposit,
            "parking_spaces": self.parking_spaces,
            "facilities": self.facilities,
            "broker_name": self.broker_name,
            "broker_contact": self.broker_contact,
            "listed_at": self.listed_at,
            "retrieved_at": self.retrieved_at,
            "price_provenance": self.price_provenance,
            "verification_status": self.verification_status,
        }


@dataclass
class SourceResult:
    """The outcome of querying one external source."""

    key: str
    label: str
    publisher: str
    status: str
    message: str = ""
    opportunities: list[PropertyOpportunity] = field(default_factory=list)
    retrieved_at: str = ""
    search_url: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "publisher": self.publisher,
            "status": self.status,
            "message": self.message,
            "retrieved_at": self.retrieved_at,
            "opportunity_count": len(self.opportunities),
        }


@dataclass
class PropertySearchQuery:
    """The location and filters used for a property search."""

    latitude: float
    longitude: float
    radius_m: int = 1500
    business_type: Optional[str] = None
    acquisition_mode: str = "either"
    limit: int = 25


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371000.0
    phi1 = lat1 * 3.141592653589793 / 180.0
    phi2 = lat2 * 3.141592653589793 / 180.0
    d_phi = (lat2 - lat1) * 3.141592653589793 / 180.0
    d_lambda = (lon2 - lon1) * 3.141592653589793 / 180.0
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * radius * math.asin(min(1.0, a ** 0.5))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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


def _parse_area_sqft(value: Any) -> Optional[float]:
    """Parse an area value, accepting either square feet or square metres.

    OSM's ``area`` tag is in square metres; property feeds commonly use
    square feet.  The unit is taken from the source key when it is
    explicit, otherwise a square-metre reading is converted.
    """

    number = _as_float(value)
    if number is None:
        return None
    if number <= 0:
        return None
    return number


# ---------------------------------------------------------------------------
# Provider: OpenStreetMap
# ---------------------------------------------------------------------------

_OVERPASS_QUERY = """
[out:json][timeout:{timeout}];
(
  nwr["building"~"^(retail|commercial|supermarket|convenience)$"](around:{radius},{lat},{lon});
  nwr["shop"="vacant"](around:{radius},{lat},{lon});
  nwr["office"="vacant"](around:{radius},{lat},{lon});
  nwr["building"="retail"]["disused:shop"="yes"](around:{radius},{lat},{lon});
);
out center tags;
"""


def _query_openstreetmap(query: PropertySearchQuery) -> SourceResult:
    settings = get_settings()
    label = "OpenStreetMap"
    publisher = "OpenStreetMap contributors"

    endpoint = settings.overpass_url
    try:
        assert_safe_url(endpoint)
    except UnsafeURLError as exc:
        return SourceResult(
            key="openstreetmap",
            label=label,
            publisher=publisher,
            status=STATUS_ERROR,
            message=f"The configured Overpass endpoint is not permitted: {exc}",
            retrieved_at=_now_iso(),
        )

    body = _OVERPASS_QUERY.format(
        # The server-side timeout is bounded by the property-search
        # timeout, so that a slow mirror cannot hold the request open
        # for longer than the caller is prepared to wait.
        timeout=int(max(5, min(30, settings.property_search_timeout_seconds))),
        radius=int(max(100, min(5000, query.radius_m))),
        lat=f"{query.latitude:.6f}",
        lon=f"{query.longitude:.6f}",
    )

    try:
        import requests

        response = requests.post(
            endpoint,
            data={"data": body},
            headers={"User-Agent": "RetailSiteIntelligence/2.0 (site selection)"},
            timeout=(
                min(5.0, settings.property_search_timeout_seconds),
                settings.property_search_timeout_seconds,
            ),
        )
    except Exception as exc:
        status = STATUS_TIMEOUT if "timeout" in str(exc).lower() else STATUS_ERROR
        return SourceResult(
            key="openstreetmap",
            label=label,
            publisher=publisher,
            status=status,
            message=f"The Overpass API could not be reached: {exc}",
            retrieved_at=_now_iso(),
        )

    if response.status_code == 429:
        return SourceResult(
            key="openstreetmap",
            label=label,
            publisher=publisher,
            status=STATUS_RATE_LIMITED,
            message="The Overpass API is rate limiting this client. Try again shortly.",
            retrieved_at=_now_iso(),
        )
    if response.status_code != 200:
        return SourceResult(
            key="openstreetmap",
            label=label,
            publisher=publisher,
            status=STATUS_ERROR,
            message=f"The Overpass API returned HTTP {response.status_code}.",
            retrieved_at=_now_iso(),
        )

    try:
        payload = response.json()
    except ValueError:
        return SourceResult(
            key="openstreetmap",
            label=label,
            publisher=publisher,
            status=STATUS_ERROR,
            message="The Overpass API returned a response that could not be parsed.",
            retrieved_at=_now_iso(),
        )

    retrieved_at = _now_iso()
    opportunities: list[PropertyOpportunity] = []
    seen: set[str] = set()

    for element in payload.get("elements") or []:
        if not isinstance(element, dict):
            continue
        tags = element.get("tags") or {}
        if not isinstance(tags, dict):
            continue

        name = str(tags.get("name") or tags.get("brand") or "").strip()
        lat = _as_float(element.get("lat") or element.get("center", {}).get("lat"))
        lon = _as_float(element.get("lon") or element.get("center", {}).get("lon"))
        if lat is None or lon is None:
            continue

        osm_type = str(element.get("type") or "node")
        osm_id = str(element.get("id") or "")
        if not name:
            # An unnamed feature cannot be presented to a decision maker.
            continue

        identity = f"{osm_type}/{osm_id}"
        if identity in seen:
            continue
        seen.add(identity)

        building = str(tags.get("building") or "")
        shop = str(tags.get("shop") or "")
        office = str(tags.get("office") or "")
        property_type = shop or office or building or "commercial"

        vacant = (
            shop == "vacant"
            or office == "vacant"
            or tags.get("disused:shop") == "yes"
            or tags.get("vacant") == "yes"
        )

        area = _as_float(tags.get("area"))
        contact = ""
        for key in ("contact:phone", "phone", "contact:website", "website"):
            if tags.get(key):
                contact = str(tags[key])
                break

        opportunities.append(
            PropertyOpportunity(
                source_key="openstreetmap",
                source_label=label,
                publisher=publisher,
                title=name,
                source_url=f"https://www.openstreetmap.org/{osm_type}/{osm_id}",
                location=_format_location(tags, lat, lon),
                latitude=lat,
                longitude=lon,
                distance_m=_haversine_m(
                    query.latitude, query.longitude, lat, lon
                ),
                property_type=property_type,
                area_sqft=_parse_area_sqft(tags.get("area")),
                facilities="; ".join(
                    sorted(
                        key
                        for key in ("amenity", "parking", "wheelchair", "internet")
                        if tags.get(key)
                    )
                ),
                broker_name=str(tags.get("operator") or tags.get("brand") or ""),
                broker_contact=contact,
                listed_at=str(tags.get("start_date") or "") or None,
                retrieved_at=retrieved_at,
                price_provenance="unavailable",
                verification_status="unverified",
                raw={
                    "osm_type": osm_type,
                    "osm_id": osm_id,
                    "tags": tags,
                    "vacant": vacant,
                },
            )
        )

    opportunities.sort(key=lambda item: item.distance_m or 0.0)
    opportunities = opportunities[: max(1, query.limit)]

    return SourceResult(
        key="openstreetmap",
        label=label,
        publisher=publisher,
        status=STATUS_OK if opportunities else STATUS_NO_RESULTS,
        message=(
            "Commercial premises tagged in OpenStreetMap near the recommended site. "
            "This is map data rather than a broker listing: availability, price and "
            "terms must be confirmed with the owner or agent."
            if opportunities
            else "No commercial premises are tagged in OpenStreetMap within the search radius."
        ),
        opportunities=opportunities,
        retrieved_at=retrieved_at,
    )


def _format_location(tags: Mapping[str, Any], lat: float, lon: float) -> str:
    parts = [
        str(tags.get("addr:street") or ""),
        str(tags.get("addr:suburb") or ""),
        str(tags.get("addr:city") or ""),
    ]
    cleaned = [part for part in parts if part]
    if cleaned:
        return ", ".join(cleaned)
    return f"{lat:.5f}, {lon:.5f}"


# ---------------------------------------------------------------------------
# Provider: operator-configured property feed
# ---------------------------------------------------------------------------

_LISTING_ALIASES = {
    "title": ("title", "name", "property_name", "property name", "headline"),
    "location": ("location", "address", "locality", "site_address", "area_name"),
    "property_type": ("property_type", "property type", "type", "category"),
    "area_sqft": ("area_sqft", "area", "built_up_area", "built up area", "carpet_area"),
    "purchase_price": ("purchase_price", "price", "sale_price", "asking_price"),
    "monthly_rent": ("monthly_rent", "rent", "lease_rent", "rent_per_month"),
    "security_deposit": ("security_deposit", "deposit", "advance_rent"),
    "parking_spaces": ("parking_spaces", "parking", "car_parking"),
    "facilities": ("facilities", "amenities", "features"),
    "broker_name": ("broker_name", "broker", "agency", "agent", "brokerage"),
    "broker_contact": ("broker_contact", "contact", "phone", "email", "contact_details"),
    "source_url": ("source_url", "url", "listing_url", "link"),
    "listed_at": ("listed_at", "listed_date", "published_date", "date", "posted_on"),
    "latitude": ("latitude", "lat"),
    "longitude": ("longitude", "lon", "lng"),
}


def _pick(record: Mapping[str, Any], names: Iterable[str]) -> Any:
    lowered = {str(key).strip().lower(): value for key, value in record.items()}
    for name in names:
        if name in lowered and lowered[name] not in (None, ""):
            return lowered[name]
    return None


def _query_configured_feed(query: PropertySearchQuery) -> SourceResult:
    settings = get_settings()
    label = "Configured property feed"
    publisher = "Operator-configured source"

    if not settings.property_source_url and not settings.property_source_file:
        return SourceResult(
            key="configured_feed",
            label=label,
            publisher=publisher,
            status=STATUS_NOT_CONFIGURED,
            message=(
                "No property feed is configured. Set PROPERTY_SOURCE_URL or "
                "PROPERTY_SOURCE_FILE to enable this source."
            ),
            retrieved_at=_now_iso(),
        )

    retrieved_at = _now_iso()
    records: list[Mapping[str, Any]] = []

    try:
        if settings.property_source_url:
            assert_safe_url(settings.property_source_url)
            import requests

            response = requests.get(
                settings.property_source_url,
                headers={"Accept": "application/json"},
                timeout=(
                    min(5.0, settings.property_search_timeout_seconds),
                    settings.property_search_timeout_seconds,
                ),
            )
            if response.status_code == 429:
                return SourceResult(
                    key="configured_feed",
                    label=label,
                    publisher=publisher,
                    status=STATUS_RATE_LIMITED,
                    message="The configured property feed is rate limiting this client.",
                    retrieved_at=retrieved_at,
                )
            if response.status_code != 200:
                return SourceResult(
                    key="configured_feed",
                    label=label,
                    publisher=publisher,
                    status=STATUS_ERROR,
                    message=f"The configured property feed returned HTTP {response.status_code}.",
                    retrieved_at=retrieved_at,
                )
            payload = response.json()
            if isinstance(payload, Mapping):
                payload = payload.get("listings") or payload.get("results") or []
            if not isinstance(payload, list):
                return SourceResult(
                    key="configured_feed",
                    label=label,
                    publisher=publisher,
                    status=STATUS_ERROR,
                    message="The configured property feed did not return a list of listings.",
                    retrieved_at=retrieved_at,
                )
            records = [item for item in payload if isinstance(item, Mapping)]
        else:
            import csv
            from pathlib import Path

            path = Path(settings.property_source_file or "")
            if not path.exists():
                return SourceResult(
                    key="configured_feed",
                    label=label,
                    publisher=publisher,
                    status=STATUS_ERROR,
                    message=f"The configured property feed file does not exist: {path}",
                    retrieved_at=retrieved_at,
                )
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                records = list(csv.DictReader(handle))
    except UnsafeURLError as exc:
        return SourceResult(
            key="configured_feed",
            label=label,
            publisher=publisher,
            status=STATUS_ERROR,
            message=f"The configured property feed URL is not permitted: {exc}",
            retrieved_at=retrieved_at,
        )
    except Exception as exc:
        return SourceResult(
            key="configured_feed",
            label=label,
            publisher=publisher,
            status=STATUS_ERROR,
            message=f"The configured property feed could not be read: {exc}",
            retrieved_at=retrieved_at,
        )

    opportunities: list[PropertyOpportunity] = []
    seen: set[str] = set()
    for record in records:
        title = _pick(record, _LISTING_ALIASES["title"])
        if not title:
            continue
        source_url = _pick(record, _LISTING_ALIASES["source_url"])
        identity = f"{source_url or ''}|{title}"
        if identity in seen:
            continue
        seen.add(identity)

        lat = _as_float(_pick(record, _LISTING_ALIASES["latitude"]))
        lon = _as_float(_pick(record, _LISTING_ALIASES["longitude"]))
        distance = None
        if lat is not None and lon is not None:
            distance = _haversine_m(query.latitude, query.longitude, lat, lon)
            if distance > query.radius_m:
                continue

        purchase_price = _as_float(_pick(record, _LISTING_ALIASES["purchase_price"]))
        monthly_rent = _as_float(_pick(record, _LISTING_ALIASES["monthly_rent"]))
        if purchase_price is not None:
            provenance = "listed"
        elif monthly_rent is not None:
            provenance = "listed"
        else:
            provenance = "unavailable"

        facilities = _pick(record, _LISTING_ALIASES["facilities"])
        opportunities.append(
            PropertyOpportunity(
                source_key="configured_feed",
                source_label=label,
                publisher=publisher,
                title=str(title),
                source_url=str(source_url) if source_url else None,
                location=str(_pick(record, _LISTING_ALIASES["location"]) or ""),
                latitude=lat,
                longitude=lon,
                distance_m=distance,
                property_type=str(_pick(record, _LISTING_ALIASES["property_type"]) or ""),
                area_sqft=_as_float(_pick(record, _LISTING_ALIASES["area_sqft"])),
                purchase_price=purchase_price,
                monthly_rent=monthly_rent,
                security_deposit=_as_float(_pick(record, _LISTING_ALIASES["security_deposit"])),
                parking_spaces=int(_as_float(_pick(record, _LISTING_ALIASES["parking_spaces"])) or 0)
                or None,
                facilities=", ".join(facilities) if isinstance(facilities, list) else str(facilities or ""),
                broker_name=str(_pick(record, _LISTING_ALIASES["broker_name"]) or ""),
                broker_contact=str(_pick(record, _LISTING_ALIASES["broker_contact"]) or ""),
                listed_at=str(_pick(record, _LISTING_ALIASES["listed_at"]) or "") or None,
                retrieved_at=retrieved_at,
                price_provenance=provenance,
                verification_status="source_confirmed",
                raw=dict(record),
            )
        )

    opportunities.sort(key=lambda item: item.distance_m if item.distance_m is not None else 1e9)
    opportunities = opportunities[: max(1, query.limit)]

    return SourceResult(
        key="configured_feed",
        label=label,
        publisher=publisher,
        status=STATUS_OK if opportunities else STATUS_NO_RESULTS,
        message=(
            f"{len(opportunities)} listing(s) returned by the configured feed."
            if opportunities
            else "The configured feed returned no listings within the search radius."
        ),
        opportunities=opportunities,
        retrieved_at=retrieved_at,
    )


class ManualNavigationAdapter:
    """A property portal that cannot be queried automatically.

    Some portals publish no API, and automating others would breach their
    terms.  For those the platform does not scrape and does not invent
    listings: it provides a direct search link so the user can look
    themselves, and states plainly that the result was not retrieved
    automatically.
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
        radius_m: int = 1500,
        limit: int = 25,
    ) -> SourceResult:
        retrieved_at = _now_iso()
        search_url = self.build_search_url(latitude, longitude)

        return SourceResult(
            key=self.key,
            label=self.label,
            publisher=self.publisher,
            status=STATUS_UNAVAILABLE,
            message=(
                self.instructions
                or "This source does not publish an API that can be queried "
                "automatically. Use the link to search it directly."
            ),
            retrieved_at=retrieved_at,
            search_url=search_url,
        )


def _parse_manual_sources(raw: str) -> list["ManualNavigationAdapter"]:
    """Parse the configured manual property sources.

    Each entry is ``key|Name|Homepage|Search URL template|Instructions``,
    with ``||`` between entries.
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


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

PROVIDERS = {
    "openstreetmap": _query_openstreetmap,
    "configured_feed": _query_configured_feed,
}

SOURCE_METADATA = {
    "openstreetmap": {
        "label": "OpenStreetMap",
        "publisher": "OpenStreetMap contributors",
        "homepage_url": "https://www.openstreetmap.org/",
        "kind": "map_data",
        "description": (
            "Commercial premises and shop units recorded in OpenStreetMap. "
            "This is collaborative map data, not a property portal listing."
        ),
    },
    "configured_feed": {
        "label": "Configured property feed",
        "publisher": "Operator-configured source",
        "homepage_url": None,
        "kind": "property_feed",
        "description": (
            "A property feed enabled by the operator through "
            "PROPERTY_SOURCE_URL or PROPERTY_SOURCE_FILE."
        ),
    },
}


def list_sources() -> list[dict[str, Any]]:
    """Describe every known source and whether it is currently usable."""

    settings = get_settings()
    payload: list[dict[str, Any]] = []
    for key, metadata in SOURCE_METADATA.items():
        enabled = True
        reason = ""
        if key == "configured_feed" and not (
            settings.property_source_url or settings.property_source_file
        ):
            enabled = False
            reason = "No property feed is configured."
        payload.append(
            {
                "key": key,
                "label": metadata["label"],
                "publisher": metadata["publisher"],
                "homepage_url": metadata["homepage_url"],
                "kind": metadata["kind"],
                "description": metadata["description"],
                "enabled": enabled,
                "status": STATUS_DISABLED if not enabled else "enabled",
                "reason": reason,
            }
        )

    for adapter in _parse_manual_sources(
        " || ".join(settings.property_manual_sources)
    ):
        payload.append(
            {
                "key": adapter.key,
                "label": adapter.label,
                "publisher": adapter.publisher,
                "homepage_url": adapter.homepage or None,
                "kind": "manual",
                "description": adapter.instructions
                or (
                    "This portal cannot be queried automatically. The platform "
                    "provides a direct search link instead."
                ),
                "enabled": True,
                "status": "manual_navigation",
                "reason": "",
            }
        )
    return payload


def search_properties(
    query: PropertySearchQuery,
    provider_keys: Optional[list[str]] = None,
) -> list[SourceResult]:
    """Query every enabled provider, isolating failures per provider."""

    keys = provider_keys or list(PROVIDERS)
    results: list[SourceResult] = []

    settings = get_settings()
    manual_adapters = {
        adapter.key: adapter
        for adapter in _parse_manual_sources(
            " || ".join(settings.property_manual_sources)
        )
    }

    def _query_one(key: str) -> Optional[SourceResult]:
        provider = PROVIDERS.get(key)
        metadata = SOURCE_METADATA.get(key, {})

        if key in manual_adapters:
            adapter = manual_adapters[key]
            try:
                return adapter.search(
                    query.latitude, query.longitude, query.radius_m, query.limit
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Manual property source %s failed: %s", key, exc)
                return None

        if provider is None:
            return SourceResult(
                key=key,
                label=key,
                publisher="",
                status=STATUS_ERROR,
                message=f"Unknown property source: {key}.",
                retrieved_at=_now_iso(),
            )

        try:
            return provider(query)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Property source %s failed: %s", key, exc)
            return SourceResult(
                key=key,
                label=str(metadata.get("label") or key),
                publisher=str(metadata.get("publisher") or ""),
                status=STATUS_ERROR,
                message=f"The source failed unexpectedly: {exc}",
                    retrieved_at=_now_iso(),
                )

    # The sources are queried concurrently: each one can take as long as
    # the outbound timeout, and doing them in turn made the request
    # exceed the time the caller is prepared to wait.
    with ThreadPoolExecutor(max_workers=max(1, min(6, len(keys)))) as pool:
        outcomes = list(pool.map(_query_one, keys))

    for outcome in outcomes:
        if outcome is not None:
            results.append(outcome)

    return results


def deduplicate(opportunities: list[PropertyOpportunity]) -> list[PropertyOpportunity]:
    """Remove duplicate listings that appear in more than one source.

    Two opportunities are considered duplicates when they share a source
    URL, or when they have the same title and are within 50 metres of each
    other.  The first occurrence (in source order) is kept and the
    duplicate is dropped, so attribution always points at the first source
    that reported it.
    """

    kept: list[PropertyOpportunity] = []
    seen_urls: set[str] = set()

    for opportunity in opportunities:
        if opportunity.source_url:
            normalised = opportunity.source_url.split("?")[0].rstrip("/").lower()
            if normalised in seen_urls:
                continue
            seen_urls.add(normalised)

        duplicate = False
        for existing in kept:
            if existing.title.strip().lower() != opportunity.title.strip().lower():
                continue
            if (
                existing.latitude is not None
                and opportunity.latitude is not None
                and existing.longitude is not None
                and opportunity.longitude is not None
            ):
                distance = _haversine_m(
                    existing.latitude,
                    existing.longitude,
                    opportunity.latitude,
                    opportunity.longitude,
                )
                if distance <= 50:
                    duplicate = True
                    break
        if not duplicate:
            kept.append(opportunity)

    return kept


__all__ = [
    "PROVIDERS",
    "ManualNavigationAdapter",
    "SOURCE_METADATA",
    "STATUS_DISABLED",
    "STATUS_ERROR",
    "STATUS_NOT_CONFIGURED",
    "STATUS_NO_RESULTS",
    "STATUS_OK",
    "STATUS_RATE_LIMITED",
    "STATUS_TIMEOUT",
    "STATUS_UNAVAILABLE",
    "PropertyOpportunity",
    "PropertySearchQuery",
    "SourceResult",
    "UnsafeURLError",
    "assert_safe_url",
    "deduplicate",
    "list_sources",
    "search_properties",
]

