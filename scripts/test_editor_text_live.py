"""Actual browser typography checks for editor-facing controls."""
import argparse,base64,io,json
from pathlib import Path
import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright
from openkatana.render import chrome_path,write_json

def main(out):
    out.mkdir(parents=True,exist_ok=False)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=chrome_path(),headless=True,args=['--disable-gpu'])
        page=browser.new_page();page.set_content('<canvas id="c" width="480" height="240"></canvas>')
        page.add_script_tag(path=str(Path('openkatana/web/typography.js').resolve()))
        font=base64.b64encode(Path('C:/Windows/Fonts/arial.ttf').read_bytes()).decode()
        page.evaluate('async b=>{let f=new FontFace("Test",`url(data:font/ttf;base64,${b})`);await f.load();document.fonts.add(f);}',font)
        base={'text':'H','family':'Test','size':100,'weight':400,'style':'normal','shadow':False,'stroke':None,'fill':'#ffffff','pos':[.2,.5],'align':'left','render_style':'explicit'}
        def frame(name,changes,t=0):
            png=page.evaluate('([item,t])=>{let c=document.querySelector("canvas"),x=c.getContext("2d");x.fillStyle="black";x.fillRect(0,0,480,240);OpenKatanaText(x,item,t,2,30,480,240);return c.toDataURL().split(",")[1];}',[{**base,**changes},t])
            raw=base64.b64decode(png);(out/(name+'.png')).write_bytes(raw)
            return np.asarray(Image.open(io.BytesIO(raw)).convert('RGB'))
        plain=frame('plain',{});typed=frame('typed',{'anim':'type','lw':0},.5)
        assert np.array_equal(plain,typed),'Explicit typewriter must honor font/alignment/no stroke'
        legacy=frame('legacy',{'anim':'type','render_style':'legacy'},.5)
        assert not np.array_equal(plain,legacy)
        solid=frame('solid',{'text':'O'});hollow=frame('hollow',{'text':'O','fill':None,'stroke':'#ffffff','lw':1})
        assert 0<np.count_nonzero(hollow)<np.count_nonzero(solid)
        off=frame('off',{'opacity_keys':[[0,0],[.5,1]]},.25);assert not off.any()
        on=frame('on',{'opacity_keys':[[0,0],[.5,1]]},.5);assert np.array_equal(on,plain)
        a=frame('letter-a',{'text':'HH','letter_opacity_keys':[[[0,1],[.5,0]],[[0,0],[.5,1]]]},0)
        b=frame('letter-b',{'text':'HH','letter_opacity_keys':[[[0,1],[.5,0]],[[0,0],[.5,1]]]},.6)
        assert a.any() and b.any() and not np.array_equal(a,b)
        normal=frame('spacing-normal',{'text':'HH','tracking':0});wide=frame('spacing-wide',{'text':'HH','tracking':20})
        assert np.where(wide.max(2)>0)[1].max()>np.where(normal.max(2)>0)[1].max()
        flicker={'text':'HH','flicker':{'per_letter':True,'hz':12,'seed':7,'duty':.5}}
        first=frame('flicker',flicker,.7);frame('other-time',flicker,.2)
        assert np.array_equal(first,frame('flicker-repeat',flicker,.7))
        browser.close()
    write_json(out/'result.json',{'passed':True,'hollow_text':True,'clean_typewriter_matches_plain':True,'explicit_opacity_timing':True,
        'per_letter_timing':True,'tracking':True,'random_access_flicker':True,'reference_parity':'Legacy regression measured separately; new options have no parity claim'})
    print((out/'result.json').read_text(encoding='utf-8'))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);main(p.parse_args().out)
