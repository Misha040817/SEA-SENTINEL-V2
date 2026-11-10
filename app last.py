import os
import json
import base64
import tempfile
import time
import cv2
from sea_sentinel_runtime import RoboflowRunner, WebcamProcessor, draw_boxes, encode_mp4_for_browser
from datetime import datetime
from io import BytesIO

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from PIL import Image, ImageDraw, ImageFont
from inference_sdk import InferenceHTTPClient, InferenceConfiguration
from threat_assessment_page import render_threat_assessment

st.set_page_config(page_title='SEA SENTINEL | Maritime Intelligence', page_icon='⚓', layout='wide', initial_sidebar_state='expanded')
WORKSPACE = 'misha-r'
WORKFLOW_ID = 'sea-sentinel-v2-vessel-detection-1793462158075'
MODEL_METRICS = {'mAP@50':82.4, 'Precision':87.4, 'Recall':74.4, 'F1':79.6}
CLASS_METRICS = pd.DataFrame({
    'Vessel Class':['cargo_ship','container_ship','fishing_boat','military_vessel','passenger_ferry','speedboat','tanker','yacht'],
    'Validation mAP@50':[88,96,49,74,90,76,86,99],
    'Test mAP@50':[57,75,61,87,82,63,82,99],
})
NAV = {
    'COMMAND CENTRE':['Overview','Image Detection','Video Detection','Live Detection','Detection Results'],
    'VESSEL INTELLIGENCE':['Vessel Directory','AIS / GPS Tracking','AI–AIS Data Fusion'],
    'ANALYSIS & MONITORING':['Analytics','Dataset Explorer','Alerts & Monitoring'],
    'SYSTEM & MANAGEMENT':['Reports & Evidence','Settings','System Information'],
}
ICONS = {'Overview':'▦','Image Detection':'▧','Detection Results':'▤','Live Detection':'◉','Video Detection':'▣','Vessel Directory':'≡','AIS / GPS Tracking':'⌖','AI–AIS Data Fusion':'⇄','Analytics':'▥','Dataset Explorer':'▤','Threat Assessment':'◇','Alerts & Monitoring':'△','Reports & Evidence':'▧','Settings':'⚙','System Information':'ⓘ'}
st.markdown('''<style>
:root { color-scheme: dark; }
html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
 color:#F5FCFF!important;
 background-color:#041321!important;
 background-image:radial-gradient(ellipse 72% 32% at 82% 12%,rgba(0,195,255,.17),transparent 78%),
 radial-gradient(ellipse 65% 28% at 12% 80%,rgba(0,155,210,.14),transparent 80%),
 linear-gradient(135deg,#04111F 0%,#08283E 52%,#04121F 100%)!important;
 background-attachment:fixed!important;
}
/* No grid or repeating patterns. Light comes only from soft ocean gradients. */
.stApp::before,.stApp::after,[data-testid="stAppViewContainer"]::before,[data-testid="stAppViewContainer"]::after {content:none!important;display:none!important;}
[data-testid="stHeader"] {background:rgba(4,17,30,.92)!important;}
[data-testid="stMainBlockContainer"] {padding-top:4.5rem!important;}
video {max-height:560px;object-fit:contain;background:#020b14;border-radius:12px;}
[data-testid="stImage"] img {object-fit:contain;max-height:680px;}

.block-container {max-width:1450px!important;padding:2.2rem 2.4rem 3rem!important;}
[data-testid="stSidebar"] {background:linear-gradient(170deg,#07192B,#0B2639 58%,#061522)!important;border-right:1px solid rgba(36,220,249,.5)!important;box-shadow:4px 0 24px rgba(0,210,255,.09)!important;}
[data-testid="stSidebar"] .brand {font-size:1.3rem;font-weight:850;letter-spacing:.10em;color:#FFFFFF!important;text-shadow:0 0 14px rgba(32,215,255,.32)!important;}
[data-testid="stSidebar"] .brand-sub {font-size:.67rem;letter-spacing:.13em;color:#8EE7F6!important;margin-top:.25rem;}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {color:#75DCEC!important;font-weight:750;}
h1,h2,h3,h4,h5,h6 {color:#F8FDFF!important;letter-spacing:-.02em;text-shadow:0 0 14px rgba(16,195,250,.1)!important;}
h1 {font-size:1.95rem!important;} h2 {font-size:1.4rem!important;} h3 {font-size:1.1rem!important;}
[data-testid="stWidgetLabel"],[data-testid="stWidgetLabel"] *,label,.stMarkdown p {color:#F0FAFF!important;opacity:1!important;}
[data-testid="stCaptionContainer"],[data-testid="stCaptionContainer"] * {color:#B5D8E7!important;opacity:1!important;}
[data-testid="stVerticalBlockBorderWrapper"] > div {border-color:#25718D!important;}
[data-testid="stMetric"] {background:linear-gradient(140deg,rgba(20,62,84,.92),rgba(9,31,52,.9))!important;border:1px solid rgba(40,217,247,.56)!important;border-top:2px solid rgba(85,233,255,.78)!important;border-radius:15px!important;padding:16px!important;box-shadow:0 0 17px rgba(13,199,244,.13),inset 0 1px 0 rgba(190,249,255,.12)!important;}
[data-testid="stMetricLabel"] * {color:#C2E6F1!important;} [data-testid="stMetricValue"] * {color:#FFC36B!important;}
.stButton > button {border-radius:10px!important;transition:background .15s ease,border-color .15s ease,box-shadow .15s ease!important;}
.stButton > button[kind="primary"] {background:linear-gradient(110deg,#F5A623,#FFCA58)!important;color:#091625!important;border:1px solid #FFD078!important;font-weight:800!important;box-shadow:0 0 15px rgba(255,173,39,.34)!important;}
.stButton > button[kind="primary"]:hover {background:#FFD278!important;box-shadow:0 0 23px rgba(255,177,40,.48)!important;}
.stButton > button[kind="secondary"] {background:rgba(13,46,66,.88)!important;color:#F5FDFF!important;border:1px solid rgba(43,185,220,.56)!important;}
.stButton > button[kind="secondary"]:hover {background:#16435B!important;border-color:#4DE7FF!important;box-shadow:0 0 13px rgba(40,211,250,.24)!important;}
[data-baseweb="select"] > div,[data-baseweb="input"] > div {background:#102D43!important;border-color:#3D91AC!important;color:#F8FAFC!important;}
[data-baseweb="select"] input,[data-baseweb="select"] span {color:#F8FAFC!important;}
[data-baseweb="tag"] {background:#14617B!important;border:1px solid #31A9C6!important;} [data-baseweb="tag"] span {color:#FFFFFF!important;}
[data-testid="stSlider"] [role="slider"] {background:#FFB62F!important;border:2px solid #FFE09B!important;box-shadow:0 0 11px rgba(255,174,40,.58)!important;}
[data-testid="stFileUploader"] {background:rgba(14,47,68,.86)!important;border:1px solid #2AACC9!important;border-radius:13px!important;box-shadow:0 0 13px rgba(16,202,242,.12)!important;}
[data-testid="stFileUploaderDropzone"] {background:rgba(14,45,66,.9)!important;border:1px dashed #45DFF9!important;border-radius:11px!important;}
[data-testid="stFileUploaderDropzone"] * {color:#F2FCFF!important;opacity:1!important;}
[data-testid="stFileUploaderDropzone"] button {background:#144A64!important;color:#FFFFFF!important;border:1px solid #4DCFE8!important;}
[data-testid="stAlert"] {background:rgba(20,62,86,.95)!important;border:1px solid #2C91B8!important;border-radius:11px!important;}
[data-testid="stAlert"] * {color:#F0FCFF!important;}
[data-testid="stDataFrame"] {border:1px solid #2A8AA8!important;border-radius:11px!important;}
.eyebrow {font-size:.7rem;letter-spacing:.12em;text-transform:uppercase;color:#80DFF0!important;margin-bottom:.5rem;}
.panel {background:linear-gradient(145deg,rgba(22,67,88,.86),rgba(9,35,55,.91))!important;border:1px solid rgba(59,218,245,.54)!important;border-radius:14px!important;padding:20px!important;box-shadow:0 0 16px rgba(13,196,241,.12),inset 0 1px 0 rgba(220,251,255,.12)!important;}
.muted {color:#BEDBE8!important;font-size:.9rem;}
.hud-banner {position:relative!important;overflow:visible!important;background:linear-gradient(110deg,rgba(20,64,85,.94),rgba(7,35,58,.92))!important;border:1px solid #42C8E4!important;border-left:4px solid #F6AE34!important;border-radius:14px!important;padding:23px 24px!important;margin:12px 0 22px!important;box-shadow:0 0 18px rgba(20,204,245,.20),inset 0 1px 0 rgba(203,250,255,.2)!important;}
.hud-banner::before,.hud-banner::after {display:none!important;content:none!important;}
.hud-kicker,.section-cap {color:#FFC46D!important;font-size:.68rem;font-weight:750;letter-spacing:.10em;}
.hud-title {color:#FFFFFF!important;font-size:1.75rem!important;font-weight:850;letter-spacing:.02em;margin:6px 0;line-height:1.25;text-shadow:0 0 15px rgba(51,214,251,.28)!important;}
.hud-desc {display:none!important;}
.hud-divider {height:1px;background:linear-gradient(90deg,rgba(39,222,253,.7),transparent);margin:10px 0 22px;}
hr {border-color:#2D6D85!important;}
</style>''', unsafe_allow_html=True)

for k, default in {'records':[], 'runs':[], 'latest_annotated':None,'latest_original':None,'latest_predictions':[], 'confidence':0.40,'alerts':[], 'last_run':None, 'video_result':None, 'video_records':[], 'video_last_name':None}.items():
    if k not in st.session_state:
        st.session_state[k] = default

@st.cache_resource(show_spinner=False)
def roboflow_client(key):
    client = InferenceHTTPClient(api_url='https://serverless.roboflow.com',api_key=key)
    return client.configure(InferenceConfiguration(api_key_transport='header'))

def api_key():
    try:
        return st.secrets.get('ROBOFLOW_API_KEY')
    except Exception:
        return None

def predictions_from(output):
    for field in ('detections_json','predictions'):
        value=output.get(field)
        if isinstance(value,list):
            return value
        if isinstance(value,dict) and isinstance(value.get('predictions'),list):
            return value['predictions']
    return []

def annotated_from(output):
    value=output.get('output_image')
    if isinstance(value,dict):
        value=value.get('value')
    if isinstance(value,str):
        try:
            return base64.b64decode(value.split(',',1)[-1])
        except (ValueError,base64.binascii.Error):
            return None
    return None

def infer_image(img, threshold):
    key=api_key()
    if not key:
        raise RuntimeError('ROBOFLOW_API_KEY is missing from .streamlit/secrets.toml')
    path=None
    try:
        with tempfile.NamedTemporaryFile(suffix='.jpg',delete=False) as tmp:
            path=tmp.name
        img.convert('RGB').save(path,format='JPEG')
        response=roboflow_client(key).run_workflow(
            workspace_name=WORKSPACE,workflow_id=WORKFLOW_ID,
            images={'image':path},parameters={'confidence_threshold':threshold},use_cache=False)
        output=response[0] if isinstance(response,list) and response else response
        if not isinstance(output,dict):
            raise ValueError('Unexpected Roboflow response format')
        return output
    finally:
        if path and os.path.exists(path):
            try: os.remove(path)
            except OSError: pass

CLASS_COLORS = {
    'cargo_ship':'#2ECC71','container_ship':'#3B82F6','fishing_boat':'#F59E0B',
    'military_vessel':'#A78BFA','passenger_ferry':'#06B6D4',
    'speedboat':'#F472B6','tanker':'#EF4444','yacht':'#D4B66A'
}

def normalized_class(value):
    return str(value or 'unknown').strip().lower().replace(' ', '_').replace('-', '_')

def filtered_predictions(preds, classes, threshold):
    return [p for p in preds if isinstance(p,dict) and normalized_class(p.get('class')) in classes
            and float(p.get('confidence') or 0) >= threshold]

def local_annotation(img, preds, thickness=3, text_scale=0.7):
    """Draw class-coloured boxes from Roboflow centre-based x/y/width/height coordinates."""
    result=img.convert('RGB').copy()
    draw=ImageDraw.Draw(result)
    w,h=result.size
    try:
        font=ImageFont.truetype('arial.ttf',max(12,int(22*text_scale)))
    except OSError:
        font=ImageFont.load_default()
    count=0
    for p in preds:
        try:
            x,y,bw,bh=[float(p[k]) for k in ('x','y','width','height')]
            if bw<=0 or bh<=0: continue
            # Roboflow standard bounding boxes are centre-based, in image pixels.
            x1=max(0,min(w-1,int(x-bw/2))); y1=max(0,min(h-1,int(y-bh/2)))
            x2=max(0,min(w-1,int(x+bw/2))); y2=max(0,min(h-1,int(y+bh/2)))
            if x2<=x1 or y2<=y1: continue
            name=normalized_class(p.get('class'))
            color=CLASS_COLORS.get(name,'#38BDF8')
            draw.rectangle((x1,y1,x2,y2),outline=color,width=thickness)
            label=f"{name.replace('_',' ').upper()} | {float(p.get('confidence') or 0):.1%}"
            bb=draw.textbbox((0,0),label,font=font)
            tw,th=bb[2]-bb[0],bb[3]-bb[1]
            label_x=min(x1,max(0,w-tw-12))
            label_y=y1-th-10 if y1>=th+10 else min(h-th-8,y1+3)
            draw.rectangle((label_x,label_y,label_x+tw+10,label_y+th+7),fill=color)
            # Dark text on light boxes, white on darker ones.
            text_color='#081521' if name in ('fishing_boat','cargo_ship','passenger_ferry','yacht') else '#FFFFFF'
            draw.text((label_x+5,label_y+3),label,fill=text_color,font=font)
            count+=1
        except (ValueError,TypeError,KeyError):
            continue
    buffer=BytesIO();result.save(buffer,format='PNG')
    return buffer.getvalue(),count

def records_df():
    cols=['Timestamp','Run ID','Image','Vessel Class','Confidence','Detection ID']
    return pd.DataFrame(st.session_state.records,columns=cols)

def save_run(output, img, filename):
    preds=predictions_from(output)
    annotated=annotated_from(output)
    timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    run_id=len(st.session_state.runs)+1
    for p in preds:
        if not isinstance(p,dict):
            continue
        st.session_state.records.append({'Timestamp':timestamp,'Run ID':run_id,'Image':filename,
            'Vessel Class':str(p.get('class','Unknown')),
            'Confidence':float(p.get('confidence') or 0),
            'Detection ID':str(p.get('detection_id',''))})
    st.session_state.runs.append({'Run ID':run_id,'Timestamp':timestamp,'Image':filename,'Detections':len(preds)})
    st.session_state.latest_annotated=annotated
    st.session_state.latest_original=img.copy()
    st.session_state.latest_predictions=preds
    st.session_state.last_run={'timestamp':timestamp,'filename':filename,'count':len(preds)}
    return preds,annotated

def heading(title,subtitle=None):
    st.markdown(f'<div class="eyebrow">SEA SENTINEL / {title.upper()}</div>',unsafe_allow_html=True)
    st.title(title)
    if subtitle: st.caption(subtitle)

def unavailable(feature,detail):
    st.info(f'{feature} is not connected yet. {detail}')

def styled_plot(fig):
    fig.update_layout(template='plotly_dark',paper_bgcolor='#162235',plot_bgcolor='#162235',
        font_color='#DCE7EF',margin=dict(l=18,r=18,t=55,b=20),
        legend=dict(bgcolor='rgba(0,0,0,0)'))
    st.plotly_chart(fig,use_container_width=True)

with st.sidebar:
    st.markdown('<div class="brand">SEA SENTINEL</div><div class="brand-sub">MARITIME INTELLIGENCE PLATFORM</div>',unsafe_allow_html=True)
    st.divider()
    if 'page' not in st.session_state: st.session_state.page='Overview'
    for group,items in NAV.items():
        st.caption(group)
        for name in items:
            if st.button(f'{ICONS[name]}   {name}',key='nav_'+name,use_container_width=True,
                         type='primary' if st.session_state.page==name else 'secondary'):
                st.session_state.page=name
                st.rerun()
    st.divider()
    st.caption('SYSTEM CONNECTIONS')
    st.write('Roboflow: '+('API key configured' if api_key() else 'API key missing'))
    st.caption('AIS: Not connected · Video inference: available on Video Detection page')
    st.caption('Session data only · No persistent storage')

page=st.session_state.page
df=records_df()
run_count=len(st.session_state.runs)

if page=='Overview':
    st.markdown('<div class="hud-banner"><div class="hud-kicker">MARITIME INTELLIGENCE / COMMAND CENTRE</div><div class="hud-title">SEA SENTINEL</div></div><div class="hud-divider"></div>',unsafe_allow_html=True)
    st.caption('Operational snapshot · current Streamlit session only · no simulated live vessel data')
    a,b,c,d=st.columns(4)
    a.metric('Detection Runs',run_count)
    b.metric('Vessel Observations',len(df))
    c.metric('Observed Classes',df['Vessel Class'].nunique() if not df.empty else 0)
    d.metric('AIS Feed','Not connected')
    st.divider()
    left,right=st.columns([1.65,1],gap='large')
    with left:
        st.subheader('Latest Visual Observation')
        if st.session_state.latest_annotated:
            st.image(st.session_state.latest_annotated,use_container_width=True)
        elif st.session_state.latest_original:
            st.image(st.session_state.latest_original,use_container_width=True)
        else:
            st.info('No observations yet. Open Image Detection to analyse a vessel image.')
    with right:
        st.subheader('Operations Status')
        st.write('**AI inference:** '+('Ready for request' if api_key() else 'API key required'))
        st.write('**Video inference:** Available · Roboflow workflow')
        st.write('**AIS/GPS tracking:** Not connected')
        st.write('**Local evidence database:** Not configured')
        st.divider()
        st.subheader('Most Recent Run')
        if st.session_state.last_run:
            for key,val in st.session_state.last_run.items(): st.write(f'**{key.title()}:** {val}')
        else: st.caption('No run recorded in this session.')
    st.divider()
    st.subheader('Recent Activity')
    if st.session_state.runs:
        st.dataframe(pd.DataFrame(st.session_state.runs).tail(8).iloc[::-1],hide_index=True,use_container_width=True)
    else: st.caption('No recent activity.')

elif page=='Image Detection':
    heading('Image Detection')
    controls,workspace=st.columns([1,2.05],gap='large')
    with controls:
        st.subheader('Detection Configuration')
        selected=st.multiselect('Vessel classes',list(CLASS_COLORS),default=list(CLASS_COLORS),
            format_func=lambda x:x.replace('_',' ').title(),key='vessel_class_filter')
        threshold=st.slider('Confidence threshold',0.10,0.95,0.40,0.05,key='image_confidence')
        iou=st.slider('IoU threshold (reference)',0.10,0.90,0.30,0.05,
            help='Not sent to Roboflow. The workflow must expose an IoU input before it can change NMS.')
        thickness=st.slider('Bounding box thickness',1,8,3)
        text_scale=st.slider('Text scale',0.4,1.5,0.7,0.1)
        st.caption('IoU is shown for configuration planning; it does not currently change model inference.')
        st.markdown('#### Result Display')
        display_mode=st.radio('Display mode', ['Annotated image with bounding boxes','Original image','Side-by-side comparison'],
            label_visibility='collapsed')
    with workspace:
        st.subheader('Detection Workspace')
        upload=st.file_uploader('Upload a maritime image',type=['jpg','jpeg','png'],key='image_upload')
        image=Image.open(upload).convert('RGB') if upload else None
        if image is not None:
            st.image(image,caption='Image ready for inference',use_container_width=True)
        else:
            st.info('Upload an image to begin. Predictions will be generated by the connected Roboflow workflow.')
        run=st.button('Run Vessel Detection',type='primary',disabled=image is None or not selected,use_container_width=True)
        st.caption('Requires internet access and a valid Roboflow API key.')
    if run and image is not None:
        try:
            with st.spinner('Analysing vessel image...'):
                output=infer_image(image,threshold)
                preds,provider_image=save_run(output,image,upload.name)
                st.session_state['latest_config']={'classes':selected,'confidence':threshold,'iou_reference':iou,
                    'thickness':thickness,'text_scale':text_scale}
            st.success(f'Inference complete: {len(preds)} raw predictions returned. Results below apply your class filter.')
        except Exception as exc:
            st.error(f'Inference failed: {exc}')
    if st.session_state.latest_original is not None and st.session_state.last_run:
        st.divider()
        st.subheader('Detection Results')
        all_preds=st.session_state.latest_predictions
        visible=filtered_predictions(all_preds,selected,threshold)
        annotated,drawn=local_annotation(st.session_state.latest_original,visible,thickness,text_scale)
        if drawn!=len(visible):
            st.warning('Some predictions lack usable bounding-box coordinates; those boxes could not be drawn.')
        a,b,c=st.columns(3)
        a.metric('Filtered Vessel Detections',len(visible))
        b.metric('Highest Confidence',f"{max(float(p.get('confidence') or 0) for p in visible):.1%}" if visible else '—')
        c.metric('Vessel Classes',len(set(normalized_class(p.get('class')) for p in visible)))
        if display_mode=='Original image':
            st.image(st.session_state.latest_original,caption='Original image',use_container_width=True)
        elif display_mode=='Side-by-side comparison':
            before,after=st.columns(2)
            with before: st.image(st.session_state.latest_original,caption='Original',use_container_width=True)
            with after: st.image(annotated,caption='Class-coloured annotations',use_container_width=True)
        else:
            st.image(annotated,caption='Class-coloured annotations',use_container_width=True)
        st.download_button('Download annotated PNG',annotated,'sea_sentinel_detection.png','image/png')
        if visible:
            view=pd.DataFrame([{'Vessel Class':p.get('class'),'Confidence':round(float(p.get('confidence') or 0)*100,1),
                'X':p.get('x'),'Y':p.get('y'),'Width':p.get('width'),'Height':p.get('height')} for p in visible])
            st.dataframe(view,use_container_width=True,hide_index=True)
        else: st.info('No detections match the current filters. Try selecting more classes or lowering confidence.')
        st.caption('The most recent image is retained for this session. Changing filters redraws annotations locally; rerun inference to apply a different model threshold.')

elif page=='Detection Results':
    heading('Detection Results','Review actual inference observations from the current session')
    if df.empty:
        st.info('No image detection records yet. Run Image Detection to populate this page. Video results are available under Video Detection.')
    else:
        classes=sorted(df['Vessel Class'].dropna().unique().tolist())
        choice=st.multiselect('Filter vessel class',classes,default=classes)
        result_df=df[df['Vessel Class'].isin(choice)]
        a,b,c=st.columns(3)
        a.metric('Observations',len(result_df))
        b.metric('Detection Runs',run_count)
        c.metric('Classes',result_df['Vessel Class'].nunique())
        st.dataframe(result_df.iloc[::-1],use_container_width=True,hide_index=True)
        st.download_button('Export filtered results (CSV)',result_df.to_csv(index=False).encode('utf-8'),
            'sea_sentinel_results.csv','text/csv')
        if st.session_state.latest_annotated:
            st.subheader('Latest Provider Annotation')
            st.image(st.session_state.latest_annotated,use_container_width=True)
        st.caption('These are detection observations, not verified unique vessel identities. Records reset with the session.')

elif page=='Live Detection':
    heading('Live Detection','Continuous browser webcam feed with asynchronous Roboflow vessel detection')
    try:
        from streamlit_webrtc import webrtc_streamer, WebRtcMode
        import av
    except ImportError:
        st.error('Live webcam support is missing. Install streamlit-webrtc and av using the project requirements file.')
    else:
        st.info('Click START below and allow browser camera access. The webcam continues while Roboflow processes sampled frames. Camera access generally requires localhost or HTTPS.')
        left,right=st.columns([1,2.1],gap='large')
        with left:
            st.subheader('Camera Configuration')
            live_classes=st.multiselect('Detect classes',list(CLASS_COLORS),default=list(CLASS_COLORS),key='live_classes')
            live_conf=st.slider('Confidence',.10,.95,.40,.05,key='live_conf')
            live_n=st.number_input('Infer every Nth frame',1,30,3,key='live_n')
            live_interval=st.slider('Minimum seconds between cloud requests',.2,5.0,.8,.2,key='live_interval')
            st.caption('Frames stay live between inference calls. Boxes from the latest completed request are cached and may lag behind moving vessels.')
            if not api_key(): st.error('Set ROBOFLOW_API_KEY in .streamlit/secrets.toml before starting.')
        with right:
            st.subheader('Live Vessel Surveillance')
            if api_key() and live_classes:
                runner=RoboflowRunner(api_key(),WORKSPACE,WORKFLOW_ID)
                processor=WebcamProcessor(runner,live_conf,live_classes,live_n,live_interval)
                webrtc_streamer(
                    key='sea-sentinel-live',mode=WebRtcMode.SENDRECV,
                    video_frame_callback=processor.recv,
                    media_stream_constraints={'video':{'width':{'ideal':960},'height':{'ideal':540}},'audio':False},
                    async_processing=True)
            else:
                st.warning('Configure the Roboflow API key and select at least one vessel class.')
        st.caption('Live results are visual observations only. Cloud latency and network speed affect box freshness; the feed itself remains continuous.')

elif page=='Video Detection':
    heading('Video Detection','Upload footage, analyse selected frames and export an annotated video')
    controls,workspace=st.columns([1,2.1],gap='large')
    with controls:
        st.subheader('Processing Configuration')
        video_classes=st.multiselect('Vessel classes',list(CLASS_COLORS),default=list(CLASS_COLORS),key='video_classes')
        video_conf=st.slider('Confidence threshold',.10,.95,.40,.05,key='video_conf')
        video_n=st.number_input('Process every Nth frame',min_value=1,max_value=120,value=3,step=1,key='video_n',
            help='N=1 requests new predictions for every frame. N>1 reuses the latest boxes between sampled frames.')
        max_frames=st.number_input('Maximum frames to process (0 = full video)',min_value=0,max_value=500000,value=0,step=100)
        st.caption('Cloud inference may be slow and consume API credits. Start with a short video and N=3.')
    with workspace:
        st.subheader('Video Workspace')
        video=st.file_uploader('Upload maritime footage',type=['mp4','mov','avi','mkv'],key='video_upload')
        if video is not None:
            st.video(video)
            st.caption('Original uploaded video · no inference has been applied to this preview.')
        else:
            st.info('Upload a video to start analysing vessels.')
        analyse=st.button('Analyse Video',type='primary',disabled=video is None or not video_classes or not api_key(),use_container_width=True)
        if not api_key(): st.warning('ROBOFLOW_API_KEY is required for video analysis.')
    if analyse and video is not None:
        input_path=output_path=None
        cap=writer=None
        try:
            with tempfile.NamedTemporaryFile(suffix=os.path.splitext(video.name)[1] or '.mp4',delete=False) as tmp:
                input_path=tmp.name
                tmp.write(video.getbuffer())
            cap=cv2.VideoCapture(input_path)
            if not cap.isOpened(): raise RuntimeError('OpenCV could not open this video. Try an MP4 encoded with H.264.')
            fps=cap.get(cv2.CAP_PROP_FPS)
            if fps<=0 or fps>240: fps=25.0
            width=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)); height=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            if width<1 or height<1: raise RuntimeError('Video dimensions could not be read.')
            total=int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            limit=min(total,max_frames) if max_frames and total else (max_frames or total)
            with tempfile.NamedTemporaryFile(suffix='.mp4',delete=False) as tmp: output_path=tmp.name
            writer=cv2.VideoWriter(output_path,cv2.VideoWriter_fourcc(*'mp4v'),fps,(width,height))
            if not writer.isOpened(): raise RuntimeError('Unable to create output video. Check OpenCV codec support.')
            runner=RoboflowRunner(api_key(),WORKSPACE,WORKFLOW_ID)
            progress=st.progress(0,text='Preparing video analysis...')
            preview=st.empty(); status=st.empty()
            index=0; calls=0; last=[]; rows=[]; best=[]; error_count=0
            while True:
                if limit and index>=limit: break
                ok,frame=cap.read()
                if not ok: break
                sampled=index%int(video_n)==0
                if sampled:
                    try:
                        last=runner.infer(frame,video_conf)
                        calls+=1
                        _,visible=draw_boxes(frame,last,set(video_classes),video_conf)
                        for p in visible:
                            row={'Frame':index+1,'Time (s)':round(index/fps,2),
                                 'Vessel Class':str(p.get('class','Unknown')),
                                 'Confidence':round(float(p.get('confidence') or 0),4),
                                 'X':p.get('x'),'Y':p.get('y'),'Width':p.get('width'),'Height':p.get('height')}
                            rows.append(row)
                    except Exception as exc:
                        error_count+=1
                        last=[]
                        if error_count>=3: raise RuntimeError(f'Roboflow inference failed repeatedly: {exc}') from exc
                annotated,_=draw_boxes(frame,last,set(video_classes),video_conf,stale=not sampled and bool(last))
                writer.write(annotated)
                index+=1
                if index==1 or index%max(1,round(fps))==0:
                    small=cv2.resize(annotated,(min(width,800),max(1,round(height*min(width,800)/width))))
                    preview.image(cv2.cvtColor(small,cv2.COLOR_BGR2RGB),caption='Processing preview (updates during analysis)',use_container_width=True)
                    status.caption(f'Processed {index:,} frames · {calls:,} Roboflow requests · {len(rows):,} sampled detections')
                    if limit: progress.progress(min(1.0,index/limit),text=f'Analysing frame {index:,} of {limit:,}')
            writer.release(); writer=None
            if index==0: raise RuntimeError('The uploaded video contains no readable frames.')
            output_bytes,web_compatible=encode_mp4_for_browser(output_path)
            st.session_state.video_result={'video':output_bytes,'web_compatible':web_compatible,'frames':index,'fps':fps,
                                           'requests':calls,'detections':len(rows),'errors':error_count,'filename':video.name}
            st.session_state.video_records=rows
            st.session_state.video_last_name=video.name
            progress.progress(1.0,text='Video analysis completed')
            preview.empty();status.empty()
            st.success(f'Analysed {index:,} frames and recorded {len(rows):,} detections on sampled frames.')
        except Exception as exc:
            st.error(f'Video processing failed: {exc}')
        finally:
            if cap is not None: cap.release()
            if writer is not None: writer.release()
            for path in (input_path,output_path):
                if path and os.path.exists(path):
                    try: os.remove(path)
                    except OSError: pass
    result=st.session_state.video_result
    if result is not None:
        st.divider()
        st.subheader('Video Analysis Results')
        a,b,c,d=st.columns(4)
        a.metric('Frames processed',f"{result['frames']:,}")
        b.metric('Inference requests',f"{result['requests']:,}")
        c.metric('Sampled detections',f"{result['detections']:,}")
        d.metric('Video duration',f"{result['frames']/result['fps']:.1f}s")
        st.caption('Detections are observations from sampled frames, not unique vessel counts.')
        if result['web_compatible']:
            st.subheader('Analysed Video · Bounding Boxes')
            st.video(result['video'],format='video/mp4')
        else:
            st.info('The annotated MP4 was created, but H.264 conversion was unavailable. Download it to play in a compatible media player, or install FFmpeg to enable browser playback.')
        st.download_button('Download Analysed Video (MP4)',result['video'],'sea_sentinel_analysed.mp4','video/mp4',type='primary')
        video_df=pd.DataFrame(st.session_state.video_records)
        if not video_df.empty:
            st.subheader('Highest-Confidence Predictions')
            st.dataframe(video_df.sort_values('Confidence',ascending=False).head(20),hide_index=True,use_container_width=True)
            st.subheader('Detected Vessel Classes')
            counts=video_df['Vessel Class'].value_counts().rename_axis('Vessel Class').reset_index(name='Detections')
            st.dataframe(counts,hide_index=True,use_container_width=True)
            st.download_button('Download Detection Analysis (CSV)',video_df.to_csv(index=False).encode('utf-8'),
                               'sea_sentinel_video_detections.csv','text/csv')
        else:
            st.info('No vessel detections met the selected confidence and class filters.')
elif page=='Vessel Directory':
    heading('Vessel Directory','Searchable visual observations · these are not confirmed AIS vessel identities')
    if df.empty: st.info('No detected vessels in the current session.')
    else:
        query=st.text_input('Search vessel class, image or detection ID')
        display=df.copy()
        if query:
            display=display[display.astype(str).apply(lambda c:c.str.contains(query,case=False,regex=False)).any(axis=1)]
        st.dataframe(display,use_container_width=True,hide_index=True)
        st.caption('An AI detection does not establish vessel name, MMSI or GPS coordinates.')

elif page=='AIS / GPS Tracking':
    heading('AIS / GPS Tracking','Vessel positioning, movement assessment and AIS alerts in one workspace')
    st.caption('Live AIS provider not connected. The assessment tab currently supports recorded AIS CSV files.')
    ais_tab, threat_tab, history_tab = st.tabs(['Vessel Map & Telemetry','Threat Assessment','AIS Alerts & History'])
    with ais_tab:
        a,b,c=st.columns(3)
        a.metric('AIS Provider','Not connected')
        b.metric('Live AIS Tracks','—')
        c.metric('Position Updates','—')
        st.divider()
        left,right=st.columns([2,1],gap='large')
        with left:
            unavailable('Live vessel map','Connect an AIS provider or import geolocated tracks before displaying real vessel positions.')
        with right:
            st.subheader('Telemetry Inspector')
            for field in ['MMSI','Vessel name','Latitude / Longitude','Speed over ground','Course over ground','Heading']:
                st.write(f'**{field}:** Awaiting AIS data')
    with threat_tab:
        st.caption('Rule-based operational risk assessment from AIS records; not a confirmed security-threat detector.')
        render_threat_assessment()
    with history_tab:
        st.subheader('AIS Alerts & History')
        st.info('Live AIS alerts and persistent history will appear here after AIS data ingestion and storage are connected.')
        st.caption('CSV assessments are available in the Threat Assessment tab. They are not live AIS alerts.')

elif page=='AI–AIS Data Fusion':
    heading('AI–AIS Data Fusion','Correlate visual detections with vessel positioning only when evidence supports a match')
    a,b,c=st.columns(3)
    a.metric('Visual Observations',len(df))
    b.metric('AIS Tracks','Unavailable')
    c.metric('Verified Matches','—')
    st.divider()
    unavailable('Matching engine','Requires time-aligned AIS tracks and calibrated camera location/geometry. A visual class alone cannot determine MMSI.')

elif page=='Analytics':
    heading('Analytics','Evaluation metrics and actual session observations, kept separate')
    tab1,tab2,tab3=st.tabs(['Model Evaluation','Class Performance','Session Detection Analytics'])
    with tab1:
        st.subheader('Roboflow Validation Set')
        a,b,c,d=st.columns(4)
        for col,(name,value) in zip((a,b,c,d),MODEL_METRICS.items()): col.metric(name,f'{value:.1f}%')
        st.caption('Reference values from your Roboflow validation screenshot; not calculated from session images.')
        st.info('The screenshot did not provide overall test precision, recall or F1. These are not estimated.')
    with tab2:
        st.subheader('Per-class mAP@50')
        split=st.radio('Dataset split',['Validation','Test'],horizontal=True)
        col='Validation mAP@50' if split=='Validation' else 'Test mAP@50'
        plot=CLASS_METRICS.sort_values(col)
        fig=px.bar(plot,x=col,y='Vessel Class',orientation='h',range_x=[0,100],text=col,
            color_discrete_sequence=['#F59E0B'],title=f'{split} mAP@50 by vessel class')
        fig.update_traces(texttemplate='%{text:.0f}%',textposition='outside')
        styled_plot(fig)
        st.dataframe(CLASS_METRICS,use_container_width=True,hide_index=True)
        st.caption('Values transcribed from your supplied Roboflow validation and test screenshots.')
    with tab3:
        st.subheader('Current Session Observations')
        if df.empty: st.info('No inference records. Run Image Detection first.')
        else:
            a,b,c=st.columns(3)
            a.metric('Vessel Observations',len(df))
            b.metric('Average Detection Confidence',f'{df["Confidence"].mean():.1%}')
            c.metric('Detection Runs',run_count)
            left,right=st.columns(2)
            with left:
                counts=df['Vessel Class'].value_counts().reset_index()
                counts.columns=['Vessel Class','Observations']
                styled_plot(px.bar(counts,x='Vessel Class',y='Observations',title='Observations by Class',color_discrete_sequence=['#F59E0B']))
            with right:
                styled_plot(px.histogram(df,x='Confidence',nbins=12,title='Detection Confidence Distribution',color_discrete_sequence=['#38BDF8']))
            st.dataframe(df,use_container_width=True,hide_index=True)
            st.caption('Counts represent detections, not unique vessel identities. Session-only data.')

elif page=='Dataset Explorer':
    heading('Dataset Explorer','Evaluation reference data · dataset sample counts are not supplied')
    st.subheader('Model Class Evaluation Table')
    st.dataframe(CLASS_METRICS,use_container_width=True,hide_index=True)
    st.caption('The class values are evaluation metrics, not counts of training or test images.')
    unavailable('Dataset composition','Upload an exported Roboflow dataset summary or annotations to calculate class balance and split sizes.')

elif page=='Alerts & Monitoring':
    heading('Alerts & Monitoring','Central alert overview for connected modules')
    st.metric('Confirmed Security Alerts',0)
    st.info('Live AIS alerting is not connected. Use AIS / GPS Tracking → Threat Assessment to assess uploaded AIS records. Zero confirmed alerts does not establish safety.')
    st.subheader('Planned Alert Rules')
    st.write('AIS reporting gaps · monitored-zone entry · route deviation · visual/AIS mismatch (future integration)')
    st.caption('An AI vessel detection is not automatically a security incident.')

elif page=='Reports & Evidence':
    heading('Reports & Evidence','Export and review session detection evidence')
    if df.empty: st.info('No evidence records yet. Run Image Detection first.')
    else:
        st.subheader('Detection Records')
        st.dataframe(df,use_container_width=True,hide_index=True)
        st.download_button('Download detection CSV',df.to_csv(index=False).encode('utf-8'),
            'sea_sentinel_detection_records.csv','text/csv')
        st.download_button('Download detection JSON',df.to_json(orient='records',indent=2).encode('utf-8'),
            'sea_sentinel_detection_records.json','application/json')
        st.caption('Records are in memory and are lost when the Streamlit session resets.')
        if st.button('Clear session evidence'):
            for key,value in [('records',[]),('runs',[]),('latest_annotated',None),('latest_original',None),('latest_predictions',[]),('last_run',None)]:
                st.session_state[key]=value
            st.rerun()

elif page=='Settings':
    heading('Settings','Detection and integration configuration')
    st.subheader('Detection')
    st.slider('Default confidence threshold',0.10,1.00,0.05,key='confidence')
    st.divider()
    st.subheader('Roboflow Connection')
    st.text_input('Workspace',WORKSPACE,disabled=True)
    st.text_input('Workflow ID',WORKFLOW_ID,disabled=True)
    if api_key(): st.success('Roboflow API key is present in Streamlit secrets.')
    else: st.error('ROBOFLOW_API_KEY is missing. Set it in .streamlit/secrets.toml.')
    st.caption('API keys are not displayed in this interface.')
    st.divider()
    st.subheader('Upcoming Integrations')
    st.write('AIS provider API · local AIS receiver · evidence database')

elif page=='System Information':
    heading('System Information','Capabilities and operational limitations')
    info=[('Application','SEA SENTINEL'),('Development','V2 project only'),('Model','Roboflow YOLO26 workflow (as configured)'),
          ('Image inference','Roboflow serverless API, internet required'),('Video inference','Uploaded video frame analysis with Roboflow'),
          ('AIS/GPS','Not connected'),('Data persistence','Session only'),('Reference metrics','Roboflow screenshots')]
    st.dataframe(pd.DataFrame(info,columns=['Component','Status']),hide_index=True,use_container_width=True)
    st.warning('The application is not an autonomous maritime navigation or collision-avoidance system.')

st.divider()
st.caption('SEA SENTINEL · Maritime Intelligence Platform | Development dashboard · Reported model metrics are reference evaluation values')
