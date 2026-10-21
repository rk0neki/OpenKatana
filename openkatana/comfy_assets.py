"""Convert collected Comfy images to explicit source-indexed editor assets."""
import json
import uuid
from pathlib import Path
from PIL import Image
from .contracts import ContractError,number
from .render import digest,write_json

def import_outputs(job:Path,project:Path,kind='clip',clip_id=None,fps=30,output_file=None):
    from .comfy import collect
    from . import projects
    number(fps,'fps',1,240);receipt=collect(job)
    if receipt['state']!='collected':raise ContractError('The Comfy job has not completed')
    selected=receipt['outputs']
    if output_file is not None:
        selected=[x for x in selected if x['file']==output_file]
        if not selected:raise ContractError('Select an output file listed in the collected job receipt')
    provenance={'job_id':receipt['job_id'],'execution':receipt.get('execution','local'),
        'workflow_sha256':receipt['workflow_sha256'],'inputs':receipt['assets'],'outputs':selected,'review':'pending'}
    media=[x for x in selected if Path(x['file']).suffix.lower() in ('.mp4','.mov','.mkv','.webm','.avi','.wav','.mp3','.m4a','.flac','.ogg','.aac')]
    if media:
        if kind!='clip':raise ContractError('Mask import requires image frames')
        if len(selected)!=1:raise ContractError('Choose output_file when a job returns video/audio with other outputs')
        asset=projects.import_asset(project,job/media[0]['file'])
        asset['provenance']=provenance
        data=projects.state(project)
        next(x for x in data['assets'] if x['id']==asset['id'])['provenance']=provenance
        for k in ('timeline','revision','recipes'):data.pop(k,None)
        write_json(project/'project.json',data)
        if 'clip' in asset:write_json(project/asset['clip']['frames_dir']/'comfy-origin.json',provenance)
        return asset
    files=[job/x['file'] for x in selected if Path(x['file']).suffix.lower() in ('.png','.jpg','.jpeg','.webp')]
    if not files:raise ContractError('No supported collected media outputs')
    data=projects.state(project);id=uuid.uuid4().hex[:12];folder=project/('masks' if kind=='mask' else 'plates')/id
    images=[Image.open(f) for f in files];size=images[0].size
    if any(im.size!=size for im in images):raise ContractError('Output image sizes differ')
    if kind=='mask':
        if not clip_id or not data['timeline']:raise ContractError('Mask import requires --clip and a saved timeline')
        clip=data['timeline']['clips'][clip_id]
        if len(files)!=clip['n'] or size!=(clip['w'],clip['h']):raise ContractError('Mask count/geometry must match the source clip exactly')
    folder.mkdir(parents=True,exist_ok=False)
    for i,im in enumerate(images):
        if kind=='mask':
            converted=Image.new('RGBA',size,'white');converted.putalpha(im.convert('L'))
        else:converted=im.convert('RGB')
        converted.save(folder/f'{i:05d}.png');im.close()
    write_json(folder/'comfy-origin.json',provenance)
    if kind=='mask':
        clip['mask_dir']=folder.relative_to(project).as_posix();projects.save(project,data['timeline'],data['revision']);return {'mask_dir':clip['mask_dir'],'frames':len(files)}
    clip={'frames_dir':folder.relative_to(project).as_posix(),'n':len(files),'fps':fps,'w':size[0],'h':size[1],'pattern':'%05d.png'}
    asset={'id':id,'kind':'image' if len(files)==1 else 'video','name':'Comfy '+receipt['job_id'],'clip':clip,'rights':'review_pending','provenance':provenance}
    data['assets'].append(asset)
    for k in ('timeline','revision','recipes'):data.pop(k,None)
    write_json(project/'project.json',data);return asset
