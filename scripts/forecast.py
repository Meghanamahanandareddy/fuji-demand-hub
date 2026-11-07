"""Compare forecasting models on a held-out month, then store next-week forecasts.

Train: everything up to 2026-09-30.  Test: October 2026.
The best model that does not need weather is refitted on all data and used to
forecast the next 7 days into the forecasts table.
"""
import os
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sklearn.ensemble import HistGradientBoostingRegressor
from sqlalchemy import create_engine, text
from statsmodels.tsa.holtwinters import ExponentialSmoothing

warnings.filterwarnings("ignore")
load_dotenv()
engine = create_engine(os.getenv("DATABASE_URL"))

CUTOFF = pd.Timestamp("2026-09-30")
TEST_START = pd.Timestamp("2026-10-01")
TEST_END = pd.Timestamp("2026-10-31")
FORECAST_START = pd.Timestamp("2026-11-01")
FORECAST_END = pd.Timestamp("2026-11-07")
DOCS = Path(__file__).resolve().parent.parent / "docs"


def read(sql):
    with engine.connect() as conn:
        df = pd.read_sql(text(sql), conn)
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date").sort_index()


def load_series():
    rail = read("SELECT date, sum(passengers) AS value "
                "FROM ridership_daily GROUP BY date")["value"]
    hot = read("SELECT date, sum(rooms_booked)::float / sum(rooms_available) * 100 "
               "AS value FROM hotel_daily GROUP BY date")["value"]
    park = read("SELECT date, visitors AS value FROM park_daily")["value"]
    return {
        "railway": ("passengers", rail.astype(float).asfreq("D")),
        "hotels": ("occupancy_pct", hot.astype(float).asfreq("D")),
        "park": ("visitors", park.astype(float).asfreq("D")),
    }


def calendar_features(index, holiday_dates, events):
    f = pd.DataFrame(index=index)
    f["dow"] = index.dayofweek
    f["month"] = index.month
    f["doy"] = index.dayofyear
    f["trend"] = (index - pd.Timestamp("2024-01-01")).days
    f["holiday"] = index.isin(holiday_dates).astype(int)
    f["event"] = 0
    for start, end in events:
        f.loc[(index >= start) & (index <= end), "event"] = 1
    f["obon"] = ((index.month == 8) & (index.day >= 13)
                 & (index.day <= 16)).astype(int)
    f["newyear"] = (((index.month == 12) & (index.day >= 29))
                    | ((index.month == 1) & (index.day <= 3))).astype(int)
    return f


def mape(actual, predicted):
    return float(np.mean(np.abs((actual - predicted) / actual)) * 100)


def baseline(train, horizon):
    last = train.iloc[-28:]
    by_dow = last.groupby(last.index.dayofweek).mean()
    return pd.Series(by_dow.reindex(horizon.dayofweek).to_numpy(), index=horizon)


def holt_winters(train, horizon):
    model = ExponentialSmoothing(
        train, trend="add", damped_trend=True, seasonal="mul",
        seasonal_periods=7, initialization_method="estimated").fit()
    return pd.Series(model.forecast(len(horizon)).to_numpy(), index=horizon)


def boosted(X_train, y_train, X_future):
    model = HistGradientBoostingRegressor(
        max_iter=300, learning_rate=0.06, random_state=42)
    model.fit(X_train, y_train)
    return pd.Series(model.predict(X_future), index=X_future.index)


MODELS = {
    "Baseline (last 4 same weekdays)":
        lambda tr, hz, cal, wx: baseline(tr, hz),
    "Holt-Winters (weekly seasonality)":
        lambda tr, hz, cal, wx: holt_winters(tr, hz),
    "Gradient boosting (calendar)":
        lambda tr, hz, cal, wx: boosted(cal.loc[tr.index], tr, cal.loc[hz]),
    "Gradient boosting (calendar + weather)":
        lambda tr, hz, cal, wx: boosted(wx.loc[tr.index], tr, wx.loc[hz]),
}
NEEDS_WEATHER = {"Gradient boosting (calendar + weather)"}


def main():
    holiday_dates = read("SELECT date FROM holidays").index
    with engine.connect() as conn:
        ev = pd.read_sql(text("SELECT start_date, end_date FROM events"), conn)
    events = list(zip(pd.to_datetime(ev["start_date"]),
                      pd.to_datetime(ev["end_date"])))
    weather = read("SELECT date, temperature_c::float AS temp, "
                   "rainfall_mm::float AS rain, sunshine_hours::float AS sun "
                   "FROM weather_daily")

    index = pd.date_range("2024-01-01", FORECAST_END)
    cal = calendar_features(index, holiday_dates, events)
    cal_wx = cal.join(weather)

    series = load_series()
    results, stored, backtests = [], [], []

    for business, (metric, y) in series.items():
        train = y.loc[:CUTOFF]
        test = y.loc[TEST_START:TEST_END]
        scores = {}
        bt = pd.DataFrame({"actual": test})
        for name, fn in MODELS.items():
            pred = fn(train, test.index, cal, cal_wx)
            scores[name] = mape(test, pred)
            bt[name] = pred.to_numpy()
            results.append({"business": business, "metric": metric,
                            "model": name, "mape_pct": round(scores[name], 2)})
        bt.insert(0, "business", business)
        backtests.append(bt.rename_axis("date").reset_index())

        usable = {k: v for k, v in scores.items() if k not in NEEDS_WEATHER}
        best = min(usable, key=usable.get)
        print(f"\n{business} ({metric}), test month October 2026")
        for name, score in sorted(scores.items(), key=lambda kv: kv[1]):
            tag = "  <-- used for forecasts" if name == best else ""
            print(f"  {score:6.2f}%  {name}{tag}")

        full = y.loc[:TEST_END]
        horizon = pd.date_range(FORECAST_START, FORECAST_END)
        forecast = MODELS[best](full, horizon, cal, cal_wx)
        for day, value in forecast.items():
            stored.append({"code": business, "d": day.date(), "m": metric,
                           "v": round(float(value), 2), "model": best})

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM forecasts"))
        for row in stored:
            conn.execute(
                text("INSERT INTO forecasts (business_id, target_date, metric, "
                     "predicted_value, model_name) "
                     "SELECT id, :d, :m, :v, :model FROM businesses "
                     "WHERE code = :code"), row)

    pd.DataFrame(results).to_csv(DOCS / "forecast_results.csv", index=False)
    pd.concat(backtests).to_csv(DOCS / "forecast_backtest.csv", index=False)
    print(f"\nStored {len(stored)} forecast rows for "
          f"{FORECAST_START:%d %b} to {FORECAST_END:%d %b %Y}.")
    print("Scores saved to docs/forecast_results.csv")
    print("Daily backtest saved to docs/forecast_backtest.csv")


if __name__ == "__main__":
    main()