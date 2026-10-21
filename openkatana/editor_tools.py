"""Local reference inspection. Estimates are never creative or human approval."""
import json
import math
import os
from pathlib import Path
import re
import subprocess
from PIL import Image,ImageDraw,ImageFont,ImageOps
from .contracts import ContractError,fields,number,local_path
from .render import digest,run,write_json
from .preview import source_frames


def metadata(source):
    return json.loads(run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',source]))


def contact_sheet(source,out,start,end,step,columns):
    info=metadata(source);total=float(info['format'].get('duration',0))
    number(start,'start',0);number(step,'step',.01);number(columns,'columns',1,6,integer=True)
    end=total if end is None else end
    number(end,'end',start+.001)
    if total and end>total+.001:raise ContractError('Contact sheet extends beyond source duration')
    count=math.ceil((end-start)/step-1e-9)
    if count>96:raise ContractError('At most 96 frames; increase step or shorten the interval')
    times=[start+i*step for i in range(count)];out.mkdir(parents=True,exist_ok=False)
    paths=[]
    for i in range(0,count,12):paths+=source_frames(source,out/f'frames-{i:03d}',times[i:i+12])['preview_images']
    sheets=[]
    for first in range(0,count,columns*4):
        batch=paths[first:first+columns*4];sheet=Image.new('RGB',(columns*320,math.ceil(len(batch)/columns)*210),'#141414');d=ImageDraw.Draw(sheet)
        for i,p in enumerate(batch):
            with Image.open(p) as im:tile=ImageOps.pad(im.convert('RGB'),(320,180))
            x=i%columns*320;y=i//columns*210;sheet.paste(tile,(x,y+30));d.text((x+8,y+8),f'{times[first+i]:.3f} s',fill='white')
        path=out/f'sheet-{first:03d}.jpg';sheet.save(path,quality=92);sheets.append(str(path))
    result={'source':str(source),'times':times,'frames':paths,'preview_images':sheets,'note':'Sample timestamps; inspect adjacent source frames to confirm a boundary.'}
    write_json(out/'result.json',result);return result


def analyze_reference(source,out,start,duration,threshold):
    number(start,'start',0);number(duration,'duration',.01,120);number(threshold,'scene_threshold',.01,1)
    info=metadata(source);out.mkdir(parents=True,exist_ok=False)
    has_video=any(s.get('codec_type')=='video' and not s.get('disposition',{}).get('attached_pic') for s in info['streams'])
    cuts=[];end=start+duration
    if has_video:
        # Input-side -ss/-t bound decoding to the window; PTS-STARTPTS makes times relative to the first decoded frame.
        args=['ffmpeg','-hide_banner','-nostdin','-ss',str(start),'-t',str(duration),'-i',str(source),
              '-vf',f"setpts=PTS-STARTPTS,scale=160:-2,select='gt(scene,{threshold})',metadata=print",'-an','-f','null','-']
        result=subprocess.run(args,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=180)
        if result.returncode:raise ContractError('Scene analysis failed: '+result.stderr[-1500:])
        time=None
        for line in result.stderr.splitlines():
            m=re.search(r'pts_time:([\d.eE+-]+)',line)
            if m:time=start+float(m[1])
            m=re.search(r'lavfi.scene_score=([\d.eE+-]+)',line)
            if m and time is not None and start<=time<end:cuts.append({'time':round(time,6),'score':float(m[1])})
    audio=None
    if any(s.get('codec_type')=='audio' for s in info['streams']):
        import numpy as np
        pcm=subprocess.run(['ffmpeg','-v','error','-nostdin','-ss',str(start),'-i',str(source),'-t',str(duration),
            '-vn','-ac','1','-ar','8000','-f','f32le','-'],capture_output=True,timeout=180)
        if pcm.returncode:raise ContractError(pcm.stderr.decode('utf-8',errors='replace')[-2000:])
        samples=np.frombuffer(pcm.stdout,dtype='<f4');n=len(samples)//80
        rms=np.sqrt(np.mean(samples[:n*80].reshape(n,80)**2,axis=1)) if n else np.array([])
        rise=np.maximum(0,np.diff(rms,prepend=0));peaks=[]
        if n:
            limit=max(float(np.percentile(rise,90)),float(rise.max())*.15,1e-5)
            for i in range(1,n-1):
                if rise[i]>=limit and rise[i]>rise[i-1] and rise[i]>=rise[i+1]:peaks.append({'time':round(start+i*.01,4),'strength':float(rise[i])})
        audio={'window_seconds':.01,'rms':rms.tolist(),'onset_candidates':peaks,'note':'Energy rises, not verified musical beats or lyric timestamps.'}
    if not has_video and audio is None:raise ContractError('Source has neither a video nor an audio stream')
    note=('Flashes, text changes and camera motion can trigger scene scores. Confirm candidates visually; no OCR/transcription performed.'
          if has_video else 'Audio-only source: no picture, so no cut candidates; audio energy rises only.')
    report={'source':str(source),'start':start,'duration':duration,'scene_threshold':threshold,'video_available':has_video,'cut_candidates':cuts,
            'audio':audio,'note':note}
    write_json(out/'analysis.json',report)
    return {'report':str(out/'analysis.json'),'cut_candidates':cuts,'onset_candidates':audio['onset_candidates'] if audio else [],
            'video_available':has_video,'audio_available':audio is not None,'note':note}


def list_fonts(directory,query,limit,text=None):
    number(limit,'limit',1,500,integer=True)
    if text is not None and (not isinstance(text,str) or not 1<=len(text)<=500):raise ContractError('text: 1..500 characters to check coverage for')
    from .fontcov import missing
    from .bundled_fonts import FOLDER as BUNDLED,manifest,row_extras
    roots=[Path(directory).expanduser().resolve()] if directory else [BUNDLED,Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts',
        Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'Microsoft/Windows/Fonts',Path('/usr/share/fonts/truetype'),Path('/Library/Fonts')]
    bundled=manifest()
    results=[];unreadable=[]
    for root in roots:
        if not root.is_dir():continue
        # System Linux fonts commonly use one directory per family; bounded depth.
        paths=sorted(set(root.glob('*'))|set(root.glob('*/*')))
        for p in paths:
            if p.suffix.lower() not in ('.ttf','.otf','.ttc'):continue
            try:family,style=ImageFont.truetype(str(p),32).getname()
            except OSError:unreadable.append(str(p));continue
            if query.casefold() not in (family+' '+style+' '+p.name).casefold():continue
            row={'path':str(p.resolve()),'family':family,'style':style,'collection':p.suffix.lower()=='.ttc'}
            if p.resolve().parent==BUNDLED and p.name in bundled:row.update(row_extras(bundled[p.name]))
            if text is not None:
                gone=missing(p,text);row.update(missing=None if gone is None else ''.join(gone),covers=None if gone is None else not gone)
            results.append(row)
    return {'fonts':results[:limit],'matches':len(results),'truncated':len(results)>limit,'unreadable':unreadable,
            'note':'Metadata only, not automatic font identification or licensing clearance (except bundled: true rows, which ship with OpenKatana under the SIL OFL 1.1; import_media copies their licence into the project). TTC lists the first face, which is also the face browsers load for timeline fonts (TTF/OTF/TTC/WOFF/WOFF2).'}


def preview_fonts(sources,text,out):
    if not 1<=len(sources)<=8 or not isinstance(text,str) or not 1<=len(text)<=120:raise ContractError('Supply 1..8 font files and 1..120 characters')
    out.mkdir(parents=True,exist_ok=False);sheet=Image.new('RGB',(1000,160*len(sources)),'#171717');d=ImageDraw.Draw(sheet);fonts=[]
    for i,path in enumerate(sources):
        if path.suffix.lower() not in ('.ttf','.otf','.ttc'):raise ContractError('Font specimens require TTF, OTF or TTC')
        try:font=ImageFont.truetype(str(path),70)
        except OSError as e:raise ContractError('Cannot load font: '+str(path)) from e
        family,style=font.getname();width=d.textlength(text,font=font)
        if width>950:font=ImageFont.truetype(str(path),max(8,int(70*950/width)))
        d.text((20,i*160+12),family+' / '+style,fill='white');d.text((20,i*160+45),text,font=font,fill='#ff4658')
        from .fontcov import missing
        gone=missing(path,text)
        fonts.append({'path':str(path),'family':family,'style':style,'sha256':digest(path),'natural_width_at_70px':width,
                      'missing_glyphs':None if gone is None else ''.join(gone)})
    path=out/'fonts.png';sheet.save(path)
    return {'fonts':fonts,'preview_images':[str(path)],'note':'Actual local font outlines. Specimen uses Pillow; use timeline previews to verify browser layout, animation and glow.'}


def preview_segment(source,out,start,duration,max_width):
    number(start,'start',0);number(duration,'duration',.05,15);number(max_width,'max_width',160,1920,integer=True)
    info=metadata(source);out.mkdir(parents=True,exist_ok=False);video=out/'preview.mp4'
    run(['ffmpeg','-v','error','-nostdin','-ss',str(start),'-i',source,'-t',str(duration),'-map','0:v:0','-map','0:a:0?',
         '-vf',f'scale=min({max_width}\\,iw):-2','-c:v','libx264','-crf','18','-preset','fast','-pix_fmt','yuv420p','-c:a','aac','-movflags','+faststart',video])
    audio=[]
    if any(s.get('codec_type')=='audio' for s in info['streams']):
        path=out/'preview.wav';run(['ffmpeg','-v','error','-nostdin','-i',video,'-vn','-ac','1','-ar','16000',path]);audio=[str(path)]
    return {'video':str(video),'preview_audio':audio,'start':start,'duration':duration,
            'note':'Play the video in a capable client for motion and audio review. Audio is also returned as an MCP audio block; client/model support varies. File creation does not imply listening.'}


def compare_frames(reference,rendered,out,times,offset):
    number(offset,'render_offset')
    if not 1<=len(times)<=12:raise ContractError('Supply 1..12 comparison times')
    out.mkdir(parents=True,exist_ok=False)
    left=source_frames(reference,out/'reference',times)
    right=source_frames(rendered,out/'rendered',[t+offset for t in times]);images=[]
    for first in range(0,len(times),3):
        count=min(3,len(times)-first);sheet=Image.new('RGB',(960,count*390),'#151515');d=ImageDraw.Draw(sheet)
        for i in range(count):
            for col,result in enumerate((left,right)):
                with Image.open(result['preview_images'][first+i]) as im:tile=ImageOps.pad(im.convert('RGB'),(480,360))
                sheet.paste(tile,(col*480,i*390+30));d.text((col*480+8,i*390+8),('Reference' if col==0 else 'Render')+f' {times[first+i]+(offset if col else 0):.3f}s',fill='white')
        path=out/f'comparison-{first}.jpg';sheet.save(path,quality=94);images.append(str(path))
    return {'preview_images':images,'times':times,'render_offset':offset,'note':'Side-by-side frames at explicit times, letterboxed for comparison. No automatic aesthetic/effect/font equivalence claim.'}


def validate_plan(plan):
    fields(plan,'source fps frames cut_frames texts fonts shots allow_extra_text notes','reference plan')
    number(plan.get('fps'),'plan.fps',1,120);number(plan.get('frames'),'plan.frames',1,integer=True)
    if not isinstance(plan.get('source'),str):raise ContractError('Reference plan needs a source path')
    cuts=plan.get('cut_frames')
    if not isinstance(cuts,list):raise ContractError('cut_frames must list all internal shot boundaries; [] for one shot')
    last=0
    for frame in cuts:
        number(frame,'cut frame',1,plan['frames']-1,integer=True)
        if frame<=last:raise ContractError('Cut frames must strictly increase')
        last=frame
    for name in ('texts','fonts','shots'):
        if not isinstance(plan.get(name,[]),list):raise ContractError(name+' must be an array')
    if not isinstance(plan.get('allow_extra_text',True),bool):raise ContractError('allow_extra_text must be boolean')
    for t in plan.get('texts',[]):
        fields(t,'text f0 f1 family','reference text')
        if not isinstance(t.get('text'),str):raise ContractError('Reference text must preserve the literal transcription')
        number(t.get('f0'),'text.f0',0,plan['frames']-1,integer=True);number(t.get('f1'),'text.f1',t['f0']+1,plan['frames'],integer=True)
    for font in plan.get('fonts',[]):
        fields(font,'family sha256','reference font')
        if not isinstance(font.get('family'),str) or not re.fullmatch('[a-fA-F0-9]{64}',font.get('sha256','')):raise ContractError('Reference font needs family and exact file sha256')
    for shot in plan.get('shots',[]):
        fields(shot,'index fields','reference shot');number(shot.get('index'),'shot.index',0,len(cuts),integer=True)
        if not isinstance(shot.get('fields'),dict):raise ContractError('Reference shot fields must be an object')
    return plan


def audit_plan(root,timeline):
    record=json.loads((root/'reference-plan.json').read_text(encoding='utf-8'));plan=validate_plan(record['plan']);issues=[]
    source=Path(plan['source'])
    if not source.is_file() or digest(source)!=record['source_sha256']:issues.append('Reference source changed or is missing')
    def equal(label,expected,actual):
        if expected!=actual:issues.append({'field':label,'expected':expected,'actual':actual})
    equal('fps',plan['fps'],timeline['canvas']['fps']);equal('frames',plan['frames'],timeline['canvas']['frames'])
    equal('cut_frames',plan['cut_frames'],[s['f0'] for s in timeline['shots'][1:]])
    def literal(t):
        return ''.join(p[0] for p in t['parts']) if 'parts' in t else t.get('text',t.get('word','\n'.join(t.get('lines',[]))))
    texts=[]
    for t in timeline.get('text',[]):
        texts.append({'text':literal(t),'f0':t['f0'],'f1':t['f1'],'family':t.get('family')})
    # Shot-layer text/graffiti and fx.graffiti (audit F-OK-010). Same visibility rule as the renderer:
    # visible while 0 <= (frame+0.5-shot.f0)/fps - at < d, clipped to the shot.
    import math
    fps=timeline['canvas']['fps']
    for shot in timeline['shots']:
        items=[l for l in shot.get('layers',[]) if l.get('type') in ('text','graffiti')]
        if isinstance(shot.get('fx',{}).get('graffiti'),dict):items.append({'type':'graffiti',**shot['fx']['graffiti']})
        for item in items:
            at=item.get('at',0);d=item.get('d',(shot['f1']-shot['f0'])/fps)
            f0=shot['f0']+max(0,math.ceil(at*fps-.5-1e-9));f1=min(shot['f1'],shot['f0']+math.ceil((at+d)*fps-.5-1e-9))
            if f1>f0:texts.append({'text':literal(item),'f0':f0,'f1':f1,'family':item.get('family')})
    remaining=list(texts)
    for t in plan.get('texts',[]):
        found=next((i for i,x in enumerate(remaining) if all(x.get(k)==v for k,v in t.items())),None)
        if found is None:issues.append({'field':'text','expected':t,'problem':'No literal text/time/font match'})
        else:remaining.pop(found)
    if not plan.get('allow_extra_text',True) and remaining:issues.append({'field':'extra_text','actual':remaining})
    fonts={f['family']:f for f in timeline.get('fonts',[])}
    for f in plan.get('fonts',[]):
        actual=digest(local_path(root,fonts[f['family']]['url'])) if f['family'] in fonts else None
        equal('font '+f['family'],f['sha256'].lower(),actual)
    def subset(expected,actual,label):
        if isinstance(expected,dict) and isinstance(actual,dict):
            for k,v in expected.items():subset(v,actual.get(k),label+'.'+k)
        else:equal(label,expected,actual)
    for s in plan.get('shots',[]):
        subset(s['fields'],timeline['shots'][s['index']] if s['index']<len(timeline['shots']) else None,'shot '+str(s['index']))
    return {'matches_plan':not issues,'issues':issues,'reference_sha256':record['source_sha256'],
            'note':'Checks the recorded plan, not whether its transcription, timings or effects accurately describe the reference. Validate the plan visually first.'}
