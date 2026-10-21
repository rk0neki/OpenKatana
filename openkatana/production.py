"""Portable animation production utilities."""
import json
import math
from pathlib import Path
import shutil
import wave

import numpy as np
from PIL import Image

from .contracts import ContractError, fields, local_path, number, validate
from .render import digest, write_json


def display_atlas(document, out):
    """Pack frame-indexed RGB masks from explicitly scheduled LED text cues."""
    from .dotfont import line_bitmap
    fields(document,'cols rows frames fps tiles_x cues','display')
    for key,low,high in (('cols',1,512),('rows',1,256),('frames',1,36000),('fps',1,240),('tiles_x',1,256)):
        number(document.get(key),key,low,high,integer=True)
    cols,rows,n,tx=(document[k] for k in ('cols','rows','frames','tiles_x'))
    ty=math.ceil(n/tx)
    if cols*tx>16384 or rows*ty>16384 or cols*tx*rows*ty>64_000_000:
        raise ContractError('Atlas exceeds 64M pixels or 16384 pixels per side; split the sequence')
    cues=document.get('cues')
    if not isinstance(cues,list) or len(cues)>1000: raise ContractError('Supply at most 1000 text cues')
    prepared=[]
    for cue in cues:
        fields(cue,'start end text channel reveal_frames','display cue')
        number(cue.get('start'),'start',0,n-1,integer=True)
        number(cue.get('end'),'end',cue['start']+1,n,integer=True)
        channel=cue.get('channel',0);reveal=cue.get('reveal_frames',0)
        number(channel,'channel',0,2,integer=True);number(reveal,'reveal_frames',0,cue['end']-cue['start'],integer=True)
        if not isinstance(cue.get('text'),str) or not cue['text']: raise ContractError('Cue needs nonempty text')
        try: bm,_=line_bitmap(cue['text'])
        except ValueError as e: raise ContractError(str(e)) from e
        if bm.shape[0]>rows or bm.shape[1]>cols: raise ContractError('LED text overflows; enlarge grid or shorten text')
        prepared.append((cue,bm,channel,reveal))
    canvas=np.zeros((rows*ty,cols*tx,3),np.uint8)
    for f in range(n):
        tile=canvas[(f//tx)*rows:(f//tx+1)*rows,(f%tx)*cols:(f%tx+1)*cols]
        for cue,bm,ch,reveal in prepared:
            if not cue['start']<=f<cue['end']: continue
            h,w=bm.shape;y=(rows-h)//2;x=(cols-w)//2
            visible=w if reveal==0 else min(w,math.ceil(w*(f-cue['start']+1)/reveal))
            tile[y:y+h,x:x+visible,ch]=np.maximum(tile[y:y+h,x:x+visible,ch],(bm[:,:visible]*255).astype(np.uint8))
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    Image.fromarray(canvas).save(out/'atlas.png')
    receipt={'atlas':str(out/'atlas.png'),'sha256':digest(out/'atlas.png'),'tiles':[tx,ty],
             'cols':cols,'rows':rows,'frames':n,'fps':document['fps'],
             'document':document,'channels':'RGB masks, colors applied by led_material',
             'limits':'Small original LED glyph inventory; full text shaping uses compositions'}
    write_json(out/'receipt.json',receipt)
    return receipt


def synthesize_score(document,out):
    """Deterministic original oscillator/noise score; explicit note events, not an AI music model."""
    fields(document,'duration sample_rate seed notes','score')
    duration=number(document.get('duration'),'duration',.05,180)
    sr=document.get('sample_rate',48000);number(sr,'sample_rate',8000,96000,integer=True)
    seed=document.get('seed',0);number(seed,'seed',0,2**32-1,integer=True)
    notes=document.get('notes')
    if not isinstance(notes,list) or not 1<=len(notes)<=10000: raise ContractError('Supply 1..10000 note events')
    prepared=[]
    for event in notes:
        fields(event,'at duration midi gain waveform pan attack release','note')
        at=number(event.get('at'),'at',0,duration)
        length=number(event.get('duration'),'note duration',.005,duration)
        if at+length>duration+1e-9: raise ContractError('Note exceeds score duration')
        midi=number(event.get('midi',60),'midi',0,127)
        gain=number(event.get('gain',.2),'gain',0,1);pan=number(event.get('pan',0),'pan',-1,1)
        attack=number(event.get('attack',min(.01,length/4)),'attack',0,length)
        release=number(event.get('release',min(.05,length/4)),'release',0,length)
        if attack+release>length: raise ContractError('Attack and release exceed note duration')
        kind=event.get('waveform','sine')
        if kind not in ('sine','triangle','bell','noise'): raise ContractError('Unsupported oscillator')
        frequency=440*2**((midi-69)/12)
        if kind!='noise' and frequency*(2 if kind=='bell' else 1)>=sr/2:
            raise ContractError('Note exceeds oscillator Nyquist limit')
        prepared.append((at,length,frequency,gain,pan,attack,release,kind))
    mix=np.zeros((round(duration*sr),2),np.float64);rng=np.random.default_rng(seed)
    for at,length,freq,gain,pan,attack,release,kind in prepared:
        start=round(at*sr);n=min(round(length*sr),len(mix)-start);t=np.arange(n)/sr
        phase=2*np.pi*freq*t
        if kind=='sine': signal=np.sin(phase)
        elif kind=='triangle':
            signal=np.zeros(n)
            for h in range(1,min(63,int((sr/2-1e-9)/freq))+1,2): signal+=(-1)**((h-1)//2)*np.sin(h*phase)/(h*h)
            signal*=8/(np.pi*np.pi)
        elif kind=='bell': signal=(np.sin(phase)+.35*np.sin(phase*2))*np.exp(-5*t/length)
        else: signal=rng.normal(0,.25,n)
        env=np.ones(n);a=min(n,round(attack*sr));r=min(n-a,round(release*sr))
        if a: env[:a]*=np.linspace(0,1,a)
        if r: env[-r:]*=np.linspace(1,0,r)
        stereo=np.array([math.cos((pan+1)*math.pi/4),math.sin((pan+1)*math.pi/4)])
        mix[start:start+n]+=signal[:,None]*env[:,None]*gain*stereo
    peak=float(np.max(np.abs(mix)));normalization=min(1,.95/max(peak,1e-12));mix*=normalization
    pcm=(mix*32767).round().astype('<i2')
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    with wave.open(str(out/'score.wav'),'wb') as f:
        f.setnchannels(2);f.setsampwidth(2);f.setframerate(sr);f.writeframes(pcm.tobytes())
    receipt={'audio':str(out/'score.wav'),'sha256':digest(out/'score.wav'),'samples':len(pcm),
             'sample_rate':sr,'normalization':normalization,'document':document,
             'credits_used':0,'method':'Original local oscillator/noise synthesis; not an AI music model',
             'preview_audio':[str(out/'score.wav')]}
    write_json(out/'receipt.json',receipt);return receipt


def assemble_chunks(root,receipts,out,contiguous=True):
    """Build a validated timeline proposal from ordered Blender/WebGL receipts, never overwrite a timeline."""
    if type(contiguous) is not bool: raise ContractError('contiguous must be boolean')
    if not isinstance(receipts,list) or not 1<=len(receipts)<=1000: raise ContractError('Supply ordered receipt paths')
    if len(set(receipts))!=len(receipts): raise ContractError('Duplicate receipt; provide each chunk once')
    clips={};shots=[];records=[];last=None;total=0;canvas=None
    for i,rel in enumerate(receipts):
        path=local_path(root,rel);r=json.loads(path.read_text(encoding='utf8'))
        for key in ('width','height','fps','frames','source_frame_start','source_frame_end','clip','source_sha256'):
            if key not in r: raise ContractError('Not a complete render receipt: missing '+key)
        for key in ('width','height','frames'): number(r[key],key,1,36000,integer=True)
        number(r['fps'],'fps',1,120)
        for key in ('source_frame_start','source_frame_end'): number(r[key],key,0,100000,integer=True)
        if r['source_frame_end']-r['source_frame_start']+1!=r['frames']: raise ContractError('Receipt range/count disagree')
        shape=(r['width'],r['height'],r['fps'])
        if canvas is not None and shape!=canvas: raise ContractError('Chunk dimensions/fps differ; explicitly conform first')
        canvas=shape
        if contiguous and last and (r['source_frame_start']!=last['source_frame_end']+1 or r['source_sha256']!=last['source_sha256']):
            raise ContractError('Chunks have a gap/overlap or different source scripts; use contiguous=false for independent shots')
        if contiguous and last and r.get('implementation') != last.get('implementation'):
            raise ContractError('Chunks used different renderer implementations')
        clip=r['clip'];folder=local_path(root,clip['frames_dir'])
        if clip.get('pattern','%05d.png')!='%05d.png': raise ContractError('Unsupported render frame naming')
        if (clip.get('w'),clip.get('h'),clip.get('fps'),clip.get('n'))!=(*shape,r['frames']):
            raise ContractError('Receipt clip metadata disagree')
        hashes=[]
        for f in range(r['frames']):
            frame=folder/f'{f:05d}.png'
            if not frame.is_file(): raise ContractError('Missing render frame '+str(f))
            with Image.open(frame) as im:
                if im.size!=shape[:2]: raise ContractError('Frame dimensions differ from receipt')
            hashes.append(digest(frame))
        key=f'chunk_{i:03d}'
        clips[key]={'frames_dir':folder.relative_to(root).as_posix(),'n':r['frames'],'fps':r['fps'],
                    'w':r['width'],'h':r['height'],'pattern':'%05d.png'}
        shots.append({'f0':total,'f1':total+r['frames'],'clip':key,'srcf':0,'speed':1})
        records.append({'receipt':rel,'sha256':digest(path),'frames_sha256':hashes})
        total+=r['frames'];last=r
        if total>36000: raise ContractError('Assemble at most 36000 frames')
    timeline={'canvas':{'w':canvas[0],'h':canvas[1],'fps':canvas[2],'frames':total,'bg':'#000000'},'clips':clips,'shots':shots}
    validate(timeline,root)
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    write_json(out/'timeline.json',timeline);write_json(out/'inputs.json',records)
    return {'timeline':timeline,'path':str(out/'timeline.json'),'manifest':str(out/'inputs.json'),
            'saved_to_project':False,'frames':total,'credits_used':0,'next':'Preview and revision-guarded save_timeline; add project audio and overlays explicitly'}


def create_kit(root,directory,width=640,height=360,fps=30,frames=60):
    for v,k,low,high in ((width,'width',64,7680),(height,'height',64,7680),(fps,'fps',1,120),(frames,'frames',6,36000)):
        number(v,k,low,high,integer=True)
    if width%2 or height%2: raise ContractError('Video dimensions must be even')
    out=local_path(root,directory)
    if out.exists(): raise FileExistsError('Animation kit destination already exists')
    mid=frames//2
    pose=lambda pos,tgt:[{'pos':pos,'tgt':tgt,'lens':40,'fstop':5.6}]
    segments=[{'f0':0,'f1':mid,'type':'push','poses':pose([2.8,-4,2],[0,0,.5])+pose([1,-4,1.2],[0,0,.5])},
              {'f0':mid,'f1':frames-1,'type':'hold','cut':True,'poses':pose([-2,-4,1.5],[0,0,.5])+pose([-1.7,-4,1.4],[0,0,.5])}]
    config={'width':width,'height':height,'fps':fps,'schedule_fps':fps,'frames':frames,
            'camera_segments':segments,'colors':{'body':'#295F87','accent':'#E9AD57'},'shutter':.5}
    # Replaceable example content for authored animation.
    display={'cols':32,'rows':9,'frames':frames,'fps':fps,'tiles_x':min(frames,32),
             'cues':[{'start':0,'end':mid,'text':'GO','reveal_frames':min(4,mid)},
                     {'start':mid,'end':frames,'text':'PLAY','channel':1}]}
    # Validate allocation before creating a destination.
    if 9*math.ceil(frames/display['tiles_x'])>16384: raise ContractError('Display sequence too large')
    out.mkdir(parents=True)
    write_json(out/'config.json',config)
    write_json(out/'display.json',display)
    display_atlas(display,out/'display')
    score={'duration':min(180,frames/fps),'sample_rate':48000,'seed':0,
           'notes':[{'at':0,'duration':min(.25,frames/fps),'midi':60,'waveform':'bell','gain':.15}]}
    write_json(out/'score.json',score)
    shutil.copyfile(Path(__file__).with_name('templates')/'animation_scene.py',out/'scene.py')
    return {'directory':str(out),'script':(out/'scene.py').relative_to(root).as_posix(),
            'config':str(out/'config.json'),'display':str(out/'display/atlas.png'),
            'guide':'animation','credits_used':0,
            'next':'Edit original scene.py/config.json for the brief, then render_blender(trusted_script=true); Blender must already be installed'}
