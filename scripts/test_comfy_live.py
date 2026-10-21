"""Exercise the real SDK/proxy/ComfyUI using model-free CPU operations.

Starts dedicated temporary servers, with all mutable state in --out, and closes
only those child processes. Does not reconfigure the user's normal ComfyUI.
"""
import argparse
import json
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
    port,proxy_port=free_port(),free_port()
    endpoint=f'http://127.0.0.1:{proxy_port}'
    env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','NO_PROXY':'127.0.0.1,localhost'}
    flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
    processes=[]
    logs=[]
    try:
        command=[str(args.comfy_python),str(args.comfy_main),'--cpu','--disable-all-custom-nodes',
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
        source=Image.new('RGB',(320,192),'#2645a8'); source.save(root/'input.png')
        workflow=Path(__file__).resolve().parents[1]/'workflows/image-invert.api.json'
        submitted=submit(workflow,root/'job',endpoint,[f'1.image={root / "input.png"}'])
        deadline=time.monotonic()+60
        while True:
            result=collect(root/'job')
            if result['state']=='collected': break
            if result['state'] in ('failed','cancelled','canceled') or time.monotonic()>deadline:
                raise RuntimeError(f'Comfy job did not complete: {result}')
            time.sleep(.5)
        generated=root/'job'/result['outputs'][0]['file']
        a=np.asarray(source,dtype=np.int16)
        b=np.asarray(Image.open(generated).convert('RGB'),dtype=np.int16)
        maximum=int(np.abs((255-a)-b).max())
        # Comfy's floating-point image tensor -> PNG quantization can truncate by
        # one 8-bit level. This check is SDK transport/workflow validation, not a
        # claim of byte-exact integer inversion or general visual fidelity.
        assert maximum<=1, maximum
        plate=root/'plates'/'processed'; plate.mkdir(parents=True)
        Image.open(generated).convert('RGB').save(plate/'00000.png')
        timeline={'canvas':{'w':320,'h':192,'fps':60,'frames':60},
                  'clips':{'processed':{'frames_dir':'plates/processed','pattern':'%05d.png','n':1,'fps':60,'w':320,'h':192}},
                  'shots':[{'f0':0,'f1':60,'clip':'processed','speed':0,'cam':{'zoom':{'z0':1,'z1':1.2}}}]}
        write_json(root/'timeline.json',timeline)
        receipt=render(root/'timeline.json',root/'render')
        write_json(root/'result.json',{'sdk':'official comfy-sdk','job_id':submitted['job_id'],
                   'pixel_inverse_max_error':maximum,'render_frames':receipt['frames'],
                   'passed':True,'model_generation_tested':False,'mode':'real ComfyUI, model-free CPU workflow'})
        print((root/'result.json').read_text())
    finally:
        for proc in reversed(processes):
            if proc.poll() is None:
                proc.terminate()
                try: proc.wait(timeout=10)
                except subprocess.TimeoutExpired: proc.kill(); proc.wait()
        for log in logs: log.close()


if __name__=='__main__': main()
