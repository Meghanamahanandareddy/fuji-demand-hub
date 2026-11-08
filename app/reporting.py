"""Weekly report generation: one PDF and one Excel file per business."""
from datetime import date, datetime, timedelta
from pathlib import Path

from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Alignment, Font, PatternFill
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import text

from app.db import engine

BUSINESSES = {
    "railway": {
        "title": "Railway", "label": "passengers", "agg": "sum", "kind": "int",
        "sql": ("SELECT date, sum(passengers)::float AS value FROM ridership_daily "
                "WHERE date BETWEEN :s AND :e GROUP BY date ORDER BY date"),
        "columns": [("value", "Passengers", "int")],
        "extras": [],
    },
    "hotels": {
        "title": "Hotels", "label": "occupancy", "agg": "mean", "kind": "pct",
        "sql": ("SELECT date, round(sum(rooms_booked)::numeric / "
                "sum(rooms_available) * 100, 1)::float AS value, "
                "sum(rooms_booked)::float AS rooms_booked, "
                "sum(rooms_available)::float AS rooms_available, "
                "sum(rooms_booked * avg_room_rate_jpy)::float AS revenue "
                "FROM hotel_daily WHERE date BETWEEN :s AND :e "
                "GROUP BY date ORDER BY date"),
        "columns": [("value", "Occupancy %", "pct"),
                    ("rooms_booked", "Rooms booked", "int"),
                    ("rooms_available", "Rooms available", "int"),
                    ("revenue", "Room revenue (JPY)", "int")],
        "extras": [("Room revenue", "revenue", "sum", "jpy")],
    },
    "park": {
        "title": "Amusement park", "label": "visitors", "agg": "sum", "kind": "int",
        "sql": ("SELECT date, visitors::float AS value, "
                "avg_wait_minutes::float AS wait, revenue_jpy::float AS revenue "
                "FROM park_daily WHERE date BETWEEN :s AND :e ORDER BY date"),
        "columns": [("value", "Visitors", "int"),
                    ("wait", "Average wait (min)", "int"),
                    ("revenue", "Revenue (JPY)", "int")],
        "extras": [("Average wait", "wait", "mean", "min"),
                   ("Revenue", "revenue", "sum", "jpy")],
    },
}


def fmt(kind, value):
    if kind == "pct":
        return f"{value:.1f}%"
    if kind == "jpy":
        return f"JPY {value:,.0f}"
    if kind == "min":
        return f"{value:.0f} min"
    return f"{value:,.0f}"


def agg(values, how):
    return sum(values) if how == "sum" else sum(values) / len(values)


def week_start(end):
    return end - timedelta(days=6)


def latest_data_date():
    with engine.connect() as conn:
        return conn.execute(text("SELECT max(date) FROM ridership_daily")).scalar()


# ------------------------------------------------------------------ data
def fetch_days(conn, code, start, end):
    rows = conn.execute(text(BUSINESSES[code]["sql"]), {"s": start, "e": end})
    return [dict(r) for r in rows.mappings()]


def fetch_weather(conn, start, end):
    rows = conn.execute(
        text("SELECT rainfall_mm::float AS rain, sunshine_hours::float AS sun "
             "FROM weather_daily WHERE date BETWEEN :s AND :e"),
        {"s": start, "e": end})
    return [dict(r) for r in rows.mappings()]


def fetch_anomalies(conn, code, start, end):
    rows = conn.execute(
        text("SELECT a.date, a.observed::float AS observed, "
             "a.expected::float AS expected, a.score::float AS score "
             "FROM anomalies a JOIN businesses b ON b.id = a.business_id "
             "WHERE b.code = :c AND a.date BETWEEN :s AND :e ORDER BY a.date"),
        {"c": code, "s": start, "e": end})
    return [dict(r) for r in rows.mappings()]


def fetch_forecast(conn, code, end):
    rows = conn.execute(
        text("SELECT f.target_date AS date, f.predicted_value::float AS value, "
             "f.model_name AS model FROM forecasts f "
             "JOIN businesses b ON b.id = f.business_id "
             "WHERE b.code = :c AND f.target_date > :e AND f.target_date <= :e7 "
             "ORDER BY f.target_date"),
        {"c": code, "e": end, "e7": end + timedelta(days=7)})
    return [dict(r) for r in rows.mappings()]


def summarize(code, days, previous, weather):
    cfg = BUSINESSES[code]
    kind, how, name = cfg["kind"], cfg["agg"], cfg["label"]
    values = [d["value"] for d in days]
    total = agg(values, how)
    kpis = []
    if how == "sum":
        kpis.append((f"Total {name}", fmt(kind, total)))
        kpis.append(("Average per day", fmt(kind, total / len(values))))
    else:
        kpis.append((f"Average {name}", fmt(kind, total)))

    if previous:
        before = agg([d["value"] for d in previous], how)
        if how == "sum" and before:
            kpis.append(("Change vs previous 7 days",
                         f"{(total - before) / before * 100:+.1f}%"))
        elif how == "mean":
            kpis.append(("Change vs previous 7 days", f"{total - before:+.1f} points"))

    top = max(days, key=lambda d: d["value"])
    low = min(days, key=lambda d: d["value"])
    kpis.append(("Busiest day", f"{top['date']:%a %d %b}: {fmt(kind, top['value'])}"))
    kpis.append(("Quietest day", f"{low['date']:%a %d %b}: {fmt(kind, low['value'])}"))

    for label, key, extra_how, extra_kind in cfg["extras"]:
        kpis.append((label, fmt(extra_kind, agg([d[key] for d in days], extra_how))))

    if weather:
        kpis.append(("Rainfall in the week",
                     f"{sum(w['rain'] for w in weather):.0f} mm in total"))
        kpis.append(("Sunshine in the week",
                     f"{sum(w['sun'] for w in weather) / len(weather):.1f} hours per day"))
    return kpis


# ------------------------------------------------------------------- PDF
def chart_drawing(cfg, days):
    drawing = Drawing(170 * mm, 62 * mm)
    chart = VerticalBarChart()
    chart.x, chart.y = 15 * mm, 10 * mm
    chart.width, chart.height = 150 * mm, 45 * mm
    values = [d["value"] for d in days]
    chart.data = [values]
    chart.categoryAxis.categoryNames = [f"{d['date']:%a %d}" for d in days]
    chart.categoryAxis.labels.fontSize = 8
    chart.valueAxis.labels.fontSize = 8
    chart.valueAxis.valueMin = 0
    chart.valueAxis.valueMax = 100 if cfg["kind"] == "pct" else max(values) * 1.15
    chart.bars[0].fillColor = colors.HexColor("#2b6cb0")
    drawing.add(chart)
    return drawing


def styled_table(data, widths):
    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2b6cb0")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f6fa")]),
    ]))
    return table


def build_pdf(path, code, start, end, days, kpis, anomalies, forecast):
    cfg = BUSINESSES[code]
    kind = cfg["kind"]
    styles = getSampleStyleSheet()
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=8,
                           textColor=colors.grey)
    doc = SimpleDocTemplate(
        str(path), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=16 * mm, bottomMargin=16 * mm,
        title=f"{cfg['title']} weekly report", author="Mt. Fuji Tourism Demand Hub")

    story = [
        Paragraph(f"{cfg['title']} weekly report", styles["Title"]),
        Paragraph(f"Week ending {end:%d %b %Y} ({start:%d %b} to {end:%d %b %Y})",
                  styles["Heading3"]),
        Paragraph("Pilot report built on synthetic data. It does not use "
                  "Fuji Kyuko's real data.", small),
        Spacer(1, 5 * mm),
        Paragraph("Key figures", styles["Heading2"]),
    ]

    key_table = Table([[k, v] for k, v in kpis], colWidths=[62 * mm, 108 * mm])
    key_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.lightgrey),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story += [key_table, Spacer(1, 5 * mm),
              Paragraph(f"Daily {cfg['label']}", styles["Heading2"]),
              chart_drawing(cfg, days), Spacer(1, 3 * mm)]

    header = ["Date"] + [c[1] for c in cfg["columns"]]
    rows = [[f"{d['date']:%a %d %b}"] + [fmt(c[2], d[c[0]]) for c in cfg["columns"]]
            for d in days]
    widths = [32 * mm] + [(170 - 32) / len(cfg["columns"]) * mm] * len(cfg["columns"])
    story.append(styled_table([header] + rows, widths))

    story.append(Paragraph("Unusual days this week", styles["Heading2"]))
    if anomalies:
        rows = [[f"{a['date']:%a %d %b}", fmt(kind, a["observed"]),
                 fmt(kind, a["expected"]),
                 "major" if abs(a["score"]) >= 10 else "minor"] for a in anomalies]
        story.append(styled_table(
            [["Date", "Observed", "Expected", "Severity"]] + rows,
            [40 * mm, 40 * mm, 40 * mm, 40 * mm]))
    else:
        story.append(Paragraph("No unusual days were flagged this week.",
                               styles["Normal"]))

    if forecast:
        story.append(Paragraph("Forecast for the next 7 days", styles["Heading2"]))
        rows = [[f"{f['date']:%a %d %b}", fmt(kind, f["value"])] for f in forecast]
        story.append(styled_table([["Date", f"Forecast {cfg['label']}"]] + rows,
                                  [40 * mm, 60 * mm]))
        story.append(Paragraph(f"Model: {forecast[0]['model']}", small))

    story += [Spacer(1, 6 * mm),
              Paragraph(f"Generated {datetime.now():%d %b %Y %H:%M}", small)]
    doc.build(story)


# ----------------------------------------------------------------- Excel
def build_xlsx(path, code, start, end, days, kpis, anomalies, forecast):
    cfg = BUSINESSES[code]
    kind = cfg["kind"]
    bold = Font(bold=True)
    head_font = Font(bold=True, color="FFFFFF")
    head_fill = PatternFill("solid", fgColor="2B6CB0")

    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    ws["A1"] = f"{cfg['title']} weekly report"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = f"Week ending {end:%d %b %Y} ({start:%d %b} to {end:%d %b %Y})"
    ws["A3"] = "Pilot report built on synthetic data."
    row = 5
    for label, value in kpis:
        ws.cell(row=row, column=1, value=label).font = bold
        ws.cell(row=row, column=2, value=value)
        row += 1

    row += 1
    ws.cell(row=row, column=1, value="Unusual days this week").font = bold
    row += 1
    if anomalies:
        for a in anomalies:
            ws.cell(row=row, column=1, value=f"{a['date']:%a %d %b}")
            ws.cell(row=row, column=2, value=(
                f"{fmt(kind, a['observed'])} against about {fmt(kind, a['expected'])} "
                f"expected ({'major' if abs(a['score']) >= 10 else 'minor'})"))
            row += 1
    else:
        ws.cell(row=row, column=1, value="None flagged")
    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["B"].width = 56

    daily = wb.create_sheet("Daily")
    headers = ["Date"] + [c[1] for c in cfg["columns"]]
    daily.append(headers)
    for cell in daily[1]:
        cell.font = head_font
        cell.fill = head_fill
        cell.alignment = Alignment(horizontal="center")
    for d in days:
        daily.append([d["date"]] + [d[c[0]] for c in cfg["columns"]])
    for r in range(2, len(days) + 2):
        daily.cell(row=r, column=1).number_format = "ddd dd mmm"
        for i, c in enumerate(cfg["columns"], start=2):
            daily.cell(row=r, column=i).number_format = (
                "0.0" if c[2] == "pct" else "#,##0")
    for i in range(1, len(headers) + 1):
        daily.column_dimensions[chr(64 + i)].width = 20

    chart = BarChart()
    chart.title = f"Daily {cfg['label']}"
    chart.height, chart.width = 8, 16
    chart.add_data(Reference(daily, min_col=2, min_row=1, max_row=len(days) + 1),
                   titles_from_data=True)
    chart.set_categories(Reference(daily, min_col=1, min_row=2, max_row=len(days) + 1))
    chart.legend = None
    daily.add_chart(chart, "H2")

    if forecast:
        fc = wb.create_sheet("Forecast")
        fc.append(["Date", f"Forecast {cfg['label']}", "Model"])
        for cell in fc[1]:
            cell.font = head_font
            cell.fill = head_fill
        for f in forecast:
            fc.append([f["date"], round(f["value"], 1), f["model"]])
        for r in range(2, len(forecast) + 2):
            fc.cell(row=r, column=1).number_format = "ddd dd mmm"
        fc.column_dimensions["A"].width = 16
        fc.column_dimensions["B"].width = 22
        fc.column_dimensions["C"].width = 32
    wb.save(path)


# ---------------------------------------------------------------- driver
def generate(code, end, out_dir):
    """Build the PDF and Excel report for one business. Returns (pdf, xlsx)."""
    start = week_start(end)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    with engine.connect() as conn:
        days = fetch_days(conn, code, start, end)
        if not days:
            raise ValueError(f"No {code} data between {start} and {end}")
        previous = fetch_days(conn, code, start - timedelta(days=7),
                              start - timedelta(days=1))
        weather = fetch_weather(conn, start, end)
        anomalies = fetch_anomalies(conn, code, start, end)
        forecast = fetch_forecast(conn, code, end)

    kpis = summarize(code, days, previous, weather)
    stem = f"{code}_week_ending_{end:%Y-%m-%d}"
    pdf, xlsx = out_dir / f"{stem}.pdf", out_dir / f"{stem}.xlsx"
    build_pdf(pdf, code, start, end, days, kpis, anomalies, forecast)
    build_xlsx(xlsx, code, start, end, days, kpis, anomalies, forecast)
    return pdf, xlsx


def record(conn, code, end, files, root):
    """Write the generated files to the reports table and the audit log."""
    start = week_start(end)
    business_id = conn.execute(text("SELECT id FROM businesses WHERE code = :c"),
                               {"c": code}).scalar()
    conn.execute(text("DELETE FROM reports WHERE business_id = :b AND week_start = :s"),
                 {"b": business_id, "s": start})
    for f in files:
        rel = Path(f).resolve().relative_to(Path(root).resolve()).as_posix()
        conn.execute(
            text("INSERT INTO reports (business_id, week_start, file_path) "
                 "VALUES (:b, :s, :p)"),
            {"b": business_id, "s": start, "p": rel})
    conn.execute(
        text("INSERT INTO audit_log (user_id, action, detail) "
             "VALUES (NULL, 'report_generated', :d)"),
        {"d": f"{code} {start} to {end}: pdf and xlsx"})