import time
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from app import dashboard_auth, queries

st.set_page_config(page_title="Mt. Fuji Tourism Demand Hub", layout="wide")

SESSION_SECONDS = 8 * 3600
MAX_FAILED_ATTEMPTS = 5
ORDER = ["railway", "hotels", "park"]
NAMES = {"railway": "Railway", "hotels": "Hotels", "park": "Amusement park"}


@st.cache_data(ttl=300)
def load(name, *args):
    return getattr(queries, name)(*args)


# ------------------------------------------------------------------- login
def login_screen():
    st.title("Mt. Fuji Tourism Demand Hub")
    st.caption("Pilot built on synthetic data. It does not use Fuji Kyuko's real data.")
    st.subheader("Sign in")
    failed = st.session_state.get("failed", 0)
    if failed >= MAX_FAILED_ATTEMPTS:
        st.error("Too many failed attempts. Reload the page to try again.")
        return
    with st.form("login"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in")
    if submitted:
        user = dashboard_auth.authenticate(username, password)
        if user is None:
            st.session_state["failed"] = failed + 1
            st.error("Wrong username or password.")
        else:
            user["at"] = time.time()
            st.session_state["user"] = user
            st.session_state["failed"] = 0
            st.rerun()


user = st.session_state.get("user")
if user and time.time() - user["at"] > SESSION_SECONDS:
    dashboard_auth.logout(user["id"])
    st.session_state.pop("user")
    user = None
    st.warning("Your session expired. Please sign in again.")
if user is None:
    login_screen()
    st.stop()

allowed = [c for c in ORDER if c in user["businesses"]]
if not allowed:
    st.error("Your account has no business access. Ask an administrator.")
    st.stop()

# ----------------------------------------------------------------- sidebar
st.title("Mt. Fuji Tourism Demand Hub")
st.caption("Pilot built on synthetic data. It does not use Fuji Kyuko's real data.")

with st.sidebar:
    st.write(f"Signed in as **{user['full_name']}** ({user['role']})")
    st.caption("Access: " + ", ".join(NAMES[c] for c in allowed))
    if st.button("Sign out"):
        dashboard_auth.logout(user["id"])
        st.session_state.pop("user")
        st.rerun()

lo, hi = queries.data_range()
picked = st.sidebar.date_input("Date range", value=(lo, hi), min_value=lo, max_value=hi)
if len(picked) != 2:
    st.info("Pick both a start and an end date.")
    st.stop()
start, end = picked


def with_trend(df, col):
    df = df.copy()
    df["7-day average"] = df[col].rolling(7, min_periods=1).mean()
    return df


labels = [NAMES[c] for c in allowed]
if set(ORDER) <= set(allowed):
    labels.append("Cross-business")
labels += ["Forecast", "Unusual days"]
tabs = dict(zip(labels, st.tabs(labels)))

# ------------------------------------------------------------------ railway
if "Railway" in tabs:
    with tabs["Railway"]:
        stations = st.multiselect("Stations", queries.location_names("railway"),
                                  default=queries.location_names("railway"))
        if stations:
            rid = load("railway_daily", start, end, stations)
            daily = rid.groupby("date", as_index=False)["passengers"].sum()
            c1, c2, c3 = st.columns(3)
            c1.metric("Total passengers", f"{daily['passengers'].sum():,}")
            c2.metric("Average per day", f"{daily['passengers'].mean():,.0f}")
            peak = daily.loc[daily["passengers"].idxmax()]
            c3.metric("Busiest day", f"{peak['date']:%d %b %Y}",
                      f"{peak['passengers']:,} passengers")
            d = with_trend(daily, "passengers")
            st.plotly_chart(px.line(d, x="date", y=["passengers", "7-day average"],
                                    title="Daily passengers"), width="stretch")
            by_station = rid.groupby("station", as_index=False)["passengers"].sum()
            st.plotly_chart(px.bar(by_station, x="station", y="passengers",
                                   title="Passengers by station"), width="stretch")

# ------------------------------------------------------------------- hotels
if "Hotels" in tabs:
    with tabs["Hotels"]:
        hotels = st.multiselect("Hotels", queries.location_names("hotels"),
                                default=queries.location_names("hotels"))
        if hotels:
            h = load("hotel_daily", start, end, hotels)
            h["room_revenue"] = h["rooms_booked"] * h["avg_room_rate_jpy"]
            day = h.groupby("date", as_index=False).agg(
                booked=("rooms_booked", "sum"), available=("rooms_available", "sum"),
                revenue=("room_revenue", "sum"))
            day["occupancy_pct"] = day["booked"] / day["available"] * 100
            c1, c2, c3 = st.columns(3)
            c1.metric("Average occupancy", f"{day['occupancy_pct'].mean():.1f}%")
            c2.metric("Average room rate",
                      f"¥{day['revenue'].sum() / day['booked'].sum():,.0f}")
            c3.metric("Estimated room revenue", f"¥{day['revenue'].sum():,.0f}")
            d = with_trend(day, "occupancy_pct")
            st.plotly_chart(px.line(d, x="date", y=["occupancy_pct", "7-day average"],
                                    title="Occupancy (%)"), width="stretch")
            by_hotel = h.groupby("hotel", as_index=False).agg(
                booked=("rooms_booked", "sum"), available=("rooms_available", "sum"))
            by_hotel["occupancy_pct"] = by_hotel["booked"] / by_hotel["available"] * 100
            st.plotly_chart(px.bar(by_hotel, x="hotel", y="occupancy_pct",
                                   title="Average occupancy by hotel"),
                            width="stretch")

# --------------------------------------------------------------------- park
if "Amusement park" in tabs:
    with tabs["Amusement park"]:
        p = load("park_daily", start, end)
        c1, c2, c3 = st.columns(3)
        c1.metric("Total visitors", f"{p['visitors'].sum():,}")
        c2.metric("Average wait", f"{p['avg_wait_minutes'].mean():.0f} min")
        c3.metric("Revenue", f"¥{p['revenue_jpy'].sum():,}")
        d = with_trend(p, "visitors")
        st.plotly_chart(px.line(d, x="date", y=["visitors", "7-day average"],
                                title="Daily visitors"), width="stretch")
        st.plotly_chart(px.line(p, x="date", y="avg_wait_minutes",
                                title="Average wait time (minutes)"), width="stretch")

# ------------------------------------------------------------ cross-business
if "Cross-business" in tabs:
    with tabs["Cross-business"]:
        rail_all = load("railway_daily", start, end, queries.location_names("railway"))
        hot_all = load("hotel_daily", start, end, queries.location_names("hotels"))
        wx = load("weather_daily", start, end)

        rail_day = rail_all.groupby("date")["passengers"].sum().rename(
            "Railway passengers")
        hot_day = hot_all.groupby("date")[["rooms_booked", "rooms_available"]].sum()
        hot_day = (hot_day["rooms_booked"] / hot_day["rooms_available"] * 100
                   ).rename("Hotel occupancy")
        park_day = load("park_daily", start, end).set_index("date")["visitors"].rename(
            "Park visitors")
        wx = wx.set_index("date")

        merged = pd.concat([rail_day, hot_day, park_day, wx], axis=1).dropna()

        st.subheader("How the businesses move together")
        st.caption("Each series is shown as an index (its own average = 100).")
        business_cols = ["Railway passengers", "Hotel occupancy", "Park visitors"]
        index = merged[business_cols] / merged[business_cols].mean() * 100
        st.plotly_chart(px.line(index.reset_index(), x="date", y=business_cols),
                        width="stretch")

        st.subheader("What drives demand")
        corr = merged.corr().round(2)
        st.plotly_chart(px.imshow(corr, text_auto=True, zmin=-1, zmax=1,
                                  color_continuous_scale="RdBu"), width="stretch")

# ----------------------------------------------------------------- forecast
with tabs["Forecast"]:
    docs = Path(__file__).parent / "docs"
    fc = load("forecasts")
    fc = fc[fc["code"].isin(allowed)]

    st.subheader("Next 7 days")
    titles = {"railway": "Railway passengers", "hotels": "Hotel occupancy (%)",
              "park": "Park visitors"}
    cols = st.columns(len(allowed))
    for col, code in zip(cols, allowed):
        part = fc[fc["code"] == code]
        col.plotly_chart(px.bar(part, x="date", y="predicted", title=titles[code]),
                         width="stretch")

    st.subheader("How the models compared (October 2026, held out)")
    st.caption("Average error in %, lower is better. The models never saw October.")
    res = pd.read_csv(docs / "forecast_results.csv")
    res = res[res["business"].isin(allowed)]
    table = res.pivot(index="model", columns="business", values="mape_pct")
    st.dataframe(table.sort_values(table.columns[0]), width="stretch")

    st.subheader("Predicted against actual, October 2026")
    bt = pd.read_csv(docs / "forecast_backtest.csv", parse_dates=["date"])
    bt = bt[bt["business"].isin(allowed)]
    business = st.selectbox("Business", sorted(bt["business"].unique()))
    model = st.selectbox("Model", [c for c in bt.columns
                                   if c not in ("date", "business", "actual")],
                         index=2)
    part = bt[bt["business"] == business]
    st.plotly_chart(px.line(part, x="date", y=["actual", model]), width="stretch")

# ----------------------------------------------------------- unusual days
with tabs["Unusual days"]:
    st.subheader("Unusual days found automatically")
    st.caption("Each day is compared with what the calendar alone predicts. "
               "Score 10 or more is shown as major, below that as minor. "
               "Rainfall and sunshine are shown as possible explanations.")

    an_business = st.selectbox("Business", allowed, key="an_business")
    an = load("anomalies")
    an = an[an["code"] == an_business].copy()
    an["severity"] = an["score"].abs().ge(10).map({True: "major", False: "minor"})
    an = an.merge(load("weather_daily", lo, hi), on="date", how="left")

    if an_business == "railway":
        r = load("railway_daily", lo, hi, queries.location_names("railway"))
        series = r.groupby("date", as_index=False)["passengers"].sum()
        series.columns = ["date", "value"]
    elif an_business == "hotels":
        hh = load("hotel_daily", lo, hi, queries.location_names("hotels"))
        g = hh.groupby("date")[["rooms_booked", "rooms_available"]].sum()
        series = (g["rooms_booked"] / g["rooms_available"] * 100).reset_index()
        series.columns = ["date", "value"]
    else:
        series = load("park_daily", lo, hi)[["date", "visitors"]]
        series.columns = ["date", "value"]

    c1, c2 = st.columns(2)
    c1.metric("Major events", int((an["severity"] == "major").sum()))
    c2.metric("Minor flags", int((an["severity"] == "minor").sum()))

    fig = px.line(series, x="date", y="value",
                  title="Daily values, unusual days in red")
    fig.add_scatter(x=an["date"], y=an["observed"], mode="markers",
                    name="unusual day", marker=dict(color="red", size=9))
    st.plotly_chart(fig, width="stretch")

    show = an.sort_values("score", key=lambda s: s.abs(), ascending=False)[
        ["date", "severity", "observed", "expected", "score",
         "rainfall_mm", "sunshine_hours"]]
    show["date"] = show["date"].dt.strftime("%d %b %Y")
    st.dataframe(show, width="stretch", hide_index=True)