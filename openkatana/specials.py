"""Whole-frame inserts (audit F-NAT-004): `special` shots and top-level `specials[]` that override the shots beneath them.
Fills are flat colours; splats, sparkles and collage brackets are OpenKatana's own designs ."""
from .contracts import ContractError, color, fields, number

TYPES = {'flash': 'color splat bigsplat allow', 'white': 'color splat allow', 'black': 'color sparkle allow',
         'color': 'color allow', 'collage': 'bg panels brackets lines look allow'}
ALLOW = ('text', 'stickers', 'dust', 'border')
DEFAULT_ALLOW = {'flash': ['text', 'border'], 'white': ['stickers', 'text', 'dust', 'border'], 'black': ['border'],
                 'color': ['text', 'stickers'], 'collage': ['stickers', 'text', 'dust', 'border']}


def defaults(sp, palette):
    """Fill documented defaults (palette-dependent) so the renderer needs no palette."""
    kind = sp.get('type')
    if kind == 'flash':
        sp.setdefault('color', palette['accent'])
    elif kind == 'white':
        sp.setdefault('color', '#ffffff')
    elif kind == 'black':
        sp.setdefault('color', '#000000'); sp.setdefault('sparkle', True)
    elif kind == 'collage':
        sp.setdefault('bg', '#ffffff'); sp.setdefault('brackets', True)
    if kind in ('flash', 'white') and sp.get('splat', True) is True:
        sp['splat'] = palette['ink']
    return sp


def validate_special(sp, where, clips):
    from .effects import camera
    from .expanded import look
    if not isinstance(sp, dict) or sp.get('type') not in TYPES:
        raise ContractError(f'{where}: special needs a type: {", ".join(TYPES)}')
    kind = sp['type']
    fields(sp, 'type ' + TYPES[kind], where)
    if 'color' in sp:
        color(sp['color'], where + '.color')
    elif kind == 'color':
        raise ContractError(f'{where}: a color special needs color')
    if 'splat' in sp and sp['splat'] is not False:
        color(sp['splat'], where + '.splat')
    for k in ('bigsplat', 'sparkle', 'brackets'):
        if k in sp and not isinstance(sp[k], bool):
            raise ContractError(f'{where}.{k}: expected boolean')
    if 'allow' in sp:
        if not isinstance(sp['allow'], list) or any(a not in ALLOW for a in sp['allow']):
            raise ContractError(f'{where}.allow: list of {", ".join(ALLOW)}')
    if kind == 'collage':
        color(sp.get('bg', '#ffffff'), where + '.bg')
        panels = sp.get('panels')
        if not isinstance(panels, list) or not 1 <= len(panels) <= 16:
            raise ContractError(f'{where}.panels: 1..16 panels')
        for i, p in enumerate(panels):
            loc = f'{where}.panels[{i}]'
            fields(p, 'clip src srcf speed loop blend rect cam', loc)
            if p.get('clip') not in clips:
                raise ContractError(f'{loc}: unknown clip')
            if 'src' in p and 'srcf' in p:
                raise ContractError(f'{loc}: use src or srcf, not both')
            for k in ('src', 'srcf', 'speed'):
                if k in p:
                    number(p[k], f'{loc}.{k}', -1000, 1000)
            if p.get('loop', 'clamp') not in ('clamp', 'loop', 'pingpong'):
                raise ContractError(f'{loc}.loop: clamp, loop or pingpong')
            if 'blend' in p and not isinstance(p['blend'], bool):
                raise ContractError(f'{loc}.blend: expected boolean')
            rect = p.get('rect')
            if not isinstance(rect, list) or len(rect) != 4:
                raise ContractError(f'{loc}.rect: expected [x, y, w, h] (0..1)')
            for v in rect:
                number(v, loc + '.rect', 0, 1)
            if rect[2] <= 0 or rect[3] <= 0:
                raise ContractError(f'{loc}.rect: width and height must be positive')
            cam = p.get('cam', {})
            camera(cam, loc + '.cam')
            if cam.get('type') == 'facelock' or cam.get('lock'):
                raise ContractError(f'{loc}.cam: face lock is not available inside collage panels')
        for j, line in enumerate(sp.get('lines', [])):
            if not isinstance(line, list) or not 2 <= len(line) <= 256:
                raise ContractError(f'{where}.lines[{j}]: 2..256 [x, y] points')
            for pt in line:
                if not isinstance(pt, list) or len(pt) != 2:
                    raise ContractError(f'{where}.lines[{j}]: points are [x, y]')
                for v in pt:
                    number(v, f'{where}.lines[{j}]', 0, 1)
        look(sp.get('look'), where + '.look')


def validate_specials(edit):
    frames = edit['canvas']['frames']; end = 0
    items = edit.get('specials', [])
    if not isinstance(items, list):
        raise ContractError('specials: expected an array')
    for i, item in enumerate(items):
        where = f'specials[{i}]'
        if not isinstance(item, dict):
            raise ContractError(f'{where}: expected an object')
        body = {k: v for k, v in item.items() if k not in ('f0', 'f1')}
        validate_special(body, where, edit['clips'])
        number(item.get('f0'), where + '.f0', 0, frames - 1, integer=True)
        number(item.get('f1'), where + '.f1', item['f0'] + 1, frames, integer=True)
        if item['f0'] < end:
            raise ContractError(f'{where}: specials must be in time order without overlap (starts at {item["f0"]}, previous ends at {end})')
        end = item['f1']
