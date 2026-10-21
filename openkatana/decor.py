"""Decorative and face graphics layers (audit F-NAT-006 / F-NAT-007). The renderer supports configurable phases and orders; every drawing (shapes, doodles, sparkles, splats, slashes, borders,
face graphics) is OpenKatana's own design in web/decor.js. Usable as shot fx, timeline post entries or shot layers.
Face graphics and face-anchored placement use the clip's face track (eye midpoint, eye distance D = 1 eye unit,
roll); OpenKatana has no mouth/nose landmarks, so those points are estimated from the eyes."""
import re

from .contracts import ContractError, color, fields, number

KAWAII = ('note', 'note2', 'heart', 'hearto', 'bow', 'spark', 'star', 'dots', 'swirl', 'squig', 'arrow', 'cross', 'dash3', 'blush', 'ear', 'whisk')
INK = ('zig', 'scratch', 'splat', 'rays', 'arrow', 'spark', 'cross', 'hatch', 'star', 'xx', 'bolt', 'bang')
FONT_KEYS = ' family weight style kind'
SPECS = {
    'stairs': 'seed size cells x y color color2',
    'glow': 'amt v blur',
    'glint': 'at d from to src r color',
    'doodles': 'v n scratch mono types seed color',
    'face_doodles': 'items pool n seed colors',
    'doodle': 't pos size rot at seed alpha colors',
    'word': 'text v at dx dy k min max fill stroke lw shadow' + FONT_KEYS,
    'type': 'parts text at dt base dx dy k min max pos fill stroke shadow' + FONT_KEYS,
    'slash': 'at dx dy n seed fill stroke',
    'sparkle': 'pos r seed color',
    'splat': 'items pos r n seed color color2',
    'bw': 'filter bars color',
    'tag': 'text v pos bx by dx size fill' + FONT_KEYS,
    'border': 'color seed',
    'cheeks': 'color force', 'fangs': 'color len dy force', 'ears': 'at size dx dy colors', 'whisk': 'at dx dy colors',
    'blush': 'at dx dy size colors', 'ast': 'dx dy size colors',
}
NAMES = tuple(SPECS)
TEXTUAL = ('word', 'type', 'tag')   # need a declared font family
FILTER = re.compile(r'^\s*((grayscale|sepia|invert|saturate|contrast|brightness|opacity)\(\s*\d+(\.\d+)?%?\s*\)|hue-rotate\(\s*-?\d+(\.\d+)?deg\s*\)|blur\(\s*\d+(\.\d+)?px\s*\))(\s+((grayscale|sepia|invert|saturate|contrast|brightness|opacity)\(\s*\d+(\.\d+)?%?\s*\)|hue-rotate\(\s*-?\d+(\.\d+)?deg\s*\)|blur\(\s*\d+(\.\d+)?px\s*\)))*\s*$')
RANGES = {'seed': (-1e9, 1e9), 'size': (.01, 4000), 'x': (0, 1), 'y': (0, 1), 'amt': (0, 1), 'v': (0, 3), 'blur': (0, 200),
          'at': (0, 3600), 'd': (.001, 3600), 'r': (1, 4000), 'n': (0, 64), 'scratch': (0, 32), 'rot': (-12.6, 12.6),
          'alpha': (0, 1), 'dx': (-50, 50), 'dy': (-50, 50), 'k': (.05, 20), 'min': (1, 4000), 'max': (1, 4000),
          'lw': (0, 200), 'dt': (.001, 10), 'base': (0, 10000), 'bx': (0, 1), 'by': (0, 1), 'len': (.01, 10)}
INTEGER = ('seed', 'n', 'scratch', 'base')


def _xy(v, where):
    if not isinstance(v, list) or len(v) != 2:
        raise ContractError(f'{where}: expected [x, y]')
    for x in v:
        number(x, where)


def _colors(v, where):
    if not isinstance(v, dict):
        raise ContractError(f'{where}: {{line, fill, blush}} colours')
    fields(v, 'line fill blush', where)
    for k, c in v.items():
        color(c, f'{where}.{k}')


def decor_effect(name, p, where):
    fields(p, SPECS[name], where)
    for k, v in p.items():
        loc = f'{where}.{k}'
        if k in ('color', 'color2', 'fill', 'stroke'):
            color(v, loc)
        elif k == 'colors':
            _colors(v, loc)
        elif k in ('src', 'mono', 'force'):
            if not isinstance(v, bool):
                raise ContractError(f'{loc}: expected boolean')
        elif k in ('text', 'family'):
            if not isinstance(v, str) or not v or len(v) > 256:
                raise ContractError(f'{loc}: expected nonempty text')
        elif k == 'v' and name in ('word', 'tag'):
            if not isinstance(v, str) or not v or len(v) > 256:
                raise ContractError(f'{loc}: the text (alias of text)')
        elif k == 'weight':
            if not (isinstance(v, int) and 1 <= v <= 1000) and v not in ('normal', 'bold'):
                raise ContractError(f'{loc}: 1..1000, normal or bold')
        elif k == 'style':
            if v not in ('normal', 'italic'):
                raise ContractError(f'{loc}: normal or italic')
        elif k == 'kind':
            if v not in ('bold', 'thin', 'heavy'):
                raise ContractError(f'{loc}: bold, thin or heavy')
        elif k == 'shadow':
            if v not in (True, False, 'glow', 'dark'):
                raise ContractError(f'{loc}: true, false, glow or dark')
        elif k in ('from', 'to'):
            _xy(v, loc)
        elif k == 'pos':
            if name == 'tag' and v in ('bottom', 'face'):
                continue
            _xy(v, loc)
            for x in v:
                number(x, loc, 0, 1)
        elif k == 't':
            if v not in KAWAII:
                raise ContractError(f'{loc}: one of {", ".join(KAWAII)}')
        elif k in ('pool', 'types'):
            names = KAWAII if k == 'pool' else INK
            if not isinstance(v, list) or not v or any(x not in names for x in v):
                raise ContractError(f'{loc}: a list of {", ".join(names)}')
        elif k == 'cells':
            if not isinstance(v, list) or not 1 <= len(v) <= 256:
                raise ContractError(f'{loc}: 1..256 [col, row] cells')
            for c in v:
                _xy(c, loc)
                for x in c:
                    number(x, loc, -100, 100, integer=True)
        elif k == 'bars':
            _xy(v, loc)
            for x in v:
                number(x, loc, 0, 4000)
        elif k == 'filter':
            if not isinstance(v, str) or not FILTER.match(v):
                raise ContractError(f'{loc}: CSS filter functions only (grayscale, sepia, invert, saturate, contrast, brightness, opacity, hue-rotate, blur)')
        elif k == 'parts':
            if not isinstance(v, list) or not v:
                raise ContractError(f'{loc}: [[text, bold|thin|heavy], ...]')
            for part in v:
                if not isinstance(part, list) or len(part) != 2 or not isinstance(part[0], str) or part[1] not in ('bold', 'thin', 'heavy'):
                    raise ContractError(f'{loc}: [[text, bold|thin|heavy], ...]')
        elif k == 'items':
            if not isinstance(v, list) or not 1 <= len(v) <= 32:
                raise ContractError(f'{loc}: 1..32 items')
            for j, it in enumerate(v):
                sub = f'{loc}[{j}]'
                if not isinstance(it, dict):
                    raise ContractError(f'{sub}: expected an object')
                if name == 'face_doodles':
                    fields(it, 't o s r at', sub)
                    if it.get('t') not in KAWAII:
                        raise ContractError(f'{sub}.t: one of {", ".join(KAWAII)}')
                    if 'o' in it:
                        _xy(it['o'], sub + '.o')
                    for kk, (lo, hi) in {'s': (.01, 20), 'r': (-12.6, 12.6), 'at': (0, 3600)}.items():
                        if kk in it:
                            number(it[kk], f'{sub}.{kk}', lo, hi)
                else:
                    decor_effect('splat', it, sub)
        else:
            lo, hi = RANGES[k]
            number(v, loc, lo, hi, integer=k in INTEGER)
    if name in TEXTUAL and not any(k in p for k in ('text', 'v', 'parts')):
        raise ContractError(f'{where}: needs text' + (' or parts' if name == 'type' else ''))
    if name == 'face_doodles' and 'items' in p and 'n' in p:
        raise ContractError(f'{where}: give items or n, not both')
