"""After Effects' Generate effects (web/fx_generate.js): validation of the pack's timeline fields."""
from .contracts import ContractError, number

_COMMON = 'blend opacity at'
# effect name -> its fields, space separated (unknown fields are rejected before validate runs)
SPECS = {
    'local_fractal_noise': 'fractal_type noise_type invert contrast brightness overflow rotation scale offset complexity '
                           f'sub_influence sub_scaling sub_rotation evolution speed cycle seed tint {_COMMON}',
    'local_cell_pattern': f'cell_pattern invert contrast brightness overflow disperse size offset evolution speed seed {_COMMON}',
    'local_gradient_ramp': f'start start_color end end_color shape ramp_scatter {_COMMON}',
    'local_four_color_gradient': 'point_1 color_1 point_2 color_2 point_3 color_3 point_4 color_4 blend_amount jitter '
                                 f'{_COMMON}',
    'local_grid': f'anchor width height border feather invert color {_COMMON}',
    'local_radio_waves': 'producer frequency expansion lifespan shape sides stroke_color start_width end_width fade_in '
                         f'fade_out {_COMMON}',
    'local_lightning': 'origin direction lightning_type conductivity core_radius core_color glow_radius glow_opacity '
                       f'glow_color forking decay turbulence seed flicker {_COMMON}',
}
BLENDS = ('normal', 'add', 'screen', 'multiply', 'overlay', 'soft_light', 'hard_light', 'color_dodge', 'color_burn',
          'darken', 'lighten', 'difference', 'exclusion', 'hue', 'saturation', 'color', 'luminosity')
OVERFLOWS = ('clip', 'soft_clamp', 'wrap')
CHOICES = {
    'blend': BLENDS,
    'fractal_type': ('basic', 'turbulent_smooth', 'turbulent_sharp'),
    'noise_type': ('block', 'linear', 'soft_linear', 'spline'),
    'overflow': OVERFLOWS,
    'cell_pattern': ('bubbles', 'crystals', 'plates', 'tubular'),
    'lightning_type': ('strike', 'breaking', 'bouncy', 'omni', 'anywhere'),
    ('local_gradient_ramp', 'shape'): ('linear', 'radial'),
    ('local_radio_waves', 'shape'): ('circle', 'square', 'polygon'),
}
# keyframable fields (a value or [[seconds, value, ease?], ...]) and their ranges
KEYED = {'opacity': (0, 1), 'contrast': (0, 10000), 'brightness': (-1000, 1000), 'rotation': (-36000, 36000),
         'scale': (1, 20000), 'complexity': (1, 20), 'evolution': (-1e4, 1e4), 'size': (2, 4000), 'disperse': (0, 1),
         'ramp_scatter': (0, 1), 'blend_amount': (1, 1000), 'jitter': (0, 1), 'width': (2, 8000), 'height': (2, 8000),
         'border': (0, 2000), 'feather': (0, 2000), 'conductivity': (-1e4, 1e4), 'core_radius': (0, 200),
         'glow_radius': (0, 1000), 'glow_opacity': (0, 1)}
# [x, y] frame fractions, keyframable
POINTS = ('start', 'end', 'point_1', 'point_2', 'point_3', 'point_4', 'anchor', 'producer', 'origin', 'direction')
PLAIN = {'at': (0, 3600), 'seed': (-1e9, 1e9), 'speed': (-100, 100), 'cycle': (.001, 1e4), 'sub_influence': (0, 100),
         'sub_scaling': (10, 100), 'sub_rotation': (-36000, 36000), 'frequency': (.01, 60), 'expansion': (0, 1e5),
         'lifespan': (.01, 3600), 'sides': (3, 64), 'start_width': (0, 1000), 'end_width': (0, 1000),
         'fade_in': (0, 3600), 'fade_out': (0, 3600), 'forking': (0, 1), 'decay': (0, 1), 'turbulence': (0, 10),
         'flicker': (0, 600)}
INTEGER = ('seed', 'sides', 'flicker')
COLOURS = ('tint', 'start_color', 'end_color', 'color_1', 'color_2', 'color_3', 'color_4', 'color', 'stroke_color',
           'core_color', 'glow_color')


def _point(v, loc):
    if not isinstance(v, list) or len(v) != 2 or isinstance(v[0], list):
        raise ContractError(f'{loc}: expected [x, y] (fractions of the frame)')
    for c in v:
        number(c, loc, -1, 2)


def validate(name, p, where):
    """Check one effect's parameters; raise ContractError with the field path on a bad value."""
    from .contracts import color
    from .local_fx import _keyed
    from .native import Normalizer
    for k, v in p.items():
        loc = f'{where}.{k}'
        choices = CHOICES.get((name, k), CHOICES.get(k))
        if choices:
            if v not in choices:
                raise ContractError(f'{loc}: one of {", ".join(choices)}')
        elif k in POINTS:
            if isinstance(v, list) and v and isinstance(v[0], list):
                for i, key in enumerate(v):   # check the points first: _keyed's own message speaks of px at 1080
                    if isinstance(key, list) and len(key) in (2, 3):
                        _point(key[1], f'{loc}[{i}][1]')
                _keyed(v, loc, -1, 2, point=True)
            else:
                _point(v, loc)
        elif k == 'offset':
            _keyed(v, loc, -1e5, 1e5, point=True)
        elif k in KEYED:
            _keyed(v, loc, *KEYED[k])
        elif k in COLOURS:
            if k == 'tint' and v == 'none':
                continue
            c = Normalizer({}).colour(v, loc, allow_ref=False)   # every colour syntax, canonicalised to "#rrggbb"
            color(c, loc)
            if c != v:
                p[k] = c
        elif k == 'invert':
            if not isinstance(v, bool):
                raise ContractError(f'{loc}: expected boolean')
        else:
            number(v, loc, *PLAIN[k], integer=k in INTEGER)
