"""Local timeline layers and measured camera moves. Validation for web/localfx.js.
Usable as shot fx, timeline post entries or shot layers."""
from .contracts import ContractError, color, fields, number

SPECS = {
    'local_whip': 'amount d at dir',
    'local_zoom_blur': 'amount d at center',
    'local_halftone': 'spacing mix ink paper',
    'local_speed_lines': 'count opacity color inner width seed every',
    'local_frame_slices': 'amount continuous n seed d',
    'local_selective_color': 'hue tolerance soft min_sat',
    'local_posterize': 'levels',
    'local_paper_frame': 'mode color margin seed',
    'local_scramble_text': 'text family size pos fill d at seed',
}
NAMES = tuple(SPECS)
RANGES = {'amount': (0, 1), 'd': (.001, 60), 'at': (0, 3600), 'spacing': (3, 200), 'mix': (0, 1), 'count': (1, 512),
          'opacity': (0, 1), 'inner': (0, 1), 'width': (.1, 50), 'seed': (-1e9, 1e9), 'every': (1, 60), 'n': (2, 64),
          'hue': (0, 360), 'tolerance': (0, 180), 'soft': (0, 90), 'min_sat': (0, 1), 'levels': (2, 64), 'margin': (0, .3),
          'size': (1, 2000)}
INTEGER = ('count', 'seed', 'every', 'n', 'levels')


def local_effect(name, p, where):
    fields(p, SPECS[name], where)
    for k, v in p.items():
        loc = f'{where}.{k}'
        if k in ('ink', 'paper', 'color', 'fill'):
            color(v, loc)
        elif k == 'continuous':
            if not isinstance(v, bool):
                raise ContractError(f'{loc}: expected boolean')
        elif k == 'dir':
            if v not in ('left', 'right', 'up', 'down'):
                raise ContractError(f'{loc}: left, right, up or down')
        elif k == 'mode':
            if v not in ('paper', 'filmstrip'):
                raise ContractError(f'{loc}: paper or filmstrip')
        elif k in ('center', 'pos'):
            if not isinstance(v, list) or len(v) != 2:
                raise ContractError(f'{loc}: expected [x, y] (0..1)')
            for x in v:
                number(x, loc, 0, 1)
        elif k in ('text', 'family'):
            if not isinstance(v, str) or not v or len(v) > 256:
                raise ContractError(f'{loc}: expected nonempty text')
        else:
            lo, hi = RANGES[k]
            number(v, loc, lo, hi, integer=k in INTEGER)
    if name == 'local_scramble_text' and not ('text' in p and 'family' in p):
        raise ContractError(f'{where}: text and family (a declared font) are required')


def measured(value, where):
    """cam.local_measured {f0, f1, pan_x, pan_y, zoom, roll_deg}: a linear move over absolute frames f0..f1-1."""
    if not isinstance(value, dict):
        raise ContractError(f'{where}: expected an object')
    fields(value, 'f0 f1 pan_x pan_y zoom roll_deg', where)
    for k in ('f0', 'f1'):
        if k not in value:
            raise ContractError(f'{where}: f0 and f1 (absolute frames) are required')
        number(value[k], f'{where}.{k}', 0, 10 ** 7, integer=True)
    if value['f1'] <= value['f0']:
        raise ContractError(f'{where}: f1 must be after f0')
    for k, (lo, hi) in {'pan_x': (-1, 1), 'pan_y': (-1, 1), 'zoom': (-.9, 10), 'roll_deg': (-180, 180)}.items():
        if k in value:
            number(value[k], f'{where}.{k}', lo, hi)
