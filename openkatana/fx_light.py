"""Light effects (web/fx_light.js): validation of the pack's timeline fields."""
from .contracts import ContractError, color, number

# effect name -> its fields, space separated (unknown fields are rejected before validate runs)
SPECS = {
    'local_deep_glow': 'threshold radius exposure layers tint saturation blend at',
    'local_lens_flare': 'position brightness lens tint streak flicker seed at',
    'local_light_rays': 'center intensity length threshold tint blend at',
    'local_light_sweep': 'angle width softness intensity color position d ease reception at',
}
# keyframable fields (a value or [[seconds, value, ease?], ...]) and their ranges; points are [x, y] frame fractions
KEYED = {'threshold': (0, 1), 'radius': (.5, 2000), 'exposure': (0, 20), 'saturation': (0, 4), 'brightness': (0, 3),
         'streak': (0, 1), 'intensity': (0, 10), 'length': (0, 1), 'angle': (-360, 360), 'width': (1, 8000),
         'softness': (0, 1)}
POINTS = {'position': (-1, 2), 'center': (-1, 2)}
PLAIN = {'at': (0, 3600), 'd': (.001, 60), 'flicker': (0, 1), 'seed': (-1e9, 1e9), 'layers': (2, 8)}
INTEGER = ('seed', 'layers')
CHOICES = {'lens': ('50_300mm_zoom', '35mm_prime', '105mm_prime'), 'blend': ('add', 'screen'),
           'reception': ('add', 'luma')}


def _point(v, loc, lo, hi):
    if not isinstance(v, list) or len(v) != 2 or isinstance(v[0], list):
        raise ContractError(f'{loc}: expected [x, y] (fractions of the frame)')
    for c in v:
        number(c, loc, lo, hi)


def validate(name, p, where):
    """Check one effect's parameters; raise ContractError with the field path on a bad value."""
    from .local_fx import _ease, _keyed
    from .native import Normalizer
    for k, v in p.items():
        loc = f'{where}.{k}'
        if k in CHOICES:
            if v not in CHOICES[k]:
                raise ContractError(f'{loc}: one of {", ".join(CHOICES[k])}')
        elif k == 'position' and name == 'local_light_sweep':
            _keyed(v, loc, -1, 2)
        elif k in POINTS:
            if isinstance(v, list) and v and isinstance(v[0], list):
                _keyed(v, loc, *POINTS[k], point=True)
            else:
                _point(v, loc, *POINTS[k])
        elif k in KEYED:
            _keyed(v, loc, *KEYED[k])
        elif k == 'tint':
            if v != 'none':   # 'tint' is not one of native's colour keys (grades use it as a number): convert here
                c = Normalizer({}).colour(v, loc, allow_ref=False)
                color(c, loc)
                if c != v:
                    p[k] = c   # the canonical "#rrggbb" the renderer reads
        elif k == 'color':
            color(v, loc)
        elif k == 'ease':
            if v == 'hold':   # a keyframe ease; the automatic sweep would have nothing to hold
                raise ContractError(f'{loc}: hold is for keyframes; use lin, in2, out2, inout, ... or a cubic-bezier')
            _ease(v, loc)
        else:
            number(v, loc, *PLAIN[k], integer=k in INTEGER)
