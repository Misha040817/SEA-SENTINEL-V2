from area_classifier import get_vessel_area
import streamlit as st
import pandas as pd
import pydeck as pdk
import json
from pathlib import Path
from datetime import datetime, timezone

st.set_page_config(
    page_title="SEA SENTINEL V2 | AIS Tracking",
    page_icon="🚢",
    layout="wide"
)

st.title("🚢 SEA SENTINEL V2")
st.subheader("AIS / GPS Vessel Tracking")

st.caption("Maritime vessel intelligence and position monitoring")

DATA_FILE = Path(__file__).resolve().parent / "vessels_live.json"

if DATA_FILE.exists():
    try:
        snapshot = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        if isinstance(snapshot, dict):
            vessels = snapshot.get("vessels", [])
        elif isinstance(snapshot, list):
            vessels = snapshot
        else:
            vessels = []
        if not isinstance(vessels, list):
            vessels = []
    except (OSError, json.JSONDecodeError):
        vessels = []
else:
    vessels = []

df = pd.DataFrame(vessels)

if not df.empty:
    locations = df.apply(
        lambda row: get_vessel_area(
            row.get("latitude"),
            row.get("longitude")
        ),
        axis=1
    )
    df["area_name"] = locations.apply(lambda x: x[0])
    df["region"] = locations.apply(lambda x: x[1])


if not df.empty and {"latitude", "longitude"}.issubset(df.columns):
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    df = df.dropna(subset=["latitude", "longitude"])
    df = df[
        df["latitude"].between(-90, 90)
        & df["longitude"].between(-180, 180)
    ]

st.sidebar.header("AIS Tracking")
st.sidebar.info("Data source: AISStream")

if st.sidebar.button("Refresh vessel data"):
    st.rerun()

col1, col2, col3 = st.columns(3)

with col1:
    st.metric("Tracked Vessels", len(df))

with col2:
    moving = (
        (pd.to_numeric(df["speed_knots"], errors="coerce") > 0.5).sum()
        if "speed_knots" in df.columns else 0
    )
    st.metric("Moving Vessels", int(moving))

with col3:
    st.metric("AIS Data Source", "AISStream")

tab1, tab2, tab3 = st.tabs([
    "🗺️ Vessel Map",
    "📋 Vessel Directory",
    "📡 Vessel Telemetry"
])

with tab1:
    st.subheader("Vessel Position Map")

    if df.empty:
        st.warning(
            "No vessel data available yet. "
            "The AIS client must save vessel positions to vessels_live.json."
        )
    else:
        layer = pdk.Layer(
            "ScatterplotLayer",
            data=df,
            get_position="[longitude, latitude]",
            get_radius=300,
            get_fill_color=[0, 200, 255, 190],
            pickable=True
        )

        view = pdk.ViewState(
            latitude=float(df["latitude"].mean()),
            longitude=float(df["longitude"].mean()),
            zoom=9,
            pitch=0
        )

        st.pydeck_chart(
            pdk.Deck(
                layers=[layer],
                initial_view_state=view,
                tooltip={
                    "html": "<b>MMSI:</b> {mmsi}<br/><b>Name:</b> {name}",
                    "style": {"color": "white"}
                }
            )
        )

with tab2:
    st.subheader("Vessel Directory")
    if df.empty:
        st.info("No vessel records available.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)

with tab3:
    st.subheader("Vessel Telemetry")

    if df.empty or "mmsi" not in df.columns:
        st.info("Waiting for vessel data.")
    else:
        selected = st.selectbox(
            "Select vessel MMSI",
            df["mmsi"].astype(str).tolist()
        )

        vessel = df[df["mmsi"].astype(str) == selected].iloc[0]

        st.write("**Vessel Name:**", vessel.get("name", "Unknown"))
        st.write("**MMSI:**", selected)
        st.write("**Latitude:**", vessel["latitude"])
        st.write("**Longitude:**", vessel["longitude"])
        st.write("**Speed (knots):**", vessel.get("speed_knots", "N/A"))
        st.write("**Course:**", vessel.get("course", "N/A"))
        st.write("**Last Seen:**", vessel.get("last_seen", "N/A"))

st.caption("SEA SENTINEL V2 | AIS/GPS Tracking Module")
