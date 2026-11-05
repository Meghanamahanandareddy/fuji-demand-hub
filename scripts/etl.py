"""ETL: clean the raw CSV files and load them into PostgreSQL.

Every problem found is written to data_quality_log. The script is safe to rerun:
rows already in the database are skipped, and the quality log is refreshed.
"""
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()
engine = create_engine(os.getenv("DATABASE_URL"))
RAW = Path(__file__).resolve().parent.parent / "data" / "raw"

issues = []  # (source_file, issue_type, detail, action_taken)


def log(source, issue, count, detail, action):
    if count:
        issues.append((source, issue, f"{count} rows: {detail}", action))
        print(f"  [{source}] {issue}: {count} rows -> {action}")


def location_map(conn, business_code):
    """Return {lowercase name: (location id, official name)} for one business."""
    rows = conn.execute(
        text("SELECT l.id, l.name FROM locations l "
             "JOIN businesses b ON b.id = l.business_id WHERE b.code = :c"),
        {"c": business_code},
    ).all()
    return {name.lower(): (loc_id, name) for loc_id, name in rows}


def clean_ridership(conn):
    src = "ridership.csv"
    df = pd.read_csv(RAW / src)
    print(f"{src}: {len(df):,} raw rows")

    df["date"] = pd.to_datetime(df["date"], format="%d/%m/%Y")
    log(src, "date_format", len(df), "dates were dd/mm/yyyy", "converted to ISO dates")

    stations = location_map(conn, "railway")
    trimmed = df["station"].str.strip()
    log(src, "extra_whitespace", int((df["station"] != trimmed).sum()),
        "station names with extra spaces", "trimmed")

    canonical = trimmed.str.lower().map(
        lambda k: stations[k][1] if k in stations else None)
    unknown = canonical.isna()
    log(src, "unknown_station", int(unknown.sum()),
        "station not in the locations table", "dropped")
    log(src, "inconsistent_case", int(((trimmed != canonical) & ~unknown).sum()),
        "station names in the wrong case", "standardised to official name")

    df["station"] = canonical
    df = df[~unknown].copy()
    df["location_id"] = df["station"].map({v[1]: v[0] for v in stations.values()})

    dup = df.duplicated(["date", "location_id", "ticket_type"])
    log(src, "duplicate_rows", int(dup.sum()),
        "same date, station and ticket type repeated", "kept the first copy")
    df = df[~dup].sort_values(["location_id", "ticket_type", "date"])

    missing = df["passengers"].isna()
    log(src, "missing_value", int(missing.sum()), "passengers left blank",
        "filled by interpolation within station and ticket type")
    df["passengers"] = (
        df.groupby(["location_id", "ticket_type"])["passengers"]
        .transform(lambda s: s.interpolate(limit_direction="both"))
        .round().astype(int))

    df["date"] = df["date"].dt.date
    return df[["date", "location_id", "ticket_type", "passengers"]]


def clean_hotels(conn):
    src = "hotels.csv"
    df = pd.read_csv(RAW / src, parse_dates=["date"])
    print(f"{src}: {len(df):,} raw rows")

    locs = location_map(conn, "hotels")
    ids = df["hotel"].str.strip().str.lower().map(
        lambda k: locs[k][0] if k in locs else None)
    unknown = ids.isna()
    log(src, "unknown_hotel", int(unknown.sum()),
        "hotel not in the locations table", "dropped")
    df["location_id"] = ids
    df = df[~unknown].copy()
    df["location_id"] = df["location_id"].astype(int)

    dup = df.duplicated(["date", "location_id"])
    log(src, "duplicate_rows", int(dup.sum()), "same date and hotel repeated",
        "kept the first copy")
    df = df[~dup].sort_values(["location_id", "date"])

    missing = df["avg_room_rate_jpy"].isna()
    log(src, "missing_value", int(missing.sum()), "room rate left blank",
        "filled by interpolation within hotel")
    df["avg_room_rate_jpy"] = (
        df.groupby("location_id")["avg_room_rate_jpy"]
        .transform(lambda s: s.interpolate(limit_direction="both"))
        .round().astype(int))

    over = df["rooms_booked"] > df["rooms_available"]
    log(src, "booked_exceeds_available", int(over.sum()),
        "more rooms booked than the hotel has", "capped at rooms available")
    df.loc[over, "rooms_booked"] = df.loc[over, "rooms_available"]

    df["date"] = df["date"].dt.date
    return df[["date", "location_id", "rooms_available", "rooms_booked",
               "avg_room_rate_jpy"]]


def clean_park(conn):
    src = "park.csv"
    df = pd.read_csv(RAW / src, parse_dates=["date"])
    print(f"{src}: {len(df):,} raw rows")

    locs = location_map(conn, "park")
    ids = df["location"].str.strip().str.lower().map(
        lambda k: locs[k][0] if k in locs else None)
    unknown = ids.isna()
    log(src, "unknown_location", int(unknown.sum()),
        "location not in the locations table", "dropped")
    df["location_id"] = ids
    df = df[~unknown].copy()
    df["location_id"] = df["location_id"].astype(int)

    dup = df.duplicated(["date", "location_id"])
    log(src, "duplicate_rows", int(dup.sum()), "same date repeated",
        "kept the first copy")
    df = df[~dup]

    df["date"] = df["date"].dt.date
    return df[["date", "location_id", "visitors", "avg_wait_minutes",
               "revenue_jpy"]]


def clean_weather():
    src = "weather.csv"
    df = pd.read_csv(RAW / src, parse_dates=["date"])
    print(f"{src}: {len(df):,} raw rows")

    dup = df.duplicated(["date"])
    log(src, "duplicate_rows", int(dup.sum()), "same date repeated",
        "kept the first copy")
    df = df[~dup].sort_values("date")

    missing = df["temperature_c"].isna()
    log(src, "missing_value", int(missing.sum()), "temperature left blank",
        "filled by interpolation between neighbouring days")
    df["temperature_c"] = df["temperature_c"].interpolate(
        limit_direction="both").round(1)

    df["date"] = df["date"].dt.date
    return df[["date", "temperature_c", "rainfall_mm", "sunshine_hours"]]


def load(conn, table, df, conflict):
    before = conn.execute(text(f"SELECT count(*) FROM {table}")).scalar()
    columns = list(df.columns)
    sql = (f"INSERT INTO {table} ({', '.join(columns)}) "
           f"VALUES ({', '.join(':' + c for c in columns)}) "
           f"ON CONFLICT ({conflict}) DO NOTHING")
    conn.execute(text(sql), df.to_dict("records"))
    after = conn.execute(text(f"SELECT count(*) FROM {table}")).scalar()
    print(f"  {table}: {after - before:,} new rows loaded, "
          f"{after:,} rows in the table now")


def main():
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM data_quality_log"))

        print("Cleaning raw files...")
        rid = clean_ridership(conn)
        hot = clean_hotels(conn)
        park = clean_park(conn)
        wx = clean_weather()

        print("Loading into PostgreSQL...")
        load(conn, "ridership_daily", rid, "date, location_id, ticket_type")
        load(conn, "hotel_daily", hot, "date, location_id")
        load(conn, "park_daily", park, "date, location_id")
        load(conn, "weather_daily", wx, "date")

        for source, issue, detail, action in issues:
            conn.execute(
                text("INSERT INTO data_quality_log "
                     "(source_file, issue_type, detail, action_taken) "
                     "VALUES (:s, :i, :d, :a)"),
                {"s": source, "i": issue, "d": detail, "a": action},
            )
        print(f"Done. {len(issues)} data-quality entries logged.")


if __name__ == "__main__":
    main()