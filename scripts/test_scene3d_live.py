"""Original synthetic fixtures: real offline render, animated skin/morph, physics and timeline reuse."""
import argparse
import base64
import json
import math
import os
from pathlib import Path
import struct
import sys

# The package override verifies a built wheel without importing the editable checkout.
if os.environ.get('OPENKATANA_TEST_PACKAGE'):
    sys.path.insert(0,os.environ['OPENKATANA_TEST_PACKAGE'])

from openkatana.scene3d import starter,render_scene,validate,inspect_model
from openkatana.render import write_json,render,digest


def rigged_fixture(path):
    """Original four-vertex banner with a two-joint rig, a shape key and one clip."""
    chunks=bytearray();views=[];accessors=[]
    def buffer(values,fmt,type_,count,component=5126,**extra):
        while len(chunks)%4:chunks.append(0)
        data=struct.pack('<'+fmt*len(values),*values);offset=len(chunks);chunks.extend(data)
        views.append({'buffer':0,'byteOffset':offset,'byteLength':len(data)})
        accessors.append({'bufferView':len(views)-1,'componentType':component,'count':count,'type':type_,**extra});return len(accessors)-1
    pos=buffer([-.4,0,0,.4,0,0,-.4,2,0,.4,2,0],'f','VEC3',4,min=[-.4,0,0],max=[.4,2,0])
    normals=buffer([0,0,1]*4,'f','VEC3',4)
    joints=buffer([0,0,0,0]*2+[1,0,0,0]*2,'H','VEC4',4,5123)
    weights=buffer([1,0,0,0]*4,'f','VEC4',4)
    indices=buffer([0,1,2,2,1,3],'H','SCALAR',6,5123)
    identity=[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1];inverse=identity.copy();inverse[13]=-1
    binds=buffer(identity+inverse,'f','MAT4',2)
    delta=buffer([0,0,0,0,0,0,-.4,0,0,.4,0,0],'f','VEC3',4)
    times=buffer([0,1],'f','SCALAR',2,min=[0],max=[1])
    rotation=buffer([0,0,0,1,0,0,math.sin(.5),math.cos(.5)],'f','VEC4',2)
    morph=buffer([0,1],'f','SCALAR',2)
    gltf={'asset':{'version':'2.0','generator':'OpenKatana original diagnostic fixture'},
          'buffers':[{'uri':'data:application/octet-stream;base64,'+base64.b64encode(chunks).decode(),'byteLength':len(chunks)}],
          'bufferViews':views,'accessors':accessors,'scene':0,'scenes':[{'nodes':[0,1]}],
          'nodes':[{'name':'Banner','mesh':0,'skin':0},{'name':'Root','children':[2]},{'name':'Hinge','translation':[0,1,0]}],
          'skins':[{'joints':[1,2],'skeleton':1,'inverseBindMatrices':binds}],
          'materials':[{'pbrMetallicRoughness':{'baseColorFactor':[.1,.6,.9,1],'roughnessFactor':.3},'doubleSided':True}],
          'meshes':[{'weights':[0],'extras':{'targetNames':['Spread']},'primitives':[{'attributes':{'POSITION':pos,'NORMAL':normals,'JOINTS_0':joints,'WEIGHTS_0':weights},'indices':indices,'material':0,'targets':[{'POSITION':delta}]}]}],
          'animations':[{'name':'Bend','samplers':[{'input':times,'output':rotation,'interpolation':'LINEAR'},{'input':times,'output':morph,'interpolation':'LINEAR'}],
                         'channels':[{'sampler':0,'target':{'node':2,'path':'rotation'}},{'sampler':1,'target':{'node':0,'path':'weights'}}]}]}
    write_json(path,gltf)


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();root=a.out.resolve();root.mkdir(parents=True,exist_ok=False)
    from PIL import Image,ImageChops
    import openkatana
    checks={};receipts={}
    for kind in ('product','morph','physics'):
        s=starter(kind,width=320,height=180,fps=12,frames=25)
        if kind=='product':s['post']={'bloom':.18,'focus':6,'aperture':.0001,'max_blur':.005}
        path=root/f'{kind}.json';write_json(path,s)
        receipts[kind]=render_scene(path,root/kind)
        checks[kind+'_reverse_seek']=receipts[kind]['determinism']['passed']
        checks[kind+'_frames']=receipts[kind]['frames_rendered']==25
        im0=Image.open(root/kind/'frames/00000.png').convert('RGB');im1=Image.open(root/kind/'frames/00024.png').convert('RGB')
        checks[kind+'_visible_change']=ImageChops.difference(im0,im1).getbbox() is not None
    states=json.loads((root/'morph/states.json').read_text())
    first,last=states[0]['objects']['hero']['topology'],states[-1]['objects']['hero']['topology']
    checks['sphere_euler_2']=first['euler']==2 and first['nonmanifold_edges']==0
    checks['torus_euler_0']=last['euler']==0 and last['nonmanifold_edges']==0
    checks['all_sampled_morph_frames_manifold']=all(x['objects']['hero']['topology']['nonmanifold_edges']==0 for x in states)
    physics=json.loads((root/'physics/states.json').read_text())
    ys=[row['objects']['hero']['position'][1] for row in physics]
    checks['gravity_moves_body']=ys[-1]<ys[0]-1
    checks['floor_prevents_fallthrough']=min(ys)>.4
    model=root/'banner.gltf';rigged_fixture(model);info=inspect_model(model)
    s=starter(width=320,height=180,frames=13,fps=12);s['tracks']=[]
    s['objects'][1]={'id':'hero','type':'model','model':model.name,'animation':{'clip':'Bend','loop':False}}
    write_json(root/'model.json',s);receipts['model']=render_scene(root/'model.json',root/'model')
    st=json.loads((root/'model/states.json').read_text())
    checks['skin_and_clip_loaded']=info['skins']==1 and receipts['model']['runtime']['imported'][0]['skins']==1
    checks['morph_clip_moves_weights']=st[0]['objects']['hero']['morphs'][0][0]==0 and st[-1]['objects']['hero']['morphs'][0][0]==1
    checks['bone_moves_vertices']=st[0]['objects']['hero']['deformed']!=st[-1]['objects']['hero']['deformed']
    checks['model_reverse_seek']=receipts['model']['determinism']['passed']
    # Reuse a rendered plate directly in the normal OpenKatana editor, retaining frame count.
    clip=receipts['product']['clip'];clip['frames_dir']=Path(clip['frames_dir']).relative_to(root).as_posix()
    timeline={'canvas':{'w':320,'h':180,'fps':12,'frames':25},'clips':{'hero':clip},'shots':[{'f0':0,'f1':25,'clip':'hero'}]}
    write_json(root/'timeline.json',timeline);result=render(root/'timeline.json',root/'timeline-output')
    checks['timeline_import_render']=(root/'timeline-output/video.mp4').is_file()
    report={'passed':all(checks.values()),'checks':checks,'package':str(Path(openkatana.__file__).resolve()),
            'source':'Original synthetic fixtures, local fixtures only','credits_used':0,
            'sphere_topology':first,'torus_topology':last,'outputs':{k:v.get('video') for k,v in receipts.items()}}
    write_json(root/'validation.json',report);print(json.dumps(report,indent=2));return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
