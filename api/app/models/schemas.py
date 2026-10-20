"""Shared Pydantic schemas.

The response models that are shared by more than one router live here so
that the API contract is defined in one place.  Router-specific request
and response models stay with the router that owns them.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class Provenance(BaseModel):
    """How a figure was obtained.

    The interface must never present an estimate as a verified fact, so
    every monetary figure carries one of these.
    """

    verified_listed: str = Field(
        default="verified_listed",
        description="The value is published by the source and has not been altered.",
    )
    user_provided: str = Field(
        default="user_provided",
        description="The value was entered by the user.",
    )
    estimated: str = Field(
        default="estimated",
        description="The value is a modelled estimate and is indicative only.",
    )
    calculated: str = Field(
        default="calculated",
        description="The value is arithmetic over other known values.",
    )
    unavailable: str = Field(
        default="unavailable",
        description="No defensible value could be established.",
    )


class StatusValue(BaseModel):
    """A value together with the status that explains its reliability."""

    value: Optional[float] = None
    status: str = Field(
        default="unavailable",
        description="One of: pass, fail, warning, unknown, not_applicable.",
    )
    detail: str = ""


class ErrorResponse(BaseModel):
    """The shape of a failed request."""

    detail: str


class HealthResponse(BaseModel):
    """The liveness probe response."""

    status: str
    service: str
    version: str
    environment: str
    uptime_seconds: float


class CoverageSummary(BaseModel):
    """How much of the configured model the available data can support."""

    criteria_coverage: float = Field(
        default=0.0,
        description="The share of the requested weight mass that could be scored.",
    )
    criteria_coverage_grade: str = "poor"
    usable_source_count: int = 0
    total_source_count: int = 0
    matrix_available: bool = False
    backtest_available: bool = False
    overall_grade: str = "poor"
    grading_rule: str = ""


class Limitation(BaseModel):
    """A documented limitation of the platform's evidence base."""

    id: str
    severity: str = Field(default="medium", description="high, medium or low.")
    title: str
    detail: str


class SourceCoverage(BaseModel):
    """The availability of one underlying dataset."""

    table: str
    label: str
    origin: str
    available: bool
    has_rows: bool
    note: str = ""


class Disclaimer(BaseModel):
    """A statement that qualifies a set of results."""

    text: str
    applies_to: list[str] = Field(default_factory=list)


__all__ = [
    "CoverageSummary",
    "Disclaimer",
    "ErrorResponse",
    "HealthResponse",
    "Limitation",
    "Provenance",
    "SourceCoverage",
    "StatusValue",
]

