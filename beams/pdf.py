"""PDF calculation-package export for a saved beam design.

Mirrors the same content as the HTML result panel and CSV export (given
inputs, section properties, adjustment factors, load combinations, and
design checks with required bearing length) in a printable format, per
the project's roadmap: "Reports: calculation packages... HTML templates
with PDF generation."

Built with reportlab (pure Python, no native system dependencies) rather
than an HTML-to-PDF renderer like WeasyPrint, which needs GTK/Pango/Cairo
system libraries that are unreliable to install on Windows.
"""
import io
from xml.sax.saxutils import escape

from reportlab.graphics.shapes import Drawing, Line, PolyLine, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from engine import get_material

from .load_inputs import entered_uniform_loads_to_plf

PASS_COLOR = colors.HexColor("#16a34a")
FAIL_COLOR = colors.HexColor("#dc2626")
MUTED_COLOR = colors.HexColor("#6b7280")
HEADER_BG = colors.HexColor("#f3f4f6")
NAVY = colors.HexColor("#0f172a")
BLUE = colors.HexColor("#1d4ed8")
SLATE = colors.HexColor("#475569")
GRID = colors.HexColor("#d1d5db")

_TABLE_HEADER_STYLE = [
    ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("FONTSIZE", (0, 0), (-1, -1), 8),
    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ("TOPPADDING", (0, 0), (-1, -1), 4),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
]


def _table(data, col_widths=None):
    table = Table(data, colWidths=col_widths, hAlign="LEFT")
    table.setStyle(TableStyle(_TABLE_HEADER_STYLE))
    return table


def _status_badge(text, passed, styles):
    bg = "#dcfce7" if passed else "#fee2e2"
    fg = "#166534" if passed else "#b91c1c"
    style = ParagraphStyle(
        "StatusBadge",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        textColor=colors.HexColor(fg),
        backColor=colors.HexColor(bg),
        borderPadding=(4, 6, 4, 6),
        leading=12,
    )
    return Paragraph(text, style)


def _support_schedule(design):
    return [
        (row["label"], row["bearing_length_in"], row["support_type"])
        for row in design.support_schedule
    ]


def _project_lines(design):
    if not design.project:
        return []
    lines = [f"<b>Project:</b> {design.project.name}"]
    if design.project.project_number:
        lines.append(f"<b>Project number:</b> {design.project.project_number}")
    lines.append(f"<b>Project status:</b> {design.project.get_status_display()}")
    if design.project.client_name:
        lines.append(f"<b>Client:</b> {design.project.client_name}")
    if design.project.site_address:
        lines.append(f"<b>Site:</b> {design.project.site_address}")
    if design.project.notes:
        lines.append(f"<b>Project notes:</b> {design.project.notes}")
    return lines


def _point_load_rows(design):
    rows = [["Load", "Location (ft from left end)", "Type"]]
    if not design.point_loads:
        rows.append(["None", "-", "-"])
        return rows
    for load in design.point_loads:
        rows.append([
            f"{load['p']:g} lb",
            f"{load['location_ft']:g}",
            str(load["load_type"]).replace("_", " ").title(),
        ])
    return rows


def _distributed_load_rows(design):
    rows = [["Intensity", "Analysis", "Start", "End", "Type"]]
    if not design.distributed_loads:
        rows.append(["None", "-", "-", "-", "-"])
        return rows
    for load in design.distributed_loads:
        rows.append([
            f"{load['w']:g} {load.get('basis', design.uniform_load_basis)}",
            f"{load['w_plf']:g} plf",
            f"{load['start_ft']:g} ft",
            f"{load['end_ft']:g} ft",
            str(load["load_type"]).replace("_", " ").title(),
        ])
    return rows


def _diagram_drawing(series, summary, title, width=6.7 * inch, height=1.75 * inch):
    drawing = Drawing(width, height)
    pad_left = 42
    pad_right = 14
    pad_top = 24
    pad_bottom = 28
    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom
    axis_x1 = pad_left
    axis_x2 = pad_left + plot_w
    axis_y_top = pad_bottom + plot_h
    axis_y_mid = pad_bottom + (plot_h / 2)
    axis_y_bottom = pad_bottom

    drawing.add(String(axis_x1, height - 12, title, fontName="Helvetica-Bold", fontSize=10, fillColor=NAVY))
    if not series or not series.points:
        drawing.add(String(axis_x1, axis_y_mid, "No analysis data available", fontName="Helvetica", fontSize=9, fillColor=MUTED_COLOR))
        return drawing

    total_length = max(summary.total_length, 1e-9)
    lower = getattr(series, "lower", None)
    all_points = list(series.points) + list(lower) if lower else series.points
    max_abs_y = max(abs(point.y) for point in all_points) or 1.0

    def sx(x):
        return axis_x1 + (plot_w * (x / total_length))

    def sy(y):
        return axis_y_mid + (plot_h * 0.45 * (y / max_abs_y))

    drawing.add(Rect(axis_x1, axis_y_bottom, plot_w, plot_h, strokeColor=GRID, fillColor=None, strokeWidth=0.6))
    drawing.add(Line(axis_x1, axis_y_mid, axis_x2, axis_y_mid, strokeColor=SLATE, strokeWidth=0.8))

    for support_x, label in zip(summary.support_positions, summary.support_labels):
        x = sx(support_x)
        drawing.add(Line(x, axis_y_bottom, x, axis_y_top, strokeColor=colors.HexColor("#cbd5e1"), strokeWidth=0.6))
        drawing.add(String(x - 7, axis_y_bottom - 12, label, fontName="Helvetica-Bold", fontSize=7, fillColor=SLATE))

    def _polyline(series_points):
        coords = []
        for point in series_points:
            coords.extend([sx(point.x), sy(point.y)])
        drawing.add(PolyLine(coords, strokeColor=BLUE, strokeWidth=1.3))

    _polyline(series.points)
    if lower:  # continuous-beam envelope: draw the max-negative curve too
        _polyline(lower)

    peak_x = sx(series.peak_x)
    peak_y = sy(series.peak_y)
    drawing.add(Line(peak_x, axis_y_mid, peak_x, peak_y, strokeColor=colors.HexColor("#93c5fd"), strokeWidth=0.8))
    drawing.add(String(
        axis_x1,
        height - 24,
        f"{series.governing_combo} - peak {series.peak_y:.3f} {series.unit} @ {series.peak_x:.2f} ft",
        fontName="Helvetica",
        fontSize=8,
        fillColor=MUTED_COLOR,
    ))
    drawing.add(String(axis_x1 - 30, axis_y_top - 2, f"+{max_abs_y:.2f}", fontName="Helvetica", fontSize=7, fillColor=MUTED_COLOR))
    drawing.add(String(axis_x1 - 30, axis_y_bottom - 2, f"-{max_abs_y:.2f}", fontName="Helvetica", fontSize=7, fillColor=MUTED_COLOR))
    drawing.add(String(axis_x2 - 48, axis_y_bottom - 16, f"{total_length:.2f} ft", fontName="Helvetica", fontSize=7, fillColor=MUTED_COLOR))
    return drawing


def _beam_design_story(design, result, styles):
    """Build the reusable member-report flowables for individual and project PDFs."""
    story = []
    section_label_style = ParagraphStyle(
        "SectionLabel",
        parent=styles["Heading3"],
        textColor=NAVY,
        spaceAfter=6,
    )

    title = design.name or f"Beam Design #{design.pk}"
    story.append(Paragraph(title, styles["Title"]))
    story.append(Paragraph(
        f"{design.section_label} {result.summary.material_name} &middot; "
        f"{design.get_member_type_display()} &middot; "
        f"Revision {design.revision_number} &middot; Saved {design.created_at:%Y-%m-%d %H:%M}",
        styles["Normal"],
    ))
    if design.revision_note:
        story.append(Paragraph(f"<b>Revision note:</b> {escape(design.revision_note)}", styles["Normal"]))
    for line in _project_lines(design):
        story.append(Paragraph(line, styles["Normal"]))
    story.append(Spacer(1, 10))

    overall_text = "PASS" if result.passed else "FAIL"
    summary_table = Table([
        [
            _status_badge(overall_text, result.passed, styles),
            Paragraph(
                f"<b>Governing check:</b> {result.governing.name}<br/>"
                f"<b>Utilization:</b> {result.governing.ratio:.3f}",
                styles["Normal"],
            ),
            Paragraph(
                f"<b>Analysis length:</b> {result.summary.total_length:.2f} ft<br/>"
                f"<b>Supports:</b> {len(result.summary.support_labels)}",
                styles["Normal"],
            ),
        ]
    ], colWidths=[1.0 * inch, 2.9 * inch, 2.3 * inch], hAlign="LEFT")
    summary_table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, GRID),
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 8))

    # ---- Given -------------------------------------------------------
    story.append(Paragraph("Design Basis", section_label_style))
    given_lines = [
        f"<b>Member:</b> {design.section_label} {result.summary.material_name}",
        f"<b>Performance target:</b> {design.get_performance_profile_display()}",
        f"<b>Subfloor / floor feel:</b> {design.get_subfloor_profile_display()}",
    ]
    if len(design.entered_spans) > 1:
        given_lines.append(
            f"<b>Spans as entered:</b> {' + '.join(f'{span:.2f} ft' for span in design.entered_spans)} "
            f"({design.get_span_mode_display()})",
        )
        clear_labels = [
            f"B{index}-B{index + 1} = {clear_span:.2f} ft clear"
            for index, clear_span in enumerate(result.summary.span_segments, start=1)
        ]
        given_lines.append(f"<b>Analysis spans:</b> {' &middot; '.join(clear_labels)}")
        given_lines.append(f"<b>Continuous total length:</b> {result.summary.total_length:.2f} ft")
    elif design.span_mode != "inside":
        given_lines.append(
            f"<b>Span:</b> {design.span_ft:.2f} ft "
            f"({design.get_span_mode_display()}) &rarr; "
            f"{result.summary.span:.2f} ft clear (analysis span)",
        )
    else:
        given_lines.append(f"<b>Span:</b> {result.summary.span:.2f} ft (clear)")
    if result.summary.unbraced_length:
        given_lines.append(
            f"<b>Compression edge:</b> unbraced {result.summary.unbraced_length / 12:.2f} ft "
            f"(CL = {result.summary.cl:.3f}, RB = {result.summary.rb:.1f}, NDS 3.3.3, "
            "uniform-load le)",
        )
    else:
        given_lines.append("<b>Compression edge:</b> continuously braced (CL = 1.0)")
    if result.summary.wet_service:
        given_lines.append(
            f"<b>Service condition:</b> wet (NDS-S Table 4A CM: Fb {result.summary.cm_fb:.2f}, "
            f"Fv {result.summary.cm_fv:.2f}, Fc&perp; {result.summary.cm_fcperp:.2f}, "
            f"E {result.summary.cm_e:.2f})",
        )
    else:
        given_lines.append("<b>Service condition:</b> dry (CM = 1.0)")
    if result.summary.material_category == "lvl":
        given_lines.append(
            f"<b>LVL:</b> engineered member &mdash; CV = {result.summary.cf:.3f} depth factor "
            "(not CF), no Cr, dry-service. Generic LVL grade values; confirm your product "
            "meets this grade.",
        )
    elif result.summary.material_category == "glulam":
        given_lines.append(
            f"<b>Glulam:</b> engineered member &mdash; volume factor CV = {result.summary.cf:.3f} "
            f"(NDS 5.3.6), applied as the lesser of CV and CL = {result.summary.cl:.3f}; no Cr, "
            "dry-service, balanced layup. Generic NDS Table 5A stress-class values.",
        )
    given_lines.append(
        f"<b>Uniform load input:</b> {design.uniform_load_basis.upper()}"
        + (f" @ {design.spacing_in:g}\" o.c." if design.uniform_load_basis == "psf" else "")
        + (" (repetitive member)" if design.repetitive else ""),
    )
    entered_unit = design.uniform_load_basis
    given_lines.append(
        f"<b>Entered loads:</b> D = {design.dead_load_plf:g} {entered_unit}, "
        f"L = {design.live_load_plf:g} {entered_unit}, "
        f"S = {design.snow_load_plf:g} {entered_unit}, "
        f"Lr = {design.roof_live_load_plf:g} {entered_unit}, "
        f"W = {design.wind_load_plf:g} {entered_unit}",
    )
    given_lines.append(
        f"<b>Deflection criteria:</b> back span L/{result.summary.deflection_limit_live:.0f} live/snow, "
        f"L/{result.summary.deflection_limit_total:.0f} total",
    )
    if design.left_overhang_ft or design.right_overhang_ft:
        given_lines.append(
            f"<b>Cantilever criteria:</b> L/{result.summary.cantilever_deflection_limit_live:.0f} live/snow, "
            f"L/{result.summary.cantilever_deflection_limit_total:.0f} total",
        )
    given_lines.append(
        "<b>Bearing:</b> " + " &middot; ".join(
            f"{label} {length:g}\" {support_type}"
            for label, length, support_type in _support_schedule(design)
        ),
    )
    if design.left_overhang_ft or design.right_overhang_ft:
        given_lines.append(
            f"<b>Overhang:</b> {design.left_overhang_ft:g} ft left, "
            f"{design.right_overhang_ft:g} ft right "
            f"(total length {result.summary.total_length:.2f} ft)",
        )
    for line in given_lines:
        story.append(Paragraph(line, styles["Normal"]))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Geometry & Support Schedule", section_label_style))
    geometry_rows = [["Item", "Value"]]
    geometry_rows.append(["Span basis", design.get_span_mode_display()])
    geometry_rows.append(["Spans as entered", ", ".join(f"{span:.2f} ft" for span in design.entered_spans)])
    geometry_rows.append(["Analysis spans", ", ".join(f"{span:.2f} ft" for span in result.summary.span_segments)])
    geometry_rows.append(["Left overhang", f"{design.left_overhang_ft:g} ft"])
    geometry_rows.append(["Right overhang", f"{design.right_overhang_ft:g} ft"])
    geometry_rows.append(["Total member length", f"{result.summary.total_length:.2f} ft"])
    story.append(_table(geometry_rows, col_widths=[2.0 * inch, 4.2 * inch]))
    story.append(Spacer(1, 8))

    support_rows = [["Support", "Bearing length (in)", "Support type"]]
    for label, length_in, support_type in _support_schedule(design):
        support_rows.append([label, f"{length_in:g}\"", support_type])
    story.append(_table(support_rows, col_widths=[0.8 * inch, 1.3 * inch, 3.2 * inch]))
    story.append(Spacer(1, 10))

    # ---- Loads -------------------------------------------------------
    story.append(Paragraph("Load Schedule", section_label_style))
    entered_unit = design.uniform_load_basis
    normalized = entered_uniform_loads_to_plf({
        "uniform_load_basis": design.uniform_load_basis,
        "spacing_in": design.spacing_in,
        "dead_load_plf": design.dead_load_plf,
        "live_load_plf": design.live_load_plf,
        "snow_load_plf": design.snow_load_plf,
        "roof_live_load_plf": design.roof_live_load_plf,
        "wind_load_plf": design.wind_load_plf,
    })
    load_rows = [["Component", f"Entered ({entered_unit})", "Analysis (plf)", "CD"]]
    load_rows.extend([
        ["Dead", f"{design.dead_load_plf:g}", f"{normalized['dead']:.2f}", "0.90"],
        ["Live", f"{design.live_load_plf:g}", f"{normalized['live']:.2f}", "1.00"],
        ["Snow", f"{design.snow_load_plf:g}", f"{normalized['snow']:.2f}", "1.15"],
        ["Roof live", f"{design.roof_live_load_plf:g}", f"{normalized['roof_live']:.2f}", "1.25"],
        ["Wind", f"{design.wind_load_plf:g}", f"{normalized['wind']:.2f}", "1.60"],
    ])
    story.append(_table(load_rows, col_widths=[1.4 * inch, 1.3 * inch, 1.3 * inch, 0.7 * inch]))
    story.append(Spacer(1, 8))
    story.append(Paragraph("Additive Distributed Zones", styles["Normal"]))
    story.append(_table(
        _distributed_load_rows(design),
        col_widths=[1.25 * inch, 1.05 * inch, 0.8 * inch, 0.8 * inch, 1.15 * inch],
    ))
    story.append(Spacer(1, 8))
    story.append(Paragraph("Point Loads", styles["Normal"]))
    story.append(_table(_point_load_rows(design), col_widths=[1.3 * inch, 1.8 * inch, 1.2 * inch]))
    story.append(Spacer(1, 10))

    # ---- Section properties -------------------------------------------
    story.append(Paragraph("Section Properties & Adjustment Factors", section_label_style))
    section = result.summary.section
    story.append(_table([
        ["Plies", "Width b (in)", "Depth d (in)", "A (in^2)", "I (in^4)", "S (in^3)"],
        [
            f"{section.plies}", f"{section.b:.3f}", f"{section.d:.3f}",
            f"{section.A:.3f}", f"{section.I:.3f}", f"{section.S:.3f}",
        ],
    ]))
    story.append(Spacer(1, 10))

    story.append(_table([
        ["Fb base", "Fv base", "Fc perp base", "E"],
        [
            f"{result.summary.fb_base:.1f}", f"{result.summary.fv_base:.1f}",
            f"{result.summary.fc_perp_base:.1f}", f"{result.summary.e:.0f}",
        ],
    ]))
    story.append(Spacer(1, 8))
    depth_factor_label = "CF" if result.summary.material_category == "sawn" else "CV"
    story.append(_table([
        [depth_factor_label, "Cr", "CL", "Cb (left)", "Cb (right)", "Live limit", "Total limit"],
        [
            f"{result.summary.cf:.3f}", f"{result.summary.cr:.2f}", f"{result.summary.cl:.3f}",
            f"{result.summary.cb_left:.2f}", f"{result.summary.cb_right:.2f}",
            f"L/{result.summary.deflection_limit_live:.0f}",
            f"L/{result.summary.deflection_limit_total:.0f}",
        ],
    ], col_widths=[0.65 * inch, 0.65 * inch, 0.65 * inch, 0.8 * inch, 0.8 * inch, 0.85 * inch, 0.85 * inch]))
    story.append(Spacer(1, 10))

    # ---- Load combinations ---------------------------------------------
    story.append(Paragraph("Load Combinations (NDS 2018 Table 2.3.2)", section_label_style))
    combo_rows = [[
        "Combo", "CD", *[f"{label} (lb)" for label in result.summary.support_labels], "Vmax (lb)", "V @ x (ft)", "Mmax (ft-lb)", "M @ x (ft)",
    ]]
    for combo in result.summary.combos:
        combo_rows.append([
            combo.name, f"{combo.cd:.2f}", *[f"{reaction:.0f}" for reaction in combo.reactions],
            f"{combo.v_max:.0f}", f"{combo.v_max_x:.2f}", f"{combo.m_max:.0f}", f"{combo.m_max_x:.2f}",
        ])
    combo_col_widths = [0.8 * inch, 0.5 * inch]
    combo_col_widths.extend([0.7 * inch] * len(result.summary.support_labels))
    combo_col_widths.extend([0.8 * inch, 0.7 * inch, 1.0 * inch, 0.7 * inch])
    story.append(_table(combo_rows, col_widths=combo_col_widths))
    story.append(Spacer(1, 10))

    # ---- Analysis diagrams --------------------------------------------
    story.append(Paragraph("Analysis Diagrams", section_label_style))
    story.append(_diagram_drawing(result.summary.shear_diagram, result.summary, "Shear"))
    story.append(Spacer(1, 6))
    story.append(_diagram_drawing(result.summary.moment_diagram, result.summary, "Moment"))
    story.append(Spacer(1, 6))
    story.append(_diagram_drawing(result.summary.deflection_live_diagram, result.summary, "Live / transient deflection"))
    story.append(Spacer(1, 6))
    story.append(_diagram_drawing(result.summary.deflection_total_diagram, result.summary, "Total-load deflection"))
    story.append(Spacer(1, 10))

    # ---- Design checks ---------------------------------------------
    story.append(Paragraph("Design Checks", section_label_style))
    check_name_style = styles["Normal"].clone("CheckName")
    check_name_style.fontSize = 8
    check_rows = [["Check", "Demand", "Capacity", "Ratio", "Combo", "Req. Length (in)", "Status"]]
    row_colors = []
    for check in result.checks:
        required = f"{check.required_length:.2f}" if check.required_length is not None else "-"
        status = "OK" if check.passed else "FAIL"
        # Long labels (e.g. the net-uplift warning) need to wrap rather
        # than overflow the column -- plain strings don't wrap in a
        # reportlab Table cell, but a Paragraph does.
        check_rows.append([
            Paragraph(check.name, check_name_style), f"{check.demand:.2f}", f"{check.capacity:.2f}",
            f"{check.ratio:.3f}", check.governing_combo, required, status,
        ])
        row_colors.append(FAIL_COLOR if not check.passed else colors.black)

    checks_table = Table(
        check_rows,
        colWidths=[1.6 * inch, 0.7 * inch, 0.7 * inch, 0.6 * inch, 0.7 * inch, 0.9 * inch, 0.6 * inch],
        hAlign="LEFT",
    )
    table_style = list(_TABLE_HEADER_STYLE)
    for i, color in enumerate(row_colors, start=1):
        if color is FAIL_COLOR:
            table_style.append(("TEXTCOLOR", (0, i), (-1, i), FAIL_COLOR))
    checks_table.setStyle(TableStyle(table_style))
    story.append(checks_table)
    story.append(Spacer(1, 12))

    story.append(Paragraph(
        "Bending: f_b = M/S vs F'_b = Fb &times; CF &times; Cr &times; CD &middot; "
        "Shear: f_v = 1.5V/A vs F'_v = Fv &times; CD &middot; "
        "Deflection: numeric beam-curvature integration vs L/&Delta; criteria over each checked span or cantilever tip &middot; "
        "Bearing: R/(b &times; Lb) vs Fc&perp; &times; Cb, with required Lb solving that "
        "equality (min 1.5\" in the current wood workflow)",
        styles["Normal"],
    ))
    story.append(Spacer(1, 16))
    story.append(Paragraph(
        '<font color="#6b7280" size="8">Preliminary sizing only. Not a substitute '
        "for licensed engineering review.</font>",
        styles["Normal"],
    ))

    return story


def _pdf_document(buffer, title):
    return SimpleDocTemplate(
        buffer,
        pagesize=letter,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
        title=title,
    )


def _page_footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MUTED_COLOR)
    canvas.drawString(0.6 * inch, 0.32 * inch, "FrameCalc preliminary calculation package")
    canvas.drawRightString(7.9 * inch, 0.32 * inch, f"Page {doc.page}")
    canvas.restoreState()


def _beam_column_story(column, result, styles):
    """Flowables for a saved beam-column (combined axial + bending) report."""
    story = []
    section_label_style = ParagraphStyle(
        "SectionLabel", parent=styles["Heading3"], textColor=NAVY, spaceAfter=6,
    )
    s = result.summary

    story.append(Paragraph(column.name or f"Column Design #{column.pk}", styles["Title"]))
    story.append(Paragraph(
        f"{column.section_label} {s.material_name} &middot; {column.height_ft:g} ft beam-column &middot; "
        f"Saved {column.created_at.strftime('%b %d, %Y')}",
        styles["Normal"],
    ))
    if column.project:
        story.append(Paragraph(f"<b>Project:</b> {escape(column.project.name)}", styles["Normal"]))
    story.append(Spacer(1, 6))
    story.append(_status_badge("PASS" if result.passed else "FAIL", result.passed, styles))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Design Basis", section_label_style))
    end_label = dict(column._meta.get_field("end_condition").choices).get(column.end_condition, column.end_condition)
    lat_label = dict(column._meta.get_field("lateral_load_type").choices).get(
        column.lateral_load_type, column.lateral_load_type)
    for line in [
        f"<b>Section:</b> {column.section_label} {s.material_name}",
        f"<b>Height:</b> {column.height_ft:g} ft &middot; <b>End condition:</b> {end_label}",
        f"<b>Axial loads (lb):</b> D {column.dead_load_lb:g}, L {column.live_load_lb:g}, "
        f"S {column.snow_load_lb:g}, Lr {column.roof_live_load_lb:g}, W {column.wind_load_lb:g}",
        f"<b>Lateral load:</b> {column.lateral_load_plf:g} plf ({lat_label}) &rarr; "
        f"M = w&middot;H&sup2;/8 = {s.bending_moment:.0f} in-lb (strong axis)",
    ]:
        story.append(Paragraph(line, styles["Normal"]))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Section &amp; Factors", section_label_style))
    story.append(_table([
        ["Plies", "b (in)", "d (in)", "A (in^2)", "Fc base", "Fb base", "Emin"],
        [f"{s.section.plies}", f"{s.section.b:.3f}", f"{s.section.d:.3f}", f"{s.section.A:.3f}",
         f"{s.fc_base:.0f}", f"{s.fb_base:.0f}", f"{s.emin:.0f}"],
    ]))
    story.append(Spacer(1, 8))
    story.append(_table([
        ["CF (Fc)", "CF (Fb)", "c", "Ke", "Slenderness", "CP", "CL", "FcE1"],
        [f"{s.cf_c:.2f}", f"{s.cf_b:.2f}", f"{s.c_coefficient}", f"{s.ke:g}",
         f"{s.slenderness:.1f}", f"{s.cp:.3f}", f"{s.cl:.3f}", f"{s.fce1:.0f}"],
    ]))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Combined Axial + Bending (NDS 3.9-3)", section_label_style))
    story.append(Paragraph(
        "(fc/Fc')^2 + fb / [Fb'(1 - fc/FcE1)] &lt;= 1.0",
        styles["Normal"],
    ))
    story.append(Spacer(1, 4))
    rows = [["Combo", "CD", "P (lb)", "fc", "Fc'", "fb", "Fb'", "1-fc/FcE1", "Interaction"]]
    for combo in s.combos:
        rows.append([
            combo.name, f"{combo.cd:g}", f"{combo.p:.0f}", f"{combo.fc:.0f}", f"{combo.fc_allow:.0f}",
            f"{combo.fb:.0f}", f"{combo.fb_allow:.0f}", f"{combo.amplification:.3f}", f"{combo.interaction:.3f}",
        ])
    story.append(_table(rows))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        f"<b>Governing:</b> combined interaction {result.interaction.ratio:.3f} "
        f"({result.interaction.governing_combo}); axial {result.axial.ratio:.3f}, "
        f"bending {result.bending.ratio:.3f}. Dry service, uniaxial strong-axis bending.",
        styles["Normal"],
    ))
    return story


def _column_design_story(column, result, styles):
    """Flowables for a saved column / post report -- axial-only, or the
    combined beam-column report when a lateral load is present."""
    if getattr(result, "interaction", None) is not None:
        return _beam_column_story(column, result, styles)
    story = []
    section_label_style = ParagraphStyle(
        "SectionLabel", parent=styles["Heading3"], textColor=NAVY, spaceAfter=6,
    )
    s = result.summary
    c = result.compression

    story.append(Paragraph(column.name or f"Column Design #{column.pk}", styles["Title"]))
    story.append(Paragraph(
        f"{column.section_label} {s.material_name} &middot; {column.height_ft:g} ft column &middot; "
        f"Saved {column.created_at.strftime('%b %d, %Y')}",
        styles["Normal"],
    ))
    if column.project:
        story.append(Paragraph(f"<b>Project:</b> {escape(column.project.name)}", styles["Normal"]))
    story.append(Spacer(1, 6))
    story.append(_status_badge("PASS" if result.passed else "FAIL", result.passed, styles))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Design Basis", section_label_style))
    end_label = dict(column._meta.get_field("end_condition").choices).get(column.end_condition, column.end_condition)
    given = [
        f"<b>Section:</b> {column.section_label} {s.material_name}",
        f"<b>Height:</b> {column.height_ft:g} ft &middot; <b>End condition:</b> {end_label}",
        f"<b>Unbraced length (d axis):</b> {s.unbraced_length_d / 12:g} ft &middot; "
        f"<b>(b axis):</b> {s.unbraced_length_b / 12:g} ft",
        f"<b>Axial loads (lb):</b> D {column.dead_load_lb:g}, L {column.live_load_lb:g}, "
        f"S {column.snow_load_lb:g}, Lr {column.roof_live_load_lb:g}, W {column.wind_load_lb:g}",
    ]
    for line in given:
        story.append(Paragraph(line, styles["Normal"]))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Section &amp; Stability", section_label_style))
    story.append(_table([
        ["Plies", "b (in)", "d (in)", "A (in^2)", "Fc base", "E", "Emin"],
        [f"{s.section.plies}", f"{s.section.b:.3f}", f"{s.section.d:.3f}", f"{s.section.A:.3f}",
         f"{s.fc_base:.0f}", f"{s.e:.0f}", f"{s.emin:.0f}"],
    ]))
    story.append(Spacer(1, 8))
    story.append(_table([
        ["CF", "c", "Ke", "le/d", "le/b", "Slenderness", "FcE", "CP"],
        [f"{s.cf_c:.2f}", f"{s.c_coefficient}", f"{s.ke:g}",
         f"{s.le_d / s.section.d:.1f}", f"{s.le_b / s.section.b:.1f}",
         f"{s.slenderness:.1f}", f"{s.fce:.0f}", f"{s.cp:.3f}"],
    ]))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Axial Compression (NDS 3.7)", section_label_style))
    rows = [["Combo", "CD", "P (lb)", "fc (psi)", "CP", "Fc' (psi)", "Ratio", "Status"]]
    for combo in s.combos:
        rows.append([
            combo.name, f"{combo.cd:g}", f"{combo.p:.0f}", f"{combo.fc:.0f}",
            f"{combo.cp:.3f}", f"{combo.fc_allow:.0f}", f"{combo.ratio:.3f}",
            "PASS" if combo.ratio <= 1.0 else "FAIL",
        ])
    story.append(_table(rows))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        f"<b>Governing:</b> {escape(c.name)} &mdash; {c.governing_combo}, ratio {c.ratio:.3f}. "
        "Dry service, concentric axial load; le/d limited to 50 (NDS 3.7.1.4).",
        styles["Normal"],
    ))
    return story


def render_column_design_pdf(column, result) -> bytes:
    """Render one saved column design and its computed result to PDF bytes."""
    buffer = io.BytesIO()
    doc = _pdf_document(buffer, column.name or f"Column design #{column.pk}")
    styles = getSampleStyleSheet()
    doc.build(
        _column_design_story(column, result, styles),
        onFirstPage=_page_footer,
        onLaterPages=_page_footer,
    )
    return buffer.getvalue()


def _withdrawal_story(connection, result, styles):
    """Flowables for a fastener-withdrawal report (NDS 12.2)."""
    story = []
    section_label_style = ParagraphStyle(
        "SectionLabel", parent=styles["Heading3"], textColor=NAVY, spaceAfter=6,
    )
    story.append(Paragraph(connection.name or f"Connection Design #{connection.pk}", styles["Title"]))
    story.append(Paragraph(
        f"{connection.get_fastener_type_display()} &middot; {connection.diameter_in:g} in dia &middot; "
        f"withdrawal (axial) &middot; Saved {connection.created_at.strftime('%b %d, %Y')}",
        styles["Normal"],
    ))
    if connection.project:
        story.append(Paragraph(f"<b>Project:</b> {escape(connection.project.name)}", styles["Normal"]))
    story.append(Spacer(1, 6))
    if not result.applicable:
        story.append(Paragraph(
            "<b>Not applicable:</b> bolts are not designed for withdrawal. Use a nail, "
            "wood screw, or lag screw.", styles["Normal"]))
        return story
    if result.demand:
        story.append(_status_badge("PASS" if result.passed else "FAIL", result.passed, styles))
        story.append(Spacer(1, 10))

    story.append(Paragraph("Withdrawal Design (NDS 12.2)", section_label_style))
    for line in [
        f"<b>Fastener:</b> {connection.get_fastener_type_display()}, {connection.diameter_in:g} in dia",
        f"<b>Holding member:</b> {get_material(connection.main_material).name} "
        f"(G = {get_material(connection.main_material).G:g}), penetration {result.penetration:g} in",
        f"<b>Loading:</b> {connection.get_service_condition_display()}"
        + (", toe-nailed" if connection.toe_nail else "")
        + (f", {connection.get_temperature_display()}" if connection.temperature != "normal" else "")
        + f", CD = {connection.load_duration:g}, "
        f"{connection.n_fasteners} fastener(s)"
        + (f", applied {connection.load_lb:g} lb" if connection.load_lb else ""),
    ]:
        story.append(Paragraph(line, styles["Normal"]))
    story.append(Spacer(1, 10))
    story.append(_table([
        ["W (lb/in)", "Penetration (in)", "W (lb/fast.)", "CD", "CM", "Ctn", "Ct", "W' (lb/fast.)", "Capacity (lb)"],
        [f"{result.w_per_inch:.1f}", f"{result.penetration:g}", f"{result.w_single:.0f}",
         f"{result.cd:g}", f"{result.cm:.2f}", f"{result.ctn:.2f}", f"{result.ct:.2f}",
         f"{result.w_adjusted:.0f}", f"{result.capacity:.0f}"],
    ]))
    story.append(Spacer(1, 8))
    verdict = (f"demand/capacity = {result.demand:.0f}/{result.capacity:.0f} = {result.ratio:.3f}"
               if result.demand else "reference capacity (no applied load entered)")
    notes = ""
    if result.cm < 1:
        notes += f" CM = {result.cm:.2f} (NDS Table 11.3.3, wet service)."
    if result.ctn < 1:
        notes += f" Ctn = {result.ctn:.2f} (NDS 12.5.4, toe-nail)."
    if result.ct < 1:
        notes += f" Ct = {result.ct:.2f} (NDS Table 11.3.4, temperature)."
    story.append(Paragraph(
        f"<b>W' = W x penetration x CD x CM x Ctn x Ct.</b> {verdict}.{notes}",
        styles["Normal"],
    ))
    return story


def _connection_design_story(connection, result, styles):
    """Flowables for a saved connection report (NDS Chapter 12)."""
    if getattr(result, "yield_result", None) is None:
        return _withdrawal_story(connection, result, styles)
    story = []
    section_label_style = ParagraphStyle(
        "SectionLabel", parent=styles["Heading3"], textColor=NAVY, spaceAfter=6,
    )
    y = result.yield_result
    shear = "double shear (3-member)" if result.double_shear else "single shear (2-member)"

    story.append(Paragraph(connection.name or f"Connection Design #{connection.pk}", styles["Title"]))
    story.append(Paragraph(
        f"{connection.get_fastener_type_display()} &middot; {connection.diameter_in:g} in dia &middot; "
        f"{shear} &middot; Saved {connection.created_at.strftime('%b %d, %Y')}",
        styles["Normal"],
    ))
    if connection.project:
        story.append(Paragraph(f"<b>Project:</b> {escape(connection.project.name)}", styles["Normal"]))
    story.append(Spacer(1, 6))
    if result.demand:
        story.append(_status_badge("PASS" if result.passed else "FAIL", result.passed, styles))
        story.append(Spacer(1, 10))

    story.append(Paragraph("Design Basis", section_label_style))
    for line in [
        f"<b>Fastener:</b> {connection.get_fastener_type_display()}, {connection.diameter_in:g} in dia, "
        f"Fyb = {connection.fyb_psi:g} psi &middot; {shear}",
        f"<b>Main member:</b> {get_material(connection.main_material).name}, {connection.main_thickness_in:g} in",
        (f"<b>Side member:</b> {connection.get_steel_grade_display()} steel plate, "
         f"{connection.side_thickness_in:g} in (Fe = {result.yield_result.fes:.0f} psi, NDS 12.3.3)"
         if connection.side_type == "steel"
         else f"<b>Side member:</b> {get_material(connection.side_material).name}, {connection.side_thickness_in:g} in"),
        f"<b>Loading:</b> {connection.get_load_direction_display()}, "
        f"{connection.get_service_condition_display()}"
        + (", toe-nailed" if connection.toe_nail else "")
        + (f", {connection.get_temperature_display()}" if connection.temperature != "normal" else "")
        + f", CD = {connection.load_duration:g}, "
        f"{connection.n_fasteners} fastener(s)"
        + (f", applied {connection.load_lb:g} lb" if connection.load_lb else ""),
    ]:
        story.append(Paragraph(line, styles["Normal"]))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Yield-Limit Modes (NDS 12.3)", section_label_style))
    rows = [["Mode"] + list(y.mode_values.keys())]
    rows.append(["Z (lb)"] + [f"{v:.0f}" for v in y.mode_values.values()])
    story.append(_table(rows))
    story.append(Spacer(1, 8))
    story.append(_table([
        ["Z (lb)", "Mode", "Fem", "Fes", "CD", "CM", "Ctn", "Ct", "Cg", "CDelta", "Z' (lb)", "Capacity (lb)"],
        [f"{result.z:.0f}", result.mode, f"{y.fem:.0f}", f"{y.fes:.0f}",
         f"{result.cd:g}", f"{result.cm:.2f}", f"{result.ctn:.2f}", f"{result.ct:.2f}", f"{result.cg:.3f}",
         f"{result.c_delta:.3f}", f"{result.z_adjusted:.0f}", f"{result.capacity:.0f}"],
    ]))
    story.append(Spacer(1, 8))
    verdict = (f"demand/capacity = {result.demand:.0f}/{result.capacity:.0f} = {result.ratio:.3f}"
               if result.demand else "reference capacity (no applied load entered)")
    notes = ""
    if result.cm < 1:
        notes += f" CM = {result.cm:.2f} (NDS Table 11.3.3, wet service)."
    if result.ctn < 1:
        notes += f" Ctn = {result.ctn:.2f} (NDS 12.5.4, toe-nail)."
    if result.ct < 1:
        notes += f" Ct = {result.ct:.2f} (NDS Table 11.3.4, temperature)."
    if result.edge_min:
        edge_word = "adequate" if result.edge_ok else "BELOW MINIMUM - not permitted"
        notes += (f" Edge distance vs NDS Table 12.5.1A minimum {result.edge_min:.2f} in: {edge_word}.")
    if result.side_steel:
        notes += (" Side member is a steel plate (Fes per NDS 12.3.3); check the plate itself "
                  "per AISC (net section, bearing, block shear) separately.")
    story.append(Paragraph(
        f"<b>Governing:</b> mode {result.mode}, Z = {result.z:.0f} lb. {verdict}. "
        f"Z' = Z x CD x CM x Ctn x Ct x Cg x CDelta.{notes}",
        styles["Normal"],
    ))
    return story


def render_connection_design_pdf(connection, result) -> bytes:
    """Render one saved connection design and its computed result to PDF."""
    buffer = io.BytesIO()
    doc = _pdf_document(buffer, connection.name or f"Connection design #{connection.pk}")
    styles = getSampleStyleSheet()
    doc.build(
        _connection_design_story(connection, result, styles),
        onFirstPage=_page_footer,
        onLaterPages=_page_footer,
    )
    return buffer.getvalue()


def render_beam_design_pdf(design, result) -> bytes:
    """Render one saved design and its computed result to PDF bytes."""
    buffer = io.BytesIO()
    doc = _pdf_document(buffer, design.name or f"Beam design #{design.pk}")
    styles = getSampleStyleSheet()
    doc.build(
        _beam_design_story(design, result, styles),
        onFirstPage=_page_footer,
        onLaterPages=_page_footer,
    )
    return buffer.getvalue()


def render_project_pdf(project, design_results, issue=None, column_results=None, connection_results=None) -> bytes:
    """Render a project cover sheet followed by every full member report.
    ``column_results``/``connection_results`` are optional lists for the
    current package; issue packages (snapshots) stay beams-only."""
    column_results = column_results or []
    connection_results = connection_results or []
    buffer = io.BytesIO()
    package_label = issue.label if issue else "Current Calculation Package"
    doc = _pdf_document(buffer, f"{project.name} - {package_label}")
    styles = getSampleStyleSheet()
    story = [
        Spacer(1, 0.35 * inch),
        Paragraph("FrameCalc", styles["Heading2"]),
        Paragraph(escape(project.name), styles["Title"]),
        Paragraph("Structural Member Calculation Package", styles["Heading2"]),
        Paragraph(escape(package_label), styles["Heading3"]),
        Spacer(1, 16),
    ]

    project_rows = [["Project Information", ""]]
    project_rows.append(["Project number", escape(project.project_number) if project.project_number else "Not entered"])
    project_rows.append(["Status", project.get_status_display()])
    project_rows.append(["Client", escape(project.client_name) if project.client_name else "Not entered"])
    project_rows.append(["Site address", escape(project.site_address) if project.site_address else "Not entered"])
    project_rows.append(["Last updated", project.updated_at.strftime("%Y-%m-%d")])
    project_rows.append(["Member designs", str(len(design_results))])
    if column_results:
        project_rows.append(["Columns", str(len(column_results))])
    if connection_results:
        project_rows.append(["Connections", str(len(connection_results))])
    if issue:
        project_rows.append(["Issue date", issue.created_at.strftime("%Y-%m-%d %H:%M")])
        prepared_by = issue.created_by.email if issue.created_by else "Unknown"
        project_rows.append(["Prepared by", escape(prepared_by)])
    story.append(_table(project_rows, col_widths=[1.4 * inch, 4.8 * inch]))
    story.append(Spacer(1, 14))

    all_results = list(design_results) + list(column_results) + list(connection_results)
    passing_count = sum(1 for _, result in all_results if result.passed)
    failing_count = len(all_results) - passing_count
    story.append(_table([
        ["Package Status", "Passing", "Failing"],
        ["COMPLETE" if all_results else "NO DESIGNS", str(passing_count), str(failing_count)],
    ], col_widths=[2.1 * inch, 1.2 * inch, 1.2 * inch]))
    story.append(Spacer(1, 14))

    summary_rows = [["Member", "Rev.", "Type", "Section", "Spans (ft)", "Governing", "Ratio", "Status"]]
    for design, result in design_results:
        summary_rows.append([
            Paragraph(escape(design.name or f"Design #{design.pk}"), styles["Normal"]),
            f"R{design.revision_number}",
            design.get_member_type_display(),
            design.section_label,
            design.span_display,
            Paragraph(escape(result.governing.name), styles["Normal"]),
            f"{result.governing.ratio:.3f}",
            "PASS" if result.passed else "FAIL",
        ])
    if not design_results:
        summary_rows.append(["No member designs saved", "-", "-", "-", "-", "-", "-", "-"])
    story.append(_table(
        summary_rows,
        col_widths=[1.1 * inch, 0.35 * inch, 0.7 * inch, 0.55 * inch, 0.7 * inch, 1.05 * inch, 0.5 * inch, 0.5 * inch],
    ))

    if column_results:
        story.append(Spacer(1, 12))
        story.append(Paragraph("Columns", styles["Heading3"]))
        column_summary = [["Column", "Section", "Height (ft)", "Governing", "Ratio", "Status"]]
        for column, result in column_results:
            column_summary.append([
                Paragraph(escape(column.name or f"Column #{column.pk}"), styles["Normal"]),
                column.section_label,
                f"{column.height_ft:g}",
                Paragraph(escape(result.governing.name), styles["Normal"]),
                f"{result.governing.ratio:.3f}",
                "PASS" if result.passed else "FAIL",
            ])
        story.append(_table(
            column_summary,
            col_widths=[1.3 * inch, 0.9 * inch, 0.8 * inch, 1.9 * inch, 0.6 * inch, 0.6 * inch],
        ))

    if connection_results:
        story.append(Spacer(1, 12))
        story.append(Paragraph("Connections", styles["Heading3"]))
        conn_summary = [["Connection", "Fastener", "Type", "Z/W (lb)", "Capacity", "Ratio/Status"]]
        for conn, result in connection_results:
            if getattr(result, "yield_result", None) is None:  # withdrawal
                if not result.applicable:
                    ctype, ref, cap, status = "withdrawal", "n/a", "n/a", "n/a"
                else:
                    ctype = "withdrawal"
                    ref = f"{result.w_per_inch:.1f}/in"
                    cap = f"{result.capacity:.0f}"
                    status = f"{result.ratio:.3f}" if result.demand else "ref"
            else:
                ctype = "double" if result.double_shear else "single"
                ref = f"{result.z:.0f}"
                cap = f"{result.capacity:.0f}"
                status = f"{result.ratio:.3f}" if result.demand else "ref"
            conn_summary.append([
                Paragraph(escape(conn.name or f"Connection #{conn.pk}"), styles["Normal"]),
                f"{conn.get_fastener_type_display()} {conn.diameter_in:g}\"",
                ctype, ref, cap, status,
            ])
        story.append(_table(
            conn_summary,
            col_widths=[1.3 * inch, 1.1 * inch, 0.7 * inch, 0.7 * inch, 0.8 * inch, 0.8 * inch],
        ))

    if project.notes:
        story.extend([
            Spacer(1, 14),
            Paragraph("Project Notes", styles["Heading3"]),
            Paragraph(escape(project.notes).replace("\n", "<br/>"), styles["Normal"]),
        ])
    if issue and issue.notes:
        story.extend([
            Spacer(1, 14),
            Paragraph("Issue Notes", styles["Heading3"]),
            Paragraph(escape(issue.notes), styles["Normal"]),
        ])

    story.extend([
        Spacer(1, 24),
        Paragraph(
            '<font color="#6b7280" size="8">Preliminary sizing only. This package is not a substitute '
            "for licensed engineering review, construction documents, or connection design.</font>",
            styles["Normal"],
        ),
    ])

    for design, result in design_results:
        story.append(PageBreak())
        story.extend(_beam_design_story(design, result, styles))
    for column, result in column_results:
        story.append(PageBreak())
        story.extend(_column_design_story(column, result, styles))
    for conn, result in connection_results:
        story.append(PageBreak())
        story.extend(_connection_design_story(conn, result, styles))

    doc.build(story, onFirstPage=_page_footer, onLaterPages=_page_footer)
    return buffer.getvalue()
