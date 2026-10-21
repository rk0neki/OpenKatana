"""Real MCP checks for HDR and reusable model builders; optional reuse of live job receipts."""
import argparse
import asyncio
from datetime import timedelta
import json
import os
from pathlib import Path
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import numpy as np


async def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--package',type=Path,required=True)
    p.add_argument('--live-projects',type=Path);p.add_argument('--live-config',type=Path)
    args=p.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    sys.path.insert(0,str(args.package.resolve()))
    from openkatana.hdr import encode_linear
    canvas={'width':64,'height':32,'fps':4,'frames':4}
    raw=out/'original.raw';pixels=np.full((3,32,64),5,dtype='<f4');raw.write_bytes(pixels.tobytes()*4)
    source=out/'original.mkv';encode_linear(raw,canvas,source,'pq',True)
    workspace=(args.live_projects or out/'projects').resolve()
    env=dict(os.environ,PYTHONPATH=str(args.package.resolve()))
    parameters=StdioServerParameters(command=sys.executable,args=['-m','openkatana','mcp','--workspace',str(workspace)],cwd=str(out),env=env)
    checks={}
    project_id='hdr-protocol-'+out.name[:40]
    async def call(session,tool,**kw):
        result=await session.call_tool(tool,kw)
        if result.isError:raise RuntimeError(str(result))
        return result.structuredContent
    with (out/'stderr.log').open('w',encoding='utf8') as log:
        async with stdio_client(parameters,errlog=log) as (read,write):
            async with ClientSession(read,write,read_timeout_seconds=timedelta(seconds=120)) as session:
                await session.initialize();names=[x.name for x in (await session.list_tools()).tools]
                assert len(names)==64
                checks['inventory']=len(names)
                assert 'float32' in (await call(session,'read_guide',topic='hdr'))['markdown']
                await call(session,'create_project',name='HDR protocol validation',project_id=project_id)
                imported=await call(session,'import_hdr_media',project_id=project_id,source=str(source),fps=4,duration=1)
                assert imported['asset']['clip']['n']==4
                rendered=await call(session,'render_hdr',project_id=project_id,document=imported['hdr_document'])
                assert Path(rendered['master']).is_file() and abs(rendered['max_rgb_nits']-500)<2
                checks['hdr_import_render']=True
                built=await call(session,'build_workflow',project_id=project_id,kind='qwen-edit',parameters={'model':'installed-model','encoder':'installed-encoder','vae':'installed-vae','references':2})
                assert set(built['asset_ports'])=={'21.image','22.image'}
                checks['reference_builder']=True
                if args.live_config:
                    config=json.loads(args.live_config.read_text(encoding='utf8'))
                    old=json.loads((workspace.parent/'validation.json').read_text(encoding='utf8'))
                    params=config['qwen-edit']
                    resumed=await call(session,'run_model_workflow',project_id='models',kind='qwen-edit',parameters=params,assets={'21.image':'source.png','22.image':'reference.png'},request_id='test-qwen-edit')
                    assert resumed['receipt']['job_id']==old['qwen-edit']['receipt']['job_id']
                    assert resumed['receipt']['state']=='collected'
                    checks['original_job_resumed_without_resubmission']=True
    (out/'validation.json').write_text(json.dumps({'passed':True,'checks':checks,'package':str(args.package)},indent=2),encoding='utf8')
    print(json.dumps(checks))


if __name__=='__main__':asyncio.run(main())
