"""Rule-based question assistant.

It never turns the user's text into SQL. The question is matched to one of a few
known question types, and each type runs a fixed, parameterised query. The queries
run on a read-only database login (fuji_reader) that cannot see the users or audit
tables and cannot change anything.
"""
import calendar
import os
import re
from datetime import date, timedelta

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()
_engine = None


def reader():
    global _engine
    if _engine is None:
        url = os.getenv("READER_DATABASE_URL")
        if not url:
            raise RuntimeError("READER_DATABASE_URL is not set in .env")
        _engine = create_engine(url, pool_pre_ping=True)
    return _engine


BUSINESSES = {
    "railway": {
        "label": "railway passengers",
        "words": ["railway", "train", "rail", "passenger", "station", "ridership"],
        "sql": ("SELECT date, sum(passengers)::float AS value FROM ridership_daily "
                "WHERE date BETWEEN :s AND :e GROUP BY date ORDER BY date"),
    },
    "hotels": {
        "label": "hotel occupancy",
        "words": ["hotel", "occupancy", "room", "booking", "guest"],
        "sql": ("SELECT date, round(sum(rooms_booked)::numeric / "
                "sum(rooms_available) * 100, 1)::float AS value FROM hotel_daily "
                "WHERE date BETWEEN :s AND :e GROUP BY date ORDER BY date"),
    },
    "park": {
        "label": "park visitors",
        "words": ["park", "visitor", "fuji-q", "amusement", "queue"],
        "sql": ("SELECT date, visitors::float AS value FROM park_daily "
                "WHERE date BETWEEN :s AND :e ORDER BY date"),
    },
}

HELP = ("I can answer questions such as: 'Which day last month had the lowest "
        "occupancy?', 'What was the average ridership in September 2025?', "
        "'Why did park visitors drop on 18 September 2025?', 'Show unusual days "
        "for hotels in 2025', or 'What is the forecast for railway next week?'")

MONTHS = {n.lower(): i for i, n in enumerate(calendar.month_name) if n}
MONTHS.update({n.lower(): i for i, n in enumerate(calendar.month_abbr) if n})
MONTHS["sept"] = 9
MONTH_RE = "|".join(sorted(MONTHS, key=len, reverse=True))

DMY = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({MONTH_RE})\s*,?\s*(\d{{4}})\b")
MDY = re.compile(rf"\b({MONTH_RE})\s+(\d{{1,2}})(?:st|nd|rd|th)?\s*,?\s*(\d{{4}})\b")
MY = re.compile(rf"\b({MONTH_RE})\s*,?\s*(\d{{4}})\b")
IN_MONTH = re.compile(rf"\bin\s+({MONTH_RE})\b")

LOW = ["lowest", "least", "minimum", "worst", "quietest", "fewest", "smallest"]
HIGH = ["highest", "busiest", "maximum", "peak", "largest", "biggest", "most"]


def fmt(code, value):
    return f"{value:.1f}%" if code == "hotels" else f"{value:,.0f}"


def detect_business(q):
    scores = {code: sum(w in q for w in cfg["words"])
              for code, cfg in BUSINESSES.items()}
    best = max(scores.values())
    if best == 0:
        return None
    winners = [c for c, s in scores.items() if s == best]
    return winners[0] if len(winners) == 1 else None


def detect_intent(q):
    def has(words):
        return any(re.search(r"\b" + re.escape(w), q) for w in words)

    if has(["why", "reason", "explain", "cause"]):
        return "why"
    if has(["forecast", "predict", "next week", "tomorrow", "next 7 days"]):
        return "forecast"
    if has(["unusual", "anomal", "strange", "abnormal", "outlier"]):
        return "unusual"
    if has(LOW):
        return "lowest"
    if has(HIGH):
        return "highest"
    if has(["average", "typical"]):
        return "average"
    if has(["total", "how many", "sum of"]):
        return "total"
    return None


def month_range(year, month):
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def latest_full_month(latest):
    if latest.day == calendar.monthrange(latest.year, latest.month)[1]:
        return latest.year, latest.month
    previous = latest.replace(day=1) - timedelta(days=1)
    return previous.year, previous.month


def parse_period(q, latest):
    """Return (start, end, label), or None if the question names no period."""
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", q)
    if m:
        try:
            d = date(int(m[1]), int(m[2]), int(m[3]))
            return d, d, f"{d:%d %b %Y}"
        except ValueError:
            pass
    m = DMY.search(q)
    if m:
        try:
            d = date(int(m[3]), MONTHS[m[2]], int(m[1]))
            return d, d, f"{d:%d %b %Y}"
        except ValueError:
            pass
    m = MDY.search(q)
    if m:
        try:
            d = date(int(m[3]), MONTHS[m[1]], int(m[2]))
            return d, d, f"{d:%d %b %Y}"
        except ValueError:
            pass
    m = MY.search(q)
    if m:
        start, end = month_range(int(m[2]), MONTHS[m[1]])
        return start, end, f"{start:%B %Y}"
    if "last month" in q:
        start, end = month_range(*latest_full_month(latest))
        return start, end, f"{start:%B %Y}"
    if "this month" in q:
        return latest.replace(day=1), latest, f"{latest:%B %Y} so far"
    if "last week" in q:
        return latest - timedelta(days=6), latest, "the last 7 days of data"
    m = re.search(r"last (\d+) days", q)
    if m:
        n = max(1, min(int(m[1]), 3650))
        return latest - timedelta(days=n - 1), latest, f"the last {n} days of data"
    m = IN_MONTH.search(q)
    if m:
        month = MONTHS[m[1]]
        year = latest.year if date(latest.year, month, 1) <= latest else latest.year - 1
        start, end = month_range(year, month)
        return start, end, f"{start:%B %Y}"
    m = re.search(r"\b(20\d{2})\b", q)
    if m:
        year = int(m[1])
        return date(year, 1, 1), date(year, 12, 31), str(year)
    return None


def ok(code, intent, period, answer):
    return {"status": "ok", "business": code, "intent": intent,
            "period": period, "answer": answer}


def series(conn, code, start, end):
    return conn.execute(text(BUSINESSES[code]["sql"]), {"s": start, "e": end}).all()


def extreme(conn, code, intent, start, end, label):
    rows = series(conn, code, start, end)
    if not rows:
        return ok(code, intent, label, f"I have no data for {label}.")
    pick = min if intent == "lowest" else max
    day, value = pick(rows, key=lambda r: r[1])
    word = "lowest" if intent == "lowest" else "highest"
    return ok(code, intent, label,
              f"The {word} day for {BUSINESSES[code]['label']} in {label} was "
              f"{day:%A %d %b %Y}, with {fmt(code, value)}.")


def summary(conn, code, intent, start, end, label):
    rows = series(conn, code, start, end)
    if not rows:
        return ok(code, intent, label, f"I have no data for {label}.")
    values = [r[1] for r in rows]
    name = BUSINESSES[code]["label"]
    if intent == "total" and code != "hotels":
        return ok(code, intent, label,
                  f"Total {name} in {label}: {fmt(code, sum(values))} "
                  f"over {len(values)} days.")
    return ok(code, intent, label,
              f"Average {name} in {label}: {fmt(code, sum(values) / len(values))} "
              f"per day, over {len(values)} days.")


def forecast(conn, code):
    rows = conn.execute(
        text("SELECT f.target_date, f.predicted_value::float FROM forecasts f "
             "JOIN businesses b ON b.id = f.business_id WHERE b.code = :c "
             "ORDER BY f.target_date"), {"c": code}).all()
    if not rows:
        return ok(code, "forecast", "next 7 days", "There is no forecast stored yet.")
    parts = "; ".join(f"{d:%a %d %b}: {fmt(code, v)}" for d, v in rows)
    return ok(code, "forecast", f"{rows[0][0]:%d %b} to {rows[-1][0]:%d %b %Y}",
              f"Forecast for {BUSINESSES[code]['label']}: {parts}.")


def unusual(conn, code, start, end, label):
    rows = conn.execute(
        text("SELECT a.date, a.observed::float, a.expected::float, a.score::float "
             "FROM anomalies a JOIN businesses b ON b.id = a.business_id "
             "WHERE b.code = :c AND a.date BETWEEN :s AND :e "
             "ORDER BY abs(a.score) DESC"), {"c": code, "s": start, "e": end}).all()
    if not rows:
        return ok(code, "unusual", label, f"No unusual days were found in {label}.")
    major = sum(1 for r in rows if abs(r[3]) >= 10)
    top = "; ".join(f"{d:%d %b %Y} ({fmt(code, o)} against about {fmt(code, x)} expected)"
                    for d, o, x, _ in rows[:3])
    return ok(code, "unusual", label,
              f"{len(rows)} unusual days in {label} ({major} major). "
              f"The largest: {top}.")


def explain_day(conn, code, day):
    cfg = BUSINESSES[code]
    rows = series(conn, code, day - timedelta(days=28), day)
    values = {r[0]: r[1] for r in rows}
    if day not in values:
        return f"I have no {cfg['label']} figure for {day:%d %b %Y}."
    actual = values[day]

    flag = conn.execute(
        text("SELECT a.expected::float, a.score::float FROM anomalies a "
             "JOIN businesses b ON b.id = a.business_id "
             "WHERE b.code = :c AND a.date = :d"), {"c": code, "d": day}).first()
    if flag:
        expected, score = flag
    else:
        same = [values[d] for d in (day - timedelta(days=7 * k) for k in range(1, 5))
                if d in values]
        expected = sum(same) / len(same) if same else None
        score = None

    text_parts = [f"On {day:%A %d %b %Y}, {cfg['label']} was {fmt(code, actual)}"]
    if expected:
        change = (actual - expected) / expected * 100
        text_parts[0] += (f", against about {fmt(code, expected)} expected "
                          f"({change:+.0f}%).")
    else:
        text_parts[0] += "."

    wx = conn.execute(
        text("SELECT rainfall_mm::float, sunshine_hours::float FROM weather_daily "
             "WHERE date = :d"), {"d": day}).first()
    avg = conn.execute(
        text("SELECT avg(rainfall_mm)::float, avg(sunshine_hours)::float "
             "FROM weather_daily")).first()
    holiday = conn.execute(text("SELECT name FROM holidays WHERE date = :d"),
                           {"d": day}).scalar()

    factors = []
    if wx:
        rain, sun = wx
        text_parts.append(f"Rainfall that day was {rain:.0f} mm with {sun:.1f} hours "
                          f"of sunshine (an average day has {avg[0]:.1f} mm and "
                          f"{avg[1]:.1f} hours).")
        if rain >= max(40, 4 * avg[0]):
            factors.append("heavy rain")
    if holiday:
        text_parts.append(f"It was a public holiday ({holiday}).")
        factors.append("a public holiday")
    if day.weekday() >= 5:
        factors.append("a weekend")
    if score is not None:
        level = "major" if abs(score) >= 10 else "minor"
        text_parts.append(f"The system flagged this day as unusual "
                          f"(score {score:.1f}, {level}).")
    if factors:
        text_parts.append("Possible factors in the data: " + ", ".join(factors) + ".")
    return " ".join(text_parts)


def why(conn, code, start, end, label):
    if start == end:
        return ok(code, "why", label, explain_day(conn, code, start))
    top = conn.execute(
        text("SELECT a.date FROM anomalies a JOIN businesses b ON b.id = a.business_id "
             "WHERE b.code = :c AND a.date BETWEEN :s AND :e "
             "ORDER BY abs(a.score) DESC LIMIT 1"),
        {"c": code, "s": start, "e": end}).scalar()
    if top is None:
        return ok(code, "why", label,
                  "Please name a specific date, for example 'Why did visitors drop "
                  "on 18 September 2025?'")
    return ok(code, "why", label,
              f"The most unusual day in {label} was {top:%d %b %Y}. "
              + explain_day(conn, code, top))


def ask(question, allowed):
    """Answer one question. `allowed` lists the business codes the user may see."""
    q = question.lower().strip()
    code = detect_business(q)
    if code is None:
        if len(allowed) == 1:
            code = allowed[0]
        else:
            return {"status": "needs_business",
                    "answer": "Which business do you mean: railway, hotels or park?"}
    if code not in allowed:
        return {"status": "forbidden", "business": code}

    intent = detect_intent(q)
    if intent is None:
        return {"status": "not_understood", "business": code, "answer": HELP}

    with reader().connect() as conn:
        low, high = conn.execute(
            text("SELECT min(date), max(date) FROM ridership_daily")).one()
        if intent == "forecast":
            return forecast(conn, code)

        period = parse_period(q, high)
        if period is None:
            start, end = low, high
            label = f"the whole data period ({low:%b %Y} to {high:%b %Y})"
        else:
            start, end, label = period
            if end < low or start > high:
                return {"status": "no_data", "business": code,
                        "answer": f"I only have data from {low:%d %b %Y} "
                                  f"to {high:%d %b %Y}."}
            start, end = max(start, low), min(end, high)

        if intent == "why":
            return why(conn, code, start, end, label)
        if intent == "unusual":
            return unusual(conn, code, start, end, label)
        if intent in ("lowest", "highest"):
            return extreme(conn, code, intent, start, end, label)
        return summary(conn, code, intent, start, end, label)