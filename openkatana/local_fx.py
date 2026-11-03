"""Local timeline layers and measured camera moves. Validation for web/localfx.js.
Usable as shot fx, timeline post entries or shot layers."""
from .contracts import EASES, ContractError, color, fields, number

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
    'local_turbulent_displace': 'displacement amount size complexity evolution speed cycle offset drift every pin edges quality '
                                'region feather seed at',
    'local_displacement_map': 'clip src speed loop amount amount_x amount_y x y neutral fit smooth edges quality region feather at',
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
DISPLACEMENTS = ('turbulent', 'bulge', 'twist', 'turbulent_smoother', 'bulge_smoother', 'twist_smoother', 'horizontal',
                 'vertical', 'cross')
PINS = ('all', 'none', 'horizontal', 'vertical', 'all_locked', 'horizontal_locked', 'vertical_locked')
CHOICES = {'displacement': DISPLACEMENTS, 'pin': PINS, 'edges': ('reflect', 'clamp', 'wrap'), 'quality': ('low', 'high'),
           'fit': ('stretch', 'center', 'tile'), 'loop': ('loop', 'pingpong', 'clamp')}
TURBULENT = {'speed': (-60, 60), 'cycle': (.001, 1e4), 'feather': (0, 1), 'src': (0, 86400), 'smooth': (0, 200)}
# fields that take keyframes, with the range of their values (offset is an [x, y] point)
KEYED = {'amount': (0, 1000), 'amount_x': (0, 1000), 'amount_y': (0, 1000), 'size': (1, 4000), 'complexity': (1, 10),
         'evolution': (-1e4, 1e4), 'offset': (-1e5, 1e5)}
KEY_EASES = EASES + ('inout3', 'ease', 'hold')
MAX_KEYS = 64
CHANNELS = ('red', 'green', 'blue', 'alpha', 'luma', 'luminance', 'hue', 'lightness', 'saturation', 'full', 'half', 'none',
            'off')


def _ease(e, loc):
    """A keyframe's ease into the next key: a name, or a cubic-bezier [x1, y1, x2, y2] (x1 and x2 in 0..1)."""
    if isinstance(e, list):
        if len(e) != 4:
            raise ContractError(f'{loc}: an ease name or a cubic-bezier [x1, y1, x2, y2]')
        for j, c in enumerate(e):
            number(c, loc, *((0, 1) if j % 2 == 0 else (-5, 5)))
    elif not isinstance(e, str) or e not in KEY_EASES:
        raise ContractError(f'{loc}: one of {", ".join(KEY_EASES)} or a cubic-bezier [x1, y1, x2, y2]')


def _keyed(v, loc, lo, hi, point=False):
    """A value, or 1..64 keyframes [seconds, value] / [seconds, value, ease] with increasing times."""
    def value(x, at):
        if point:
            if not isinstance(x, list) or len(x) != 2:
                raise ContractError(f'{at}: expected [x, y] px (at 1080)')
            for c in x:
                number(c, at, lo, hi)
        else:
            number(x, at, lo, hi)
    if not (isinstance(v, list) and v and isinstance(v[0], list)):
        return value(v, loc)
    if len(v) > MAX_KEYS:
        raise ContractError(f'{loc}: at most {MAX_KEYS} keyframes')
    last = -1
    for i, key in enumerate(v):
        at = f'{loc}[{i}]'
        if not isinstance(key, list) or len(key) not in (2, 3):
            raise ContractError(f'{at}: expected [seconds, value] or [seconds, value, ease]')
        number(key[0], f'{at}[0]', 0, 3600)
        value(key[1], f'{at}[1]')
        if len(key) == 3:
            _ease(key[2], f'{at}[2]')
        if key[0] <= last:
            raise ContractError(f'{loc}: keyframe times must increase')
        last = key[0]


def _displacement(k, v, loc):
    """Fields of local_turbulent_displace and local_displacement_map (amounts in px at 1080, keyframes allowed)."""
    if k in CHOICES:
        if v not in CHOICES[k]:
            raise ContractError(f'{loc}: one of {", ".join(CHOICES[k])}')
    elif k in KEYED:
        _keyed(v, loc, *KEYED[k], point=k == 'offset')
    elif k in ('x', 'y'):
        if v not in CHANNELS:
            raise ContractError(f'{loc}: one of {", ".join(CHANNELS)}')
    elif k == 'clip':
        if not isinstance(v, str) or not v:
            raise ContractError(f'{loc}: the id of a clip in clips (the map)')
    elif k == 'neutral':
        if v != 'mean' and (isinstance(v, (str, bool)) or not isinstance(v, (int, float))):
            raise ContractError(f'{loc}: a level 0..255 or "mean"')
        if v != 'mean':
            number(v, loc, 0, 255)
    elif k == 'drift':
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
        number(v, loc, *TURBULENT[k])
    else:
        return False
    return True


def local_effect(name, p, where):
    fields(p, SPECS[name], where)
    for k, v in p.items():
        loc = f'{where}.{k}'
        if name in ('local_turbulent_displace', 'local_displacement_map') and _displacement(k, v, loc):
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
