"""Real stdio client/server lifecycle test with authored diagnostic media only."""
import argparse
import asyncio
from datetime import timedelta
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from openkatana.agent_api import TOOLS
from openkatana.render import run,write_json

async def main(root):
    root=root.resolve();root.mkdir(parents=True,exist_ok=False);workspace=root/'projects'
    source=root/'diagnostic.mp4'
    run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=160x96:rate=24',
         '-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','1','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',source])
    params=StdioServerParameters(command=sys.executable,args=['-m','openkatana','mcp','--workspace',str(workspace)],env={**os.environ,'OPENKATANA_MCP_TRACE':'1'})
    checks=[]
    async def call(session,tool_name,**args):
        print('MCP',tool_name,flush=True)
        result=await session.call_tool(tool_name,args)
        if result.isError:raise AssertionError((tool_name,result.content))
        checks.append(tool_name);return result
    with (root/'server-stderr.log').open('w',encoding='utf-8') as log:
        async with stdio_client(params,errlog=log) as (read,write):
            async with ClientSession(read,write,read_timeout_seconds=timedelta(seconds=120)) as session:
                init=await session.initialize();listed=await session.list_tools()
                assert {t.name for t in listed.tools}==set(TOOLS)
                assert all(t.inputSchema.get('type')=='object' for t in listed.tools)
                caps=(await call(session,'get_capabilities')).structuredContent;assert caps['name']=='OpenKatana'
                assert 'Claude' in (await call(session,'read_guide')).structuredContent['markdown']
                resources=await session.read_resource('openkatana://guide/timeline');assert resources.contents
                await call(session,'create_project',name='MCP diagnostic project',project_id='test')
                rejected=await session.call_tool('create_project',{'name':'escape','project_id':'../escape'});assert rejected.isError
                await call(session,'inspect_media',source=str(source))
                await call(session,'read_guide',topic='tool-audit')
                sheets=await call(session,'source_contact_sheet',project_id='test',source=str(source),end=1,step=.25)
                assert any(c.type=='image' for c in sheets.content)
                await call(session,'analyze_reference',project_id='test',source=str(source),duration=1)
                fonts=(await call(session,'list_fonts',directory='C:/Windows/Fonts',query='Arial',limit=5)).structuredContent['fonts']
                assert fonts
                await call(session,'preview_fonts',project_id='test',sources=[fonts[0]['path']],text='OpenKatana')
                segment=await call(session,'preview_segment',project_id='test',source=str(source),duration=.5,max_width=320)
                assert any(c.type=='audio' for c in segment.content)
                await call(session,'compare_reference',project_id='test',reference=str(source),rendered=str(source),times=[0,.5])
                batch=(await call(session,'import_media_batch',project_id='test',source=str(source),request_id='batch',excerpts=[{'duration':.25},{'start':.25,'duration':.25}])).structuredContent
                assert batch['state']=='succeeded' and len(batch['assets'])==2
                repeated=(await call(session,'import_media_batch',project_id='test',source=str(source),request_id='batch',excerpts=[{'duration':.25},{'start':.25,'duration':.25}])).structuredContent
                assert repeated['assets']==batch['assets']
                images=await call(session,'preview_source',project_id='test',source=str(source),times=[0,.5]);assert sum(c.type=='image' for c in images.content)==2
                asset=(await call(session,'import_media',project_id='test',source=str(source),start=.25,duration=.5,max_width=160,rights='own')).structuredContent
                audio=(await call(session,'import_media',project_id='test',source=str(source),audio_only=True,rights='own')).structuredContent
                edit=(await call(session,'plan_edit',project_id='test',asset_ids=[asset['id']],seconds=.5,width=320,height=192,fps=24,caption='TEST')).structuredContent['timeline']
                edit['audio']={'mode':'mix','tracks':[{'src':audio['path'],'duration':.5,'volume':.2}]}
                await call(session,'validate_timeline',project_id='test',timeline=edit)
                await call(session,'save_timeline',project_id='test',timeline=edit,revision=None)
                await call(session,'save_reference_plan',project_id='test',plan={'source':str(source),'fps':24,'frames':12,'cut_frames':[]})
                audit=(await call(session,'audit_reference_plan',project_id='test')).structuredContent
                assert audit['matches_plan']
                rejected=await session.call_tool('save_timeline',{'project_id':'test','timeline':edit,'revision':None});assert rejected.isError
                images=await call(session,'preview_timeline',project_id='test',frames=[0,8]);assert sum(c.type=='image' for c in images.content)==2
                image_path=Path(images.structuredContent['preview_images'][0]).relative_to(workspace/'test').as_posix()
                assert any(c.type=='image' for c in (await call(session,'view_image',project_id='test',path=image_path)).content)
                for operation in ('masks','faces','interpolate'):
                    analyzed=(await call(session,'analyze_clip',project_id='test',clip_id=asset['id'],operation=operation)).structuredContent
                    assert Path(analyzed['output']).is_relative_to(workspace/'test')
                await call(session,'get_project',project_id='test')
                workflow=(await call(session,'build_workflow',project_id='test',kind='matte')).structuredContent
                assert workflow['graph']['2']['class_type']=='OpenKatanaMatte'
                job=(await call(session,'start_render',project_id='test',request_id='render-once')).structuredContent
                again=(await call(session,'start_render',project_id='test',request_id='render-once')).structuredContent;assert again['id']==job['id']
        # Some Windows MCP hosts deliberately terminate all child workers on
        # disconnect. Recover the receipt and report interruption honestly.
        async with stdio_client(params,errlog=log) as (read,write):
            async with ClientSession(read,write,read_timeout_seconds=timedelta(seconds=120)) as session:
                await session.initialize();deadline=time.monotonic()+90;interrupted=False
                while True:
                    result=(await call(session,'get_render',project_id='test',job_id=job['id'])).structuredContent
                    if result['state']=='succeeded':break
                    if result['state']=='interrupted' and not interrupted:
                        interrupted=True
                        again=(await call(session,'start_render',project_id='test',request_id='render-once')).structuredContent
                        assert again['id']==job['id'] and again['state']=='interrupted'
                        job=(await call(session,'start_render',project_id='test',request_id='render-after-interruption')).structuredContent
                        continue
                    assert result['state']=='running',result
                    if time.monotonic()>deadline:raise TimeoutError(result)
                    await asyncio.sleep(.5)
                assert result['frames']==12,result
                await call(session,'review_render',project_id='test',job_id=job['id'],decision='approved',notes='Diagnostic protocol test only; no creative or human approval')
                again=(await call(session,'start_render',project_id='test',request_id=job['request_id'])).structuredContent;assert again['id']==job['id']
                assert len(list((workspace/'test/.openkatana/jobs').glob('*/job.json')))==1+int(interrupted)
                with Path(result['video_path']).open('ab') as f:f.write(b'tamper-test')
                rejected=await session.call_tool('review_render',{'project_id':'test','job_id':job['id'],'decision':'approved','notes':'Must reject modified output'})
                assert rejected.isError
    cli=json.loads(subprocess.check_output([sys.executable,'-m','openkatana','call','get_capabilities','--workspace',str(workspace)],text=True))
    assert cli['tools']==caps['tools']
    def cli_call(name,arguments):
        args_path=root/'cli-arguments.json';write_json(args_path,arguments)
        return json.loads(subprocess.check_output([sys.executable,'-m','openkatana','call',name,
            '--workspace',str(workspace),'--arguments',str(args_path)],text=True,encoding='utf-8'))
    job=cli_call('start_render',{'project_id':'test','request_id':'cli-render'})
    deadline=time.monotonic()+90
    while True:
        status=cli_call('get_render',{'project_id':'test','job_id':job['id']})
        if status['state']=='succeeded':break
        assert status['state']=='running',status
        if time.monotonic()>deadline:raise TimeoutError(status)
        await asyncio.sleep(.5)
    assert status['frames']==12
    write_json(root/'result.json',{'passed':True,'protocol':'real MCP stdio SDK client/server','tools':len(TOOLS),
        'checked_tools':sorted(set(checks)),'preview_image_blocks':True,'render_frames':12,'job_recovered_after_reconnect':True,
        'host_terminated_worker_on_disconnect':interrupted,
        'duplicate_render_prevented':True,'stale_save_rejected':True,'changed_output_review_rejected':True,
        'path_escape_rejected':True,'cli_mcp_catalog_agree':True,'cli_render_after_command_exits':True,'creative_edit_made':False})
    print((root/'result.json').read_text(encoding='utf-8'))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
    asyncio.run(main(parser.parse_args().out))
