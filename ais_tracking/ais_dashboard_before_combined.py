import json
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd
import pydeck as pdk
import streamlit as st
from area_classifier import get_vessel_area


# SEA_SENTINEL_STATE_LABEL_LAYER
# Reference label positions, not official state boundaries.
STATE_LABELS = {
    "Perlis": (6.44, 100.20),
    "Kedah": (6.05, 100.65),
    "Pulau Pinang": (5.35, 100.30),
    "Perak": (4.60, 101.00),
    "Selangor": (3.10, 101.35),
    "Negeri Sembilan": (2.72, 102.10),
    "Melaka": (2.20, 102.25),
    "Johor": (2.00, 103.45),
    "Pahang": (3.85, 102.85),
    "Terengganu": (5.10, 103.05),
    "Kelantan": (5.95, 102.20),
    "Sabah": (5.55, 116.40),
    "Sarawak": (2.70, 113.00),
}

STATE_COASTAL_ZONES = {
    "Johor": (1.0, 2.55, 102.45, 104.7),
    "Melaka": (2.0, 2.6, 101.8, 102.6),
    "Negeri Sembilan": (2.4, 2.9, 101.4, 102.1),
    "Selangor": (2.65, 3.8, 100.6, 101.7),
    "Perak": (3.7, 5.05, 99.7, 101.25),
    "Pulau Pinang": (5.1, 5.7, 99.8, 100.75),
    "Kedah": (5.7, 6.45, 99.2, 100.9),
    "Perlis": (6.35, 6.75, 99.8, 100.5),
    "Pahang": (2.6, 4.25, 102.7, 105.1),
    "Terengganu": (4.15, 5.85, 102.5, 105.1),
    "Kelantan": (5.75, 7.0, 101.8, 104.6),
    "Sabah": (4.0, 8.0, 115.0, 120.5),
    "Sarawak": (0.5, 5.5, 108.0, 115.0),
}

def nearby_state(lat, lon):
    for name, (south, north, west, east) in STATE_COASTAL_ZONES.items():
        if south <= lat <= north and west <= lon <= east:
            return name
    return "Other / Offshore"

def state_label_layer():
    data = [
        {"name": name, "latitude": lat, "longitude": lon}
        for name, (lat, lon) in STATE_LABELS.items()
    ]
    return pdk.Layer(
        "TextLayer",
        data=data,
        get_position="[longitude, latitude]",
        get_text="name",
        get_size=15,
        size_min_pixels=10,
        size_max_pixels=18,
        get_color=[235, 247, 255, 255],
        get_background_color=[5, 22, 36, 0],
        background=False,
        get_alignment_baseline="center",
        get_text_anchor="middle",
        pickable=False
    )

st.set_page_config(
    page_title="SEA SENTINEL V2 | Maritime Command Centre",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
.stApp {
    background: linear-gradient(145deg,#07111f,#0b2034 65%,#07111f);
    color: #e6f4ff;
}
[data-testid="stSidebar"] {
    background: #081725;
    border-right: 1px solid #1b4057;
}
h1,h2,h3 {color:#e9f8ff !important;}
div[data-testid="stMetric"] {
    background:#10283b;
    border:1px solid #24506b;
    border-radius:14px;
    padding:16px;
}
div[data-testid="stMetricValue"] {color:#52d9ff;}
div[data-testid="stMetricLabel"] {color:#b3ccdc;}
.stButton button {
    border:1px solid #287c9b;
    background:#10364b;
    color:#e9f8ff;
}
</style>
""", unsafe_allow_html=True)

REGIONS = {
    "All Malaysian Regions": (4.3, 109.0, 4.8),
    "Johor / Singapore Strait": (1.85, 103.65, 8.2),
    "Selangor / Port Klang": (3.0, 101.25, 8.4),
    "Penang / Northern Strait": (5.38, 100.32, 9.0),
    "Kelantan": (6.15, 102.25, 8.2),
    "Terengganu": (5.05, 103.15, 8.0),
    "Pahang": (3.75, 103.35, 7.6),
    "Perak": (4.25, 100.6, 8.0),
    "Kedah": (6.0, 100.25, 8.2),
    "Perlis": (6.42, 100.16, 9.0),
    "Negeri Sembilan": (2.45, 101.75, 8.4),
    "Melaka": (2.2, 102.2, 8.5),
    "Sabah": (5.8, 116.6, 7.0),
    "Sarawak": (2.8, 112.2, 6.5),
    "East Coast Peninsula": (4.7, 103.75, 7.0),
}

def classify_region(lat, lon):
    # Approximate monitoring zones, not territorial boundaries.
    if 1.0 <= lat <= 2.5 and 102.5 <= lon <= 104.5:
        return "Johor / Singapore Strait"
    if 2.5 <= lat <= 3.8 and 100.5 <= lon <= 102.0:
        return "Selangor / Port Klang"
    if 4.0 <= lat <= 6.5 and 99.0 <= lon <= 101.5:
        return "Penang / Northern Strait"
    if 2.5 <= lat <= 7.5 and 102.0 <= lon <= 106.0:
        return "East Coast Peninsula"
    if 4.0 <= lat <= 8.0 and 115.0 <= lon <= 120.5:
        return "Sabah"
    if 0.5 <= lat <= 5.5 and 108.0 <= lon <= 115.5:
        return "Sarawak"
    return "Other"

DATA_FILE = Path(__file__).resolve().parent / "vessels_live.json"

def load_data():
    try:
        snapshot = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        if isinstance(snapshot, dict):
            vessels = snapshot.get("vessels", [])
            updated = snapshot.get("updated_at")
        else:
            vessels = snapshot
            updated = None
        if not isinstance(vessels, list):
            vessels = []
    except (OSError, ValueError, TypeError):
        vessels, updated = [], None

    df = pd.DataFrame(vessels)
    if df.empty:
        return pd.DataFrame(), updated

    for col in ("latitude", "longitude", "speed_knots", "course"):
        if col not in df.columns:
            df[col] = None
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["latitude", "longitude"]).copy()
    df = df[
        df["latitude"].between(-90, 90)
        & df["longitude"].between(-180, 180)
    ].copy()

    if df.empty:
        return df, updated

    if "name" not in df.columns:
        df["name"] = "Unknown"
    if "mmsi" not in df.columns:
        df["mmsi"] = "Unknown"
    if "last_seen" not in df.columns:
        df["last_seen"] = None

    df["name"] = df["name"].fillna("Unknown").astype(str)
    df["mmsi"] = df["mmsi"].fillna("Unknown").astype(str)
    df["region"] = df.apply(
        lambda r: classify_region(r["latitude"], r["longitude"]),
        axis=1
    )
    df["area_name"] = df.apply(
        lambda r: get_vessel_area(r["latitude"], r["longitude"])[0],
        axis=1
    )
    df["movement"] = df["speed_knots"].apply(
        lambda x: "Moving" if pd.notna(x) and x > 0.5 else "Stationary / Unknown"
    )
    df["marker_color"] = df["movement"].apply(
        lambda x: [0, 220, 255, 220]
        if x == "Moving" else [65, 145, 255, 220]
    )
    return df, updated

st.sidebar.markdown("## 🌊 SEA SENTINEL V2")
st.sidebar.caption("MARITIME SITUATIONAL AWARENESS")
st.sidebar.divider()

region = st.sidebar.selectbox(
    "Monitoring Region",
    list(REGIONS.keys())
)
search = st.sidebar.text_input(
    "Search vessel name or MMSI",
    placeholder="Enter vessel name or MMSI"
)
movement = st.sidebar.selectbox(
    "Vessel Movement",
    ["All vessels", "Moving only", "Stationary / Unknown"]
)
st.sidebar.caption("Data source: AISStream position reports")
st.sidebar.caption("Regional labels are approximate.")
st.sidebar.divider()

st.title("🌊 SEA SENTINEL V2")
st.caption("AIS / GPS VESSEL TRACKING • MALAYSIAN MARITIME REGIONS")
st.markdown("### Maritime Command Centre")

@st.fragment(run_every="15s")
def live_dashboard():
    df, updated = load_data()

    if updated:
        try:
            dt = datetime.fromisoformat(str(updated).replace("Z", "+00:00"))
            age = max(
                0,
                int((datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds())
            )
            freshness = f"{age}s ago"
        except (ValueError, TypeError, OverflowError):
            freshness = "Unknown"
    else:
        freshness = "No snapshot"

    filtered = df.copy()

    if not filtered.empty:
        if region != "All Malaysian Regions":
            if region in STATE_COASTAL_ZONES:
                filtered = filtered[
                    filtered.apply(
                        lambda r: nearby_state(
                            r["latitude"], r["longitude"]
                        ) == region,
                        axis=1
                    )
                ]
            else:
                filtered = filtered[filtered["region"] == region]

        if search.strip():
            mask = (
                filtered["name"].str.contains(search.strip(), case=False, regex=False)
                | filtered["mmsi"].str.contains(search.strip(), case=False, regex=False)
            )
            filtered = filtered[mask]

        if movement == "Moving only":
            filtered = filtered[filtered["movement"] == "Moving"]
        elif movement == "Stationary / Unknown":
            filtered = filtered[filtered["movement"] == "Stationary / Unknown"]

    a, b, c, d = st.columns(4)
    a.metric("Total AIS Vessels", len(df))
    b.metric("Displayed Vessels", len(filtered))
    c.metric(
        "Moving in View",
        int((filtered["movement"] == "Moving").sum())
        if not filtered.empty else 0
    )
    d.metric("Snapshot Updated", freshness)

    map_tab, directory_tab, telemetry_tab = st.tabs([
        "🗺️ Live Vessel Map",
        "📋 Vessel Directory",
        "📡 Vessel Telemetry"
    ])

    with map_tab:
        st.markdown(f"#### {region}")
        lat, lon, zoom = REGIONS[region]

        layer = pdk.Layer(
            "ScatterplotLayer",
            data=filtered,
            get_position="[longitude, latitude]",
            get_fill_color="marker_color",
            get_radius=650,
            radius_min_pixels=9,
            radius_max_pixels=22,
            stroked=True,
            get_line_color=[235, 250, 255, 255],
            line_width_min_pixels=1,
            pickable=True,
            auto_highlight=True
        )

        deck = pdk.Deck(
            map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
            initial_view_state=pdk.ViewState(
                latitude=lat,
                longitude=lon,
                zoom=zoom,
                pitch=0
            ),
            layers=[state_label_layer(), layer],
            tooltip={
                "html": """
                <b>{name}</b><br/>
                MMSI: {mmsi}<br/>
                Area: {area_name}<br/>
                Region: {region}<br/>
                Speed: {speed_knots} knots<br/>
                Status: {movement}
                """,
                "style": {
                    "backgroundColor": "#0a2438",
                    "color": "#e8f8ff",
                    "fontSize": "13px"
                }
            }
        )

        st.pydeck_chart(deck, width="stretch", height=550)

        if filtered.empty:
            st.info(
                "No AIS vessel positions in this selected view. "
                "The map still shows the chosen region. "
                "Wait for new reports or choose another region."
            )
        else:
            st.caption(
                "Hover over a blue marker to see the vessel name, "
                "MMSI, approximate area and speed."
            )

    with directory_tab:
        st.markdown("#### Vessel Directory")

        if filtered.empty:
            st.info("No vessels match the selected filters.")
        else:
            columns = [
                "name", "mmsi", "area_name", "region",
                "latitude", "longitude", "speed_knots",
                "course", "movement", "last_seen"
            ]
            st.dataframe(
                filtered[columns],
                width="stretch",
                hide_index=True
            )

            csv = filtered[columns].to_csv(index=False).encode("utf-8")
            st.download_button(
                "Download Vessel Directory (CSV)",
                data=csv,
                file_name="sea_sentinel_vessels.csv",
                mime="text/csv"
            )

    with telemetry_tab:
        st.markdown("#### Vessel Telemetry")

        if filtered.empty:
            st.info("No vessel available for inspection.")
        else:
            options = list(filtered.index)
            chosen = st.selectbox(
                "Select vessel",
                options,
                format_func=lambda i: (
                    f"{filtered.loc[i, 'name']} "
                    f"({filtered.loc[i, 'mmsi']})"
                )
            )
            vessel = filtered.loc[chosen]

            st.markdown(f"### {vessel['name']}")
            st.write("**MMSI:**", vessel["mmsi"])
            st.write("**Approximate area:**", vessel["area_name"])
            st.write("**Monitoring region:**", vessel["region"])
            st.write("**Latitude:**", vessel["latitude"])
            st.write("**Longitude:**", vessel["longitude"])
            st.write("**Speed (knots):**", vessel["speed_knots"])
            st.write("**Course:**", vessel["course"])
            st.write("**Movement:**", vessel["movement"])
            st.write("**Last AIS report:**", vessel["last_seen"])

    st.caption(
        "AIS positions may be delayed or incomplete. "
        "Nearest coastal area is not proof of maritime jurisdiction. "
        "AIS vessel class is not a threat assessment."
    )

live_dashboard()

# SEA SENTINEL V2 - Dark Theme Label Visibility Fix
st.markdown("""
<style>
/* Main text and widget labels */
.stApp,
.stApp p,
.stApp label,
.stApp span,
.stApp small {
    color: #EAF4FF;
}

/* Sidebar labels */
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span {
    color: #EAF4FF !important;
}

/* Statistics card labels */
[data-testid="stMetricLabel"],
[data-testid="stMetricLabel"] *,
[data-testid="stMetric"] label {
    color: #D7E9F8 !important;
    opacity: 1 !important;
}

/* Navigation tab labels */
button[data-baseweb="tab"] {
    color: #C8DDED !important;
}
button[data-baseweb="tab"][aria-selected="true"] {
    color: #36D0FF !important;
    font-weight: 700 !important;
}

/* Select boxes and text inputs */
[data-baseweb="select"] *,
[data-baseweb="input"] input {
    color: #172A3B !important;
}

/* Dataframe and headings */
.stApp h1, .stApp h2, .stApp h3,
.stApp h4, .stApp h5 {
    color: #FFFFFF !important;
}

/* Captions */
[data-testid="stCaptionContainer"] *,
.stCaption {
    color: #B7C9D9 !important;
}

/* Sidebar background */
[data-testid="stSidebar"] {
    background-color: #071827;
}
</style>
""", unsafe_allow_html=True)
