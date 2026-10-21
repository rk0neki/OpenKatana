"""Original local image registration and piecewise-affine morph, using installed OpenCV."""
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from .contracts import ContractError
from .render import digest, encode, write_json
from .scene3d import num


def correspondence(a, b, points=None):
    import cv2
    h,w=a.shape[:2]
    if points is not None:
        if not isinstance(points,dict) or set(points)!={'source','target'}:
            raise ContractError('Points must contain source and target lists of normalized [x,y] pairs')
        pa,pb=np.asarray(points['source'],dtype=np.float32),np.asarray(points['target'],dtype=np.float32)
        if pa.shape!=pb.shape or pa.ndim!=2 or pa.shape[1]!=2 or not 3<=len(pa)<=128 or not np.isfinite(pa).all() or not np.isfinite(pb).all():
            raise ContractError('Supply 3..128 paired finite 2D landmarks')
        if (pa<=0).any() or (pa>=1).any() or (pb<=0).any() or (pb>=1).any():
            raise ContractError('Landmarks must be strictly inside 0..1; canvas corners are fixed automatically')
        pa=pa*[w-1,h-1];pb=pb*[w-1,h-1];method='explicit landmarks'
    else:
        detector=cv2.ORB_create(nfeatures=2000)
        ka,da=detector.detectAndCompute(cv2.cvtColor(a,cv2.COLOR_RGB2GRAY),None)
        kb,db=detector.detectAndCompute(cv2.cvtColor(b,cv2.COLOR_RGB2GRAY),None)
        if da is None or db is None:raise ContractError('No reliable image features; provide explicit landmarks')
        matches=cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(da,db,k=2)
        good=[m for pair in matches if len(pair)==2 for m,n in [pair] if m.distance<.7*n.distance]
        if len(good)<8:raise ContractError('Too few reliable feature matches; provide explicit landmarks')
        pa=np.float32([ka[m.queryIdx].pt for m in good]);pb=np.float32([kb[m.trainIdx].pt for m in good])
        _,mask=cv2.findHomography(pa,pb,cv2.RANSAC,3.)
        if mask is None or mask.sum()<8:raise ContractError('Feature registration failed; provide explicit landmarks')
        pa,pb=pa[mask.ravel().astype(bool)],pb[mask.ravel().astype(bool)];method='ORB + RANSAC inliers (geometric, not semantic)'
    accepted=[]
    for x,y in zip(pa,pb):
        if min(*x,*y)<2 or max(x[0],y[0])>w-3 or max(x[1],y[1])>h-3:continue
        if all(np.linalg.norm(x-u)>3 and np.linalg.norm(y-v)>3 and np.linalg.norm((x+y-u-v)/2)>3 for u,v in accepted):
            accepted.append((x,y))
        if len(accepted)>=128:break
    if len(accepted)<3:raise ContractError('Too few distinct interior landmarks after filtering')
    corners=np.float32([[0,0],[w-1,0],[w-1,h-1],[0,h-1]])
    pa=np.float32([*corners,*(x for x,y in accepted)]);pb=np.float32([*corners,*(y for x,y in accepted)])
    mid=(pa+pb)/2;sub=cv2.Subdiv2D((0,0,w,h))
    for p in mid:sub.insert(tuple(map(float,p)))
    triangles=[]
    for triangle in sub.getTriangleList():
        p=triangle.reshape(3,2);ids=[int(np.argmin(np.linalg.norm(mid-q,axis=1))) for q in p]
        if len(set(ids))==3 and max(np.linalg.norm(mid[i]-q) for i,q in zip(ids,p))<.1:triangles.append(ids)
    return pa,pb,triangles,method


def morph_images(source,target,out,width=512,height=512,fps=30,frames=60,points=None):
    try:import cv2
    except ImportError as e:raise ContractError('Install the OpenKatana vision extra for image morphs') from e
    num(width,'width',32,4096,True);num(height,'height',32,4096,True)
    num(fps,'fps',1,120,True);num(frames,'frames',2,3600,True)
    if width%2 or height%2:raise ContractError('Use even morph dimensions')
    source,target,out=Path(source).resolve(),Path(target).resolve(),Path(out).resolve()
    def load(p):
        with Image.open(p) as im:
            im=ImageOps.exif_transpose(im).convert('RGB')
            # Deliberate fit; preserve aspect by padding, never stretch the inputs.
            return np.array(ImageOps.pad(im,(width,height),method=Image.Resampling.LANCZOS,color='#000000'))
    sha={'source':digest(source),'target':digest(target)}
    a,b=load(source),load(target);pa,pb,triangles,method=correspondence(a,b,points)
    def signed(p):
        x,y,z=p;return (y[0]-x[0])*(z[1]-x[1])-(y[1]-x[1])*(z[0]-x[0])
    for f in range(frames):
        t=f/(frames-1);p=pa*(1-t)+pb*t
        for tri in triangles:
            area=signed(p[tri]);initial=signed(pa[tri])
            if abs(area)<.02 or area*initial<=0:
                raise ContractError(f'Landmarks fold/collapse a triangle at frame {f}; revise correspondence')
    out.mkdir(parents=True,exist_ok=False);(out/'frames').mkdir()
    for f in range(frames):
        t=f/(frames-1)
        if f==0:result=a
        elif f==frames-1:result=b
        else:
            p=pa*(1-t)+pb*t;result=np.zeros_like(a,dtype=np.float32);coverage=np.zeros((height,width),np.float32)
            for tri in triangles:
                q=p[tri];x,y,w,h=cv2.boundingRect(q)
                x0,y0=max(x,0),max(y,0);x1,y1=min(x+w,width),min(y+h,height)
                local=q-np.float32([x0,y0]);size=(x1-x0,y1-y0)
                if min(size)<=0:continue
                wa=cv2.warpAffine(a,cv2.getAffineTransform(pa[tri],local),size,flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT_101)
                wb=cv2.warpAffine(b,cv2.getAffineTransform(pb[tri],local),size,flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT_101)
                mask=np.zeros((size[1],size[0]),np.float32);cv2.fillConvexPoly(mask,np.round(local*256).astype(np.int32),1.,shift=8)
                result[y0:y1,x0:x1]+=(wa*(1-t)+wb*t)*mask[...,None];coverage[y0:y1,x0:x1]+=mask
            if np.any(coverage==0):raise ContractError('Morph triangulation left uncovered pixels')
            result=np.clip(result/coverage[...,None],0,255).round().astype(np.uint8)
        Image.fromarray(result).save(out/'frames'/f'{f:05d}.png')
    encode(out/'frames',{'frames':frames,'fps':fps},out/'video.mp4')
    if sha!={'source':digest(source),'target':digest(target)}:raise ContractError('Morph inputs changed during processing')
    receipt={'method':method,'source':str(source),'target':str(target),'input_sha256':sha,
             'points':{'source':pa.tolist(),'target':pb.tolist()},'triangles':triangles,
             'video':str(out/'video.mp4'),'clip':{'frames_dir':str(out/'frames'),'pattern':'%05d.png','n':frames,'fps':fps,'w':width,'h':height},
             'preview_images':[str(out/'frames'/f'{f:05d}.png') for f in (0,frames//2,frames-1)],
             'credits_used':0,'limits':'Geometric image warp and color blend, not semantic video generation; inspect matching and intermediates.'}
    write_json(out/'receipt.json',receipt);return receipt
