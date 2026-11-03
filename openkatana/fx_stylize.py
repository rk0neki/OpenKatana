"""After Effects' Stylize effects (web/fx_stylize.js): validation of the pack's timeline fields."""
from .contracts import ContractError, number

_COMMON = 'region feather at'
# effect name -> its fields, space separated (unknown fields are rejected before validate runs)
SPECS = {
    'local_rgb_split': f'mode amount angle center edges quality {_COMMON}',
    'local_motion_tile': 'tile_center tile_width tile_height output_width output_height mirror_edges phase '
                         f'horizontal_phase_shift {_COMMON}',
    'local_find_edges': f'invert blend_with_original {_COMMON}',
    'local_emboss': f'direction relief contrast blend_with_original {_COMMON}',
    'local_mosaic': f'horizontal_blocks vertical_blocks sharp_colors {_COMMON}',
    'local_scatter': f'scatter_amount grain randomize_every_frame seed {_COMMON}',
}
CHOICES = {'mode': ('linear', 'radial'), 'grain': ('both', 'horizontal', 'vertical')}
# fields that take keyframes (a value or [[seconds, value, ease?], ...]), with the range of their values
KEYED = {'amount': (-1000, 1000), 'angle': (-36000, 36000), 'tile_width': (.5, 1000), 'tile_height': (.5, 1000),
         'output_width': (0, 1000), 'output_height': (0, 1000), 'phase': (-36000, 36000), 'blend_with_original': (0, 1),
         'direction': (-36000, 36000), 'relief': (0, 200), 'contrast': (0, 1000), 'horizontal_blocks': (1, 8192),
         'vertical_blocks': (1, 8192), 'scatter_amount': (0, 1000)}
POINTS = {'center': (0, 1), 'tile_center': (-10, 10)}   # [x, y] frame fractions, keyframable
BOOLS = ('mirror_edges', 'horizontal_phase_shift', 'invert', 'sharp_colors', 'randomize_every_frame')


def _point(v, loc, lo, hi):
    if not isinstance(v, list) or len(v) != 2 or isinstance(v[0], list):
        raise ContractError(f'{loc}: expected [x, y] (fractions of the frame)')
    for c in v:
        number(c, loc, lo, hi)


def validate(name, p, where):
    """Check one effect's parameters; raise ContractError with the field path on a bad value."""
    from .local_fx import _displacement, _keyed
    for k, v in p.items():
        loc = f'{where}.{k}'
        if k in CHOICES:
            if v not in CHOICES[k]:
                raise ContractError(f'{loc}: one of {", ".join(CHOICES[k])}')
        elif k in KEYED:
            _keyed(v, loc, *KEYED[k])
        elif k in POINTS:
            if isinstance(v, list) and v and isinstance(v[0], list):
                for i, key in enumerate(v):   # check the points first: _keyed's own message speaks of px at 1080
                    if isinstance(key, list) and len(key) in (2, 3):
                        _point(key[1], f'{loc}[{i}][1]', *POINTS[k])
                _keyed(v, loc, *POINTS[k], point=True)
            else:
                _point(v, loc, *POINTS[k])
        elif k in BOOLS:
            if not isinstance(v, bool):
                raise ContractError(f'{loc}: expected boolean')
        elif k == 'seed':
            number(v, loc, -1e9, 1e9, integer=True)
        elif k == 'at':
            number(v, loc, 0, 3600)
        elif not _displacement(k, v, loc):   # edges, quality, region, feather
            raise ContractError(f'{loc}: unsupported field')
