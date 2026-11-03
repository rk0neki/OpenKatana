"""After Effects' Distort effects (web/fx_distort.js): validation of the pack's timeline fields."""
from .contracts import ContractError, number

_COMMON = 'edges quality region feather at'
# effect name -> its fields, space separated (unknown fields are rejected before validate runs)
SPECS = {
    'local_wave_warp': f'wave_type wave_height wave_width direction wave_speed phase pinning {_COMMON}',
    'local_ripple': f'center radius wavelength amplitude wave_speed phase conversion {_COMMON}',
    'local_shockwave': f'center d ease max_radius width amount split {_COMMON}',
    'local_twirl': f'angle radius center {_COMMON}',
    'local_bulge': f'center horizontal_radius vertical_radius height taper pin {_COMMON}',
    'local_polar': f'interpolation conversion {_COMMON}',
    'local_kaleidoscope': f'center segments rotation size mirroring {_COMMON}',
    'local_mirror': f'reflection_center reflection_angle {_COMMON}',
}
WAVE_TYPES = ('sine', 'square', 'triangle', 'sawtooth', 'circle', 'semicircle', 'uncircle', 'noise', 'smooth_noise')
PINNINGS = ('none', 'all', 'center', 'top', 'bottom', 'left', 'right', 'horizontal', 'vertical')
CHOICES = {
    ('local_wave_warp', 'wave_type'): WAVE_TYPES,
    ('local_wave_warp', 'pinning'): PINNINGS,
    ('local_ripple', 'conversion'): ('asymmetric', 'symmetric'),
    ('local_polar', 'conversion'): ('rect_to_polar', 'polar_to_rect'),
    ('local_kaleidoscope', 'mirroring'): ('on', 'off'),
}
# fields that take keyframes, with the range of their values
KEYED = {'wave_height': (-1000, 1000), 'wave_width': (1, 10000), 'amplitude': (-1000, 1000), 'amount': (-1000, 1000),
         'angle': (-36000, 36000), 'height': (-4, 4), 'interpolation': (0, 1), 'rotation': (-36000, 36000),
         'reflection_angle': (-36000, 36000)}
POINTS = ('center', 'reflection_center')   # [x, y] (0..1), keyframable
RANGES = {'direction': (-3600, 3600), 'wave_speed': (-100, 100), 'phase': (-36000, 36000), 'radius': (.001, 4),
          'wavelength': (1, 10000), 'd': (.001, 60), 'max_radius': (.001, 4), 'width': (1, 4000), 'split': (0, 200),
          'horizontal_radius': (1, 20000), 'vertical_radius': (1, 20000), 'taper': (0, 1), 'segments': (2, 32),
          'size': (1, 20000)}


def _point(v, loc):
    if not isinstance(v, list) or len(v) != 2:
        raise ContractError(f'{loc}: expected [x, y] (0..1)')
    for c in v:
        number(c, loc, 0, 1)


def validate(name, p, where):
    """Check one effect's parameters; raise ContractError with the field path on a bad value."""
    from .local_fx import _displacement, _ease, _keyed
    for k, v in p.items():
        loc = f'{where}.{k}'
        if (name, k) in CHOICES:
            if v not in CHOICES[name, k]:
                raise ContractError(f'{loc}: one of {", ".join(CHOICES[name, k])}')
        elif k in KEYED:
            _keyed(v, loc, *KEYED[k])
        elif k in POINTS:
            if isinstance(v, list) and v and isinstance(v[0], list):
                _keyed(v, loc, 0, 1, point=True)
            else:
                _point(v, loc)
        elif k == 'ease':
            _ease(v, loc)
        elif k == 'pin':
            if not isinstance(v, bool):
                raise ContractError(f'{loc}: expected boolean')
        elif k in RANGES:
            number(v, loc, *RANGES[k], integer=k == 'segments')
        elif k == 'at':
            number(v, loc, 0, 3600)
        elif not _displacement(k, v, loc):   # edges, quality, region, feather
            raise ContractError(f'{loc}: unsupported field')
