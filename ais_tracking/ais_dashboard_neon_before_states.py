import json
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd
import plotly.graph_objects as go
import pydeck as pdk
import streamlit as st

st.set_page_config(page_title='SEA SENTINEL | AIS/GPS', page_icon='🚢', layout='wide', initial_sidebar_state='expanded')
BASE = Path(__file__).resolve().parent
DATA_FILE = BASE / 'combined_vessels.json'
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


def make_map(df, region):
    lat, lon, zoom = REGIONS[region]

    colors = {
        'Moving': [198, 255, 0, 245],
        'Slow': [0, 217, 255, 245],
        'Stationary / Unknown': [164, 112, 255, 245]
    }

    dots = df.copy()

    if not dots.empty:
        dots['color'] = dots['movement'].map(colors)
        dots['glow_color'] = dots['color'].apply(
            lambda c: [c[0], c[1], c[2], 55]
        )

    labels = pd.DataFrame(LABELS)

    layers = [
        pdk.Layer(
            'ScatterplotLayer',
            dots,
            get_position='[longitude, latitude]',
            get_fill_color='glow_color',
            get_radius=12000,
            radius_min_pixels=10,
            radius_max_pixels=24,
            stroked=False,
            pickable=False
        ),
        pdk.Layer(
            'ScatterplotLayer',
            dots,
            get_position='[longitude, latitude]',
            get_fill_color='color',
            get_radius=3000,
            radius_min_pixels=5,
            radius_max_pixels=11,
            pickable=True,
            auto_highlight=True
        ),
        pdk.Layer(
            'TextLayer',
            labels,
            get_position='[longitude, latitude]',
            get_text='name',
            get_size=15,
            get_color=[255, 255, 255, 225],
            get_text_anchor='middle',
            get_alignment_baseline='center',
            pickable=False
        )
    ]

    deck = pdk.Deck(
        layers=layers,
        initial_view_state=pdk.ViewState(
            latitude=4.0,
            longitude=109.0,
            zoom=3.5,
            pitch=0
        ),
        map_style='https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json',
        tooltip={
            'html': '<b>{name}</b><br/>MMSI: {mmsi}<br/>Source: {source}<br/>Speed: {speed_knots} kn<br/>Observed: {last_seen}',
            'style': {
                'backgroundColor': '#06172A',
                'color': 'white',
                'border': '1px solid #00D9FF'
            }
        }
    )

    st.pydeck_chart(deck, height=510, use_container_width=True)
    st.caption(
        'Neon markers represent genuine AIS vessel positions. '
        'White labels are approximate reference locations.'
    )



def chart_style(fig, height=270):
    fig.update_layout(paper_bgcolor='#06172A', plot_bgcolor='#06172A', font_color='white', margin=dict(l=10,r=10,t=20,b=10), height=height, legend=dict(orientation='h',y=-.12))
    return fig


def source_chart(df):
    counts = df.source.value_counts() if not df.empty else pd.Series(dtype=int)
    if counts.empty:
        st.info('No recent AIS positions available.')
        return
    fig = go.Figure(go.Pie(labels=counts.index, values=counts.values, hole=.65, marker=dict(colors=['#168BFF','#C6FF00','#00D9FF','#A478FF']), textinfo='percent'))
    fig.add_annotation(text=str(len(df)), x=.5,y=.5,showarrow=False,font=dict(size=25,color='white'))
    st.plotly_chart(chart_style(fig), use_container_width=True)


def region_chart(df):
    counts = df.region.value_counts() if not df.empty else pd.Series(dtype=int)
    counts = counts.reindex(MONITORED_AREAS, fill_value=0)
    fig = go.Figure(go.Bar(x=counts.values, y=counts.index, orientation='h', marker_color='#C6FF00'))
    fig.update_layout(yaxis=dict(autorange='reversed'), showlegend=False, xaxis=dict(gridcolor='#1A3850'))
    st.plotly_chart(chart_style(fig,310), use_container_width=True)


with st.sidebar:
    st.markdown('<div class="brand">⛴ SEA <b>SENTINEL</b></div><div class="brand-sub">MARITIME INTELLIGENCE SYSTEM</div>',unsafe_allow_html=True)
    st.divider()
    page = st.radio('Navigation', ['Overview','Live AIS Map','Vessel Routes','Vessel Explorer','Threat Assessment','Analytics','Event History','Reports','Settings'], label_visibility='collapsed')
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
    sources = df.source.value_counts() if not df.empty else pd.Series(dtype=int)
    st.markdown('<div class="section-head"><h2>Maritime '+('Overview' if page=='Overview' else page)+'</h2><p>Real AIS vessel monitoring across Malaysian waters</p></div>', unsafe_allow_html=True)
    st.markdown('<div class="info-strip">◉ &nbsp; AIS DATA STATUS &nbsp; | &nbsp; Snapshot: '+str(updated or 'Unavailable')+' &nbsp; | &nbsp; Showing only vessel observations ≤ 30 minutes old</div>',unsafe_allow_html=True)
    if df.empty:
        st.warning('No fresh AIS vessel positions in combined_vessels.json. Run your AIS receivers and combiner again to populate the map; dashboard refresh alone does not update the source data.')
    a,b,c,d = st.columns(4)
    a.metric('Tracked Vessels', len(df))
    b.metric('AISStream', int(sources.get('aisstream',0)))
    c.metric('Open Waters', int(sources.get('openwaters',0)))
    d.metric('Monitored Regions', len(MONITORED_AREAS))
    if page in ('Overview','Live AIS Map'):
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
        st.info('Threat alerts, vessel routes and 24-hour trends will appear only after their respective data modules are connected. No fabricated values are displayed.')
    elif page=='Vessel Explorer':
        filtered = df[df.name.str.contains(search,case=False,regex=False) | df.mmsi.str.contains(search,case=False,regex=False)] if search and not df.empty else df
        st.dataframe(filtered[['name','mmsi','region','latitude','longitude','speed_knots','source','last_seen']] if not filtered.empty else pd.DataFrame(), use_container_width=True,hide_index=True)
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
        st.info('Route plotting will be enabled after storing consecutive positions for each MMSI. No artificial routes are displayed.')
    elif page=='Threat Assessment':
        st.info('Threat assessment rules are not yet connected. No unverified threat alerts are shown.')
    elif page=='Event History':
        st.info('Historical event logging will be connected after a persistent event store is implemented.')
    elif page=='Reports':
        st.download_button('Download current AIS CSV',df.to_csv(index=False).encode('utf-8'),file_name='sea_sentinel_ais_report.csv',mime='text/csv')
    elif page=='Settings':
        st.write('Current AIS snapshot:',str(DATA_FILE))
        st.write('Freshness filter: 30 minutes · Dashboard refresh: 15 seconds')
        st.warning('Dashboard refresh does not fetch new Open Waters data or rerun the AIS combiner. Schedule those separately.')

dashboard()
