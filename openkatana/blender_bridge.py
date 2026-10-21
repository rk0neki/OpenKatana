"""Optional installed Blender: trusted scene authoring and full scene rendering, no bundled binary."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from .contracts import ContractError
from .render import digest, encode, probe, write_json


def executable():
    choices = [os.environ.get('OPENKATANA_BLENDER'), shutil.which('blender'),
               *map(str, sorted(Path('C:/Program Files/Blender Foundation').glob('Blender */blender.exe'), reverse=True)),
               '/Applications/Blender.app/Contents/MacOS/Blender']
    for p in choices:
        if p and Path(p).is_file():
            return p
    raise ContractError('Install Blender separately, or set OPENKATANA_BLENDER; no automatic download')


def render_blender(source, out, engine='BLENDER_EEVEE', start=None, end=None, trusted_script=False, timeout=1800):
    source, out = Path(source).resolve(), Path(out).resolve()
    if type(trusted_script) is not bool:
        raise ContractError('trusted_script must be an explicit boolean')
    if source.suffix.lower() not in ('.blend', '.py') or not source.is_file():
        raise ContractError('Blender source must be an existing .blend or trusted .py scene authoring script')
    if source.suffix.lower() == '.py' and not trusted_script:
        raise ContractError('Python scene scripts execute trusted local code; specify trusted_script explicitly')
    if engine not in ('BLENDER_EEVEE', 'CYCLES'):
        raise ContractError('Blender engine must be BLENDER_EEVEE or CYCLES')
    for value in (start, end):
        if value is not None and (type(value) is not int or not 0 <= value <= 100000):
            raise ContractError('Blender frame bounds must be nonnegative integers')
    if start is not None and end is not None and end < start:
        raise ContractError('Blender end must not precede start')
    exe=executable();out.mkdir(parents=True,exist_ok=False)
    request={'source':str(source),'output':str(out),'engine':engine,'start':start,'end':end,'source_sha256':digest(source)}
    write_json(out/'request.json',request)
    args=[exe,'--background','--factory-startup','--disable-autoexec']
    if source.suffix.lower()=='.blend':args.append(str(source))
    args += ['--python-exit-code','1','--python',str(Path(__file__).with_name('blender_worker.py')),'--',str(out/'request.json')]
    with (out/'blender.log').open('w',encoding='utf-8') as log:
        result=subprocess.run(args,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,timeout=timeout,cwd=source.parent)
    if result.returncode:
        raise ContractError(f'Blender failed; see {out / "blender.log"}')
    metadata=json.loads((out/'blender-result.json').read_text(encoding='utf-8'))
    for f in range(metadata['frames']):
        if not (out/'frames'/f'{f:05d}.png').is_file():raise ContractError(f'Blender missed frame {f}')
    if digest(source)!=request['source_sha256']:raise ContractError('Blender source changed during render')
    encode(out/'frames',metadata,out/'video.mp4')
    stream=next(s for s in probe(out/'video.mp4')['streams'] if s['codec_type']=='video')
    if int(stream['nb_read_frames'])!=metadata['frames']:raise ContractError('Blender export frame count mismatch')
    receipt={**request,**metadata,'video':str(out/'video.mp4'),'video_sha256':digest(out/'video.mp4'),
             'clip':{'frames_dir':str(out/'frames'),'n':metadata['frames'],'fps':metadata['fps'],
                     'w':metadata['width'],'h':metadata['height'],'pattern':'%05d.png'},
             'preview_images':[str(out/'frames'/'00000.png')],
             'security':'Trusted local Blender/script execution, not an OS sandbox',
             'scope':'Local capability, not proof of identical hosted output','credits_used':0}
    write_json(out/'receipt.json',receipt);return receipt
