import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd
import plotly.graph_objects as go
import folium
import streamlit.components.v1 as components
from html import escape
import streamlit as st

st.set_page_config(page_title='SEA SENTINEL | AIS/GPS', page_icon='🚢', layout='wide', initial_sidebar_state='expanded')
BASE = Path(__file__).resolve().parent
DATA_FILE = BASE / 'combined_vessels.json'
HISTORY_DB = BASE / 'ais_position_history.sqlite3'
LIME, CYAN, NAVY = '#C6FF00', '#00D9FF', '#06172A'
REGIONS = {
    'Malaysia': (4.1, 109.0, 5.0),
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
    if .7 <= lat <= 2.5 and 103.1 <= lon <= 105.0:
        return 'Johor / Singapore'
    if 5.0 <= lat <= 7.6 and 115.0 <= lon <= 119.8:
        return 'Sabah'
    if .5 <= lat <= 5.0 and 109.0 <= lon <= 115.5:
        return 'Sarawak'
    if 5.5 <= lat <= 6.8 and 101.8 <= lon <= 103.5:
        return 'Kelantan'
    if 4.3 <= lat <= 5.8 and 102.5 <= lon <= 104.0:
        return 'Terengganu'
    if 3.2 <= lat <= 4.5 and 102.5 <= lon <= 104.3:
        return 'Pahang / Kuantan'
    if 2.5 <= lat <= 3.8 and 100.5 <= lon <= 101.8:
        return 'Port Klang / Selangor'
    if 4.8 <= lat <= 6.0 and 99.7 <= lon <= 100.9:
        return 'Penang'
    return 'Other'


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


def vessel_routes_page(df):
    st.markdown('<div class="panel-title">Vessel Routes · Recorded AIS Positions</div>', unsafe_allow_html=True)
    st.caption('Routes connect actual stored observations. History begins when this dashboard starts collecting; a single position cannot establish a route.')
    history = route_history()
    if history.empty:
        st.info('No recorded AIS position history yet. Keep the dashboard running while receivers and the combiner refresh data.')
        return
    counts = history.groupby('mmsi').size()
    eligible = counts[counts >= 2].index.tolist()
    st.metric('Vessels with at least 2 observations', len(eligible))
    if not eligible:
        st.info('Positions are being recorded. A vessel needs at least two observations at different times before its route can be drawn.')
        st.dataframe(history.tail(15), width='stretch', hide_index=True)
        return
    options = {m: f"{history[history.mmsi == m].iloc[-1]['name']} · {m} ({int(counts[m])} points)" for m in eligible}
    selected = st.selectbox('Select vessel', eligible, format_func=lambda m: options[m])
    points = history[history.mmsi == selected].sort_values('observed')
    first = points.iloc[0]
    m = folium.Map(location=[float(first.latitude), float(first.longitude)], zoom_start=8,
                   tiles='OpenStreetMap', control_scale=True)
    coords = points[['latitude','longitude']].astype(float).values.tolist()
    folium.PolyLine(coords, color='#00D9FF', weight=3, opacity=.85,
                    tooltip='Recorded AIS positions (not an inferred route)').add_to(m)
    folium.CircleMarker(coords[0], radius=6, color='#C6FF00', fill=True,
                        tooltip='First recorded observation').add_to(m)
    folium.CircleMarker(coords[-1], radius=6, color='#FF4DB8', fill=True,
                        tooltip='Latest recorded observation').add_to(m)
    if len(coords) > 1:
        m.fit_bounds(coords)
    components.html(m.get_root().render(), height=480, scrolling=False)
    st.dataframe(points[['observed','name','latitude','longitude','speed_knots','source']],
                 width='stretch', hide_index=True)
    st.download_button('Download selected vessel route CSV', points.to_csv(index=False),
                       file_name=f'vessel_route_{selected}.csv', mime='text/csv')


def make_map(df, region):
    # Navy-tinted OpenStreetMap map with genuine AIS positions.
    lat, lon, zoom = REGIONS[region]
    m = folium.Map(location=[lat, lon], zoom_start=zoom, tiles=None,
                   control_scale=True, zoom_control=True, prefer_canvas=True)
    # Keep the OpenStreetMap coastline and place names, tint the raster ocean navy.
    tiles = folium.TileLayer(
        tiles='https://tile.openstreetmap.org/{z}/{x}/{y}.png',
        attr='© OpenStreetMap contributors', name='OpenStreetMap (navy tinted)',
        max_zoom=19, overlay=False, control=False)
    tiles.add_to(m)
    # The tile filter recolours the raster itself; unlike PyDeck's custom style,
    # this does not pass a dictionary into Streamlit's map renderer.
    m.get_root().header.add_child(folium.Element('''<style>
      .leaflet-container {background: #071F3D !important;}
      .leaflet-tile-pane img.leaflet-tile {
        filter: grayscale(1) sepia(1) saturate(3) hue-rotate(175deg) brightness(0.46) contrast(1.35);
      }
      .sea-label {color:white;font:800 12px Arial,sans-serif;
        text-shadow:0 1px 3px #000,0 0 5px #000;white-space:nowrap;}
    </style>'''))
    colors = REGION_COLORS
    for _, r in df.iterrows():
        color = colors.get(str(r.get('region', 'Other')), '#FF4242')
        info = (f"<b>{escape(str(r.get('name','Unknown')))}</b>"
                f"<br>MMSI: {escape(str(r.get('mmsi','')))}"
                f"<br>Region: {escape(str(r.get('region','Other')))}"
                f"<br>Source: {escape(str(r.get('source','')))}"
                f"<br>Speed: {escape(str(r.get('speed_knots','')))} kn"
                f"<br>Observed: {escape(str(r.get('last_seen','')))}")
        folium.CircleMarker(location=[float(r.latitude), float(r.longitude)],
            radius=4, color="#FFFFFF", weight=0.8, fill=True,
            fill_color=color, fill_opacity=0.95,
            popup=folium.Popup(info, max_width=290)).add_to(m)
    # Detailed state labels only at regional zoom; otherwise they overlap at Malaysia-wide scale.
    if zoom >= 7:
        for label in LABELS:
            if abs(label['latitude'] - lat) <= 2.5 and abs(label['longitude'] - lon) <= 3.5:
                folium.Marker([label['latitude'], label['longitude']],
                    icon=folium.DivIcon(html='<div class="sea-label">'+escape(label['name'])+'</div>')).add_to(m)
    components.html(m.get_root().render(), height=515, scrolling=False)
    st.caption('Real AIS positions only. Marker colours identify regions, not threat levels.')


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
    'Other': '#B5BDC9',                   # Unclassified / outside monitored areas
}


def source_chart(df):
    counts = df.source.value_counts() if not df.empty else pd.Series(dtype=int)
    if counts.empty:
        st.info('No recent AIS positions available.')
        return
    source_colors = {'aisstream':'#C6FF00', 'openwaters':'#168BFF'}
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
    st.plotly_chart(chart_style(fig, 295), width='stretch')


def region_chart(df):
    counts = df.region.value_counts() if not df.empty else pd.Series(dtype=int)
    counts = counts.reindex(MONITORED_AREAS, fill_value=0)
    fig = go.Figure(go.Bar(
        x=counts.values, y=counts.index, orientation='h',
        marker=dict(color=[REGION_COLORS[region] for region in counts.index]),
        text=[str(int(v)) for v in counts.values],
        textposition='outside',
        textfont=dict(color='#FFFFFF', size=13, family='Arial Black'),
        cliponaxis=False,
        hovertemplate='%{y}: %{x} vessels<extra></extra>'
    ))
    fig.update_layout(
        yaxis=dict(autorange='reversed', tickfont=dict(color='#FFFFFF', size=12, family='Arial')),
        xaxis=dict(gridcolor='#1A3850', rangemode='tozero',
                   range=[0, max(4, float(counts.max()) * 1.25)]),
        showlegend=False, margin=dict(l=12, r=38, t=15, b=18),
        bargap=0.32
    )
    st.plotly_chart(chart_style(fig, 330), width='stretch')



# Transparent screening rules; these are operational flags, not verified threats.
EVENT_DB = BASE / 'ais_events.sqlite3'

def assess_vessels(df):
    columns = ['mmsi', 'name', 'region', 'speed_knots', 'level', 'reason', 'observed', 'source']
    flagged = []
    if df.empty:
        return pd.DataFrame(columns=columns)
    for _, r in df.iterrows():
        speed = r.get('speed_knots')
        if pd.isna(speed) or float(speed) < 0:
            continue
        if float(speed) >= 25:
            level, reason = 'High', 'Speed at least 25 knots (review required)'
        elif float(speed) >= 15:
            level, reason = 'Advisory', 'Speed at least 15 knots (review recommended)'
        else:
            continue
        flagged.append({'mmsi':str(r.mmsi), 'name':str(r['name']),
            'region':str(r.region), 'speed_knots':float(speed), 'level':level,
            'reason':reason, 'observed':r.observed.isoformat(), 'source':str(r.source)})
    return pd.DataFrame(flagged, columns=columns)


def save_events(flags):
    with sqlite3.connect(EVENT_DB, timeout=10) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS events (
            mmsi TEXT NOT NULL, observed TEXT NOT NULL, rule TEXT NOT NULL,
            name TEXT, region TEXT, speed_knots REAL, level TEXT, source TEXT,
            PRIMARY KEY (mmsi, observed, rule))''')
        if not flags.empty:
            rows = [(r.mmsi, r.observed, r.reason, r['name'], r.region,
                     r.speed_knots, r.level, r.source) for _, r in flags.iterrows()
                     if r.mmsi.strip().lower() not in ('', 'unknown', 'none')]
            conn.executemany('INSERT OR IGNORE INTO events VALUES (?,?,?,?,?,?,?,?)', rows)


def event_history():
    if not EVENT_DB.exists():
        return pd.DataFrame(columns=['mmsi','observed','rule','name','region','speed_knots','level','source'])
    with sqlite3.connect(EVENT_DB, timeout=10) as conn:
        return pd.read_sql_query('SELECT * FROM events ORDER BY observed DESC', conn)


def threat_assessment_page(flags):
    st.markdown('<div class="panel-title">Rule-based Vessel Screening</div>', unsafe_allow_html=True)
    st.caption('Operational speed thresholds are illustrative screening rules, not validated maritime threat detections. Speed alone cannot establish suspicious intent.')
    x,y,z = st.columns(3)
    x.metric('High-speed flags (≥25 kn)', int((flags.level == 'High').sum()) if not flags.empty else 0)
    y.metric('Advisory flags (15–25 kn)', int((flags.level == 'Advisory').sum()) if not flags.empty else 0)
    z.metric('Total flagged observations', len(flags))
    if flags.empty:
        st.info('No current observations meet the configured speed screening thresholds.')
    else:
        st.dataframe(flags, width='stretch', hide_index=True)
        st.download_button('Download current screening CSV', flags.to_csv(index=False),
                           file_name='sea_sentinel_screening.csv', mime='text/csv')
    st.caption('Missing speed values are not scored. Restricted-zone, loitering, and route-deviation rules are not implemented.')


def event_history_page():
    st.markdown('<div class="panel-title">Recorded Screening Events</div>', unsafe_allow_html=True)
    events = event_history()
    st.metric('Stored screening events', len(events))
    if events.empty:
        st.info('No screening events have been recorded yet.')
    else:
        st.dataframe(events, width='stretch', hide_index=True)
        st.download_button('Download event history CSV', events.to_csv(index=False),
                           file_name='sea_sentinel_event_history.csv', mime='text/csv')
    st.caption('Events are saved only for observed records meeting screening rules. These are not verified security incidents.')


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
    st.download_button('Download screening events CSV', event_history().to_csv(index=False),
                       file_name='sea_sentinel_screening_events.csv', mime='text/csv')
    st.caption('PDF reporting is not yet implemented; CSV exports contain only actual collected data.')

with st.sidebar:
    st.markdown('<div class="brand">⛴ SEA <b>SENTINEL</b></div><div class="brand-sub">MARITIME INTELLIGENCE SYSTEM</div>',unsafe_allow_html=True)
    st.divider()
    page = st.radio('Navigation', ['Live AIS Map','Vessel Routes','Vessel Explorer','Threat Assessment','Analytics','Event History','Reports'], label_visibility='collapsed')
    st.divider()
    region = st.selectbox('Monitoring Region', list(REGIONS.keys()))
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
    try:
        save_events(flags)
    except (sqlite3.Error, OSError) as exc:
        st.warning(f'Screening event storage unavailable: {exc}')
    sources = df.source.value_counts() if not df.empty else pd.Series(dtype=int)
    st.markdown('<div class="section-head"><h2>Maritime '+(page)+'</h2><p>Real AIS vessel monitoring across Malaysian waters</p></div>', unsafe_allow_html=True)
    st.markdown('<div class="info-strip">◉ &nbsp; AIS DATA STATUS &nbsp; | &nbsp; Snapshot: '+str(updated or 'Unavailable')+' &nbsp; | &nbsp; Showing only vessel observations ≤ 30 minutes old</div>',unsafe_allow_html=True)
    if df.empty:
        st.warning('No fresh AIS vessel positions in combined_vessels.json. Run your AIS receivers and combiner again to populate the map; dashboard refresh alone does not update the source data.')
    a,b,c,d = st.columns(4)
    a.metric('Tracked Vessels', len(df))
    b.metric('AISStream', int(sources.get('aisstream',0)))
    c.metric('Open Waters', int(sources.get('openwaters',0)))
    d.metric('Monitored Regions', len(MONITORED_AREAS))
    if page == 'Live AIS Map':
        left,right = st.columns([2.3,1],gap='medium')
        with left:
            st.markdown('<div class="panel-title">Live AIS Vessel Tracking</div>', unsafe_allow_html=True)
            filtered = df
            if region != 'Malaysia':
                filtered = df[df.region==region] if region in MONITORED_AREAS else df
            if search:
                filtered = filtered[filtered.name.str.contains(search,case=False,regex=False) | filtered.mmsi.str.contains(search,case=False,regex=False)]
            make_map(filtered, region)
            st.caption(f'{len(filtered)} fresh vessel positions in the selected view. Regions without data remain selectable.')
        with right:
            st.markdown('<div class="panel-title">Vessel Source Distribution</div>', unsafe_allow_html=True)
            source_chart(df)
            st.markdown('<div class="panel-title">Vessels by Region</div>', unsafe_allow_html=True)
            region_chart(df)
        st.markdown('<div class="panel-title">Operational Snapshot</div>',unsafe_allow_html=True)
        x,y,z,w = st.columns(4)
        x.metric('Moving > 5 kn', int((df.movement=='Moving').sum()) if not df.empty else 0)
        y.metric('Slow 0.5–5 kn', int((df.movement=='Slow').sum()) if not df.empty else 0)
        z.metric('Stationary / Unknown', int((df.movement=='Stationary / Unknown').sum()) if not df.empty else 0)
        w.metric('Fresh Sources', len(sources))
        st.caption('Screening results are available in Threat Assessment. Historical routes require repeated observations; no synthetic data is used.')
    elif page=='Vessel Explorer':
        filtered = df[df.name.str.contains(search,case=False,regex=False) | df.mmsi.str.contains(search,case=False,regex=False)] if search and not df.empty else df
        st.dataframe(filtered[['name','mmsi','region','latitude','longitude','speed_knots','source','last_seen']] if not filtered.empty else pd.DataFrame(), width='stretch',hide_index=True)
        st.download_button('Download current AIS CSV',filtered.to_csv(index=False).encode('utf-8'),file_name='sea_sentinel_recent_vessels.csv',mime='text/csv')
    elif page=='Analytics':
        x,y=st.columns(2)
        with x:
            st.markdown('<div class="panel-title">AIS Source Distribution</div>',unsafe_allow_html=True)
            source_chart(df)
        with y:
            st.markdown('<div class="panel-title">Vessels by Region</div>',unsafe_allow_html=True)
            region_chart(df)
        st.info('Historical activity charts require stored time-series snapshots. Current data is a single fresh snapshot.')
    elif page=='Vessel Routes':
        vessel_routes_page(df)
    elif page=='Threat Assessment':
        threat_assessment_page(flags)
    elif page=='Event History':
        event_history_page()
    elif page=='Reports':
        reports_page(df, flags, updated)

dashboard()
