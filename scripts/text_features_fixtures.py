"""Newly authored text and face-coordinate fixtures; no reference assets."""
import json
import shutil
from pathlib import Path


def configure(edit, root, suite):
    shutil.copyfile(Path('C:/Windows/Fonts/arial.ttf'),root/'fixture.ttf')
    edit['fonts']=[{'family':'Fixture','url':'fixture.ttf'}]
    parts=[['HE','bold'],['LL','thin'],['O','heavy']]
    if suite=='mixed-text':
        variants=[('parts',{'parts':parts}),('parts-type',{'parts':parts,'anim':'type'}),
                  ('parts-no-text',{'parts':parts,'text':None}),
                  ('kind-thin',{'kind':'thin'}),('kind-heavy',{'kind':'heavy'}),
                  ('explicit-weight',{'parts':parts,'weight':500,'style':'normal'}),
                  ('no-stroke',{'parts':parts,'stroke':None}),('left',{'parts':parts,'align':'left'}),
                  ('base',{'parts':parts,'anim':'type','base':2,'dt':.1}),
                  ('animated',{'parts':parts,'anim':'grow','anim_d':.4,'fade_out':.2,'boil':2,'rot':.2}),
                  ('spaces',{'parts':[['A ','thin'],['B C','heavy']]}),
                  ('empty-part',{'parts':[['','thin'],['YES','bold']],'shadow':False}),
                  ('custom-line-width',{'parts':parts,'lw':10}),
                  ('parts-pop',{'parts':parts,'anim':'pop'}),
                  ('parts-fade',{'parts':parts,'anim':'fade','alpha':.5}),
                  ('parts-slam',{'parts':parts,'anim':'slam'}),
                  ('kind-type',{'kind':'thin','anim':'type'}),
                  ('unicode',{'parts':[['Hi ','thin'],['é!','bold']]})]
        cases=[(name,{},params) for name,params in variants]
    elif suite=='face-text':
        face={'box':[80,30,240,170]}
        track=[{'f':i,'box':[60+i*2,30,160,140],'eyes':[[100+i*2,75+i*.3],[160+i*2,85-i*.3]],'score':1} for i in range(30)]
        (root/'faces.json').write_text(json.dumps(track))
        edit['clips']['B']={**edit['clips']['A'],'faces':'faces.json','faces_size':[320,192]}
        scaled=[{**r,'box':[v*2 for v in r['box']],'eyes':[[v*2 for v in point] for point in r['eyes']]} for r in track]
        (root/'scaled-faces.json').write_text(json.dumps(scaled))
        edit['clips']['C']={**edit['clips']['A'],'faces':'scaled-faces.json','faces_size':[640,384]}
        gaps=[r if i not in (0,1,8,9,10,28,29) else None for i,r in enumerate(track)]
        (root/'gap-faces.json').write_text(json.dumps(gaps))
        edit['clips']['D']={**edit['clips']['A'],'faces':'gap-faces.json','faces_size':[320,192]}
        cases=[('box-default',{'face':face},{}),('box-offset',{'face':face},{'o':[.4,-.5]}),
               ('box-sized',{'face':face},{'size_eu':.5,'min':10,'max':100}),
               ('box-small',{'face':{'box':[110,50,150,100]}},{}),
               ('box-rotate',{'face':face,'cam':{'rot':.3,'z':1.2}},{}),
               ('box-mirror',{'face':face,'cam':{'mir':1,'rot':-.2}},{}),
               ('box-override-rotation',{'face':face},{'rot':.4}),
               ('track',{'clip':'B'},{}),('track-reverse',{'clip':'B','srcf':25,'speed':-1},{}),
               ('track-slow',{'clip':'B','speed':.5},{}),
               ('track-transform',{'clip':'B','cam':{'mir':1,'rot':.3,'z':1.1}},{'o':[-.4,1.2],'size_eu':.8,'min':10,'max':80}),
               ('disabled-face',{'clip':'B','face':False},{}),('missing-face',{},{}),
               ('face-parts',{'clip':'B'},{'parts':parts,'anim':'type','boil':2}),
               ('default-size',{'face':face},{'size':None}),
               ('size-eu-default-clamp',{'face':face},{'size_eu':.05}),
               ('size-eu-large-clamp',{'face':face},{'size_eu':10}),
               ('face-min',{'face':face},{'size_eu':.1,'min':20}),
               ('face-max',{'face':face},{'size_eu':10,'max':80}),
               ('scaled-track',{'clip':'C'},{'size_eu':.7}),
               ('gap-track',{'clip':'D'},{}),
               ('override-track',{'clip':'B','face':face},{}),
               ('layer-anchor',{'clip':'B','layers':[{'type':'text','anchor':'face','family':'Fixture','parts':parts,'size':34,'at':.15,'d':.4}]},{'text':''})]
    else:raise ValueError(suite)
    edit['shots']=[];edit['text']=[];edit['canvas']['frames']=len(cases)*48
    for i,(name,shot,params) in enumerate(cases):
        edit['shots'].append({'f0':i*48,'f1':(i+1)*48,'clip':'A',**shot})
        item={'type':'font','family':'Fixture','text':'HELLO','size':42,'pos':[.5,.5],'f0':i*48,'f1':(i+1)*48,**params}
        if suite=='face-text':item['anchor']='face'
        if item.get('text') is None:item.pop('text',None)
        if item.get('size') is None:item.pop('size',None)
        edit['text'].append(item)
    return [{'name':name,'f0':i*48,'f1':(i+1)*48} for i,(name,_,_) in enumerate(cases)]
