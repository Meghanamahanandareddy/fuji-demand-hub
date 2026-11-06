import pandas as pd
import plotly.express as px
import streamlit as st

from app import queries

st.set_page_config(page_title="Mt. Fuji Tourism Demand Hub", layout="wide")
st.title("Mt. Fuji Tourism Demand Hub")
st.caption("Pilot built on synthetic data. It does not use Fuji Kyuko's real data.")


@st.cache_data(ttl=300)
def load(name, *args):
    return getattr(queries, name)(*args)


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


tab_rail, tab_hotel, tab_park, tab_cross = st.tabs(
    ["Railway", "Hotels", "Amusement park", "Cross-business"])

# ------------------------------------------------------------------ railway
with tab_rail:
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
        fig = px.line(d, x="date", y=["passengers", "7-day average"],
                      title="Daily passengers")
        st.plotly_chart(fig, width='stretch')
        by_station = rid.groupby("station", as_index=False)["passengers"].sum()
        st.plotly_chart(px.bar(by_station, x="station", y="passengers",
                               title="Passengers by station"),
                        width='stretch')

# ------------------------------------------------------------------- hotels
with tab_hotel:
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
                                title="Occupancy (%)"), width='stretch')
        by_hotel = h.groupby("hotel", as_index=False).agg(
            booked=("rooms_booked", "sum"), available=("rooms_available", "sum"))
        by_hotel["occupancy_pct"] = by_hotel["booked"] / by_hotel["available"] * 100
        st.plotly_chart(px.bar(by_hotel, x="hotel", y="occupancy_pct",
                               title="Average occupancy by hotel"),
                        width='stretch')

# --------------------------------------------------------------------- park
with tab_park:
    p = load("park_daily", start, end)
    c1, c2, c3 = st.columns(3)
    c1.metric("Total visitors", f"{p['visitors'].sum():,}")
    c2.metric("Average wait", f"{p['avg_wait_minutes'].mean():.0f} min")
    c3.metric("Revenue", f"¥{p['revenue_jpy'].sum():,}")
    d = with_trend(p, "visitors")
    st.plotly_chart(px.line(d, x="date", y=["visitors", "7-day average"],
                            title="Daily visitors"), width='stretch')
    st.plotly_chart(px.line(p, x="date", y="avg_wait_minutes",
                            title="Average wait time (minutes)"),
                    width='stretch')

# ------------------------------------------------------------ cross-business
with tab_cross:
    rail_all = load("railway_daily", start, end, queries.location_names("railway"))
    hot_all = load("hotel_daily", start, end, queries.location_names("hotels"))
    wx = load("weather_daily", start, end)

    rail_day = rail_all.groupby("date")["passengers"].sum().rename("Railway passengers")
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
                    width='stretch')

    st.subheader("What drives demand")
    corr = merged.corr().round(2)
    st.plotly_chart(px.imshow(corr, text_auto=True, zmin=-1, zmax=1,
                              color_continuous_scale="RdBu"),
                    width='stretch')
