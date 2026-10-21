"""Exercise all six animation tools over MCP using the original live fixture's existing files."""
import argparse
import asyncio
from datetime import timedelta
import json
import os
from pathlib import Path
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    p=argparse.ArgumentParser();p.add_argument('--workspace',type=Path,required=True)
    p.add_argument('--package',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();workspace=args.workspace.resolve();out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    live=json.loads((workspace/'validation.json').read_text())
    root=workspace/'fixture'
    params=StdioServerParameters(command=sys.executable,args=['-m','openkatana','mcp','--workspace',str(workspace)],
                                cwd=str(out),env=dict(os.environ,PYTHONPATH=str(args.package.resolve())))
    calls=[]
    async def call(session,name,**arguments):
        response=await session.call_tool(name,arguments)
        if response.isError: raise RuntimeError(str(response))
        calls.append(name);return response.structuredContent
    with (out/'stderr.log').open('w',encoding='utf8') as err:
        async with stdio_client(params,errlog=err) as (read,write):
            async with ClientSession(read,write,read_timeout_seconds=timedelta(seconds=120)) as session:
                await session.initialize()
                tools={t.name:t for t in (await session.list_tools()).tools}
                new={'create_animation_kit','build_display_atlas','synthesize_score','assemble_blender_clips','analyze_render_motion','analyze_camera_motion'}
                assert new<=tools.keys()
                guide=await call(session,'read_guide',topic='animation');assert 'Camera paths' in guide['markdown']
                await call(session,'create_animation_kit',project_id='fixture',directory='mcp-kit',frames=6)
                atlas=await call(session,'build_display_atlas',project_id='fixture',document=json.loads((root/'animation/display.json').read_text()))
                assert Path(atlas['atlas']).is_file()
                score=await call(session,'synthesize_score',project_id='fixture',document=json.loads((root/'animation/score.json').read_text()))
                assert Path(score['audio']).is_file()
                assembled=await call(session,'assemble_blender_clips',project_id='fixture',receipts=live['blender_receipts'])
                assert assembled['frames']==12 and not assembled['saved_to_project']
                motion=await call(session,'analyze_render_motion',project_id='fixture',source=live['video'],cuts=[6],work_width=160)
                assert motion['frames']==12
                camera=await call(session,'analyze_camera_motion',project_id='fixture',document=json.loads((root/'animation/camera_samples.json').read_text()))
                assert camera['frames']==12
                rejected=await session.call_tool('create_animation_kit',{'project_id':'fixture','unexpected':True})
                assert rejected.isError
    result={'passed':True,'tools_discovered':len(tools),'calls':calls,'unknown_arguments_rejected':True,'credits_used':0}
    (out/'validation.json').write_text(json.dumps(result,indent=2),encoding='utf8');print(json.dumps(result))


if __name__=='__main__':asyncio.run(main())
