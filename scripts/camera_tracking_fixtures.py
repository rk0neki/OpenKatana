"""Authored movement and face-track inputs for the optional reference comparison."""
import json
import shutil
from pathlib import Path
from PIL import Image,ImageDraw


def configure(edit,root,suite):
    if suite=='handheld':
        cases=[('default',{'cam':{'handheld':True}}),
               ('translation',{'cam':{'handheld':{'rot':0}}}),
               ('rotation',{'cam':{'handheld':{'amp':0}}}),
               ('parameters',{'cam':{'handheld':{'amp':12,'hz':2.5,'rot':.03,'seed':19}}}),
               ('alias',{'cam':{'handheld':{'v':3,'hz':.25,'seed':0}}}),
               ('zero-frequency',{'cam':{'handheld':{'hz':0}}}),
               ('zero-motion',{'cam':{'handheld':{'amp':0,'rot':0}}}),
               ('fx',{'fx':{'handheld':True}}),
               ('disabled',{'cam':{'handheld':False},'fx':{'handheld':True}}),
               ('freeze',{'speed':0,'cam':{'handheld':True}}),
               ('reverse',{'srcf':25,'speed':-1,'cam':{'handheld':True}}),
               ('cover',{'cam':{'handheld':{'amp':20,'rot':.1},'cover':True}}),
               ('stack',{'cam':{'z':1.3,'mir':1,'pan':{'dx':.02},'roll':{'rate':.03},'zoom':True,'handheld':True,'shake':True}}),
               ('repeat-default',{'cam':{'handheld':True}}),('clip',{'clip':'B'}),
               ('shot-override',{'clip':'B','cam':{'handheld':{'rot':0,'seed':42}}})]
        edit['clips']['B']={**edit['clips']['A'],'cam':{'handheld':{'amp':9,'hz':1.2,'seed':5}}}
    elif suite=='facelock':
        track=[{'f':i,'box':[60+i*2,30,160,140],'eyes':[[100+i*2,75+i*.3],[160+i*2,85-i*.3]]} for i in range(30)]
        for name,rows,size in [('faces',track,[320,192]),('gaps',[None if i in (0,1,8,9,10,28,29) else r for i,r in enumerate(track)],[320,192]),('scaled',[{**r,'box':[v*2 for v in r['box']],'eyes':[[v*2 for v in p] for p in r['eyes']]} for r in track],[640,384])]:
            (root/f'{name}.json').write_text(json.dumps(rows),encoding='utf-8')
            edit['clips'][name]={**edit['clips']['A'],'faces':f'{name}.json','faces_size':size}
        variants=[('default',{}),('no-cover',{'cover':False}),
                  ('target',{'ld':.3,'lx':.35,'ly':.6,'cover':False}),
                  ('zoom-kick',{'ld':.25,'z0':1.2,'z1':1.5,'kick':.12,'kick_rate':5}),
                  ('no-kick',{'kick':0,'z0':1,'z1':1}),
                  ('partial-roll',{'lockRot':.4,'cover':False}),('no-roll',{'lockRot':0}),
                  ('base-fields',{'z':1.4,'ax':.2,'ay':.7,'sx':.3,'sy':.8,'rot':.2}),
                  ('mirror',{'mir':1,'ld':.3}),('crop',{'crop':[.2,.8]}),
                  ('stack',{'ld':.3,'zoom':True,'push':True,'pan':{'dx':.1},'roll':{'v':.1},'handheld':True,'shake':True})]
        cases=[(name,{'clip':'faces','cam':{'type':'facelock',**cam}}) for name,cam in variants]
        cases += [('lock-alias',{'clip':'faces','cam':{'lock':True}}),
                  ('reverse',{'clip':'faces','srcf':25,'speed':-1,'cam':{'type':'facelock','ld':.3}}),
                  ('slow',{'clip':'faces','speed':.5,'cam':{'type':'facelock','ld':.3}}),
                  ('freeze',{'clip':'faces','srcf':12,'speed':0,'cam':{'type':'facelock','ld':.3}}),
                  ('scaled-track',{'clip':'scaled','cam':{'type':'facelock','ld':.3}}),
                  ('gap-track',{'clip':'gaps','cam':{'type':'facelock','ld':.3}}),
                  ('manual-box',{'clip':'faces','face':{'box':[40,50,120,130]},'cam':{'type':'facelock'}}),
                  ('hidden-face',{'clip':'faces','face':False,'cam':{'type':'facelock'}})]
    elif suite=='camera-tracking':
        edit['canvas'].update(w=640,h=360,fps=30000/1001)
        folder=root/'plates/portrait';folder.mkdir()
        masks=root/'masks/portrait';masks.mkdir(parents=True)
        track=[]
        for i in range(30):
            im=Image.new('RGB',(192,320),'#173848');d=ImageDraw.Draw(im)
            d.rectangle((0,0,191,319),outline='white',width=5)
            x=70+i;d.ellipse((x-35,55,x+35,155),fill='#dd782f')
            eyes=[[x-15,90+i*.3],[x+15,96-i*.2]]
            for ex,ey in eyes:d.ellipse((ex-3,ey-3,ex+3,ey+3),fill='white')
            im.save(folder/f'{i:05d}.png')
            mask=Image.new('RGBA',(192,320));ImageDraw.Draw(mask).ellipse((x-35,55,x+35,155),fill='white');mask.save(masks/f'{i:05d}.png')
            track.append({'f':i,'box':[x-35,55,70,100],'eyes':eyes})
        (root/'portrait-faces.json').write_text(json.dumps(track),encoding='utf-8')
        (root/'box-faces.json').write_text(json.dumps([{k:v for k,v in r.items() if k!='eyes'} for r in track]),encoding='utf-8')
        edit['clips']['P']={'frames_dir':'plates/portrait','pattern':'%05d.png','w':192,'h':320,'n':30,'fps':24,'faces':'portrait-faces.json','mask_dir':'masks/portrait'}
        edit['clips']['B']={**edit['clips']['P'],'faces':'box-faces.json','cam':{'handheld':{'amp':3,'seed':19}}}
        edit['cam']={'lock':True,'ld':.2,'handheld':{'amp':2,'seed':3}}
        cases=[('portrait-lock',{'clip':'P'}),('portrait-no-cover',{'clip':'P','cam':{'cover':False}}),
               ('portrait-offset',{'clip':'P','cam':{'lx':.3,'ly':.7,'lockRot':.6}}),
               ('portrait-mirror',{'clip':'P','cam':{'mir':1,'ld':.3}}),
               ('box-only-track',{'clip':'B'}),
               ('mask-text',{'clip':'P','fx':{'outline':{'r':4,'blur':1}}}),
               ('global-handheld',{'cam':{'lock':False}}),
               ('disabled-global',{'cam':{'lock':False,'handheld':False}}),
               ('portrait-drift',{'clip':'P','cam':{'lock':False,'handheld':True,'cover':True}}),
               ('source-ramp',{'clip':'P','speed':1,'speed1':-.5,'srcf':8}),
               ('zoom-out',{'clip':'P','cam':{'z0':1.5,'z1':.8,'kick':0}}),
               ('clip-drift',{'clip':'B','cam':{'lock':False,'cover':True}})]
        shutil.copyfile(Path('C:/Windows/Fonts/arial.ttf'),root/'fixture.ttf')
        edit['fonts']=[{'family':'Fixture','url':'fixture.ttf'}]
        edit['text']=[{'type':'font','family':'Fixture','text':'LOCK','size':35,'anchor':'face','f0':5*96,'f1':6*96}]
    else:raise ValueError(suite)
    edit['canvas']['frames']=len(cases)*96
    edit['shots']=[{'f0':i*96,'f1':(i+1)*96,'clip':'A','loop':'pingpong',**shot} for i,(_,shot) in enumerate(cases)]
    return [{'name':name,'f0':i*96,'f1':(i+1)*96} for i,(name,_) in enumerate(cases)]
