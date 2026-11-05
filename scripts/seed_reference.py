import os
from datetime import date

import holidays
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()
engine = create_engine(os.getenv("DATABASE_URL"))

BUSINESSES = [("railway", "Railway"), ("hotels", "Hotels"), ("park", "Amusement Park")]

# Station names are from the public Fujikyuko Line; check them on fujikyu.co.jp.
# Hotel names are fictional.
LOCATIONS = {
    "railway": ["Otsuki", "Shimoyoshida", "Fuji-Q Highland", "Kawaguchiko"],
    "hotels": ["Lakeside Hotel", "Fuji View Hotel", "Highland Resort Hotel"],
        "park": ["Fuji-Q Highland Park"],
}

# Approximate seasons, written by hand
EVENT_TEMPLATES = [
    ("Cherry blossom season", (4, 1), (4, 20)),
    ("Shibazakura season", (4, 20), (5, 31)),
    ("Summer climbing season", (7, 1), (8, 31)),
    ("Autumn leaves season", (11, 1), (11, 25)),
]

YEARS = [2024, 2025, 2026]

with engine.begin() as conn:
    for code, name in BUSINESSES:
        conn.execute(
            text("INSERT INTO businesses (code, name) VALUES (:c, :n) "
                 "ON CONFLICT (code) DO NOTHING"),
            {"c": code, "n": name},
        )

    for code, names in LOCATIONS.items():
        business_id = conn.execute(
            text("SELECT id FROM businesses WHERE code = :c"), {"c": code}
        ).scalar()
        for name in names:
            conn.execute(
                text("INSERT INTO locations (business_id, name) VALUES (:b, :n) "
                     "ON CONFLICT (business_id, name) DO NOTHING"),
                {"b": business_id, "n": name},
            )

    for d, name in sorted(holidays.Japan(years=YEARS).items()):
        conn.execute(
            text("INSERT INTO holidays (date, name) VALUES (:d, :n) "
                 "ON CONFLICT (date) DO NOTHING"),
            {"d": d, "n": name},
        )

    # events has no unique key, so clear and reload to keep this rerunnable
    conn.execute(text("DELETE FROM events"))
    for year in YEARS:
        for name, (sm, sd), (em, ed) in EVENT_TEMPLATES:
            conn.execute(
                text("INSERT INTO events (name, start_date, end_date) "
                     "VALUES (:n, :s, :e)"),
                {"n": name, "s": date(year, sm, sd), "e": date(year, em, ed)},
            )

print("Reference data loaded.")