"""Real browser walkthrough against a disposable local project."""
import argparse,json,os,subprocess,sys,time
from pathlib import Path
from PIL import Image,ImageDraw
from playwright.sync_api import sync_playwright
from openkatana.projects import create,save,state
from openkatana.agent_api import TOOLS
from openkatana.render import chrome_path,write_json

def wait(page,expression,timeout=60000):
    deadline=time.monotonic()+timeout/1000
    while time.monotonic()<deadline:
        if page.evaluate('()=>'+expression):return
        time.sleep(.1)
    raise TimeoutError(page.locator('#status').inner_text())

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);args=p.parse_args();root=args.out.resolve();create(root,'Studio integration test')
    source=root/'test-plate.png';im=Image.new('RGB',(640,360),'#102735');d=ImageDraw.Draw(im);d.ellipse((200,50,440,320),fill='#e55d7c');d.rectangle((0,280,640,360),fill='#f0b756');im.save(source)
    proc=subprocess.Popen([sys.executable,'-m','openkatana','studio',str(root)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    try:
        address=json.loads(proc.stdout.readline())['studio'];errors=[]
        with sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path=chrome_path(),headless=True,args=['--disable-gpu']);page=browser.new_page(viewport={'width':1440,'height':1000},permissions=['clipboard-read','clipboard-write']);page.on('pageerror',lambda e:errors.append(str(e)));page.goto(address)
            page.wait_for_selector('#projectName:has-text("Studio integration test")',state='attached')
            assert page.locator('#view-start').is_visible()
            assert not page.locator('.resume-bar, footer.statusbar').count()
            assert page.get_by_role('link',name='Give us a star on GitHub').get_attribute('href')=='https://github.com/rk0neki/OpenKatana'
            page.screenshot(path=str(root/'desktop-start.png'),full_page=True)
            page.locator('[data-connect]').first.click()
            setup=page.locator('#setupPrompt').input_value()
            assert 'https://github.com/rk0neki/OpenKatana.git' in setup
            assert 'python scripts/setup.py' in setup
            assert not page.locator('[data-agent]').count()
            assert str(root) not in setup and str(Path.home()) not in setup
            page.locator('#copySetup').click()
            wait(page,"document.getElementById('copyFeedback').textContent.startsWith('Copied')")
            assert page.evaluate('navigator.clipboard.readText()').replace('\r\n','\n')==setup
            page.locator('#connectDialog').screenshot(path=str(root/'onboarding.png'))
            page.locator('.mcp-setup>summary').click();page.locator('#openMcpGuide').click()
            assert not page.locator('#connectDialog').is_visible()
            wait(page,"document.getElementById('guideText').textContent.includes('Optional MCP setup')")
            page.keyboard.press('Escape');assert not page.locator('#guideDialog').is_visible()
            page.locator('.main-nav [data-view="tools"]').click()
            page.wait_for_selector('.tool-card')
            assert page.locator('.tool-card').count()==len(TOOLS)
            page.locator('#toolSearch').fill('morph_images')
            assert page.locator('.tool-card').count()==1
            page.locator('.tool-open').focus();page.keyboard.press('Enter')
            wait(page,"document.getElementById('guideText').textContent.includes('Comfy')")
            header=page.locator('#guideDialog .dialog-heading').bounding_box()
            page.locator('#guideText').evaluate('(el)=>el.scrollTop=el.scrollHeight')
            assert page.locator('#guideText').evaluate('(el)=>el.scrollTop')>0
            assert page.locator('#guideDialog .dialog-heading').bounding_box()==header
            page.locator('#copyGuide').click()
            wait(page,"document.getElementById('copyGuide').textContent==='Copied'")
            assert page.evaluate('navigator.clipboard.readText()').replace('\r\n','\n')==page.locator('#guideText').text_content().replace('\r\n','\n')
            with page.expect_download() as downloading:
                page.locator('#downloadGuide').click()
            download=downloading.value
            assert download.suggested_filename=='openkatana-comfy-models.md'
            guide_file=root/download.suggested_filename;download.save_as(str(guide_file))
            assert guide_file.read_text(encoding='utf-8')==page.locator('#guideText').text_content().replace('\r\n','\n')
            page.locator('#guideDialog').screenshot(path=str(root/'guide-scrolled.png'))
            page.get_by_role('button',name='Close guide').click()
            assert not page.locator('#guideDialog').is_visible()
            page.locator('.tool-card').get_by_role('button',name='Add to brief').click()
            assert 'morph_images' in page.locator('#creativeBrief').input_value()
            assert page.locator('#view-studio').is_visible()
            assert page.locator('.studio-steps button').count()==3
            assert not page.locator('#refinePanel').get_attribute('open')
            page.locator('#refinePanel>summary').click()
            page.locator('.inspector-tabs [data-inspector="comfy"]').click()
            page.locator('#workflowKind').select_option('qwen-generation')
            assert page.locator('#qwenComponents').is_visible()
            page.locator('#checkWorkflow').click();wait(page,"document.getElementById('status').textContent.includes('text encoder')")
            assert page.locator('#notification').is_visible()
            page.locator('#dismissStatus').click();assert not page.locator('#notification').is_visible()
            page.locator('#workflowKind').select_option('matte')
            assert not page.locator('#qwenComponents').is_visible()
            page.get_by_text('Media permissions',exact=True).click()
            page.locator('#rights').select_option('own');page.locator('#files').set_input_files(str(source));wait(page,"document.querySelectorAll('[data-asset]').length===1")
            page.locator('.quick-edit>summary').click()
            page.get_by_text('Opening lettering',exact=True).click()
            page.locator('#seconds').fill('1');page.locator('#caption').fill('OPEN KATANA');page.locator('#plan').click();wait(page,"document.getElementById('status').textContent.startsWith('Edit prepared')")
            page.locator('.inspector-tabs [data-inspector="shot"]').click()
            page.locator('#speed').fill('0');page.locator('#transition').select_option('mosaic');page.locator('#update').click();wait(page,"document.getElementById('status').textContent.startsWith('Shot updated')")
            page.locator('#save').click();wait(page,"document.getElementById('status').textContent.startsWith('Saved')")
            page.locator('#scrub').fill('20');page.locator('#scrub').dispatch_event('input');page.wait_for_timeout(400)
            # Simulate an agent saving the same project while the human reviews it.
            current=state(root);current['timeline']['shots'][0]['cam']['z']=1.1
            save(root,current['timeline'],current['revision'])
            wait(page,"document.getElementById('zoom').value==='1.1'")
            # Unsaved human changes must never adopt an external revision and overwrite it.
            page.locator('#zoom').fill('1.2');page.locator('#update').click();wait(page,"document.getElementById('status').textContent.startsWith('Shot updated')")
            current=state(root);current['timeline']['shots'][0]['cam']['z']=1.3
            save(root,current['timeline'],current['revision'])
            page.locator('#syncNotice').wait_for(state='visible',timeout=15000)
            assert page.locator('#zoom').input_value()=='1.2'
            page.locator('#save').click();wait(page,"document.getElementById('status').textContent.includes('changed since')")
            assert state(root)['timeline']['shots'][0]['cam']['z']==1.3
            page.once('dialog',lambda dialog:dialog.accept());page.locator('#reloadProject').click()
            wait(page,"document.getElementById('status').textContent==='Loaded the saved project.'")
            assert page.locator('#zoom').input_value()=='1.3'
            page.locator('#refinePanel>summary').click()
            page.locator('.quick-edit>summary').click()
            page.locator('.main-nav [data-view="studio"]').click()
            page.screenshot(path=str(root/'studio.png'),full_page=True)
            page.locator('#render').click();wait(page,"document.querySelector('#jobs video')!==null",timeout=60000)
            page.locator('#jobs video').evaluate('(v)=>v.load()');wait(page,"document.querySelector('#jobs video').readyState>=1")
            response=page.request.post(address+'/api/save',data={'timeline':json.loads((root/'timeline.json').read_text()),'revision':'stale'})
            assert response.status==400
            rejected=page.request.post(address+'/api/render',headers={'Origin':'https://outside.example'},data={});assert rejected.status==403
            assert page.request.get(address+'/api/guide?topic=../../private').status==400
            assert page.request.get(address+'/api/tools',headers={'Host':'outside.example'}).status==403
            assert page.request.get(address+'/app/studio.css').status==200
            assert page.request.get(address+'/app/openkatana-logo.jpg').status==200
            assert "style-src 'self'" in page.request.get(address).headers['content-security-policy']
            page.set_viewport_size({'width':390,'height':844})
            for view in ('start','studio','tools','review'):
                page.locator('.main-nav [data-view="'+view+'"]').click()
                assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth'),view
                page.screenshot(path=str(root/('mobile-'+view+'.png')),full_page=True)
            page.locator('.main-nav [data-view="tools"]').click()
            page.locator('#toolSearch').fill('render_scene3d')
            page.locator('.tool-open').click()
            wait(page,"document.getElementById('guideText').textContent.includes('3D')")
            header=page.locator('#guideDialog .dialog-heading').bounding_box()
            page.locator('#guideText').evaluate('(el)=>el.scrollTop=el.scrollHeight')
            assert page.locator('#guideDialog .dialog-heading').bounding_box()==header
            assert page.get_by_role('button',name='Close guide').is_visible()
            assert page.locator('#copyGuide').is_visible()
            assert page.locator('#downloadGuide').is_visible()
            assert page.locator('#guideDialog').evaluate('(el)=>el.scrollWidth<=el.clientWidth')
            page.locator('#guideDialog').screenshot(path=str(root/'mobile-guide-scrolled.png'))
            page.get_by_role('button',name='Close guide').click()
            browser.close();assert not errors,errors
        job=json.loads(next((root/'.openkatana/jobs').glob('*/job.json')).read_text());receipt=json.loads((root/'.openkatana/jobs'/job['id']/'render/receipt.json').read_text());assert receipt['ok']
        write_json(root/'result.json',{'passed':True,'browser_errors':errors,'import_plan_edit_save_render':True,'onboarding_and_tool_discovery':True,'setup_clipboard':True,'fixed_guide_toolbar_and_clipboard':True,'guide_download_content_and_filename':True,'keyboard_tool_cards':True,'guided_studio':True,'local_mcp_setup_guide':True,'dismissible_notifications':True,'tool_count':len(TOOLS),'external_agent_sync':True,'unsaved_human_edit_protected':True,'mobile_views_without_overflow':True,'stale_save_rejected':True,'cross_origin_write_rejected':True,'render_frames':receipt['frames'],'human_visual_approval':False})
        print((root/'result.json').read_text())
    finally:
        proc.terminate()
        try:proc.wait(timeout=10)
        except subprocess.TimeoutExpired:proc.kill();proc.wait()
if __name__=='__main__':main()
