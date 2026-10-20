"""Executive report exports in PDF, CSV and Excel.

The export is built from the same report payload the interface shows, so
what is exported is exactly what was presented.  The exported file always
contains the weighting configuration, the aggregation method and the
requirement set that produced the ranking, so the result is reproducible
from the file alone.

The reproducible *ranking* export lives in
:mod:`api.app.routers.exports`; this router renders the executive report.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.domain.exports import build_export, export_filename

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reports", tags=["Reporting"])

FORMATS = ("pdf", "csv", "xlsx", "json")


class ExportRequest(BaseModel):
    """The report payload to export."""

    report: dict[str, Any] = Field(
        default_factory=dict,
        description="The report payload, as produced by POST /reports/generate.",
    )
    format: str = Field(
        default="pdf",
        description="The export format: pdf, csv, xlsx or json.",
    )


@router.post(
    "/export",
    summary="Export the executive report",
    response_description="The exported file.",
    responses={
        200: {
            "content": {
                "application/pdf": {},
                "text/csv": {},
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {},
                "application/json": {},
            }
        }
    },
)
def export_report(payload: ExportRequest) -> Response:
    """Export a report as PDF, CSV, Excel or JSON."""

    export_format = payload.format.strip().lower()
    if export_format not in FORMATS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unsupported export format {payload.format!r}. Choose one of: "
                + ", ".join(FORMATS)
            ),
        )

    report = payload.report
    if not report:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "There is nothing to export. Generate the report first and "
                "export the result."
            ),
        )

    try:
        content, media_type, extension = build_export(report, export_format)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"The export could not be produced: {exc}",
        ) from exc
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("The export failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"The export could not be produced: {exc}",
        ) from exc

    filename = export_filename(report, extension)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export/formats", summary="The available report export formats")
def list_formats() -> dict[str, Any]:
    """Describe the export formats the API can produce."""

    return {
        "formats": [
            {
                "key": "pdf",
                "label": "PDF",
                "media_type": "application/pdf",
                "description": (
                    "A paginated decision document for circulation to "
                    "management and property teams."
                ),
            },
            {
                "key": "csv",
                "label": "CSV",
                "media_type": "text/csv",
                "description": (
                    "The ranked shortlist, the weighting configuration and the "
                    "assumptions, in a spreadsheet-friendly form."
                ),
            },
            {
                "key": "xlsx",
                "label": "Excel",
                "media_type": (
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                ),
                "description": (
                    "A workbook with one sheet per section: overview, shortlist, "
                    "weights, requirements, costs, property opportunities, data "
                    "quality and sensitivity."
                ),
            },
            {
                "key": "json",
                "label": "JSON",
                "media_type": "application/json",
                "description": (
                    "The complete report payload, for programmatic use and for "
                    "archiving."
                ),
            },
        ]
    }


__all__ = ["router"]

