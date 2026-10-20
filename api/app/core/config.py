"""Centralised runtime configuration for the Retail Site Intelligence API.

Every value is read from the environment exactly once at import time and
exposed through a single immutable settings object.  Nothing here is ever
serialised to an API response, so credentials cannot leak to the browser.

Rules enforced by this module:

* No secret is ever returned by :meth:`Settings.public_fingerprint` or by
  :meth:`Settings.validation_report`.
* Missing optional integrations degrade to "disabled" rather than crashing
  the process at import time.
* CORS origins are read from the environment; there is no hard-coded
  placeholder production origin.
* The environment file is loaded before the settings are read, so a local
  checkout works without exporting every variable by hand.  Variables
  already present in the process environment always win, which is what
  makes a deployment's own configuration take precedence over a file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

#: The repository root, used to locate the environment file.
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def load_environment_file() -> Path | None:
    """Load the environment file from the repository root, if one exists.

    ``.env.local`` is checked first and ``.env`` second, so a local
    override always wins over the shared defaults.  Values already present
    in the process environment are never overwritten, so a deployment's own
    configuration always takes precedence over a file.

    Returns:
        The path that was loaded, or ``None`` when no file was found.
    """

    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - optional dependency
        return None

    for name in (".env.local", ".env"):
        candidate = REPOSITORY_ROOT / name
        if candidate.is_file():
            load_dotenv(candidate, override=False)
            return candidate

    return None


# The environment file is loaded at import time so that every entry point --
# uvicorn, a script, a test -- sees the same configuration.
load_environment_file()


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    return value.strip() if isinstance(value, str) else default


def _env_opt(name: str) -> Optional[str]:
    value = _env(name)
    return value or None


def _env_bool(name: str, default: bool = False) -> bool:
    raw = _env(name).lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = _env(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _cors_origins() -> list[str]:
    """Allowed browser origins.

    ``FRONTEND_ORIGINS`` is a comma-separated list.  In development the
    Next.js dev server origins are added automatically.  When nothing is
    configured the API runs with no browser origins rather than with a
    placeholder domain that would silently never match.
    """

    raw = _env("FRONTEND_ORIGINS")
    origins = [item.strip() for item in raw.split(",") if item.strip()]

    if _env_bool("ALLOW_DEV_CORS", default=True):
        origins.extend(
            [
                "http://localhost:3000",
                "http://127.0.0.1:3000",
                "http://localhost:3001",
            ]
        )

    # De-duplicate while preserving order.
    seen: set[str] = set()
    unique: list[str] = []
    for origin in origins:
        if origin not in seen:
            seen.add(origin)
            unique.append(origin)
    return unique


@dataclass(frozen=True)
class Settings:
    """Immutable snapshot of the process configuration."""

    # --- Runtime -----------------------------------------------------
    environment: str = field(default_factory=lambda: _env("ENVIRONMENT", "development"))
    log_level: str = field(default_factory=lambda: _env("LOG_LEVEL", "INFO"))

    # --- Supabase ----------------------------------------------------
    supabase_url: Optional[str] = field(default_factory=lambda: _env_opt("SUPABASE_URL"))
    supabase_key: Optional[str] = field(default_factory=lambda: _env_opt("SUPABASE_KEY"))
    supabase_service_role_key: Optional[str] = field(
        default_factory=lambda: _env_opt("SUPABASE_SERVICE_ROLE_KEY")
    )
    supabase_anon_key: Optional[str] = field(
        default_factory=lambda: _env_opt("SUPABASE_ANON_KEY")
    )
    supabase_jwt_secret: Optional[str] = field(
        default_factory=lambda: _env_opt("SUPABASE_JWT_SECRET")
    )

    # --- Observability ------------------------------------------------
    sentry_dsn: Optional[str] = field(default_factory=lambda: _env_opt("SENTRY_DSN"))
    sentry_traces_sample_rate: float = field(
        default_factory=lambda: _env_float("SENTRY_TRACES_SAMPLE_RATE", 0.1)
    )
    enable_metrics: bool = field(
        default_factory=lambda: _env_bool("ENABLE_METRICS", default=True)
    )

    # --- Scoring artefacts -------------------------------------------
    normalized_matrix_file: Optional[str] = field(
        default_factory=lambda: _env_opt("NORMALIZED_MATRIX_FILE")
    )
    matrix_versions_table: str = field(
        default_factory=lambda: _env("SCORING_MATRIX_VERSIONS_TABLE", "normalized_matrix_versions")
    )
    matrix_storage_bucket: str = field(
        default_factory=lambda: _env("SCORING_MATRIX_STORAGE_BUCKET", "scoring-matrices")
    )

    # --- External integrations ---------------------------------------
    ors_api_key: Optional[str] = field(default_factory=lambda: _env_opt("ORS_API_KEY"))
    overpass_url: str = field(
        default_factory=lambda: _env(
            "OVERPASS_URL", "https://overpass-api.de/api/interpreter"
        )
    )
    property_source_url: Optional[str] = field(
        default_factory=lambda: _env_opt("PROPERTY_SOURCE_URL")
    )
    property_source_file: Optional[str] = field(
        default_factory=lambda: _env_opt("PROPERTY_SOURCE_FILE")
    )
    #: Manual-navigation sources for property portals and brokerages that
    #: cannot be queried automatically.  Format:
    #: ``key|Name|Homepage|Search URL template|Instructions``.
    property_manual_sources: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            item.strip()
            for item in _env("PROPERTY_MANUAL_SOURCES").split("||")
            if item.strip()
        )
    )
    brokerage_manual_sources: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            item.strip()
            for item in _env("BROKERAGE_MANUAL_SOURCES").split("||")
            if item.strip()
        )
    )

    # --- AI (Groq) ---------------------------------------------------
    groq_api_key: Optional[str] = field(default_factory=lambda: _env_opt("GROQ_API_KEY"))
    groq_base_url: str = field(
        default_factory=lambda: _env("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
    )
    groq_model: str = field(
        default_factory=lambda: _env("GROQ_MODEL", "qwen/qwen3.8-27b")
    )
    groq_timeout_seconds: float = field(
        default_factory=lambda: _env_float("GROQ_TIMEOUT_SECONDS", 30.0)
    )
    groq_explanation_model: str = field(
        default_factory=lambda: _env("GROQ_EXPLANATION_MODEL", "qwen/qwen3.8-27b")
    )

    # --- Cost estimation ----------------------------------------------
    #: When enabled, the cost engine may estimate a missing component from
    #: the documented rules below.  It is off by default: nothing is
    #: estimated unless an operator turns it on.
    cost_estimation_enabled: bool = field(
        default_factory=lambda: _env_bool("COST_ESTIMATION_ENABLED", default=False)
    )
    cost_estimation_brokerage_percent: float = field(
        default_factory=lambda: _env_float("COST_ESTIMATION_BROKERAGE_PERCENT", 2.0)
    )
    cost_estimation_registration_percent: float = field(
        default_factory=lambda: _env_float("COST_ESTIMATION_REGISTRATION_PERCENT", 5.0)
    )
    cost_estimation_setup_multiple: float = field(
        default_factory=lambda: _env_float("COST_ESTIMATION_SETUP_MULTIPLE", 1.5)
    )
    cost_estimation_maintenance_multiple: float = field(
        default_factory=lambda: _env_float("COST_ESTIMATION_MAINTENANCE_MULTIPLE", 0.10)
    )
    cost_horizon_months: int = field(
        default_factory=lambda: _env_int("COST_HORIZON_MONTHS", 60)
    )

    # --- HTTP --------------------------------------------------------
    cors_origins: list[str] = field(default_factory=_cors_origins)
    allow_anonymous_api: bool = field(
        default_factory=lambda: _env_bool("ALLOW_ANONYMOUS_API", default=False)
    )
    outbound_timeout_seconds: float = field(
        default_factory=lambda: _env_float("OUTBOUND_TIMEOUT_SECONDS", 12.0)
    )
    property_search_timeout_seconds: float = field(
        default_factory=lambda: _env_float("PROPERTY_SEARCH_TIMEOUT_SECONDS", 15.0)
    )
    max_property_results: int = field(
        default_factory=lambda: _env_int("MAX_PROPERTY_RESULTS", 25)
    )

    # --- Derived helpers ----------------------------------------------
    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}

    @property
    def supabase_service_key(self) -> Optional[str]:
        """Service-role key if present, else the general-purpose key."""

        return self.supabase_service_role_key or self.supabase_key

    @property
    def has_supabase(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_key)

    @property
    def has_supabase_auth(self) -> bool:
        """True when the API can verify a Supabase session."""

        return bool(self.supabase_url and (self.supabase_anon_key or self.supabase_jwt_secret))

    @property
    def has_ai_provider(self) -> bool:
        """True when the Groq requirement builder is available."""

        return bool(self.groq_api_key)

    def cost_estimation_rules(self) -> Any:
        """The cost estimation rules, built from the configuration."""

        from scoring.cost_estimation import EstimationRules

        return EstimationRules(
            enabled=self.cost_estimation_enabled,
            brokerage_percent=self.cost_estimation_brokerage_percent,
            registration_percent=self.cost_estimation_registration_percent,
            setup_multiple_of_rent=self.cost_estimation_setup_multiple,
            maintenance_multiple_of_rent=self.cost_estimation_maintenance_multiple,
        )

    @property
    def has_property_source(self) -> bool:
        return bool(self.property_source_url or self.property_source_file)

    def public_fingerprint(self) -> dict[str, Any]:
        """Non-secret description of which integrations are active.

        Safe to expose over the health endpoint: it contains booleans and
        configuration names, never credential values.
        """

        return {
            "environment": self.environment,
            "supabase_configured": self.has_supabase,
            "supabase_auth_configured": self.has_supabase_auth,
            "sentry_configured": bool(self.sentry_dsn),
            "metrics_enabled": self.enable_metrics,
            "normalized_matrix_configured": bool(self.normalized_matrix_file),
            "ors_configured": bool(self.ors_api_key),
            "property_source_configured": self.has_property_source,
            "manual_property_sources": len(self.property_manual_sources),
            "manual_brokerage_sources": len(self.brokerage_manual_sources),
            "groq_configured": self.has_ai_provider,
            "anonymous_api_allowed": self.allow_anonymous_api,
            "cors_origin_count": len(self.cors_origins),
        }

    # --- Configuration validation --------------------------------------
    def validation_report(self) -> list[dict[str, Any]]:
        """Describe the configuration state of every integration.

        Each entry carries a status of ``ok``, ``warning`` or ``error``, a
        short explanation and, where useful, the environment variable that
        must be set.  No credential value is ever included.
        """

        checks: list[dict[str, Any]] = []

        def add(
            key: str,
            label: str,
            status: str,
            detail: str,
            variable: Optional[str] = None,
            required: bool = False,
        ) -> None:
            checks.append(
                {
                    "key": key,
                    "label": label,
                    "status": status,
                    "detail": detail,
                    "variable": variable,
                    "required": required,
                }
            )

        # --- Supabase ------------------------------------------------
        if self.has_supabase:
            add(
                "supabase",
                "Supabase (data store)",
                "ok",
                "The project URL and a server-side key are configured.",
                "SUPABASE_URL",
            )
        else:
            add(
                "supabase",
                "Supabase (data store)",
                "error",
                "The candidate inventory, the scoring matrix and the saved "
                "analyses are all read from Supabase. Without it the API can "
                "only serve the analytical endpoints.",
                "SUPABASE_URL",
                required=True,
            )

        if self.has_supabase_auth:
            add(
                "supabase_auth",
                "Google sign-in (Supabase Auth)",
                "ok",
                "Sessions can be verified.",
                "SUPABASE_ANON_KEY",
            )
        else:
            add(
                "supabase_auth",
                "Google sign-in (Supabase Auth)",
                "error",
                "Sign-in cannot be verified, so the user-owned endpoints are "
                "unavailable. Set the anon key, or the JWT secret for local "
                "verification.",
                "SUPABASE_ANON_KEY",
                required=True,
            )

        # --- Scoring matrix ------------------------------------------
        if self.normalized_matrix_file:
            add(
                "scoring_matrix",
                "Normalised scoring matrix",
                "ok",
                "Loaded from the configured file.",
                "NORMALIZED_MATRIX_FILE",
            )
        else:
            add(
                "scoring_matrix",
                "Normalised scoring matrix",
                "warning",
                "No file is configured, so the matrix is loaded from Supabase "
                "Storage. Every ranking depends on it.",
                "NORMALIZED_MATRIX_FILE",
            )

        # --- Groq ----------------------------------------------------
        if self.has_ai_provider:
            add(
                "groq",
                "AI requirement builder (Groq)",
                "ok",
                f"Configured, using the {self.groq_model} model.",
                "GROQ_API_KEY",
            )
        else:
            add(
                "groq",
                "AI requirement builder (Groq)",
                "warning",
                "Not configured. The assistant is unavailable and the manual "
                "requirement form is used instead. The platform is fully "
                "functional without it.",
                "GROQ_API_KEY",
            )

        # --- Routing --------------------------------------------------
        if self.ors_api_key:
            add(
                "ors",
                "Drive-time catchments (OpenRouteService)",
                "ok",
                "Configured.",
                "ORS_API_KEY",
            )
        else:
            add(
                "ors",
                "Drive-time catchments (OpenRouteService)",
                "warning",
                "Not configured, so catchments cannot be regenerated. Existing "
                "catchments remain usable.",
                "ORS_API_KEY",
            )

        # --- Property sources -----------------------------------------
        if self.has_property_source:
            add(
                "property_source",
                "Property feed",
                "ok",
                "A property feed is configured.",
                "PROPERTY_SOURCE_URL",
            )
        else:
            add(
                "property_source",
                "Property feed",
                "warning",
                "No feed is configured. Public map data and the manual "
                "source links are still available.",
                "PROPERTY_SOURCE_URL",
            )

        if self.property_manual_sources:
            add(
                "property_manual",
                "Property portals (manual navigation)",
                "ok",
                f"{len(self.property_manual_sources)} portal(s) available for manual search.",
                "PROPERTY_MANUAL_SOURCES",
            )
        else:
            add(
                "property_manual",
                "Property portals (manual navigation)",
                "warning",
                "No portals are configured, so a user cannot be given a direct "
                "search link for a source that cannot be queried automatically.",
                "PROPERTY_MANUAL_SOURCES",
            )

        if self.brokerage_manual_sources:
            add(
                "brokerage_manual",
                "Brokerages (manual navigation)",
                "ok",
                f"{len(self.brokerage_manual_sources)} brokerage source(s) available.",
                "BROKERAGE_MANUAL_SOURCES",
            )
        else:
            add(
                "brokerage_manual",
                "Brokerages (manual navigation)",
                "warning",
                "No brokerage sources are configured.",
                "BROKERAGE_MANUAL_SOURCES",
            )

        # --- Cost estimation -------------------------------------------
        if self.cost_estimation_enabled:
            add(
                "cost_estimation",
                "Cost estimation rules",
                "ok",
                "Enabled. Missing cost components may be estimated, and every "
                "estimated figure is labelled and shows the rule that produced it.",
                "COST_ESTIMATION_ENABLED",
            )
        else:
            add(
                "cost_estimation",
                "Cost estimation rules",
                "warning",
                "Disabled, which is the default. No cost component is estimated; "
                "an unknown component is reported as unavailable.",
                "COST_ESTIMATION_ENABLED",
            )

        # --- Observability --------------------------------------------
        if self.sentry_dsn:
            add(
                "sentry",
                "Error reporting (Sentry)",
                "ok",
                "Configured.",
                "SENTRY_DSN",
            )
        else:
            add(
                "sentry",
                "Error reporting (Sentry)",
                "warning",
                "Not configured. Errors are logged to the platform's own logs "
                "but are not tracked centrally.",
                "SENTRY_DSN",
            )

        if self.enable_metrics:
            add(
                "metrics",
                "Metrics (Prometheus)",
                "ok",
                "Exposed at /metrics.",
            )
        else:
            add(
                "metrics",
                "Metrics (Prometheus)",
                "warning",
                "Disabled.",
                "ENABLE_METRICS",
            )

        if self.allow_anonymous_api and self.is_production:
            add(
                "anonymous_api",
                "Anonymous API access",
                "error",
                "Enabled in a production environment. Every user-owned "
                "endpoint should require a session.",
                "ALLOW_ANONYMOUS_API",
            )
        elif self.allow_anonymous_api:
            add(
                "anonymous_api",
                "Anonymous API access",
                "warning",
                "Enabled for local development. The user-owned endpoints are "
                "unavailable without a session.",
                "ALLOW_ANONYMOUS_API",
            )

        return checks

    @property
    def configuration_is_valid(self) -> bool:
        """True when nothing is in an error state."""

        return not any(
            check["status"] == "error" for check in self.validation_report()
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""

    return Settings()
