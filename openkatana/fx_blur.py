"""After Effects' Blur & Sharpen effects (web/fx_blur.js): validation of the pack's timeline fields."""
from .contracts import ContractError, number

_REGION = 'region feather at'
# effect name -> its fields, space separated (unknown fields are rejected before validate runs)
SPECS = {
    'local_gaussian_blur': f'blurriness dimensions repeat_edge_pixels {_REGION}',
    'local_directional_blur': f'direction blur_length {_REGION}',
    'local_radial_blur': f'amount center type quality {_REGION}',
    'local_camera_lens_blur': 'blur_radius iris_shape iris_rotation iris_roundness highlight_gain highlight_threshold map clip src '
                              f'speed loop focal_distance invert center {_REGION}',
    'local_unsharp_mask': f'amount radius threshold {_REGION}',
    'local_channel_blur': f'red_blurriness green_blurriness blue_blurriness dimensions repeat_edge_pixels {_REGION}',
    'local_tilt_shift': 'center angle band feather blur_radius saturation at',
}
IRIS = ('triangle', 'square', 'pentagon', 'hexagon', 'heptagon', 'octagon', 'nonagon', 'decagon')
CHOICES = {
    'dimensions': ('both', 'horizontal', 'vertical'),
    'type': ('spin', 'zoom'),
    'quality': ('low', 'high'),
    'iris_shape': IRIS,
    'map': ('horizontal', 'vertical', 'radial', 'clip'),
}
# fields that take keyframes, with the range of their values; (effect, field) entries override a field's range
KEYED = {'blurriness': (0, 1000), 'red_blurriness': (0, 1000), 'green_blurriness': (0, 1000), 'blue_blurriness': (0, 1000),
         'blur_length': (0, 1000), 'direction': (-36000, 36000), 'blur_radius': (0, 500), 'radius': (0, 250),
         'angle': (-36000, 36000), 'band': (0, 1), 'saturation': (0, 4)}
KEYED_BY_EFFECT = {('local_radial_blur', 'amount'): (0, 100), ('local_unsharp_mask', 'amount'): (0, 500)}
RANGES = {'iris_rotation': (-36000, 36000), 'iris_roundness': (0, 100), 'highlight_gain': (0, 100),
          'highlight_threshold': (0, 255), 'focal_distance': (0, 255), 'threshold': (0, 255), 'at': (0, 3600)}
BOOLS = ('repeat_edge_pixels', 'invert')


def _point(v, loc):
    if not isinstance(v, list) or len(v) != 2 or isinstance(v[0], list):
        raise ContractError(f'{loc}: expected [x, y] (fractions of the frame, 0..1)')
    for c in v:
        number(c, loc, 0, 1)


def _center(v, loc, scalar_ok):
    """[x, y] (0..1), or for tilt-shift also a y fraction; either may be keyframed."""
    from .local_fx import _keyed
    if isinstance(v, list) and v and isinstance(v[0], list):
        points = any(isinstance(key, list) and len(key) in (2, 3) and isinstance(key[1], list) for key in v)
        if points:
            for i, key in enumerate(v):   # check the points first: _keyed's own message speaks of px at 1080
                if isinstance(key, list) and len(key) in (2, 3):
                    _point(key[1], f'{loc}[{i}][1]')
            return _keyed(v, loc, 0, 1, point=True)
        if not scalar_ok:
            raise ContractError(f'{loc}: expected [x, y] keyframes (fractions of the frame, 0..1)')
        return _keyed(v, loc, 0, 1)
    if scalar_ok and not isinstance(v, list):
        return number(v, loc, 0, 1)
    _point(v, loc)


def validate(name, p, where):
    """Check one effect's parameters; raise ContractError with the field path on a bad value."""
    from .local_fx import _displacement, _keyed
    for k, v in p.items():
        loc = f'{where}.{k}'
        if k in CHOICES:
            if v not in CHOICES[k]:
                raise ContractError(f'{loc}: one of {", ".join(CHOICES[k])}')
        elif (name, k) in KEYED_BY_EFFECT:
            _keyed(v, loc, *KEYED_BY_EFFECT[name, k])
        elif k in KEYED:
            _keyed(v, loc, *KEYED[k])
        elif k == 'center':
            _center(v, loc, name == 'local_tilt_shift')
        elif k in BOOLS:
            if not isinstance(v, bool):
                raise ContractError(f'{loc}: expected boolean')
        elif k in RANGES:
            number(v, loc, *RANGES[k])
        elif k == 'feather' and name == 'local_tilt_shift':
            number(v, loc, 0, 1)
        elif k in ('clip', 'src', 'speed', 'loop', 'region', 'feather'):
            _displacement(k, v, loc)
        else:
            raise ContractError(f'{loc}: unsupported field')
    if name == 'local_camera_lens_blur':
        if p.get('map') == 'clip' and 'clip' not in p:
            raise ContractError(f'{where}: map "clip" needs clip (the id of the map clip in clips)')
        if 'clip' in p and p.get('map', 'clip') != 'clip':
            raise ContractError(f'{where}: clip is the blur map; it goes with map "clip"')
        extra = [k for k in ('src', 'speed', 'loop') if k in p]
        if extra and 'clip' not in p:
            raise ContractError(f'{where}: {", ".join(extra)} set where the map clip plays; they need clip')
        extra = [k for k in ('focal_distance', 'invert') if k in p]
        if extra and 'map' not in p and 'clip' not in p:
            raise ContractError(f'{where}: {", ".join(extra)} shape the blur map; set map (or clip)')
        if 'center' in p and p.get('map') != 'radial':
            raise ContractError(f'{where}: center is the radial blur map\'s centre; it goes with map "radial"')
