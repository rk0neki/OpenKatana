"""Local project assets, original edit recipes, versioned saves and review records."""
import hashlib
import json
import shutil
import uuid
from datetime import datetime,timezone
from pathlib import Path
from .contracts import ContractError,local_path,validate
from .render import digest,write_json,prepare,probe

RECIPES={
    'Pulse':{'cam':{'push':{'v':.12}},'in':{'type':'flash','d':.1,'amt':.5}},
    'Drift':{'cam':{'handheld':{'amp':4,'hz':.45,'rot':.003},'cover':True}},
    'Cutline':{'in':{'type':'wipe','kind':'stripes','d':.3,'color':'#171923'}},
    'Afterglow':{'look':{'type':'grade','filter':'saturate(0.85) contrast(1.06)','layers':[{'op':'screen','color':'#ffbd85','alpha':.08}]}}
}

def stamp():return datetime.now(timezone.utc).isoformat()
def fingerprint(edit):return hashlib.sha256(json.dumps(edit,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def create(root,name='Untitled'):
    root.mkdir(parents=True,exist_ok=False)
    write_json(root/'project.json',{'schema':1,'name':name,'created_at':stamp(),'assets':[],'reviews':[],'release':'project review pending'})
    return state(root)

def state(root):
    value=json.loads((root/'project.json').read_text(encoding='utf-8'))
    if (root/'timeline.json').is_file():
        value['timeline']=json.loads((root/'timeline.json').read_text(encoding='utf-8'));value['revision']=fingerprint(value['timeline'])
    else:value.update(timeline=None,revision=None)
    value['recipes']=list(RECIPES);return value

def register(root,path,label=None,rights='review_pending'):
    path=path.resolve();root=root.resolve()
    if not path.is_relative_to(root):raise ContractError('Import media into the project first')
    data=state(root);asset={'id':uuid.uuid4().hex[:12],'name':label or path.name,'path':path.relative_to(root).as_posix(),'sha256':digest(path),'rights':rights}
    ext=path.suffix.lower()
    if ext in ('.png','.jpg','.jpeg','.webp'):
        from PIL import Image,ImageOps
        folder=root/'plates'/asset['id'];folder.mkdir(parents=True)
        im=ImageOps.exif_transpose(Image.open(path)).convert('RGB');im.save(folder/'00000.png')
        asset.update(kind='image',clip={'frames_dir':folder.relative_to(root).as_posix(),'n':1,'fps':30,'w':im.width,'h':im.height,'pattern':'%05d.png'})
    elif ext in ('.mp4','.mov','.mkv','.webm','.avi'):
        folder=root/'plates'/asset['id'];clip=prepare(path,folder);clip['frames_dir']=folder.relative_to(root).as_posix();asset.update(kind='video',clip=clip)
    elif ext in ('.wav','.mp3','.m4a','.flac','.ogg','.aac'):
        info=probe(path)
        if not any(s['codec_type']=='audio' for s in info['streams']):raise ContractError('No audio stream')
        asset.update(kind='audio',duration=float(info['format']['duration']))
    elif ext in ('.ttf','.otf','.woff','.woff2'):asset['kind']='font'
    else:raise ContractError('Unsupported media format')
    data['assets'].append(asset)
    for k in ('timeline','revision','recipes'):data.pop(k,None)
    write_json(root/'project.json',data);return asset

def import_asset(root,source,rights='review_pending'):
    folder=root/'media';folder.mkdir(exist_ok=True)
    name=uuid.uuid4().hex[:12]+source.suffix.lower();target=folder/name
    shutil.copyfile(source,target)
    from .bundled_fonts import copy_license
    lic=copy_license(source,target)
    asset=register(root,target,source.name,rights)
    if lic:
        # A bundled OFL font keeps its licence and copyright notice beside the project copy.
        data=state(root);row=next(a for a in data['assets'] if a['id']==asset['id']);row['license']=lic
        for k in ('timeline','revision','recipes'):data.pop(k,None)
        write_json(root/'project.json',data);asset['license']=lic
    return asset

def plan(root,asset_ids,recipe='Drift',seconds=3,width=1280,height=720,fps=30,caption=''):
    from .contracts import number
    number(seconds,'seconds per shot',.1,600);number(fps,'fps',1,120)
    if recipe not in RECIPES:raise ContractError('Unknown edit recipe')
    assets={a['id']:a for a in state(root)['assets']};clips={};shots=[];offset=0
    if not isinstance(asset_ids,list) or not asset_ids:raise ContractError('Select at least one video or image')
    for key in asset_ids:
        if key not in assets or 'clip' not in assets[key]:raise ContractError('Plan input must be imported video/image assets')
        a=assets[key];clips[key]=a['clip'];n=max(1,round(min(seconds,a['clip']['n']/a['clip']['fps'] if a['kind']=='video' else seconds)*fps))
        shots.append({'f0':offset,'f1':offset+n,'clip':key,'speed':0 if a['kind']=='image' else 1,**json.loads(json.dumps(RECIPES[recipe]))});offset+=n
    edit={'canvas':{'w':width,'h':height,'fps':fps,'frames':offset},'clips':clips,'shots':shots}
    if caption:edit['text']=[{'type':'graffiti','word':caption,'f0':0,'f1':min(offset,round(seconds*fps)),'region':'bottom','mode':'write'}]
    validate(edit,root);return {'timeline':edit,'decisions':['Source order follows your selection.','Video shots are limited to available footage.','Original OpenKatana recipe: '+recipe],'needs_review':True}

def save(root,edit,revision):
    validate(edit,root);lock=root/'timeline.json.lock';acquired=False
    try:
        with lock.open('x',encoding='utf-8'):
            acquired=True;data=state(root)
            if data['revision']!=revision:raise ContractError('Project changed since it was opened. Reload before saving')
            if data['timeline'] is not None:write_json(root/'history'/(data['revision']+'.json'),data['timeline'])
            write_json(root/'timeline.json',edit)
    except FileExistsError as e:raise ContractError('Timeline save is already in progress; inspect a stale lock before retrying') from e
    finally:
        if acquired:lock.unlink(missing_ok=True)
    return {'revision':fingerprint(edit)}

def review(root,job_dir,decision,notes=''):
    if decision not in ('approved','changes_requested'):raise ContractError('Unknown review decision')
    job=json.loads((job_dir/'job.json').read_text(encoding='utf-8'));receipt_path=job_dir/'render'/'receipt.json'
    if job.get('state')!='succeeded' or not receipt_path.is_file():raise ContractError('Review requires a completed render')
    receipt=json.loads(receipt_path.read_text(encoding='utf-8'));data=state(root)
    if digest(local_path(root,job['video']))!=receipt['sha256']:raise ContractError('Rendered video changed after verification')
    if job.get('revision')!=data['revision']:raise ContractError('Timeline changed after this render')
    for rel,sha in json.loads((job_dir/'render'/'input-manifest.json').read_text(encoding='utf-8')).items():
        if digest(local_path(root,rel))!=sha:raise ContractError('An input changed after rendering')
    result={'at':stamp(),'decision':decision,'notes':notes,'timeline_revision':data['revision'],'video_sha256':receipt['sha256'],'job_id':job['id']}
    data['reviews'].append(result)
    for k in ('timeline','revision','recipes'):data.pop(k,None)
    write_json(root/'project.json',data);return result
