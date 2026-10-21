"""Native timeline syntax (audit F-NAT-001/002/004/012): authoring forms that `normalize()` rewrites into the explicit
canonical contract before validation and rendering. The saved timeline keeps the author's form.

Forms (documented in docs/TIMELINE.md "Native syntax"):
  * times: seconds, "f<n>" frame starts, "b<n>" beats on the top-level `beat` grid {bpm, t0}; shots/text/specials
    accept t0/t1 in place of f0/f1 (a shot's t1 defaults to the next shot's start or the end);
  * colours: "#rrggbb", "rgb()/rgba()", [r,g,b(,a)] or "$name" from `palette` (documented defaults below);
  * looks: preset strings, type strings, {"preset": name, ...overrides} and names from a top-level `looks` table;
  * fx numbers: `"fx": {"tint": 0.4}` means {"v": 0.4};
  * clip keywords FLASH/WHITE/BLACK/COLLAGE mean the corresponding `special`;
  * shot `note` is free text (dropped); shot `seed` becomes the default `seed` of that shot's seeded effects.
"""
import copy
import math
import re

from .contracts import ContractError, fields, number

DEFAULT_PALETTE = {'ink': '#0b0b0b', 'accent': '#b6ff1f', 'accent2': '#6fd600', 'lav': '#c98be0',
                   'magenta': '#ff2bd6', 'magenta2': '#7a2bff'}
LOOK_PRESETS = {
    'clean': 'none', 'none': 'none',
    'x': {'type': 'xerox', 'key': True},
    'xl': {'type': 'xerox', 'key': True, 'black': 0, 'white': .5},
    'duo': {'type': 'duotone'},
    'neg': {'type': 'neg'},
    'kawaii': {'type': 'grade', 'filter': 'brightness(1.08) contrast(1.02) saturate(1.12)',
               'layers': [{'op': 'soft-light', 'color': 'rgba(255,160,210,0.24)'}, {'op': 'screen', 'color': 'rgba(255,240,248,0.03)'}]},
    'bw': {'type': 'filter', 'filter': 'grayscale(1) contrast(1.22) brightness(1.04)'},
}
from .studio_looks import PRESETS as _STUDIO_PRESETS
LOOK_PRESETS.update({name: {'type': 'studio', **value} for name, value in _STUDIO_PRESETS.items()})   # audit F-STU-003
LOOK_TYPES = ('grade', 'filter', 'levels', 'threshold', 'duotone', 'xerox', 'neg', 'posterize', 'studio')
CLIP_KEYWORDS = {'FLASH': 'flash', 'WHITE': 'white', 'BLACK': 'black', 'COLLAGE': 'collage'}
# keys whose values are colours wherever they appear (arrays are only colours under these keys)
COLOR_KEYS = {'color', 'color2', 'fill', 'stroke', 'ink', 'paper', 'bg', 'halo_color', 'echo', 'rim_color', 'divider_color',
              'dark', 'light', 'colors'}
SEEDED_FX = ('grain', 'dust', 'leak', 'glitch', 'wipe', 'particles', 'burst', 'handheld')
TIME_RE = re.compile(r'([fb])(-?\d+(?:\.\d+)?)')


# Named camera moves (audit F-STU-003): Studio move names map onto OpenKatana camera keys; values are OpenKatana's own.
EASE_NAMES = {'linear': 'lin', 'lin': 'lin', 'inQuad': 'in2', 'outQuad': 'out2', 'inOutQuad': 'inout', 'inCubic': 'in3',
              'outCubic': 'out3', 'inOutCubic': 'inout3', 'outBack': 'outback'}
HANDHELD_PROFILES = {'calm': {'amp': 4, 'hz': .45, 'rot': .003}, 'walk': {'amp': 9, 'hz': 1.1, 'rot': .007},
                     'chaos': {'amp': 22, 'hz': 2.2, 'rot': .016}}
SHAKE_PROFILES = {'impact': 18, 'heavy': 30, 'micro': 6}
MOVE_FIELDS = {'zoom.crash': 'scale dur at ease center blur_shutter', 'zoom.punch': 'times scale mode release center blur_shutter',
               'zoom.in_out': 'times scale center blur_shutter', 'shake.beat': 'times profile amp blur_shutter',
               'drift': 'dx dy zoom rot ease blur_shutter'}


def frame_of(seconds, fps):
    """First output frame whose centre (f + 0.5) / fps is at or after `seconds`. Text at
    t0 = 2.3 frames starts on frame 2, at 2.7 on frame 3; shot and special boundaries follow the same rule."""
    return math.ceil(seconds * fps - .5 - 1e-9)


class Normalizer:
    def __init__(self, edit):
        canvas = edit.get('canvas') if isinstance(edit.get('canvas'), dict) else {}
        self.fps = canvas.get('fps', 30) if isinstance(canvas.get('fps'), (int, float)) and canvas.get('fps') > 0 else 30
        beat = edit.get('beat')
        if beat is not None:
            fields(beat, 'bpm t0', 'beat'); number(beat.get('bpm'), 'beat.bpm', 1, 1000); number(beat.get('t0', 0), 'beat.t0', -3600, 3600)
        self.beat = beat
        palette = edit.get('palette', {})
        if not isinstance(palette, dict):
            raise ContractError('palette: expected {name: colour}')
        self.palette = dict(DEFAULT_PALETTE)
        for name, value in palette.items():
            if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,40}', name):
                raise ContractError(f'palette: invalid name {name!r}')
            self.palette[name] = self.colour(value, f'palette.{name}', allow_ref=False)
        looks = edit.get('looks', {})
        if not isinstance(looks, dict):
            raise ContractError('looks: expected {name: look}')
        self.looks = looks

    # -- times --------------------------------------------------------------
    def seconds(self, value, where):
        if isinstance(value, bool):
            raise ContractError(f'{where}: expected seconds, "f<n>" or "b<n>"')
        if isinstance(value, (int, float)):
            return number(value, where, -36000, 36000)
        m = TIME_RE.fullmatch(value) if isinstance(value, str) else None
        if not m:
            raise ContractError(f'{where}: expected seconds, "f<n>" or "b<n>"')
        n = float(m.group(2))
        if m.group(1) == 'f':
            return n / self.fps
        if not self.beat:
            raise ContractError(f'{where}: "b<n>" times need a top-level beat {{"bpm", "t0"}}')
        return self.beat.get('t0', 0) + n * 60 / self.beat['bpm']

    def frame(self, value, where):
        return frame_of(self.seconds(value, where), self.fps)

    def span(self, item, where, default_end=None):
        """Replace t0/t1 (or n / d) with f0/f1 on a timed item."""
        if 't0' in item or 't1' in item:
            for k in ('f0', 'f1'):
                if k in item:
                    raise ContractError(f'{where}: use t0/t1 or f0/f1, not both')
            item['f0'] = self.frame(item.pop('t0'), where + '.t0') if 't0' in item else item.get('f0')
            if 't1' in item:
                item['f1'] = self.frame(item.pop('t1'), where + '.t1')
            elif default_end is not None:
                item['f1'] = default_end
        return item

    # -- colours ------------------------------------------------------------
    def colour(self, value, where, allow_ref=True):
        if isinstance(value, str) and value.startswith('$') and allow_ref:
            name = value[1:]
            if name not in self.palette:
                raise ContractError(f'{where}: unknown palette colour {value} (have: {", ".join(sorted(self.palette))})')
            return self.palette[name]
        rgba = None
        if isinstance(value, str):
            if re.fullmatch(r'#[0-9a-fA-F]{6}', value):
                return value.lower()
            m = re.fullmatch(r'rgba?\(\s*([^)]*)\)', value.strip())
            if m:
                parts = [p.strip() for p in m.group(1).split(',')]
                try:
                    rgba = [float(p) for p in parts]
                except ValueError:
                    rgba = None
        elif isinstance(value, list) and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value):
            rgba = [float(v) for v in value]
        if rgba is None or len(rgba) not in (3, 4) or any(not 0 <= v <= 255 for v in rgba[:3]) or (len(rgba) == 4 and not 0 <= rgba[3] <= 1):
            raise ContractError(f'{where}: use "#rrggbb", "rgb()/rgba()", [r,g,b(,a)] or a "$palette" name')
        r, g, b = (int(round(v)) for v in rgba[:3])
        if len(rgba) == 4 and rgba[3] < 1:
            return f'rgba({r},{g},{b},{rgba[3]:g})'
        return f'#{r:02x}{g:02x}{b:02x}'

    def colours(self, value, where, key=None):
        """Resolve "$name" anywhere and colour syntaxes under colour keys, recursively."""
        if isinstance(value, dict):
            return {k: self.colours(v, f'{where}.{k}', k) for k, v in value.items()}
        if key in COLOR_KEYS:
            if key == 'colors' and isinstance(value, list):
                return [self.colour(v, f'{where}[{i}]') for i, v in enumerate(value)]
            if value is None or isinstance(value, bool):
                return value
            return self.colour(value, where)
        if isinstance(value, list):
            return [self.colours(v, f'{where}[{i}]') for i, v in enumerate(value)]
        if isinstance(value, str) and value.startswith('$'):
            return self.colour(value, where)
        return value

    # -- looks --------------------------------------------------------------
    def look(self, value, where, seen=()):
        if value is None:
            return None
        if isinstance(value, str):
            if value in self.looks:
                if value in seen:
                    raise ContractError(f'{where}: looks {value!r} refers to itself')
                return self.look(self.looks[value], f'looks.{value}', seen + (value,))
            if value in LOOK_PRESETS:
                preset = copy.deepcopy(LOOK_PRESETS[value])
                return self.look(preset, where, seen) if isinstance(preset, dict) else preset
            if value in LOOK_TYPES:
                return self.look({'type': value}, where, seen)
            raise ContractError(f'{where}: unknown look {value!r} (presets: {", ".join(LOOK_PRESETS)}; types: {", ".join(LOOK_TYPES)})')
        if isinstance(value, dict) and value.get('type') == 'filter' and 'v' in value and 'filter' not in value:
            value = {**{k: v for k, v in value.items() if k != 'v'}, 'filter': value['v']}   # Short-form alias
        if isinstance(value, dict) and value.get('type') == 'duotone' and 'paper' not in value:
            value = {**value, 'paper': self.palette['accent']}   # documented default: paper $accent
        if isinstance(value, dict) and 'preset' in value:
            base = self.look(value['preset'], where + '.preset', seen)
            if base == 'none':
                raise ContractError(f'{where}: preset {value["preset"]!r} takes no parameters')
            rest = {k: v for k, v in value.items() if k != 'preset'}
            if 'type' in rest and rest['type'] != base.get('type'):
                raise ContractError(f'{where}: preset {value["preset"]!r} is a {base.get("type")} look')
            return self.look({**base, **rest}, where, seen)
        return value

    # -- named camera moves ---------------------------------------------------
    def ease_name(self, value, where):
        if value not in EASE_NAMES:
            raise ContractError(f'{where}: use one of {", ".join(EASE_NAMES)}')
        return EASE_NAMES[value]

    def event_times(self, spec, span, where):
        """Shot-relative seconds for "beats", "downbeats", "1/2", "1/8", "offbeat", "snare" or a list of absolute times."""
        s0, s1 = span
        if isinstance(spec, list):
            return [round(self.seconds(t, where) - s0, 4) for t in spec if s0 <= self.seconds(t, where) < s1]
        if not self.beat:
            raise ContractError(f'{where}: "{spec}" needs a top-level beat {{"bpm", "t0"}} (analyze_audio gives bpm and phase)')
        P = 60 / self.beat['bpm']; t0 = self.beat.get('t0', 0)
        step, offset, pick = {'beats': (1, 0, None), 'downbeats': (1, 0, (0,)), '1/2': (2, 0, None), '1/8': (.5, 0, None),
                              'offbeat': (1, .5, None), 'snare': (1, 0, (1, 3))}.get(spec, (None, None, None))
        if step is None:
            raise ContractError(f'{where}: times use beats, downbeats, 1/2, 1/8, offbeat, snare or a list of seconds')
        out, k = [], math.ceil((s0 - t0) / (P * step) - offset - 1e-9) - 1
        while True:
            t = t0 + (k + offset) * P * step
            if t >= s1 - 1e-9:
                break
            if t >= s0 - 1e-9 and (pick is None or round(k * step) % 4 in pick):
                out.append(round(t - s0, 4))
            k += 1
        return out

    def camera_moves(self, cam, span, where):
        if not isinstance(cam, dict):
            return cam
        cam = dict(cam)
        def shutter(spec, default=.5):
            if 'shutter' not in cam:
                cam['shutter'] = number(spec.get('blur_shutter', default), where + '.blur_shutter', 0, 1)
        for name in [k for k in cam if k in MOVE_FIELDS]:
            spec = cam.pop(name); loc = f'{where}.{name}'
            spec = {} if spec is True else spec
            fields(spec, MOVE_FIELDS[name], loc)
            if span is None and ('times' in spec or name in ('zoom.punch', 'zoom.in_out', 'shake.beat', 'drift')):
                raise ContractError(f'{loc}: put this move on a shot camera (it is timed within the shot)')
            if name == 'zoom.crash':
                at = spec.get('at'); d = spec.get('dur', .4)
                cam['crash'] = {'v': spec.get('scale', 4), 'd': d, 'at': round(self.seconds(at, loc + '.at') - span[0], 4) if at is not None and span else d,
                                'ease': self.ease_name(spec.get('ease', 'inOutCubic'), loc + '.ease'), **({'center': spec['center']} if 'center' in spec else {})}
                shutter(spec)
            elif name == 'zoom.punch':
                if spec.get('mode', 'bounce') != 'bounce':
                    raise ContractError(f'{loc}.mode: only bounce is available in OpenKatana')
                if spec.get('center', [.5, .5]) != [.5, .5]:
                    raise ContractError(f'{loc}.center: punches zoom about the frame centre in OpenKatana')
                hits = self.event_times(spec.get('times', 'beats'), span, loc + '.times')
                if hits:
                    cam['punch'] = {'hits': hits, 'v': round(spec.get('scale', 1.2) - 1, 4), 'd': spec.get('release', .32), 'curve': 2}
                shutter(spec)
            elif name == 'zoom.in_out':
                hits = self.event_times(spec.get('times', 'beats'), span, loc + '.times')
                d = 60 / self.beat['bpm'] if self.beat else .25
                if hits:
                    cam['pulse'] = {'hits': hits, 'v': round(spec.get('scale', 1.3) - 1, 4), 'd': round(d, 4), **({'center': spec['center']} if 'center' in spec else {})}
                if 'blur_shutter' in spec:
                    shutter(spec)
            elif name == 'shake.beat':
                profile = spec.get('profile', 'impact')
                if profile not in SHAKE_PROFILES:
                    raise ContractError(f'{loc}.profile: use {", ".join(SHAKE_PROFILES)}')
                a = spec.get('amp', SHAKE_PROFILES[profile])
                hits = self.event_times(spec.get('times', 'beats'), span, loc + '.times')
                if hits:
                    cam['shake'] = {'hits': hits, 'd': .12, 'amp': [a, round(a * .75, 3)]}
                shutter(spec)
            elif name == 'drift':
                dur = max(1e-3, span[1] - span[0]); e = self.ease_name(spec.get('ease', 'linear'), loc + '.ease')
                if spec.get('dx') or spec.get('dy'):
                    cam['pan'] = {'dx': round(spec.get('dx', 0) / dur, 5), 'dy': round(spec.get('dy', 0) / dur, 5)}
                if spec.get('zoom', 1) != 1:
                    cam['zoom'] = {'z0': 1, 'z1': spec['zoom'], 'ease': e}
                if spec.get('rot'):
                    cam['roll'] = {'from': 0, 'to': round(math.radians(spec['rot']), 5), 'ease': e}
                cam['cover'] = True   # a digital move never reveals the plate edge
                shutter(spec, 0)
        hh = cam.get('handheld')
        if isinstance(hh, dict) and ('profile' in hh or 'blur_shutter' in hh):
            hh = dict(hh); profile = hh.pop('profile', None)
            if profile is not None and profile not in HANDHELD_PROFILES:
                raise ContractError(f'{where}.handheld.profile: use {", ".join(HANDHELD_PROFILES)}')
            if 'blur_shutter' in hh:
                cam.setdefault('shutter', number(hh.pop('blur_shutter'), where + '.handheld.blur_shutter', 0, 1))
            cam['handheld'] = {**(HANDHELD_PROFILES.get(profile) or {}), **hh}; cam['cover'] = True
        roll = cam.get('roll')
        if isinstance(roll, dict) and 'angle' in roll:
            roll = dict(roll); fields(roll, 'angle dir ease blur_shutter', where + '.roll')
            a0, a1 = roll['angle'] if isinstance(roll['angle'], list) and len(roll['angle']) == 2 else (None, None)
            if a0 is None:
                raise ContractError(f'{where}.roll.angle: expected [from, to] degrees')
            sign = -1 if roll.get('dir', 'ccw') == 'ccw' else 1
            cam['roll'] = {'from': round(math.radians(a0) * sign, 5), 'to': round(math.radians(a1) * sign, 5),
                           'ease': self.ease_name(roll.get('ease', 'inOutCubic'), where + '.roll.ease')}
            cam['cover'] = True
            cam.setdefault('shutter', number(roll.get('blur_shutter', .5), where + '.roll.blur_shutter', 0, 1))
        return cam

    # -- whole edit ---------------------------------------------------------
    def run(self, edit):
        e = copy.deepcopy(edit)
        for k in ('beat', 'palette', 'looks'):
            e.pop(k, None)
        from .hooks import normalize as hook_names
        hook_names(edit, e)   # declared hook layers / text types become explicit hook items
        e = self.colours(e, 'timeline')
        if 'look' in e:
            e['look'] = self.look(e['look'], 'look')
        if isinstance(e.get('cam'), dict):
            e['cam'] = self.camera_moves(e['cam'], None, 'cam')
        for key, clip in (e.get('clips') or {}).items() if isinstance(e.get('clips'), dict) else []:
            if isinstance(clip, dict) and isinstance(clip.get('cam'), dict):
                clip['cam'] = self.camera_moves(clip['cam'], None, f'clips.{key}.cam')
        frames = (e.get('canvas') or {}).get('frames')
        shots = e.get('shots')
        if isinstance(shots, list):
            starts = []
            for i, shot in enumerate(shots):
                if isinstance(shot, dict) and 't0' in shot:
                    if 'f0' in shot:
                        raise ContractError(f'shots[{i}]: use t0/t1 or f0/f1, not both')
                    starts.append(self.frame(shot['t0'], f'shots[{i}].t0'))
                else:
                    starts.append(shot.get('f0') if isinstance(shot, dict) else None)
            for i, shot in enumerate(shots):
                if not isinstance(shot, dict):
                    continue
                where = f'shots[{i}]'
                if 't0' in shot or 't1' in shot:
                    nxt = starts[i + 1] if i + 1 < len(shots) else frames
                    self.span(shot, where, default_end=nxt)
                shot.pop('note', None) if isinstance(shot.get('note', ''), str) else None
                for meta in ('motion_locked', 'cadence_group'):   # Review metadata; no rendering effect
                    shot.pop(meta, None)
                for entry in list((shot.get('fx') or {}).values()) + list(shot.get('layers') or []):
                    if isinstance(entry, dict):
                        entry.pop('review_window', None)
                if isinstance(shot.get('layers'), list):   # a text layer with items[] = one text layer per item
                    expanded = []
                    for layer in shot['layers']:
                        if isinstance(layer, dict) and layer.get('type') == 'text' and isinstance(layer.get('items'), list):
                            common = {k: v for k, v in layer.items() if k != 'items'}
                            expanded += [{**common, **item} for item in layer['items'] if isinstance(item, dict)]
                        else:
                            expanded.append(layer)
                    shot['layers'] = expanded
                if isinstance(shot.get('cam'), dict) and isinstance(shot.get('f0'), int) and isinstance(shot.get('f1'), int):
                    shot['cam'] = self.camera_moves(shot['cam'], (shot['f0'] / self.fps, shot['f1'] / self.fps), where + '.cam')
                if 'look' in shot:
                    shot['look'] = self.look(shot['look'], where + '.look')
                if shot.get('clip') in CLIP_KEYWORDS:
                    kind = CLIP_KEYWORDS[shot.pop('clip')]
                    if 'special' in shot:
                        raise ContractError(f'{where}: clip keyword and special both given')
                    shot['special'] = {'type': kind}
                    for k in ('srcf', 'src', 'speed', 'speed1', 'blend', 'loop'):
                        shot.pop(k, None)
                if isinstance(shot.get('special'), str):
                    shot['special'] = {'type': shot['special']}
                if isinstance(shot.get('special'), dict):
                    from .specials import defaults
                    shot['special'] = defaults(shot['special'], self.palette)
                    if shot['special'].get('type') == 'collage' and 'look' in shot['special']:
                        shot['special']['look'] = self.look(shot['special']['look'], where + '.special.look')
                fx = shot.get('fx')
                if isinstance(fx, dict):
                    shot['fx'] = self.shorthand(fx)
                if 'seed' in shot:
                    seed = number(shot.pop('seed'), where + '.seed', 0, 2 ** 31, integer=True)
                    for name in SEEDED_FX:
                        if isinstance(shot.get('fx', {}).get(name), dict):
                            shot['fx'][name].setdefault('seed', seed)
                        elif shot.get('fx', {}).get(name) is True:
                            shot['fx'][name] = {'seed': seed}
                    for layer in shot.get('layers', []):
                        if isinstance(layer, dict) and layer.get('type') in SEEDED_FX:
                            layer.setdefault('seed', seed)
        if isinstance(e.get('post'), dict):
            e['post'] = self.shorthand(e['post'])
        for i, item in enumerate(e.get('text', []) if isinstance(e.get('text'), list) else []):
            if isinstance(item, dict):
                self.span(item, f'text[{i}]')
        for i, item in enumerate(e.get('specials', []) if isinstance(e.get('specials'), list) else []):
            if not isinstance(item, dict):
                continue
            where = f'specials[{i}]'
            self.span(item, where)
            if 'f0' not in item:
                raise ContractError(f'{where}: needs f0 or t0')
            given = [k for k in ('f1', 'n', 'd') if k in item]
            if len(given) != 1:
                raise ContractError(f'{where}: give exactly one of t1/f1, n (frames) or d (seconds)')
            if 'n' in item:
                item['f1'] = item['f0'] + number(item.pop('n'), where + '.n', 1, 100000, integer=True)
            elif 'd' in item:
                item['f1'] = frame_of(item['f0'] / self.fps + number(item.pop('d'), where + '.d', .001, 3600), self.fps)
            from .specials import defaults
            defaults(item, self.palette)
            if item.get('type') == 'collage' and 'look' in item:
                item['look'] = self.look(item['look'], where + '.look')
        self.authoring_aliases(e)
        return e

    # -- stickers, font strings/stacks, sfx and audio_tracks (audit F-NAT-008) --------------------------------------
    CSS_FONT = re.compile(r'^\s*(?:(normal|italic|oblique)\s+)?(?:(normal|bold|[1-9]00)\s+)?(\{S\}|\{size\}|\d+(?:\.\d+)?)px\s+(.+?)\s*$')

    def css_font(self, item, where):
        m = self.CSS_FONT.match(item.pop('font')) if isinstance(item.get('font'), str) else None
        if not m:
            raise ContractError(f'{where}.font: CSS shorthand such as \'700 {{S}}px "Family"\' ([style] [weight] size family)')
        style, weight, size, families = m.groups()
        family = families.split(',')[0].strip().strip('"\'')
        if style:
            item.setdefault('style', 'italic' if style == 'oblique' else style)
        if weight:
            item.setdefault('weight', 700 if weight == 'bold' else 400 if weight == 'normal' else int(weight))
        if size[0] != '{':
            item.setdefault('size', float(size))
        item.setdefault('family', family)

    @staticmethod
    def stack_family(stacks, kind, declared):
        for name in (kind, 'sans'):
            for fam in (stacks.get(name) or '').split(','):
                fam = fam.strip().strip('"\'')
                if fam in declared:
                    return fam
        return None

    def track(self, t, i):
        where = f'audio_tracks[{i}]'
        if not isinstance(t, dict):
            raise ContractError(f'{where}: expected an object')
        fields(t, 'asset_id src start duration at speed gain_db fade_in fade_out', where)
        out = {k: t[k] for k in ('start', 'duration', 'at', 'speed', 'fade_in', 'fade_out') if k in t}
        if ('asset_id' in t) == ('src' in t):
            raise ContractError(f'{where}: give asset_id (an imported asset with sound) or src (a project path)')
        if 'src' in t:
            out['src'] = t['src']
        else:
            import json as _json
            assets = {}
            if self.root is not None and (self.root / 'project.json').is_file():
                assets = {a['id']: a for a in _json.loads((self.root / 'project.json').read_text(encoding='utf-8')).get('assets', [])}
            a = assets.get(t['asset_id'])
            if a is None or a.get('kind') not in ('audio', 'video'):
                raise ContractError(f'{where}.asset_id: an imported asset with sound in this project')
            out['src'] = a['path']
        if 'gain_db' in t:
            out['volume'] = round(10 ** (number(t['gain_db'], where + '.gain_db', -60, 12) / 20), 6)
        return out

    def authoring_aliases(self, e):
        if 'assets' in e:
            from .stickers import expand_assets
            e['assets'] = expand_assets(e['assets'])
        for i, ev in enumerate(e.get('stickers', []) if isinstance(e.get('stickers'), list) else []):
            if isinstance(ev, dict):
                self.span(ev, f'stickers[{i}]')
                if 'step' not in ev and self.beat:   # burst step: a 1/16 note on the beat grid
                    ev['step'] = round(60 / self.beat['bpm'] / 4, 6)
        stacks = e.pop('font_stacks', None)
        if stacks is not None and (not isinstance(stacks, dict) or not all(isinstance(v, str) for v in stacks.values())):
            raise ContractError('font_stacks: {kind: "CSS font stack"}, e.g. {"heavy": "\\"Family\\", sans-serif"}')
        declared = {f.get('family') for f in e.get('fonts', []) if isinstance(f, dict)}
        texts = [(f'text[{i}]', t) for i, t in enumerate(e.get('text', []) if isinstance(e.get('text'), list) else [])]
        texts += [(f'shots[{i}].layers[{j}]', l) for i, s in enumerate(e.get('shots', []) if isinstance(e.get('shots'), list) else []) if isinstance(s, dict)
                  for j, l in enumerate(s.get('layers', []) if isinstance(s.get('layers'), list) else []) if isinstance(l, dict) and l.get('type') == 'text']
        cues = []
        for where, item in texts:
            if not isinstance(item, dict) or item.get('type') in ('graffiti', 'hook'):
                continue
            if 'font' in item:
                self.css_font(item, where)
            if stacks and 'family' not in item:
                fam = self.stack_family(stacks, item.get('kind', 'sans'), declared)
                if fam is None:
                    raise ContractError(f'{where}: font_stacks names no declared font for kind {item.get("kind", "sans")!r}')
                item['family'] = fam
            if 'sfx' in item:   # a cue at the event start, played with OpenKatana's own synthesised sound
                if 'f0' not in item:
                    raise ContractError(f'{where}.sfx: only on timeline text events (with f0/t0)')
                cues.append({'sfx': item.pop('sfx'), 'at': round(item['f0'] / self.fps, 4)})
        if stacks:   # word / type / tag decorative text takes its family from the stacks too
            for s in e.get('shots', []) if isinstance(e.get('shots'), list) else []:
                if not isinstance(s, dict):
                    continue
                entries = [v for k, v in (s.get('fx') or {}).items() if k in ('word', 'type', 'tag') and isinstance(v, dict)] if isinstance(s.get('fx'), dict) else []
                entries += [l for l in s.get('layers', []) if isinstance(l, dict) and l.get('type') in ('word', 'type', 'tag')] if isinstance(s.get('layers'), list) else []
                for v in entries:
                    if 'family' not in v:
                        fam = self.stack_family(stacks, v.get('kind', 'sans'), declared)
                        if fam:
                            v['family'] = fam
        sfx = e.pop('sfx', None)
        if sfx is not None:
            if not isinstance(sfx, dict):
                raise ContractError('sfx: expected {"cues": [...]}')
            fields(sfx, 'auto cues hits', 'sfx')
            for k in ('auto', 'hits'):
                if sfx.get(k):
                    raise ContractError(f'sfx.{k}: automatic SFX placement is not available; list cues ({{"sfx", "at", "variant", "level_db"}})')
            if not isinstance(sfx.get('cues', []), list):
                raise ContractError('sfx.cues: a list of cues')
            cues += sfx.get('cues', [])
        if 'audio_tracks' in e:
            tracks = e.pop('audio_tracks')
            if 'audio' in e:
                raise ContractError('use audio or audio_tracks, not both')
            if not isinstance(tracks, list) or len(tracks) > 32:
                raise ContractError('audio_tracks: up to 32 tracks ([] for silence)')
            if tracks:
                e['audio'] = {'mode': 'mix', 'tracks': [self.track(t, i) for i, t in enumerate(tracks)]}
        if cues:
            audio = e.setdefault('audio', {'mode': 'mix'})
            if not isinstance(audio, dict) or audio.get('mode') != 'mix':
                raise ContractError('sound-effect cues need audio mode "mix"')
            audio['cues'] = list(audio.get('cues', [])) + cues

    def shorthand(self, fx):
        return {k: ({'v': v} if isinstance(v, (int, float)) and not isinstance(v, bool) else v) for k, v in fx.items()}


def normalize(edit, root=None):
    if not isinstance(edit, dict):
        raise ContractError('timeline: expected an object')
    n = Normalizer(edit); n.root = root   # root resolves audio_tracks asset ids
    return n.run(edit)
