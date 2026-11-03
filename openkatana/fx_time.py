"""After Effects' Time effects (web/fx_time.js): validation of the pack's timeline fields."""
from .contracts import ContractError, number

# effect name -> its fields, space separated (unknown fields are rejected before validate runs)
SPECS = {
    'local_echo': 'echo_time number_of_echoes starting_intensity decay operator at',
    'local_time_displacement': 'map clip src speed loop max_displacement levels invert center at',
    'local_posterize_time': 'fps at',
    'local_frame_blend': 'samples shutter at',
}
OPERATORS = ('add', 'maximum', 'minimum', 'screen', 'composite_back', 'composite_front', 'blend')
MAPS = ('horizontal', 'vertical', 'radial', 'self', 'clip')
RANGES = {'echo_time': (-10, 10), 'number_of_echoes': (1, 16), 'starting_intensity': (0, 1), 'decay': (0, 1),
          'levels': (2, 16), 'fps': (1, 60), 'samples': (2, 16), 'shutter': (0, 1), 'at': (0, 3600)}
INTEGER = ('number_of_echoes', 'levels', 'samples')


def validate(name, p, where):
    """Check one effect's parameters; raise ContractError with the field path on a bad value."""
    from .local_fx import _displacement, _keyed
    for k, v in p.items():
        loc = f'{where}.{k}'
        if k == 'operator':
            if v not in OPERATORS:
                raise ContractError(f'{loc}: one of {", ".join(OPERATORS)}')
        elif k == 'map':
            if v not in MAPS:
                raise ContractError(f'{loc}: one of {", ".join(MAPS)}')
        elif k == 'max_displacement':
            _keyed(v, loc, 0, 60)
        elif k == 'invert':
            if not isinstance(v, bool):
                raise ContractError(f'{loc}: expected boolean')
        elif k == 'center':
            if not isinstance(v, list) or len(v) != 2:
                raise ContractError(f'{loc}: expected [x, y] (0..1)')
            for x in v:
                number(x, loc, 0, 1)
        elif k in ('clip', 'src', 'speed', 'loop'):
            _displacement(k, v, loc)
        else:
            number(v, loc, *RANGES[k], integer=k in INTEGER)
    if name == 'local_time_displacement':
        if p.get('map') == 'clip' and 'clip' not in p:
            raise ContractError(f'{where}: map "clip" needs clip (the id of the map clip in clips)')
        if 'clip' in p and p.get('map', 'clip') != 'clip':
            raise ContractError(f'{where}: clip is the map clip; it goes with map "clip"')
