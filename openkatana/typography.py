"""Strict supplied-font typography contract."""
from .contracts import ContractError, fields, number, color


def text_item(item, fonts, where, layer=False):
    if isinstance(item,dict) and item.get('type')=='graffiti':
        from .graffiti import graffiti_item
        return graffiti_item(item,where,layer)
    allowed='type text pos family size fill alpha align weight style stroke lw shadow rot anim anim_d pop sc dt base fade_out boil seed parts kind anchor o size_eu min max render_style tracking scale_x scale_y flicker opacity_keys letter_opacity_keys karaoke on_specials'
    fields(item,allowed+(' at d phase order' if layer else ' f0 f1'),where)
    if item.get('type') not in (('text',) if layer else ('font','word','caption')) or item.get('family') not in fonts:
        raise ContractError('Text requires an explicitly supplied font and a supported text type')
    if not isinstance(item.get('text','' if 'parts' in item else None),str): raise ContractError('Text must be a string')
    if item.get('kind','bold') not in ('bold','thin','heavy'): raise ContractError('Unsupported text kind')
    if 'parts' in item:
        if not isinstance(item['parts'],list) or not item['parts']: raise ContractError('parts requires a nonempty array')
        for part in item['parts']:
            if not isinstance(part,list) or len(part)!=2 or not isinstance(part[0],str) or part[1] not in ('bold','thin','heavy'):
                raise ContractError('Each part requires [text, bold/thin/heavy]')
    if 'anchor' in item and item['anchor']!='face': raise ContractError('Unsupported text anchor')
    if 'o' in item:
        if not isinstance(item['o'],list) or len(item['o'])!=2: raise ContractError('Face offset requires two eye-unit coordinates')
        for v in item['o']: number(v,where+'.o',-100,100)
    for key in ('size_eu','min','max'):
        if key in item:number(item[key],where+'.'+key,.001,2000)
    if 'min' in item and 'max' in item and item['min']>item['max']: raise ContractError('Text min exceeds max')
    number(item.get('size',96),where+'.size',1,2000)
    if isinstance(item.get('weight'),str):
        # CSS keyword/numeric-string forms, as accepted for declared fonts (audit F-OK-003)
        import re
        if item['weight'] not in ('normal','bold') and not re.fullmatch(r'[1-9][0-9]{0,2}|1000',item['weight']):
            raise ContractError(f'{where}.weight: use normal, bold or 1..1000')
    for key in ('alpha','lw','rot','anim_d','pop','dt','base','fade_out','boil','seed','weight'):
        if key not in item or (key=='weight' and isinstance(item[key],str)): continue
        low,high=None,None
        if key in ('lw','base','fade_out','boil'): low=0
        if key in ('anim_d','dt'): low=.001
        if key=='alpha': low,high=0,1
        if key=='weight': low,high=1,1000
        number(item[key],f'{where}.{key}',low,high,integer=key in ('base','seed'))
    for key in ('fill','stroke'):
        if key in item and item[key] is not None: color(item[key],f'{where}.{key}')
    if item.get('render_style','legacy') not in ('legacy','explicit'):raise ContractError('Unknown text render_style')
    if 'on_specials' in item and not isinstance(item['on_specials'],bool):raise ContractError('on_specials must be true or false')
    if 'tracking' in item:number(item['tracking'],where+'.tracking',-200,1000)
    for key in ('scale_x','scale_y'):
        if key in item:number(item[key],where+'.'+key,.001,20)
    def keys(rows,label):
        if not isinstance(rows,list) or not rows:raise ContractError(label+' requires opacity keyframes')
        last=-1
        for row in rows:
            if not isinstance(row,list) or len(row)!=2:raise ContractError(label+' requires [seconds, alpha] pairs')
            number(row[0],label+'.time',0);number(row[1],label+'.alpha',0,1)
            if row[0]<=last:raise ContractError(label+' times must strictly increase')
            last=row[0]
    if 'opacity_keys' in item:keys(item['opacity_keys'],where+'.opacity_keys')
    if 'karaoke' in item:   # audit F-CAP-001: per-word highlight timing (seconds from the item start)
        k=item['karaoke'];fields(k,'words highlight mode',where+'.karaoke')
        if 'parts' in item:raise ContractError(f'{where}.karaoke: use plain text (not parts)')
        color(k.get('highlight'),where+'.karaoke.highlight',alpha=True)
        if k.get('mode','word') not in ('word','sweep'):raise ContractError(f'{where}.karaoke.mode: word or sweep')
        words=k.get('words')
        if not isinstance(words,list) or not words:raise ContractError(f'{where}.karaoke.words: nonempty list of {{text, t0, t1}}')
        pos=0;text=item.get('text','')
        for i,w in enumerate(words):
            fields(w,'text t0 t1',f'{where}.karaoke.words[{i}]')
            if not isinstance(w.get('text'),str) or not w['text']:raise ContractError(f'{where}.karaoke.words[{i}].text: nonempty string')
            number(w.get('t0'),f'{where}.karaoke.words[{i}].t0',0);number(w.get('t1'),f'{where}.karaoke.words[{i}].t1',w['t0'])
            at=text.find(w['text'],pos)
            if at<0:raise ContractError(f'{where}.karaoke.words[{i}]: {w["text"]!r} does not occur (in order) in the text')
            pos=at+len(w['text'])
    if 'letter_opacity_keys' in item:
        text=''.join(p[0] for p in item['parts']) if 'parts' in item else item['text']
        rows=item['letter_opacity_keys']
        if not isinstance(rows,list) or len(rows)!=len(text):raise ContractError('letter_opacity_keys requires one keyframe list per Unicode character, including spaces')
        for row in rows:keys(row,where+'.letter_opacity_keys')
    if 'flicker' in item:
        f=item['flicker'];fields(f,'hz duty min_alpha seed per_letter',where+'.flicker')
        number(f.get('hz',12),'flicker.hz',.01,240);number(f.get('duty',.8),'flicker.duty',0,1)
        number(f.get('min_alpha',0),'flicker.min_alpha',0,1);number(f.get('seed',1),'flicker.seed',integer=True)
        if not isinstance(f.get('per_letter',False),bool):raise ContractError('flicker.per_letter must be boolean')
    pos=item.get('pos',[.5,.5])
    if not isinstance(pos,list) or len(pos)!=2: raise ContractError('Text pos must have two coordinates')
    for v in pos: number(v,where+'.pos',0,1)
    if item.get('style','italic') not in ('normal','italic','oblique'): raise ContractError('Unsupported font style')
    if item.get('align','center') not in ('left','center','right'): raise ContractError('Unsupported text alignment')
    if item.get('anim','none') not in ('none','pop','slam','fade','grow','type'): raise ContractError('Unsupported text animation')
    if 'sc' in item:
        if not isinstance(item['sc'],list) or not item['sc']: raise ContractError('sc requires a nonempty array')
        for v in item['sc']: number(v,where+'.sc',.001,100)
    shadow=item.get('shadow','glow')
    if isinstance(shadow,dict):
        fields(shadow,'color blur dx dy',where+'.shadow')
        if 'color' in shadow: color(shadow['color'],where+'.shadow.color')
        for key in ('blur','dx','dy'):
            if key in shadow: number(shadow[key],where+'.shadow.'+key,0 if key=='blur' else None)
    elif shadow is not False and shadow not in ('glow','dark'):
        raise ContractError('Unsupported text shadow')
