"""Resumable source-frame processing. Every submitted job is persisted once."""
import json
from pathlib import Path
from PIL import Image
from .vision import clip_at
from .contracts import ContractError
from .render import digest,write_json
from .comfy import submit,collect
from .workflows import build_from_form,preflight

UPLOAD_LIMIT=100*1024*1024  # the proxy's (and ComfyUI's default) single-upload ceiling

def _clip_video(clip,files,target):
    """Encode the clip's frames, in order and at their own size and rate, as the single upload of a whole-clip job."""
    import subprocess
    pattern=files[0].parent/clip.get('pattern','%05d.png')
    subprocess.run(['ffmpeg','-v','error','-framerate',str(clip['fps']),'-start_number','0','-i',str(pattern),'-frames:v',str(len(files)),
                    '-c:v','libx264','-preset','veryfast','-crf','12','-pix_fmt','yuv444p',str(target)],check=True,capture_output=True)
    if target.stat().st_size>UPLOAD_LIMIT:
        target.unlink();raise ContractError('The clip is too large for one upload (over 100 MB). Trim or downscale the clip first')

def _whole_clip(state,root,out,graph,files,clip,endpoint,native_endpoint):
    folder=out/'jobs'/'clip';workflow=out/'workflow.json';video=out/'source.mp4'
    if not workflow.exists():write_json(workflow,graph)
    if not folder.exists():
        if not video.exists():_clip_video(clip,files,video)
        submit(workflow,folder,endpoint,[f'1.video={video}'],native_endpoint)
    receipt=collect(folder)
    if receipt['state']!='collected':
        state.update(state=receipt['state'],waiting_job=receipt['job_id']);write_json(out/'sequence.json',state)
        return {'state':state['state'],'completed':0,'total':1,'job_id':receipt['job_id'],'resume':'Run the same command to collect; it will not resubmit this job'}
    # Output order follows the saved image counter, which follows the frame order of the batch.
    images=sorted((folder/o['file'] for o in receipt['outputs'] if Path(o['file']).suffix.lower()=='.png'),key=lambda f:f.name.split('-',1)[1])
    if len(images)!=len(files):raise ContractError(f'Expected one mask per source frame ({len(files)}), got {len(images)}')
    for index,f in enumerate(images):
        with Image.open(f) as im:
            if im.size!=(clip['w'],clip['h']):raise ContractError('Workflow changed source geometry')
            result=Image.new('RGBA',im.size,'white');result.putalpha(im.convert('L'))
        name=f'{index:05d}.png';result.save(out/name);state['frame_hashes'][name]=digest(out/name)
    update={'mask_dir':out.relative_to(root).as_posix()}
    state.update(state='complete',completed=[0],clip_update=update);state.pop('waiting_job',None);write_json(out/'sequence.json',state)
    return {'state':'complete','clip_update':update,'frames':len(state['frame_hashes']),'review':'pending'}

def process(timeline,clip_id,out,kind,endpoint,native_endpoint,model=None,positive=None,negative=None):
    clip,files=clip_at(timeline,clip_id);root=timeline.resolve().parent;out=out.resolve()
    if not out.is_relative_to(root):raise ContractError('Sequence outputs must be inside the timeline project')
    if kind not in ('matte','segmentation','interpolation','cutout'):raise ContractError('Unsupported sequence workflow')
    form={'model':model}
    if kind=='cutout':form.update(positive=positive,negative=negative)
    elif positive or negative:raise ContractError('Click points (positive/negative) apply only to the cutout kind')
    try:graph=build_from_form(kind,form)
    except ValueError as e:raise ContractError(str(e)) from None
    check=preflight(graph,native_endpoint)
    if not check['ready']:raise ContractError('; '.join(check['errors']))
    signature={'kind':kind,'clip':clip_id,'model':model,'endpoint':endpoint,'native_endpoint':native_endpoint,
               'inputs':{f.name:digest(f) for f in files},'graph':graph,'fps':clip['fps']}
    if (out/'sequence.json').is_file():
        state=json.loads((out/'sequence.json').read_text())
        if state['spec']!=signature:raise ContractError('Sequence inputs/settings changed. Choose a new output folder')
        for name,sha in state.get('frame_hashes',{}).items():
            if digest(out/name)!=sha:raise ContractError('A completed sequence frame changed')
    else:
        out.mkdir(parents=True,exist_ok=False);state={'spec':signature,'state':'prepared','completed':[],'frame_hashes':{}};write_json(out/'sequence.json',state)
    if kind=='cutout':
        if state['state']=='complete':return {'state':'complete','clip_update':state['clip_update'],'frames':len(state['frame_hashes']),'review':'pending'}
        return _whole_clip(state,root,out,graph,files,clip,endpoint,native_endpoint)
    count=len(files) if kind!='interpolation' else max(1,len(files)-1)
    for i in range(count):
        if i in state['completed']:continue
        folder=out/'jobs'/f'{i:05d}';workflow=out/'workflow.json'
        if not workflow.exists():write_json(workflow,graph)
        if not folder.exists():
            bindings=[f'1.image={files[i]}']
            if kind=='interpolation':bindings.append(f'2.image={files[min(i+1,len(files)-1)]}')
            submit(workflow,folder,endpoint,bindings,native_endpoint)
        receipt=collect(folder)
        if receipt['state']!='collected':
            state.update(state=receipt['state'],waiting_job=receipt['job_id']);write_json(out/'sequence.json',state)
            return {'state':state['state'],'completed':len(state['completed']),'total':count,'job_id':receipt['job_id'],'resume':'Run the same command to collect; it will not resubmit this job'}
        images=[folder/o['file'] for o in receipt['outputs'] if Path(o['file']).suffix.lower()=='.png']
        expected=4 if kind=='interpolation' else 1
        if len(images)!=expected:raise ContractError(f'Expected {expected} output images, got {len(images)}')
        for j,f in enumerate(images[:2] if kind=='interpolation' else images):
            with Image.open(f) as im:
                if im.size!=(clip['w'],clip['h']):raise ContractError('Workflow changed source geometry')
                if kind=='interpolation':result=im.convert('RGB');index=i*2+j
                else:result=Image.new('RGBA',im.size,'white');result.putalpha(im.convert('L'));index=i
                name=f'{index:05d}.png';result.save(out/name);state['frame_hashes'][name]=digest(out/name)
        state['completed'].append(i);write_json(out/'sequence.json',state)
    if kind=='interpolation':
        with Image.open(files[-1]) as im:
            for index in range((len(files)-1)*2,len(files)*2):
                name=f'{index:05d}.png';im.convert('RGB').save(out/name);state['frame_hashes'][name]=digest(out/name)
        update={**clip,'frames_dir':out.relative_to(root).as_posix(),'n':len(files)*2,'fps':clip['fps']*2,'pattern':'%05d.png'}
        for k in ('mask_dir','faces','faces_size'):update.pop(k,None)
    else:update={'mask_dir':out.relative_to(root).as_posix()}
    state.update(state='complete',clip_update=update);state.pop('waiting_job',None);write_json(out/'sequence.json',state)
    return {'state':'complete','clip_update':update,'frames':len(state['frame_hashes']),'review':'pending'}
