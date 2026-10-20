"""Executive decision report API.

The report is assembled from the deterministic results the platform has
already produced.  The endpoint accepts the analysis context that the
interface already holds, recomputes nothing that is already known, and
returns the report in JSON, Markdown or printable HTML.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, Field

from app.domain.reporting import build_report, render_html, render_markdown

router = APIRouter(prefix="/reports", tags=["Reporting"])


class ReportRequest(BaseModel):
    """The analysis context and computed results that make up a report."""

    analysis: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "The analysis context: name, business type, acquisition mode, "
            "location, requirements, weights and aggregation method."
        ),
    )
    ranking: list[dict[str, Any]] = Field(
        default_factory=list,
        description="The ranked sites, best first.",
    )
    explanations: list[dict[str, Any]] = Field(
        default_factory=list,
        description="The per-site explanations produced by the explainability API.",
    )
    cost_assessments: list[dict[str, Any]] = Field(default_factory=list)
    property_results: list[dict[str, Any]] = Field(default_factory=list)
    sensitivity: dict[str, Any] = Field(default_factory=dict)
    data_quality: dict[str, Any] = Field(default_factory=dict)
    comparison: dict[str, Any] = Field(default_factory=dict)


def _build(payload: ReportRequest) -> dict[str, Any]:
    return build_report(
        analysis=payload.analysis,
        ranking=payload.ranking,
        explanations=payload.explanations,
        cost_assessments=payload.cost_assessments,
        property_results=payload.property_results,
        sensitivity=payload.sensitivity,
        data_quality=payload.data_quality,
        comparison=payload.comparison,
    )


@router.post("/generate", summary="Generate an executive decision report")
def generate_report(payload: ReportRequest) -> dict[str, Any]:
    """Return the executive report as structured JSON."""

    if not payload.ranking:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "A report needs a ranking. Run the analysis before generating "
                "the report."
            ),
        )
    return _build(payload)


@router.post(
    "/generate/markdown",
    summary="Generate the executive report as Markdown",
    response_class=PlainTextResponse,
)
def generate_report_markdown(payload: ReportRequest) -> str:
    """Return the executive report as Markdown."""

    if not payload.ranking:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "A report needs a ranking. Run the analysis before generating "
                "the report."
            ),
        )
    return render_markdown(_build(payload))


@router.post(
    "/generate/html",
    summary="Generate the executive report as printable HTML",
    response_class=HTMLResponse,
)
def generate_report_html(payload: ReportRequest) -> HTMLResponse:
    """Return the executive report as a self-contained printable document."""

    if not payload.ranking:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "A report needs a ranking. Run the analysis before generating "
                "the report."
            ),
        )
    return HTMLResponse(content=render_html(_build(payload)))


__all__ = ["router"]

