"""All database reads for the dashboard live here, so access control can be
added in one place later."""
import pandas as pd
from sqlalchemy import text

from app.db import engine


def _read(sql, **params):
    with engine.connect() as conn:
        df = pd.read_sql(text(sql), conn, params=params)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
    return df


def data_range():
    df = _read("SELECT min(date) AS lo, max(date) AS hi FROM ridership_daily")

    def as_date(value):
        return value.date() if hasattr(value, "date") else value

    return as_date(df["lo"][0]), as_date(df["hi"][0])


def location_names(business_code):
    df = _read(
        "SELECT l.name FROM locations l JOIN businesses b ON b.id = l.business_id "
        "WHERE b.code = :c ORDER BY l.name", c=business_code)
    return df["name"].tolist()


def railway_daily(start, end, stations):
    return _read(
        "SELECT r.date, l.name AS station, r.ticket_type, r.passengers "
        "FROM ridership_daily r JOIN locations l ON l.id = r.location_id "
        "WHERE r.date BETWEEN :s AND :e AND l.name = ANY(:names) "
        "ORDER BY r.date", s=start, e=end, names=stations)


def hotel_daily(start, end, hotels):
    return _read(
        "SELECT h.date, l.name AS hotel, h.rooms_available, h.rooms_booked, "
        "h.avg_room_rate_jpy "
        "FROM hotel_daily h JOIN locations l ON l.id = h.location_id "
        "WHERE h.date BETWEEN :s AND :e AND l.name = ANY(:names) "
        "ORDER BY h.date", s=start, e=end, names=hotels)


def park_daily(start, end):
    return _read(
        "SELECT date, visitors, avg_wait_minutes, revenue_jpy FROM park_daily "
        "WHERE date BETWEEN :s AND :e ORDER BY date", s=start, e=end)


def weather_daily(start, end):
    return _read(
        "SELECT date, temperature_c::float AS temperature_c, "
        "rainfall_mm::float AS rainfall_mm, sunshine_hours::float AS sunshine_hours "
        "FROM weather_daily WHERE date BETWEEN :s AND :e ORDER BY date",
        s=start, e=end)

def forecasts():
    return _read(
        "SELECT b.code, f.target_date AS date, f.metric, "
        "f.predicted_value::float AS predicted, f.model_name "
        "FROM forecasts f JOIN businesses b ON b.id = f.business_id "
        "ORDER BY b.code, f.target_date")
