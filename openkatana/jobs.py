"""Persistent local render jobs shared by CLI, MCP and the local editor."""
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
from . import projects
from .contracts import ContractError,validate
from .render import write_json

def alive(pid):
    if os.name=='nt':
        import ctypes
        from ctypes import wintypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        handle=kernel.OpenProcess(0x1000,False,pid)
        if not handle:return None if ctypes.get_last_error()==5 else False
        try:
            code=wintypes.DWORD()
            return code.value==259 if kernel.GetExitCodeProcess(handle,ctypes.byref(code)) else None
        finally:kernel.CloseHandle(handle)
    try:os.kill(pid,0);return True
    except ProcessLookupError:return False
    except PermissionError:return None

def folder(root,job_id):
    return root/'.openkatana/jobs'/uuid.UUID(job_id).hex

def start(root,request_id):
    root=root.resolve();state=projects.state(root)
    if not state['timeline']:raise ContractError('Save a timeline before rendering')
    validate(state['timeline'],root)
    if not isinstance(request_id,str) or not 1<=len(request_id)<=128:raise ContractError('Supply a request ID of 1..128 characters')
    job_id=uuid.uuid5(uuid.NAMESPACE_URL,str(root)+'/'+request_id).hex;target=folder(root,job_id)
    if target.exists():
        saved=json.loads((target/'job.json').read_text(encoding='utf-8'))
        if saved['revision']!=state['revision']:raise ContractError('This request ID belongs to an earlier timeline; use a new ID for the revision')
        return status(root,job_id)
    target.mkdir(parents=True,exist_ok=False)
    snapshot=root/f'timeline-{job_id}.json';write_json(snapshot,state['timeline'])
    job={'id':job_id,'request_id':request_id,'state':'running','revision':state['revision'],'created_at':projects.stamp(),
         'video':f'.openkatana/jobs/{job_id}/render/video.mp4'}
    write_json(target/'job.json',job)
    try:
        with (target/'log.txt').open('w',encoding='utf-8') as log:
            proc=subprocess.Popen([sys.executable,'-m','openkatana.job_worker',str(root),job_id],stdin=subprocess.DEVNULL,
                stdout=log,stderr=subprocess.STDOUT,close_fds=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        write_json(target/'process.json',{'pid':proc.pid})
    except Exception as error:
        job.update(state='failed',message=str(error));write_json(target/'job.json',job);raise
    return status(root,job_id)

def status(root,job_id):
    target=folder(root,job_id);job=json.loads((target/'job.json').read_text(encoding='utf-8'))
    receipt=target/'render/receipt.json'
    if receipt.is_file():
        data=json.loads(receipt.read_text(encoding='utf-8'))
        if data.get('ok'):job.update(state='succeeded',frames=data['frames'],sha256=data['sha256'])
    process=target/'process.json'
    if job['state']=='running' and process.is_file():
        pid=json.loads(process.read_text(encoding='utf-8'))['pid'];job['pid']=pid
        if alive(pid) is False:job.update(state='interrupted',message='Worker exited without a completed receipt; this request is not automatically restarted')
        job['rendered_frames']=len(list((target/'render/frames').glob('*.png')))
    if job['state']=='failed' and (target/'log.txt').is_file():job['message']=(target/'log.txt').read_text(encoding='utf-8',errors='replace')[-3000:]
    job.update(project=str(root.resolve()),video_path=str((root/job['video']).resolve()))
    return job

def run_worker(root,job_id):
    from .render import render
    target=folder(root,job_id);job=json.loads((target/'job.json').read_text(encoding='utf-8'))
    try:
        result=render(root/f'timeline-{job_id}.json',target/'render')
        job.update(state='succeeded',frames=result['frames'],sha256=result['sha256'])
    except Exception as error:
        job.update(state='failed',message=f'{type(error).__name__}: {error}')
        print(job['message'],file=sys.stderr)
    finally:
        job['finished_at']=projects.stamp();write_json(target/'job.json',job)
