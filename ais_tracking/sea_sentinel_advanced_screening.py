"""Evidence-limited AIS screening. No synthetic events or unverified zone claims."""
import json, math, sqlite3
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

BASE=Path(__file__).resolve().parent
DB=BASE/'ais_position_history.sqlite3'
ZONES=BASE/'verified_geofences.geojson'  # user-supplied, verified GeoJSON polygons

def _bearing(a,b,c,d):
    p1,p2=math.radians(a),math.radians(c); dl=math.radians(d-b)
    y=math.sin(dl)*math.cos(p2)
    x=math.cos(p1)*math.sin(p2)-math.sin(p1)*math.cos(p2)*math.cos(dl)
    return (math.degrees(math.atan2(y,x))+360)%360

def _distance_nm(a,b,c,d):
    p1,p2=math.radians(a),math.radians(c)
    dp=p2-p1; dl=math.radians(d-b)
    h=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 3440.065*2*math.asin(min(1,math.sqrt(h)))

def _point_in_poly(lon,lat,coords):
    inside=False
    for i in range(len(coords)):
        x1,y1=coords[i-1][:2]; x2,y2=coords[i][:2]
        if (y1>lat)!=(y2>lat) and lon<(x2-x1)*(lat-y1)/(y2-y1)+x1:
            inside=not inside
    return inside

def _zones():
    if not ZONES.exists(): return [],'Not configured: verified_geofences.geojson is missing'
    try:
        raw=json.loads(ZONES.read_text(encoding='utf-8'))
        zones=[]
        for f in raw.get('features',[]):
            geom=f.get('geometry') or {}; props=f.get('properties') or {}
            if props.get('verified') is not True: continue
            if geom.get('type')=='Polygon': polys=[geom['coordinates']]
            elif geom.get('type')=='MultiPolygon': polys=geom['coordinates']
            else: continue
            for p in polys:
                if p and len(p[0])>=3: zones.append((str(props.get('name','Verified zone')),p))
        return zones,('Active' if zones else 'No verified polygon zones configured')
    except (OSError,ValueError,TypeError,KeyError) as exc:
        return [],f'Invalid geofence file: {exc}'

def screen(df, advisory=15, elevated=25):
    """Return per-module counts, status and evidence-backed review rows."""
    names=['Speed anomalies','Route anomalies','Collision screening','Geofence checks','AIS reporting gaps']
    results={k:{'count':0,'status':'No fresh AIS data','details':''} for k in names}
    events=[]
    if df.empty:
        results['Geofence checks']['status']=_zones()[1]
        results['AIS reporting gaps']['status']='Coverage configuration required'
        return results,pd.DataFrame(events)
    now=datetime.now(timezone.utc)
    by_mmsi={str(r.get('mmsi')):r for _,r in df.iterrows()}
    for _,r in df.iterrows():
        speed=r.get('speed_knots')
        if pd.notna(speed) and 0<=float(speed)<=100 and float(speed)>=advisory:
            events.append(dict(mmsi=str(r.mmsi),name=str(r['name']),detection='Speed anomalies',
                detail=f'SOG {float(speed):.1f} kn; advisory {advisory:g} kn, elevated {elevated:g} kn',
                evidence='AIS reported SOG; vessel context not verified',observed=str(r.get('observed'))))
    results['Speed anomalies'].update(count=sum(e['detection']=='Speed anomalies' for e in events),status='Screened current AIS speed')

    # Route: 3 genuinely distinct historical points, two movement legs, reasonable temporal spacing.
    if DB.exists():
        try:
            with sqlite3.connect(DB,timeout=5) as conn:
                h=pd.read_sql_query('SELECT mmsi,observed,latitude,longitude FROM positions WHERE observed >= ? ORDER BY mmsi,observed DESC',conn,params=((now-pd.Timedelta(hours=6)).isoformat(),))
        except (sqlite3.Error,ValueError): h=pd.DataFrame()
    else: h=pd.DataFrame()
    if not h.empty:
        h['ts']=pd.to_datetime(h.observed,utc=True,errors='coerce')
        for m,group in h.groupby('mmsi'):
            if str(m) not in by_mmsi: continue
            g=group.dropna(subset=['ts']).sort_values('ts').drop_duplicates(subset=['latitude','longitude'],keep='last').tail(3)
            if len(g)<3: continue
            p=list(g.itertuples(index=False))
            t1=(p[1].ts-p[0].ts).total_seconds()/60; t2=(p[2].ts-p[1].ts).total_seconds()/60
            if not (2<=t1<=90 and 2<=t2<=90): continue
            d1=_distance_nm(p[0].latitude,p[0].longitude,p[1].latitude,p[1].longitude)
            d2=_distance_nm(p[1].latitude,p[1].longitude,p[2].latitude,p[2].longitude)
            if not (d1>=.15 and d2>=.15): continue
            b1=_bearing(p[0].latitude,p[0].longitude,p[1].latitude,p[1].longitude)
            b2=_bearing(p[1].latitude,p[1].longitude,p[2].latitude,p[2].longitude)
            turn=abs((b2-b1+180)%360-180)
            if turn>=70:
                r=by_mmsi[str(m)]
                events.append(dict(mmsi=str(m),name=str(r['name']),detection='Route anomalies',
                    detail=f'Observed track bearing change {turn:.0f}° across 3 positions',
                    evidence='Historical positions; possible manoeuvre, not confirmed hazard',observed=str(p[2].observed)))
        results['Route anomalies']['status']='Screened available position history'
    else: results['Route anomalies']['status']='Awaiting position history'
    results['Route anomalies']['count']=sum(e['detection']=='Route anomalies' for e in events)

    # CPA/TCPA in local tangent plane, course assumed true degrees, speed in knots.
    moving=[]
    for _,r in df.iterrows():
        try:
            v=float(r.speed_knots); course=float(r.course)
            if math.isfinite(v) and math.isfinite(course) and 0<=v<=60 and 0<=course<=360:
                moving.append(r)
        except (TypeError,ValueError,AttributeError): pass
    if len(moving)>=2:
        for i,a in enumerate(moving):
            for b in moving[i+1:]:
                if str(a.mmsi)==str(b.mmsi): continue
                if _distance_nm(a.latitude,a.longitude,b.latitude,b.longitude)>8: continue
                ta=a.get('observed'); tb=b.get('observed')
                if not hasattr(ta,'timestamp') or not hasattr(tb,'timestamp') or abs((ta-tb).total_seconds())>120: continue
                lat0=math.radians((float(a.latitude)+float(b.latitude))/2)
                rx=(float(b.longitude)-float(a.longitude))*60*math.cos(lat0)
                ry=(float(b.latitude)-float(a.latitude))*60
                ca,cb=math.radians(float(a.course)),math.radians(float(b.course))
                vx=float(b.speed_knots)*math.sin(cb)-float(a.speed_knots)*math.sin(ca)
                vy=float(b.speed_knots)*math.cos(cb)-float(a.speed_knots)*math.cos(ca)
                vv=vx*vx+vy*vy
                if vv<.01: continue
                tcpa=-(rx*vx+ry*vy)/vv*60
                if not (0<tcpa<=30): continue
                cx=rx+vx*tcpa/60; cy=ry+vy*tcpa/60
                cpa=math.hypot(cx,cy)
                if cpa<.5:
                    for r in (a,b):
                        events.append(dict(mmsi=str(r.mmsi),name=str(r['name']),detection='Collision screening',
                            detail=f'Pair {a.mmsi}/{b.mmsi}: CPA {cpa:.2f} NM, TCPA {tcpa:.1f} min',
                            evidence='Straight-line estimate from AIS SOG/COG; verify navigation context',observed=str(r.get('observed'))))
        results['Collision screening']['status']='CPA/TCPA screened for eligible pairs'
    else: results['Collision screening']['status']='Need ≥2 vessels with valid SOG/COG'
    results['Collision screening']['count']=len({e['mmsi'] for e in events if e['detection']=='Collision screening'})

    zones,zone_status=_zones()
    results['Geofence checks']['status']=zone_status
    for _,r in df.iterrows():
        for name,polys in zones:
            # GeoJSON: outer ring followed by optional holes
            if _point_in_poly(float(r.longitude),float(r.latitude),polys[0]) and not any(_point_in_poly(float(r.longitude),float(r.latitude),hole) for hole in polys[1:]):
                events.append(dict(mmsi=str(r.mmsi),name=str(r['name']),detection='Geofence checks',
                    detail=f'Position inside verified polygon: {name}',evidence='Geometric inclusion only; restrictions must be independently confirmed',observed=str(r.get('observed'))))
    results['Geofence checks']['count']=len({e['mmsi'] for e in events if e['detection']=='Geofence checks'})
    # AIS absence cannot be attributed to a vessel without receiver coverage and expected cadence.
    results['AIS reporting gaps'].update(count=0,status='Not enabled: receiver coverage/cadence unverified',details='0 does not mean no reporting gaps')
    return results,pd.DataFrame(events)
