"""Report exports in PDF, CSV and Excel.

Every export carries the **exact** weighting configuration, aggregation
method and requirement set that produced the ranking, so a reader can
reproduce the result from the exported file alone.

The formats are produced with free, server-side libraries:

* CSV  - the standard library's writer, so the file opens in any tool.
* Excel - ``openpyxl``, with one sheet per section.
* PDF  - ``reportlab``, laid out as a professional decision document.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Optional, Sequence

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

MONEY_FORMAT = "#,##0.00"


def _number(value: Any, digits: int = 4) -> Optional[float]:
    try:
        if value is None:
            return None
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value)
    if isinstance(value, dict):
        return "; ".join(f"{key}: {item}" for key, item in value.items())
    return str(value)


def _flatten_weights(weights: Any) -> list[dict[str, Any]]:
    """Flatten a weight configuration into rows.

    Accepts the hierarchical form used by the scoring engine
    (``{"root": {...}, "category": {...}}``) as well as a flat mapping.
    """

    rows: list[dict[str, Any]] = []
    if not isinstance(weights, Mapping):
        return rows

    for parent, children in weights.items():
        # The hierarchical form: a category whose leaves carry the
        # weights.
        if isinstance(children, Mapping):
            for child, value in children.items():
                try:
                    numeric = float(value)
                except (TypeError, ValueError):
                    continue
                rows.append(
                    {
                        "level": str(parent),
                        "criterion": str(child),
                        "weight": round(numeric, 8),
                    }
                )
            continue

        # The flat form: a criterion whose weight is the value.  This is
        # the form the report carries, and it used to be dropped
        # silently, which left the exported weighting configuration
        # empty.
        try:
            numeric = float(children)
        except (TypeError, ValueError):
            continue
        rows.append(
            {
                "level": "criterion",
                "criterion": str(parent),
                "weight": round(numeric, 8),
            }
        )
    return rows


def _shortlist(report: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Return the ranked shortlist carried by the report.

    The report keeps the full ranking in ``shortlist`` and the narrative
    section in ``top_sites``.  An export has to carry the ranking that
    was produced, so the full list is used, with the narrative section
    as the fallback for a report that only has that.
    """

    shortlist = report.get("shortlist")
    if isinstance(shortlist, list) and shortlist:
        return shortlist
    return list(report.get("top_sites") or [])


def _report_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return the shortlist as flat rows, ready for a tabular export."""

    analysis = report.get("analysis") or {}
    rows: list[dict[str, Any]] = []

    for site in _shortlist(report):
        cost = site.get("cost") or {}
        totals = cost.get("totals") or {}
        rows.append(
            {
                "position": site.get("position"),
                "site_id": site.get("site_id"),
                "site_name": site.get("site_name"),
                "rank": site.get("rank"),
                "score": _number(site.get("score"), 6),
                "initial_investment": _number(totals.get("initial_investment_total"), 2),
                "monthly_cost": _number(totals.get("recurring_monthly_total"), 2),
                "annual_cost": _number(totals.get("recurring_annual_total"), 2),
                "cost_complete": totals.get("is_complete"),
                "why": site.get("why"),
                "caveats": _text(site.get("caveats")),
                "property_opportunities": len(site.get("property_opportunities") or []),
            }
        )

    return rows


def _export_context(report: Mapping[str, Any]) -> dict[str, Any]:
    analysis = report.get("analysis") or {}
    return {
        "analysis_name": analysis.get("name") or "Site selection analysis",
        "business_type": analysis.get("business_type"),
        "acquisition_mode": analysis.get("acquisition_mode"),
        "aggregation_method": analysis.get("aggregation_method"),
        "location": analysis.get("location"),
        "requirements": analysis.get("requirements"),
        "weights": analysis.get("weights"),
        "generated_at": report.get("generated_at")
        or datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------

SHORTLIST_COLUMNS = [
    ("position", "Position"),
    ("site_id", "Site ID"),
    ("site_name", "Site"),
    ("rank", "Rank"),
    ("score", "Multi-criteria score"),
    ("initial_investment", "Initial investment"),
    ("monthly_cost", "Monthly recurring cost"),
    ("annual_cost", "Annual recurring cost"),
    ("cost_complete", "Cost data complete"),
    ("property_opportunities", "Property opportunities found"),
    ("why", "Why this site"),
    ("caveats", "Caveats"),
]


def build_csv(report: Mapping[str, Any]) -> bytes:
    """Build the shortlist as a CSV file.

    The file contains the ranking, the cost position, the explanation and
    the weighting configuration, so it is self-describing.
    """

    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")

    context = _export_context(report)
    writer.writerow(["Retail Site Intelligence - Site Selection Report"])
    writer.writerow(["Analysis", context["analysis_name"]])
    writer.writerow(["Business type", context["business_type"] or "Not specified"])
    writer.writerow(["Acquisition mode", context["acquisition_mode"] or "either"])
    writer.writerow(["Aggregation method", context["aggregation_method"] or "weighted_sum"])
    writer.writerow(["Generated at", context["generated_at"]])
    writer.writerow([])

    writer.writerow(["RANKED SHORTLIST"])
    writer.writerow([label for _, label in SHORTLIST_COLUMNS])
    for row in _report_rows(report):
        writer.writerow([_text(row.get(key)) for key, _ in SHORTLIST_COLUMNS])
    writer.writerow([])

    writer.writerow(["WEIGHTING CONFIGURATION (used for this ranking)"])
    writer.writerow(["Level", "Criterion", "Weight"])
    for weight in _flatten_weights(context.get("weights")):
        writer.writerow(
            [weight["level"], weight["criterion"], weight["weight"]]
        )
    writer.writerow([])

    summary = report.get("executive_summary") or {}
    writer.writerow(["EXECUTIVE SUMMARY"])
    writer.writerow([summary.get("headline") or ""])
    for paragraph in summary.get("paragraphs") or []:
        writer.writerow([paragraph])
    writer.writerow([])

    writer.writerow(["ASSUMPTIONS"])
    for assumption in report.get("assumptions") or []:
        writer.writerow([assumption])
    writer.writerow([])

    writer.writerow(["LIMITATIONS"])
    for limitation in (report.get("data_quality") or {}).get("limitations") or []:
        writer.writerow([limitation.get("title"), limitation.get("detail")])

    return output.getvalue().encode("utf-8-sig")


# ---------------------------------------------------------------------------
# Excel
# ---------------------------------------------------------------------------

def build_excel(report: Mapping[str, Any]) -> bytes:
    """Build the report as an Excel workbook with one sheet per section."""

    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
    except ImportError:  # pragma: no cover - optional dependency
        raise RuntimeError("openpyxl is required to build an Excel export.")

    workbook = Workbook()
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="1D4ED8")
    wrap = Alignment(vertical="top", wrap_text=True)

    def style_header(sheet, row: int = 1) -> None:
        for cell in sheet[row]:
            if cell.value is not None:
                cell.font = header_font
                cell.fill = header_fill

    def autosize(sheet, maximum: int = 70) -> None:
        for column in sheet.columns:
            length = 0
            for cell in column:
                if cell.value is not None:
                    length = max(length, len(str(cell.value)))
            sheet.column_dimensions[column[0].column_letter].width = min(
                max(10, length + 2), maximum
            )

    # --- Overview -----------------------------------------------------
    overview = workbook.active
    overview.title = "Overview"
    context = _export_context(report)
    summary = report.get("executive_summary") or {}
    quality = report.get("data_quality") or {}
    quality_summary = quality.get("summary") or {}

    rows = [
        ("Analysis", context["analysis_name"]),
        ("Business type", context["business_type"] or "Not specified"),
        ("Acquisition mode", context["acquisition_mode"] or "either"),
        ("Aggregation method", context["aggregation_method"] or "weighted_sum"),
        ("Generated at", context["generated_at"]),
        ("Location", _text(context.get("location"))),
        ("Criteria coverage", quality_summary.get("criteria_coverage")),
        ("Overall data-quality grade", quality_summary.get("overall_grade")),
        ("Backtest available", quality_summary.get("backtest_available")),
        ("Summary", summary.get("headline")),
    ]
    for paragraph in summary.get("paragraphs") or []:
        rows.append(("", paragraph))
    for row in rows:
        overview.append(list(row))
    overview["A1"].font = Font(bold=True, size=14)
    overview["A2"].font = Font(bold=True)
    for index, (key, _) in enumerate(rows, start=1):
        if key:
            overview.cell(row=index, column=1).font = Font(bold=True)
    autosize(overview, 90)

    # --- Shortlist -----------------------------------------------------
    shortlist = workbook.create_sheet("Shortlist")
    shortlist.append([label for _, label in SHORTLIST_COLUMNS])
    for row in _report_rows(report):
        shortlist.append([row.get(key) for key, _ in SHORTLIST_COLUMNS])
    style_header(shortlist)
    autosize(shortlist)

    # --- Weights -------------------------------------------------------
    weights = workbook.create_sheet("Weights")
    weights.append(["Level", "Criterion", "Weight"])
    for weight in _flatten_weights(context.get("weights")):
        weights.append([weight["level"], weight["criterion"], weight["weight"]])
    style_header(weights)
    autosize(weights)

    # --- Requirements --------------------------------------------------
    requirements = workbook.create_sheet("Requirements")
    requirements.append(["Section", "Item", "Importance", "Value"])
    requirement_block = context.get("requirements") or {}
    for item in requirement_block.get("business_requirements") or []:
        requirements.append(
            [
                "Business",
                item.get("label") or item.get("key"),
                item.get("importance"),
                _text(item.get("value")),
            ]
        )
    for item in requirement_block.get("facilities") or []:
        requirements.append(
            [
                "Facility",
                item.get("label") or item.get("key"),
                item.get("importance"),
                "",
            ]
        )
    parking = requirement_block.get("parking") or {}
    for key, value in parking.items():
        requirements.append(["Parking", key, "setting", _text(value)])
    for key, value in (requirement_block.get("financial") or {}).items():
        requirements.append(["Financial", key, "budget", _text(value)])
    style_header(requirements)
    autosize(requirements)

    # --- Costs ---------------------------------------------------------
    costs = workbook.create_sheet("Cost analysis")
    costs.append(
        [
            "Site ID",
            "Category",
            "Item",
            "Amount",
            "Provenance",
            "Source",
            "Note",
        ]
    )
    for item in report.get("cost_analysis") or []:
        for line in item.get("lines") or []:
            costs.append(
                [
                    item.get("site_id"),
                    line.get("category"),
                    line.get("label"),
                    _number(line.get("amount"), 2),
                    line.get("provenance_label"),
                    line.get("source"),
                    line.get("note"),
                ]
            )
    style_header(costs)
    autosize(costs)

    # --- Property opportunities ---------------------------------------
    properties = workbook.create_sheet("Property opportunities")
    properties.append(
        [
            "Site ID",
            "Title",
            "Source",
            "Location",
            "Area (sq ft)",
            "Purchase price",
            "Monthly rent",
            "Broker / agency",
            "Contact",
            "Listing URL",
            "Retrieved at",
            "Price provenance",
        ]
    )
    for entry in (report.get("property_intelligence") or {}).get("sites") or []:
        for opportunity in entry.get("opportunities") or []:
            properties.append(
                [
                    entry.get("site_id"),
                    opportunity.get("title"),
                    opportunity.get("source_label"),
                    opportunity.get("location"),
                    _number(opportunity.get("area_sqft"), 0),
                    _number(opportunity.get("purchase_price"), 2),
                    _number(opportunity.get("monthly_rent"), 2),
                    opportunity.get("broker_name"),
                    opportunity.get("broker_contact"),
                    opportunity.get("source_url"),
                    opportunity.get("retrieved_at"),
                    opportunity.get("price_provenance"),
                ]
            )
    style_header(properties)
    autosize(properties)

    # --- Data quality --------------------------------------------------
    quality_sheet = workbook.create_sheet("Data quality")
    quality_sheet.append(["Severity", "Limitation", "Detail"])
    for limitation in quality.get("limitations") or []:
        quality_sheet.append(
            [limitation.get("severity"), limitation.get("title"), limitation.get("detail")]
        )
    quality_sheet.append([])
    quality_sheet.append(["Assumption", "Detail"])
    for assumption in report.get("assumptions") or []:
        quality_sheet.append(["", assumption])
    style_header(quality_sheet)
    autosize(quality_sheet, 100)

    # --- Sensitivity ---------------------------------------------------
    sensitivity = workbook.create_sheet("Sensitivity")
    sensitivity.append(["Measure", "Value"])
    sensitivity_block = report.get("sensitivity") or {}
    for key, value in sensitivity_block.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            sensitivity.append([key, _text(value)])
    style_header(sensitivity)
    autosize(sensitivity, 100)

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

def build_pdf(report: Mapping[str, Any]) -> bytes:
    """Build the report as a professional PDF decision document."""

    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            KeepTogether,
            PageBreak,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError:  # pragma: no cover - optional dependency
        raise RuntimeError("reportlab is required to build a PDF export.")

    context = _export_context(report)
    quality = report.get("data_quality") or {}

    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=context["analysis_name"],
        author="Retail Site Intelligence",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "Title",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=19,
        leading=23,
        textColor=colors.HexColor("#111820"),
        spaceAfter=2,
        alignment=TA_LEFT,
    )
    subtitle_style = ParagraphStyle(
        "Subtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor("#57616F"),
        spaceAfter=10,
    )
    heading_style = ParagraphStyle(
        "Heading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        textColor=colors.HexColor("#111820"),
        spaceBefore=14,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "Body",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=14,
        textColor=colors.HexColor("#111820"),
        spaceAfter=6,
    )
    small_style = ParagraphStyle(
        "Small",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#57616F"),
        spaceAfter=4,
    )
    callout_style = ParagraphStyle(
        "Callout",
        parent=body_style,
        fontName="Helvetica-Oblique",
        textColor=colors.HexColor("#12499F"),
        backColor=colors.HexColor("#E9F0FD"),
        borderPadding=7,
        borderColor=colors.HexColor("#A9C6F5"),
        borderWidth=0.6,
        spaceBefore=8,
        spaceAfter=8,
    )

    story: list[Any] = []

    # --- Cover --------------------------------------------------------
    story.append(Paragraph(context["analysis_name"], title_style))
    story.append(
        Paragraph(
            "Retail Site Intelligence &amp; Site Selection &mdash; executive decision report",
            subtitle_style,
        )
    )

    summary = report.get("executive_summary") or {}
    story.append(Paragraph("Executive summary", heading_style))
    story.append(Paragraph(_text(summary.get("headline")), body_style))
    for paragraph in summary.get("paragraphs") or []:
        story.append(Paragraph(_text(paragraph), body_style))

    recommendation = summary.get("recommendation") or {}
    if recommendation.get("next_steps"):
        story.append(Paragraph("Recommended next steps", heading_style))
        for step in recommendation["next_steps"]:
            story.append(Paragraph(f"&bull;&nbsp;{_text(step)}", body_style))

    # --- Scope --------------------------------------------------------
    story.append(Paragraph("Scope of the analysis", heading_style))
    scope_rows = [
        ["Business type", _text(context.get("business_type")) or "Not specified"],
        ["Acquisition mode", _text(context.get("acquisition_mode")) or "either"],
        ["Aggregation method", _text(context.get("aggregation_method")) or "weighted_sum"],
        ["Search area", _text(context.get("location")) or "Not specified"],
        ["Generated", _text(context.get("generated_at"))],
    ]
    story.append(_pdf_table(scope_rows, styles))

    # --- Shortlist ----------------------------------------------------
    story.append(Paragraph("Ranked shortlist", heading_style))
    shortlist_rows = [["#", "Site", "Score", "Initial investment", "Monthly cost"]]
    for site in _shortlist(report):
        cost = site.get("cost") or {}
        totals = cost.get("totals") or {}
        shortlist_rows.append(
            [
                _text(site.get("position")),
                _text(site.get("site_name")),
                _text(_number(site.get("score"), 4)),
                _text(_number(totals.get("initial_investment_total"), 0)),
                _text(_number(totals.get("recurring_monthly_total"), 0)),
            ]
        )
    story.append(_pdf_table(shortlist_rows, styles, numeric_from=2))

    # --- Why the sites ------------------------------------------------
    for site in report.get("top_sites") or []:
        block = [Paragraph(f"{site.get('position')}. {_text(site.get('site_name'))}", heading_style)]
        if site.get("why"):
            block.append(Paragraph(_text(site["why"]), body_style))
        if site.get("caveats"):
            block.append(Paragraph("Caveats", small_style))
            for caveat in site["caveats"]:
                block.append(Paragraph(f"&bull;&nbsp;{_text(caveat)}", small_style))
        story.append(KeepTogether(block))

    # --- Weighting ----------------------------------------------------
    story.append(Paragraph("Weighting configuration", heading_style))
    story.append(
        Paragraph(
            "These are the exact weights that produced the ranking above. "
            "The ranking is reproducible from them and the aggregation method.",
            small_style,
        )
    )
    weight_rows = [["Level", "Criterion", "Weight"]]
    for weight in _flatten_weights(context.get("weights")):
        weight_rows.append(
            [weight["level"], weight["criterion"], f"{weight['weight']:.6f}"]
        )
    if len(weight_rows) > 1:
        story.append(_pdf_table(weight_rows, styles, numeric_from=2))

    # --- Cost analysis ------------------------------------------------
    cost_rows = [["Site", "Item", "Amount", "Provenance"]]
    for item in report.get("cost_analysis") or []:
        for line in item.get("lines") or []:
            cost_rows.append(
                [
                    _text(item.get("site_id")),
                    _text(line.get("label")),
                    _text(_number(line.get("amount"), 2)),
                    _text(line.get("provenance_label")),
                ]
            )
    if len(cost_rows) > 1:
        story.append(PageBreak())
        story.append(Paragraph("Cost analysis", heading_style))
        story.append(_pdf_table(cost_rows, styles, numeric_from=2))

    # --- Property intelligence ----------------------------------------
    property_intel = report.get("property_intelligence") or {}
    story.append(Paragraph("Property and brokerage opportunities", heading_style))
    property_rows = [["Site", "Title", "Source", "Location", "Price", "Broker"]]
    for entry in property_intel.get("sites") or []:
        for opportunity in entry.get("opportunities") or []:
            price = opportunity.get("purchase_price") or opportunity.get("monthly_rent")
            property_rows.append(
                [
                    _text(entry.get("site_name") or entry.get("site_id")),
                    _text(opportunity.get("title")),
                    _text(opportunity.get("source_label")),
                    _text(opportunity.get("location")),
                    _text(_number(price, 2)),
                    _text(opportunity.get("broker_name")),
                ]
            )
    if len(property_rows) > 1:
        story.append(_pdf_table(property_rows, styles, numeric_from=4))
    else:
        story.append(
            Paragraph(
                "No external property or brokerage opportunity was returned for the "
                "recommended locations. The source status for each search is "
                "recorded in the data-quality section.",
                body_style,
            )
        )

    # --- Data quality -------------------------------------------------
    story.append(Paragraph("Data quality and limitations", heading_style))
    limitation_rows = [["Severity", "Limitation", "Detail"]]
    for limitation in quality.get("limitations") or []:
        limitation_rows.append(
            [
                _text(limitation.get("severity")),
                _text(limitation.get("title")),
                _text(limitation.get("detail")),
            ]
        )
    story.append(_pdf_table(limitation_rows, styles))

    # --- Assumptions --------------------------------------------------
    assumptions = report.get("assumptions") or []
    if assumptions:
        story.append(Paragraph("Assumptions", heading_style))
        for assumption in assumptions:
            story.append(Paragraph(f"&bull;&nbsp;{_text(assumption)}", body_style))

    # --- Statement ----------------------------------------------------
    story.append(
        Paragraph(
            _text(report.get("statement"))
            or "This report is decision support produced by a deterministic "
            "multi-criteria analysis. It does not replace site visits, "
            "commercial due diligence or local market knowledge.",
            callout_style,
        )
    )

    document.build(story)
    return buffer.getvalue()


def _pdf_table(rows: Sequence[Sequence[Any]], styles: Any, numeric_from: int = 1) -> Any:
    """Build a styled table for the PDF document."""

    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle

    table = Table(
        [list(row) for row in rows],
        repeatRows=1,
        hAlign="LEFT",
    )
    table_style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1D4ED8")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("LEADING", (0, 0), (-1, -1), 11),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E0E4EA")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F9FB")]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]
    for index in range(1, len(rows)):
        for column in range(numeric_from, len(rows[index])):
            table_style.append(
                ("ALIGN", (column, index), (column, index), "RIGHT")
            )
    table.setStyle(TableStyle(table_style))
    return table


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

FORMATS = {
    "csv": ("text/csv; charset=utf-8", "csv"),
    "xlsx": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xlsx",
    ),
    "pdf": ("application/pdf", "pdf"),
    "json": ("application/json", "json"),
}


def build_export(report: Mapping[str, Any], export_format: str) -> tuple[bytes, str, str]:
    """Build an export in the requested format.

    Returns:
        The file content, the media type and the file extension.
    """

    key = export_format.strip().lower()
    if key not in FORMATS:
        raise ValueError(
            f"Unsupported export format {export_format!r}. Choose one of: "
            + ", ".join(sorted(FORMATS))
        )

    if key == "csv":
        content = build_csv(report)
    elif key == "xlsx":
        content = build_excel(report)
    elif key == "pdf":
        content = build_pdf(report)
    else:
        content = json.dumps(report, indent=2, default=str).encode("utf-8")

    media_type, extension = FORMATS[key]
    return content, media_type, extension


def export_filename(report: Mapping[str, Any], extension: str) -> str:
    """Build a safe, descriptive file name for an export."""

    context = _export_context(report)
    slug = "".join(
        character if character.isalnum() else "-"
        for character in str(context["analysis_name"]).lower()
    ).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    slug = slug or "site-selection"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    return f"{slug}-{stamp}.{extension}"


__all__ = [
    "FORMATS",
    "build_csv",
    "build_excel",
    "build_export",
    "build_pdf",
    "export_filename",
]
