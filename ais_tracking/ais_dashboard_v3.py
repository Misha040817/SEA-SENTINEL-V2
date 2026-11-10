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

st.markdown('''<style>
:root {color-scheme:dark}
.stApp, [data-testid="stAppViewContainer"] {background:#030D1B;color:#fff}
[data-testid="stSidebar"] {background:#06172A;border-right:1px solid #16405B}
[data-testid="stHeader"] {background:#030D1B}
h1,h2,h3,h4,p,label,span {color:#fff}
h1 {font-weight:800;letter-spacing:.4px}
[data-testid="stMetric"] {background:linear-gradient(135deg,#09223A,#06172A);border:1px solid #087CA0;border-radius:14px;padding:16px;box-shadow:0 0 15px #00D9FF12}
[data-testid="stMetricValue"] {color:#C6FF00;font-weight:800}
[data-testid="stMetricLabel"] {color:#fff}
[data-testid="stVerticalBlockBorderWrapper"] {border-color:#087CA0!important}
div.stButton>button {background:#10243A;color:#fff;border:1px solid #176A87;border-radius:9px}
div.stButton>button:hover {border-color:#C6FF00;color:#C6FF00}
[data-testid="stSelectbox"] div[data-baseweb="select"]>div {background:#10243A;color:#fff}
[data-testid="stDataFrame"] {border:1px solid #176A87}
.section-head {border-left:6px solid #C6FF00;padding-left:14px;margin:12px 0 20px}
.section-head h2 {margin:0;color:#fff}
.section-head p {color:#B8C7D9;margin:0}
.panel-title {font-weight:700;font-size:17px;color:#fff;border-left:5px solid #C6FF00;padding-left:10px;margin-bottom:8px}
.small-note {color:#B8C7D9;font-size:13px}
</style>''', unsafe_allow_html=True)

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
    colors = {'Moving':[198,255,0,225], 'Slow':[0,217,255,225], 'Stationary / Unknown':[164,112,255,225]}
    dots = df.copy()
    if not dots.empty:
        dots['color'] = dots['movement'].map(colors)
        dots['radius'] = 400
    labels = pd.DataFrame(LABELS)
    layers = [
        pdk.Layer('ScatterplotLayer', dots, get_position='[longitude, latitude]', get_fill_color='color', get_radius='radius', radius_min_pixels=3, radius_max_pixels=8, pickable=True, auto_highlight=True),
        pdk.Layer('TextLayer', labels, get_position='[longitude, latitude]', get_text='name', get_size=15, get_color=[255,255,255,225], get_text_anchor='middle', get_alignment_baseline='center', pickable=False),
    ]
    deck = pdk.Deck(layers=layers, initial_view_state=pdk.ViewState(latitude=lat, longitude=lon, zoom=zoom, pitch=0), map_style='https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json', tooltip={'html':'<b>{name}</b><br/>MMSI: {mmsi}<br/>Source: {source}<br/>Speed: {speed_knots} kn<br/>Observed: {last_seen}', 'style':{'backgroundColor':'#06172A','color':'white','border':'1px solid #00D9FF'}})
    st.pydeck_chart(deck, height=510, use_container_width=True)
    st.caption('White state labels are approximate reference points, not administrative boundaries. Markers are genuine AIS records only.')


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
    st.markdown('## 🚢 SEA SENTINEL')
    st.caption('AIS / GPS INTELLIGENCE')
    st.divider()
    page = st.radio('Navigation', ['Overview','Live AIS Map','Vessel Routes','Vessel Explorer','Threat Assessment','Analytics','AI Detection','Event History','Reports','Settings'], label_visibility='collapsed')
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
    st.markdown('<div class="section-head"><h2>Maritime '+('Overview' if page=='Overview' else page)+'</h2><p>SEA SENTINEL — Malaysian maritime situational awareness</p></div>', unsafe_allow_html=True)
    st.caption('Snapshot updated: '+str(updated or 'Unavailable')+' · Display uses observations within the last 30 minutes')
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
        x,y,z = st.columns(3)
        x.metric('Moving > 5 kn', int((df.movement=='Moving').sum()) if not df.empty else 0)
        y.metric('Slow 0.5–5 kn', int((df.movement=='Slow').sum()) if not df.empty else 0)
        z.metric('Stationary / Unknown', int((df.movement=='Stationary / Unknown').sum()) if not df.empty else 0)
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
    elif page=='AI Detection':
        st.info('The webcam/video detection module will be integrated from the main SEA SENTINEL application.')
    elif page=='Event History':
        st.info('Historical event logging will be connected after a persistent event store is implemented.')
    elif page=='Reports':
        st.download_button('Download current AIS CSV',df.to_csv(index=False).encode('utf-8'),file_name='sea_sentinel_ais_report.csv',mime='text/csv')
    elif page=='Settings':
        st.write('Current AIS snapshot:',str(DATA_FILE))
        st.write('Freshness filter: 30 minutes · Dashboard refresh: 15 seconds')
        st.warning('Dashboard refresh does not fetch new Open Waters data or rerun the AIS combiner. Schedule those separately.')

dashboard()
