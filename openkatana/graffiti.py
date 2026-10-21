"""Marker lettering contract. Original Switchback letterforms retain the animation and layout contract."""
from .contracts import ContractError,fields,number,color

REGIONS={'left','full','bl','right','leftwide','br','top','rightwide','tl2','bottom','tl','lower','center','tr','title'}
GLYPHS="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!?.,:-'/+*#& "


def graffiti_item(item,where,layer=False):
    fields(item,'type word text lines region cap mode wdur wkeys sc seed under nib halo halo_color ink echo line_dx line_rot line_scale leading rot slant bounce longbar'+(' at d phase order' if layer else ' f0 f1 on_specials'),where)
    if 'on_specials' in item and not isinstance(item['on_specials'],bool):raise ContractError('on_specials must be true or false')
    content=[k for k in ('word','text','lines') if k in item]
    if len(content)!=1:raise ContractError('Graffiti requires exactly one of word, text, lines')
    lines=item.get('lines')
    if lines is None:
        value=item.get('word',item.get('text'))
        if not isinstance(value,str):raise ContractError('Graffiti text must be a string')
        lines=value.split('\n')
    if not isinstance(lines,list) or not lines or len(lines)>12 or any(not isinstance(s,str) or not s.strip() for s in lines):raise ContractError('Graffiti requires 1..12 nonempty lines')
    text=''.join(lines).upper()
    if len(text)>512 or any(c not in GLYPHS for c in text):raise ContractError('Unsupported graffiti glyph or text length')
    if item.get('mode','static') not in ('static','write','slam','hold'):raise ContractError('Unsupported graffiti mode')
    region=item.get('region','center')
    if isinstance(region,str):
        if region not in REGIONS:raise ContractError('Unknown graffiti region')
    else:
        if not isinstance(region,list) or len(region)!=4:raise ContractError('Graffiti region needs four coordinates')
        for v in region:number(v,'region',0,1)
        if region[2]<=region[0] or region[3]<=region[1]:raise ContractError('Graffiti region must have positive area')
    for key in ('cap','wdur','nib','halo','leading','rot','slant','bounce','seed','at','d'):
        if key in item:
            low=.001 if key in ('cap','wdur','nib','d') else 0 if key in ('halo','leading','bounce','at') else None
            number(item[key],where+'.'+key,low,integer=key=='seed')
    for key in ('halo_color','ink','echo'):
        if key in item and not (key!='ink' and item[key] is False):color(item[key],key)
    for key in ('line_dx','line_rot','line_scale'):
        if key in item:
            if not isinstance(item[key],list) or len(item[key])!=len(lines):raise ContractError(f'{key} needs one number per line')
            for v in item[key]:number(v,key,.001 if key=='line_scale' else None)
    under=item.get('under',True)
    if not isinstance(under,bool) and (not isinstance(under,list) or len(under)!=len(lines) or any(not isinstance(v,bool) for v in under)):raise ContractError('under must be boolean or one boolean per line')
    if 'longbar' in item and not isinstance(item['longbar'],bool):raise ContractError('longbar must be boolean')
    if 'sc' in item:
        if not isinstance(item['sc'],list) or not item['sc']:raise ContractError('sc requires a nonempty array')
        for v in item['sc']:number(v,'sc',.001,100)
    if 'wkeys' in item:
        keys=item['wkeys'];count=sum(c!=' ' for c in text)
        if not isinstance(keys,list) or len(keys)!=count+1:raise ContractError('wkeys needs one absolute time per letter plus an end time')
        for v in keys:number(v,'wkeys',0)
        if any(a>=b for a,b in zip(keys,keys[1:])):raise ContractError('wkeys must strictly increase')
