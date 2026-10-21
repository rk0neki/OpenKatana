"""Opt-in local SDK integration with installed weights. No downloads/cloud fallback.

--config supplies {kind: parameters}; output is original synthetic test media,
not a quality benchmark or release film. Restart with --resume to collect jobs.
"""
import argparse
import json
import math
from pathlib import Path
import struct
import sys
import time
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from openkatana.agent_api import AgentAPI
from openkatana.model_workflows import asset_ports
from openkatana.render import run, write_json
from openkatana.workflows import build, preflight
from PIL import Image, ImageDraw


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--config',type=Path,required=True)
    p.add_argument('--resume',action='store_true');p.add_argument('--timeout',type=int,default=1800)
    args=p.parse_args();out=args.out.resolve()
    if not args.resume:out.mkdir(parents=True,exist_ok=False)
    api=AgentAPI(out/'projects');root=out/'projects/models'
    if not root.exists():
        api.create_project('Original adapter test','models')
        for k,color in [('source','#ca4d21'),('reference','#2399b0')]:
            im=Image.new('RGB',(256,256),'#161d28');d=ImageDraw.Draw(im)
            d.rounded_rectangle((70,45,185,215),radius=20,fill=color);d.rectangle((90,85,165,130),fill='#ededdd');im.save(root/f'{k}.png')
        with wave.open(str(root/'tone.wav'),'wb') as f:
            f.setnchannels(1);f.setsampwidth(2);f.setframerate(24000)
            f.writeframes(b''.join(struct.pack('<h',round(math.sin(2*math.pi*220*i/24000)*1500)) for i in range(48000)))
        run(['ffmpeg','-v','error','-loop','1','-i',root/'source.png','-i',root/'tone.wav','-t','2','-r','24','-vf','scale=128:128','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',root/'source.mp4'])
        run(['ffmpeg','-v','error','-i',root/'source.mp4','-t',str(5/24),'-c:v','libx264','-c:a','aac',root/'short.mp4'])
    report={}
    for kind,params in json.loads(args.config.read_text(encoding='utf8')).items():
        g=build(kind,**params);check=preflight(g,'http://127.0.0.1:8000')
        if not check['ready']:
            report[kind]={'state':'not_ready','check':check};write_json(out/'validation.json',report);print(kind,'not ready',check['errors'],flush=True);continue
        assets={}
        for i,(port,placeholder) in enumerate(asset_ports(g).items()):
            assets[port]='tone.wav' if placeholder.endswith('.wav') else ('short.mp4' if kind=='seedvr2-restore' else 'source.mp4') if placeholder.endswith('.mp4') else ('source.png' if i==0 else 'reference.png')
        started=time.time()
        try:
            while True:
                result=api.run_model_workflow('models',kind,params,assets,'test-'+kind)
                state=result['receipt']['state'];print(kind,state,flush=True)
                report[kind]=result;write_json(out/'validation.json',report)
                if state in ('collected','failed','cancelled','submission_unknown'):break
                if time.time()-started>args.timeout:raise TimeoutError('Job still recorded; resume to collect, never resubmit')
                time.sleep(15)
        except Exception as e:
            report[kind]={'error':str(e),'resume_required':True};write_json(out/'validation.json',report);raise
    print(json.dumps({k:v.get('receipt',v).get('state',v.get('error')) for k,v in report.items()}),flush=True)


if __name__=='__main__':main()
