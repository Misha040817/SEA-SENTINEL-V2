import json
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd
import pydeck as pdk
import streamlit as st

st.set_page_config(page_title='SEA SENTINEL V2 | AIS', page_icon='🌊', layout='wide')
st.markdown('''<style>.stApp{background:linear-gradient(135deg,#06111f,#0b2437);color:#e6f4ff}[data-testid="stSidebar"]{background:#081927}div[data-testid="stMetric"]{background:#102a3e;border:1px solid #23516b;border-radius:12px;padding:12px}h1,h2,h3{color:#e7f7ff!important}</style>''',unsafe_allow_html=True)
DATA_FILE=Path(__file__).resolve().parent/'vessels_live.json'
# Approximate coastal monitoring sectors. Not official territorial or state boundaries.
SECTORS={
 'Johor / Singapore Strait':(1.55,103.75,9,(1.0,2.5,102.5,104.5)),
 'Melaka / Negeri Sembilan':(2.35,101.85,9,(1.7,2.9,100.8,102.7)),
 'Selangor / Port Klang':(3.0,101.15,9,(2.5,3.8,100.5,102.0)),
 'Perak / Lumut':(4.15,100.55,9,(3.6,5.0,99.6,101.4)),
 'Penang / Kedah':(5.45,100.25,9,(4.8,6.6,99.0,101.5)),
 'Kelantan / Kota Bharu':(6.15,102.4,9,(5.4,7.0,101.7,103.7)),
 'Terengganu / Kuala Terengganu':(5.3,103.25,9,(4.1,5.8,102.5,104.7)),
 'Pahang / Kuantan':(3.85,103.45,9,(2.6,4.4,102.6,104.8)),
 'Sarawak':(2.8,112.0,7,(0.5,5.5,108.0,115.5)),
 'Sabah':(5.8,116.3,7,(4.0,8.0,115.0,120.5)),
}
# Order avoids obvious overlap: most specific coastal sectors first.
ORDER=['Johor / Singapore Strait','Melaka / Negeri Sembilan','Selangor / Port Klang','Penang / Kedah','Perak / Lumut','Kelantan / Kota Bharu','Terengganu / Kuala Terengganu','Pahang / Kuantan','Sabah','Sarawak']
LANDMARKS=[
 ('Kota Kinabalu vicinity',6.0,116.08,.40),('Sandakan vicinity',5.84,118.12,.45),
 ('Kuching vicinity',1.55,110.35,.50),('Bintulu vicinity',3.17,113.04,.55),('Miri vicinity',4.4,113.99,.55),
 ('Port Klang vicinity',3.0,101.37,.40),('Penang Port vicinity',5.41,100.35,.40),
 ('Kota Bharu vicinity',6.13,102.24,.45),('Kuala Terengganu vicinity',5.33,103.14,.45),
 ('Kemaman vicinity',4.23,103.43,.45),('Kuantan vicinity',3.82,103.33,.45),
 ('Pasir Gudang vicinity',1.46,103.9,.18),('Tanjung Pelepas vicinity',1.36,103.55,.22),
 ('Singapore Strait vicinity',1.25,103.86,.48),('Melaka Strait vicinity',2.2,102.25,.40),
 ('Lumut vicinity',4.24,100.63,.35),('Langkawi vicinity',6.33,99.83,.45),
]
def sector_of(lat,lon):
 for key in ORDER:
  a,b,c,d=SECTORS[key][3]
  if a<=lat<=b and c<=lon<=d:return key
 return 'Other maritime area'
def area_of(lat,lon):
 # Nearest named reference within a limited radius; not a jurisdiction claim.
 import math
 best=None
 for name,a,b,r in LANDMARKS:
  distance=math.hypot(lat-a,(lon-b)*math.cos(math.radians(lat)))
  if distance<=r and (best is None or distance<best[0]):best=(distance,name)
 return best[1] if best else sector_of(lat,lon)+' vicinity'
def load_data():
 try:
  raw=json.loads(DATA_FILE.read_text(encoding='utf-8'))
  vessels=raw.get('vessels',[]) if isinstance(raw,dict) else raw
  updated=raw.get('updated_at') if isinstance(raw,dict) else None
 except (OSError,ValueError,TypeError):vessels,updated=[],None
 df=pd.DataFrame(vessels if isinstance(vessels,list) else [])
 if df.empty:return pd.DataFrame(),updated
 for c in ['latitude','longitude','speed_knots','course']:
  if c not in df:df[c]=None
  df[c]=pd.to_numeric(df[c],errors='coerce')
 df=df.dropna(subset=['latitude','longitude']).copy()
 df=df[df.latitude.between(-90,90)&df.longitude.between(-180,180)].copy()
 if df.empty:return df,updated
 for c in ['name','mmsi','last_seen']:
  if c not in df:df[c]='Unknown'
  df[c]=df[c].fillna('Unknown').astype(str)
 df['region']=[sector_of(a,b) for a,b in zip(df.latitude,df.longitude)]
 df['area_name']=[area_of(a,b) for a,b in zip(df.latitude,df.longitude)]
 df['movement']=df.speed_knots.apply(lambda x:'Moving' if pd.notna(x) and x>.5 else 'Stationary / unknown')
 df['vessel_key']=df.mmsi+' | '+df.name
 return df,updated

st.title('🌊 SEA SENTINEL V2')
st.caption('AIS / GPS TRACKING • MARITIME SITUATIONAL AWARENESS')
st.sidebar.title('Monitoring controls')
region=st.sidebar.selectbox('Coastal region',['All Malaysian Regions']+list(SECTORS),key='region_select')
query=st.sidebar.text_input('Search vessel name / MMSI')
movement=st.sidebar.selectbox('Movement',['All','Moving','Stationary / unknown'])
if st.sidebar.button('Refresh now'):st.rerun()
st.sidebar.caption('Area labels are approximate. No territorial-water determination.')

@st.fragment(run_every='15s')
def dashboard():
 df,updated=load_data()
 shown=df.copy()
 if not shown.empty:
  if region!='All Malaysian Regions':shown=shown[shown.region==region]
  if query.strip():shown=shown[shown.name.str.contains(query,case=False,regex=False)|shown.mmsi.str.contains(query,case=False,regex=False)]
  if movement!='All':shown=shown[shown.movement==movement]
  shown=shown.reset_index(drop=True)
 c1,c2,c3,c4=st.columns(4)
 c1.metric('Received positions',len(df))
 c2.metric('In selected view',len(shown))
 c3.metric('Moving',int((shown.movement=='Moving').sum()) if not shown.empty else 0)
 age='No snapshot'
 if updated:
  try:
   t=datetime.fromisoformat(str(updated).replace('Z','+00:00'))
   age=f'{max(0,int((datetime.now(timezone.utc)-t).total_seconds()))}s ago'
  except (ValueError,TypeError):age='Unknown'
 c4.metric('Snapshot age',age)
 # Single-page layout: clicking a name updates selected vessel and focuses the map below.
 st.subheader('Vessel directory — select a vessel to locate it')
 if shown.empty:
  st.info('No AIS reports match this area/filter. This does not mean no vessels are present.')
 else:
  display_cols=['name','mmsi','area_name','region','latitude','longitude','speed_knots','movement']
  event=st.dataframe(shown[display_cols],width='stretch',hide_index=True,on_select='rerun',selection_mode='single-row',key='vessel_directory')
  selected=event.selection.rows
  if selected:
   row=shown.iloc[selected[0]]
   st.session_state['focus_vessel']={'mmsi':str(row.mmsi),'name':str(row['name'])}
  st.download_button('Export displayed vessels (CSV)',shown.drop(columns=['vessel_key'],errors='ignore').to_csv(index=False).encode('utf-8'),file_name='sea_sentinel_vessels.csv',mime='text/csv')
 focus=st.session_state.get('focus_vessel')
 target=None
 if focus and not shown.empty:
  found=shown[shown.mmsi==focus['mmsi']]
  if not found.empty:target=found.iloc[0]
 if target is not None:
  lat,lon,zoom=float(target.latitude),float(target.longitude),12
  st.success(f"Map focused on {target['name']} (MMSI {target.mmsi}) — {target.area_name}")
 elif region in SECTORS:lat,lon,zoom=SECTORS[region][:3]
 else:lat,lon,zoom=4.5,109.0,4
 st.subheader('Interactive vessel map')
 if not shown.empty:
  dots=shown.copy()
  dots['marker_color']=[[255,198,60,245] if target is not None and str(r.mmsi)==str(target.mmsi) else [0,205,255,220] for _,r in dots.iterrows()]
 else:dots=shown
 deck=pdk.Deck(map_style='https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json',initial_view_state=pdk.ViewState(latitude=lat,longitude=lon,zoom=zoom,pitch=0),layers=[pdk.Layer('ScatterplotLayer',data=dots,get_position='[longitude, latitude]',get_radius=500,radius_min_pixels=6,radius_max_pixels=17,get_fill_color='marker_color',pickable=True)],tooltip={'html':'<b>{name}</b><br/>MMSI: {mmsi}<br/>Area: {area_name}<br/>Region: {region}<br/>Speed: {speed_knots} knots','style':{'backgroundColor':'#10283b','color':'white'}})
 st.pydeck_chart(deck,width='stretch',height=530,key=f"map_{region}_{focus['mmsi'] if target is not None else 'region'}")
 if target is not None:
  st.markdown('#### Selected vessel telemetry')
  st.write({'Vessel':target['name'],'MMSI':target.mmsi,'Approximate area':target.area_name,'Region':target.region,'Speed (knots)':None if pd.isna(target.speed_knots) else float(target.speed_knots),'Course':None if pd.isna(target.course) else float(target.course),'Last report':target.last_seen})
 if st.button('Clear vessel focus'):
  st.session_state.pop('focus_vessel',None)
  st.rerun()
 st.caption('Blue dots: reported AIS positions. Gold: selected vessel. Regional sectors and nearby area labels are approximate, not official maritime boundaries. AIS reception can be incomplete.')

dashboard()
