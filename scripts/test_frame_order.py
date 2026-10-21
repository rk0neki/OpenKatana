"""Check random access and renderer reuse against saved reference frames."""
import argparse
import base64
import io
import json
import random
import threading
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

from PIL import Image, ImageChops
from playwright.sync_api import sync_playwright
from openkatana.contracts import validate
from openkatana.render import Handler,chrome_path,write_json


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--project',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--expected',default='comp',help='Saved render directory; comp selects the comparison directory')
    args=parser.parse_args();root=args.project.resolve();args.out.mkdir(parents=True,exist_ok=False)
    expected_dir=(root/args.expected).resolve()
    if expected_dir.parent!=root:raise ValueError('Expected render must be a direct child of the project')
    edit=validate(json.loads((root/'timeline.json').read_text(encoding='utf-8')),root)
    cases=json.loads((root/'cases.json').read_text(encoding='utf-8'))
    frames=[f for c in cases for f in [c['f0'],c['f0']+2,(c['f0']+c['f1'])//2,c['f1']-1]]
    random.Random(42).shuffle(frames);frames+=frames[:5]
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(Handler,project=root))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();checks=[]
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=chrome_path(),headless=True,args=['--disable-gpu'])
            try:
                page=browser.new_page();page.goto(f'http://127.0.0.1:{server.server_port}/app/render.html')
                page.evaluate('e=>OpenKatana.boot(e)',edit)
                for i,f in enumerate(frames):
                    if i==len(frames)//2:page.evaluate('e=>OpenKatana.boot(e)',edit)
                    try:
                        result=page.evaluate('f=>OpenKatana.render(f)',f)
                    except Exception as error:
                        write_json(args.out/'failure.json',{'frame':f,'iteration':i,'error':str(error),'completed':checks})
                        raise
                    data=base64.b64decode(result['png'])
                    with Image.open(io.BytesIO(data)) as actual,Image.open(expected_dir/f'frames/{f:05d}.png') as expected:
                        exact=ImageChops.difference(actual.convert('RGB'),expected.convert('RGB')).getbbox() is None
                    checks.append({'frame':f,'exact':exact})
                    if not exact:(args.out/f'mismatch-{i}-{f}.png').write_bytes(data)
            finally:browser.close()
    finally:server.shutdown();server.server_close();thread.join()
    result={'passed':all(c['exact'] for c in checks),'frames_checked':len(checks),'rebooted_mid_test':True,'reference_comparison':args.expected=='comp','expected_render':args.expected,'checks':checks}
    write_json(args.out/'result.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='checks'}))
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()
