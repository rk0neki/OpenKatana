"""Studio looks: grade and effect lists applied to a plate by web/studiofx.js, plus named presets."""
from .contracts import ContractError, color, fields, number

N = lambda lo, hi: ('num', lo, hi)
I = lambda lo, hi: ('int', lo, hi)
B = ('bool',)
C = ('color',)
V2 = ('vec', 2, 0, 1)
CH = lambda *v: ('choice', v)

GRADE = {'auto': N(0, 1), 'sat': N(0, 3), 'temp': N(-1, 1), 'tint': N(-1, 1), 'contrast': N(.2, 3), 'gamma': N(.2, 3),
         'black': N(0, .5), 'fade': N(0, .5), 'gain': N(.2, 2), 'mono': N(0, 1), 'exposure': N(-4, 4), 'mult': ('vec', 3, 0, 3)}
FX = {
    'bleach': {'a': N(0, 1)},
    'bloom': {'thr': N(0, 1), 'r': N(0, 400), 'strength': N(0, 2)},
    'blur': {'r': N(0, 200)},
    'chroma': {'px': N(0, 200), 'vertical': B},
    'clarity': {'amount': N(-1, 1), 'radius': N(.001, .2)},
    'contour_glow': {'color': C, 'radius': N(0, .2), 'strength': N(0, 2), 'inner': N(0, 1), 'blend': CH('screen', 'add')},
    'datamosh': {'block': N(2, 256), 'drift': N(0, 1), 'share': N(0, 1), 'seed': I(0, 2 ** 31)},
    'defocus': {'amount': N(0, .2), 'highlights': N(1, 5)},
    'dirblur': {'len': N(0, 1), 'angle': N(-360, 360)},
    'duotone': {'shadows': C, 'highlights': C, 'amount': N(0, 1)},
    'exposure': {'ev': N(-6, 6)},
    'film_overlay': {'level': I(1, 3), 'grain': N(0, .3), 'dust': I(0, 200), 'scratch': I(0, 10), 'flicker': N(0, .5), 'weave': N(0, 20), 'seed': I(0, 2 ** 31)},
    'glow': {'threshold': N(0, 1), 'knee': N(0, 1), 'radii': ('list', 1, 8, 0, .5), 'weights': ('list', 1, 8, 0, 1), 'strength': N(0, 3),
             'tint': C, 'blend': CH('screen', 'add')},
    'grain': {'sigma': N(0, .3), 'size': N(.5, 16), 'mono': B, 'seed': I(0, 2 ** 31)},
    'invert': {},
    'lens_warp': {'mode': CH('bulge', 'pinch', 'sphere', 'twirl', 'barrel', 'pincushion'), 'strength': N(0, 3), 'center': V2, 'radius': N(.05, 4),
                  'dir': CH('ccw', 'cw'), 'chroma': N(0, .5), 'vignette': N(0, 1)},
    'light_leak': {'anchor': CH('left', 'right', 'top', 'bottom', 'center', 'tl', 'tr', 'bl', 'br'), 'palette': CH('amber', 'magenta', 'gold', 'peach', 'cool'),
                   'peak': N(0, 1), 'size': N(.05, 2), 'blend': CH('screen', 'add'), 'seed': I(0, 2 ** 31)},
    'pixel_art': {'block': N(.001, .1), 'colors': I(2, 256), 'dither': CH('none', 'bayer4'), 'strength': N(0, 1)},
    'pixel_sort': {'mask': CH('bright', 'dark', 'full'), 'lo': N(0, 1), 'axis': CH('x', 'y'), 'dir': CH('down', 'up'), 'work_res': I(64, 2160)},
    'pixelate': {'size': N(.002, .5)},
    'posterize': {'levels': I(2, 64), 'mode': CH('rgb', 'luma')},
    'rgb_split': {'px': N(0, 200), 'angle': N(-360, 360)},
    'saturation': {'sat': N(-1, 3), 'hue': N(-360, 360)},
    'shake': {'px': N(0, 200), 'seed': I(0, 2 ** 31)},
    'smear': {'len': N(0, 1), 'angle': N(-360, 360), 'px': N(0, 200), 'sat': N(0, 4)},
    'tape': {'res': N(.05, 1), 'vres': N(.05, 1), 'chroma_shift': N(0, .05), 'depth': N(0, 1), 'noise': N(0, .5), 'head': N(0, .2), 'seed': I(0, 2 ** 31)},
    'vignette': {'amount': N(0, 1), 'feather': N(0, 1), 'center': V2},
    'zoomblur': {'amount': N(0, 1), 'cx': N(0, 1), 'cy': N(0, 1), 'n': I(2, 32)},
}
FX['glitch_blocks'] = FX['datamosh']

PRESETS = {
    'film_print': {'grade': {'auto': .3, 'sat': .9, 'temp': .12, 'contrast': 1.02, 'fade': .03, 'gain': .98, 'split': [[.46, .51, .52], [.54, .5, .47], .5]},
                   'fx': [{'type': 'glow', 'threshold': .8, 'strength': .1, 'tint': '#ff7a4a'}, {'type': 'film_overlay', 'level': 1}, {'type': 'grain', 'sigma': .018, 'size': 1.6}]},
    'home_tape': {'grade': {'auto': .5, 'sat': 1.3, 'mult': [1.06, 1, .95], 'contrast': 1.05, 'fade': .02, 'gain': .95}, 'fx': [{'type': 'tape'}]},
    'clean_luxe': {'grade': {'auto': .7, 'sat': .88, 'temp': .06, 'contrast': 1.15, 'black': .02, 'gain': .97, 'split': [[.48, .5, .53], [.53, .5, .47], .4]},
                   'fx': [{'type': 'glow', 'threshold': .8, 'strength': .15}, {'type': 'grain', 'sigma': .008, 'size': 1.2, 'mono': True}]},
    'dreamy_bloom': {'grade': {'auto': .4, 'sat': .9, 'temp': .1, 'tint': .06, 'contrast': .9, 'fade': .04, 'gain': .96},
                     'fx': [{'type': 'glow', 'threshold': .55, 'knee': .2, 'strength': .3, 'tint': '#ffd6e8'}, {'type': 'light_leak', 'anchor': 'tr', 'palette': 'peach', 'peak': .18, 'size': .25}]},
    'gritty_contrast': {'grade': {'auto': .8, 'sat': .65, 'tint': -.05, 'contrast': 1.35, 'black': .05, 'split': [[.42, .55, .53], [.54, .52, .46], .5]},
                        'fx': [{'type': 'clarity', 'amount': .45}, {'type': 'grain', 'sigma': .045, 'size': 2.2, 'mono': True}, {'type': 'vignette', 'amount': .45}]},
    'mono_noir': {'grade': {'mono': 1, 'auto': .85, 'contrast': 1.4, 'gamma': 1.05, 'black': .03},
                  'fx': [{'type': 'clarity', 'amount': .3}, {'type': 'grain', 'sigma': .035, 'size': 2.2, 'mono': True}, {'type': 'vignette', 'amount': .5}]},
    'neon_night': {'grade': {'auto': .6, 'sat': 1.2, 'temp': -.2, 'tint': .07, 'contrast': 1.15, 'black': .02, 'split': [[.45, .42, .65], [.6, .45, .56], .55]},
                   'fx': [{'type': 'glow', 'threshold': .6, 'strength': .35}, {'type': 'chroma', 'px': 3}]},
    'golden_hour': {'grade': {'auto': .5, 'sat': 1.08, 'temp': .32, 'contrast': 1.04, 'fade': .02, 'split': [[.5, .49, .5], [.58, .5, .4], .35]},
                    'fx': [{'type': 'light_leak', 'anchor': 'right', 'palette': 'gold', 'peak': .22, 'size': .3}, {'type': 'glow', 'threshold': .72, 'strength': .15, 'tint': '#ffb050'}]},
    'silver_bleach': {'grade': {'auto': .8, 'sat': .33, 'contrast': 1.28, 'temp': -.04, 'black': .03, 'gamma': .95},
                      'fx': [{'type': 'clarity', 'amount': .4}, {'type': 'grain', 'sigma': .02, 'size': 1.6, 'mono': True}]},
    'teal_orange': {'grade': {'auto': .6, 'sat': 1.18, 'temp': .04, 'tint': -.02, 'contrast': 1.14, 'black': .01, 'split': [[.3, .53, .6], [.66, .5, .36], .7]},
                    'fx': [{'type': 'glow', 'threshold': .8, 'strength': .15}]},
    'vivid_pop': {'grade': {'auto': .8, 'sat': 1.25, 'temp': .03, 'contrast': 1.12, 'gamma': .95, 'black': .01},
                  'fx': [{'type': 'clarity', 'amount': .28, 'radius': .015}, {'type': 'glow', 'threshold': .85, 'strength': .12}]},
    'pastel_fade': {'grade': {'auto': .4, 'sat': .72, 'temp': -.05, 'tint': .06, 'contrast': .88, 'fade': .07, 'gain': .98, 'gamma': .88},
                    'fx': [{'type': 'glow', 'threshold': .75, 'strength': .12}, {'type': 'grain', 'sigma': .008, 'size': 1.4}]},
    'cold_concrete': {'grade': {'auto': .7, 'sat': .3, 'temp': -.25, 'contrast': .96, 'black': .03, 'gain': .9, 'split': [[.47, .5, .55], [.5, .5, .52], .5]},
                      'fx': [{'type': 'grain', 'sigma': .015, 'size': 1.8, 'mono': True}, {'type': 'vignette', 'amount': .3}]},
}


def _value(spec, v, loc):
    kind = spec[0]
    if kind == 'num':
        number(v, loc, spec[1], spec[2])
    elif kind == 'int':
        number(v, loc, spec[1], spec[2], integer=True)
    elif kind == 'bool':
        if not isinstance(v, bool):
            raise ContractError(f'{loc}: expected boolean')
    elif kind == 'color':
        color(v, loc)
    elif kind == 'choice':
        if v not in spec[1]:
            raise ContractError(f'{loc}: use one of {", ".join(spec[1])}')
    elif kind == 'vec':
        if not isinstance(v, list) or len(v) != spec[1]:
            raise ContractError(f'{loc}: expected {spec[1]} numbers')
        for x in v:
            number(x, loc, spec[2], spec[3])
    elif kind == 'list':
        if not isinstance(v, list) or not spec[1] <= len(v) <= spec[2]:
            raise ContractError(f'{loc}: expected {spec[1]}..{spec[2]} numbers')
        for x in v:
            number(x, loc, spec[3], spec[4])


def validate_studio(look, where):
    fields(look, 'type grade fx', where)
    grade = look.get('grade', {})
    fields(grade, ' '.join(GRADE) + ' split', where + '.grade')
    for k, v in grade.items():
        if k == 'split':
            if not isinstance(v, list) or len(v) != 3:
                raise ContractError(f'{where}.grade.split: expected [[shadow r,g,b], [highlight r,g,b], strength] (0..1, 0.5 = neutral)')
            _value(('vec', 3, 0, 1), v[0], where + '.grade.split[0]'); _value(('vec', 3, 0, 1), v[1], where + '.grade.split[1]'); number(v[2], where + '.grade.split[2]', 0, 1)
        else:
            _value(GRADE[k], v, f'{where}.grade.{k}')
    items = look.get('fx', [])
    if not isinstance(items, list) or len(items) > 16:
        raise ContractError(f'{where}.fx: up to 16 effects')
    for i, item in enumerate(items):
        loc = f'{where}.fx[{i}]'
        if not isinstance(item, dict) or item.get('type') not in FX:
            raise ContractError(f'{loc}: effect type must be one of {", ".join(sorted(FX))}')
        spec = FX[item['type']]
        fields(item, 'type amt ' + ' '.join(spec), loc)
        if 'amt' in item:
            number(item['amt'], loc + '.amt', 0, 1)
        for k, v in item.items():
            if k in spec:
                _value(spec[k], v, f'{loc}.{k}')
    if 'weights' in next((x for x in items if x.get('type') == 'glow' and 'radii' in x), {}):
        g = next(x for x in items if x.get('type') == 'glow' and 'radii' in x)
        if len(g['weights']) != len(g['radii']):
            raise ContractError(f'{where}: glow weights and radii need the same length')


def catalog():
    return {'grade': {k: list(v[1:]) for k, v in GRADE.items()} | {'split': '[[r,g,b], [r,g,b], strength]'},
            'fx': {name: {k: list(v[1:]) if v[0] != 'choice' else list(v[1]) for k, v in spec.items()} for name, spec in FX.items()},
            'presets': sorted(PRESETS)}
