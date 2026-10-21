"""Original, reproducible silent 3D/morph/physics demonstration. No service or model calls."""
import argparse
from pathlib import Path
import shutil

import openkatana
from openkatana.scene3d import starter, render_scene
from openkatana.render import write_json, render
from openkatana.bundled_fonts import copy_license


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    p.add_argument('--width',type=int,default=640);p.add_argument('--height',type=int,default=360)
    p.add_argument('--fps',type=int,default=24);p.add_argument('--frames',type=int,default=60)
    a=p.parse_args();root=a.out.resolve();root.mkdir(parents=True,exist_ok=False)
    fonts=Path(openkatana.__file__).parent/'fonts';font=fonts/'Inter[opsz,wght].ttf'
    shutil.copyfile(font,root/'title.ttf');copy_license(font,root/'title.ttf')
    timeline={'canvas':{'w':a.width,'h':a.height,'fps':a.fps,'frames':3*a.frames},'clips':{},'shots':[],
              'fonts':[{'family':'Title','url':'title.ttf'}],'text':[]}
    for i,(kind,label) in enumerate([('product','LIGHT / MATERIAL / MOTION'),('morph','TOPOLOGY IN MOTION'),('physics','CONTACT / WEIGHT / GRAVITY')]):
        scene=starter(kind,width=a.width,height=a.height,fps=a.fps,frames=a.frames)
        if kind=='product':scene['motion_blur']={'samples':4,'shutter':.5}
        path=root/f'{kind}.json';write_json(path,scene)
        result=render_scene(path,root/kind,video=False)
        clip=result['clip'];clip['frames_dir']=Path(clip['frames_dir']).relative_to(root).as_posix();timeline['clips'][kind]=clip
        first,last=i*a.frames,(i+1)*a.frames
        timeline['shots'].append({'f0':first,'f1':last,'clip':kind})
        for text,size,y in [(label,a.width*.035,.87),('OPENKATANA  /  ORIGINAL LOCAL SCENE',a.width*.018,.94)]:
            timeline['text'].append({'type':'font','text':text,'family':'Title','size':size,'fill':'#ffffff','f0':first,'f1':last,'pos':[.5,y]})
    write_json(root/'timeline.json',timeline);result=render(root/'timeline.json',root/'final')
    write_json(root/'showcase.json',{'credits_used':0,'assets':'Original geometry; bundled OFL Inter. No private footage or music.','render':result})
    print(root/'final/video.mp4')


if __name__=='__main__':main()
