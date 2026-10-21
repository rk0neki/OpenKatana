"""Exercise new graphics, original letters and browser determinism on own plates."""
import argparse,base64,json,threading,shutil
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from PIL import Image,ImageDraw
from playwright.sync_api import sync_playwright
from openkatana.render import render,write_json,Handler,chrome_path,digest
from openkatana.contracts import validate

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path);args=p.parse_args();root=args.out.resolve();root.mkdir(parents=True)
    (root/'plate').mkdir();(root/'mask').mkdir();(root/'font').mkdir();shutil.copyfile('C:/Windows/Fonts/arial.ttf',root/'font/test.ttf')
    im=Image.new('RGB',(640,360),'#102735');d=ImageDraw.Draw(im);d.rectangle((0,280,640,360),fill='#f0b756');d.ellipse((220,50,420,320),fill='#e55d7c');d.rectangle((250,130,300,170),fill='#ffffff');im.save(root/'plate/00000.png')
    mask=Image.new('RGBA',im.size,(255,255,255,0));ImageDraw.Draw(mask).ellipse((220,50,420,320),fill='white');mask.save(root/'mask/00000.png')
    cases=[]
    for kind in ('iris','stripes','torn'):
        for side in ('in','out'):cases.append((kind+'-'+side,{side:{'type':'wipe','kind':kind,'d':.8,'feather':2,'color':'#1d1b32'}}))
    for name in ('grain','dust','vignette','leak','contour'):cases.append((name,{'fx':{name:True}}))
    cases += [('particles',{'fx':{'particles':{'shape':'confetti','burst':40,'rate':20,'gravity':200,'seed':3}}}),
              ('polygon3d',{'fx':{'polygon3d':{'points':[[-150,-100,0],[150,-100,0],[150,100,0],[-150,100,0]],'fill':'#66e7c8','ry':.4,'spin':1}}}),
              ('morph',{'fx':{'morph':{'from':[[.2,.2],[.8,.2],[.8,.8],[.2,.8]],'to':[[.5,.1],[.9,.5],[.5,.9],[.1,.5]],'fill':'#66e7c8','ease':'inout'}}}),
              ('big-behind',{'fx':{'big':{'text':'OPEN','family':'Test','size':190}}}),
              ('burst',{'fx':{'burst':{'letters':'WOW','family':'Test'}}})]
    for name in ('levels','threshold','duotone','xerox','neg','posterize'):cases.append((name,{'look':{'type':name}}))
    for mode in ('hold','write','slam','static'):
        cases.append(('graffiti-'+mode,{'layers':[{'type':'graffiti','word':'OPEN\nKATANA','mode':mode,'region':'full','ink':'#161c29','echo':'#66e7c8'}]}))
    cases.append(('glyphs',{'layers':[{'type':'graffiti','lines':['ABCDEFGHIJKLM','NOPQRSTUVWXYZ','0123456789','!?.,:-\'/+*#&'],'mode':'hold','region':'full','cap':60}]}))
    n=24;edit={'canvas':{'w':640,'h':360,'fps':30,'frames':len(cases)*n},'clips':{'A':{'frames_dir':'plate','mask_dir':'mask','n':1,'fps':30,'w':640,'h':360}},'fonts':[{'family':'Test','url':'font/test.ttf'}],'shots':[{'f0':i*n,'f1':(i+1)*n,'clip':'A','speed':0,**opts} for i,(_,opts) in enumerate(cases)]}
    write_json(root/'timeline.json',edit);validate(edit,root);receipt=render(root/'timeline.json',root/'render')
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(Handler,project=root));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();checks=[]
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path=chrome_path(),headless=True,args=['--disable-gpu']);page=browser.new_page();page.goto(f'http://127.0.0.1:{server.server_port}/app/render.html');page.evaluate('(e)=>OpenKatana.boot(e)',edit)
            for f in list(range(n//2,edit['canvas']['frames'],n))[::-1]+[0,5,0]:
                result=page.evaluate('(f)=>OpenKatana.render(f)',f)
                assert base64.b64decode(result['png'])==(root/f'render/frames/{f:05d}.png').read_bytes();checks.append(f)
            browser.close()
    finally:server.shutdown();server.server_close();thread.join()
    sheet=Image.new('RGB',(960,((len(cases)+2)//3)*206),'#0d1117');draw=ImageDraw.Draw(sheet)
    for i,(name,_) in enumerate(cases):
        frame=root/f'render/frames/{i*n+12:05d}.png';x=(i%3)*320;y=(i//3)*206
        sheet.paste(Image.open(frame).resize((320,180)),(x,y+24));draw.text((x+8,y+6),name,fill='white')
    sheet.save(root/'contact-sheet.jpg')
    write_json(root/'result.json',{'passed':True,'cases':len(cases),'frames':receipt['frames'],'random_access_checks':len(checks),'scope':'Own graphics and repeatability; not a general visual quality score'})
    print((root/'result.json').read_text())
if __name__=='__main__':main()
