"""Bounded source and timeline previews for agent visual inspection."""
import base64
from functools import partial
from .http_runtime import LocalHTTPServer
from pathlib import Path
import threading
from .contracts import ContractError,validate,number
from .render import Handler,chrome_path,run,write_json

def source_frames(source,out,times):
    if not 1<=len(times)<=12:raise ContractError('Request 1..12 source times per preview')
    for t in times:number(t,'source time',0)
    out.mkdir(parents=True,exist_ok=False);images=[]
    for i,t in enumerate(times):
        path=out/f'{i:02d}.png'
        if Path(source).suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp'):
            from PIL import Image, ImageOps
            if t != 0: raise ContractError('Still-image previews use time 0')
            with Image.open(source) as original:
                im = ImageOps.exif_transpose(original).convert('RGB')
                im.thumbnail((768, 768), Image.Resampling.LANCZOS)
                im.save(path)
        else:
            run(['ffmpeg','-v','error','-ss',str(t),'-i',source,'-frames:v','1','-vf','scale=768:-2',path])
        if not path.is_file():raise ContractError(f'No source picture at {t} seconds')
        images.append(str(path.resolve()))
    return {'times':times,'preview_images':images,'source':str(source)}

def timeline_frames(edit,root,out,frames):
    from .render import playwright
    sync_playwright = playwright()
    edit=validate(edit,root)
    if not 1<=len(frames)<=12:raise ContractError('Request 1..12 timeline frames per preview')
    for f in frames:number(f,'frame',0,edit['canvas']['frames']-1,integer=True)
    out.mkdir(parents=True,exist_ok=False);write_json(out/'timeline.json',edit)
    server=LocalHTTPServer(('127.0.0.1',0),partial(Handler,project=root));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();images=[]
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path=chrome_path(),headless=True,args=['--disable-gpu'])
            try:
                from .render import guard_page, open_engine
                page=browser.new_page();guard_page(page,server.server_port);open_engine(page,server.server_port);page.evaluate('(e)=>OpenKatana.boot(e)',edit)
                for f in frames:
                    result=page.evaluate('(f)=>OpenKatana.render(f)',f);path=out/f'{f:05d}.png'
                    path.write_bytes(base64.b64decode(result['png']));images.append(str(path.resolve()))
            finally:browser.close()
    finally:server.shutdown();server.server_close();thread.join()
    return {'frames':frames,'preview_images':images,'audio':'Preview frames are silent; review audio in the full render',
            'flat_frames':flat_frames(edit,frames,images)}


FLAT_SPECIALS=('black','white','color','flash')


def flat_frames(edit,frames,images):
    """Previewed frames that came out as one flat colour (every channel within 2 levels) where no flat special is
    scheduled: usually a broken effect value (a NaN in hook params paints nothing) rather than intent."""
    from PIL import Image
    flat=[]
    for f,path in zip(frames,images):
        specials=[s.get('type') for s in edit.get('specials',[]) if s['f0']<=f<s['f1']]
        specials+=[s['special'].get('type') for s in edit['shots'] if s['f0']<=f<s['f1'] and isinstance(s.get('special'),dict)]
        if any(t in FLAT_SPECIALS for t in specials):continue
        with Image.open(path) as im:
            ext=im.convert('RGB').getextrema()
        if all(hi-lo<=2 for lo,hi in ext):flat.append({'frame':f,'rgb':[round((lo+hi)/2) for lo,hi in ext]})
    return flat
