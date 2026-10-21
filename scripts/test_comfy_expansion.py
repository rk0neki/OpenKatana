"""Exercise the real SDK/proxy/ComfyUI using model-free CPU operations.

Starts dedicated temporary servers, with all mutable state in --out, and closes
only those child processes. Does not reconfigure the user's normal ComfyUI.
"""
import argparse
import json
import shutil
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

from openkatana.comfy import submit, collect
from openkatana.render import render, write_json


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0))
        return sock.getsockname()[1]


def wait_http(url, process):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline = time.monotonic()+90
    while time.monotonic()<deadline:
        if process.poll() is not None:
            raise RuntimeError('Test server exited; see its log')
        try:
            with opener.open(url, timeout=2) as response:
                if response.status==200: return
        except Exception:
            time.sleep(.5)
    raise TimeoutError(url)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--comfy-python',required=True,type=Path)
    p.add_argument('--comfy-main',required=True,type=Path)
    p.add_argument('--out',required=True,type=Path)
    args=p.parse_args()
    root=args.out.resolve(); root.mkdir(parents=True,exist_ok=False)
    for part in ['input','output','temp','user','frontend']: (root/part).mkdir()
    (root/'frontend'/'index.html').write_text('<!doctype html><title>OpenKatana test</title>')
    shutil.copytree(Path(__file__).resolve().parents[1]/'comfy_nodes',root/'custom_nodes/openkatana_nodes')
    port,proxy_port=free_port(),free_port()
    endpoint=f'http://127.0.0.1:{proxy_port}'
    env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','NO_PROXY':'127.0.0.1,localhost','PYTHONPATH':str(Path(__file__).resolve().parents[1])}
    flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
    processes=[]
    logs=[]
    try:
        command=[str(args.comfy_python),str(args.comfy_main),'--cpu',
                 '--disable-api-nodes','--disable-auto-launch','--listen','127.0.0.1','--port',str(port),
                 '--base-directory',str(root),'--user-directory',str(root/'user'),
                 '--front-end-root',str(root/'frontend'),'--database-url','sqlite:///:memory:']
        log=(root/'comfy.log').open('w'); logs.append(log)
        proc=subprocess.Popen(command,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=flags)
        processes.append(proc)
        wait_http(f'http://127.0.0.1:{port}/system_stats',proc)
        proxy=Path(sys.executable).parent/('comfy-api-proxy.exe' if os.name=='nt' else 'comfy-api-proxy')
        log=(root/'proxy.log').open('w'); logs.append(log)
        proc=subprocess.Popen([str(proxy),'run','--comfyui',f'http://127.0.0.1:{port}',
                               '--port',str(proxy_port),'--state-dir',str(root/'proxy-state')],
                              env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=flags)
        processes.append(proc)
        wait_http(endpoint+'/api/v2/health',proc)
        from openkatana.workflows import build,preflight
        from openkatana import projects
        from openkatana.comfy_assets import import_outputs
        from PIL import ImageDraw
        source=Image.new('RGB',(64,48),'#00ff00');ImageDraw.Draw(source).rectangle((20,12,39,35),fill='#ff0000');source.save(root/'input.png')
        second=Image.new('RGB',(64,48),'#00ff00');ImageDraw.Draw(second).rectangle((24,12,43,35),fill='#ff0000');second.save(root/'second.png')
        records=[]
        for kind in ('matte','interpolation'):
            workflow=root/(kind+'.json');write_json(workflow,build(kind))
            assets=[f'1.image={root / "input.png"}']
            if kind=='interpolation':assets.append(f'2.image={root / "second.png"}')
            directory=root/kind
            submitted=submit(workflow,directory,endpoint,assets,f'http://127.0.0.1:{port}')
            deadline=time.monotonic()+60
            while True:
                result=collect(directory)
                if result['state']=='collected':break
                if result['state'] in ('failed','cancelled','canceled') or time.monotonic()>deadline:raise RuntimeError(result)
                time.sleep(.5)
            outputs=[np.array(Image.open(directory/o['file']).convert('RGB')) for o in result['outputs']]
            if kind=='matte':assert outputs[0][0,0,0]==0 and outputs[0][20,30,0]==255
            else:
                assert len(outputs)==4,len(outputs)
                assert np.array_equal(outputs[0],np.array(source))
                assert np.array_equal(outputs[-1],np.array(second))
                project=root/'imported-project';projects.create(project)
                imported=import_outputs(directory,project,fps=48)
                assert imported['clip']['n']==4
            records.append({'kind':kind,'job_id':submitted['job_id'],'outputs':len(outputs),'passed':True})
        from openkatana.comfy_sequence import process
        sequence_edit={'canvas':{'w':64,'h':48,'fps':48,'frames':4},'clips':{'A':imported['clip']},'shots':[{'clip':'A','f0':0,'f1':4}]}
        write_json(project/'timeline.json',sequence_edit)
        deadline=time.monotonic()+60
        while True:
            sequence=process(project/'timeline.json','A',project/'matte-sequence','matte',endpoint,f'http://127.0.0.1:{port}')
            if sequence['state']=='complete':break
            if time.monotonic()>deadline:raise RuntimeError(sequence)
            time.sleep(.3)
        jobs_before={p.parent.name:json.loads(p.read_text())['job_id'] for p in (project/'matte-sequence/jobs').glob('*/job.json')}
        sequence_again=process(project/'timeline.json','A',project/'matte-sequence','matte',endpoint,f'http://127.0.0.1:{port}')
        assert sequence_again['state']=='complete' and sequence_again['frames']==4
        jobs_after={p.parent.name:json.loads(p.read_text())['job_id'] for p in (project/'matte-sequence/jobs').glob('*/job.json')}
        assert jobs_before==jobs_after
        records.append({'kind':'resumable-matte-sequence','frames':4,'resubmitted':False,'passed':True})
        missing=preflight(build('generation',model='not-installed.safetensors'),f'http://127.0.0.1:{port}')
        assert not missing['ready']
        write_json(root/'result.json',{'passed':True,'sdk':'official comfy-sdk','jobs':records,'missing_model_preflight':missing,'normal_comfy_instance_changed':False})
        print((root/'result.json').read_text())
    finally:
        for proc in reversed(processes):
            if proc.poll() is None:
                proc.terminate()
                try: proc.wait(timeout=10)
                except subprocess.TimeoutExpired: proc.kill(); proc.wait()
        for log in logs: log.close()


if __name__=='__main__': main()
