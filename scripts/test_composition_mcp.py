"""Exercise every new operation over the actual official MCP stdio adapter."""
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
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--package',type=Path,required=True)
    args=p.parse_args();root=args.out.resolve();root.mkdir(parents=True,exist_ok=False)
    env=dict(os.environ,PYTHONPATH=str(args.package.resolve()))
    params=StdioServerParameters(command=sys.executable,args=['-m','openkatana','mcp','--workspace',str(root/'projects')],env=env,cwd=str(root))
    called=[]
    async def call(session,tool_name,**kw):
        result=await session.call_tool(tool_name,kw)
        if result.isError:raise RuntimeError(str(result))
        called.append(tool_name);return result
    with (root/'stderr.log').open('w',encoding='utf-8') as log:
        async with stdio_client(params,errlog=log) as (read,write):
            async with ClientSession(read,write,read_timeout_seconds=timedelta(seconds=120)) as session:
                await session.initialize();tools=[t.name for t in (await session.list_tools()).tools]
                assert {'shape_text','edit_timeline','render_composition'}.issubset(tools)
                guide=await call(session,'read_guide',topic='composition');assert 'Contextual' in guide.structuredContent['markdown'] or 'contextual' in guide.structuredContent['markdown']
                await call(session,'create_project',name='Composition proof',project_id='demo')
                made=await call(session,'create_composition',project_id='demo',name='title',width=320,height=180,fps=12,frames=3)
                doc=made.structuredContent['document'];path=made.structuredContent['path']
                catalog=await call(session,'list_plugins',project_id='demo');assert catalog.structuredContent['plugins'][0]['id']=='core'
                changed=await call(session,'run_plugin_operator',project_id='demo',operator='core/batch',document=doc,
                                   parameters={'ops':[{'op':'replace','path':'/root/children/0/params/title','value':'Updated locally'}]})
                proposal=changed.structuredContent
                await call(session,'save_composition',project_id='demo',path=path,document=proposal['document'],revision=proposal['before_revision'])
                preview=await call(session,'inspect_composition',project_id='demo',path=path,frame=2)
                assert any(c.type=='image' for c in preview.content)
                render=await call(session,'render_composition',project_id='demo',path=path)
                assert render.structuredContent['clip']['n']==3 and not Path(render.structuredContent['clip']['frames_dir']).is_absolute()
                font=args.package.resolve()/'openkatana/fonts/anton_Anton-Regular.ttf'
                shaped=await call(session,'shape_text',project_id='demo',font=str(font),text='OPEN',size=48)
                assert Path(shaped.structuredContent['svg_file']).is_file()
                timeline={'canvas':{'w':64,'h':64,'fps':12,'frames':3},'clips':{},'shots':[{'f0':0,'f1':3,'special':{'type':'color','color':'#112233'}}]}
                saved=await call(session,'save_timeline',project_id='demo',timeline=timeline,revision=None)
                revision=saved.structuredContent['revision']
                revised=await call(session,'edit_timeline',project_id='demo',revision=revision,save=True,operations=[{'op':'replace','path':'/shots/0/special/color','value':'#445566'}])
                assert revised.structuredContent['saved'] and revised.structuredContent['revision']!=revision
                bad=await session.call_tool('save_composition',{'project_id':'demo','path':path,'document':doc,'revision':None})
                assert bad.isError
    report={'passed':True,'tools_discovered':len(tools),'calls':called,'stale_revision_rejected':True,'package':str(args.package.resolve()),'credits_used':0}
    (root/'validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))


if __name__=='__main__':asyncio.run(main())
