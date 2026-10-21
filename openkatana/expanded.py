"""Explicit contracts for independently authored effects and graphics."""
import re
from .contracts import ContractError, animated, fields, number, color

SPECS = {
    'mosaic':'from to', 'blur':'max frame', 'blurIn':'max frame', 'blurOut':'max color frame',
    'fin':'k blocks', 'fout':'k blocks', 'glitch':'amt seed blocks tile block',
    'magenta':'from to color color2', 'rgbsplit':'v decay',
    'wipe':'kind dir n stagger seed amp step feather cx cy color invert',
    'vignette':'v amt r0 r1 color', 'grain':'v amt op cell mono seed',
    'dust':'n seed color', 'leak':'color color2 amt x y r drift seed op',
    'contour':'r color alpha threshold',
    'big':'text family size fill stroke lw pos rot cut',
    'burst':'letters family seed rot dx dy r ls lr a0 a1 ry points fill stroke rays lw cut',
    'particles':'rate burst seed pos radius rect angle cone speed gravity drag wobble life size fadeIn fadeOut colors max shape',
    'polygon3d':'points fill stroke lw fov rx ry rz pivot near z spin pos',
    'morph':'from to fill stroke lw ease closed',
}
PHASES = {'contour':'over','big':'back','burst':'back','particles':'over','polygon3d':'over','morph':'over',
          'vignette':'final','grain':'final','dust':'final'}
ORDERS = {'glitch':10,'mosaic':11,'blur':12,'blurIn':13,'blurOut':14,'rgbsplit':15,
          'fin':30,'fout':31,'magenta':50,'leak':52,'vignette':5,'grain':10,'dust':20,
          'big':10,'burst':10,'contour':10,'particles':45,'polygon3d':45,'morph':45,'wipe':65}

def vector(v, n, where, low=None, high=None):
    if not isinstance(v,list) or len(v)!=n:raise ContractError(f'{where}: expected {n} coordinates')
    for x in v:number(x,where,low,high)

def points(v,n,where):
    if not isinstance(v,list) or not 2<=len(v)<=2048:raise ContractError(f'{where}: expected 2..2048 points')
    for p in v:vector(p,n,where)

def effect(name,p,where):
    fields(p,SPECS[name]+' at d side',where)
    for k,v in p.items():
        loc=f'{where}.{k}'
        if k in ('color','color2','fill','stroke','rays'): color(v,loc)
        elif k=='colors':
            if not isinstance(v,list) or not 1<=len(v)<=32:raise ContractError('colors requires 1..32 colors')
            for c in v:color(c,loc)
        elif k in ('blocks','frame','invert','mono','cut','closed'):
            if not isinstance(v,bool):raise ContractError(f'{loc}: expected boolean')
        elif k in ('text','letters','family'):
            if not isinstance(v,str) or not v or len(v)>512:raise ContractError(f'{loc}: expected nonempty text')
        elif k=='op':
            from .effects import BLENDS
            if v not in BLENDS:raise ContractError('Unsupported blend')
        elif k in ('kind','dir','side','shape','ease'):
            allowed={'kind':('iris','stripes','torn'),'dir':('left','right','up','down'),
                     'side':('in','out'),'shape':('dot','square','spark','confetti'),
                     'ease':('lin','in2','in3','out2','out3','inout')}
            if v not in allowed[k]:raise ContractError(f'{loc}: unsupported value')
        elif k in ('pos','pivot','rect'):vector(v,{'pos':2,'pivot':3,'rect':4}[k],loc)
        elif name=='morph' and k in ('from','to'):points(v,2,loc)
        elif name=='polygon3d' and k=='points':points(v,3,loc)
        else:
            lo=hi=None; integer=k in ('n','seed','cell','max','burst') and not (name.startswith('blur') and k=='max')
            if k in ('d','life','size','cell','tile','block','step','near','z','ls','lr','ry'):lo=.001
            if k in ('at','r','r0','r1','radius','lw','feather','rate','burst','max','n','fadeIn','fadeOut','drag','decay'):lo=0
            if k in ('amt','alpha','stagger','threshold'):lo,hi=0,1
            if name in ('mosaic','magenta') and k in ('from','to'):lo,hi=1,4096
            if name in ('grain','vignette') and k=='v':lo,hi=0,1
            if k=='fov':lo,hi=1,175
            if k=='n':lo,hi=(2 if name=='wipe' else 0),256;integer=True
            if k=='points' and name=='burst':lo,hi=3,256;integer=True
            if k in ('max','burst') and name=='particles':hi=10000
            if k=='rate':lo,hi=0,2000
            if name=='grain' and k=='cell':lo,hi=1,128
            if k in ('fadeIn','fadeOut'):hi=1
            number(v,loc,lo,hi,integer=integer)
    if name=='morph':
        if not p.get('from') or len(p['from'])!=len(p.get('to',[])):raise ContractError('Morph needs equal-length from/to point arrays')
    if name=='polygon3d' and len(p.get('points',[]))<3:raise ContractError('polygon3d requires at least three points')
    if name=='big' and not p.get('text'):raise ContractError('big requires text')
    if name=='vignette' and p.get('r1',.95)<=p.get('r0',.45):raise ContractError('vignette r1 must exceed r0')

def look(value,where='look'):
    if value in (None,'none','clean'):return
    if not isinstance(value,dict):raise ContractError('Look requires an explicit object')
    kind=value.get('type')
    if kind=='studio':
        from .studio_looks import validate_studio
        return validate_studio(value,where)
    allowed={'grade':'filter layers','filter':'filter layers','posterize':'levels'}
    fields(value,'type '+allowed.get(kind,'black white hard grit ink paper invert seed grain_every key'),where)
    if 'key' in value:
        k=value['key']
        if k is not True:
            fields(k,'channel lo width vmin vw hue soft sat val dark light amt stoch mix lift gain',where+'.key')
            if k.get('channel','g') not in ('r','g','b'):raise ContractError(f'{where}.key.channel: r, g or b')
            if 'hue' in k:
                if not isinstance(k['hue'],list) or len(k['hue'])!=2:raise ContractError(f'{where}.key.hue: [from, to] degrees')
                for h in k['hue']:number(h,where+'.key.hue',0,360)
            for name,lo,hi in (('lo',-1,1),('width',0,1),('vmin',0,1),('vw',0,1),('soft',0,180),('sat',0,1),('val',0,1),('amt',0,1),('stoch',0,1),('mix',0,1),('lift',-1,1),('gain',0,4)):
                if name in k:number(k[name],f'{where}.key.{name}',lo,hi)
            for name in ('dark','light'):
                if name in k:color(k[name],f'{where}.key.{name}')
    if value.get('type') not in ('grade','filter','levels','threshold','duotone','xerox','neg','posterize'):raise ContractError('Unsupported look')
    for k in ('black','white','hard','grit'):
        if k in value:animated(value[k],where+'.'+k,0,1)
    ends=lambda k,d:[value[k]['from'],value[k]['to']] if isinstance(value.get(k),dict) else [value.get(k,d)]
    if min(ends('white',1 if kind=='threshold' else .8))<=max(ends('black',0 if kind=='threshold' else .13)):raise ContractError('look.white must exceed look.black')
    if 'grain_every' in value:number(value['grain_every'],where+'.grain_every',1,240,integer=True)
    if 'levels' in value:number(value['levels'],'levels',2,256,integer=True)
    if 'seed' in value:number(value['seed'],'seed',integer=True)
    if 'invert' in value and not isinstance(value['invert'],bool):raise ContractError('look.invert must be boolean')
    for k in ('ink','paper'):
        if k in value:color(value[k],k)
    if 'filter' in value:
        if not isinstance(value['filter'],str) or not re.fullmatch(r'(?:none|(?:(?:brightness|contrast|saturate|grayscale|sepia|invert|opacity|blur|hue-rotate)\([0-9.]+(?:%|px|deg)?\)\s*)+)',value['filter']):raise ContractError('Use numeric CSS color filters; external filters are not supported')
    if not isinstance(value.get('layers',[]),list):raise ContractError('look.layers must be an array')
    for layer in value.get('layers',[]):
        fields(layer,'op color alpha','look layer');color(layer.get('color'),'look layer.color',alpha=True)
        number(layer.get('alpha',1),'look layer.alpha',0,1)
        from .effects import BLENDS
        if layer.get('op','soft-light') not in BLENDS:raise ContractError('Unsupported look blend')
