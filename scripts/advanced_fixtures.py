"""Synthetic inputs for the motion, matte and typography comparison suites."""
import shutil
from pathlib import Path
from PIL import Image, ImageDraw


def configure(edit, root, suite):
    cases = []
    if suite == 'coverage':
        for name, cam in [
            ('identity', {'cover':True}), ('underscan', {'z':.6,'cover':True}),
            ('rotation', {'rot':.3,'cover':True}),
            ('rotation-negative', {'rot':-.7,'z':.8,'cover':True}),
            ('anchor-edge', {'ax':.1,'ay':.9,'cover':True}),
            ('screen-offset', {'sx':.2,'sy':.8,'cover':True}),
            ('pan', {'pan':{'dx':.3,'dy':-.2},'cover':True}),
            ('overscan-pan', {'z':1.6,'pan':{'dx':.3,'dy':-.2},'cover':True}),
            ('crop-point', {'crop':[.1,.8],'z':1.5}), ('crop-y', {'crop':.8,'z':1.5}),
            ('crop-screen', {'crop':[.2,.8],'sx':.3,'sy':.7,'rot':.2}),
            ('mirror', {'mir':1,'rot':.3,'sx':.2,'sy':.6,'cover':True}),
            ('animated', {'zoom':{'z0':.7,'z1':1.6},'roll':{'rate':.6},'cover':True}),
            ('combined-shake', {'crop':[.8,.1],'mir':1,'rot':-.3,'shake':{'d':.8,'amp':[40,30]}}),
            ('disabled', {'cover':False,'rot':.3,'z':.7}),
        ]: cases.append((name, {'cam':cam}))
        for key,size in [('B',(96,192)),('C',(480,160))]:
            folder=root/f'plates/{key}';folder.mkdir(parents=True)
            for f in range(30):
                with Image.open(root/f'plates/A/{f:05d}.png') as im:im.resize(size).save(folder/f'{f:05d}.png')
            edit['clips'][key]={**edit['clips']['A'],'frames_dir':f'plates/{key}','w':size[0],'h':size[1]}
            for fit in ('cover','contain','width','height'):
                cases.append((key+'-'+fit,{'clip':key,'cam':{'fit':fit,'cover':True,'rot':.22,'crop':[.2,.7]}}))
    elif suite == 'shake':
        cases = [
            ('default', {'cam':{'shake':True}}),
            ('repeat-shot', {'cam':{'shake':True}}),
            ('long', {'cam':{'shake':{'d':.8}}}),
            ('every-one', {'cam':{'shake':{'d':.8,'every':1}}}),
            ('every-three', {'cam':{'shake':{'d':.8,'every':3,'amp':[10,25]}}}),
            ('offset', {'cam':{'shake':{'at':.2,'d':.4}}}),
            ('hits', {'cam':{'shake':{'hits':[.1,.2,.5],'d':.3}}}),
            ('freeze', {'srcf':8,'speed':0,'cam':{'shake':True}}),
            ('reverse', {'srcf':25,'speed':-1,'cam':{'shake':True}}),
            ('covered', {'cam':{'shake':{'d':.6},'cover':True}}),
            ('combined', {'cam':{'shake':{'d':.6},'z':1.2,'mir':1,'rot':.15,'pan':{'dx':.05}}}),
            ('fx-shake', {'fx':{'shake':{'d':.4,'every':4,'amp':[5,9]}}}),
            ('zero-amplitude', {'cam':{'shake':{'amp':[0,0]}}}),
            ('ramp-from-freeze', {'speed':0,'speed1':1,'cam':{'shake':True}}),
            ('disabled-in-camera', {'cam':{'shake':False},'fx':{'shake':True}}),
        ]
    elif suite == 'typography':
        variants = [
            ('defaults',{}), ('plain',{'stroke':None,'shadow':False,'style':'normal','weight':400}),
            ('stroke',{'stroke':'#238fae','lw':3,'shadow':False}),
            ('shadow-custom',{'shadow':{'color':'#cd275e','blur':8,'dx':4,'dy':-3}}),
            ('shadow-dark',{'shadow':'dark'}), ('rotation',{'rot':.22}),
            ('align-left',{'align':'left','pos':[.12,.55]}), ('align-right',{'align':'right','pos':[.85,.45]}),
            ('opacity',{'alpha':.45}), ('fade-out',{'fade_out':.3}),
            ('pop',{'anim':'pop'}), ('pop-custom',{'anim':'pop','pop':.4}),
            ('slam',{'anim':'slam'}), ('slam-custom',{'anim':'slam','sc':[1.5,.8,1.2,1]}),
            ('fade',{'anim':'fade'}), ('grow',{'anim':'grow','anim_d':.4}),
            ('typewriter',{'anim':'type'}), ('typewriter-base',{'anim':'type','dt':.08,'base':2}),
            ('fade-combined',{'anim':'fade','anim_d':.3,'fade_out':.35,'alpha':.6}),
            ('boil',{'boil':3,'seed':11}),
            ('no-stroke-glow',{'stroke':None}),
            ('type-no-stroke',{'anim':'type','stroke':None,'shadow':False}),
            ('type-align-left',{'anim':'type','align':'left','pos':[.15,.6],'stroke':None}),
            ('type-align-right',{'anim':'type','align':'right','pos':[.85,.4]}),
            ('combined',{'rot':-.15,'anim':'grow','anim_d':.3,'boil':2,'seed':4,'fade_out':.25,'alpha':.7}),
            ('caption-alias',{'type':'caption','style':'normal','weight':700}),
            ('word-alias',{'type':'word','style':'normal','weight':300}),
            ('hidden-on-shot',{}),
        ]
        cases=[(name, {'_text':params}) for name,params in variants]
    elif suite == 'masks':
        cases = [
            ('cutout', {'fx':{'cutout':True}}),
            ('back-color', {'layers':[{'type':'white','phase':'back','d':.8,'color':'#8a35d4'}],'fx':{'cutout':True}}),
            ('transformed', {'cam':{'z':1.3,'rot':.2,'mir':1},'layers':[{'type':'white','phase':'back','d':.8,'color':'#2345aa'}],'fx':{'cutout':True}}),
            ('slow-mask', {'speed':.5,'layers':[{'type':'white','phase':'back','d':.8}],'fx':{'cutout':True}}),
            ('reverse-mask', {'srcf':25,'speed':-1,'layers':[{'type':'white','phase':'back','d':.8}],'fx':{'cutout':True}}),
            ('outline-default', {'fx':{'outline':True}}),
            ('outline-custom', {'fx':{'outline':{'r':6,'color':'#f64b85','blur':2,'alpha':.7,'dx':-5,'dy':7}}}),
            ('outline-no-cutout', {'fx':{'outline':{'r':8},'cutout':False}}),
            ('text-behind', {'layers':[{'type':'text','phase':'back','text':'HELLO','family':'Fixture','size':55,'pos':[.5,.5],'stroke':None,'shadow':False}],'fx':{'cutout':True}}),
            ('outline-transform',{'cam':{'z':1.3,'rot':-.27,'mir':1,'sx':.4},'fx':{'outline':{'r':9,'blur':1,'dx':-7,'dy':3}}}),
            ('outline-shake',{'cam':{'z':1.2,'shake':{'d':.8},'cover':True},'fx':{'outline':True}}),
            ('ordered-subject',{'layers':[{'type':'white','phase':'back','d':.8},{'type':'cutout'},{'type':'outline','r':2,'blur':0,'dx':0,'dy':0}]}),
            ('text-layer-window',{'layers':[{'type':'text','at':.2,'d':.3,'text':'MASK','family':'Fixture','size':38,'pos':[.5,.5],'anim':'fade','fade_out':.1}]}),
            ('text-layer-type',{'layers':[{'type':'text','at':.15,'d':.5,'text':'HELLO','family':'Fixture','size':38,'pos':[.5,.5],'anim':'type','boil':2}]}),
        ]
        folder=root/'masks/A';folder.mkdir(parents=True)
        for f in range(30):
            im=Image.new('RGBA',(320,192),(255,255,255,0));draw=ImageDraw.Draw(im)
            draw.ellipse((50+f*3,25,150+f*3,160), fill=(255,255,255,255))
            draw.rectangle((140,70,210,120),fill=(255,255,255,128))
            im.save(folder/f'{f:05d}.png')
        edit['clips']['A']['mask_dir']='masks/A'
    else:
        raise ValueError(suite)
    if suite in ('typography','masks'):
        # Test input only. The font is never shipped with OpenKatana.
        shutil.copyfile(Path('C:/Windows/Fonts/arial.ttf'),root/'fixture.ttf')
        edit['fonts']=[{'family':'Fixture','url':'fixture.ttf'}]
    edit['canvas']['frames']=len(cases)*48
    edit['shots']=[]
    for i,(name, params) in enumerate(cases):
        params=dict(params);text=params.pop('_text',None)
        edit['shots'].append({'f0':i*48,'f1':(i+1)*48,'clip':'A',**params})
        if name=='hidden-on-shot':edit['shots'][-1]['fx']={'text':False}
        if text is not None:
            edit.setdefault('text',[]).append({'type':'font','family':'Fixture','text':'HELLO','size':42,
                'pos':[.5,.5],'f0':i*48,'f1':(i+1)*48,**text})
    return [{'name':name,'f0':i*48,'f1':(i+1)*48} for i,(name,_) in enumerate(cases)]
