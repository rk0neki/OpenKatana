"""Validation for the explicitly implemented camera and compositing subset."""
from .contracts import ContractError, color, fields, number


CAMERA = ('zoom', 'push', 'punch', 'ladder', 'pan', 'tilt', 'roll', 'handheld', 'shake', 'crash', 'pulse')
TRANSITIONS = ('white', 'flash', 'dip', 'mosaic', 'blur', 'flashlight', 'glitch', 'magenta', 'wipe')
POST = ('invert', 'tint', 'white', 'flash', 'dip', 'strobe', 'letterbox')
SUBJECT = ('cutout', 'outline')
SOURCE = ('stutter', 'trail')   # source-frame effects (audit F-NAT-005)
from .expanded import SPECS
from .local_fx import NAMES as LOCAL, local_effect, measured
from .decor import NAMES as DECOR, decor_effect
EXTRA = tuple(SPECS) + LOCAL + DECOR
BLENDS = ('source-over', 'multiply', 'screen', 'overlay', 'darken', 'lighten',
          'color-dodge', 'color-burn', 'hard-light', 'soft-light', 'difference',
          'exclusion', 'hue', 'saturation', 'color', 'luminosity', 'lighter')


def effect(name, value, where):
    if name=='graffiti':
        if value is False:return
        from .graffiti import graffiti_item
        if not isinstance(value,dict):raise ContractError('graffiti requires a text object')
        if any(k in value for k in ('type','phase','order')):raise ContractError('Use an explicit layer for graffiti phase/order')
        return graffiti_item({'type':'graffiti',**value},where,layer=True)
    if value is False:
        return
    if value is True:
        value = {}
    if not isinstance(value, dict):
        raise ContractError(f'{where}: use an object, true or false')
    if name in LOCAL:
        return local_effect(name, value, where)
    if name in DECOR:
        return decor_effect(name, value, where)
    if name in SPECS:
        from .expanded import effect as expanded_effect
        return expanded_effect(name,value,where)
    allowed = {
        'zoom': 'z0 z1 ease', 'push': 'v rate', 'punch': 'v amt d curve at hits',
        'ladder': 'steps v', 'pan': 'dx dy v', 'tilt': 'v', 'roll': 'v rate from to ease d',
        'crash': 'v d at ease center', 'pulse': 'v d at hits center',
        'white': 'at d color side', 'flash': 'at d color side amt',
        'dip': 'd color side', 'invert': 'at d amt', 'tint': 'color v amt op d',
        'strobe': 'every color amt at d', 'letterbox': 'top bottom v color',
        'shake': 'amp d every at hits', 'cutout': '',
        'handheld': 'amp v hz rot seed',
        'outline': 'r color blur alpha dx dy',
        'stutter': 'n step', 'trail': 'n step alpha op',
    }
    fields(value, allowed[name], where)
    for key, item in value.items():
        location = f'{where}.{key}'
        if key == 'color':
            color(item, location, alpha=name == 'tint')   # tint replaces the colour's alpha with v
        elif isinstance(item, dict) and 'from' in item:
            raise ContractError(f'{location}: animated numbers are supported in looks only')
        elif key == 'ease':
            if item not in ('lin', 'in2', 'in3', 'out2', 'out3', 'inout', 'inout3', 'outback'):
                raise ContractError(f'{location}: unsupported easing (lin, in2, in3, out2, out3, inout, inout3, outback)')
        elif key == 'side':
            if item not in ('in', 'out'):
                raise ContractError(f'{location}: expected in or out')
        elif key == 'op':
            if item not in BLENDS:
                raise ContractError(f'{location}: unsupported blend mode')
        elif key == 'center':
            if not isinstance(item, list) or len(item) != 2:
                raise ContractError(f'{location}: expected [x, y] (0..1 of the screen)')
            for v in item: number(v, location, 0, 1)
        elif key == 'amp' and name=='shake':
            if not isinstance(item,list) or len(item)!=2:
                raise ContractError(f'{location}: expected two amplitudes')
            for v in item: number(v,location,0,10000)
        elif key == 'hits' or name == 'ladder':
            if not isinstance(item, list) or not item:
                raise ContractError(f'{location}: expected a nonempty array')
            for entry in item:
                number(entry, location, 0 if key == 'hits' else .001)
        else:
            low, high = None, None
            if key in ('d', 'curve', 'z0', 'z1'):
                low = .001
            elif key == 'at':
                low = 0
            elif key == 'every':
                low = 1
            elif name in ('flash', 'invert', 'tint', 'strobe') and key in ('amt', 'v'):
                low, high = 0, 1
            elif name == 'letterbox':
                low, high = 0, 1
            elif name == 'outline' and key in ('r','blur','alpha'):
                low,high = 0,1 if key=='alpha' else 1000
            elif name=='handheld' and key in ('amp','v','hz'):low=0
            elif name=='crash' and key=='v':low,high=1,20
            elif name=='pulse' and key=='v':low,high=0,5
            elif name in SOURCE and key in ('n','step'):low,high=1,(16 if name=='trail' and key=='n' else 64)
            elif name=='trail' and key=='alpha':low,high=0,1
            number(item, location, low, high, integer=key in ('every','seed') or (name in SOURCE and key in ('n','step')))


def camera(cam, where):
    fields(cam, 'fit z ax ay sx sy rot mir cover crop type lock ld lx ly z0 z1 kick kick_rate lockRot shutter local_measured ' + ' '.join(CAMERA), where)
    if 'local_measured' in cam:
        measured(cam['local_measured'], where + '.local_measured')
    if 'shutter' in cam:
        number(cam['shutter'], where + '.shutter', 0, 1)
    if 'type' in cam and cam['type']!='facelock':raise ContractError('Unsupported camera type')
    if 'lock' in cam and not isinstance(cam['lock'],bool):raise ContractError('Camera lock must be boolean')
    for prop in ('ld','lx','ly','z0','z1','kick','kick_rate','lockRot'):
        if prop in cam:
            number(cam[prop],f'{where}.{prop}',.001 if prop in ('ld','z0','z1') else 0,1 if prop in ('lx','ly','lockRot') else None)
    if 'cover' in cam and not isinstance(cam['cover'],bool):
        raise ContractError('cover must be boolean')
    if 'crop' in cam:
        values=cam['crop'] if isinstance(cam['crop'],list) else [.5,cam['crop']]
        if len(values)!=2: raise ContractError('crop requires a y coordinate or [x,y]')
        for v in values: number(v,'crop',0,1)
    if cam.get('fit', 'cover') not in ('cover', 'contain', 'width', 'height'):
        raise ContractError('Unsupported fit')
    for prop in ('z', 'ax', 'ay', 'sx', 'sy', 'rot'):
        if prop in cam:
            number(cam[prop], f'{where}.{prop}')
    if cam.get('z', 1) <= 0:
        raise ContractError('Camera zoom must be positive')
    if cam.get('mir', 0) not in (0, 1, False, True):
        raise ContractError('mir must be 0 or 1')
    for name in CAMERA:
        if name in cam:
            effect(name, cam[name], f'{where}.{name}')


def effects(values, where):
    fields(values, ' '.join(CAMERA + POST + SUBJECT + SOURCE + EXTRA + ('text','graffiti','stickers')), where)
    for name, value in values.items():
        if name in ('text','stickers'):
            if value is not False: raise ContractError(f'fx.{name} only supports false (hide them on this shot)')
            continue
        effect(name, value, f'{where}.{name}')


def transition(value, where):
    entries = value if isinstance(value, list) else [value]
    for entry in entries:
        if isinstance(entry, str):
            entry = {'type': entry}
        if not isinstance(entry, dict) or entry.get('type') not in TRANSITIONS:
            raise ContractError(f'{where}: unsupported transition')
        effect('fin' if entry['type']=='flashlight' else entry['type'], {k: v for k, v in entry.items() if k != 'type'}, where)


def layers(values, where):
    if not isinstance(values, list):
        raise ContractError(f'{where}: expected an array')
    for index, item in enumerate(values):
        location = f'{where}[{index}]'
        if not isinstance(item, dict) or item.get('type') not in POST + SUBJECT + EXTRA + ('text','graffiti'):
            raise ContractError(f'{location}: unsupported layer')
        if item.get('phase', 'post') not in ('back', 'subject', 'over', 'post', 'final'):
            raise ContractError(f'{location}: unsupported phase')
        if 'order' in item:
            number(item['order'], location + '.order')
        if item['type']=='text':
            continue  # Font/timing validation runs after the declared fonts are known.
        effect(item['type'], {k:v for k,v in item.items() if k not in ('type','phase','order')}, location)
