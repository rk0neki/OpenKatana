"""Motion diagnostics for rendered clips. Measurements are review candidates, not taste scores."""
import csv
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from .contracts import ContractError, number, fields
from .render import digest, write_json


def cut_set(cuts, count, start=0):
    if not isinstance(cuts, list):
        raise ContractError('cuts must be a list of incoming master-frame indices')
    for c in cuts:
        number(c, 'cut', start + 1, start + count - 1, integer=True)
    return set(cuts)


def write_report(out, summary, rows, columns):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    write_json(out/'report.json', summary)
    with (out/'metrics.csv').open('w', newline='', encoding='utf8') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    im = Image.new('RGB', (1000, 180*len(columns)), '#141821')
    draw = ImageDraw.Draw(im)
    for i, column in enumerate(columns):
        vals = [r.get(column) for r in rows]
        mx = max([abs(x) for x in vals if x is not None] or [0]) or 1
        draw.text((8, i*180+8), f'{column}: peak {mx:.3f}', fill='white')
        points = []
        for j, value in enumerate(vals):
            if value is None:
                if len(points)>1: draw.line(points, fill='#7ADECA', width=2)
                points=[]; continue
            points.append((j*999/max(1,len(rows)-1), i*180+165-abs(value)/mx*130))
        if len(points)>1: draw.line(points, fill='#7ADECA', width=2)
    im.save(out/'metrics.png')
    return {**summary, 'report':str(out/'report.json'), 'metrics':str(out/'metrics.csv'),
            'preview_images':[str(out/'metrics.png')], 'review_required':True}


def flow_flags(rows, moving=1.5, ratio=2.2, stall=.25):
    flags=[]
    for i in range(2,len(rows)-1):
        a,b,c = (r['median_px'] for r in rows[i-1:i+2])
        if any(v is None for v in (a,b,c)) or min(a,c)<=moving:
            continue
        if b<stall or b>ratio*max(a,c) or b<min(a,c)/ratio:
            flags.append({'frame':rows[i]['frame'], 'kind':'stall' if b<stall else 'judder',
                          'previous':a,'current':b,'next':c})
    return flags


def analyze_video(source, out, cuts=None, work_width=480, moving=1.5, ratio=2.2, stall=.25):
    """Read every decoded frame. Optical flow scaled to actual source pixels; cuts excluded."""
    try:
        import cv2
    except ImportError as e:
        raise ContractError('Install the OpenKatana vision extra for optical-flow analysis') from e
    number(work_width,'work_width',64,1920,integer=True)
    number(moving,'moving',0,10000);number(ratio,'ratio',1.01,100);number(stall,'stall',0,10000)
    before=digest(source)
    cap=cv2.VideoCapture(str(source))
    if not cap.isOpened(): raise ContractError('Could not decode video for motion analysis')
    rows=[];prev=None;previous_raw=None
    try:
        fps=cap.get(cv2.CAP_PROP_FPS);number(fps,'video fps',.01,1000)
        width=round(cap.get(cv2.CAP_PROP_FRAME_WIDTH));height=round(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cut_values=cut_set(cuts or [], max(2,round(cap.get(cv2.CAP_PROP_FRAME_COUNT))))
        w=min(work_width,width);h=max(1,round(height*w/width));scale=width/w
        while True:
            ok,frame=cap.read()
            if not ok: break
            if len(rows)>=36000: raise ContractError('Analyze at most 36000 frames per segment')
            i=len(rows)
            grey=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
            g=cv2.resize(grey,(w,h),interpolation=cv2.INTER_AREA)
            duplicate=previous_raw is not None and np.array_equal(frame,previous_raw)
            row={'frame':i,'cut':i in cut_values,'duplicate':bool(duplicate), 'median_px':None,'p95_px':None}
            if prev is not None and i not in cut_values:
                flow=cv2.calcOpticalFlowFarneback(prev,g,None,.5,4,21,3,5,1.1,0)
                mag=np.hypot(flow[...,0],flow[...,1])*scale
                row.update(median_px=float(np.median(mag)),p95_px=float(np.percentile(mag,95)))
            rows.append(row);prev=g;previous_raw=frame
    finally:
        cap.release()
    if len(rows)<3: raise ContractError('Motion analysis needs at least three decoded frames')
    cut_set(cuts or [],len(rows))
    if digest(source)!=before: raise ContractError('Source changed during motion analysis')
    flags=flow_flags(rows,moving,ratio,stall)
    summary={'source_sha256':before,'frames':len(rows),'fps':fps,'width':width,'height':height,
             'cuts':sorted(cut_values),'flags':flags,
             'duplicate_frames':[r['frame'] for r in rows if r['duplicate'] and not r['cut']],
             'thresholds':{'moving_px':moving,'judder_ratio':ratio,'stall_px':stall},
             'method':'Farneback flow at reduced size, scaled to source pixels per decoded frame; analysis only',
             'limits':'Heuristics can flag intentional holds, occlusions or flashes; inspect playback. CFR expected.'}
    return write_report(out,summary,rows,['median_px','p95_px'])


def angle(a,b):
    norms=math.sqrt(sum(x*x for x in a)*sum(x*x for x in b))
    if norms<1e-12: raise ContractError('Camera forward vector must be nonzero')
    return math.degrees(math.acos(max(-1,min(1,sum(x*y for x,y in zip(a,b))/norms))))


def analyze_camera(document, out, jolt_threshold=2500, jolt_ratio=3):
    fields(document,'fps width height shutter cuts rows','camera samples')
    number(document.get('fps'),'fps',1,240);number(document.get('width'),'width',16,16384,integer=True)
    number(jolt_threshold,'jolt_threshold',0,1e9);number(jolt_ratio,'jolt_ratio',1,100)
    source=document.get('rows')
    if not isinstance(source,list) or not 3<=len(source)<=36000: raise ContractError('Supply 3..36000 evaluated camera samples')
    fps=document['fps'];width=document['width'];start=source[0].get('f')
    number(start,'first frame',0,100000,integer=True)
    cuts=cut_set(document.get('cuts',[]),len(source),start)
    rows=[]
    for i,r in enumerate(source):
        fields(r,'f pos fwd pos_open fwd_open pos_close fwd_close lens hfov_deg','camera row')
        if r.get('f')!=start+i: raise ContractError('Camera samples must contain consecutive master frames')
        for k in ('pos','fwd','fwd_open','fwd_close'):
            v=r.get(k)
            if not isinstance(v,list) or len(v)!=3: raise ContractError(k+' needs three coordinates')
            for x in v: number(x,k)
        number(r.get('hfov_deg'),'hfov_deg',.1,179)
        ppd=width/r['hfov_deg']
        rec={'frame':r['f'],'cut':r['f'] in cuts,'speed':None,'aim_deg_s':None,
             'pan_px':None,'shutter_rotation_px':angle(r['fwd_open'],r['fwd_close'])*ppd,'aim_accel':None}
        if i and not rec['cut']:
            previous=source[i-1]
            delta=angle(previous['fwd'],r['fwd'])
            rec.update(speed=math.dist(previous['pos'],r['pos'])*fps,aim_deg_s=delta*fps,pan_px=delta*ppd)
            if rows[-1]['aim_deg_s'] is not None:
                rec['aim_accel']=(rec['aim_deg_s']-rows[-1]['aim_deg_s'])*fps
        rows.append(rec)
    flags=[]
    for i in range(2,len(rows)-2):
        value=rows[i]['aim_accel']
        adjacent=[abs(rows[k]['aim_accel']) for k in (i-2,i-1,i+1,i+2) if rows[k]['aim_accel'] is not None]
        if value is not None and adjacent and abs(value)>jolt_threshold and abs(value)>jolt_ratio*sum(adjacent)/len(adjacent):
            flags.append({'frame':rows[i]['frame'],'kind':'aim_jolt','aim_accel':value})
    summary={'frames':len(rows),'fps':fps,'cuts':sorted(cuts),'flags':flags,
             'max_shutter_rotation_px':max(r['shutter_rotation_px'] for r in rows),
             'thresholds':{'jolt_deg_s2':jolt_threshold,'relative_ratio':jolt_ratio},
             'limits':'Rotation-only pixel estimate; translation/depth, occlusion and creative intent require rendered-video review.'}
    return write_report(out,summary,rows,['speed','aim_deg_s','shutter_rotation_px','aim_accel'])
