"""Explicit, deliberately small timeline contract for the first implementation."""
from __future__ import annotations

import math
import re
from pathlib import Path


class ContractError(ValueError):
    pass


def fields(value, allowed, where):
    if not isinstance(value, dict):
        raise ContractError(f"{where}: expected an object")
    unknown = set(value) - set(allowed.split())
    if unknown:
        raise ContractError(f"{where}: unsupported fields: {', '.join(sorted(unknown))}")


def number(value, where, low=None, high=None, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ContractError(f"{where}: expected a finite number")
    if integer and int(value) != value:
        raise ContractError(f"{where}: expected an integer")
    if low is not None and value < low or high is not None and value > high:
        raise ContractError(f"{where}: out of range")
    return value


def local_path(root: Path, value: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ContractError("A nonempty project-relative path is required")
    path = (root / value).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ContractError(f"Path leaves the project: {value}")
    return path


FONT_SIGNATURES = {bytes.fromhex('00010000'): 'TrueType', b'true': 'TrueType', b'OTTO': 'OpenType/CFF', b'ttcf': 'TrueType collection',
                   b'wOFF': 'WOFF', b'wOF2': 'WOFF2'}


def check_font_file(path: Path, family: str = '') -> str:
    """Reject unreadable font files before rendering (a corrupt file would abort the browser render)."""
    head = path.read_bytes()[:4]
    kind = FONT_SIGNATURES.get(head)
    label = f'Font "{family}" ({path.name})' if family else f'Font {path.name}'
    if not kind:
        raise ContractError(f'{label} is not a TrueType/OpenType/WOFF font file')
    if kind not in ('WOFF', 'WOFF2'):
        from PIL import ImageFont
        try:
            ImageFont.truetype(str(path), 16)
        except OSError as e:
            raise ContractError(f'{label} cannot be read: {e}') from e
    elif path.stat().st_size < 64:
        raise ContractError(f'{label} is truncated')
    return kind


RGBA = re.compile(r'rgba\((\d{1,3}),(\d{1,3}),(\d{1,3}),(0|1|0?\.\d+)\)')


def color(value, where, alpha=False):
    """Canonical colours: "#rrggbb", or "rgba(r,g,b,a)" where the field supports transparency. Authoring forms
    ("$name", rgb()/rgba(), [r,g,b(,a)]) are converted by native.normalize before this check."""
    if isinstance(value, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', value):
        return
    if isinstance(value, str) and RGBA.fullmatch(value):
        if alpha:
            return
        raise ContractError(f'{where}: this colour must be opaque')
    raise ContractError(f'{where}: use "#rrggbb", rgb()/rgba(), [r,g,b(,a)] or a "$palette" name')


EASES = ('lin', 'in2', 'in3', 'out2', 'out3', 'inout', 'outback')


def animated(value, where, low=None, high=None):
    """A number, or an animated number {from, to, ease, over, at} (progress over `over` x shot duration from `at` s)."""
    if isinstance(value, dict):
        fields(value, 'from to ease over at', where)
        for k in ('from', 'to'):
            number(value.get(k), f'{where}.{k}', low, high)
        if value.get('ease', 'lin') not in EASES:
            raise ContractError(f'{where}.ease: use one of {", ".join(EASES)}')
        number(value.get('over', 1), where + '.over', .001, 100)
        number(value.get('at', 0), where + '.at', 0)
        return value
    return number(value, where, low, high)


def validate(edit: dict, root: Path | None = None) -> dict:
    """Check a timeline and return its canonical form (native authoring syntax rewritten by native.normalize)."""
    from .effects import camera, effects, transition, layers
    from .native import normalize
    canonical = normalize(edit, Path(root) if root is not None else None)
    edit = edit if canonical == edit else canonical   # an already-canonical timeline is returned as the same object
    fields(edit, 'canvas clips shots text fonts audio cam post look specials hooks assets stickers', 'timeline')
    from .hooks import validate as validate_hooks, check_layer, check_text
    hook_layers, hook_texts = validate_hooks(edit, root)
    from .expanded import look
    look(edit.get('look'))
    camera(edit.get('cam', {}), 'cam')
    effects(edit.get('post', {}), 'post')
    canvas = edit.get('canvas', {})
    fields(canvas, 'w h fps frames bg boil', 'canvas')
    number(canvas.get('boil',2),'canvas.boil',1,120,integer=True)
    for key in ('w', 'h'):
        n = number(canvas.get(key), f'canvas.{key}', 2, 7680, integer=True)
        if n % 2:
            raise ContractError('Canvas dimensions must be even')
    number(canvas.get('fps'), 'canvas.fps', 1, 120)
    number(canvas.get('frames'), 'canvas.frames', 1, 216000, integer=True)
    if 'bg' in canvas:
        color(canvas['bg'], 'canvas.bg')
    clips = edit.get('clips', {})
    face_rows = {}
    if not isinstance(clips, dict):
        raise ContractError('clips must be an object')
    for key, clip in clips.items():
        if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', key):
            raise ContractError(f'Clip id {key!r}: use 1..64 letters, digits, _ or -')
        fields(clip, 'frames_dir n fps w h pattern cam mask_dir faces faces_size', f'clips.{key}')
        if 'faces_size' in clip:
            from .faces import coordinates
            coordinates(clip['faces_size'],2,'faces_size')
            for v in clip['faces_size']:number(v,'faces_size',1)
            if 'faces' not in clip:raise ContractError('faces_size requires a face track')
        camera(clip.get('cam', {}), f'clips.{key}.cam')
        for prop in ('n', 'w', 'h'):
            number(clip.get(prop), f'clips.{key}.{prop}', 1, integer=True)
        number(clip.get('fps'), f'clips.{key}.fps', 1, 240)
        if clip.get('pattern', '%05d.png') not in ('%05d.png', '%05d.jpg'):
            raise ContractError('Only %05d.png and %05d.jpg sequences are supported')
        if root:
            if 'faces' in clip:
                from .faces import read_track
                face_rows[key]=read_track(root,clip)
            folder = local_path(root, clip.get('frames_dir'))
            for index in range(clip['n']):
                if not (folder / (clip.get('pattern', '%05d.png') % index)).is_file():
                    raise ContractError(f'Missing source frame: {key}/{index}')
            if 'mask_dir' in clip:
                from PIL import Image
                masks=local_path(root,clip['mask_dir'])
                for index in range(clip['n']):
                    mask=masks/f'{index:05d}.png'
                    if not mask.is_file(): raise ContractError(f'Missing mask frame: {key}/{index}')
                    with Image.open(mask) as im:
                        if im.size!=(clip['w'],clip['h']): raise ContractError(f'Mask geometry differs from source: {key}/{index}')
                        if 'A' not in im.getbands(): raise ContractError(f'Mask requires an alpha channel: {key}/{index}')
    shots = edit.get('shots')
    if not isinstance(shots, list) or not shots:
        raise ContractError('shots must be a nonempty array')
    end = 0
    for i, shot in enumerate(shots):
        where = f'shots[{i}]'
        fields(shot, 'f0 f1 clip src srcf speed speed1 blend loop cam bg fx in out layers face look transition special', where)
        look(shot.get('look'),where+'.look')
        if 'face' in shot:
            from .faces import shot_face
            shot_face(shot['face'])
        effects(shot.get('fx', {}), where + '.fx')
        shot_layers = shot.get('layers', [])
        layers([l for l in shot_layers if not (isinstance(l, dict) and l.get('type') == 'hook')] if isinstance(shot_layers, list) else shot_layers, where + '.layers')
        for li, l in enumerate(shot_layers if isinstance(shot_layers, list) else []):
            if isinstance(l, dict) and l.get('type') == 'hook':
                check_layer(l, f'{where}.layers[{li}]', hook_layers)
                if l.get('phase', 'over') not in ('back', 'subject', 'over', 'post', 'final'):
                    raise ContractError(f'{where}.layers[{li}]: unsupported phase')
                if 'order' in l:
                    number(l['order'], f'{where}.layers[{li}].order')
        for side in ('in', 'out'):
            if side in shot:
                transition(shot[side], f'{where}.{side}')
        if 'bg' in shot:
            color(shot['bg'], where + '.bg')
        for prop in ('f0', 'f1'):
            number(shot.get(prop), f'{where}.{prop}', 0, canvas['frames'], integer=True)
        if shot['f0'] != end or shot['f1'] <= end:
            raise ContractError(f'{where}: shots must cover the timeline without gaps or overlap (starts at frame {shot["f0"]}, previous shot ends at {end})')
        end = shot['f1']
        if 'special' in shot:
            from .specials import validate_special
            if 'clip' in shot:
                raise ContractError(f'{where}: a special shot has no clip')
            validate_special(shot['special'], where + '.special', clips)
            continue
        if shot.get('clip') not in clips:
            raise ContractError(f'{where}: unknown clip')
        for prop in ('src', 'srcf', 'speed', 'speed1'):
            if prop in shot:
                number(shot[prop], f'{where}.{prop}', -1000, 1000)
        if 'src' in shot and 'srcf' in shot:
            raise ContractError('Use src or srcf, not both')
        if 'blend' in shot and not isinstance(shot['blend'], bool):
            raise ContractError('blend must be boolean')
        if shot.get('loop', 'clamp') not in ('clamp', 'loop', 'pingpong'):
            raise ContractError('Unsupported loop mode')
        camera(shot.get('cam', {}), where + '.cam')
        clip=clips[shot['clip']]
        shot_look=shot.get('look',edit.get('look'))
        if isinstance(shot_look,dict) and shot_look.get('type')=='studio' and any(f.get('type')=='contour_glow' for f in shot_look.get('fx',[])) and 'mask_dir' not in clip:
            raise ContractError(f'{where}: contour_glow needs a subject matte (clip mask_dir)')
        merged_cam={**edit.get('cam',{}),**clip.get('cam',{}),**shot.get('cam',{})}
        if merged_cam.get('type')=='facelock' or merged_cam.get('lock') is True:
            if not clip.get('faces'):raise ContractError(f'{where}: face lock requires a supplied clip face track')
            if root:
                usable=[r for r in face_rows[shot['clip']] if r and r.get('box')]
                if not usable:raise ContractError(f'{where}: face lock requires at least one usable face')
                if any(r.get('eyes') and r['eyes'][0]==r['eyes'][1] for r in usable):
                    raise ContractError(f'{where}: face lock requires distinct eye coordinates')
    if end != canvas['frames']:
        raise ContractError('Shots must end at canvas.frames')
    from .transitions import validate_transitions
    validate_transitions(edit)
    from .specials import validate_specials
    validate_specials(edit)
    fonts = {}
    for font in edit.get('fonts', []):
        fields(font, 'family url weight style', 'font')
        if font.get('style','normal') not in ('normal','italic','oblique'):
            raise ContractError('Unsupported declared font style')
        weight=font.get('weight','normal')
        if isinstance(weight,str):
            if weight not in ('normal','bold') and not re.fullmatch(r'[1-9][0-9]{0,2}|1000',weight):
                raise ContractError('Declared font weight must be normal, bold or 1..1000')
        else: number(weight,'font.weight',1,1000)
        if not isinstance(font.get('family'), str):
            raise ContractError('Font family is required')
        if font['family'] in fonts:
            raise ContractError('Duplicate font family')
        fonts[font['family']] = font
        if root:
            path = local_path(root, font.get('url'))
            if not path.is_file():
                raise ContractError(f"Font file missing: {font.get('url')}")
            check_font_file(path, font['family'])
    for ti, item in enumerate(edit.get('text', [])):
        if isinstance(item, dict) and item.get('type') == 'hook':
            check_text(item, f'text[{ti}]', hook_texts, end)
            continue
        from .typography import text_item
        text_item(item,fonts,'text')
        number(item.get('f0'), 'text.f0', 0, end - 1, integer=True)
        number(item.get('f1'), 'text.f1', item['f0'] + 1, end, integer=True)
        number(item.get('size',96), 'text.size', 1, 2000)
        number(item.get('alpha', 1), 'text.alpha', 0, 1)
        if 'fill' in item and item['fill'] is not None:
            color(item['fill'], 'text.fill')
        pos = item.get('pos', [.5, .5])
        if not isinstance(pos, list) or len(pos) != 2:
            raise ContractError('Text pos must have two coordinates')
        for v in pos:
            number(v, 'text.pos', 0, 1)
        if item.get('align', 'center') not in ('left', 'center', 'right'):
            raise ContractError('Unsupported text alignment')
    from .typography import text_item
    for shot in shots:
        for layer in shot.get('layers',[]):
            if layer['type']=='text':
                text_item(layer,fonts,'text layer',layer=True)
                number(layer.get('at',0),'text layer.at',0)
                if 'd' in layer: number(layer['d'],'text layer.d',.001)
    for shot in shots:
        entries=[(k,v) for k,v in {**edit.get('post',{}),**shot.get('fx',{})}.items()]
        entries += [(v['type'],v) for v in shot.get('layers',[])]
        for name,v in entries:
            if name in ('big','burst') and v is not False:
                v={} if v is True else v
                if name=='big' or v.get('letters'):
                    if v.get('family') not in fonts:raise ContractError(f'{name}: requires an explicitly supplied font')
            if name=='local_scramble_text' and isinstance(v,dict) and v.get('family') not in fonts:
                raise ContractError('local_scramble_text: family must be a declared font')
            if name in ('word','type','tag') and isinstance(v,dict) and v.get('family') not in fonts:
                raise ContractError(f'{name}: family must be a declared font (or font_stacks)')
    from .stickers import validate as validate_stickers
    validate_stickers(edit, root, canvas['frames'], canvas['fps'])
    from .audio import validate_audio
    validate_audio(edit.get('audio'),root,canvas['frames']/canvas['fps'])
    return edit
