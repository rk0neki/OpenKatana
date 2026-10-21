"""Local analysis of supplied frames. No network access or automatic downloads."""
from pathlib import Path
import json
import numpy as np
from PIL import Image,ImageFilter
from .contracts import ContractError,local_path,number
from .render import digest,write_json

def cv():
    try:import cv2
    except ImportError as e:raise ContractError('Install OpenKatana with the vision extra for this operation') from e
    return cv2

def clip_at(timeline,clip_id):
    edit=json.loads(timeline.read_text(encoding='utf-8'));clip=edit['clips'][clip_id];root=timeline.resolve().parent
    files=[local_path(root,clip['frames_dir'])/(clip.get('pattern','%05d.png')%i) for i in range(clip['n'])]
    for f in files:
        if not f.is_file():raise ContractError(f'Missing frame: {f.name}')
    return clip,files

def output_path(timeline,out):
    """Return a usable project-relative path, including nested output folders."""
    root=timeline.resolve().parent;out=out.resolve()
    if not out.is_relative_to(root):raise ContractError('Analysis outputs must be inside the timeline project')
    return out.relative_to(root).as_posix()

def masks(timeline,clip_id,out,mode='chroma',key='#00ff00',tolerance=.18,softness=.08,rect=None,feather=0):
    relative=output_path(timeline,out)
    clip,files=clip_at(timeline,clip_id)
    if mode not in ('chroma','luma','alpha','grabcut'):raise ContractError('Unknown matte method')
    number(tolerance,'tolerance',0,1);number(softness,'softness',.0001,1);number(feather,'feather',0,100)
    from .contracts import color
    color(key,'key')
    if mode=='grabcut':
        from .expanded import vector
        vector(rect,4,'rect',0,1)
        if rect[2]<=0 or rect[3]<=0 or rect[0]+rect[2]>1 or rect[1]+rect[3]>1:raise ContractError('rect must fit within the source')
    out.mkdir(parents=True,exist_ok=False);hashes={}
    if mode=='grabcut':
        # Audit F-OK-004: each frame is segmented at <= 720 px from the rectangle (3 iterations), upsampled and its edge
        # snapped to full-resolution detail with a guided filter; frames run in a small thread pool (OpenCV releases
        # the GIL), so 78 1080p frames take tens of seconds instead of ~13 minutes.
        import os
        from concurrent.futures import ThreadPoolExecutor
        def one(f):
            c=cv();bgr=c.cvtColor(np.asarray(Image.open(f).convert('RGB')),c.COLOR_RGB2BGR);h,w=bgr.shape[:2]
            sc=min(1.0,720/max(w,h));sw,sh=max(1,round(w*sc)),max(1,round(h*sc))
            small=c.resize(bgr,(sw,sh),interpolation=c.INTER_AREA) if sc<1 else bgr
            box=tuple(max(1,round(v*(sw if j%2==0 else sh))) for j,v in enumerate(rect))
            mask=np.zeros((sh,sw),np.uint8);bg=np.zeros((1,65));fg=np.zeros((1,65));c.setRNGSeed(0)
            c.grabCut(small,mask,box,bg,fg,3,c.GC_INIT_WITH_RECT)
            hard=((mask==c.GC_FGD)|(mask==c.GC_PR_FGD)).astype(np.float32)
            soft=c.resize(hard,(w,h),interpolation=c.INTER_LINEAR) if sc<1 else hard
            gray=c.cvtColor(bgr,c.COLOR_BGR2GRAY).astype(np.float32)/255
            return np.clip(_guided(gray,soft,max(2,round(2/sc)),1e-3),0,1)*255
        with ThreadPoolExecutor(max_workers=max(1,min(4,(os.cpu_count() or 2)-1))) as pool:
            grabcut_alpha=list(pool.map(one,files))
    for i,f in enumerate(files):
        im=Image.open(f).convert('RGBA');rgb=np.asarray(im)[:,:,:3]/255
        if mode=='alpha':alpha=np.asarray(im)[:,:,3]
        elif mode=='chroma':
            k=np.array([int(key[j:j+2],16)/255 for j in (1,3,5)])
            distance=np.linalg.norm(rgb-k,axis=2)/np.sqrt(3);alpha=np.clip((distance-tolerance)/softness,0,1)*255
        elif mode=='luma':alpha=np.clip((rgb@np.array([.2126,.7152,.0722])-tolerance)/softness,0,1)*255
        else:
            alpha=grabcut_alpha[i]
        matte=Image.fromarray(alpha.astype('uint8'),'L')
        if feather:matte=matte.filter(ImageFilter.GaussianBlur(feather))
        result=Image.new('RGBA',im.size,'white');result.putalpha(matte);result.save(out/f'{i:05d}.png');hashes[f.name]=digest(f)
    receipt={'method':mode,'frames':len(files),'width':clip['w'],'height':clip['h'],'source_hashes':hashes,
             'clip_update':{'mask_dir':relative},'quality_review':'pending','model':'none'}
    write_json(out/'masks.json',receipt);return receipt

def mask_digest(root, mask_dir, n):
    """Content fingerprint of a clip's matte frames (what a mask review approves)."""
    import hashlib
    h = hashlib.sha256()
    for i in range(n):
        h.update(digest(local_path(root, f'{mask_dir}/{i:05d}.png')).encode())
    return h.hexdigest()


def refine_masks(timeline, clip_id, out, grow=0, feather=0, fill_holes=False, smooth=0, keep_largest=False):
    """Refine an existing matte (audit F-MSK-001): grow (+) / shrink (-) by px, fill enclosed holes, average over
    +-smooth neighbouring frames (temporal steadiness), then feather. Writes a new mask_dir; the source is untouched."""
    relative = output_path(timeline, out)
    root = timeline.resolve().parent
    clip, _ = clip_at(timeline, clip_id)
    if 'mask_dir' not in clip:
        raise ContractError('refine needs a clip with mask_dir (run masks first)')
    number(grow, 'grow', -50, 50, integer=True); number(feather, 'feather', 0, 100); number(smooth, 'smooth', 0, 4, integer=True)
    if not isinstance(fill_holes, bool) or not isinstance(keep_largest, bool):
        raise ContractError('fill_holes and keep_largest must be true or false')
    c = cv()
    load = lambda i: np.asarray(Image.open(local_path(root, f'{clip["mask_dir"]}/{i:05d}.png')).convert('RGBA'))[:, :, 3].astype(np.float32)
    src = [load(i) for i in range(clip['n'])]
    out.mkdir(parents=True, exist_ok=False)
    for i in range(clip['n']):
        lo, hi = max(0, i - smooth), min(clip['n'], i + smooth + 1)
        a = np.mean(src[lo:hi], axis=0) if smooth else src[i]
        if grow:
            k = c.getStructuringElement(c.MORPH_ELLIPSE, (2 * abs(grow) + 1, 2 * abs(grow) + 1))
            a = (c.dilate if grow > 0 else c.erode)(a, k)
        if keep_largest:   # drop stray islands: keep the largest connected region of the matte
            n_, lab, st_, _ = c.connectedComponentsWithStats((a > 127).astype(np.uint8), connectivity=8)
            if n_ > 2:
                big = 1 + int(np.argmax(st_[1:, c.CC_STAT_AREA]))
                a = np.where((lab == big) | (a <= 127), a, 0)
        if fill_holes:
            hard = (a > 127).astype(np.uint8)
            flood = hard.copy(); mask = np.zeros((hard.shape[0] + 2, hard.shape[1] + 2), np.uint8)
            for seed in ((0, 0), (hard.shape[1] - 1, 0), (0, hard.shape[0] - 1), (hard.shape[1] - 1, hard.shape[0] - 1)):
                if flood[seed[1], seed[0]] == 0:
                    c.floodFill(flood, mask, seed, 1)
            holes = (flood == 0)
            a = np.where(holes, 255, a)
        matte = Image.fromarray(np.clip(a, 0, 255).astype('uint8'), 'L')
        if feather:
            matte = matte.filter(ImageFilter.GaussianBlur(feather))
        result = Image.new('RGBA', matte.size, 'white'); result.putalpha(matte); result.save(out / f'{i:05d}.png')
    receipt = {'method': 'refine', 'from': clip['mask_dir'], 'grow': grow, 'feather': feather, 'fill_holes': fill_holes, 'smooth': smooth, 'keep_largest': keep_largest,
               'frames': clip['n'], 'clip_update': {'mask_dir': relative}, 'quality_review': 'pending', 'model': 'none'}
    write_json(out / 'masks.json', receipt); return receipt


def review_masks(timeline, clip_id, out, step=.25, columns=4):
    """Matte review sheet (audit F-MSK-001): source frames every `step` seconds plus the last frame, background tinted,
    matte edge outlined, coverage per frame; flags empty/full mattes and coverage jumps between sampled frames."""
    root = timeline.resolve().parent
    clip, files = clip_at(timeline, clip_id)
    if 'mask_dir' not in clip:
        raise ContractError('review needs a clip with mask_dir')
    number(step, 'step', .02, 10); number(columns, 'columns', 1, 8, integer=True)
    n = clip['n']; picks = sorted({min(n - 1, round(k * step * clip['fps'])) for k in range(int((n - 1) / clip['fps'] / step) + 1)} | {n - 1})
    out.mkdir(parents=True, exist_ok=False)
    c = cv(); tw = 320; th = max(1, round(tw * clip['h'] / clip['w'])); tiles, stats = [], []
    for i in picks:
        rgb = np.asarray(Image.open(files[i]).convert('RGB')).astype(np.float32)
        a = np.asarray(Image.open(local_path(root, f'{clip["mask_dir"]}/{i:05d}.png')).convert('RGBA'))[:, :, 3].astype(np.float32) / 255
        tint = rgb * a[..., None] + (rgb * .35 + np.array([255, 0, 180]) * .65) * (1 - a[..., None])
        edge = c.Canny((a > .5).astype(np.uint8) * 255, 50, 150) > 0
        edge = c.dilate(edge.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
        tint[edge] = (255, 255, 0)
        cov = float(a.mean())
        n_, _, st_, _ = c.connectedComponentsWithStats((a > .5).astype(np.uint8), connectivity=8)
        islands = int(sum(1 for k in range(1, n_) if st_[k, c.CC_STAT_AREA] >= 16))
        stats.append({'frame': i, 't': round(i / clip['fps'], 3), 'coverage': round(cov, 4), 'islands': islands})
        im = Image.fromarray(tint.clip(0, 255).astype('uint8')).resize((tw, th))
        from PIL import ImageDraw
        d = ImageDraw.Draw(im); d.rectangle((0, 0, tw, 14), fill=(0, 0, 0)); d.text((3, 1), f'f{i}  t={i / clip["fps"]:.2f}s  {cov * 100:.1f}%', fill=(255, 255, 255))
        tiles.append(im)
    flags = [f"frame {s['frame']}: empty matte" for s in stats if s['coverage'] < .005] + [f"frame {s['frame']}: matte covers the whole frame" for s in stats if s['coverage'] > .98]
    flags += [f"frame {s['frame']}: {s['islands']} separate regions (stray islands? refine keep_largest)" for s in stats if s['islands'] > 2]
    flags += [f"frames {a_['frame']}-{b['frame']}: coverage jumps {abs(b['coverage'] - a_['coverage']) * 100:.0f} points" for a_, b in zip(stats, stats[1:]) if abs(b['coverage'] - a_['coverage']) > .25]
    sheets = []
    per = columns * 4
    for k in range(0, len(tiles), per):
        part = tiles[k:k + per]; rows = (len(part) + columns - 1) // columns
        sheet = Image.new('RGB', (columns * tw, rows * th), (20, 20, 24))
        for j, im in enumerate(part):
            sheet.paste(im, ((j % columns) * tw, (j // columns) * th))
        p = out / f'mask-review-{k // per:02d}.jpg'; sheet.save(p, quality=88); sheets.append(str(p))
    result = {'clip': clip_id, 'mask_dir': clip['mask_dir'], 'frames': picks, 'coverage': stats, 'flags': flags, 'sheets': sheets,
              'mask_sha256': mask_digest(root, clip['mask_dir'], n), 'step': step}
    write_json(out / 'mask-review.json', result); return result


def _guided(I,p,r,eps):
    """Grey guided filter (box-filter form): smooths p while following edges of the guide I."""
    c=cv();box=lambda x:c.boxFilter(x,-1,(2*r+1,2*r+1))
    mI,mp=box(I),box(p);a=(box(I*p)-mI*mp)/(box(I*I)-mI*mI+eps);b=mp-a*mI
    return box(a)*I+box(b)


YUNET=Path(__file__).resolve().parent/'models'/'face_detection_yunet_2023mar.onnx'   # MIT, OpenCV Zoo (see THIRD_PARTY_NOTICES)

def faces(timeline,clip_id,out,cascade=None,min_size=24,detector='auto'):
    """Face track with landmarks; no downloads (audit F-OK-005). detector yunet (default when available): the bundled
    YuNet model (OpenCV FaceDetectorYN) gives the box, both eyes, the nose tip and both mouth corners on a 640 px
    working copy. detector cascade: OpenCV's frontal (default + alt2) and profile cascades, eyes from the eye cascades
    (no nose/mouth). Either way the candidate most consistent with the previous face is chosen; missed frames are
    filled by Lucas-Kanade tracking of features inside the face (forward and backward) and the landmarks are tracked
    from the previous frame, else the eyes are estimated from the box (each row says which: eyes_src det|track|estimate;
    nose/mouth share it and are omitted when estimated); light temporal smoothing."""
    relative=output_path(timeline,out)
    c=cv();clip,files=clip_at(timeline,clip_id)
    number(min_size,'min_size',8,4096,integer=True)
    if detector not in ('auto','yunet','cascade'):raise ContractError('faces detector: auto, yunet or cascade')
    use_yunet=detector=='yunet' or (detector=='auto' and not cascade and YUNET.is_file() and hasattr(c,'FaceDetectorYN'))
    if use_yunet and not (YUNET.is_file() and hasattr(c,'FaceDetectorYN')):raise ContractError('YuNet needs OpenCV >= 4.8 and the bundled model file')
    if use_yunet and cascade:raise ContractError('cascade applies to detector cascade only')
    hd=Path(c.data.haarcascades)
    names=[] if use_yunet else [Path(cascade)] if cascade else [hd/'haarcascade_frontalface_default.xml',hd/'haarcascade_frontalface_alt2.xml',hd/'haarcascade_profileface.xml']
    detectors=[c.CascadeClassifier(str(p)) for p in names]
    if any(d.empty() for d in detectors):raise ContractError('Could not load the supplied face classifier')
    eye_names=[] if use_yunet else [hd/'haarcascade_eye.xml',hd/'haarcascade_eye_tree_eyeglasses.xml']
    eye_det=[c.CascadeClassifier(str(p)) for p in eye_names]
    out.mkdir(parents=True,exist_ok=False)
    rgbs=[np.array(Image.open(f).convert('RGB')) for f in files]
    grays=[c.cvtColor(im,c.COLOR_RGB2GRAY) for im in rgbs]
    H,W=grays[0].shape;scale=min(1.0,640/W)
    if use_yunet:
        sw,sh=int(round(W*scale)),int(round(H*scale))
        yn=c.FaceDetectorYN.create(str(YUNET),'',(sw,sh),.6,.3,50)
    def detect_yunet(i):
        img=c.cvtColor(c.resize(rgbs[i],(sw,sh),interpolation=c.INTER_AREA) if scale<1 else rgbs[i],c.COLOR_RGB2BGR)
        _,res=yn.detect(img);found=[]
        for row in (res if res is not None else []):
            box=[float(v)/scale for v in row[:4]]
            if min(box[2],box[3])<min_size:continue
            lm=[[float(row[4+2*k])/scale,float(row[5+2*k])/scale] for k in range(5)]
            found.append((box,'yunet',{'eyes':sorted(lm[:2]),'nose':lm[2],'mouth':sorted(lm[3:5]),'score':float(row[14])}))
        return found
    def detect(g):
        small=c.equalizeHist(c.resize(g,(int(W*scale),int(H*scale)),interpolation=c.INTER_AREA)) if scale<1 else c.equalizeHist(g)
        ms=max(8,int(min_size*scale));found=[]
        for k,d in enumerate(detectors):
            for flip in ((False,True) if 'profile' in names[k].name else (False,)):
                img=c.flip(small,1) if flip else small
                for (x,y,w,h) in d.detectMultiScale(img,scaleFactor=1.08,minNeighbors=5,minSize=(ms,ms)):
                    if flip:x=img.shape[1]-x-w
                    found.append(([x/scale,y/scale,w/scale,h/scale],names[k].stem.replace('haarcascade_','')+('_flip' if flip else '')))
        return found
    def eyes_in(g,box):
        x,y,w,h=[int(round(v)) for v in box];x=max(0,x);y=max(0,y)
        roi=g[y+int(.15*h):y+int(.58*h),x:x+w]
        if roi.size==0:return None
        cands=[]
        for d in eye_det:
            for (ex,ey,ew,eh) in d.detectMultiScale(roi,scaleFactor=1.08,minNeighbors=4,minSize=(max(6,w//10),max(6,w//10)),maxSize=(w//2,w//2)):
                cands.append((x+ex+ew/2,y+int(.15*h)+ey+eh/2,ew))
        best=None
        for i in range(len(cands)):
            for j in range(i+1,len(cands)):
                (x1,y1,s1),(x2,y2,s2)=cands[i],cands[j]
                sep=abs(x2-x1)
                if .25*w<=sep<=.65*w and abs(y2-y1)<.18*w and .5<s1/s2<2:
                    score=-abs(sep-.42*w)-abs(y2-y1)
                    if best is None or score>best[0]:best=(score,sorted([[x1,y1],[x2,y2]]))
        return best[1] if best else None
    def track_points(g0,g1,pts):
        if pts is None or len(pts)==0:return None,None
        p0=np.asarray(pts,dtype=np.float32).reshape(-1,1,2)
        p1,st,_=c.calcOpticalFlowPyrLK(g0,g1,p0,None,winSize=(21,21),maxLevel=3)
        back,st2,_=c.calcOpticalFlowPyrLK(g1,g0,p1,None,winSize=(21,21),maxLevel=3)
        good=(st.ravel()==1)&(st2.ravel()==1)&(np.linalg.norm((back-p0).reshape(-1,2),axis=1)<1.5)
        return p1.reshape(-1,2),good
    def shift_box(g0,g1,box):
        x,y,w,h=box;mask=np.zeros_like(g0);mask[int(max(0,y)):int(y+h),int(max(0,x)):int(x+w)]=255
        feats=c.goodFeaturesToTrack(g0,80,.01,max(3,w/20),mask=mask)
        if feats is None:return None
        p1,good=track_points(g0,g1,feats.reshape(-1,2))
        if good is None or good.sum()<6:return None
        d=np.median(p1[good]-feats.reshape(-1,2)[good],axis=0)
        return [x+float(d[0]),y+float(d[1]),w,h]
    rows=[None]*len(files);last=None;misses=0
    for i,g in enumerate(grays):
        found=detect_yunet(i) if use_yunet else [(b,k,None) for b,k in detect(g)]
        if found:
            def score(item):
                b=item[0]
                if last is None or misses>6:return float(b[2]*b[3])*(1.2 if 'frontal' in item[1] else 1)
                center=np.array([b[0]+b[2]/2,b[1]+b[3]/2]);old=np.array([last[0]+last[2]/2,last[1]+last[3]/2])
                return float(b[2]*b[3])/(1+float(np.linalg.norm(center-old)))*(1.2 if 'frontal' in item[1] else 1)
            b,kind,extra=max(found,key=score)
            if last is not None and misses<=6 and np.linalg.norm(np.array([b[0]+b[2]/2-last[0]-last[2]/2,b[1]+b[3]/2-last[1]-last[3]/2]))>.8*max(last[2],b[2]):
                rows[i]=None;misses+=1;continue   # implausible jump: let tracking bridge it
            last=b;rows[i]={'f':i,'box':[round(v,1) for v in b],'src':'det','detector':kind};misses=0
            if extra:rows[i].update(eyes=[[round(v,1) for v in q] for q in extra['eyes']],nose=[round(v,1) for v in extra['nose']],
                                    mouth=[[round(v,1) for v in q] for q in extra['mouth']],score=round(extra['score'],3),eyes_src='det')
        else:misses+=1
    for direction in (1,-1):   # bridge misses by tracking from the nearest known frame
        order=range(len(files)) if direction==1 else range(len(files)-1,-1,-1)
        prev=None
        for i in order:
            if rows[i] is not None:prev=i;continue
            if prev is None:continue
            box=shift_box(grays[prev],grays[i],rows[prev]['box'])
            if box is not None:rows[i]={'f':i,'box':[round(v,1) for v in box],'src':'track'};prev=i
    for i,r in enumerate(rows):
        if r is None or 'eyes' in r or use_yunet:continue
        e=eyes_in(grays[i],r['box'])
        if e is not None:r['eyes']=[[round(v,1) for v in p] for p in e];r['eyes_src']='det'
    for direction in (1,-1):   # carry landmarks into frames where detection failed
        order=range(len(files)) if direction==1 else range(len(files)-1,-1,-1)
        prev=None
        for i in order:
            r=rows[i]
            if r is None:prev=None;continue
            if 'eyes' in r:prev=i;continue
            if prev is None:continue
            q=rows[prev];pts=q['eyes']+([q['nose']]+q['mouth'] if 'mouth' in q else [])
            p1,good=track_points(grays[prev],grays[i],pts)
            if good is not None and good.all():
                pts=[[round(float(v),1) for v in pt] for pt in p1];r['eyes']=pts[:2];r['eyes_src']='track';prev=i
                if len(pts)==5:r['nose']=pts[2];r['mouth']=pts[3:5]
    for r in rows:
        if r is not None and 'eyes' not in r:
            x,y,w,h=r['box'];r['eyes']=[[round(x+.3*w,1),round(y+.4*h,1)],[round(x+.7*w,1),round(y+.4*h,1)]];r['eyes_src']='estimate'
    # light temporal smoothing (3-frame weighted) of boxes and landmarks over runs of present rows
    keys=('box','eyes','nose','mouth')
    smoothed=[None if r is None else dict(r) for r in rows]
    for i,r in enumerate(rows):
        if r is None:continue
        for k in keys:
            if k not in r:continue
            acc=np.zeros_like(np.asarray(r[k],dtype=float));wsum=0
            for j,wt in ((i-1,.25),(i,.5),(i+1,.25)):
                if 0<=j<len(rows) and rows[j] is not None and k in rows[j]:acc+=wt*np.asarray(rows[j][k],dtype=float);wsum+=wt
            smoothed[i][k]=(acc/wsum).round(1).tolist()
    rows=smoothed
    write_json(out/'faces.json',rows)
    count=lambda key,val:sum(1 for r in rows if r is not None and r.get(key)==val)
    receipt={'frames':len(rows),'detected':sum(r is not None for r in rows),'by_source':{'det':count('src','det'),'track':count('src','track')},
             'eyes':{'det':count('eyes_src','det'),'track':count('eyes_src','track'),'estimate':count('eyes_src','estimate')},
             'detector':'yunet' if use_yunet else 'cascade',
             'classifiers':{p.name:digest(p) for p in (names+eye_names if not use_yunet else [YUNET])},'opencv':c.__version__,'quality_review':'pending',
             'landmarks':'eyes, nose tip and mouth corners (YuNet)' if use_yunet else 'eyes only (the cascade detector has no nose/mouth landmarks; use detector yunet)',
             'nose_mouth':count('eyes_src','det')+count('eyes_src','track') if use_yunet else 0,
             'source_hashes':{f.name:digest(f) for f in files},'clip_update':{'faces':relative+'/faces.json'}}
    write_json(out/'faces-receipt.json',receipt);return receipt

def _flow(c,a,b):
    """Dense flow a->b: DIS (medium preset with variational refinement) when available, Farneback otherwise."""
    try:
        dis=c.DISOpticalFlow_create(c.DISOPTICAL_FLOW_PRESET_MEDIUM)
        return dis.calc(a,b,None)
    except AttributeError:
        return c.calcOpticalFlowFarneback(a,b,None,.5,4,21,4,7,1.5,0)


def _pair_flows(a,b):
    c=cv();ag=c.cvtColor(a,c.COLOR_RGB2GRAY);bg=c.cvtColor(b,c.COLOR_RGB2GRAY)
    flow=_flow(c,ag,bg);back=_flow(c,bg,ag)
    cut=float(np.mean(np.abs(ag.astype(float)-bg.astype(float))))>65
    return flow,back,cut


def _sample(c,img,xx,yy,f):
    return c.remap(img,xx+f[:,:,0],yy+f[:,:,1],c.INTER_LINEAR,borderMode=c.BORDER_REPLICATE)


def _warp_blend(a,b,flow,back,u):
    """In-between at time u (audit F-OK-006): intermediate flows from both directions, forward-backward visibility
    weights, and a near-hard choice of the temporally closer frame where the two warps disagree (no double edges)."""
    c=cv();h,w=a.shape[:2];yy,xx=np.mgrid[:h,:w].astype('float32')
    ft0=(-(1-u)*u*flow+u*u*back).astype('float32')          # flow from time u back to frame a
    ft1=((1-u)*(1-u)*flow-u*(1-u)*back).astype('float32')   # flow from time u forward to frame b
    wa=_sample(c,a,xx,yy,ft0).astype('float32');wb=_sample(c,b,xx,yy,ft1).astype('float32')
    # forward-backward error at each frame, carried to time u with the same sampling
    occ_a=np.linalg.norm(flow+_sample(c,back,xx,yy,flow),axis=2);occ_b=np.linalg.norm(back+_sample(c,flow,xx,yy,back),axis=2)
    va=np.exp(-(_sample(c,occ_a.astype('float32'),xx,yy,ft0)/2.0)**2);vb=np.exp(-(_sample(c,occ_b.astype('float32'),xx,yy,ft1)/2.0)**2)
    ka=(1-u)*va+1e-4;kb=u*vb+1e-4;alpha=kb/(ka+kb)
    diff=np.abs(wa-wb).mean(axis=2) if wa.ndim==3 else np.abs(wa-wb)
    sharp=1+np.clip(diff-12,0,None)/6                        # disagreement -> pick one source instead of mixing
    alpha=np.clip((alpha-.5)*sharp+.5,0,1).astype('float32')
    alpha=c.GaussianBlur(alpha,(0,0),2)                      # smooth the choice so it never tears pixel by pixel
    if wa.ndim==3:alpha=alpha[:,:,None]
    return np.clip(wa*(1-alpha)+wb*alpha,0,255).astype('uint8')


def interpolate_pair(a,b,multiplier,masks=None,flows=None):
    """Yield `multiplier` frames from a towards b (a first). With masks=(ma,mb) yields (frame, mask) pairs where
    the mask is warped with the same flow, so mattes stay aligned with the interpolated picture."""
    flow,back,cut=flows or _pair_flows(a,b)
    for j in range(multiplier):
        u=j/multiplier
        if j==0 or cut:frame,mask=a,(masks[0] if masks else None)
        else:frame,mask=_warp_blend(a,b,flow,back,u),(_warp_blend(masks[0],masks[1],flow,back,u) if masks else None)
        yield (frame,mask) if masks else frame


def _lerp_face(r0,r1,u):
    """Interpolate a supplied face-track entry between two source frames (u in [0,1))."""
    if u==0 or r0 is None or r1 is None or r0.get('box') is None or r1.get('box') is None:
        return dict(r0) if (u==0 and r0) else None
    out={}
    for key in ('box','eyes','nose','mouth'):
        p,q=r0.get(key),r1.get(key)
        if p is None or q is None:continue
        out[key]=(np.asarray(p,dtype=float)*(1-u)+np.asarray(q,dtype=float)*u).round(3).tolist()
    if r0.get('score') is not None and r1.get('score') is not None:out['score']=min(r0['score'],r1['score'])
    out['src']='interp'
    return out


def interpolate(timeline,clip_id,out,multiplier=2):
    """Optical-flow frame interpolation (DIS flow, visibility-weighted warp). Output frame j shows source time j/(fps*multiplier); the last source
    frame is held so duration is unchanged. A clip's mask_dir is warped with the same flow and its face track is
    re-derived (linear between source detections), so annotations survive; nothing is silently dropped."""
    relative=output_path(timeline,out)
    clip,files=clip_at(timeline,clip_id);number(multiplier,'multiplier',2,8,integer=True)
    root=timeline.resolve().parent
    mask_files=[local_path(root,clip['mask_dir'])/f'{i:05d}.png' for i in range(clip['n'])] if clip.get('mask_dir') else None
    if mask_files and not all(f.is_file() for f in mask_files):raise ContractError('Clip mask_dir is incomplete; cannot carry the matte through interpolation')
    rows=None
    if clip.get('faces'):
        from .faces import read_track
        rows=read_track(root,clip)
    out.mkdir(parents=True,exist_ok=False);index=0
    if mask_files:(out/'mask').mkdir()
    def load(f):return np.array(Image.open(f).convert('RGB'))
    def load_mask(f):return np.array(Image.open(f).convert('RGBA'))[:,:,3]
    a=load(files[0]);ma=load_mask(mask_files[0]) if mask_files else None;cuts=[]
    for k in range(len(files)):
        nxt=min(k+1,len(files)-1);b=load(files[nxt]);mb=load_mask(mask_files[nxt]) if mask_files else None
        flows=_pair_flows(a,b)
        if flows[2] and k<len(files)-1:cuts.append(k)
        for item in interpolate_pair(a,b,multiplier,(ma,mb) if mask_files else None,flows):
            frame,matte=item if mask_files else (item,None)
            Image.fromarray(frame).save(out/f'{index:05d}.png')
            if matte is not None:
                m=Image.new('RGBA',(matte.shape[1],matte.shape[0]),'white');m.putalpha(Image.fromarray(matte,'L'));m.save(out/'mask'/f'{index:05d}.png')
            index+=1
        a,ma=b,mb
    result={**clip,'frames_dir':relative,'n':index,'fps':clip['fps']*multiplier,'pattern':'%05d.png'}
    carried={}
    if mask_files:result['mask_dir']=relative+'/mask';carried['mask_dir']='warped with the interpolation flow'
    if rows is not None:
        track=[]
        for j in range(index):
            k,i=divmod(j,multiplier);u=0 if (k in cuts or k>=len(rows)-1) else i/multiplier
            e=_lerp_face(rows[min(k,len(rows)-1)],rows[min(k+1,len(rows)-1)],u)
            if e is not None:e['f']=j
            track.append(e)
        write_json(out/'faces.json',track);result['faces']=relative+'/faces.json';carried['faces']='re-derived by linear interpolation of the supplied track'
    write_json(out/'interpolation.json',{'method':'DIS optical flow; intermediate flows from both directions; forward-backward visibility weighting; closer frame chosen where warps disagree','multiplier':multiplier,'clip':result,'carried':carried,'cut_pairs':cuts,
        'source_hashes':{f.name:digest(f) for f in files},'quality_review':'pending'})
    return result


def _cadence(frames,threshold):
    """Consecutive-frame difference (mean absolute, 8-bit, on a <=480 px grey copy) and repeat runs. A repeat is a
    frame whose difference to the previous one is <= threshold (a baked duplicate, e.g. 24p conformed to 30p by
    repeating every fifth frame)."""
    c=cv();small=[]
    for f in frames:
        g=c.cvtColor(f,c.COLOR_RGB2GRAY);s=min(1,480/g.shape[1])
        small.append(c.resize(g,(max(1,round(g.shape[1]*s)),max(1,round(g.shape[0]*s))),interpolation=c.INTER_AREA).astype('float32'))
    diffs=[float(np.abs(small[i]-small[i-1]).mean()) for i in range(1,len(small))]
    runs=[[0,1]]
    for i,d in enumerate(diffs,1):
        if d<=threshold:runs[-1][1]+=1
        else:runs.append([i,1])
    return diffs,runs


def _pair_motion(frames):
    """How far each step between consecutive pictures moves: mean optical-flow magnitude over the most textured 20 %
    of pixels (where flow is meaningful; works for camera moves and for small moving subjects), in px of the frame's
    own width, from <=480 px grey copies."""
    c=cv();small=[]
    for f in frames:
        g=c.cvtColor(f,c.COLOR_RGB2GRAY);sc=min(1,480/g.shape[1])
        small.append(c.resize(g,(max(1,round(g.shape[1]*sc)),max(1,round(g.shape[0]*sc))),interpolation=c.INTER_AREA))
    scale=frames[0].shape[1]/small[0].shape[1];out=[]
    for k in range(len(small)-1):
        a=small[k].astype('float32');grad=np.hypot(c.Sobel(a,c.CV_32F,1,0),c.Sobel(a,c.CV_32F,0,1))
        sel=grad>=np.quantile(grad,.8)
        mag=np.linalg.norm(_flow(c,small[k],small[k+1]),axis=2)
        out.append(float(mag[sel].mean() if sel.any() else mag.mean())*scale+1e-3)
    return out


def retime(timeline,clip_id,out,start,seconds,output_frames,fps=None,take_start=None,take_seconds=None,
           deduplicate=False,duplicate_threshold=.5,timing=None):
    """Motion-compensated slow motion as a plate: exactly `output_frames` pictures at `fps` covering the clip's
    source interval [start, start+seconds) (seconds of the clip). Output frame j shows source time
    start+(j+.5)*seconds/output_frames, warped between the two source pictures around that time (DIS flow, the same
    visibility-weighted warp as `interpolate`), so every output frame is a new picture at an even step - no
    multiplier, no re-sampling, no frame blending. Use the plate in a shot at speed 1 from src 0.

    The take window [take_start, take_start+take_seconds) (default: the whole clip) bounds the frames that may be
    used; it must be a single take (a hard cut inside it is refused). deduplicate collapses runs of baked repeats
    (difference <= duplicate_threshold) into one picture each; leave it off for intentional holds. timing places the
    collapsed pictures: 'even' (default with deduplicate) spaces them uniformly over the take, i.e. assumes the
    footage was shot at a constant rate and only conformed by repeating frames (24p in 30p); 'run_centre' times each
    at the centre of its repeat run (an estimate that keeps irregular cadences); 'motion' (with or without
    deduplicate) times each picture by its measured motion relative to its 5-pair neighbourhood, which evens out
    uneven conversion cadences (e.g. frame-blended 24p in 30p: three large steps, two small) while keeping slower
    speed changes - review it: it assumes motion is locally steady. The receipt reports the cadence,
    repeat runs, unique pictures per second, pictures held at the window edges and pairs that fell back to the
    nearer picture. Output times before the first or after the last picture's time hold that picture and are listed
    in held_output_frames: keep the interval inside the take's picture times (e.g. start at least half a source frame
    after the take start) for motion on every frame."""
    relative=output_path(timeline,out)
    clip,files=clip_at(timeline,clip_id)
    if clip.get('mask_dir') or clip.get('faces'):
        raise ContractError('retime does not carry mattes or face tracks; retime the plain clip and analyse the plate')
    edit=json.loads(timeline.read_text(encoding='utf-8'))
    src_fps=float(clip['fps']);fps=float(fps if fps is not None else edit['canvas']['fps'])
    number(fps,'fps',1,240);number(output_frames,'output_frames',2,7200,integer=True)
    number(seconds,'seconds',1e-6,600);number(start,'start',0,clip['n']/src_fps)
    number(duplicate_threshold,'duplicate_threshold',0,2)
    take_start=0.0 if take_start is None else float(take_start)
    take_end=clip['n']/src_fps if take_seconds is None else take_start+float(take_seconds)
    i0=int(round(take_start*src_fps));i1=min(clip['n'],int(round(take_end*src_fps)))
    if not 0<=i0<i1-1:raise ContractError('The take window must contain at least two source frames of the clip')
    if start<i0/src_fps-1e-9 or start+seconds>i1/src_fps+1e-9:
        raise ContractError(f'The source interval {start:.4f}-{start+seconds:.4f} s lies outside the take window '
                            f'{i0/src_fps:.4f}-{i1/src_fps:.4f} s')
    def load(f):return np.array(Image.open(f).convert('RGB'))
    frames=[load(files[i]) for i in range(i0,i1)]
    diffs,runs=_cadence(frames,duplicate_threshold)
    c=cv()
    for k,d in enumerate(diffs):
        a=c.cvtColor(frames[k],c.COLOR_RGB2GRAY).astype(float);b=c.cvtColor(frames[k+1],c.COLOR_RGB2GRAY).astype(float)
        if float(np.mean(np.abs(a-b)))>65:
            raise ContractError(f'Hard cut inside the take window between clip frames {i0+k} and {i0+k+1}; '
                                'narrow take_start/take_seconds to one take')
    # pictures and the source time each represents (frame centre; run centre when repeats are collapsed)
    timing=timing or ('even' if deduplicate else 'frame_centre')
    if timing not in ('even','run_centre','frame_centre','motion'):raise ContractError('timing: use even, run_centre, frame_centre or motion')
    if timing in ('even','run_centre') and not deduplicate:raise ContractError('timing even/run_centre applies to deduplicated pictures')
    motion=None
    if timing=='frame_centre':pictures=[(i0+k,(i0+k+.5)/src_fps) for k in range(len(frames))]
    elif timing=='motion':
        idx=[s for s,_ in runs] if deduplicate else list(range(len(frames)))
        motion=_pair_motion([frames[i] for i in idx])
        local=[float(np.mean(motion[max(0,k-2):k+3])) for k in range(len(motion))]
        steps=np.clip(np.array([m/max(l,1e-6) for m,l in zip(motion,local)]),.2,5)
        first=(i0+(idx[0]+(runs[0][1] if deduplicate else 1)/2))/src_fps;last=(i0+idx[-1]+(runs[-1][1] if deduplicate else 1)/2)/src_fps
        cum=np.concatenate([[0],np.cumsum(steps)]);cum=cum/cum[-1]
        pictures=[(i0+i,first+(last-first)*float(cum[k])) for k,i in enumerate(idx)]
    elif timing=='run_centre':pictures=[(i0+s,(i0+s+n/2)/src_fps) for s,n in runs]
    else:
        step=(i1-i0)/len(runs)
        pictures=[(i0+s,(i0+(k+.5)*step)/src_fps) for k,(s,n) in enumerate(runs)]
    times=[t for _,t in pictures]
    out.mkdir(parents=True,exist_ok=False)
    flows={};held=[];fallback=set()
    for j in range(output_frames):
        t=start+(j+.5)*seconds/output_frames
        if t<=times[0] or t>=times[-1]:
            k=0 if t<=times[0] else len(pictures)-1
            if abs(t-times[k])>1e-9:held.append(j)   # before the first / after the last picture: a held frame
            frame=frames[pictures[k][0]-i0]
        else:
            k=int(np.searchsorted(times,t,side='right'))-1
            u=(t-times[k])/(times[k+1]-times[k])
            a=frames[pictures[k][0]-i0];b=frames[pictures[k+1][0]-i0]
            if u<1e-3:frame=a
            elif u>1-1e-3:frame=b
            else:
                if k not in flows:flows={k:_pair_flows(a,b)}   # pairs are visited in order; keep one
                flow,back,cut=flows[k]
                if cut:fallback.add(pictures[k][0]);frame=a if u<.5 else b
                else:frame=_warp_blend(a,b,flow,back,u)
        Image.fromarray(frame).save(out/f'{j:05d}.png')
    h,w=frames[0].shape[:2]
    result={'frames_dir':relative,'n':output_frames,'fps':fps,'w':w,'h':h,'pattern':'%05d.png'}
    unique=len(runs);take_s=(i1-i0)/src_fps
    write_json(out/'retime.json',{
        'method':'exact-time optical-flow retime: output frame j = source time start+(j+.5)*seconds/output_frames; DIS flow, '
                 'intermediate flows from both directions, forward-backward visibility weighting',
        'clip':result,'source_clip':clip_id,'source_fps':src_fps,'start':start,'seconds':seconds,'output_frames':output_frames,
        'fps':fps,'effective_speed':round(seconds/(output_frames/fps),6),
        'take':{'start':i0/src_fps,'end':i1/src_fps,'frames':[i0,i1]},
        'cadence':{'frame_differences':[round(d,3) for d in diffs],'repeat_runs':[[i0+s,n] for s,n in runs if n>1],
                   'unique_pictures':unique,'unique_pictures_per_second':round(unique/take_s,3),'duplicate_threshold':duplicate_threshold,
                   'deduplicated':bool(deduplicate),'timing':timing,
                   **({'pair_motion_px':[round(m,2) for m in motion],'picture_times':[round(t,5) for t in times]} if motion is not None else {})},
        'held_output_frames':held,'fallback_pairs':sorted(fallback),
        'source_hashes':{files[i].name:digest(files[i]) for i in range(i0,i1)},'quality_review':'pending'})
    return result
