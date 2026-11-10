import json
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd
import streamlit as st
import pydeck as pdk

ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title='SEA SENTINEL | Command Centre', page_icon='🚢', layout='wide', initial_sidebar_state='expanded')
st.markdown('''<style>
.stApp{background:#061525;color:#eaf6ff}section[data-testid="stSidebar"]{background:#071c2f;border-right:1px solid #174761}
.block-container{padding-top:1rem;padding-bottom:2rem;max-width:100%}
[data-testid="stMetric"]{background:#0b253b;border:1px solid #22607c;border-radius:12px;padding:13px}
[data-testid="stMetricValue"]{color:#c8ff00}h1,h2,h3{color:#f2f9ff}
div[data-testid="stVerticalBlockBorderWrapper"]>div{border-color:#1c607d!important}
</style>''', unsafe_allow_html=True)

@st.cache_data(ttl=20)
def load_vessels():
    path=ROOT/'combined_vessels.json'
    if not path.exists():return [],None
    data=json.loads(path.read_text(encoding='utf-8-sig'))
    return data.get('vessels',[]),data.get('updated_at')


@st.cache_data
def load_boundaries():
    path=ROOT/'malaysia_states.geojson'
    if not path.exists():return None
    return json.loads(path.read_text(encoding='utf-8-sig'))

REGIONS={'Malaysia':(4.3,109.1,4.1),'Peninsular Malaysia':(4.3,102.2,6.0),'Sabah':(5.5,117.2,6.4),'Sarawak':(2.8,112.5,6.0)}
STATE_LABELS=[('Perlis',6.44,100.19),('Kedah',6.0,100.55),('Pulau Pinang',5.35,100.26),('Perak',4.8,101.1),('Kelantan',5.55,102.15),('Terengganu',4.95,103.05),('Pahang',3.9,102.35),('Selangor',3.3,101.35),('N. Sembilan',2.73,102.15),('Melaka',2.25,102.27),('Johor',2.0,103.45),('Sabah',5.65,116.5),('Sarawak',2.8,113.2),('Kuala Lumpur',3.14,101.68)]
COUNTRY_LABELS=[('THAILAND',9.5,101.2),('INDONESIA',-0.7,110.5),('BRUNEI',4.6,114.8),('SINGAPORE',1.30,103.8),('VIETNAM',11.0,107.8),('PHILIPPINES',10.7,122.3)]

def timestamp(value):
    if not value:return None
    try:return datetime.fromisoformat(str(value).replace('Z','+00:00')).astimezone(timezone.utc)
    except (ValueError,TypeError):return None

def prepare(raw):
    rows=[];now=datetime.now(timezone.utc)
    for v in raw:
        try:
            lat=float(v['latitude']);lon=float(v['longitude'])
            if not(-90<=lat<=90 and -180<=lon<=180):continue
        except (ValueError,TypeError,KeyError):continue
        seen=timestamp(v.get('last_seen'))
        if seen is None or not(0<=(now-seen).total_seconds()<=1800):continue
        speed=v.get('speed_knots')
        try:speed=float(speed) if speed is not None else None
        except (ValueError,TypeError):speed=None
        movement='Moving' if speed is not None and speed>5 else ('Slow' if speed is not None and speed>0.5 else 'Stationary / Unknown')
        color={'Moving':[198,255,0,235],'Slow':[0,217,255,235],'Stationary / Unknown':[170,112,255,235]}[movement]
        rows.append(dict(name=str(v.get('name') or 'Unknown Vessel'),mmsi=str(v.get('mmsi') or 'Unknown'),latitude=lat,longitude=lon,speed_knots=speed,course=v.get('course'),source=str(v.get('source') or 'Unknown'),last_seen=str(v.get('last_seen') or ''),movement=movement,color=color,region=str(v.get('region') or 'Other')))
    return pd.DataFrame(rows)

with st.sidebar:
    st.title('🚢 SEA SENTINEL')
    st.caption('MARITIME INTELLIGENCE SYSTEM')
    st.divider()
    st.markdown('**Navigation**')
    st.markdown('🗺️  Live AIS Map')
    st.markdown('🚢  Vessel Explorer')
    st.markdown('🛡️  Threat Assessment')
    st.markdown('📊  Analytics')
    st.divider()
    region=st.selectbox('Monitoring region',list(REGIONS))
    show_labels=st.toggle('State and country labels',value=True)
    show_glow=st.toggle('Subtle boundary glow',value=True)
    show_stale=st.toggle('Show all stored positions (may be stale)',value=False)

raw,updated=load_vessels()
df=prepare(raw)
if show_stale:
    # Historical/stale mode explicitly separated from recent data.
    stale=[]
    for v in raw:
        try:
            la=float(v['latitude']);lo=float(v['longitude'])
            if not(-90<=la<=90 and -180<=lo<=180):continue
            speed=float(v['speed_knots']) if v.get('speed_knots') is not None else None
        except (KeyError,ValueError,TypeError):continue
        movement='Moving' if speed is not None and speed>5 else ('Slow' if speed is not None and speed>0.5 else 'Stationary / Unknown')
        stale.append(dict(name=str(v.get('name') or 'Unknown Vessel'),mmsi=str(v.get('mmsi') or 'Unknown'),latitude=la,longitude=lo,speed_knots=speed,source=str(v.get('source') or 'Unknown'),last_seen=str(v.get('last_seen') or ''),movement=movement,color={'Moving':[198,255,0,235],'Slow':[0,217,255,235],'Stationary / Unknown':[170,112,255,235]}[movement],region=str(v.get('region') or 'Other')))
    df=pd.DataFrame(stale)

st.title('SEA SENTINEL  ·  Maritime Command Centre')
st.caption('AIS vessel monitoring across Malaysia and surrounding waters')
a,b,c,d=st.columns(4)
a.metric('Recent vessels (30 min)',len(prepare(raw)))
b.metric('AISStream',int((df['source'].str.lower()=='aisstream').sum()) if not df.empty else 0)
c.metric('Open Waters',int((df['source'].str.lower()=='openwaters').sum()) if not df.empty else 0)
d.metric('Stored vessel records',len(raw))
if show_stale:st.warning('Displaying stored positions, including potentially stale AIS reports. These are not all live vessels.')
if df.empty:st.warning('No recent vessel positions found. Restart the receivers and combiner, or enable stored-position mode to inspect previous records.')

map_col,info_col=st.columns([3,1],gap='medium')
with map_col:
    st.subheader('Live AIS Vessel Tracking' if not show_stale else 'Stored AIS Vessel Positions')
    boundaries=load_boundaries()
    layers=[]
    if boundaries:
        if show_glow:
            layers.append(pdk.Layer('GeoJsonLayer',boundaries,filled=False,stroked=True,get_line_color=[0,204,255,28],get_line_width=3,line_width_units='pixels',pickable=False))
        layers.append(pdk.Layer('GeoJsonLayer',boundaries,filled=False,stroked=True,get_line_color=[30,210,255,190],get_line_width=1,line_width_units='pixels',pickable=False))
    if not df.empty:
        layers.append(pdk.Layer('ScatterplotLayer',df,get_position='[longitude, latitude]',get_fill_color='color',get_radius=3,radius_units='pixels',radius_min_pixels=3,radius_max_pixels=5,pickable=True,auto_highlight=True))
    if show_labels:
        labels=pd.DataFrame([{'name':n,'latitude':la,'longitude':lo} for n,la,lo in STATE_LABELS])
        layers.append(pdk.Layer('TextLayer',labels,get_position='[longitude, latitude]',get_text='name',get_size=17,size_units='pixels',get_color=[255,255,255,255],get_background_color=[3,15,29,200],background=True,get_text_anchor='middle',get_alignment_baseline='center',pickable=False))
        countries=pd.DataFrame([{'name':n,'latitude':la,'longitude':lo} for n,la,lo in COUNTRY_LABELS])
        layers.append(pdk.Layer('TextLayer',countries,get_position='[longitude, latitude]',get_text='name',get_size=19,size_units='pixels',get_color=[175,204,230,235],get_text_anchor='middle',get_alignment_baseline='center',pickable=False))
    lat,lon,zoom=REGIONS[region]
    deck=pdk.Deck(layers=layers,initial_view_state=pdk.ViewState(latitude=lat,longitude=lon,zoom=zoom,pitch=0),map_style='https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json',tooltip={'html':'<b>{name}</b><br/>MMSI: {mmsi}<br/>Speed: {speed_knots} kn<br/>Lat: {latitude}<br/>Lon: {longitude}<br/>Source: {source}<br/>Last AIS: {last_seen}','style':{'backgroundColor':'#071c30','color':'#ffffff','border':'1px solid #00d9ff'}})
    st.pydeck_chart(deck,height=610,use_container_width=True)
    st.caption('● Lime: moving (>5 kn)    ● Cyan: slow (0.5–5 kn)    ● Purple: stationary / unknown. Hover over a marker for vessel details.')
    st.caption('Boundaries: DOSM state GeoJSON. State label coordinates are approximate. Map shows only genuine AIS records.')
with info_col:
    st.subheader('Vessel Information')
    if df.empty:
        st.info('No vessel available for selection.')
    else:
        choices=[f"{r['name']} · {r['mmsi']}" for _,r in df.reset_index(drop=True).iterrows()]
        selected=st.selectbox('Select a vessel',range(len(choices)),format_func=lambda i:choices[i])
        v=df.reset_index(drop=True).iloc[selected]
        st.markdown(f"### {v['name']}")
        st.write('**MMSI:**',v['mmsi'])
        st.write('**Status:**',v['movement'])
        st.write('**Speed:**',f"{v['speed_knots']} kn" if pd.notna(v['speed_knots']) else 'Unknown')
        st.write('**Coordinates:**',f"{v['latitude']:.5f}, {v['longitude']:.5f}")
        st.write('**Source:**',v['source'])
        st.write('**Last AIS report:**',v['last_seen'])
    st.divider()
    st.subheader('Threat Alerts')
    st.info('Threat indicators are not shown until connected to validated threat-assessment rules. No alerts are inferred from speed alone.')
    st.subheader('Source Distribution')
    if not df.empty:
        st.bar_chart(df['source'].value_counts(),horizontal=True)

st.caption('Refresh the page after running AIS receivers and the combiner. This prototype uses map hover and a vessel selector; map-click selection is not yet wired.')
