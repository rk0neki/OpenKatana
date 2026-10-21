"""Actual renders for the independent release additions. No hosted calls or model downloads."""
import argparse
import copy
import io
import json
import os
from pathlib import Path
import sys

if os.environ.get('OPENKATANA_TEST_PACKAGE'):sys.path.insert(0,os.environ['OPENKATANA_TEST_PACKAGE'])

from PIL import Image
import numpy as np
from openkatana.scene3d import render_scene, starter
from openkatana.render import write_json, playwright, chrome_path
from openkatana.text_shape import export_text


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    root=a.out.resolve();root.mkdir(parents=True,exist_ok=False);checks={};metrics={}
    import openkatana
    font=Path(openkatana.__file__).parent/'fonts/NotoSansArabic[wdth,wght].ttf'
    glyphs=export_text(font,'سلام',root/'glyphs',size=96,radius=180,language='ar')
    with playwright()() as pw:
        browser=pw.chromium.launch(executable_path=chrome_path(),headless=True)
        page=browser.new_page(viewport={'width':640,'height':240})
        page.set_content('<body style="margin:0;background:white;display:grid;place-items:center;height:100vh">'+glyphs['svg']+'</body>')
        page.screenshot(path=str(root/'glyphs.png'));browser.close()
    a=np.asarray(Image.open(root/'glyphs.png').convert('RGB'))
    checks['svg_outline_renders']=int((a.min(axis=2)<100).sum())>500
    # Fast-moving unlit-like white box: shutter samples must broaden its spatial footprint.
    s={'schema':1,'canvas':{'width':160,'height':96,'fps':12,'frames':5},'environment':'none',
       'background':'#000000','camera':{'type':'orthographic','position':[0,0,5],'target':[0,0,0],'span':3},
       'lights':[{'id':'lamp','type':'ambient','intensity':5}],
       'objects':[{'id':'box','geometry':{'type':'box','size':[.15,1,.15]},'material':{'color':'#ffffff'},'cast_shadow':False}],
       'tracks':[{'target':'box','property':'position','keys':[[0,[-2,0,0]],[4/12,[2,0,0]]]}]}
    write_json(root/'sharp.json',s);sharp=render_scene(root/'sharp.json',root/'sharp',[0,2,4],False)
    s['motion_blur']={'samples':8,'shutter':1};write_json(root/'blur.json',s)
    blur=render_scene(root/'blur.json',root/'blur',[0,2,4],False)
    def footprint(path):
        im=np.asarray(Image.open(path).convert('RGB'));cols=np.where(im.max(axis=(0,2))>30)[0]
        return int(cols[-1]-cols[0]+1) if len(cols) else 0
    widths=[footprint(root/k/'frames/00002.png') for k in ('sharp','blur')]
    metrics['motion_width_pixels']={'sharp':widths[0],'blurred':widths[1]}
    checks['temporal_blur_broadens_motion']=widths[1]>widths[0]+8
    checks['blur_deterministic']=blur['determinism']['passed']
    states=json.loads((root/'blur/states.json').read_text())
    checks['clamped_exposure_edges']=min(states[0]['shutter_samples'])==0 and max(states[-1]['shutter_samples'])==4
    stationary=copy.deepcopy(s);stationary['tracks']=[];write_json(root/'stationary.json',stationary)
    render_scene(root/'stationary.json',root/'stationary',[2],False)
    stationary.pop('motion_blur');write_json(root/'stationary-sharp.json',stationary)
    render_scene(root/'stationary-sharp.json',root/'stationary-sharp',[2],False)
    checks['static_exposure_preserves_pixels']=np.array_equal(np.asarray(Image.open(root/'stationary/frames/00002.png')),np.asarray(Image.open(root/'stationary-sharp/frames/00002.png')))
    physics=starter('physics',width=160,height=96,fps=6,frames=6);physics['motion_blur']={'samples':4,'shutter':1}
    write_json(root/'physics.json',physics);pr=render_scene(root/'physics.json',root/'physics',[0,2,5],False)
    ps=json.loads((root/'physics/states.json').read_text())
    checks['physics_blur_seek_stable']=pr['determinism']['passed'] and ps[-1]['objects']['hero']['position'][1]<ps[0]['objects']['hero']['position'][1]
    report={'passed':all(checks.values()),'checks':checks,'metrics':metrics,'credits_used':0,'package':str(Path(openkatana.__file__).resolve())}
    write_json(root/'validation.json',report);print(json.dumps(report,indent=2));return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
