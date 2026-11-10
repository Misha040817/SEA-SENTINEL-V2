import json
import math
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd
import plotly.graph_objects as go
import folium
import streamlit.components.v1 as components
from html import escape
import streamlit as st
from sea_sentinel_advanced_screening import screen as advanced_screen

st.set_page_config(page_title='SEA SENTINEL | AIS/GPS', page_icon='🚢', layout='wide', initial_sidebar_state='expanded')
BASE = Path(__file__).resolve().parent
DATA_FILE = BASE / 'combined_vessels.json'
HISTORY_DB = BASE / 'ais_position_history.sqlite3'
LIME, CYAN, NAVY = '#C6FF00', '#00D9FF', '#06172A'
REGIONS = {
    'Malaysia': (4.1, 109.0, 5.0),
    'All Malaysian States': (4.1, 109.0, 5.0),
    'Peninsular': (4.2, 102.3, 6.0),
    'Johor / Singapore': (1.4, 103.8, 8.0),
    'Kelantan': (6.0, 102.4, 8.0),
    'Terengganu': (5.0, 103.2, 7.5),
    'Pahang / Kuantan': (3.8, 103.5, 8.0),
    'Port Klang / Selangor': (3.0, 101.2, 8.0),
    'Penang': (5.4, 100.3, 8.0),
    'Sarawak': (2.5, 111.8, 6.2),
    'Sabah': (5.8, 116.0, 6.6),
}
LABELS = [
    {'name':'Kelantan','latitude':5.9,'longitude':102.3},
    {'name':'Terengganu','latitude':5.0,'longitude':103.0},
    {'name':'Pahang','latitude':3.85,'longitude':102.75},
    {'name':'Selangor','latitude':3.25,'longitude':101.25},
    {'name':'Penang','latitude':5.43,'longitude':100.33},
    {'name':'Johor','latitude':2.1,'longitude':103.35},
    {'name':'Sarawak','latitude':2.85,'longitude':113.0},
    {'name':'Sabah','latitude':5.8,'longitude':116.4},
]
MONITORED_AREAS = ['Johor / Singapore','Port Klang / Selangor','Penang','Kelantan','Terengganu','Pahang / Kuantan','Sarawak','Sabah']

# Reference points are state/territory labels, NOT AIS vessel observations.
# Coordinates are approximate administrative reference locations, not maritime boundaries.
STATE_POINTS = {
    'Johor': (2.05, 103.45), 'Kedah': (6.12, 100.37),
    'Kelantan': (5.95, 102.25), 'Melaka': (2.19, 102.25),
    'Negeri Sembilan': (2.73, 101.94), 'Pahang': (3.81, 103.33),
    'Perak': (4.60, 101.09), 'Perlis': (6.44, 100.20),
    'Pulau Pinang': (5.41, 100.33), 'Sabah': (5.98, 116.08),
    'Sarawak': (1.55, 110.35), 'Selangor': (3.07, 101.52),
    'Terengganu': (5.33, 103.14),
    'Kuala Lumpur': (3.14, 101.69), 'Putrajaya': (2.93, 101.69),
    'Labuan': (5.28, 115.24),
}
# The original receiver covers regional boxes, not exact state maritime boundaries.
# Only display regional context, never claim these counts are exact state counts.
STATE_REGION_CONTEXT = {
    'Johor':'Johor / Singapore', 'Kelantan':'Kelantan',
    'Pahang':'Pahang / Kuantan', 'Pulau Pinang':'Penang',
    'Sabah':'Sabah', 'Sarawak':'Sarawak',
    'Selangor':'Port Klang / Selangor', 'Terengganu':'Terengganu',
}
STATE_COLORS = {name: color for name, color in [
    ('Johor','#C6FF00'), ('Kedah','#4AC9FF'), ('Kelantan','#FF4040'),
    ('Melaka','#F6A6FF'), ('Negeri Sembilan','#E8A04D'),
    ('Pahang','#A855F7'), ('Perak','#62E5C3'), ('Perlis','#E6E86B'),
    ('Pulau Pinang','#FF9500'), ('Sabah','#00E5A0'),
    ('Sarawak','#FF4DB8'), ('Selangor','#FFE600'),
    ('Terengganu','#00D9FF'), ('Kuala Lumpur','#B5BDC9'),
    ('Putrajaya','#A4B9CE'), ('Labuan','#EAC0FF')
]}

# Pixel nudges move labels away from busy coastal AIS ship plotting areas.
# These affect only label appearance, never actual AIS coordinates.
STATE_LABEL_OFFSETS = {
    'Johor': (-24, 28), 'Kedah': (-36, -22),
    'Kelantan': (30, -28), 'Melaka': (-45, 18),
    'Negeri Sembilan': (-55, -10), 'Pahang': (-12, 30),
    'Perak': (-40, 0), 'Perlis': (-38, -32),
    'Pulau Pinang': (-56, -9), 'Sabah': (32, -24),
    'Sarawak': (30, 24), 'Selangor': (-55, 16),
    'Terengganu': (45, 4), 'Kuala Lumpur': (55, -30),
    'Putrajaya': (48, 32), 'Labuan': (-43, 22),
}

def plot_state_markers(m, df):
    """Show state labels only where the displayed AIS vessels have a matching monitored region."""
    counts = df.region.value_counts().to_dict() if not df.empty else {}
    group = folium.FeatureGroup(name='State / Federal Territory reference pins', show=True)
    for name, (lat, lon) in STATE_POINTS.items():
        regional_area = STATE_REGION_CONTEXT.get(name)
        count = int(counts.get(regional_area, 0)) if regional_area else 0
        if count == 0:
            continue  # No fresh plotted vessel in this area: hide its label
        context = (f'Regional AIS context: {count} fresh observations (approximate area; not a state-specific count)'
                   if count is not None else 'State-specific AIS coverage not verified')
        if name in ('Kuala Lumpur', 'Putrajaya'):
            context = 'Inland Federal Territory; coastal vessel tracking not applicable'
        info = f'<b>{escape(name)}</b><br>State / territory reference pin (not a vessel)<br>{escape(context)}'
        color = STATE_COLORS[name]
        dx, dy = STATE_LABEL_OFFSETS.get(name, (0, 0))
        folium.Marker(
            [lat, lon], tooltip=f'{name} — state reference',
            popup=folium.Popup(info, max_width=320),
            icon=folium.DivIcon(html=(
                f'<div style="white-space:nowrap;display:inline-block;transform:translate(calc(-50% + {dx}px),calc(-50% + {dy}px));'
                f'background:#081b2ee8;border:1px solid {color};border-radius:7px;'
                f'padding:3px 6px;color:#fff;font:600 11px Arial;box-shadow:0 0 7px {color}55">'
                f'<span style="color:{color}">◆</span> {escape(name)}</div>'))
        ).add_to(group)
    group.add_to(m)

def state_coverage_table(df):
    counts = df.region.value_counts().to_dict() if not df.empty else {}
    rows=[]
    for state in STATE_POINTS:
        context = STATE_REGION_CONTEXT.get(state)
        if state in ('Kuala Lumpur','Putrajaya'):
            status='Inland — coastal AIS not applicable'
        elif context and counts.get(context,0):
            status='Fresh AIS in approximate regional monitoring box'
        elif context:
            status='No fresh AIS in regional monitoring box'
        else:
            status='State-specific AIS coverage not configured / verified'
        rows.append({'State / Federal Territory':state,
                     'Nearby monitoring region':context or 'Not mapped to an existing receiver region',
                     'Fresh regional AIS (not state count)':int(counts.get(context,0)) if context else None,
                     'Coverage status':status})
    return pd.DataFrame(rows)


st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@500;600;700&family=Inter:wght@400;500;600;700;800&display=swap');
:root {color-scheme:dark}
.stApp,[data-testid="stAppViewContainer"] {background:radial-gradient(ellipse at 75% -25%,#10304a 0%,#030b17 50%,#020914 100%);color:#f7fbff;font-family:Inter,sans-serif}
[data-testid="stHeader"] {background:transparent}
[data-testid="stSidebar"] {background:linear-gradient(180deg,#071c30 0%,#041322 100%);border-right:1px solid #13516c}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {color:#b9d1df}
[data-testid="stSidebar"] [role="radiogroup"] label {padding:9px 8px;border-bottom:1px solid #18364b;border-radius:8px}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {background:linear-gradient(90deg,#355c1b,#1b3829);box-shadow:inset 4px 0 #c6ff00}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) p {color:#fff;font-weight:700}
.block-container {padding-top:1.0rem;max-width:1800px}
h1,h2,h3 {font-family:Rajdhani,Inter,sans-serif;letter-spacing:.35px;color:#fff}
[data-testid="stMetric"] {background:linear-gradient(145deg,#09243b,#041524);border:1px solid #1287a8;border-radius:13px;padding:17px 18px;box-shadow:0 0 19px #00d9ff14,inset 0 0 22px #0e425021}
[data-testid="stMetricValue"] {font-family:Rajdhani,sans-serif;font-size:2.65rem;font-weight:800;color:#c6ff00;text-shadow:0 0 15px #c6ff0040}
[data-testid="stMetricLabel"] {font-weight:600;color:#d9ecf6}
[data-testid="stVerticalBlockBorderWrapper"] {border-color:#12728e!important}
[data-testid="stDataFrame"] {border:1px solid #176a87}
[data-testid="stPlotlyChart"] {border:1px solid #0b5471;border-radius:12px;overflow:hidden;background:#06172a}
[data-testid="stDeckGlJsonChart"] {border:1px solid #0b5471;border-radius:12px;overflow:hidden}
.stButton>button,.stDownloadButton>button {background:#0b2941;color:#e6faff;border:1px solid #168eae;border-radius:9px;font-weight:600}
.stButton>button:hover,.stDownloadButton>button:hover {border-color:#c6ff00;color:#c6ff00}
[data-testid="stSelectbox"] div[data-baseweb="select"]>div,[data-testid="stTextInput"] input {background:#0b263c;color:white;border:1px solid #14617c}
.section-head {border-left:7px solid #c6ff00;padding-left:17px;margin:8px 0 22px;filter:drop-shadow(0 0 5px #c6ff0038)}
.section-head h2 {font-size:2.25rem;line-height:1.05;margin:0;font-weight:800}
.section-head p {color:#b6d4e4;margin:0;font-size:14px}
.panel-title {font-family:Rajdhani,sans-serif;font-weight:700;font-size:21px;color:#fff;border-left:5px solid #c6ff00;padding-left:12px;margin:8px 0 12px}
.brand {font-family:Rajdhani,sans-serif;font-size:29px;font-weight:800;letter-spacing:1.5px;color:#fff;line-height:1.05}
.brand b {color:#c6ff00}
.brand-sub {font-size:10px;color:#8fc6d9;letter-spacing:2.4px;margin-top:3px}
.status {padding:8px 12px;border:1px solid #4dbe2d;background:#0b2c1b;color:#c6ff00;border-radius:30px;display:inline-block;font-size:12px;font-weight:700}
.info-strip {border:1px solid #135a76;background:#061b2c;padding:12px 15px;border-radius:11px;color:#b4c9d8;font-size:13px}
.small-note {color:#b8c7d9;font-size:13px}

/* Unified maritime panels for Live AIS / route explorer */
.panel-title {background:linear-gradient(90deg,#0b3048,#071a2d);border:1px solid #126e89;
 border-left:5px solid #c6ff00;border-radius:8px;padding:10px 14px;margin:20px 0 12px;
 box-shadow:0 4px 18px #00d9ff12;font-size:21px}
.route-subheading {font:700 15px Rajdhani,Inter,sans-serif;letter-spacing:1px;color:#00d9ff;
 border-bottom:1px solid #17536b;padding:8px 2px;margin:8px 0 12px}
.route-details {background:linear-gradient(150deg,#0b2d44,#061725);border:1px solid #167b9a;
 border-radius:12px;padding:18px;color:#e8f4fb;font-size:13px;line-height:1.6;min-height:370px}
.route-vessel {font:800 24px Rajdhani,Inter,sans-serif;color:#c6ff00;overflow-wrap:anywhere}
.route-id {color:#a9c6d7;margin-bottom:12px}
.route-detail-label {font-size:10px;font-weight:800;letter-spacing:.9px;color:#00d9ff;margin-top:13px}
[data-testid="stMetric"] {padding:11px 15px!important;min-height:95px!important}
[data-testid="stMetricValue"] {font-size:2rem!important}
[data-testid="stDataFrame"] {border:1px solid #197c9c!important;border-radius:10px!important;
 box-shadow:0 0 18px #00d9ff0c;overflow:hidden}
[data-testid="stDataFrame"] iframe {color-scheme:dark}
/* Accessible high-contrast inputs and help text on dark backgrounds */
.stApp [data-testid="stWidgetLabel"] p, .stApp label p {color:#e8f6ff!important;font-weight:650!important}
.stApp [data-testid="stCaptionContainer"] p, .stApp .stCaption p,
.stApp [data-testid="stMarkdownContainer"] small {color:#bfd8e8!important}
.stApp [data-testid="stTextInput"] input {background:rgba(10,38,58,.94)!important;color:#f5fbff!important;
 border:1px solid #37a9c9!important;box-shadow:0 0 0 1px #124b63 inset}
.stApp [data-testid="stTextInput"] input::placeholder {color:#a7c4d6!important;opacity:1}
.stApp [data-testid="stTextInput"] input:focus {border-color:#c6ff00!important;box-shadow:0 0 0 2px #c6ff0040!important}
/* Glass AIS history grid */
.ais-glass-frame {position:relative;overflow:hidden;border:1px solid rgba(65,200,232,.58);
 border-radius:14px;background:linear-gradient(140deg,rgba(19,59,80,.78),rgba(5,19,37,.91));
 box-shadow:0 12px 35px rgba(0,0,0,.33),inset 0 1px rgba(255,255,255,.11),0 0 25px rgba(0,217,255,.09);
 backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px)}
.ais-glass-scroll {max-height:375px;overflow:auto;scrollbar-color:#247b95 #0b2031;scrollbar-width:thin}
.ais-glass-table {border-collapse:separate;border-spacing:0;width:100%;min-width:960px;
 font:500 12px Inter,Arial,sans-serif;color:#eaf8ff}
.ais-glass-table thead th {position:sticky;top:0;z-index:2;text-align:left;
 background:#123b52;color:#d9f7ff;font-weight:800;font-size:11px;letter-spacing:.25px;
 padding:13px 12px;border-bottom:1px solid #36a5c4;white-space:nowrap}
.ais-glass-table tbody td {padding:10px 12px;border-bottom:1px solid rgba(101,174,199,.16);
 white-space:nowrap;color:#e5f3fc}
.ais-glass-table tbody tr:nth-child(even) {background:rgba(23,76,101,.24)}
.ais-glass-table tbody tr:hover {background:rgba(0,217,255,.14)}
.ais-glass-table tbody td:nth-child(2) {font-weight:700;color:#fff}
.ais-glass-table tbody td:nth-child(3) {color:#c6ff00;font-variant-numeric:tabular-nums}
.ais-glass-table tbody td:nth-child(5),.ais-glass-table tbody td:nth-child(6),
.ais-glass-table tbody td:nth-child(7) {font-variant-numeric:tabular-nums}
.ais-glass-meta {display:flex;flex-wrap:wrap;gap:10px;margin:12px 0;color:#e6f8ff;font-size:12px}
.ais-glass-chip {background:rgba(10,50,68,.8);border:1px solid rgba(60,179,210,.5);
 padding:7px 12px;border-radius:8px;color:#e7f7ff}
.ais-glass-chip strong {color:#c6ff00;font-weight:800}
.ais-glass-empty {padding:24px;color:#c3deed;text-align:center}
</style>""", unsafe_allow_html=True)

def parse_time(value):
    try:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def load_data():
    try:
        raw = json.loads(DATA_FILE.read_text(encoding='utf-8'))
        records = raw.get('vessels', []) if isinstance(raw, dict) else raw
        updated = raw.get('updated_at') if isinstance(raw, dict) else None
        if not isinstance(records, list):
            records = []
    except (OSError, ValueError, TypeError):
        records, updated = [], None
    df = pd.DataFrame(records)
    for key in ['name','mmsi','source','latitude','longitude','speed_knots','course','last_seen']:
        if key not in df.columns:
            df[key] = None
    if df.empty:
        return df, updated
    for key in ['latitude','longitude','speed_knots','course']:
        df[key] = pd.to_numeric(df[key], errors='coerce')
    df = df.dropna(subset=['latitude','longitude']).copy()
    df = df[df.latitude.between(-90,90) & df.longitude.between(-180,180)].copy()
    now = datetime.now(timezone.utc)
    df['observed'] = df['last_seen'].map(parse_time)
    df = df[df['observed'].map(lambda x: x is not None and 0 <= (now-x).total_seconds() <= 1800)].copy()
    df['name'] = df['name'].fillna('Unknown').astype(str)
    df['mmsi'] = df['mmsi'].fillna('Unknown').astype(str)
    df['source'] = df['source'].fillna('unknown').astype(str)
    df['movement'] = df['speed_knots'].apply(lambda x: 'Moving' if pd.notna(x) and x > 5 else ('Slow' if pd.notna(x) and x > .5 else 'Stationary / Unknown'))
    return df, updated


def classify_region(lat, lon):
    """Approximate monitoring boxes, not official maritime boundaries."""
    if 0.7 <= lat <= 2.5 and 103.1 <= lon <= 105.0:
        return "Johor / Singapore"
    if 5.0 <= lat <= 7.6 and 115.0 <= lon <= 119.8:
        return "Sabah"
    if 0.5 <= lat <= 5.0 and 109.0 <= lon <= 115.5:
        return "Sarawak"
    if 5.5 <= lat <= 6.8 and 101.8 <= lon <= 103.5:
        return "Kelantan"
    if 4.3 <= lat <= 5.8 and 102.5 <= lon <= 104.0:
        return "Terengganu"
    if 3.2 <= lat <= 4.5 and 102.5 <= lon <= 104.3:
        return "Pahang / Kuantan"
    if 2.5 <= lat <= 3.8 and 100.5 <= lon <= 101.8:
        return "Port Klang / Selangor"
    if 4.8 <= lat <= 6.0 and 99.7 <= lon <= 100.9:
        return "Penang"
    return "Other / Unclassified"


# Geographic labels are approximate monitoring-area context, not state boundaries.
REGION_STATE_HINTS = {
    'Johor / Singapore': 'Johor / Singapore area',
    'Port Klang / Selangor': 'Selangor area',
    'Penang': 'Pulau Pinang area',
    'Kelantan': 'Kelantan area',
    'Terengganu': 'Terengganu area',
    'Pahang / Kuantan': 'Pahang area',
    'Sarawak': 'Sarawak area',
    'Sabah': 'Sabah area',
}


def vessel_state_hint(region):
    return REGION_STATE_HINTS.get(str(region), 'State not verified')


def record_position_history(df):
    """Persist real AIS observations; one record per MMSI and timestamp."""
    if df.empty:
        return
    with sqlite3.connect(HISTORY_DB, timeout=10) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS positions (
            mmsi TEXT NOT NULL, observed TEXT NOT NULL, name TEXT,
            latitude REAL NOT NULL, longitude REAL NOT NULL,
            region TEXT, source TEXT, speed_knots REAL,
            PRIMARY KEY (mmsi, observed))""")
        rows = []
        for _, r in df.iterrows():
            mmsi = str(r.get('mmsi', '')).strip()
            observed = r.get('observed')
            if not mmsi or mmsi.lower() in ('none', 'unknown') or observed is None:
                continue
            speed = r.get('speed_knots')
            rows.append((mmsi, observed.isoformat(), str(r.get('name','')),
                         float(r.latitude), float(r.longitude), str(r.region),
                         str(r.source), float(speed) if pd.notna(speed) else None))
        conn.executemany('INSERT OR IGNORE INTO positions VALUES (?,?,?,?,?,?,?,?)', rows)


def route_history():
    if not HISTORY_DB.exists():
        return pd.DataFrame()
    with sqlite3.connect(HISTORY_DB, timeout=10) as conn:
        return pd.read_sql_query('SELECT * FROM positions ORDER BY observed ASC', conn)



def plotting_history_page_section():
    """Show AIS positions actually recorded by this dashboard, including older observations."""
    st.markdown('<div class="panel-title">AIS Position History</div>', unsafe_allow_html=True)
    st.caption('Stored AIS observations from this dashboard, not fabricated routes. Historical rows remain available after the live 30-minute window expires.')
    try:
        history = route_history()
    except (sqlite3.Error, OSError) as exc:
        st.warning(f'Cannot read saved plotting history: {exc}')
        return
    if history.empty:
        st.info('No plotting history recorded yet. Refresh the AIS receiver and combiner, then leave this dashboard running to collect genuine observations.')
        return
    history = history.copy()
    history['observed_utc'] = pd.to_datetime(history['observed'], utc=True, errors='coerce')
    history = history.dropna(subset=['observed_utc']).sort_values('observed_utc', ascending=False)
    if history.empty:
        st.info('No valid timestamped observations have been recorded.')
        return
    history['region'] = history.apply(lambda r: classify_region(float(r.latitude), float(r.longitude)), axis=1)
    history['State / Area (approx.)'] = history['region'].map(vessel_state_hint)
    history['observed_myt'] = history['observed_utc'].dt.tz_convert('Asia/Kuala_Lumpur').dt.strftime('%Y-%m-%d %H:%M:%S')
    col1, col2, col3 = st.columns([1.3, 1, 1])
    with col1:
        vessel_query = st.text_input('Search recorded vessel / MMSI', key='history_search')
    with col2:
        area = st.selectbox('History region', ['All regions'] + MONITORED_AREAS + ['Other / Unclassified'], key='history_region')
    with col3:
        days = st.selectbox('History period', ['All recorded', 'Last 24 hours', 'Last 7 days', 'Last 30 days'], key='history_period')
    selected = history
    if vessel_query.strip():
        query = vessel_query.strip()
        selected = selected[selected['name'].fillna('').astype(str).str.contains(query, case=False, regex=False) |
                            selected['mmsi'].fillna('').astype(str).str.contains(query, case=False, regex=False)]
    if area != 'All regions':
        selected = selected[selected.region == area]
    if days != 'All recorded':
        hours = {'Last 24 hours':24, 'Last 7 days':168, 'Last 30 days':720}[days]
        cutoff = pd.Timestamp.now(tz='UTC') - pd.Timedelta(hours=hours)
        selected = selected[selected.observed_utc >= cutoff]
    c1, c2 = st.columns(2)
    c1.metric('Recorded Plots', len(selected))
    c2.metric('Unique Vessels in History', selected.mmsi.nunique())
    columns = ['observed_myt', 'name', 'mmsi', 'region', 'latitude', 'longitude', 'speed_knots', 'source']
    table = selected[columns].rename(columns={'observed_myt':'Plotted (Malaysia time)', 'name':'Vessel', 'mmsi':'MMSI',
          'region':'Region', 'latitude':'Latitude', 'longitude':'Longitude', 'speed_knots':'Speed (knots)', 'source':'AIS Source'})
    st.dataframe(table, width='stretch', hide_index=True, height=280)
    st.download_button('Download plotting history CSV', table.to_csv(index=False),
                       file_name='sea_sentinel_plotting_history.csv', mime='text/csv', key='download_plotting_history')
    st.caption('Each row represents a unique vessel MMSI and observation timestamp. History collection occurs when this dashboard reads refreshed AIS snapshots.')


def live_radar_view(df, region):
    """Real vessel bearings and distances from the selected monitoring centre."""
    lat0, lon0, _ = REGIONS[region]
    if not df.empty and region in ('Malaysia', 'All Malaysian States', 'Peninsular'):
        # Nationwide monitoring has no useful single 50 NM centre: use the
        # median of actual fresh positions, without inventing vessel data.
        lat0 = float(df['latitude'].median())
        lon0 = float(df['longitude'].median())
    if df.empty:
        st.info('No fresh AIS positions for radar plotting.')
        return
    def polar_position(lat, lon):
        a1, a2 = math.radians(lat0), math.radians(float(lat))
        dlat = a2 - a1
        dlon = math.radians(float(lon) - lon0)
        h = math.sin(dlat/2)**2 + math.cos(a1)*math.cos(a2)*math.sin(dlon/2)**2
        dist_nm = 3440.065 * 2 * math.asin(min(1, math.sqrt(max(0,h))))
        y = math.sin(dlon)*math.cos(a2)
        x = math.cos(a1)*math.sin(a2)-math.sin(a1)*math.cos(a2)*math.cos(dlon)
        return (math.degrees(math.atan2(y,x))+360)%360, dist_nm
    plotted = df.copy()
    bearings, distances = zip(*(polar_position(r.latitude, r.longitude) for _,r in plotted.iterrows()))
    plotted['bearing'] = bearings
    plotted['distance_nm'] = distances
    # Expand the geographic display range for nationwide/multi-region views.
    # Local views retain a 50 NM minimum but expand if actual vessels lie farther.
    max_distance = float(plotted['distance_nm'].max())
    display_range = max(50, math.ceil(max_distance / 25) * 25)
    within = plotted[plotted.distance_nm <= display_range].copy()
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(r=within.distance_nm, theta=within.bearing,
        mode='markers', marker=dict(size=8, color='#C6FF00', opacity=.9,
        line=dict(color='#00D9FF',width=.5)),
        customdata=within[['name','mmsi','region']].astype(str).values.tolist(),
        hovertemplate='<b>%{customdata[0]}</b><br>MMSI: %{customdata[1]}<br>Region: %{customdata[2]}<br>Range: %{r:.1f} NM<br>Bearing: %{theta:.0f}°<extra></extra>'))
    fig.update_layout(height=410,margin=dict(l=30,r=30,t=18,b=22),showlegend=False,
        paper_bgcolor='#06172A',font=dict(color='#D5E9F2'),
        polar=dict(bgcolor='#062337',angularaxis=dict(direction='clockwise',rotation=90,
            tickmode='array',tickvals=list(range(0,360,45)),gridcolor='#147F6E',linecolor='#19A990'),
            radialaxis=dict(range=[0,display_range],tickvals=[display_range*i/5 for i in range(1,6)],
                ticksuffix=' NM',gridcolor='#147F6E',linecolor='#19A990',tickfont=dict(size=9))))
    st.plotly_chart(fig,width='stretch',key='live_radar_plot')
    st.caption(f'{len(within)} fresh AIS positions displayed · range {display_range:.0f} NM · centre {lat0:.3f}°, {lon0:.3f}°. Geographic AIS polar plot, not a physical radar feed.')


def vessel_routes_page(df):
    st.markdown('<div class="panel-title">Vessel Route Explorer</div>', unsafe_allow_html=True)
    st.caption('Routes connect actual stored observations. History begins when this dashboard starts collecting; a single position cannot establish a route.')
    history = route_history()
    if history.empty:
        st.info('No recorded AIS position history yet. Keep the dashboard running while receivers and the combiner refresh data.')
        return
    counts = history.groupby('mmsi').size()
    eligible = counts[counts >= 2].index.tolist()
    if not eligible:
        st.info('A vessel needs at least two recorded positions to display a route.')
        return
    # Build the selector without repeated full-data scans for each vessel.
    latest = history.sort_values('observed').drop_duplicates('mmsi', keep='last').set_index('mmsi')
    options = {m: f"{latest.loc[m, 'name']} · {m} ({int(counts[m])} positions)" for m in eligible}
    selected = st.selectbox('Choose a recorded vessel', eligible, format_func=lambda m: options[m], key='route_explorer_vessel')
    points = history[history.mmsi == selected].sort_values('observed').copy()
    coords = points[['latitude', 'longitude']].astype(float).values.tolist()
    first, last = points.iloc[0], points.iloc[-1]
    observed = pd.to_datetime(points['observed'], utc=True, errors='coerce')
    duration = (observed.max() - observed.min()).total_seconds() / 60 if observed.notna().any() else 0
    st.markdown('<div class="route-subheading">RECORDED ROUTE · AIS EVIDENCE</div>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4, gap='small')
    c1.metric('Recorded Positions', len(points))
    c2.metric('Track Duration', f'{duration:.0f} min')
    c3.metric('Latest Speed', f"{float(last.speed_knots):.1f} kn" if pd.notna(last.speed_knots) else 'N/A')
    c4.metric('AIS Source', str(last.source).upper())
    left, right = st.columns([2.1, 1], gap='medium')
    with left:
        st.markdown('<div class="route-subheading">VESSEL TRACK MAP</div>', unsafe_allow_html=True)
        m = folium.Map(location=[float(first.latitude), float(first.longitude)], zoom_start=9,
                       tiles=None, control_scale=True, prefer_canvas=True)
        folium.TileLayer('OpenStreetMap', name='Maritime map').add_to(m)
        m.get_root().header.add_child(folium.Element('''<style>
        .leaflet-tile-pane {filter: invert(1) hue-rotate(180deg) brightness(.78) contrast(1.13) saturate(.8);}
        .leaflet-container {background:#071b2d !important;}
        </style>'''))

        folium.LayerControl(collapsed=True).add_to(m)
        for index, (_, obs) in enumerate(points.iterrows(), start=1):
            if pd.isna(obs.latitude) or pd.isna(obs.longitude):
                continue
            info = (f'<b>{escape(str(obs["name"]))}</b><br>'
                    f'Observation #{index}<br>'
                    f'Time (UTC): {escape(str(obs["observed"]))}<br>'
                    f'Speed: {escape(str(obs["speed_knots"]))} kn<br>'
                    f'Source: {escape(str(obs["source"]))}')
            folium.CircleMarker([float(obs.latitude), float(obs.longitude)], radius=4,
                color='#00D9FF',fill=True,fill_color='#00D9FF',fill_opacity=.85,
                popup=folium.Popup(info,max_width=280)).add_to(m)
        folium.PolyLine(coords, color='#00D9FF', weight=4, opacity=.95,
                        tooltip='Actual recorded AIS positions').add_to(m)
        folium.CircleMarker(coords[0], radius=7, color='#C6FF00', fill=True,
                            fill_color='#C6FF00', fill_opacity=1,
                            tooltip='First recorded observation').add_to(m)
        folium.CircleMarker(coords[-1], radius=7, color='#FF4DB8', fill=True,
                            fill_color='#FF4DB8', fill_opacity=1,
                            tooltip='Latest recorded observation').add_to(m)
        # Fit to real coordinates, with a minimum span for nearly stationary ships.
        latitudes = [pt[0] for pt in coords]
        longitudes = [pt[1] for pt in coords]
        center_lat = (min(latitudes) + max(latitudes)) / 2
        center_lon = (min(longitudes) + max(longitudes)) / 2
        pad_lat = max((max(latitudes) - min(latitudes)) * .4, .009)
        pad_lon = max((max(longitudes) - min(longitudes)) * .4, .009)
        m.fit_bounds([[min(latitudes)-pad_lat, min(longitudes)-pad_lon],
                      [max(latitudes)+pad_lat, max(longitudes)+pad_lon]])
        components.html(m.get_root().render(), height=370, scrolling=False)
        st.caption('Same map styling as Live AIS · Lime = first position · Pink = latest · Cyan = recorded AIS track. Tracks connect recorded observations only.')
    with right:
        st.markdown('<div class="route-subheading">VESSEL DETAILS</div>', unsafe_allow_html=True)
        name = escape(str(last['name']))
        mmsi = escape(str(selected))
        start_utc = escape(str(first['observed'])[:19].replace('T', ' '))
        end_utc = escape(str(last['observed'])[:19].replace('T', ' '))
        st.markdown(f"""<div class='route-details'>
            <div class='route-vessel'>{name}</div><div class='route-id'>MMSI {mmsi}</div>
            <div class='route-detail-label'>REGION</div><div>{escape(str(last['region']))}</div>
            <div class='route-detail-label'>AIS SOURCE</div><div>{escape(str(last['source']))}</div>
            <div class='route-detail-label'>RECORDED POSITIONS</div><div>{len(points)}</div>
            <div class='route-detail-label'>FIRST OBSERVATION (UTC)</div><div>{start_utc}</div>
            <div class='route-detail-label'>LATEST OBSERVATION (UTC)</div><div>{end_utc}</div>
            <div class='route-detail-label'>START COORDINATES</div><div>{float(first.latitude):.5f}°, {float(first.longitude):.5f}°</div>
            <div class='route-detail-label'>LATEST COORDINATES</div><div>{float(last.latitude):.5f}°, {float(last.longitude):.5f}°</div>
            <div class='route-detail-label'>TRACK STATUS</div><div>Recorded observations only · No inferred path</div>
        </div>""", unsafe_allow_html=True)
    # One consolidated AIS history table for ALL recorded vessels.
    # The route selector above only controls the route map and details card.
    st.markdown('<div class="panel-title">All Tracked Vessels & Position History</div>', unsafe_allow_html=True)
    st.caption('All stored AIS observations, including vessels outside the current live freshness window. The route selection does not filter this table.')
    history_table = history[['observed','name','mmsi','region','latitude','longitude','speed_knots','source']].copy()
    history_table['observed'] = pd.to_datetime(history_table['observed'], utc=True, errors='coerce')
    history_table = history_table.dropna(subset=['observed']).sort_values('observed', ascending=False)
    history_table['observed'] = history_table['observed'].dt.strftime('%Y-%m-%d %H:%M:%S UTC')
    search_all = st.text_input('Search all recorded vessels by name or MMSI', key='all_vessel_history_search',
                               placeholder='Vessel name or MMSI')
    if search_all.strip():
        q = search_all.strip()
        history_table = history_table[
            history_table['name'].fillna('').astype(str).str.contains(q, case=False, regex=False) |
            history_table['mmsi'].fillna('').astype(str).str.contains(q, case=False, regex=False)
        ]
    history_table = history_table.rename(columns={
        'observed':'Date & Time (UTC)', 'name':'Vessel Name', 'mmsi':'MMSI',
        'region':'Region', 'latitude':'Latitude', 'longitude':'Longitude',
        'speed_knots':'Speed (kn)', 'source':'AIS Source'
    })
    # Render a genuine dark glass table; Streamlit's native dataframe grid can
    # otherwise force a light background and unreadable low-contrast headers.
    from html import escape as html_escape
    display_columns = list(history_table.columns)
    def _history_cell(value, column):
        if pd.isna(value):
            return '—'
        if column in ('Latitude', 'Longitude'):
            try:
                return f'{float(value):.5f}'
            except (TypeError, ValueError):
                pass
        if column == 'Speed (kn)':
            try:
                return f'{float(value):.1f}'
            except (TypeError, ValueError):
                pass
        return str(value)
    header_html = ''.join(f'<th scope="col">{html_escape(col)}</th>' for col in display_columns)
    rows_html = ''.join(
        '<tr>' + ''.join(
            f'<td>{html_escape(_history_cell(row[col], col))}</td>' for col in display_columns
        ) + '</tr>'
        for _, row in history_table.iterrows()
    )
    if not rows_html:
        rows_html = f'<tr><td colspan="{len(display_columns)}" class="ais-glass-empty">No recorded positions match your search.</td></tr>'
    st.markdown(
        '<div class="ais-glass-meta">'
        f'<span class="ais-glass-chip"><strong>{len(history_table):,}</strong> recorded positions</span>'
        f'<span class="ais-glass-chip"><strong>{history_table["MMSI"].nunique():,}</strong> unique vessels</span>'
        '</div>'
        '<div class="ais-glass-frame"><div class="ais-glass-scroll">'
        f'<table class="ais-glass-table"><thead><tr>{header_html}</tr></thead>'
        f'<tbody>{rows_html}</tbody></table>'
        '</div></div>', unsafe_allow_html=True
    )
    st.download_button('Download all vessel position history CSV',
                       history_table.to_csv(index=False),
                       file_name='sea_sentinel_all_vessel_positions.csv',
                       mime='text/csv', key='all_vessel_history_export')


def make_map(df, region):
    """Match the Threat Assessment dark OpenStreetMap, preserve region-coloured AIS dots."""
    lat, lon, zoom = REGIONS[region]
    m = folium.Map(location=[lat, lon], zoom_start=zoom, tiles=None,
                   control_scale=True, zoom_control=True, prefer_canvas=True)
    folium.TileLayer('OpenStreetMap', name='OpenStreetMap (dark display)').add_to(m)
    # Identical map treatment to the working Threat Assessment map.
    # The filter affects only raster tiles; vessel marker colours are untouched.
    m.get_root().header.add_child(folium.Element('''<style>
    .leaflet-tile-pane {filter: invert(1) hue-rotate(180deg) brightness(.78) contrast(1.13) saturate(.8);}
    .leaflet-container {background:#071b2d !important;}
    </style>'''))
    plot_state_markers(m, df)
    folium.LayerControl(collapsed=True).add_to(m)
    for _, r in df.iterrows():
        color = REGION_COLORS.get(str(r.get('region', 'Other')), '#FF4242')
        info = (f"<b>{escape(str(r.get('name','Unknown')))}</b>"
                f"<br>MMSI: {escape(str(r.get('mmsi','')))}"
                f"<br>Region: {escape(str(r.get('region','Other')))}"
                f"<br>Source: {escape(str(r.get('source','')))}"
                f"<br>Speed: {escape(str(r.get('speed_knots','')))} kn"
                f"<br>Observed: {escape(str(r.get('last_seen','')))}")
        folium.CircleMarker(location=[float(r.latitude), float(r.longitude)],
            radius=4, color='#FFFFFF', weight=1, fill=True,
            fill_color=color, fill_opacity=.95,
            tooltip=escape(str(r.get('name','Unknown'))),
            popup=folium.Popup(info, max_width=290)).add_to(m)
    components.html(m.get_root().render(), height=465, scrolling=False)
    st.caption('State labels appear only for monitored areas with plotted fresh AIS vessels. Circular dots are real AIS positions; region boxes are approximate.')


def chart_style(fig, height=270):
    fig.update_layout(paper_bgcolor='#06172A', plot_bgcolor='#06172A', font_color='white', margin=dict(l=10,r=10,t=20,b=10), height=height, legend=dict(orientation='h',y=-.12))
    return fig


# Region colours are shared by the map and bar chart.
REGION_COLORS = {
    'Johor / Singapore': '#C6FF00',       # Neon lime
    'Port Klang / Selangor': '#FFE600',   # Yellow
    'Penang': '#FF9500',                  # Orange
    'Kelantan': '#FF4040',                # Neon red
    'Terengganu': '#00D9FF',              # Cyan
    'Pahang / Kuantan': '#A855F7',        # Purple
    'Sarawak': '#FF4DB8',                 # Pink
    'Sabah': '#00E5A0',                   # Mint green
    'Other / Unclassified': '#B5BDC9',                   # Unclassified / outside monitored areas
}


def source_chart(df):
    counts = df.source.value_counts() if not df.empty else pd.Series(dtype=int)
    if counts.empty:
        st.info('No recent AIS positions available.')
        return
    source_colors = {'aisstream':'#00D9FF', 'openwaters':'#C6FF00'}
    labels = [str(source) for source in counts.index]
    fig = go.Figure(go.Pie(
        labels=labels, values=counts.values, hole=0.65,
        marker=dict(colors=[source_colors.get(source.lower(), '#00D9FF') for source in labels]),
        textinfo='percent', textfont=dict(color='#FFFFFF', size=13),
        hovertemplate='%{label}: %{value} vessels (%{percent})<extra></extra>'
    ))
    fig.add_annotation(text=str(len(df)), x=0.5, y=0.5, showarrow=False,
                       font=dict(size=26, color='#FFFFFF', family='Arial Black'))
    fig.update_layout(
        showlegend=True,
        legend=dict(orientation='h', x=0.5, xanchor='center', y=-0.08,
                    font=dict(color='#FFFFFF', size=13, family='Arial'),
                    bgcolor='rgba(0,0,0,0)'),
        margin=dict(l=8, r=8, t=10, b=48)
    )
    st.plotly_chart(chart_style(fig, 220), width='stretch')


def region_chart(df):
    counts = df.region.value_counts() if not df.empty else pd.Series(dtype=int)
    counts = counts.reindex(MONITORED_AREAS, fill_value=0)
    fig = go.Figure(go.Bar(
        x=counts.values, y=counts.index, orientation='h',
        marker=dict(color=[REGION_COLORS[region] for region in counts.index]),
        text=[str(int(v)) for v in counts.values],
        textposition='outside',
        textfont=dict(color='#FFFFFF', size=11, family='Arial Black'),
        cliponaxis=False,
        hovertemplate='%{y}: %{x} vessels<extra></extra>'
    ))
    fig.update_layout(
        yaxis=dict(autorange='reversed', tickfont=dict(color='#FFFFFF', size=10, family='Arial')),
        xaxis=dict(gridcolor='#1A3850', rangemode='tozero',
                   range=[0, max(4, float(counts.max()) * 1.25)]),
        showlegend=False, margin=dict(l=12, r=38, t=15, b=18),
        bargap=0.32
    )
    st.plotly_chart(chart_style(fig, 230), width='stretch')



# AIS-based maritime risk screening. Scores are preliminary and not validated
# probabilities or formal Safety Management System risk assessments.
ASSESSMENT_DB = BASE / 'ais_risk_assessments.sqlite3'


def _historical_course_changes():
    'Optional route-change evidence from real, recorded positions.'
    # Existing history stores coordinates but not heading. Deriving heading from
    # just two positions can be unreliable, so no course-change flags are inferred.
    return {}


def assess_vessels(df, advisory_kn=15, high_kn=25):
    columns = ['mmsi','name','region','source','speed_knots','hazard',
               'likelihood','consequence','risk_score','level','reason',
               'recommended_control','observed','evidence_status']
    results=[]
    if df.empty:
        return pd.DataFrame(columns=columns)
    for _,r in df.iterrows():
        speed=r.get('speed_knots')
        if pd.isna(speed):
            continue  # unknown speed is not evidence of safe movement
        speed=float(speed)
        if not (0 <= speed <= 100):
            continue  # exclude invalid / implausible sensor readings
        if speed >= high_kn:
            hazard='Elevated reported vessel speed'
            likelihood=3  # provisional screening indicator, NOT event probability
            consequence=3 # assumed scenario impact; not vessel-specific
            reason=f'Reported speed {speed:.1f} kn meets high-speed screening threshold ({high_kn} kn).'
            control='Verify AIS speed and vessel type; review traffic density and navigational context; continue monitoring.'
        elif speed >= advisory_kn:
            hazard='Speed warrants contextual review'
            likelihood=2
            consequence=2
            reason=f'Reported speed {speed:.1f} kn meets advisory threshold ({advisory_kn} kn).'
            control='Check vessel type, local speed guidance and traffic conditions; monitor for changes.'
        else:
            continue
        score=likelihood*consequence
        level='Critical' if score>=20 else 'High' if score>=10 else 'Moderate' if score>=5 else 'Low'
        observed=r.get('observed')
        results.append(dict(mmsi=str(r.get('mmsi','Unknown')),
            name=str(r.get('name','Unknown')),region=str(r.get('region','Other')),
            source=str(r.get('source','unknown')),speed_knots=speed,hazard=hazard,
            likelihood=likelihood,consequence=consequence,risk_score=score,
            level=level,reason=reason,recommended_control=control,
            observed=observed.isoformat() if hasattr(observed,'isoformat') else str(observed),
            evidence_status='AIS speed only; context not verified'))
    return pd.DataFrame(results,columns=columns)


def save_assessments(flags):
    'Document preliminary screening without creating an Event History page.'
    if flags.empty:
        return
    with sqlite3.connect(ASSESSMENT_DB,timeout=10) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS assessments (
            mmsi TEXT NOT NULL, observed TEXT NOT NULL, hazard TEXT NOT NULL,
            name TEXT, region TEXT, source TEXT, speed_knots REAL,
            likelihood INTEGER, consequence INTEGER, risk_score INTEGER,
            level TEXT, reason TEXT, recommended_control TEXT,
            evidence_status TEXT, review_status TEXT DEFAULT 'Pending review',
            PRIMARY KEY(mmsi,observed,hazard))''')
        rows=[]
        for _,r in flags.iterrows():
            rows.append((r.mmsi,r.observed,r.hazard,r['name'],r.region,r.source,
                float(r.speed_knots),int(r.likelihood),int(r.consequence),
                int(r.risk_score),r.level,r.reason,r.recommended_control,r.evidence_status))
        conn.executemany('''INSERT OR IGNORE INTO assessments
            (mmsi,observed,hazard,name,region,source,speed_knots,likelihood,
            consequence,risk_score,level,reason,recommended_control,evidence_status)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',rows)



RISK_PALETTE = {'Low':'#22e79a','Moderate':'#ffe600','High':'#ff971f','Critical':'#ff4757'}
RISK_LEVELS = ['Low','Moderate','High','Critical']

def _risk_map(df, flags):
    """Actual AIS locations only; flags are provisional speed screening."""
    center = [3.8, 108.0]
    zoom = 5
    if not df.empty:
        center = [float(df.latitude.median()), float(df.longitude.median())]
        zoom = 6
    m = folium.Map(location=center, zoom_start=zoom, tiles=None,
                   control_scale=True, prefer_canvas=True)
    folium.TileLayer('OpenStreetMap', name='OpenStreetMap (dark display)').add_to(m)
    # Apply dark styling to base-map tiles only; markers retain their risk colours.
    m.get_root().header.add_child(folium.Element('''<style>
    .leaflet-tile-pane {filter: invert(1) hue-rotate(180deg) brightness(.78) contrast(1.13) saturate(.8);}
    .leaflet-container {background:#071b2d !important;}
    </style>'''))
    flagged = set(flags.mmsi.astype(str)) if not flags.empty else set()
    levels = dict(zip(flags.mmsi.astype(str), flags.level)) if not flags.empty else {}
    plot_state_markers(m, df)
    folium.LayerControl(collapsed=True).add_to(m)
    for _, vessel in df.iterrows():
        mmsi = str(vessel.get('mmsi','Unknown'))
        level = levels.get(mmsi, 'Low')
        # Green means no speed-screening flag, not proof of safety.
        color = RISK_PALETTE[level]
        title = escape(str(vessel.get('name','Unknown')))
        details = (f"<b>{title}</b><br>MMSI: {escape(mmsi)}"
                   f"<br>Screening: {escape(level if mmsi in flagged else 'No speed flag / not fully assessed')}"
                   f"<br>Speed: {escape(str(vessel.get('speed_knots','Unknown')))} kn"
                   f"<br>Region: {escape(str(vessel.get('region','Other')))}")
        folium.CircleMarker(
            location=[float(vessel.latitude),float(vessel.longitude)],
            radius=5 if mmsi in flagged else 3.5, color='white',
            weight=1, fill=True, fill_color=color, fill_opacity=.94,
            tooltip=title, popup=folium.Popup(details, max_width=300)
        ).add_to(m)
    components.html(m.get_root().render(), height=365, scrolling=False)

def _risk_donut(df, flags):
    counts = {k:0 for k in RISK_LEVELS}
    for key in RISK_LEVELS:
        counts[key] = int((flags.level == key).sum()) if not flags.empty else 0
    no_flag = max(0,len(df)-len(flags))
    labels = ['No speed flag','Moderate','High','Critical','Low']
    values = [no_flag,counts['Moderate'],counts['High'],counts['Critical'],counts['Low']]
    colors = ['#1ca78c',RISK_PALETTE['Moderate'],RISK_PALETTE['High'],
              RISK_PALETTE['Critical'],RISK_PALETTE['Low']]
    if sum(values)==0:
        labels,values,colors=['No fresh AIS data'],[1],['#30465a']
    fig=go.Figure(go.Pie(labels=labels,values=values,hole=.7,
        marker=dict(colors=colors,line=dict(color='#06172A',width=2)),
        sort=False,textinfo='none'))
    fig.update_layout(
        height=340,margin=dict(l=5,r=5,t=12,b=48),
        paper_bgcolor='#06172A',plot_bgcolor='#06172A',
        font=dict(color='#e8f5ff',size=12),
        legend=dict(orientation='h',y=-.13,x=.5,xanchor='center',font=dict(size=12,color='#eaf5ff'),bgcolor='rgba(0,0,0,0)'),
        annotations=[dict(text=f'<b>{len(df)}</b><br>Vessels',x=.5,y=.5,
                          font=dict(size=21,color='#ffffff'),showarrow=False)])
    st.plotly_chart(fig, width='stretch',key='threat_risk_donut')

def _matrix():
    matrix = [[l*c for c in range(1,6)] for l in range(5,0,-1)]
    fig=go.Figure()
    for row_index,l in enumerate(range(5,0,-1)):
        for c in range(1,6):
            score=l*c
            color=('#b72a37' if score>=20 else '#d66a1d' if score>=10
                   else '#a88a16' if score>=5 else '#166c51')
            fig.add_shape(type='rect',x0=c-.48,x1=c+.48,
                          y0=l-.48,y1=l+.48,
                          line=dict(color='#09263d',width=2),fillcolor=color)
            fig.add_annotation(x=c,y=l,text=str(score),showarrow=False,
                               font=dict(color='white',size=15))
    fig.update_xaxes(range=[.5,5.5],tickvals=[1,2,3,4,5],
                     title='Consequence (1–5)',showgrid=False,zeroline=False)
    fig.update_yaxes(range=[.5,5.5],tickvals=[1,2,3,4,5],
                     title='Likelihood (1–5)',showgrid=False,zeroline=False)
    fig.update_layout(height=340,margin=dict(l=35,r=8,t=10,b=38),
                      paper_bgcolor='#06172A',plot_bgcolor='#06172A',
                      font=dict(color='#e6f5ff'),showlegend=False)
    st.plotly_chart(fig,width='stretch',key='threat_risk_matrix')

def threat_assessment_page(df, flags, advisory_kn, high_kn):
    """Compact maritime risk dashboard using real, fresh AIS screening evidence."""
    st.markdown('''<style>
    .threat-hero{border:1px solid #087b9b;border-radius:13px;padding:17px 22px;
       background:linear-gradient(105deg,#061c31 10%,#0a3550 75%,#071c31);margin-bottom:12px}
    .threat-hero h2{font-size:31px;font-weight:800;margin:0;letter-spacing:1px;color:#fff}
    .threat-hero p{color:#c0d8e6;font-size:13px;margin:3px 0 0}
    .threat-head{background:linear-gradient(110deg,#092a42,#05182a);border:1px solid #0c8ca9;
       border-radius:9px;padding:9px 12px;color:#e9fbff;font-size:15px;font-weight:800;margin:7px 0 7px}
    .threat-head span{color:#00d9ff;margin-right:8px}
    .threat-kpi{background:linear-gradient(145deg,#0a314b,#041726);border:1px solid #00a5c7;
       border-radius:11px;min-height:103px;padding:11px 10px;box-shadow:inset 0 0 18px #00d9ff12}
    .threat-kpi .name{font-size:12px;color:#d8ecf6;min-height:29px;line-height:1.2}
    .threat-kpi .number{font-size:30px;font-weight:850;color:#c6ff00;line-height:1.2}
    .threat-kpi .hint{font-size:10px;color:#90b6c9;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .threat-alert{border:1px solid #20617b;border-left:4px solid #ffe600;background:#0a2336;
       border-radius:8px;padding:9px 11px;margin-bottom:7px;color:#e9f7ff;font-size:12px}
    .threat-alert strong{font-size:13px;color:#fff}
    .threat-step{background:linear-gradient(145deg,#0a3049,#06192b);border:1px solid #1087aa;
       border-radius:10px;padding:11px;min-height:135px;color:#d3e7f2}
    .threat-step .num{color:#00d9ff;font-size:21px;font-weight:850}
    .threat-step .label{color:#fff;font-size:13px;font-weight:800;margin:4px 0}
    .threat-step .desc{font-size:11px;line-height:1.4;color:#b5cfdf}
    div[data-testid="stDataFrame"]{border:1px solid #126a89;border-radius:9px}
    </style>''', unsafe_allow_html=True)

    st.markdown('''<div class="threat-hero"><h2>🛡 THREAT <span style="color:#c6ff00">ASSESSMENT</span></h2>
    <p>Advanced Maritime Anomaly Screening · Evidence-based AIS vessel monitoring</p></div>''',
    unsafe_allow_html=True)

    modules, advanced_events = advanced_screen(df, advisory_kn, high_kn)
    card_specs = [
        ('⚓', 'Vessels Assessed', str(len(df)), 'Fresh AIS observations'),
        ('◉', 'Speed Anomalies', str(modules['Speed anomalies']['count']), modules['Speed anomalies']['status']),
        ('⌁', 'Route Anomalies', str(modules['Route anomalies']['count']), modules['Route anomalies']['status']),
        ('⚠', 'Collision Alerts', str(modules['Collision screening']['count']), modules['Collision screening']['status']),
        ('◎', 'Geofence Checks', str(modules['Geofence checks']['count']) if 'verified' in modules['Geofence checks']['status'].lower() and 'unverified' not in modules['Geofence checks']['status'].lower() else '—', modules['Geofence checks']['status']),
        ('◉', 'AIS Reporting Gaps', 'N/A', modules['AIS reporting gaps']['status']),
    ]
    cols = st.columns(6, gap='small')
    for col, (symbol, label, value, hint) in zip(cols, card_specs):
        with col:
            st.markdown(f'<div class="threat-kpi"><div class="name">{escape(symbol)} &nbsp; {escape(label)}</div>'
                        f'<div class="number">{escape(value)}</div><div class="hint" title="{escape(str(hint),quote=True)}">{escape(str(hint))}</div></div>',
                        unsafe_allow_html=True)
    st.caption('Counts reflect current AIS screening, not confirmed incidents. A zero flag is not proof of safety; reporting-gap monitoring is not configured.')

    map_col, matrix_col, donut_col = st.columns([1.85, 1.15, 1.3], gap='small')
    with map_col:
        st.markdown('<div class="threat-head"><span>◉</span>Threat Monitoring Map (Risk View)</div>',unsafe_allow_html=True)
        _risk_map(df, flags)
        st.caption('Green = no speed flag / unassessed · Yellow = Moderate · Orange = High · Red = Critical. Actual AIS positions only.')
    with matrix_col:
        st.markdown('<div class="threat-head"><span>▦</span>Risk Matrix (5 × 5)</div>',unsafe_allow_html=True)
        _matrix()
    with donut_col:
        st.markdown('<div class="threat-head"><span>◉</span>Threat Level Distribution</div>',unsafe_allow_html=True)
        _risk_donut(df, flags)

    # Three aligned reference-style panels, populated from genuine screening data.
    st.markdown("""<style>
    .threat-three [data-testid="stVerticalBlock"]{gap:.35rem}
    .threat-panel-shell{background:linear-gradient(150deg,#061d31,#041321);border:1px solid #078aaa;
      border-radius:11px;padding:10px 11px;box-shadow:inset 0 0 18px #00d9ff0b}
    .threat-alert-row{display:flex;align-items:center;gap:9px;border:1px solid #215572;
      border-left:4px solid var(--risk-color,#ffe600);background:#0a2539;border-radius:8px;
      padding:9px;margin:7px 0;color:#e9f7ff;min-height:67px}
    .threat-alert-icon{font-size:22px;color:var(--risk-color,#ffe600);min-width:25px}
    .threat-alert-body{flex:1;min-width:0}
    .threat-alert-title{font-size:12px;font-weight:800;color:#fff;line-height:1.25}
    .threat-alert-meta{font-size:10px;color:#9bbdd1;overflow:hidden;text-overflow:ellipsis}
    .threat-pill{display:inline-block;background:var(--pill-bg,#375268);color:#fff;
      border-radius:20px;padding:3px 9px;font-size:11px;font-weight:800;white-space:nowrap}
    .threat-table{width:100%;border-collapse:collapse;color:#e9f8ff;font-size:11px;table-layout:fixed}
    .threat-table th{background:#0a3a50;color:#b8e3ef;text-align:left;font-size:10px;padding:9px 5px;
      border-bottom:1px solid #1187a5}
    .threat-table td{padding:9px 5px;border-bottom:1px solid #1a4257;overflow:hidden;
      text-overflow:ellipsis;white-space:nowrap}
    .threat-table tr:nth-child(even){background:#09253a}
    .threat-vessel-title{color:#fff;font-size:17px;font-weight:800;margin:3px 0 9px}
    .threat-details-grid{display:grid;grid-template-columns:92px minmax(0,1fr);gap:5px 8px;
      color:#e4f2fa;font-size:12px;line-height:1.35}
    .threat-details-grid .key{color:#86b9cf}
    .threat-control{border-top:1px solid #156c86;margin-top:12px;padding-top:9px;
      font-size:12px;color:#d2e7f2;line-height:1.5}
    .threat-empty{border:1px dashed #1b637b;border-radius:8px;padding:14px;
      font-size:12px;color:#a9cbdb;background:#081e31}
    </style>""",unsafe_allow_html=True)

    # Combine verified advanced-screening events and speed flags, avoiding duplicate alerts.
    alert_items = []
    if not advanced_events.empty:
        for _, event in advanced_events.iterrows():
            alert_items.append({
                'name': str(event.get('name','Unknown')),
                'mmsi': str(event.get('mmsi','Unknown')),
                'title': str(event.get('detection','Screening indicator')),
                'detail': str(event.get('detail','')),
                'observed': str(event.get('observed','')),
                'kind': 'advanced',
            })
    advanced_speed_ids = {x['mmsi'] for x in alert_items if 'speed' in x['title'].lower()}
    if not flags.empty:
        for _, f in flags.iterrows():
            if str(f.mmsi) not in advanced_speed_ids:
                alert_items.append({'name':str(f['name']), 'mmsi':str(f.mmsi),
                    'title':str(f.hazard), 'detail':str(f.reason),
                    'observed':str(f.observed), 'kind':'speed', 'level':str(f.level)})
    alert_items.sort(key=lambda x: x['observed'],reverse=True)

    # Rank vessels by evidence-backed indicators, then by provisional speed score.
    # No speed flag is not interpreted as an assessed Normal or Low risk.
    evidence_counts = {}
    evidence_names = {}
    for item in alert_items:
        ident=item['mmsi']
        evidence_counts[ident]=evidence_counts.get(ident,0)+1
        evidence_names.setdefault(ident,[])
        if item['title'] not in evidence_names[ident]:
            evidence_names[ident].append(item['title'])
    flag_by_id = {str(f.mmsi):f for _,f in flags.iterrows()} if not flags.empty else {}
    ranked_ids = sorted(evidence_counts, key=lambda m:(
        int(m in flag_by_id and flag_by_id[m].level=='Critical'),
        int(m in flag_by_id and flag_by_id[m].level=='High'),
        evidence_counts[m],
        int(flag_by_id[m].risk_score) if m in flag_by_id else 0),reverse=True)[:5]
    vessel_by_id = {str(v.mmsi):v for _,v in df.iterrows()} if not df.empty else {}

    alerts_col, vessels_col, details_col = st.columns([1.2,1.65,1.25],gap='small')
    with alerts_col:
        st.markdown('<div class="threat-head"><span>⚠</span>Recent Threat Alerts</div>',unsafe_allow_html=True)
        if alert_items:
            rows=[]
            for item in alert_items[:4]:
                title=item['title']
                is_collision='collision' in title.lower() or 'cpa' in title.lower()
                level=item.get('level','Review')
                color='#ff4658' if level in ('Critical','High') or is_collision else '#ffe600'
                badge=level if level in ('Critical','High','Moderate') else ('Potential Collision' if is_collision else ('Speed Anomaly' if 'speed' in title.lower() else 'Screening Indicator'))
                bg='#b92c3a' if color=='#ff4658' else '#967600'
                timestamp=item['observed'].replace('T',' ').replace('Z','')[-8:]
                rows.append(f'<div class="threat-alert-row" style="--risk-color:{color}">'
                    f'<div class="threat-alert-icon">⚠</div><div class="threat-alert-body">'
                    f'<div class="threat-alert-title">{escape(title)}</div>'
                    f'<div class="threat-alert-meta">{escape(item["name"])} · {escape(vessel_state_hint(vessel_by_id[item["mmsi"]]["region"]) if item["mmsi"] in vessel_by_id else "State not verified")} · {escape(item["mmsi"])}</div>'
                    f'<div class="threat-alert-meta" title="{escape(item["detail"],quote=True)}">{escape(item["detail"][:70])}</div>'
                    f'</div><div style="text-align:right"><div class="threat-alert-meta">{escape(timestamp)}</div>'
                    f'<span class="threat-pill" style="--pill-bg:{bg}">{escape(badge)}</span></div></div>')
            st.markdown('<div class="threat-panel-shell">'+''.join(rows)+'</div>',unsafe_allow_html=True)
        else:
            st.markdown('<div class="threat-panel-shell"><div class="threat-empty">No evidence-backed screening alerts in the current fresh AIS snapshot. Other hazards may remain unassessed.</div></div>',unsafe_allow_html=True)
        st.caption('Alerts are provisional screening observations, not confirmed incidents.')

    with vessels_col:
        st.markdown('<div class="threat-head"><span>⚓</span>Vessel Threat Assessment (Top 5)</div>',unsafe_allow_html=True)
        if ranked_ids:
            rows=[]
            for n,mmsi in enumerate(ranked_ids,1):
                v=vessel_by_id.get(mmsi)
                f=flag_by_id.get(mmsi)
                name=str(v['name']) if v is not None else next((a['name'] for a in alert_items if a['mmsi']==mmsi),'Unknown')
                speed=v.get('speed_knots') if v is not None else None
                speed_text=f'{float(speed):.1f}' if speed is not None and pd.notna(speed) else '—'
                level=str(f.level) if f is not None else 'Screened'
                colors={'Critical':('#ff4658','#951c2d'),'High':('#ff971f','#93490b'),
                    'Moderate':('#ffe600','#776100'),'Low':('#20e79a','#145d45'),'Review':('#00d9ff','#164b68')}
                fg,bg=colors.get(level,colors['Review'])
                triggered=', '.join(evidence_names.get(mmsi,[]))
                rows.append(f'<tr><td>{n}</td><td title="{escape(name,quote=True)}">{escape(name)}</td>'
                    f'<td>{escape(mmsi)}</td><td>{speed_text}</td>'
                    f'<td><span class="threat-pill" style="--pill-bg:{bg};color:{fg}">{escape(level)}</span></td>'
                    f'<td title="{escape(triggered,quote=True)}">{escape(triggered)}</td></tr>')
            table='<table class="threat-table"><colgroup><col style="width:6%"><col style="width:23%"><col style="width:20%"><col style="width:12%"><col style="width:16%"><col style="width:23%"></colgroup><thead><tr><th>No.</th><th>Vessel Name</th><th>MMSI</th><th>Speed (kn)</th><th>Risk</th><th>Triggered Rule(s)</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table>'
            st.markdown('<div class="threat-panel-shell">'+table+'</div>',unsafe_allow_html=True)
        else:
            st.markdown('<div class="threat-panel-shell"><div class="threat-empty">No vessels with evidence-backed screening flags in the latest snapshot.</div></div>',unsafe_allow_html=True)
        if not advanced_events.empty:
            st.download_button('⬇ Export screening evidence',advanced_events.to_csv(index=False),
                file_name='sea_sentinel_advanced_screening.csv',mime='text/csv',key='advanced_screening_csv')

    with details_col:
        st.markdown('<div class="threat-head"><span>⚓</span>Selected Vessel Details</div>',unsafe_allow_html=True)
        if df.empty:
            st.markdown('<div class="threat-panel-shell"><div class="threat-empty">No fresh AIS vessel available.</div></div>',unsafe_allow_html=True)
        else:
            ordered=df.copy()
            ordered['_priority']=ordered.mmsi.astype(str).map(lambda m: 1 if m in ranked_ids else 0)
            ordered=ordered.sort_values('_priority',ascending=False).reset_index(drop=True)
            choices=list(range(len(ordered)))
            selection=st.selectbox('Inspect vessel',choices,
                format_func=lambda i:f"{ordered.iloc[i]['name']} · {vessel_state_hint(ordered.iloc[i]['region'])} · {ordered.iloc[i]['mmsi']}",
                key='threat_vessel_choice',label_visibility='collapsed')
            vessel=ordered.iloc[selection]
            mmsi=str(vessel.mmsi)
            f=flag_by_id.get(mmsi)
            level=str(f.level) if f is not None else ('Screening Indicator' if mmsi in evidence_counts else 'Unassessed')
            speed=vessel.get('speed_knots')
            speed_text=f'{float(speed):.1f} kn' if pd.notna(speed) else 'Unavailable'
            course=vessel.get('course')
            course_text=f'{float(course):.1f}°' if pd.notna(course) else 'Unavailable'
            coords=f'{float(vessel.latitude):.4f}°, {float(vessel.longitude):.4f}°'
            controls=str(f.recommended_control) if f is not None else (
                'Verify screening evidence and vessel movement; continue monitoring.' if mmsi in evidence_counts
                else 'Continue AIS monitoring; no vessel-specific risk conclusion is available.')
            triggered=', '.join(evidence_names.get(mmsi,[])) or 'No current screening flag'
            details=[('MMSI',mmsi),('Speed',speed_text),('Course',course_text),
                ('Position',coords),('State / Area (approx.)',vessel_state_hint(vessel.get('region'))),('Region',str(vessel.get('region','Unknown'))),('Risk indicator',level)]
            grid=''.join(f'<div class="key">{escape(k)}</div><div>{escape(val)}</div>' for k,val in details)
            st.markdown('<div class="threat-panel-shell"><div class="threat-vessel-title">⚓ '+escape(str(vessel['name']))+'</div>'
                '<div class="threat-details-grid">'+grid+'</div>'
                '<div class="threat-control"><b style="color:#c6ff00">▣ Recommended Actions</b><div>'+
                escape(controls)+'</div><div style="color:#86b9cf;margin-top:7px">Triggered: '+escape(triggered)+'</div></div></div>',
                unsafe_allow_html=True)

    st.markdown('<div class="threat-head"><span>▣</span>Maritime Risk Assessment — 5 Key Steps</div>',unsafe_allow_html=True)
    steps = [
        ('01','Identify Hazards','Review speed, route and CPA/TCPA screening evidence.'),
        ('02','Likelihood & Consequence','Verify vessel type, traffic and local context.'),
        ('03','Evaluate Risk','Risk = likelihood × consequence; provisional scoring.'),
        ('04','Implement Controls','Verify AIS, monitor traffic and escalate if justified.'),
        ('05','Document & Review','Record observations and reassess when evidence changes.'),
    ]
    for col,(num,title,description) in zip(st.columns(5,gap='small'),steps):
        with col:
            st.markdown(f'<div class="threat-step"><div class="num">{num}</div><div class="label">{escape(title)}</div>'
                        f'<div class="desc">{escape(description)}</div></div>',unsafe_allow_html=True)

    # Preserve access to full advanced evidence and geographic coverage without
    # displacing the historical register from the bottom of the page.
    with st.expander('Advanced screening evidence and nationwide coverage'):
        for name, info in modules.items():
            st.write(f"**{name}:** {info['count']} · {info['status']}")
        if not advanced_events.empty:
            st.dataframe(advanced_events,hide_index=True,width='stretch',height=250)
        st.markdown('**Nationwide State / Territory Coverage**')
        st.dataframe(state_coverage_table(df),hide_index=True,width='stretch',height=260)
        st.caption('Reference pins and approximate regional context are not state-specific vessel counts.')

    st.markdown('<div class="threat-head"><span>▤</span>Historical Assessment Register</div>',unsafe_allow_html=True)
    st.caption('Saved speed-screening assessments only; historical records are not current alerts. Search, filter and scroll the register below.')
    if ASSESSMENT_DB.exists():
        try:
            with sqlite3.connect(ASSESSMENT_DB,timeout=10) as conn:
                totals = conn.execute("SELECT COUNT(*), SUM(CASE WHEN review_status='Pending review' THEN 1 ELSE 0 END) FROM assessments").fetchone()
                log = pd.read_sql_query('SELECT * FROM assessments ORDER BY observed DESC LIMIT 500',conn)
            st.caption(f"Saved assessments (all time): {int(totals[0] or 0)} · Pending review: {int(totals[1] or 0)} · Showing latest 500 maximum")
            if not log.empty:
                log = log.copy()
                log['_date'] = pd.to_datetime(log['observed'],errors='coerce',utc=True).dt.date
                valid_dates = log['_date'].dropna()
                q_col, from_col, to_col, export_col = st.columns([2.2,1.1,1.1,1.1],gap='small')
                with q_col:
                    query = st.text_input('Search vessel / MMSI',key='threat_history_query',placeholder='Search vessel name or MMSI...')
                with from_col:
                    date_from = st.date_input('From (UTC)',value=valid_dates.min() if not valid_dates.empty else datetime.now(timezone.utc).date(),key='threat_history_from')
                with to_col:
                    date_to = st.date_input('To (UTC)',value=valid_dates.max() if not valid_dates.empty else datetime.now(timezone.utc).date(),key='threat_history_to')
                filtered = log
                if query.strip():
                    filtered = filtered[filtered['name'].fillna('').astype(str).str.contains(query.strip(),case=False,regex=False) |
                        filtered['mmsi'].fillna('').astype(str).str.contains(query.strip(),case=False,regex=False)]
                filtered = filtered[filtered['_date'].between(date_from,date_to)] if date_from<=date_to else filtered.iloc[:0]
                view_cols = ['observed','name','mmsi','speed_knots','level','hazard','review_status','recommended_control']
                view = filtered[view_cols].rename(columns={'observed':'Date & Time (UTC)','name':'Vessel Name',
                    'mmsi':'MMSI','speed_knots':'Speed (kn)','level':'Risk Level',
                    'hazard':'Triggered Rule','review_status':'Assessment Result',
                    'recommended_control':'Action / Remarks'})
                with export_col:
                    st.write('')
                    st.download_button('⬇ Export CSV',view.to_csv(index=False),
                        file_name='sea_sentinel_risk_register_filtered.csv',mime='text/csv',key='threat_register_csv')
                st.dataframe(view,width='stretch',hide_index=True,height=285)
                st.caption(f'{len(view)} matching historical assessments · Table scrolls independently')
            else:
                st.info('No historical screening records have been saved yet.')
        except (sqlite3.Error,KeyError,ValueError) as exc:
            st.warning(f'Historical assessment register unavailable: {exc}')
    else:
        st.info('The historical register will appear when a real AIS observation meets a screening threshold.')
    st.caption('Operational decisions require verified AIS data, local navigation context and maritime expert review.')

def reports_page(df, flags, updated):
    st.markdown('<div class="panel-title">AIS Monitoring Reports</div>', unsafe_allow_html=True)
    st.caption(f'Current observation snapshot: {updated or "Unavailable"}. Only positions within the 30-minute window are included.')
    counts = df.region.value_counts().reindex(MONITORED_AREAS, fill_value=0) if not df.empty else pd.Series(0, index=MONITORED_AREAS)
    summary = pd.DataFrame({'Region':counts.index, 'Recent vessels':counts.values})
    st.dataframe(summary, width='stretch', hide_index=True)
    st.download_button('Download vessel snapshot CSV', df.to_csv(index=False),
                       file_name='sea_sentinel_vessel_snapshot.csv', mime='text/csv')
    st.download_button('Download region summary CSV', summary.to_csv(index=False),
                       file_name='sea_sentinel_region_summary.csv', mime='text/csv')
    if HISTORY_DB.exists():
        try:
            with sqlite3.connect(HISTORY_DB,timeout=10) as conn:
                total=conn.execute('SELECT COUNT(*) FROM positions').fetchone()[0]
                history=pd.read_sql_query('SELECT * FROM positions ORDER BY observed DESC LIMIT 10000',conn)
            st.metric('Archived AIS Observations (All Time)',total)
            if not history.empty:
                st.download_button('Download archived AIS history CSV (latest 10,000)',history.to_csv(index=False),file_name='sea_sentinel_ais_history.csv',mime='text/csv')
        except sqlite3.Error as exc:
            st.warning(f'Historical export unavailable: {exc}')
    st.markdown('<div class="panel-title">All Malaysian States — Monitoring Coverage</div>',unsafe_allow_html=True)
    coverage = state_coverage_table(df)
    st.dataframe(coverage,width='stretch',hide_index=True)
    st.download_button('Download nationwide state coverage CSV',coverage.to_csv(index=False),file_name='sea_sentinel_state_coverage.csv',mime='text/csv')
    st.caption('CSV exports contain real collected data only; PDF reporting is not yet implemented.')

with st.sidebar:
    st.markdown('<div class="brand">⛴ SEA <b>SENTINEL</b></div><div class="brand-sub">MARITIME INTELLIGENCE SYSTEM</div>',unsafe_allow_html=True)
    st.divider()
    page = st.radio('Navigation', ['Live AIS Map','Threat Assessment','Intelligence & Reports'], label_visibility='collapsed')
    st.divider()
    region = st.selectbox('Monitoring Region', list(REGIONS.keys()))
    st.caption('All Malaysian States plots all 13 states + 3 Federal Territories. Region views use approximate monitoring boxes.')
    search = st.text_input('Vessel name or MMSI')
    st.caption('AISStream + Open Waters · 30-minute freshness window')

@st.fragment(run_every='15s')
def dashboard():
    df, updated = load_data()
    if not df.empty:
        df['region'] = df.apply(lambda r: classify_region(r.latitude, r.longitude), axis=1)
    else:
        df['region'] = pd.Series(dtype=str)
    if not df.empty:
        try:
            record_position_history(df)
        except (sqlite3.Error, OSError) as exc:
            st.warning(f'Position history could not be saved: {exc}')
    flags = assess_vessels(df)
    if not flags.empty:
        try:
            save_assessments(flags)
        except (sqlite3.Error, OSError) as exc:
            st.warning(f'Risk register could not be saved: {exc}')
    sources = df.source.value_counts() if not df.empty else pd.Series(dtype=int)
    if page != 'Threat Assessment':
        st.markdown('<div class="section-head"><h2>Maritime '+(page)+'</h2><p>Real AIS vessel monitoring across Malaysian waters</p></div>', unsafe_allow_html=True)
        st.markdown('<div class="info-strip">◉ &nbsp; AIS DATA STATUS &nbsp; | &nbsp; Snapshot: '+str(updated or 'Unavailable')+' &nbsp; | &nbsp; Showing only vessel observations ≤ 30 minutes old</div>',unsafe_allow_html=True)
    if df.empty:
        st.warning('No fresh AIS vessel positions in combined_vessels.json. Run your AIS receivers and combiner again to populate the map; dashboard refresh alone does not update the source data.')
    if page != 'Threat Assessment':
        a,b,c,d = st.columns(4)
        a.metric('Tracked Vessels', len(df))
        b.metric('AISStream', int(sources.get('aisstream',0)))
        c.metric('Open Waters', int(sources.get('openwaters',0)))
        d.metric('Monitored Regions', len(MONITORED_AREAS))
    if page == 'Live AIS Map':
        filtered = df
        if region in MONITORED_AREAS:
            filtered = df[df.region == region]
        elif region == 'Peninsular':
            filtered = df[df.region.isin(MONITORED_AREAS[:6])]
        if search:
            filtered = filtered[filtered.name.str.contains(search,case=False,regex=False) |
                                filtered.mmsi.str.contains(search,case=False,regex=False)]
        st.markdown('<div class="panel-title">AIS/GPS Tracking · Live Map & Radar</div>', unsafe_allow_html=True)
        left, right = st.columns([1.55, 1], gap='small')
        with left:
            st.markdown('<div class="route-subheading">LIVE AIS VESSEL MAP</div>',unsafe_allow_html=True)
            make_map(filtered, region)
            st.caption(f'{len(filtered)} fresh vessels in selected region/search. Markers are real AIS coordinates.')
        with right:
            st.markdown('<div class="route-subheading">RADAR VIEW · AIS POSITIONS</div>',unsafe_allow_html=True)
            st.markdown("""
            <style>
            @keyframes seaRadarSweep { from { transform:rotate(0deg); } to { transform:rotate(360deg); } }
            @media (prefers-reduced-motion: reduce) {
                .st-key-sea_radar_sweep [data-testid="stPlotlyChart"]::after { animation:none !important; }
            }
            .st-key-sea_radar_sweep [data-testid="stPlotlyChart"] { position:relative; overflow:hidden; }
            .st-key-sea_radar_sweep [data-testid="stPlotlyChart"]::after {
                content:""; position:absolute; inset:0; pointer-events:none; z-index:5;
                background:conic-gradient(from 0deg at 50% 50%, transparent 0deg,
                    transparent 300deg, rgba(0,255,128,.025) 318deg,
                    rgba(0,255,128,.13) 344deg, rgba(0,255,128,.42) 359deg, transparent 360deg);
                clip-path:circle(42% at 50% 50%);
                animation:seaRadarSweep 6s linear infinite;
            }
            </style>
            """,unsafe_allow_html=True)
            with st.container(key='sea_radar_sweep'):
                live_radar_view(filtered, region)
            st.caption('Animated scanning beam is visual only; plotted targets use real AIS coordinates.')
        x,y = st.columns(2,gap='small')
        with x:
            st.markdown('<div class="panel-title">AIS Source Distribution</div>',unsafe_allow_html=True)
            source_chart(df)
        with y:
            st.markdown('<div class="panel-title">Vessels by Region</div>',unsafe_allow_html=True)
            region_chart(df)
        st.caption('Live positions are limited to the 30-minute freshness window. Historical routes below use saved observations.')
        vessel_routes_page(df)
    elif page=='Intelligence & Reports':
        x,y=st.columns(2)
        with x:
            st.markdown('<div class="panel-title">AIS Source Distribution</div>',unsafe_allow_html=True)
            source_chart(df)
        with y:
            st.markdown('<div class="panel-title">Vessels by Region</div>',unsafe_allow_html=True)
            region_chart(df)
        if HISTORY_DB.exists():
            try:
                with sqlite3.connect(HISTORY_DB,timeout=10) as conn:
                    activity=pd.read_sql_query('''SELECT substr(observed,1,10) AS day, COUNT(*) AS observations, COUNT(DISTINCT mmsi) AS vessels FROM positions GROUP BY substr(observed,1,10) ORDER BY day''',conn)
                if not activity.empty:
                    st.markdown('<div class="panel-title">Historical AIS Activity</div>',unsafe_allow_html=True)
                    fig=go.Figure(go.Scatter(x=activity.day,y=activity.observations,mode='lines+markers',line=dict(color='#FF9500',width=3)))
                    fig.update_layout(template='plotly_dark',paper_bgcolor='#06172A',plot_bgcolor='#06172A',height=320,xaxis_title='UTC date',yaxis_title='Recorded observations')
                    st.plotly_chart(fig,width='stretch')
                    st.caption('Real archived AIS observations grouped by UTC date.')
                else:
                    st.info('No AIS observations have been archived yet.')
            except sqlite3.Error as exc:
                st.warning(f'Historical analytics unavailable: {exc}')
        else:
            st.info('Start the independent history collector to build historical analytics.')
        st.markdown('<div class="panel-title">Monitoring Reports & Data Exports</div>', unsafe_allow_html=True)
        reports_page(df, flags, updated)
    elif page=='Threat Assessment':
        threat_assessment_page(df,flags,15,25)

dashboard()
