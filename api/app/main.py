"""FastAPI application entrypoint for the Retail Site Intelligence platform.

Design notes
------------
* Sentry is initialised exactly once, with ``send_default_pii=False`` so
  demographic and site data never leave the platform.
* CORS origins come from configuration.  There is no placeholder production
  origin left in the code.
* Every router is imported directly.  A missing router is a hard startup
  failure rather than a silently degraded API, so partial deployments are
  impossible to miss.
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse


from app.core.config import get_settings
from app.routers import (
    brokerage,
    criteria,
    data_quality,
    decomposition,
    exports,
    elicitation,
    explanations,
    health,
    projects,
    properties,
    report_exports,
    reports,
    requirements,
    scenarios,
    scores,
    sensitivity,
    sites,
)

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("api")


def _init_sentry() -> None:
    """Initialise Sentry once, if a DSN is configured."""

    if not settings.sentry_dsn:
        logger.info("Sentry is not configured; error reporting is disabled.")
        return

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
    except ImportError:  # pragma: no cover - optional dependency
        logger.warning("sentry-sdk is not installed; error reporting is disabled.")
        return

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        integrations=[
            StarletteIntegration(transaction_style="endpoint"),
            FastApiIntegration(transaction_style="endpoint"),
        ],
        traces_sample_rate=settings.sentry_traces_sample_rate,
        environment=settings.environment,
        # Explicitly disabled: demographic and candidate-site data must not
        # be attached to error reports.
        send_default_pii=False,
    )
    logger.info("Sentry initialised for environment '%s'.", settings.environment)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: start-up and shutdown work."""

    _init_sentry()
    logger.info(
        "Retail Site Intelligence API starting (environment=%s).",
        settings.environment,
    )
    yield
    logger.info("Retail Site Intelligence API shutting down.")


app = FastAPI(
    title="Retail Site Intelligence & Site Selection API",
    version="2.0.0",
    description=(
        "Decision-support APIs for retail site selection: candidate-site "
        "inventory, deterministic multi-criteria scoring, requirement "
        "evaluation, cost analysis, explainability, sensitivity analysis and "
        "executive reporting."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Request-Id"],
)

if settings.enable_metrics:
    try:
        from prometheus_fastapi_instrumentator import Instrumentator

        Instrumentator().instrument(app).expose(app, include_in_schema=False)
    except ImportError:  # pragma: no cover - optional dependency
        logger.warning(
            "prometheus-fastapi-instrumentator is not installed; /metrics is disabled."
        )


@app.middleware("http")
async def request_timing_middleware(request: Request, call_next):
    """Attach a server-timing header and log slow requests.

    This keeps request-level performance visible without adding a new
    monitoring dependency: the value is also available to the existing
    Prometheus instrumentator.
    """

    started = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - started) * 1000
    response.headers["X-Response-Time-Ms"] = f"{elapsed_ms:.1f}"
    if elapsed_ms > 1000:
        logger.warning(
            "Slow request: %s %s took %.0f ms",
            request.method,
            request.url.path,
            elapsed_ms,
        )
    return response


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    """Translate deterministic validation failures into 422 responses.

    The scoring engine raises ``ValueError`` for genuine input problems
    (bad weights, unknown method, malformed matrices).  Surfacing them as
    500s would hide user-fixable errors from the interface.
    """

    logger.info("ValueError on %s: %s", request.url.path, exc)
    return JSONResponse(status_code=422, content={"detail": str(exc)})


# --- Router registration ---------------------------------------------------
app.include_router(health.router)
app.include_router(criteria.router)
app.include_router(projects.router)
app.include_router(sites.router)
app.include_router(scores.router)
app.include_router(decomposition.router)
app.include_router(requirements.router)
app.include_router(explanations.router)
app.include_router(properties.router)
app.include_router(brokerage.router)
app.include_router(data_quality.router)
app.include_router(reports.router)
app.include_router(exports.router)
app.include_router(report_exports.router)
app.include_router(scenarios.router)
app.include_router(sensitivity.router)
app.include_router(elicitation.router)


__all__ = ["app", "settings"]


