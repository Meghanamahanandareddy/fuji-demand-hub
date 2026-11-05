"""Generate synthetic raw data for the Mt. Fuji Tourism Demand Hub.

Writes CSV files to data/raw/. By default the files contain a few realistic
data-quality problems (blanks, duplicates, inconsistent names) for the ETL step
to find and fix. Use --clean to skip them.
"""
import argparse
from pathlib import Path

import holidays
import numpy as np
import pandas as pd

SEED = 42
START, END = "2024-01-01", "2026-10-31"
TYPHOON_START = pd.Timestamp("2025-09-16")
TYPHOON_END = pd.Timestamp("2025-09-20")
OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

parser = argparse.ArgumentParser()
parser.add_argument("--clean", action="store_true",
                    help="skip the injected data-quality problems")
args = parser.parse_args()

rng = np.random.default_rng(SEED)
dates = pd.date_range(START, END, freq="D")
n = len(dates)
doy = dates.dayofyear.to_numpy()
month = dates.month.to_numpy()
day = dates.day.to_numpy()
dow = dates.dayofweek.to_numpy()  # Monday = 0

typhoon = ((dates >= TYPHOON_START) & (dates <= TYPHOON_END))
recovery = ((dates > TYPHOON_END) &
            (dates <= TYPHOON_END + pd.Timedelta(days=2)))

# ---------------------------------------------------------------- weather
temp = 11 + 13 * np.sin(2 * np.pi * (doy - 110) / 365) + rng.normal(0, 2.5, n)
rain_prob = np.array([.15, .15, .20, .25, .28, .45,
                      .40, .35, .40, .30, .20, .12])[month - 1]
rain = np.where(rng.random(n) < rain_prob, rng.gamma(1.5, 8.0, n), 0.0)
rain = np.where(typhoon, rng.uniform(120, 250, n), rain)
sunshine = np.clip(
    rng.normal(7.0, 2.5, n)
    - np.where(rain > 0, 3.0 + np.minimum(rain, 50) * 0.05, 0.0), 0, 13)
sunshine = np.where(typhoon, rng.uniform(0, 0.5, n), sunshine)

wx = pd.DataFrame({
    "date": dates,
    "temperature_c": temp.round(1),
    "rainfall_mm": rain.round(1),
    "sunshine_hours": sunshine.round(1),
})

# ----------------------------------------------------------- demand index
dow_f = np.array([0.85, 0.80, 0.80, 0.85, 1.00, 1.35, 1.20])[dow]
month_f = np.array([1.00, 0.80, 0.90, 1.15, 1.20, 0.85,
                    1.10, 1.40, 0.95, 1.05, 1.20, 1.00])[month - 1]

EVENTS = [((4, 1), (4, 20), 1.15), ((4, 20), (5, 31), 1.10),
          ((7, 1), (8, 31), 1.10), ((11, 1), (11, 25), 1.15)]
event_f = np.ones(n)
for year in range(2024, 2027):
    for (sm, sd), (em, ed), f in EVENTS:
        m = ((dates >= pd.Timestamp(year, sm, sd)) &
             (dates <= pd.Timestamp(year, em, ed)))
        event_f = np.where(m, np.maximum(event_f, f), event_f)

jp = holidays.Japan(years=range(2024, 2027))
holiday_f = np.where([d.date() in jp for d in dates], 1.30, 1.0)
obon_f = np.where((month == 8) & (day >= 13) & (day <= 16), 1.25, 1.0)
newyear_f = np.where(((month == 12) & (day >= 29)) |
                     ((month == 1) & (day <= 3)), 1.25, 1.0)
rain_f = 1 - np.minimum(rain, 50) / 50 * 0.35
sun_f = 1 + (sunshine - 6) * 0.01
growth_f = 1 + 0.04 * ((dates - dates[0]).days.to_numpy() / 365.25)
typhoon_f = np.where(typhoon, 0.15, np.where(recovery, 0.70, 1.0))

demand = (dow_f * month_f * event_f * holiday_f * obon_f * newyear_f
          * rain_f * sun_f * growth_f * typhoon_f
          * rng.lognormal(0, 0.06, n))

# --------------------------------------------------------------- railway
STATIONS = {  # name: (base daily passengers, commuter share)
    "Otsuki": (6000, 0.45), "Shimoyoshida": (3500, 0.35),
    "Fuji-Q Highland": (4000, 0.15), "Kawaguchiko": (7000, 0.20),
}
off_day = (dow >= 5) | (holiday_f > 1)
commute_f = np.where(off_day, 0.45, 1.0) * np.where(typhoon, 0.6, 1.0)

frames = []
for station, (base, share) in STATIONS.items():
    noise = rng.lognormal(0, 0.05, n)
    means = {
        "commuter_pass": base * share * commute_f,
        "regular": base * (1 - share) * 0.6 * demand,
        "tourist_pass": base * (1 - share) * 0.4 * demand ** 1.3,
    }
    for ticket, mean in means.items():
        frames.append(pd.DataFrame({
            "date": dates, "station": station, "ticket_type": ticket,
            "passengers": rng.poisson(mean * noise),
        }))
rid = pd.concat(frames, ignore_index=True)

# ---------------------------------------------------------------- hotels
HOTELS = {  # name: (rooms, base nightly rate in JPY); names are fictional
    "Lakeside Hotel": (60, 18000), "Fuji View Hotel": (80, 22000),
    "Highland Resort Hotel": (120, 15000),
}
frames = []
for hotel, (rooms, base_rate) in HOTELS.items():
    occ = np.clip(0.62 * demand ** 0.85 * rng.normal(1, 0.05, n), 0.05, 0.99)
    rate = np.round(base_rate * (0.80 + 0.40 * occ)
                    * (0.95 + 0.10 * month_f)).astype(int)
    frames.append(pd.DataFrame({
        "date": dates, "hotel": hotel, "rooms_available": rooms,
        "rooms_booked": rng.binomial(rooms, occ), "avg_room_rate_jpy": rate,
    }))
hot = pd.concat(frames, ignore_index=True)

# ------------------------------------------------------------------ park
visitors = rng.poisson(14000 * demand * rain_f)
wait = np.clip(np.round(8 + (visitors / 22000) ** 2 * 70
                        + rng.normal(0, 4, n)), 3, 150).astype(int)
revenue = np.round(visitors * rng.normal(7800, 400, n)).astype(np.int64)
park = pd.DataFrame({
    "date": dates, "location": "Fuji-Q Highland Park", "visitors": visitors,
    "avg_wait_minutes": wait, "revenue_jpy": revenue,
})

# --------------------------------------- realistic data-quality problems
if not args.clean:
    rid["passengers"] = rid["passengers"].astype("Int64")
    rid.loc[rid.sample(frac=0.005, random_state=SEED).index,
            "passengers"] = pd.NA
    up = rid.sample(frac=0.01, random_state=SEED + 1).index
    rid.loc[up, "station"] = rid.loc[up, "station"].str.upper()
    sp = rid.sample(frac=0.01, random_state=SEED + 2).index
    rid.loc[sp, "station"] = rid.loc[sp, "station"] + " "
    rid = pd.concat([rid, rid.sample(frac=0.003, random_state=SEED + 3)],
                    ignore_index=True)

    hot["avg_room_rate_jpy"] = hot["avg_room_rate_jpy"].astype("Int64")
    hot.loc[hot.sample(frac=0.005, random_state=SEED + 4).index,
            "avg_room_rate_jpy"] = pd.NA
    bad = hot.sample(frac=0.002, random_state=SEED + 5).index
    hot.loc[bad, "rooms_booked"] = (hot.loc[bad, "rooms_available"]
                                    + rng.integers(1, 6, len(bad)))

    wx.loc[wx.sample(frac=0.005, random_state=SEED + 6).index,
           "temperature_c"] = np.nan

# ----------------------------------------------------------------- write
rid = rid.sort_values(["date", "station"], kind="stable")
rid["date"] = rid["date"].dt.strftime("%d/%m/%Y")  # legacy system format
for frame in (hot, park, wx):
    frame["date"] = frame["date"].dt.strftime("%Y-%m-%d")

OUT_DIR.mkdir(parents=True, exist_ok=True)
for name, frame in [("ridership", rid), ("hotels", hot),
                    ("park", park), ("weather", wx)]:
    frame.to_csv(OUT_DIR / f"{name}.csv", index=False)
    print(f"{name}.csv: {len(frame):,} rows")

print(f"Typhoon-week demand index: {demand[typhoon].mean():.2f} "
      f"(normal days: {demand[~typhoon & ~recovery].mean():.2f})")