"""Run one existing local workflow through the SDK and import its image.

Uses the user's running ComfyUI without reconfiguration. Starts and stops only a
temporary API proxy. A saved job is collected, never submitted a second time.
No model downloads or paid nodes are permitted by OpenKatana's allowlist.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from PIL import Image
from openkatana.comfy import submit,collect,local_endpoint
from openkatana.comfy_assets import import_outputs
from openkatana import projects
from openkatana.render import write_json
from scripts.test_comfy_expansion import free_port,wait_http

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--native-endpoint',default='http://127.0.0.1:8000')
    args=parser.parse_args();root=args.out.resolve()
    local_endpoint(args.native_endpoint)
    receipt_path=root/'job/job.json'
    if receipt_path.exists():
        prior=json.loads(receipt_path.read_text());port=int(prior['endpoint'].rsplit(':',1)[1])
    else:port=free_port()
    endpoint=f'http://127.0.0.1:{port}'
    proxy=Path(sys.executable).parent/('comfy-api-proxy.exe' if os.name=='nt' else 'comfy-api-proxy')
    with (root/'proxy.log').open('a') as log:
        proc=subprocess.Popen([str(proxy),'run','--comfyui',args.native_endpoint,'--port',str(port),'--state-dir',str(root/'proxy-state')],
            env={**os.environ,'NO_PROXY':'localhost,127.0.0.1'},stdout=log,stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        try:
            wait_http(endpoint+'/api/v2/health',proc)
            if not receipt_path.exists():submit(root/'workflow.json',root/'job',endpoint,native_endpoint=args.native_endpoint)
            deadline=time.monotonic()+1200;previous=None
            while True:
                result=collect(root/'job')
                if result['state']!=previous:print(result['state'],result.get('job_id'),flush=True);previous=result['state']
                if result['state']=='collected':break
                if result['state'] in ('failed','canceled','cancelled'):raise RuntimeError(result)
                if time.monotonic()>deadline:raise TimeoutError('Job remains recorded; inspect and collect without resubmitting')
                time.sleep(3)
            assert len(result['outputs'])==1
            output=root/'job'/result['outputs'][0]['file'];im=Image.open(output)
            assert im.size==(512,512),im.size
            assert max(high-low for low,high in im.convert('RGB').getextrema())>64
            project=root/'imported-project';projects.create(project)
            imported=import_outputs(root/'job',project)
            assert imported['clip']['n']==1
            write_json(root/'result.json',{'passed':True,'job_id':result['job_id'],'output':str(output.relative_to(root)),
                'size':list(im.size),'sdk':'official comfy-sdk','imported_clip':imported['clip'],
                'models_downloaded':False,'comfy_configuration_changed':False,'quality_review':'single low-resolution integration sample only'})
            print((root/'result.json').read_text(),flush=True)
        finally:
            proc.terminate()
            try:proc.wait(timeout=10)
            except subprocess.TimeoutExpired:proc.kill();proc.wait()

if __name__=='__main__':main()
