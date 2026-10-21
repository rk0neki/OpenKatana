"""Loopback-only editor. Background work uses isolated CLI child processes."""
import json
import os
import subprocess
import sys
import threading
import uuid
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit,unquote,parse_qs
from .render import Handler,write_json
from .contracts import local_path,ContractError
from . import projects

class Studio(Handler):
    def host_ok(self):return self.headers.get('Host')==f'127.0.0.1:{self.server.server_port}'
    def json(self,value,status=200):
        raw=json.dumps(value).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        if not self.host_ok():return self.json({'error':'Invalid host'},403)
        route=urlsplit(self.path).path
        if route=='/':self.path='/app/studio.html'
        if route=='/api/studio-info':
            from . import __version__
            from pathlib import Path
            source=Path(__file__).resolve().parent.parent
            return self.json({'version':__version__,'project_path':str(self.project),'project_id':self.project.name,
                'workspace':str(self.project.parent),'python':sys.executable,
                'source':str(source) if (source/'pyproject.toml').is_file() else None,
                'skill':str(next((p for p in (source/'skills/openkatana-video/SKILL.md',Path(sys.prefix)/'share/openkatana/skills/openkatana-video/SKILL.md') if p.is_file()),''))})
        if route=='/api/tools':
            from .agent_api import AgentAPI
            return self.json(AgentAPI(self.project.parent).catalog())
        if route=='/api/guide':
            from .agent_api import AgentAPI
            try:return self.json(AgentAPI(self.project.parent).read_guide(parse_qs(urlsplit(self.path).query).get('topic',['agent'])[0]))
            except (ValueError,RuntimeError) as e:return self.json({'error':str(e)},400)
        if route=='/api/state':
            value=projects.state(self.project)
            if value.get('timeline'):   # Studio edits the canonical form (native t0/t1, $palette, presets rewritten)
                from .native import normalize
                try:value['timeline']=normalize(value['timeline'])
                except ContractError as e:value['timeline_error']=str(e)
            return self.json(value)
        if route=='/api/jobs':
            from .jobs import status
            jobs=[]
            for f in sorted((self.project/'.openkatana/jobs').glob('*/job.json')):
                job=json.loads(f.read_text());process=self.server.processes.get(job['id'])
                if (f.parent/'process.json').is_file():
                    jobs.append(status(self.project,job['id']));continue
                if job['state']=='running' and process and process.poll() is not None:
                    job['state']='succeeded' if process.returncode==0 else 'failed';job['exit_code']=process.returncode
                    job['message']=(f.parent/'log.txt').read_text(encoding='utf-8',errors='replace')[-3000:];write_json(f,job)
                elif job['state']=='running' and not process:
                    receipt=f.parent/'render/receipt.json'
                    job['state']='succeeded' if receipt.is_file() and json.loads(receipt.read_text()).get('ok') else 'interrupted'
                    write_json(f,job)
                jobs.append(job)
            return self.json(jobs)
        super().do_GET()
    def do_POST(self):
        origin=self.headers.get('Origin');expected=f'http://127.0.0.1:{self.server.server_port}'
        if not self.host_ok() or origin not in (None,expected):return self.json({'error':'Invalid origin'},403)
        if self.headers.get('Content-Type')!='application/json':return self.json({'error':'JSON required'},415)
        try:
            size=int(self.headers.get('Content-Length',0))
            if not 0<size<=96*1024*1024:raise ContractError('Request too large; import large media with the CLI')
            body=json.loads(self.rfile.read(size));route=urlsplit(self.path).path
            with self.server.mutation_lock:
                if route=='/api/save':result=projects.save(self.project,body['timeline'],body.get('revision'))
                elif route=='/api/plan':result=projects.plan(self.project,**body)
                elif route=='/api/import':
                    import base64
                    ext=Path(body['name']).suffix.lower()
                    if ext not in ('.png','.jpg','.jpeg','.webp','.mp4','.mov','.mkv','.webm','.avi','.wav','.mp3','.m4a','.flac','.ogg','.aac','.ttf','.otf','.woff','.woff2'):raise ContractError('Unsupported media format')
                    path=self.project/'media'/(uuid.uuid4().hex+ext);path.parent.mkdir(exist_ok=True);path.write_bytes(base64.b64decode(body['data'],validate=True))
                    result=projects.register(self.project,path,Path(body['name']).name,body.get('rights','review_pending'))
                elif route=='/api/render':
                    from .jobs import start
                    result=start(self.project,uuid.uuid4().hex)
                elif route=='/api/comfy-check':
                    from .workflows import build_from_form,preflight
                    result=preflight(build_from_form(body['kind'],body),body['native_endpoint'])
                elif route=='/api/comfy-submit':
                    from .workflows import build_from_form
                    from .comfy import submit
                    graph=build_from_form(body['kind'],body)
                    job_id=uuid.uuid4().hex;folder=self.project/'.openkatana/comfy'/job_id;folder.mkdir(parents=True)
                    workflow=folder/'workflow.json';write_json(workflow,graph);bindings=[]
                    if body['kind'] not in ('generation','qwen-generation'):
                        data=projects.state(self.project);assets={a['id']:a for a in data['assets']}
                        ids=[body.get('image')]+([body.get('second')] if body['kind']=='interpolation' else [])
                        for i,key in enumerate(ids):
                            clip=assets.get(key,{}).get('clip')
                            if not clip:raise ContractError('Choose an imported image or clip')
                            filename=clip.get('pattern','%05d.png')%0
                            source=local_path(self.project,clip['frames_dir']+'/'+filename);bindings.append(f'{i+1}.image={source}')
                    result=submit(workflow,folder/'job',body['endpoint'],bindings,body['native_endpoint']);result['studio_id']=job_id
                elif route in ('/api/comfy-collect','/api/comfy-import'):
                    from .comfy import collect
                    from .comfy_assets import import_outputs
                    key=str(uuid.UUID(body['id'])).replace('-','');folder=self.project/'.openkatana/comfy'/key/'job'
                    result=collect(folder) if route.endswith('collect') else import_outputs(folder,self.project,body.get('kind','clip'),body.get('clip'),body.get('fps',30))
                elif route=='/api/review':result=projects.review(self.project,local_path(self.project,'.openkatana/jobs/'+body['job_id']),body['decision'],body.get('notes',''))
                else:return self.json({'error':'Unknown endpoint'},404)
            return self.json(result)
        except Exception as e:return self.json({'error':str(e)},400)

def serve(root,port=0):
    root=root.resolve();projects.state(root)
    server=ThreadingHTTPServer(('127.0.0.1',port),partial(Studio,project=root))
    server.processes={};server.mutation_lock=threading.Lock()
    print(json.dumps({'studio':f'http://127.0.0.1:{server.server_port}','project':str(root)}),flush=True)
    try:server.serve_forever()
    finally:server.server_close()
