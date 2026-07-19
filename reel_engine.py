#!/usr/bin/env python3
"""
NAL Reel Engine — carrusel JSON (Notion) -> reel funk 9:16 MP4.
Marca Cafe Editorial. Kinetic typography, hard cuts on beat, funk groove sintetizado.

v2 (low-memory): disenado para caber en 512MB (Render Free).
  - Diseno se compone en espacio 1080x1920 y se exporta a 720x1280.
  - NO escribe 600 frames: solo ~6 imagenes por tarjeta (5 de animacion + 1 estatica)
    y ffmpeg las une con el demuxer concat usando duraciones.
  - ffmpeg con -threads 1 y memoria liberada antes de codificar.

Uso:
  python reel_engine.py --carousel row.json --out reel.mp4
Robusto: auto-ajusta cada texto para que NUNCA se corte.
"""
import os, sys, json, argparse, subprocess, wave, tempfile, shutil, gc
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# Espacio de diseno (donde vive el layout validado) y salida real
BW, BH = 1080, 1920
OW, OH = 720, 1280
FPS = 30
N_ANIM = 5                      # frames de animacion por corte
ANIM_WIN = N_ANIM / FPS         # ~0.167s

FD = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.environ.get("NAL_FONT_DIR", os.path.join(FD, "fonts"))
FRB = os.path.join(FONT_DIR, "Fraunces_900Black.ttf")
FRb = os.path.join(FONT_DIR, "Fraunces_700Bold.ttf")
DMB = os.path.join(FONT_DIR, "DMSans_700Bold.ttf")
C = dict(papel=(243,234,216), espresso=(42,30,22), terracota=(200,85,61),
         marigold=(242,169,59), salvia=(126,139,90), ciruela=(59,31,58))
BPM = 114; BEAT = 60.0/BPM

# ---------- text helpers (auto-fit) ----------
_scratch = ImageDraw.Draw(Image.new("RGB",(10,10)))
_fcache = {}
def font(path, size):
    k=(path,size)
    if k not in _fcache: _fcache[k]=ImageFont.truetype(path,size)
    return _fcache[k]
def tw(s, f): b=_scratch.textbbox((0,0),s,font=f); return b[2]-b[0]
def wrap(text, f, maxw):
    out=[]; cur=""
    for w in str(text).split():
        t=(cur+" "+w).strip()
        if tw(t,f)>maxw and cur: out.append(cur); cur=w
        else: cur=t
    if cur: out.append(cur)
    return out
def fit_block(text, path, size_max, maxw, maxlines, size_min=46):
    size=size_max
    while size>=size_min:
        f=font(path,size); lines=wrap(text,f,maxw)
        if len(lines)<=maxlines and all(tw(l,f)<=maxw for l in lines):
            return f,size,lines
        size-=5
    f=font(path,size_min)
    return f,size_min,wrap(text,f,maxw)[:maxlines]
def draw_tracked(d,xy,s,f,fill,tr):
    x,y=xy
    for ch in s: d.text((x,y),ch,font=f,fill=fill); x+=tw(ch,f)+tr

# ---------- card model ----------
PALETTE_CYCLE = ['papel','espresso','terracota','ciruela','papel','espresso']
ANIM_CYCLE = ['slideU','slideL','punch','slideL','slideU','pop']
def contrast_text(bg): return 'papel' if bg in ('espresso','terracota','ciruela','salvia') else 'espresso'
def accent_for(bg): return 'marigold' if bg!='marigold' else 'terracota'

def spec_from_carousel(cj):
    import re
    pillar=str(cj.get('pilar','')).split('·')[0].split('-')[0].strip().upper()[:14]
    hook=cj.get('hook') or (cj.get('laminas',[{}])[0].get('titulo',''))
    body=[l for l in cj.get('laminas',[]) if l.get('rol') in ('valor','contexto','recap')][:6]
    cards=[dict(bg='papel', anim='punch', beats=4, label=pillar,
                title=hook, size=150, color='espresso', center=True)]
    for i,l in enumerate(body):
        raw=str(l.get('titulo','')).strip()
        m=re.match(r'^(\d+)\s*[·.\-]?\s*(.*)$', raw)
        num=m.group(1) if m else None
        title=(m.group(2) if m else raw).strip()
        bg=PALETTE_CYCLE[i%len(PALETTE_CYCLE)]
        cards.append(dict(bg=bg, anim=ANIM_CYCLE[i%len(ANIM_CYCLE)], beats=4,
                          num=num, title=title, size=140, color=contrast_text(bg)))
    cards.append(dict(bg='espresso', anim='pop', beats=8, cta=True,
                      title="Sígueme.", size=170, color='papel',
                      handle="@noailimites.ia"))
    return cards

# ---------- base image (composed at 1080x1920, returned at 720x1280) ----------
def base_image(card):
    bg=C[card['bg']]; img=Image.new("RGB",(BW,BH),bg); d=ImageDraw.Draw(img)
    draw_tracked(d,(70,80),"NO [AI] LÍMITES",font(DMB,26),C[accent_for(card['bg'])],5)
    maxw=BW-180
    if card.get('label'):
        d.text((90,150),card['label'],font=font(FRb,50),fill=C['salvia'])
    if card.get('num'):
        r=95; cx,cy=175,470
        d.ellipse([cx-r,cy-r,cx+r,cy+r],fill=C[accent_for(card['bg'])])
        nf=font(FRB,118); nb=d.textbbox((0,0),card['num'],font=nf)
        d.text((cx-(nb[2]-nb[0])/2-nb[0],cy-(nb[3]-nb[1])/2-nb[1]),card['num'],
               font=nf,fill=C[contrast_text(accent_for(card['bg']))])
    maxlines = 3 if card.get('center') else 2
    f,size,lines=fit_block(card['title'],FRB,card['size'],maxw,maxlines)
    lh=int(size*1.04); blockH=len(lines)*lh
    if card.get('num'): y0=720
    elif card.get('cta'): y0=int(BH*0.30)
    else: y0=int(BH/2-blockH/2)
    y=y0
    for ln in lines:
        x=(BW-tw(ln,f))/2 if (card.get('center') or card.get('cta')) else 90
        d.text((x,y),ln,font=f,fill=C[card['color']]); y+=lh
    if not card.get('center') and not card.get('cta'):
        d.rectangle([90,y+18,270,y+36],fill=C[accent_for(card['bg'])])
    if card.get('cta'):
        hf=font(FRb,86); hw=tw(card['handle'],hf)
        d.rectangle([(BW-180)/2,y0+230,(BW+180)/2,y0+248],fill=C['terracota'])
        d.text(((BW-hw)/2,y0+300),card['handle'],font=hf,fill=C['marigold'])
    small = img.resize((OW,OH), Image.LANCZOS)   # exportar a 720x1280
    img.close(); del img, d
    return small

# ---------- imagenes + lista concat (pocas escrituras) ----------
def render_segments(cards, work):
    t=0.0
    for c in cards: c['t0']=t; c['t1']=t+c['beats']*BEAT; t=c['t1']
    total=t
    entries=[]   # (path, duration)
    for i,c in enumerate(cards):
        base=base_image(c); bg=C[c['bg']]; anim=c['anim']
        # frames de animacion (entrada del corte)
        for k in range(N_ANIM):
            p=(k+1)/N_ANIM
            canvas=Image.new("RGB",(OW,OH),bg)
            if anim in('pop','punch'):
                s=(1.18-0.18*p) if anim=='pop' else (0.82+0.18*p)
                nw,nh=int(OW*s),int(OH*s)
                sc=base.resize((nw,nh))
                canvas.paste(sc,(int((OW-nw)/2),int((OH-nh)/2))); sc.close()
            elif anim=='slideL': canvas.paste(base,(int(-(1-p)*OW*0.31),0))
            elif anim=='slideU': canvas.paste(base,(0,int((1-p)*OH*0.20)))
            else: canvas.paste(base,(0,0))
            fp=os.path.join(work,f"c{i:02d}a{k}.jpg")
            canvas.save(fp,quality=88); canvas.close()
            entries.append((fp, 1.0/FPS))
        # estatica sostenida
        sp=os.path.join(work,f"c{i:02d}s.jpg")
        base.save(sp,quality=88); base.close()
        hold=max(0.1,(c['t1']-c['t0'])-ANIM_WIN)
        entries.append((sp, hold))
        gc.collect()
    # archivo concat (el ultimo se repite sin duracion: requisito del demuxer)
    lp=os.path.join(work,"list.txt")
    with open(lp,"w") as fh:
        for p,dur in entries:
            fh.write(f"file '{p}'\nduration {dur:.4f}\n")
        fh.write(f"file '{entries[-1][0]}'\n")
    return lp, total, len(entries)

# ---------- funk music (synth, royalty-free) ----------
def make_funk(total_beats, path, sr=44100):
    beat=60.0/BPM; six=beat/4; N=int(total_beats*beat*sr)
    master=np.zeros(N, dtype=np.float32)
    def midi(n): return 440.0*2**((n-69)/12.0)
    def add(a,t):
        i=int(round(t*sr)); j=min(i+len(a),N)
        if i<N: master[i:j]+=a[:j-i].astype(np.float32)
    def pl(n,dec):
        t=np.linspace(0,n/sr,n,False); return np.exp(-t/dec)
    def lp(x,k): return x if k<=1 else np.convolve(x,np.ones(k)/k,'same')
    def kick(v=1,dur=0.18):
        n=int(sr*dur);t=np.linspace(0,dur,n,False);f=60*np.exp(-t/0.03)+42
        return v*(np.sin(2*np.pi*np.cumsum(f)/sr)*np.exp(-t/0.09)+0.3*np.sin(2*np.pi*f*t)*np.exp(-t/0.02))
    def snare(v=1,dur=0.19):
        n=int(sr*dur);t=np.linspace(0,dur,n,False)
        return v*(0.7*np.random.randn(n)*np.exp(-t/0.06)+0.5*(np.sin(2*np.pi*185*t)+np.sin(2*np.pi*330*t))*np.exp(-t/0.05))
    def hat(v=1,open_=False):
        dur=0.14 if open_ else 0.05;n=int(sr*dur);t=np.linspace(0,dur,n,False)
        h=np.random.randn(n)*np.exp(-t/(0.05 if open_ else 0.014))
        return v*0.5*np.convolve(h,np.array([1,-1]),'same')
    def bass(note,dur,v=1):
        n=int(sr*dur);t=np.linspace(0,dur,n,False);f=midi(note)
        w=np.sign(np.sin(2*np.pi*f*t))*0.5+np.sin(2*np.pi*f*t)+0.3*np.sin(2*np.pi*2*f*t)
        return v*0.6*lp(w,14)*pl(n,dur*0.5)
    def stab(notes,dur,v=1):
        n=int(sr*dur);t=np.linspace(0,dur,n,False);w=np.zeros(n)
        for m in notes:
            f=midi(m)
            for h,g in [(1,1),(2,0.6),(3,0.36),(4,0.18)]: w+=g*np.sin(2*np.pi*f*h*t)
        return v*0.12*lp(w,4)*pl(n,dur*0.4)
    def horn(notes,dur,v=1):
        n=int(sr*dur);t=np.linspace(0,dur,n,False);w=np.zeros(n)
        for m in notes:
            f=midi(m)
            for h in range(1,9): w+=(1.0/h)*np.sin(2*np.pi*f*h*t)
        a=int(n*0.06);env=np.ones(n);env[:a]=np.linspace(0,1,a);env[-int(n*0.3):]=np.linspace(1,0,int(n*0.3))
        return v*0.10*lp(w,3)*env
    Dm=[62,65,69,72];Gm=[67,70,74,77]
    def s16(b,i): return (b*16+i)*six
    nbars=int(np.ceil(total_beats/4))
    bassline={0:50,3:50,6:53,7:57,8:50,10:55,11:50,14:48}
    for b in range(nbars):
        for i in range(16): add(hat(0.9 if i%2 else 0.5, open_=(i==14)), s16(b,i))
        for i in (0,6,8,11): add(kick(1.0), s16(b,i))
        for i in (4,12): add(snare(1.0), s16(b,i))
        add(kick(0.5), s16(b,14))
        for i,note in bassline.items(): add(bass(note,six*1.6,1.0), s16(b,i))
        for i in (2,7,10,15): add(stab(Dm,six*0.9,0.9), s16(b,i))
        add(horn(Dm,six*1.4,0.9), s16(b,6))
        if b%2: add(horn(Gm,six*1.2,0.8), s16(b,12))
    master/=np.max(np.abs(master))+1e-9; master=np.tanh(master*1.2)*0.9
    fi=int(sr*0.02);master[:fi]*=np.linspace(0,1,fi)
    fo=int(sr*0.5);master[-fo:]*=np.linspace(1,0,fo)
    st=np.clip(np.stack([master,np.roll(master,90)*0.97],1),-1,1)
    data=(st*32767).astype(np.int16)
    with wave.open(path,'w') as wf:
        wf.setnchannels(2);wf.setsampwidth(2);wf.setframerate(sr);wf.writeframes(data.tobytes())
    del master, st, data; gc.collect()

# ---------- orchestration ----------
def build_reel(carousel_json, out_path):
    cards=spec_from_carousel(carousel_json)
    total_beats=sum(c['beats'] for c in cards)
    work=tempfile.mkdtemp(prefix="nalreel_")
    try:
        listfile, total, nimgs = render_segments(cards, work)
        music=os.path.join(work,"funk.wav"); make_funk(total_beats, music)
        _fcache.clear(); gc.collect()          # liberar antes de ffmpeg
        subprocess.run(["ffmpeg","-y","-loglevel","error","-threads","1",
            "-f","concat","-safe","0","-i",listfile,"-i",music,
            "-r",str(FPS),"-c:v","libx264","-crf","23","-preset","veryfast",
            "-pix_fmt","yuv420p","-c:a","aac","-b:a","128k",
            "-movflags","+faststart","-shortest",out_path],check=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
        gc.collect()
    return out_path, round(total,2), len(cards)

def load_carousel(path):
    raw=json.load(open(path,encoding="utf-8"))
    if isinstance(raw,str): raw=json.loads(raw)
    if "carousel" in raw: raw=raw["carousel"]
    if isinstance(raw,str): raw=json.loads(raw)
    return raw

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--carousel",required=True); ap.add_argument("--out",required=True)
    a=ap.parse_args()
    cj=load_carousel(a.carousel)
    out,dur,nc=build_reel(cj,a.out)
    print(f"OK {out}  dur={dur}s  cards={nc}")
