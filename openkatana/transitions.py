"""Two-shot transitions (audit F-STU-002): the outgoing shot A and incoming shot B are both rendered through their full
pipelines inside a frame window around the cut and composited by the renderer (`web/transitions.js`).

Timeline form, on the INCOMING shot (index >= 1):
    "transition": {"type": "dissolve", "d": 0.5, "align": "center", ...type parameters}
A keeps playing past its f1 and B pre-rolls before its f0 using their own timing (handles; clamp/loop rules apply).
Global text is drawn above the composite on transition frames (it does not move with pushes/slides).
"""
import math
from .contracts import ContractError, color, fields, number

EASES = ('linear', 'inQuad', 'outQuad', 'inOutQuad', 'inCubic', 'outCubic', 'inOutCubic', 'inExpo', 'outExpo', 'inOutExpo', 'inOutSine')
DIRS = ('left', 'right', 'up', 'down')
# type: (default seconds, {param: default}, {param: choices}); a tuple default means [min, max] numeric range check
SPECS = {
    'dissolve': (.5, {'curve': 'linear'}, {'curve': EASES}),
    'fade': (.52, {'color': '#000000', 'out': .24, 'hold': 0, 'in': .28, 'mode': 'dip'}, {'mode': ('dip', 'in', 'out')}),
    'dip': (.44, {'color': '#000000', 'out': .16, 'hold': .04, 'in': .24, 'mode': 'dip'}, {'mode': ('dip', 'in', 'out')}),
    'flash': (None, {'color': '#ffffff', 'mode': 'solid', 'pre_frames': 0, 'pre': [.35, .65], 'peak_frames': 1, 'tau': .06, 'cutoff': .05},
              {'mode': ('solid', 'add', 'screen', 'exposure', 'black', 'invert')}),
    'glitch': (.3, {'streaks': 'vertical', 'split': .5, 'intensity': .8, 'seed': 0}, {'streaks': ('vertical', 'horizontal')}),
    'lens': (.43, {'mode': 'bulge', 'split': .46, 'strength': .6, 'center': [.5, .5], 'radius': 1.0, 'chroma': .04, 'vignette': .25},
             {'mode': ('bulge', 'pinch', 'twirl', 'barrel', 'pincushion')}),
    'light_leak': (.7, {'anchor': 'right', 'palette': 'amber', 'peak': 1.3, 'size': .95, 'blend': 'add', 'split': .45, 'seed': 0},
                   {'anchor': ('left', 'right', 'top', 'bottom', 'center'), 'palette': ('amber', 'rose', 'teal', 'white'), 'blend': ('add', 'screen')}),
    'liquid': (.6, {'mode': 'blob', 'wobble': .04, 'rim_width': .015, 'rim_glow': .7, 'rim_color': '#ffd9a0', 'softness': .06, 'ease': 'outCubic', 'seed': 0},
               {'mode': ('blob', 'melt'), 'ease': EASES}),
    'luma': (.6, {'source': 'A', 'order': 'dark_first', 'softness': .08, 'noise': .15, 'seed': 0}, {'source': ('A', 'B', 'noise'), 'order': ('dark_first', 'light_first')}),
    'pixel_sort': (.37, {'axis': 'y', 'dir': 'down', 'mask': 'bright', 'split': .5, 'work_res': 540}, {'axis': ('x', 'y'), 'dir': ('down', 'up'), 'mask': ('bright', 'dark', 'all')}),
    'push': (.4, {'dir': 'left', 'ease': 'inOutCubic', 'shutter': .5, 'divider_width': 0, 'divider_color': '#000000'}, {'dir': DIRS, 'ease': EASES}),
    'slide': (.4, {'dir': 'left', 'ease': 'inOutCubic', 'shutter': .5, 'reveal': False}, {'dir': DIRS, 'ease': EASES}),
    'spin': (.5, {'dir': 'cw', 'out_angle': 120, 'in_angle': -120, 'scale': 1.4, 'center': [.5, .5], 'split': .4, 'shutter': .75}, {'dir': ('cw', 'ccw')}),
    'whip': (.3, {'dir': 'right', 'split': .5, 'travel': 1.2, 'shutter': .7, 'blur_max': .4}, {'dir': DIRS}),
    'wipe': (.5, {'shape': 'linear', 'dir': 'rtl', 'feather': .02, 'ease': 'inOutCubic', 'mode': 'open', 'center': [.5, .5], 'count': 7, 'stagger': .5},
             {'shape': ('linear', 'circle', 'diamond', 'box', 'star', 'clock', 'barn', 'strips'), 'dir': ('rtl', 'ltr', 'ttb', 'btt'), 'mode': ('open', 'close'), 'ease': EASES}),
    'zoom': (.4, {'mode': 'through', 'out_scale': 3.0, 'in_scale': .55, 'center': [.5, .5], 'split': .55, 'shutter': .5}, {'mode': ('through', 'punch')}),
    'datamosh': (.5, {'block': 16, 'drift': .08, 'split': .0, 'seed': 0}, {}),
}
NUMERIC = {'out': (0, 10), 'hold': (0, 10), 'in': (0, 10), 'pre_frames': (0, 60), 'peak_frames': (0, 30), 'tau': (.001, 5), 'cutoff': (.0001, .99),
           'split': (0, 1), 'intensity': (0, 2), 'seed': (0, 2 ** 31), 'strength': (0, 3), 'radius': (.05, 4), 'chroma': (0, .5), 'vignette': (0, 1),
           'peak': (0, 4), 'size': (.05, 4), 'wobble': (0, .5), 'rim_width': (0, .2), 'rim_glow': (0, 2), 'softness': (0, 1), 'noise': (0, 1),
           'work_res': (64, 2160), 'shutter': (0, 1), 'divider_width': (0, .2), 'out_angle': (-1080, 1080), 'in_angle': (-1080, 1080), 'scale': (.05, 10),
           'travel': (0, 5), 'blur_max': (0, 2), 'feather': (0, .5), 'count': (1, 64), 'stagger': (0, 1), 'out_scale': (.05, 20), 'in_scale': (.05, 20),
           'block': (2, 256), 'drift': (0, 1)}
INTEGER = {'pre_frames', 'peak_frames', 'seed', 'work_res', 'count', 'block'}
COLORS = {'color', 'rim_color', 'divider_color'}


def catalog():
    """Machine-readable vocabulary for agents: default seconds, parameter defaults, choices and numeric ranges."""
    return {kind: {'d': d, 'params': params, 'choices': {k: list(v) for k, v in choices.items()},
                   'ranges': {k: list(NUMERIC[k]) for k in params if k in NUMERIC}} for kind, (d, params, choices) in SPECS.items()}


def frame_window(spec, cut, fps):
    """[w0, w1) output frames of a transition whose incoming shot starts at `cut` (shared rule with web/transitions.js)."""
    kind = spec['type']
    if kind == 'flash':
        p = {**SPECS['flash'][1], **spec}
        tail = max(1, math.ceil(p['tau'] * math.log(1 / p['cutoff']) * fps - 1e-9))
        return cut - p['pre_frames'], cut + p['peak_frames'] + tail
    n = max(2, math.floor(spec.get('d', SPECS[kind][0]) * fps + .5))   # same rounding as Math.round in JS
    align = spec.get('align', 'center')
    w0 = cut - n // 2 if align == 'center' else cut if align == 'start' else cut - n
    return w0, w0 + n


def validate_transition(spec, where):
    if not isinstance(spec, dict) or spec.get('type') not in SPECS:
        raise ContractError(f'{where}: transition needs a type: {", ".join(SPECS)}')
    kind = spec['type']; defaults, choices = SPECS[kind][1], SPECS[kind][2]
    fields(spec, 'type d align ' + ' '.join(defaults), where)
    if 'd' in spec:
        if kind == 'flash':
            raise ContractError(f'{where}: flash timing uses pre_frames/peak_frames/tau/cutoff, not d')
        number(spec['d'], where + '.d', .02, 10)
    if spec.get('align', 'center') not in ('center', 'start', 'end'):
        raise ContractError(f'{where}.align: use center, start or end')
    for k, v in spec.items():
        if k in ('type', 'd', 'align'):
            continue
        loc = f'{where}.{k}'
        if k in choices:
            if v not in choices[k]:
                raise ContractError(f'{loc}: use one of {", ".join(choices[k])}')
        elif k in COLORS:
            color(v, loc)
        elif k == 'reveal':
            if not isinstance(v, bool):
                raise ContractError(f'{loc}: expected boolean')
        elif k == 'center':
            if not isinstance(v, list) or len(v) != 2:
                raise ContractError(f'{loc}: expected [x, y]')
            for c in v:
                number(c, loc, 0, 1)
        elif k == 'pre':
            if not isinstance(v, list) or len(v) != 2:
                raise ContractError(f'{loc}: expected [start, end] opacity')
            for c in v:
                number(c, loc, 0, 1)
        elif k in NUMERIC:
            lo, hi = NUMERIC[k]; number(v, loc, lo, hi, integer=k in INTEGER)
        else:
            raise ContractError(f'{loc}: unsupported value')


def validate_transitions(edit):
    """Check every shot transition: incoming shot >= 1, window inside A and B, windows do not overlap."""
    shots, fps = edit['shots'], edit['canvas']['fps']; previous_end = 0
    for i, shot in enumerate(shots):
        if 'transition' not in shot:
            continue
        where = f'shots[{i}].transition'
        if i == 0:
            raise ContractError(f'{where}: the first shot has no outgoing shot to transition from')
        validate_transition(shot['transition'], where)
        w0, w1 = frame_window(shot['transition'], shot['f0'], fps)
        a = shots[i - 1]
        if w0 < a['f0'] or w1 > shot['f1']:
            raise ContractError(f'{where}: window frames {w0}-{w1} must lie inside shots {i - 1} ({a["f0"]}-{a["f1"]}) and {i} ({shot["f0"]}-{shot["f1"]}); shorten d or change align')
        if w0 < previous_end:
            raise ContractError(f'{where}: window starts at frame {w0}, before the previous transition ends ({previous_end})')
        previous_end = w1
