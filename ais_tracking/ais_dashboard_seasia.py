"""SEA SENTINEL | Southeast Asia Command Map
Run: python -m streamlit run ais_tracking/ais_dashboard_seasia.py --server.port 8516
Requires: streamlit, folium, streamlit-folium; local malaysia_states.geojson and combined_vessels.json.
"""
import html
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import folium
from folium.plugins import Fullscreen, MiniMap
import streamlit as st
from streamlit_folium import st_folium

ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title="SEA SENTINEL | Maritime Command Centre", page_icon="🚢", layout="wide", initial_sidebar_state="expanded")
st.markdown("""<style>
.stApp{background:#041221;color:#edf7ff}
[data-testid="stSidebar"]{background:#03101f;border-right:1px solid #12445b}
.block-container{max-width:1900px;padding-top:.75rem;padding-bottom:1rem}
[data-testid="stMetric"]{background:linear-gradient(130deg,#081e31,#07182a);border:1px solid #17637b;border-radius:11px;padding:10px 15px}
[data-testid="stMetricLabel"]{color:#9db9c8}
[data-testid="stMetricValue"]{color:#dcff64}
div[data-testid="stVerticalBlock"]{gap:.55rem}
h1,h2,h3{color:#f3f9ff!important}
.sea-title{font-size:32px;font-weight:900;letter-spacing:1px;color:white}
.sea-title span{color:#b5f820}
.sea-sub{font-size:12px;color:#8fc8da;letter-spacing:2px;margin-top:-7px}
.section{border-left:4px solid #a9f320;padding-left:12px;font-size:21px;font-weight:800;margin:5px 0 8px}
.note{font-size:12px;color:#a6c0d2}
.legend{font-size:13px;line-height:2.2}
</style>""", unsafe_allow_html=True)

VIEWS={
 "Southeast Asia":([5.5,111.0],5),
 "Malaysia":([4.3,109.2],6),
 "Peninsular Malaysia":([4.5,101.9],7),
 "Sabah":([5.6,117.0],8),
 "Sarawak":([2.8,113.2],7),
 "Singapore Strait":([1.28,103.9],10),
 "Thailand":([14.2,101.0],6),
 "Indonesia":([-2.0,117.0],5),
 "Philippines":([12.0,122.0],6),
 "Vietnam":([15.3,107.8],6),
}
# Manually placed cartographic label anchors (not administrative boundaries).
STATE_LABELS=[('Perlis',6.46,100.23),('Kedah',6.0,100.7),('Penang',5.38,100.25),('Perak',4.8,101.1),('Kelantan',5.75,102.1),('Terengganu',5.0,103.05),('Pahang',3.95,102.5),('Selangor',3.35,101.45),('N. Sembilan',2.72,102.1),('Melaka',2.28,102.3),('Johor',2.0,103.35),('Sabah',5.5,116.4),('Sarawak',2.75,113.35)]
COUNTRY_LABELS=[('THAILAND',14.3,101.1),('VIETNAM',16.0,107.9),('CAMBODIA',12.7,104.9),('PHILIPPINES',12.5,122.4),('INDONESIA',-2.1,116.2),('BRUNEI',4.5,114.7),('SINGAPORE',1.25,103.85)]

def parse_dt(value):
    if not value:return None
    try:
        d=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return (d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc))
    except (TypeError,ValueError):return None

@st.cache_data(ttl=15)
def read_json(path,mtime):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def marker_class(speed):
    if speed is None:return ('Unknown speed','#a078dc')
    if speed>5:return ('Moving','#8ef12a')
    if speed>0.5:return ('Slow','#ffbf36')
    return ('Stationary','#e44852')

st.sidebar.markdown('### 🚢 SEA SENTINEL')
st.sidebar.caption('MARITIME INTELLIGENCE COMMAND CENTRE')
st.sidebar.divider()
page=st.sidebar.radio('Navigation',['Overview','Live AIS Map','Vessel Explorer','Threat Assessment','Analytics'],label_visibility='collapsed')
st.sidebar.divider()
view=st.sidebar.selectbox('Map region',list(VIEWS),index=0)
show_stored=st.sidebar.toggle('Include stored / stale positions',value=True,help='For map testing. Stored positions are not necessarily live.')
show_states=st.sidebar.toggle('Malaysia state shading',value=True)
show_labels=st.sidebar.toggle('Bold state and country labels',value=True)
show_vessels=st.sidebar.toggle('AIS vessel dots',value=True)
st.sidebar.caption('Country borders are supplied by the map baselayer. Detailed Malaysian state boundaries come from the local GeoJSON.')

st.markdown('<div class="sea-title">🚢 SEA <span>SENTINEL</span></div><div class="sea-sub">MARITIME INTELLIGENCE COMMAND CENTRE · SOUTHEAST ASIA</div>',unsafe_allow_html=True)
geo_path=ROOT/'malaysia_states.geojson'; data_path=ROOT/'combined_vessels.json'
if not geo_path.exists():st.error(f'Missing GeoJSON: {geo_path}');st.stop()
try:geo=read_json(str(geo_path),geo_path.stat().st_mtime_ns)
except Exception as e:st.error(f'GeoJSON cannot be read: {e}');st.stop()
if geo.get('type')!='FeatureCollection':st.error('Expected a GeoJSON FeatureCollection');st.stop()
records=[]
if data_path.exists():
    try:
        raw=read_json(str(data_path),data_path.stat().st_mtime_ns)
        records=raw.get('vessels',[]) if isinstance(raw,dict) else raw
    except Exception as e:st.warning(f'AIS data unavailable: {e}')
else:st.warning('combined_vessels.json not found. The geographical map will still work.')
now=datetime.now(timezone.utc); vessels=[]
for v in records:
    try:
        lat=float(v.get('latitude'));lon=float(v.get('longitude'))
        if not (-90<=lat<=90 and -180<=lon<=180):continue
    except (ValueError,TypeError,AttributeError):continue
    d=parse_dt(v.get('last_seen'))
    age=(now-d).total_seconds()/60 if d else None
    fresh=age is not None and 0<=age<=30
    if not show_stored and not fresh:continue
    try:speed=float(v.get('speed_knots'))
    except (TypeError,ValueError):speed=None
    category,color=marker_class(speed)
    vessels.append({**v,'latitude':lat,'longitude':lon,'speed':speed,'fresh':fresh,'age':age,'category':category,'color':color})

fresh_count=sum(x['fresh'] for x in vessels)
sources=Counter(str(x.get('source') or 'Unknown') for x in vessels)
k1,k2,k3,k4=st.columns(4)
k1.metric('Displayed AIS Positions',len(vessels));k2.metric('Recent (≤30 min)',fresh_count)
k3.metric('AISStream',sources.get('aisstream',0));k4.metric('Open Waters',sources.get('openwaters',0))
if not fresh_count:st.info('No recent AIS positions found. Stored-position mode can show older records; restart your receivers and combiner for new data.')

mapcol,sidecol=st.columns([3.5,1.1],gap='medium')
with mapcol:
    st.markdown('<div class="section">Southeast Asia · AIS Vessel Tracking</div>',unsafe_allow_html=True)
    center,zoom=VIEWS[view]
    m=folium.Map(location=center,zoom_start=zoom,tiles='CartoDB dark_matter',control_scale=True,prefer_canvas=True,zoom_control=True)
    Fullscreen(position='topleft').add_to(m)
    if show_states:
        # Polygons are kept as polygons; no manually extracted paths, avoiding spiky coastlines.
        folium.GeoJson(geo,name='Malaysia states',style_function=lambda f:{'fillColor':'#0b6537','fillOpacity':0.29,'color':'#3cd778','weight':1.15,'opacity':0.82},highlight_function=lambda f:{'fillColor':'#16894a','fillOpacity':0.42,'color':'#b4fa48','weight':2.0}).add_to(m)
    if show_vessels:
        for v in vessels:
            name=html.escape(str(v.get('name') or 'Unknown vessel'))
            mmsi=html.escape(str(v.get('mmsi') or 'N/A'))
            source=html.escape(str(v.get('source') or 'Unknown'))
            seen=html.escape(str(v.get('last_seen') or 'Unknown'))
            speed='Unknown' if v['speed'] is None else f"{v['speed']:.1f} kn"
            status='RECENT' if v['fresh'] else 'STORED / STALE'
            content=(f'<div style="font:13px Arial;min-width:200px;color:#111"><b>{name}</b><hr>'
                     f'MMSI: {mmsi}<br>Speed: {speed}<br>Position: {v["latitude"]:.5f}, {v["longitude"]:.5f}<br>'
                     f'Category: {v["category"]}<br>Source: {source}<br>Observed: {seen}<br><b>{status}</b></div>')
            folium.CircleMarker([v['latitude'],v['longitude']],radius=3.1,color=v['color'],weight=0.7,opacity=0.9,fill=True,fill_color=v['color'],fill_opacity=0.95,tooltip=f'{name} · {v["category"]}',popup=folium.Popup(content,max_width=330)).add_to(m)
    if show_labels:
        for name,lat,lon in COUNTRY_LABELS+STATE_LABELS:
            is_country=(name,lat,lon) in COUNTRY_LABELS
            size=17 if is_country else 15
            if view=='Southeast Asia' and not is_country:size=12
            label=html.escape(name)
            folium.Marker([lat,lon],icon=folium.DivIcon(html=(
                f'<div style="display:inline-block;white-space:nowrap;transform:translate(-50%,-50%);'
                f'font:800 {size}px Arial,sans-serif;letter-spacing:{".8px" if is_country else "0"};'
                'color:#f5faff;text-shadow:0 2px 3px #00101b,0 0 6px #00101b;'
                f'pointer-events:none">{label}</div>'))).add_to(m)
    folium.LayerControl(collapsed=True).add_to(m)
    result=st_folium(m,height=660,use_container_width=True,key='sea_map_'+view,returned_objects=['last_object_clicked_popup'])
    st.caption('Map shading and labels are cartographic overlays. AIS markers are genuine stored observations; recent counts use a 30-minute freshness window. No simulated vessel positions.')
with sidecol:
    st.markdown('<div class="section">Selected Vessel</div>',unsafe_allow_html=True)
    if vessels:
        choices=sorted(range(len(vessels)),key=lambda i:str(vessels[i].get('name') or ''))
        chosen=st.selectbox('Vessel',choices,format_func=lambda i:f'{vessels[i].get("name") or "Unnamed"} · {vessels[i].get("mmsi") or "N/A"}')
        v=vessels[chosen]
        st.markdown(f'### {html.escape(str(v.get("name") or "Unnamed vessel"))}')
        st.caption('RECENT AIS' if v['fresh'] else 'STORED POSITION · MAY BE STALE')
        st.write('**MMSI:**',v.get('mmsi') or 'N/A')
        st.write('**Movement:**',v['category'])
        st.write('**Speed:**',f'{v["speed"]:.1f} kn' if v['speed'] is not None else 'Unknown')
        st.write('**Coordinates:**',f'{v["latitude"]:.5f}, {v["longitude"]:.5f}')
        st.write('**Source:**',v.get('source') or 'Unknown')
        st.write('**Last AIS:**',v.get('last_seen') or 'Unknown')
    else:st.info('No AIS vessel positions to display.')
    st.divider()
    st.markdown('#### Vessel legend')
    st.markdown('<div class="legend">🟢 Moving (&gt;5 kn)<br>🟡 Slow (0.5–5 kn)<br>🔴 Stationary (≤0.5 kn)<br>🟣 Unknown speed</div>',unsafe_allow_html=True)
    st.divider()
    st.markdown('#### Threat assessment')
    st.caption('No threat counts are inferred from vessel speed. Connect your validated rule-based threat module to display real alerts.')
    st.markdown('#### Data sources')
    st.write('AISStream:',sources.get('aisstream',0))
    st.write('Open Waters:',sources.get('openwaters',0))
    st.caption('Map does not imply AIS coverage across every Southeast Asian country.')
