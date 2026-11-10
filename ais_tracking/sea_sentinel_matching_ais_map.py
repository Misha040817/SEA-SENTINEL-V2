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



def plotting_history_page_section():
    """Show AIS positions actually recorded by this dashboard, including older observations."""
    st.markdown('<div class="panel-title">Vessel Plotting History</div>', unsafe_allow_html=True)
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
    history['observed_myt'] = history['observed_utc'].dt.tz_convert('Asia/Kuala_Lumpur').dt.strftime('%Y-%m-%d %H:%M:%S')
    col1, col2, col3 = st.columns([1.3, 1, 1])
    with col1:
        vessel_query = st.text_input('Search recorded vessel / MMSI', key='history_search')
    with col2:
        area = st.selectbox('History region', ['All regions'] + MONITORED_AREAS + ['Other'], key='history_region')
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
    st.dataframe(table, width='stretch', hide_index=True, height=310)
    st.download_button('Download plotting history CSV', table.to_csv(index=False),
                       file_name='sea_sentinel_plotting_history.csv', mime='text/csv', key='download_plotting_history')
    st.caption('Each row represents a unique vessel MMSI and observation timestamp. History collection occurs when this dashboard reads refreshed AIS snapshots.')


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
    """Single-page maritime threat dashboard; no tabs or expanders."""
    st.markdown("""
    <style>
    [data-testid="stAlert"] {background:#102c43 !important;border:1px solid #286789 !important;}
    [data-testid="stAlert"] p, [data-testid="stAlert"] div {color:#e5f4ff !important;}
    [data-testid="stDataFrame"] {background:#0d2337 !important;}
    .threat-heading {padding:6px 0 12px;border-bottom:1px solid #1b6d8b;margin-bottom:12px}
    .threat-heading h2 {margin:0;color:#fff;font-size:30px;font-weight:800}
    .threat-heading p {margin:3px 0 0;color:#a9c7d8;font-size:13px}
    .threat-panel {background:linear-gradient(130deg,#09243b,#07182c);
        border:1px solid #147c9f;border-radius:10px;padding:12px 16px;margin:12px 0 6px;
        color:#f4fbff;font-size:15px;font-weight:750}
    .step-tile {min-height:195px;padding:15px 13px;border:1px solid #1685ae;
        border-radius:12px;background:linear-gradient(145deg,#0c3151,#071c35);
        box-shadow:inset 0 0 20px #0a80a015;color:#e8f5ff}
    .step-num {font-size:22px;font-weight:800;color:#00d9ff;margin-bottom:9px}
    .step-name {font-weight:800;font-size:15px;color:#fff;margin-bottom:9px}
    .step-detail {font-size:12px;line-height:1.55;color:#c7dbe8}
    .threat-note {font-size:12px;color:#9fc2d4;margin:4px 0 13px}
    </style>""",unsafe_allow_html=True)
    st.markdown('<div class="threat-heading"><h2>🛡️ Threat Assessment</h2>'
                '<p>Maritime Risk Assessment and Vessel Threat Monitoring • AIS screening prototype</p></div>',
                unsafe_allow_html=True)

    levels = {k:int((flags.level==k).sum()) if not flags.empty else 0 for k in RISK_LEVELS}
    a,b,c,d=st.columns(4)
    a.metric('Tracked Vessels',len(df))
    b.metric('Monitored Regions',len(MONITORED_AREAS))
    c.metric('Flagged for Review',len(flags))
    d.metric('High / Critical',levels['High']+levels['Critical'])
    st.caption('Real AIS data only • A speed-screening flag is not a confirmed security threat. '
               'Counts reflect the latest fresh snapshot, not a live incident feed.')

    left,middle,right=st.columns([2.0,1.1,1.25],gap='small')
    with left:
        st.markdown('<div class="threat-panel">🌊 Maritime Threat Map (Risk View)</div>',unsafe_allow_html=True)
        _risk_map(df,flags)
        st.markdown('<div class="threat-note">🟢 No speed flag / unassessed &nbsp; '
                    '🟡 Moderate &nbsp; 🟠 High &nbsp; 🔴 Critical. '
                    'Markers use actual coordinates.</div>',unsafe_allow_html=True)
    with middle:
        st.markdown('<div class="threat-panel">Risk Matrix (5 × 5)</div>',unsafe_allow_html=True)
        _matrix()
    with right:
        st.markdown('<div class="threat-panel">Risk Distribution</div>',unsafe_allow_html=True)
        _risk_donut(df,flags)

    st.markdown('<div class="threat-panel">🚢 Vessels Requiring Review</div>',unsafe_allow_html=True)
    if flags.empty:
        st.info('0 speed-screening flags in the current AIS snapshot. No fresh vessels meet the current thresholds. '
                'This does not establish that all vessels are safe.')
    else:
        show = flags.sort_values('risk_score',ascending=False).copy()
        show = show.rename(columns={
            'name':'Vessel Name','mmsi':'MMSI','hazard':'Detected Indicator',
            'likelihood':'Likelihood (1–5)','consequence':'Consequence (1–5)',
            'risk_score':'Risk Score','level':'Risk Level',
            'recommended_control':'Recommended Action','speed_knots':'Speed (kn)',
            'observed':'Observed (UTC)'})
        st.dataframe(show[['Vessel Name','MMSI','Speed (kn)','Detected Indicator',
                          'Likelihood (1–5)','Consequence (1–5)','Risk Score',
                          'Risk Level','Recommended Action','Observed (UTC)']],
                     width='stretch',hide_index=True)
        st.download_button('⬇ Export risk screening CSV',flags.to_csv(index=False),
            file_name='sea_sentinel_risk_screening.csv',mime='text/csv',
            key='threat_current_csv')
    st.caption(f'Current provisional thresholds: advisory ≥ {advisory_kn} kn; '
               f'elevated ≥ {high_kn} kn. A vessel’s speed alone cannot establish likelihood '
               'of an accident or the severity of consequences.')

    st.markdown('<div class="threat-panel">📋 Maritime Risk Assessment — 5 Key Steps</div>',
                unsafe_allow_html=True)
    steps = [
        ('01','Identify Hazards','Review AIS speed flags. Collision, weather, '
         'restricted-zone and onboard-work hazards require additional verified data.'),
        ('02','Likelihood & Consequence','Illustrative 1–5 ratings. '
         'Verify vessel type, traffic, weather and operating context.'),
        ('03','Evaluate Risk','Risk score = likelihood × consequence. '
         'Low 1–4 · Moderate 5–9 · High 10–19 · Critical 20–25.'),
        ('04','Implement Controls','Verify AIS and vessel identity, review '
         'local navigation context, increase monitoring where warranted.'),
        ('05','Document & Review','Store real observations and screening results; '
         'review evidence, assumptions and recommended controls.')
    ]
    cols=st.columns(5,gap='small')
    for col,(num,title,detail) in zip(cols,steps):
        with col:
            st.markdown(f'<div class="step-tile"><div class="step-num">{num}</div>'
                        f'<div class="step-name">{escape(title)}</div>'
                        f'<div class="step-detail">{escape(detail)}</div></div>',
                        unsafe_allow_html=True)

    st.markdown('<div class="threat-panel">Historical Assessment Register (Not Current Alerts)</div>',
                unsafe_allow_html=True)
    st.info('Historical entries may refer to vessels no longer in the fresh AIS snapshot. Only AIS speed is screened automatically in this version. '
            'The 5×5 ratings are scenario assumptions, not calibrated collision '
            'probabilities or validated maritime operational risk assessments.')
    if ASSESSMENT_DB.exists():
        try:
            with sqlite3.connect(ASSESSMENT_DB,timeout=10) as conn:
                log=pd.read_sql_query('SELECT * FROM assessments ORDER BY observed DESC LIMIT 500',conn)
            if not log.empty:
                st.dataframe(log[['observed','name','mmsi','hazard','risk_score',
                                  'level','evidence_status','review_status']],
                             width='stretch',hide_index=True)
                st.download_button('⬇ Export documented risk register',
                    log.to_csv(index=False),file_name='sea_sentinel_risk_register.csv',
                    mime='text/csv',key='threat_register_csv')
            else:
                st.caption('No screening records saved yet.')
        except (sqlite3.Error,KeyError) as exc:
            st.warning(f'Could not read risk register: {exc}')
    else:
        st.caption('Risk register will be created when a real observation triggers screening.')
    st.caption('Operational deployment requires validated hazard models, '
               'vessel-specific context, and maritime expert review.')

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
    st.caption('PDF reporting is not yet implemented; CSV exports contain only actual collected data.')

with st.sidebar:
    st.markdown('<div class="brand">⛴ SEA <b>SENTINEL</b></div><div class="brand-sub">MARITIME INTELLIGENCE SYSTEM</div>',unsafe_allow_html=True)
    st.divider()
    page = st.radio('Navigation', ['Live AIS Map','Vessel Routes','Threat Assessment','Analytics','Reports'], label_visibility='collapsed')
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
        plotting_history_page_section()
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
        threat_assessment_page(df,flags,15,25)
    elif page=='Reports':
        reports_page(df, flags, updated)

dashboard()
