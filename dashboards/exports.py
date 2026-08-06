"""
CSV and PDF report exporters (FR-11).

Both writers go through ``Complaint.complainant_display(viewer)``, so an
anonymous complainant can never leak into an HOD's export.
"""

import csv
import io

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

COLUMNS = [
    "Reference",
    "Subject",
    "Category",
    "Department",
    "Status",
    "Complainant",
    "Assigned To",
    "Submitted",
    "Resolved (hrs)",
]


def _row(complaint, viewer):
    return [
        complaint.reference,
        complaint.subject,
        complaint.get_category_display(),
        complaint.department.name,
        complaint.get_status_display(),
        complaint.complainant_display(viewer),
        complaint.assigned_to.get_full_name() if complaint.assigned_to_id else "-",
        timezone.localtime(complaint.created_at).strftime("%Y-%m-%d %H:%M"),
        complaint.resolution_hours if complaint.resolution_hours is not None else "-",
    ]


def _filename(extension):
    stamp = timezone.localtime().strftime("%Y%m%d-%H%M")
    return f"complaint-report-{stamp}.{extension}"


def complaints_to_csv(complaints, *, viewer):
    """Stream the filtered complaint set as CSV."""
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{_filename("csv")}"'
    response.write("﻿")  # BOM so Excel reads UTF-8 correctly

    writer = csv.writer(response)
    writer.writerow(COLUMNS)
    for complaint in complaints:
        writer.writerow(_row(complaint, viewer))
    return response


def complaints_to_pdf(complaints, *, viewer):
    """Render the filtered complaint set as a landscape A4 PDF."""
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title="Complaint Report",
        author=settings.INSTITUTION_NAME,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle", parent=styles["Title"], fontSize=15, alignment=TA_CENTER
    )
    meta_style = ParagraphStyle(
        "ReportMeta", parent=styles["Normal"], fontSize=8.5, alignment=TA_CENTER,
        textColor=colors.HexColor("#5a6169"),
    )
    cell_style = ParagraphStyle(
        "Cell", parent=styles["Normal"], fontSize=7.5, leading=9.5
    )
    header_style = ParagraphStyle(
        "CellHead",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        textColor=colors.white,
        fontName="Helvetica-Bold",
    )

    scope = (
        viewer.department.name
        if getattr(viewer, "is_hod", False) and viewer.department_id
        else "All departments"
    )

    story = [
        Paragraph(settings.INSTITUTION_NAME, title_style),
        Paragraph("Complaint Report", meta_style),
        Spacer(1, 4),
        Paragraph(
            f"Scope: {scope} &nbsp;|&nbsp; Records: {len(complaints)} "
            f"&nbsp;|&nbsp; Generated: "
            f"{timezone.localtime().strftime('%d %b %Y, %H:%M')} "
            f"by {viewer.get_full_name()}",
            meta_style,
        ),
        Spacer(1, 10),
    ]

    data = [[Paragraph(column, header_style) for column in COLUMNS]]
    for complaint in complaints:
        data.append(
            [Paragraph(str(value), cell_style) for value in _row(complaint, viewer)]
        )

    column_widths = [26 * mm, 58 * mm, 22 * mm, 36 * mm, 22 * mm, 34 * mm, 32 * mm, 26 * mm, 18 * mm]
    table = Table(data, colWidths=column_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#7b1030")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#c9ced4")),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.white, colors.HexColor("#f4f5f7")],
                ),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(table)
    document.build(story)

    pdf = buffer.getvalue()
    buffer.close()

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{_filename("pdf")}"'
    return response
