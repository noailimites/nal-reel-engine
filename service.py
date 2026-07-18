#!/usr/bin/env python3
"""
NAL Reel Engine — HTTP service (paralelo al carousel render engine).
POST /render  {carousel:{...}}  -> {url: "https://host/vid/<id>.mp4", dur, cards}
GET  /vid/<id>.mp4              -> sirve el MP4 (TTL 20 min; público para que Meta lo descargue)
GET  /                          -> health
Auth: header x-api-key == NAL_RENDER_KEY (si está seteada).
"""
import os, io, uuid, time, threading, tempfile
from flask import Flask, request, jsonify, send_file, abort
import reel_engine as E

app = Flask(__name__)
KEY = os.environ.get("NAL_RENDER_KEY")
BASE = os.environ.get("PUBLIC_BASE_URL") or os.environ.get("RENDER_EXTERNAL_URL","")
STORE = {}            # id -> (path, expires)
TTL = 20*60

def _gc():
    now=time.time()
    for k,(p,exp) in list(STORE.items()):
        if exp<now:
            try: os.remove(p)
            except OSError: pass
            STORE.pop(k,None)

@app.get("/")
def health(): return jsonify(ok=True, service="nal-reel-engine")

@app.post("/render")
def render():
    if KEY and request.headers.get("x-api-key")!=KEY: abort(401)
    body=request.get_json(force=True, silent=True) or {}
    cj=body.get("carousel", body)
    if isinstance(cj,str):
        import json as _j; cj=_j.loads(cj)
    vid=uuid.uuid4().hex[:12]
    out=os.path.join(tempfile.gettempdir(), f"{vid}.mp4")
    _, dur, cards = E.build_reel(cj, out)
    STORE[vid]=(out, time.time()+TTL); _gc()
    base=(BASE or request.host_url.rstrip("/")).rstrip("/")
    return jsonify(url=f"{base}/vid/{vid}.mp4", dur=dur, cards=cards)

@app.get("/vid/<vid>.mp4")
def serve(vid):
    _gc()
    if vid not in STORE: abort(404)
    return send_file(STORE[vid][0], mimetype="video/mp4",
                     as_attachment=False, download_name=f"{vid}.mp4")

if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT","8080")))
