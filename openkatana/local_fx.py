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
    'local_curve': 'scale dx dy blur glow exposure at mirror glow_radius glow_bright glow_contrast glow_mode',
    'local_turbulent_displace': 'displacement amount size complexity evolution speed offset drift every pin region feather seed at',
    'local_displacement_map': 'clip src speed loop amount x y smooth region feather at',
}
NAMES = tuple(SPECS)
RANGES = {'amount': (0, 1), 'd': (.001, 60), 'at': (0, 3600), 'spacing': (3, 200), 'mix': (0, 1), 'count': (1, 512),
          'opacity': (0, 1), 'inner': (0, 1), 'width': (.1, 50), 'seed': (-1e9, 1e9), 'every': (1, 60), 'n': (2, 64),
          'hue': (0, 360), 'tolerance': (0, 180), 'soft': (0, 90), 'min_sat': (0, 1), 'levels': (2, 64), 'margin': (0, .3),
          'size': (1, 2000), 'glow_radius': (.001, .5), 'glow_bright': (0, 10), 'glow_contrast': (0, 10)}
INTEGER = ('count', 'seed', 'every', 'n', 'levels')
# local_curve per-frame arrays (frame 0 = the shot start): scale, offsets and blur radius as fractions of the canvas height
CURVES = {'scale': (.05, 20), 'dx': (-5, 5), 'dy': (-5, 5), 'blur': (0, .5), 'glow': (0, 4), 'exposure': (0, 8)}
MAX_CURVE = 600
DISPLACEMENTS = ('turbulent', 'bulge', 'twist', 'horizontal', 'vertical', 'cross')
PINS = ('all', 'none', 'horizontal', 'vertical')
TURBULENT = {'size': (1, 4000), 'complexity': (1, 8), 'evolution': (-1e4, 1e4), 'speed': (-60, 60), 'feather': (0, 1)}
CHANNELS = ('red', 'green', 'blue', 'alpha', 'luma', 'none')


def _displacement_map(k, v, loc):
    """local_displacement_map fields beyond those shared with local_turbulent_displace."""
    if k == 'clip':
        if not isinstance(v, str) or not v:
            raise ContractError(f'{loc}: the id of a clip in clips (the map)')
    elif k in ('x', 'y'):
        if v not in CHANNELS:
            raise ContractError(f'{loc}: one of {", ".join(CHANNELS)}')
    elif k == 'loop':
        if v not in ('loop', 'pingpong', 'clamp'):
            raise ContractError(f'{loc}: loop, pingpong or clamp')
    elif k == 'src':
        number(v, loc, 0, 86400)
    elif k == 'smooth':
        number(v, loc, 0, 200)
    else:
        return False
    return True


def _turbulent(k, v, loc):
    """local_turbulent_displace fields that differ from the shared ones (amount in px at 1080, keyframes allowed)."""
    if k == 'displacement':
        if v not in DISPLACEMENTS:
            raise ContractError(f'{loc}: one of {", ".join(DISPLACEMENTS)}')
    elif k == 'pin':
        if v not in PINS:
            raise ContractError(f'{loc}: one of {", ".join(PINS)}')
    elif k == 'amount':
        if isinstance(v, list):
            if not 1 <= len(v) <= 64:
                raise ContractError(f'{loc}: a number or 1..64 keyframes [seconds, px]')
            last = -1
            for i, key in enumerate(v):
                if not isinstance(key, list) or len(key) != 2:
                    raise ContractError(f'{loc}[{i}]: expected [seconds, px]')
                number(key[0], f'{loc}[{i}][0]', 0, 3600); number(key[1], f'{loc}[{i}][1]', 0, 1000)
                if key[0] <= last:
                    raise ContractError(f'{loc}: keyframe times must increase')
                last = key[0]
        else:
            number(v, loc, 0, 1000)
    elif k in ('offset', 'drift'):
        if not isinstance(v, list) or len(v) != 2:
            raise ContractError(f'{loc}: expected [x, y] px (at 1080)')
        for x in v:
            number(x, loc, -1e5, 1e5)
    elif k == 'region':
        if not isinstance(v, list) or len(v) != 4:
            raise ContractError(f'{loc}: expected [x0, y0, x1, y1] (0..1)')
        for x in v:
            number(x, loc, 0, 1)
        if v[2] <= v[0] or v[3] <= v[1]:
            raise ContractError(f'{loc}: x1 and y1 must be greater than x0 and y0')
    elif k in TURBULENT:
        lo, hi = TURBULENT[k]
        number(v, loc, lo, hi, integer=k == 'complexity')
    else:
        return False
    return True


def local_effect(name, p, where):
    fields(p, SPECS[name], where)
    for k, v in p.items():
        loc = f'{where}.{k}'
        if name in ('local_turbulent_displace', 'local_displacement_map') and _turbulent(k, v, loc):
            continue
        if name == 'local_displacement_map' and _displacement_map(k, v, loc):
            continue
        if k in ('ink', 'paper', 'color', 'fill'):
            color(v, loc)
        elif k in CURVES:
            if not isinstance(v, list) or not 1 <= len(v) <= MAX_CURVE:
                raise ContractError(f'{loc}: an array of 1..{MAX_CURVE} per-frame values')
            lo, hi = CURVES[k]
            for i, x in enumerate(v):
                number(x, f'{loc}[{i}]', lo, hi)
        elif k == 'mirror':
            if not isinstance(v, bool):
                raise ContractError(f'{loc}: expected boolean')
        elif k == 'glow_mode':
            if v not in ('screen', 'add'):
                raise ContractError(f'{loc}: screen or add')
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
    if name == 'local_displacement_map' and 'clip' not in p:
        raise ContractError(f'{where}: clip (the id of the map clip in clips) is required')


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
