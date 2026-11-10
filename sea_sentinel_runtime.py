"""SEA SENTINEL video and webcam inference helpers (no Streamlit calls in camera threads)."""
from __future__ import annotations
import base64
import os
import shutil
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

import cv2
import numpy as np
from inference_sdk import InferenceHTTPClient, InferenceConfiguration

COLORS = {
    'cargo_ship': (113, 204, 46), 'container_ship': (246, 130, 59),
    'fishing_boat': (11, 158, 245), 'military_vessel': (250, 139, 167),
    'passenger_ferry': (212, 182, 6), 'speedboat': (182, 114, 244),
    'tanker': (68, 68, 239), 'yacht': (106, 182, 212)
}

def normalized_class(name):
    return str(name or 'unknown').lower().strip().replace(' ', '_').replace('-', '_')

def extract_predictions(response):
    data = response[0] if isinstance(response, list) and response else response
    if not isinstance(data, dict):
        return []
    for key in ('detections_json', 'predictions'):
        value = data.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict) and isinstance(value.get('predictions'), list):
            return value['predictions']
    return []

class RoboflowRunner:
    def __init__(self, key, workspace, workflow):
        self.key, self.workspace, self.workflow = key, workspace, workflow
        self.client = InferenceHTTPClient(api_url='https://serverless.roboflow.com', api_key=key)
        self.client = self.client.configure(InferenceConfiguration(api_key_transport='header'))
        self.lock = Lock()

    def infer(self, bgr, confidence, max_width=960):
        h, w = bgr.shape[:2]
        scale = min(1.0, max_width / max(1, w))
        sample = cv2.resize(bgr, (round(w*scale), round(h*scale))) if scale < 1 else bgr
        path = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                path = tmp.name
            if not cv2.imwrite(path, sample, [cv2.IMWRITE_JPEG_QUALITY, 85]):
                raise RuntimeError('Unable to encode inference frame')
            with self.lock:
                response = self.client.run_workflow(
                    workspace_name=self.workspace, workflow_id=self.workflow,
                    images={'image': path}, parameters={'confidence_threshold': confidence}, use_cache=False)
            predictions = extract_predictions(response)
            if scale != 1:
                predictions = [dict(p, **{k: float(p[k])/scale for k in ('x','y','width','height')})
                               if isinstance(p,dict) and all(k in p for k in ('x','y','width','height')) else p
                               for p in predictions]
            return predictions
        finally:
            if path and os.path.exists(path):
                os.remove(path)

def draw_boxes(frame, predictions, allowed, threshold, stale=False):
    out = frame.copy()
    h,w = out.shape[:2]
    visible=[]
    for p in predictions:
        if not isinstance(p,dict): continue
        label = normalized_class(p.get('class'))
        try:
            confidence=float(p.get('confidence') or 0)
            if label not in allowed or confidence < threshold: continue
            x,y,bw,bh=(float(p[k]) for k in ('x','y','width','height'))
            x1,y1=max(0,int(x-bw/2)),max(0,int(y-bh/2))
            x2,y2=min(w-1,int(x+bw/2)),min(h-1,int(y+bh/2))
            if x2<=x1 or y2<=y1: continue
            color=COLORS.get(label,(248,189,56))
            cv2.rectangle(out,(x1,y1),(x2,y2),color,2)
            text=f'{label.replace("_"," ").title()} {confidence:.0%}'
            (tw,th),_ = cv2.getTextSize(text,cv2.FONT_HERSHEY_SIMPLEX,.52,1)
            ytop=max(0,y1-th-12)
            cv2.rectangle(out,(x1,ytop),(min(w-1,x1+tw+9),min(h-1,ytop+th+9)),color,-1)
            cv2.putText(out,text,(x1+4,ytop+th+3),cv2.FONT_HERSHEY_SIMPLEX,.52,(5,17,27),1,cv2.LINE_AA)
            visible.append(p)
        except (KeyError,ValueError,TypeError):
            continue
    if stale:
        cv2.putText(out,'CACHED BOXES - NOT A NEW PREDICTION',(12,26),cv2.FONT_HERSHEY_SIMPLEX,.55,(0,190,255),2,cv2.LINE_AA)
    return out,visible

def encode_mp4_for_browser(path):
    """Try H264 conversion; otherwise keep mp4v file (download may still work)."""
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        try:
            import imageio_ffmpeg
            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        except (ImportError,RuntimeError,OSError):
            return open(path,'rb').read(), False
    target = path + '.h264.mp4'
    result = subprocess.run([ffmpeg,'-y','-loglevel','error','-i',path,'-c:v','libx264',
                             '-preset','veryfast','-pix_fmt','yuv420p','-movflags','+faststart',target],
                            capture_output=True,text=True)
    if result.returncode==0 and os.path.getsize(target)>0:
        with open(target,'rb') as f: data=f.read()
        os.remove(target)
        return data,True
    if os.path.exists(target): os.remove(target)
    return open(path,'rb').read(),False

class WebcamProcessor:
    """Non-blocking inference: webcam frames continue while Roboflow processes a sample."""
    def __init__(self,runner,confidence,allowed,every_n=3,min_interval=0.5):
        self.runner=runner; self.confidence=confidence; self.allowed=set(allowed)
        self.every_n=max(1,int(every_n)); self.min_interval=max(.1,float(min_interval))
        self.executor=ThreadPoolExecutor(max_workers=1)
        self.future=None; self.last_predictions=[]; self.last_submit=0; self.frame_number=0
        self.error=None; self.lock=Lock()

    def recv(self, frame):
        import av
        bgr=frame.to_ndarray(format='bgr24')
        with self.lock:
            self.frame_number+=1
            if self.future is not None and self.future.done():
                try: self.last_predictions=self.future.result(); self.error=None
                except Exception as exc: self.error=str(exc)
                self.future=None
            now=time.monotonic()
            if (self.future is None and self.frame_number%self.every_n==0
                    and now-self.last_submit>=self.min_interval):
                self.future=self.executor.submit(self.runner.infer,bgr.copy(),self.confidence)
                self.last_submit=now
            output,_=draw_boxes(bgr,self.last_predictions,self.allowed,self.confidence,
                                stale=bool(self.last_predictions))
            if self.error:
                cv2.putText(output,'Inference error - check terminal',(12,55),cv2.FONT_HERSHEY_SIMPLEX,.65,(0,0,255),2)
        return av.VideoFrame.from_ndarray(output,format='bgr24')
