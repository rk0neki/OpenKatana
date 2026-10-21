"""Exercise renderer selection and mixed-renderer assembly over actual installed-package MCP."""
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
    args=p.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    workspace=args.workspace.resolve();root=workspace/'mcp-fixture';calls=[]
    params=StdioServerParameters(command=sys.executable,args=['-m','openkatana','mcp','--workspace',str(workspace)],
                                cwd=str(out),env=dict(os.environ,PYTHONPATH=str(args.package.resolve())))
    async def call(session,tool_name,**arguments):
        result=await session.call_tool(tool_name,arguments)
        if result.isError:raise RuntimeError(str(result))
        calls.append(tool_name);return result.structuredContent
    with (out/'stderr.log').open('w',encoding='utf8') as err:
        async with stdio_client(params,errlog=err) as (read,write):
            async with ClientSession(read,write,read_timeout_seconds=timedelta(seconds=180)) as session:
                await session.initialize();tools={t.name:t for t in (await session.list_tools()).tools}
                assert {'create_webgl_kit','assemble_render_clips','render_scene3d','render_blender'}<=tools.keys()
                guide=await call(session,'read_guide',topic='webgl');assert 'Choose the renderer' in guide['markdown']
                await call(session,'create_project',name='Renderer choice fixture',project_id='mcp-fixture')
                web=await call(session,'create_webgl_kit',project_id='mcp-fixture',width=160,height=96,fps=24,frames=6)
                bad=await session.call_tool('render_scene3d',{'project_id':'mcp-fixture','scene':web['scene'],'preview_frames':[0]})
                assert bad.isError
                rendered=await call(session,'render_scene3d',project_id='mcp-fixture',scene=web['scene'],start=3,end=5,trusted_script=True)
                assert rendered['frames']==3 and rendered['source_frame_start']==3
                assert rendered['runtime']['engine']=='Three.js'
                blend=await call(session,'create_animation_kit',project_id='mcp-fixture',width=160,height=96,fps=24,frames=6)
                other=await call(session,'render_blender',project_id='mcp-fixture',source=blend['script'],start=3,end=5,trusted_script=True)
                receipts=[Path(rendered['receipt']).relative_to(root).as_posix(),
                          (Path(other['video']).parent/'receipt.json').relative_to(root).as_posix()]
                assembled=await call(session,'assemble_render_clips',project_id='mcp-fixture',receipts=receipts,contiguous=False)
                assert assembled['frames']==6 and len(assembled['timeline']['clips'])==2 and not assembled['saved_to_project']
                invalid=await session.call_tool('create_webgl_kit',{'project_id':'mcp-fixture','unexpected':True});assert invalid.isError
    report={'passed':True,'tools_discovered':len(tools),'calls':calls,'webgl_and_blender_rendered':True,
            'mixed_renderer_timeline_validated':True,'untrusted_module_rejected':True,'unknown_arguments_rejected':True,
            'credits_used':0,'model_calls':0}
    (out/'validation.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))


if __name__=='__main__':asyncio.run(main())
