"""
pdf_report.py
────────────────────────────────────────────────────────────────────────────
Generates real, downloadable PDF documents for the PainVoice app:

  - build_medical_report_pdf()        -> the "Generate Medical Report" page
  - build_effectiveness_report_pdf()  -> the "Treatment Effectiveness" page

Both return raw PDF bytes, ready to hand to st.download_button.
"""

import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
)

BRAND_BLUE = colors.HexColor("#1C97D6")
BRAND_BLUE_BG = colors.HexColor("#EAF7FD")
RED = colors.HexColor("#D42525")
RED_BG = colors.HexColor("#FDF4F4")
GREEN = colors.HexColor("#1FA34D")
GREEN_BG = colors.HexColor("#F4FCF4")
INK = colors.HexColor("#171A1C")
SUB = colors.HexColor("#5B6470")
MUTED = colors.HexColor("#8A929C")
BORDER = colors.HexColor("#E7E8EA")

_styles = getSampleStyleSheet()
_styles.add(ParagraphStyle("PVTitle", parent=_styles["Title"], fontSize=16,
                            textColor=BRAND_BLUE, spaceAfter=2, alignment=0))
_styles.add(ParagraphStyle("PVSubtitle", parent=_styles["Normal"], fontSize=8.5,
                            textColor=MUTED, spaceAfter=4))
_styles.add(ParagraphStyle("PVSectionHeader", parent=_styles["Normal"], fontSize=9,
                            textColor=SUB, spaceBefore=10, spaceAfter=4, fontName="Helvetica-Bold"))
_styles.add(ParagraphStyle("PVLabel", parent=_styles["Normal"], fontSize=7.5, textColor=MUTED))
_styles.add(ParagraphStyle("PVValue", parent=_styles["Normal"], fontSize=10,
                            textColor=INK, fontName="Helvetica-Bold"))
_styles.add(ParagraphStyle("PVBody", parent=_styles["Normal"], fontSize=9.5,
                            textColor=INK, leading=14))
_styles.add(ParagraphStyle("PVSignature", parent=_styles["Normal"], fontSize=10,
                            textColor=INK, fontName="Helvetica-Oblique"))


def _header_block(report_id: str):
    flow = []
    header_tbl = Table(
        [[
            Paragraph("PAINVOICE CLINICAL AI", _styles["PVTitle"]),
            Paragraph(f"<b>Report ID</b><br/>{report_id}", _styles["PVLabel"]),
        ]],
        colWidths=[4.2 * inch, 2.3 * inch],
    )
    header_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
    ]))
    flow.append(header_tbl)
    flow.append(Paragraph("Standardized Voice-Based Pain Classification System", _styles["PVSubtitle"]))
    flow.append(HRFlowable(width="100%", thickness=1, color=BORDER, spaceAfter=8))
    return flow


def _demographics_table(p: dict):
    data = [
        [Paragraph("FULL NAME", _styles["PVLabel"]), Paragraph("DATE OF BIRTH", _styles["PVLabel"]),
         Paragraph("GENDER", _styles["PVLabel"]), Paragraph("CLINICAL ID", _styles["PVLabel"])],
        [Paragraph(p["name"], _styles["PVValue"]), Paragraph(p["dob"], _styles["PVValue"]),
         Paragraph(p["gender"], _styles["PVValue"]), Paragraph(p["id"], _styles["PVValue"])],
    ]
    tbl = Table(data, colWidths=[1.7 * inch, 1.7 * inch, 1.5 * inch, 1.5 * inch])
    tbl.setStyle(TableStyle([
        ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
        ("TOPPADDING", (0, 1), (-1, 1), 0),
    ]))
    return tbl


def _result_box(label: str, confidence: float, duration_sec, date_str: str, is_high: bool):
    bg = RED_BG if is_high else GREEN_BG
    fg = RED if is_high else GREEN
    data = [[
        Paragraph(f'<font color="{fg.hexval()}"><b>DETECTED CLASSIFICATION</b></font><br/>'
                  f'<font color="{fg.hexval()}" size="16"><b>{label}</b></font>', _styles["PVBody"]),
        Paragraph(f"<b>Confidence</b><br/>{confidence:.1f}%", _styles["PVBody"]),
        Paragraph(f"<b>Duration</b><br/>{duration_sec}s", _styles["PVBody"]),
        Paragraph(f"<b>Date</b><br/>{date_str}", _styles["PVBody"]),
    ]]
    tbl = Table(data, colWidths=[2.4 * inch, 1.4 * inch, 1.2 * inch, 1.4 * inch])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (0, 0), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("ROUNDEDCORNERS", [8, 8, 8, 8]),
    ]))
    return tbl


def _biomarkers_table(biomarkers):
    row = [Paragraph(f"<b>{b['label']}</b><br/>{b['value']}<br/>"
                      f'<font size="7.5" color="{SUB.hexval()}">{b["note"]}</font>', _styles["PVBody"])
           for b in biomarkers]
    tbl = Table([row], colWidths=[2.13 * inch] * len(row))
    tbl.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return tbl


def build_medical_report_pdf(patient: dict, result: dict | None, clinician: dict, is_high: bool) -> bytes:
    """Build the clinical session report PDF. `result` is the dict returned by
    PainVoiceAnalyzer.analyze() for the active session (may be None if no live
    session was recorded, in which case placeholder values are shown)."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        leftMargin=0.7 * inch, rightMargin=0.7 * inch,
        topMargin=0.6 * inch, bottomMargin=0.6 * inch,
        title=f"PainVoice Medical Report — {patient['name']}",
    )

    report_id = f"{patient['id']}-{datetime.now().strftime('%Y%m%d')}"
    label = result["label"] if result else ("High Pain" if is_high else "Low Pain")
    confidence = result["confidence"] if result else 89.4
    duration = result["duration_sec"] if result else 10.4
    biomarkers = result["biomarkers"] if result else []

    story = []
    story += _header_block(report_id)

    story.append(Paragraph("PATIENT DEMOGRAPHICS", _styles["PVSectionHeader"]))
    story.append(_demographics_table(patient))

    story.append(Paragraph("AI SPEECH ANALYSIS RESULTS", _styles["PVSectionHeader"]))
    story.append(_result_box(label, confidence, duration, datetime.now().strftime("%b %d, %Y"), is_high))

    if biomarkers:
        story.append(Spacer(1, 8))
        story.append(Paragraph("ACOUSTIC BIOMARKERS DETECTED", _styles["PVSectionHeader"]))
        story.append(_biomarkers_table(biomarkers))
    if result is not None:
        story.append(Spacer(1, 6))
        note = "Model weights are randomly initialized (no trained checkpoint present)." \
            if not result.get("is_trained") else "Model is running trained weights."
        story.append(Paragraph(f'<font size="7.5" color="{MUTED.hexval()}"><i>{note}</i></font>', _styles["PVBody"]))

    story.append(Paragraph("CLINICIAN ASSESSMENT", _styles["PVSectionHeader"]))
    story.append(Paragraph(
        f"Patient presented with {patient['condition'].lower()}. Voice recording captured during "
        f"standard assessment. AI classification aligns with clinical observation of "
        f"{'guarding behaviors and restricted vocal cadence' if is_high else 'relaxed posture and steady vocal cadence'}. "
        f"No acute respiratory distress noted. Cognitive status remains stable.",
        _styles["PVBody"],
    ))

    story.append(Paragraph("TREATMENT PLAN & FOLLOW-UP", _styles["PVSectionHeader"]))
    tp_tbl = Table(
        [[
            Paragraph(f'<font color="{BRAND_BLUE.hexval()}" size="7.5"><b>PRESCRIBED REGIMEN</b></font><br/>'
                      f"{patient['care_plan']}", _styles["PVBody"]),
            Paragraph(f'<font size="7.5" color="{MUTED.hexval()}">NEXT CLINICAL REVIEW</font><br/>'
                      f"{patient['next_titration']} — re-evaluation of pain trends required", _styles["PVBody"]),
        ]],
        colWidths=[3.1 * inch, 3.1 * inch],
    )
    tp_tbl.setStyle(TableStyle([
        ("BOX", (0, 0), (0, 0), 0.5, BRAND_BLUE),
        ("BOX", (1, 0), (1, 0), 0.5, BORDER),
        ("BACKGROUND", (0, 0), (0, 0), BRAND_BLUE_BG),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(tp_tbl)

    story.append(Spacer(1, 18))
    story.append(HRFlowable(width="100%", thickness=1, color=BORDER, spaceAfter=8))
    story.append(Paragraph(f"Dr. {clinician['name']}", _styles["PVSignature"]))
    story.append(Paragraph(f'<font size="7" color="{MUTED.hexval()}">DIGITAL ATTESTATION &nbsp;•&nbsp; '
                            f'{datetime.now().strftime("%b %d, %Y %I:%M %p")}</font>', _styles["PVBody"]))

    doc.build(story)
    return buf.getvalue()


def build_effectiveness_report_pdf(patient: dict, clinician: dict) -> bytes:
    """Build a treatment-effectiveness summary PDF (session history + trend stats)."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        leftMargin=0.7 * inch, rightMargin=0.7 * inch,
        topMargin=0.6 * inch, bottomMargin=0.6 * inch,
        title=f"PainVoice Treatment Effectiveness — {patient['name']}",
    )
    report_id = f"{patient['id']}-EFF-{datetime.now().strftime('%Y%m%d')}"

    story = []
    story += _header_block(report_id)
    story.append(Paragraph("Treatment Effectiveness Report", _styles["PVSectionHeader"]))
    story.append(_demographics_table(patient))

    story.append(Paragraph("SUMMARY METRICS", _styles["PVSectionHeader"]))
    summary_tbl = Table(
        [[
            Paragraph(f"<b>Average Pain (30D)</b><br/>{patient['avg_pain_30d']}", _styles["PVBody"]),
            Paragraph(f"<b>Adherence Rate</b><br/>{patient['adherence']}%", _styles["PVBody"]),
            Paragraph(f"<b>AI Accuracy Avg</b><br/>{patient['ai_accuracy']}%", _styles["PVBody"]),
            Paragraph(f"<b>Sessions Logged</b><br/>{len(patient['sessions'])}", _styles["PVBody"]),
        ]],
        colWidths=[1.55 * inch] * 4,
    )
    summary_tbl.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(summary_tbl)

    story.append(Paragraph("SESSION HISTORY", _styles["PVSectionHeader"]))
    if patient["sessions"]:
        rows = [["Date", "Time", "Classification", "Level", "Confidence", "Duration"]]
        for s in patient["sessions"]:
            rows.append([s["date"], s["time"], s["classification"], str(s["level"]),
                         f"{s['confidence']}%", s["duration"]])
        sess_tbl = Table(rows, colWidths=[1.1 * inch, 0.9 * inch, 1.5 * inch, 0.7 * inch, 1.0 * inch, 1.0 * inch])
        sess_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BRAND_BLUE_BG),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(sess_tbl)
    else:
        story.append(Paragraph("No sessions recorded yet.", _styles["PVBody"]))

    story.append(Spacer(1, 18))
    story.append(HRFlowable(width="100%", thickness=1, color=BORDER, spaceAfter=8))
    story.append(Paragraph(f"Dr. {clinician['name']}", _styles["PVSignature"]))
    story.append(Paragraph(f'<font size="7" color="{MUTED.hexval()}">DIGITAL ATTESTATION &nbsp;•&nbsp; '
                            f'{datetime.now().strftime("%b %d, %Y %I:%M %p")}</font>', _styles["PVBody"]))

    doc.build(story)
    return buf.getvalue()
