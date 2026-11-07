"""Detect unusual days: compare each day with what the calendar alone predicts.

Each 60-day block is predicted by a model trained on all the other days, so the
model never judges days it has seen. Days whose robust score is at or beyond the
threshold are stored in the anomalies table.

The day-of-year feature is left out on purpose: with it, the model would learn
that mid-September is always low (from the 2025 typhoon) and raise false alarms
in other years.
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sqlalchemy import text

from forecast import calendar_features, engine, load_series, read

THRESHOLD = 3.5
FOLD_DAYS = 60


def episodes(flagged):
    """Group consecutive flagged dates into (first day, last day, worst score)."""
    out, current = [], None
    for day, score in flagged.items():
        if current and (day - current["end"]).days == 1:
            current["end"] = day
            current["worst"] = max(current["worst"], abs(score))
        else:
            if current:
                out.append(current)
            current = {"start": day, "end": day, "worst": abs(score)}
    if current:
        out.append(current)
    return out


def main():
    holiday_dates = read("SELECT date FROM holidays").index
    with engine.connect() as conn:
        ev = pd.read_sql(text("SELECT start_date, end_date FROM events"), conn)
    events = list(zip(pd.to_datetime(ev["start_date"]),
                      pd.to_datetime(ev["end_date"])))
    index = pd.date_range("2024-01-01", "2026-10-31")
    cal = calendar_features(index, holiday_dates, events)
    cal = cal.drop(columns=["doy"])

    stored = []
    for business, (metric, y) in load_series().items():
        expected = pd.Series(index=y.index, dtype=float)
        for start in range(0, len(y), FOLD_DAYS):
            test_idx = y.index[start:start + FOLD_DAYS]
            train_idx = y.index.difference(test_idx)
            model = HistGradientBoostingRegressor(
                max_iter=300, learning_rate=0.06, random_state=42)
            model.fit(cal.loc[train_idx], y.loc[train_idx])
            expected.loc[test_idx] = model.predict(cal.loc[test_idx])

        resid = np.log(y / expected)
        median = resid.median()
        mad = (resid - median).abs().median()
        score = (resid - median) / (1.4826 * mad)
        flagged = score[score.abs() >= THRESHOLD]

        print(f"\n{business} ({metric}): {len(flagged)} unusual days")
        for ep in episodes(flagged):
            span = (f"{ep['start']:%d %b %Y}" if ep["start"] == ep["end"]
                    else f"{ep['start']:%d %b} to {ep['end']:%d %b %Y}")
            print(f"  {span}  (worst score {ep['worst']:.1f})")

        for day, s in flagged.items():
            stored.append({"code": business, "d": day.date(), "m": metric,
                           "o": round(float(y[day]), 2),
                           "x": round(float(expected[day]), 2),
                           "s": round(float(s), 2)})

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM anomalies"))
        for row in stored:
            conn.execute(
                text("INSERT INTO anomalies (business_id, date, metric, observed, "
                     "expected, score) SELECT id, :d, :m, :o, :x, :s "
                     "FROM businesses WHERE code = :code"), row)
    print(f"\nStored {len(stored)} anomaly rows.")


if __name__ == "__main__":
    main()