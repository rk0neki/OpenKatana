"""Timeline overlays: layers stacked over the finished frame, above every shot, transition, special, text event and
shot layer, drawn in array order (web/engine.js drawOverlays; docs/TIMELINE.md "Overlays").

  {"type": "clip", "clip": id, "f0", "f1", "src" | "srcf", "speed", "fps", "loop", "blend", "opacity", "floor", "tint",
   "fit"}   another clip blended over the picture: texture plates (dust, film scratches, grain, light leaks)
  {"type": "adjust", "f0", "f1", "look", "amt"}
           an adjustment layer: a look applied to everything beneath it, mixed back at `amt`

`opacity` and `amt` are a number or keyframes [[frame, value], ...] (absolute output frames, increasing, linear between
keys, held before the first and after the last)."""
from .contracts import ContractError, color, fields, number

BLENDS = ('normal', 'screen', 'add', 'multiply', 'overlay', 'soft-light', 'hard-light', 'lighten', 'darken',
          'color-dodge', 'color-burn', 'difference', 'exclusion')
FITS = ('cover', 'contain', 'stretch')
LOOPS = ('loop', 'pingpong', 'clamp')
MAX_OVERLAYS = 64


def keyframes(value, where, frames):
    """A number in 0..1, or [[frame, value], ...] with increasing absolute frames."""
    if not isinstance(value, list):
        return number(value, where, 0, 1)
    if not 1 <= len(value) <= 1000:
        raise ContractError(f'{where}: 1..1000 keyframes')
    last = None
    for i, key in enumerate(value):
        if not isinstance(key, list) or len(key) != 2:
            raise ContractError(f'{where}[{i}]: a keyframe is [frame, value]')
        number(key[0], f'{where}[{i}][0]', 0, frames, integer=True)
        number(key[1], f'{where}[{i}][1]', 0, 1)
        if last is not None and key[0] <= last:
            raise ContractError(f'{where}: keyframe frames must increase')
        last = key[0]


def validate(edit, clips, frames):
    items = edit.get('overlays', [])
    if not isinstance(items, list):
        raise ContractError('overlays: expected an array')
    if len(items) > MAX_OVERLAYS:
        raise ContractError(f'overlays: at most {MAX_OVERLAYS} layers')
    from .expanded import look
    for i, o in enumerate(items):
        where = f'overlays[{i}]'
        if not isinstance(o, dict) or o.get('type') not in ('clip', 'adjust'):
            raise ContractError(f'{where}: type "clip" or "adjust"')
        if o['type'] == 'clip':
            fields(o, 'type clip f0 f1 src srcf speed fps loop blend opacity floor tint fit', where)
        else:
            fields(o, 'type f0 f1 look amt', where)
        for k in ('f0', 'f1'):
            if k not in o:
                raise ContractError(f'{where}: f0 and f1 (or t0 and t1) are required')
        number(o['f0'], where + '.f0', 0, frames - 1, integer=True)
        number(o['f1'], where + '.f1', o['f0'] + 1, frames, integer=True)
        if o['type'] == 'adjust':
            if 'look' not in o:
                raise ContractError(f'{where}: an adjustment layer needs a look')
            look(o['look'], where + '.look')
            if o['look'] in (None, 'none', 'clean'):
                raise ContractError(f'{where}.look: an adjustment layer needs a look that changes the picture')
            if 'amt' in o:
                keyframes(o['amt'], where + '.amt', frames)
            continue
        if o.get('clip') not in clips:
            raise ContractError(f'{where}.clip: a clip id from clips')
        if 'src' in o and 'srcf' in o:
            raise ContractError(f'{where}: use src or srcf, not both')
        if 'src' in o:
            number(o['src'], where + '.src', 0, 86400)
        if 'srcf' in o:
            number(o['srcf'], where + '.srcf', 0, 10 ** 7)
        if 'speed' in o:
            number(o['speed'], where + '.speed', 0, 100)
        if 'fps' in o:
            number(o['fps'], where + '.fps', 1, 240)
        if o.get('loop', 'loop') not in LOOPS:
            raise ContractError(f'{where}.loop: {", ".join(LOOPS)}')
        if o.get('blend', 'screen') not in BLENDS:
            raise ContractError(f'{where}.blend: {", ".join(BLENDS)}')
        if o.get('fit', 'cover') not in FITS:
            raise ContractError(f'{where}.fit: {", ".join(FITS)}')
        if 'opacity' in o:
            keyframes(o['opacity'], where + '.opacity', frames)
        if 'floor' in o:
            number(o['floor'], where + '.floor', 0, .9)
        if 'tint' in o:
            color(o['tint'], where + '.tint')
