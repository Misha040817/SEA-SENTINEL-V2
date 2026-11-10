import json
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd
import pydeck as pdk
import streamlit as st

st.set_page_config(page_title="SEA SENTINEL V2 | Live AIS Malaysia", page_icon="🌊", layout="wide")
st.markdown("""<style>
.stApp {background: #07121f; color: #e9f5ff}
[data-testid="stSidebar"] {background: #0b1d30}
[data-testid="stMetric"] {background:#112b40;border:1px solid #24506b;border-radius:12px;padding:12px}
</style>""", unsafe_allow_html=True)

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'vessels_live.json'
VIEWS = {
 'Malaysia': (4.2, 109.0, 4.3), 'Johor': (1.85, 103.65, 8.2),
 'Selangor / Port Klang': (3.0, 101.15, 8.8), 'Negeri Sembilan': (2.45, 101.75, 8.7),
 'Melaka': (2.2, 102.2, 8.8), 'Perak': (4.25, 100.6, 8.1),
 'Pulau Pinang': (5.38, 100.32, 9.4), 'Kedah': (6.0, 100.25, 8.5),
 'Perlis': (6.42, 100.16, 9.5), 'Kelantan': (6.15, 102.25, 8.5),
 'Terengganu': (5.05, 103.15, 8.0), 'Pahang': (3.75, 103.35, 7.9),
 'Sabah': (5.8, 116.6, 7.2), 'Sarawak': (2.8, 112.2, 6.7),
}
# Broad proximity rectangles for display only, NOT state or territorial boundaries.
ZONES = [
 ('Johor',1.0,2.55,102.45,104.7),
 ('Melaka',2.0,2.6,101.8,102.6),
 ('Negeri Sembilan',2.4,2.9,101.4,102.1),
 ('Selangor / Port Klang',2.65,3.8,100.6,101.7),
 ('Perak',3.7,5.05,99.7,101.25),
 ('Pulau Pinang',5.1,5.7,99.8,100.75),
 ('Kedah',5.7,6.45,99.2,100.9),
 ('Perlis',6.35,6.75,99.8,100.5),
 ('Pahang',2.6,4.25,102.7,105.1),
 ('Terengganu',4.15,5.85,102.5,105.1),
 ('Kelantan',5.75,7.0,101.8,104.6),
 ('Sabah',4.0,8.0,115.0,120.5),
 ('Sarawak',0.5,5.5,108.0,115.0),
]
def near_state(lat,lon):
    for name,s,n,w,e in ZONES:
        if s <= lat <= n and w <= lon <= e: return name
    return 'Other / offshore'

def read_data():
    try:
        payload = json.loads(DATA.read_text(encoding='utf-8'))
        records = payload.get('vessels', []) if isinstance(payload,dict) else payload
        updated = payload.get('updated_at') if isinstance(payload,dict) else None
        if not isinstance(records,list): records=[]
    except (OSError,ValueError,TypeError): records,updated=[],None
    df=pd.DataFrame([x for x in records if isinstance(x,dict)])
    if df.empty: return df,updated
    for c in ('latitude','longitude','speed_knots','course'):
        if c not in df: df[c]=None
        df[c]=pd.to_numeric(df[c],errors='coerce')
    df=df.dropna(subset=['latitude','longitude']).copy()
    df=df[df.latitude.between(-90,90)&df.longitude.between(-180,180)].copy()
    if df.empty: return df,updated
    for c in ('name','mmsi','last_seen'):
        if c not in df: df[c]=None
    df['name']=df['name'].fillna('Unknown').astype(str)
    df['mmsi']=df['mmsi'].fillna('Unknown').astype(str)
    df['nearby_state']=[near_state(a,b) for a,b in zip(df.latitude,df.longitude)]
    times=pd.to_datetime(df.last_seen,utc=True,errors='coerce')
    df['age_min']=(pd.Timestamp.now(tz='UTC')-times).dt.total_seconds()/60
    df['status']=df.age_min.apply(lambda a:'Recent' if pd.notna(a) and 0<=a<=30 else 'Older / unknown')
    df['color']=df.status.apply(lambda s:[0,195,255,230] if s=='Recent' else [135,145,155,190])
    df['reported']=times.dt.strftime('%Y-%m-%d %H:%M UTC').fillna('Unknown')
    return df.reset_index(drop=True),updated

st.title('🌊 SEA SENTINEL V2')
st.caption('REAL AIS POSITION REPORTS · MALAYSIA MARITIME VIEW')
state=st.sidebar.selectbox('Focus on Malaysia / state',list(VIEWS))
search=st.sidebar.text_input('Search vessel name or MMSI')
show_older=st.sidebar.checkbox('Show older / unknown reports',True)
st.sidebar.caption('Blue: AIS report ≤30 minutes old · Grey: older / unknown')
st.sidebar.caption('State labels indicate approximate nearby coasts, not jurisdiction.')

if 'focus_id' not in st.session_state: st.session_state.focus_id=None
if 'last_state' not in st.session_state: st.session_state.last_state=state
if state != st.session_state.last_state:
    st.session_state.focus_id=None
    st.session_state.last_state=state

@st.fragment(run_every='15s')
def show_map():
    df,updated=read_data()
    if df.empty:
        st.warning('No valid AIS positions saved. Check the receiver and vessels_live.json.')
        return
    visible=df if state=='Malaysia' else df[df.nearby_state==state]
    if search.strip():
        q=search.strip()
        visible=visible[visible.name.str.contains(q,case=False,regex=False)|visible.mmsi.str.contains(q,case=False,regex=False)]
    if not show_older: visible=visible[visible.status=='Recent']
    visible=visible.reset_index(drop=True)
    a,b,c=st.columns(3)
    a.metric('Saved AIS vessels',len(df))
    b.metric('Visible in selected area',len(visible))
    c.metric('Recent visible',int((visible.status=='Recent').sum()) if not visible.empty else 0)
    st.subheader('Vessel directory — select a row to locate its map marker')
    if not visible.empty:
        cols=['name','mmsi','nearby_state','speed_knots','status','reported']
        event=st.dataframe(visible[cols],hide_index=True,width='stretch',on_select='rerun',selection_mode='single-row',key='ais_select')
        if event.selection.rows:
            st.session_state.focus_id=str(visible.iloc[event.selection.rows[0]].mmsi)
        st.download_button('Export AIS CSV',visible.drop(columns=['color']).to_csv(index=False).encode('utf-8'),'sea_sentinel_ais.csv','text/csv')
    else:
        st.info('No AIS positions in this selection. This does not mean no ships are present.')
    focus=None
    if st.session_state.focus_id and not visible.empty:
        match=visible[visible.mmsi==st.session_state.focus_id]
        if not match.empty: focus=match.iloc[0]
    lat,lon,zoom=VIEWS[state]
    if focus is not None:
        lat,lon,zoom=float(focus.latitude),float(focus.longitude),12
        st.success(f"Focused vessel: {focus['name']} · {focus['nearby_state']} · {focus['reported']}")
    if st.button('Reset map focus'):
        st.session_state.focus_id=None
        st.rerun(scope='fragment')
    layers=[]
    boundary=ROOT/'malaysia_states.geojson'
    if boundary.exists():
        try:
            gj=json.loads(boundary.read_text(encoding='utf-8'))
            if gj.get('type') in ('FeatureCollection','Feature'):
                layers.append(pdk.Layer('GeoJsonLayer',data=gj,filled=False,stroked=True,get_line_color=[70,215,255,155],line_width_min_pixels=1))
        except (OSError,ValueError,TypeError): pass
    if not visible.empty:
        layers.append(pdk.Layer('ScatterplotLayer',data=visible,get_position='[longitude, latitude]',get_fill_color='color',get_radius=350,radius_min_pixels=5,radius_max_pixels=16,pickable=True,auto_highlight=True))
    if focus is not None:
        layers.append(pdk.Layer('ScatterplotLayer',data=[{'latitude':lat,'longitude':lon}],get_position='[longitude, latitude]',get_radius=600,radius_min_pixels=12,radius_max_pixels=20,get_fill_color=[255,192,35,240]))
    st.subheader(f'Real AIS vessel map — {state}')
    deck=pdk.Deck(layers=layers,initial_view_state=pdk.ViewState(latitude=lat,longitude=lon,zoom=zoom,pitch=0),map_style='https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json',tooltip={'html':'<b>{name}</b><br/>MMSI: {mmsi}<br/>Nearby: {nearby_state}<br/>Speed: {speed_knots} kn<br/>Last report: {reported}<br/>Status: {status}','style':{'backgroundColor':'#0a2336','color':'white'}})
    st.pydeck_chart(deck,width='stretch',height=580,key=f"ais_map_{state}_{st.session_state.focus_id or 'all'}")
    st.caption('Markers come from received AISStream reports, not the Roboflow image model. Nearby-state rectangles are approximate and do not represent maritime boundaries.')
    if updated: st.caption(f'Snapshot saved: {updated}')
show_map()