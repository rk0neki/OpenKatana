"""Exercise the new scene tools over real MCP stdio, optionally from an installed wheel."""
import argparse
import asyncio
from datetime import timedelta
import json
import os
from pathlib import Path
import sys

from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);parser.add_argument('--package',type=Path)
    args=parser.parse_args();root=args.out.resolve();root.mkdir(parents=True,exist_ok=False)
    env=dict(os.environ)
    if args.package:env['PYTHONPATH']=str(args.package.resolve())
    params=StdioServerParameters(command=sys.executable,args=['-m','openkatana','mcp','--workspace',str(root/'projects')],env=env,cwd=str(root))
    called=[]
    async def call(session,tool_name,**kw):
        result=await session.call_tool(tool_name,kw)
        if result.isError:raise RuntimeError(str(result))
        called.append(tool_name);return result
    with (root/'stderr.log').open('w',encoding='utf-8') as log:
        async with stdio_client(params,errlog=log) as (read,write):
            async with ClientSession(read,write,read_timeout_seconds=timedelta(seconds=180)) as session:
                await session.initialize();names=[t.name for t in (await session.list_tools()).tools]
                for name in ('create_scene3d','inspect_model3d','import_model3d','check_scene3d','render_scene3d','render_blender','morph_images'):assert name in names
                guide=await call(session,'read_guide',topic='scene3d');assert 'Three.js' in guide.structuredContent['markdown']
                await call(session,'create_project',name='3D integration',project_id='proof')
                from openkatana.scene3d import starter
                s=starter(width=160,height=96,frames=3,fps=12)
                created=await call(session,'create_scene3d',project_id='proof',name='demo',scene=s)
                scene=created.structuredContent['scene']
                await call(session,'check_scene3d',project_id='proof',scene=scene)
                preview=await call(session,'render_scene3d',project_id='proof',scene=scene,preview_frames=[0,2])
                assert sum(c.type=='image' for c in preview.content)==2
                rendered=await call(session,'render_scene3d',project_id='proof',scene=scene)
                assert rendered.structuredContent['clip']['n']==3
                assert not Path(rendered.structuredContent['clip']['frames_dir']).is_absolute()
                from test_scene3d_live import rigged_fixture
                model=root/'rig.gltf';rigged_fixture(model)
                await call(session,'inspect_model3d',source=str(model))
                await call(session,'import_model3d',project_id='proof',source=str(model),destination='scenes/demo/assets/rig')
                from PIL import Image,ImageDraw
                for name,x in [('a',25),('b',50)]:
                    image=Image.new('RGB',(96,96));draw=ImageDraw.Draw(image);draw.rectangle((x,30,x+15,55),fill='orange');image.save(root/f'{name}.png')
                points={'source':[[25/95,30/95],[40/95,30/95],[32/95,55/95]],'target':[[50/95,30/95],[65/95,30/95],[57/95,55/95]]}
                morphed=await call(session,'morph_images',project_id='proof',source=str(root/'a.png'),target=str(root/'b.png'),width=96,height=96,fps=12,frames=3,points=points)
                assert morphed.structuredContent['clip']['n']==3
    report={'passed':True,'tools_discovered':len(names),'called':called,'package_override':str(args.package),'credits_used':0}
    (root/'validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))


if __name__=='__main__':asyncio.run(main())
