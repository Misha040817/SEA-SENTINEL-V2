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