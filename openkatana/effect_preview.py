"""preview_effect: a short render of ONE shot effect on a project picture, a video excerpt or a built-in test card.

The preview is an ordinary one-shot timeline, checked by contracts.validate and rendered by render.render, so it
accepts exactly the effect names and fields a saved timeline accepts (the effect packs included)."""
import difflib
import shutil

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

from .contracts import ContractError, local_path, number, validate
from .render import prepare, render, run, write_json

STILLS = ('.png', '.jpg', '.jpeg', '.webp')
VIDEOS = ('.mp4', '.mov', '.mkv', '.webm', '.avi')
MAX_FRAMES = 120
SHEET_FRAMES = 6


def effect_names():
    """Every name a shot's fx object accepts (docs/TIMELINE.md), read from the validator so new packs appear."""
    from . import effects as E
    return tuple(dict.fromkeys(E.CAMERA + E.POST + E.SUBJECT + E.SOURCE + E.EXTRA + ('graffiti',)))


def check_effect(effect, params):
    """Reject an unknown name or bad fields before any media work. Returns the timeline value (true for no params)."""
    from .effects import effects
    names = effect_names()
    if not isinstance(effect, str) or effect not in names:
        close = difflib.get_close_matches(str(effect), names, 3, .6)
        hint = f' Did you mean {", ".join(close)}?' if close else ''
        raise ContractError(f'Unknown effect {effect!r}: effect names are the shot fx names listed in docs/TIMELINE.md '
                            f'(read_guide topic "timeline"), e.g. local_turbulent_displace, glow, invert.{hint}')
    if params is not None and not isinstance(params, dict):
        raise ContractError('params: an object of the effect\'s fields (or omit it for the defaults)')
    value = True if not params else params
    effects({effect: value}, 'params')
    return value


def _even(v):
    return max(2, int(round(v / 2)) * 2)


def _fit(w, h, limit):
    s = min(1, limit / w, limit / h)
    return _even(w * s), _even(h * s)


def test_card(w, h):
    """A test card with detail every effect can act on: a grid, colour shapes, text, a gradient and a light spot."""
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    base = np.stack([18 + 30 * x / w, 20 + 18 * y / h, 34 + 40 * (1 - x / w)], -1)
    im = Image.fromarray(base.clip(0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    step = max(8, w // 16)
    for gx in range(0, w, step):
        d.line([(gx, 0), (gx, h)], fill=(70, 78, 96), width=1)
    for gy in range(0, h, step):
        d.line([(0, gy), (w, gy)], fill=(70, 78, 96), width=1)
    d.line([(0, 0), (w, h)], fill=(110, 118, 140), width=max(1, w // 480))
    d.line([(0, h), (w, 0)], fill=(110, 118, 140), width=max(1, w // 480))
    u = w / 960
    d.ellipse([90 * u, 300 * u, 270 * u, 480 * u], fill=(235, 70, 60), outline=(255, 230, 220), width=max(1, int(4 * u)))
    d.rectangle([330 * u, 330 * u, 480 * u, 480 * u], fill=(60, 190, 110))
    d.polygon([(560 * u, 480 * u), (650 * u, 320 * u), (740 * u, 480 * u)], fill=(70, 130, 245))
    for i in range(8):   # a hue strip along the bottom
        r, g, b = (np.array(Image.new('HSV', (1, 1), (i * 32, 220, 255)).convert('RGB')).reshape(3))
        d.rectangle([800 * u, (300 + i * 22) * u, 900 * u, (320 + i * 22) * u], fill=(int(r), int(g), int(b)))
    font = ImageFont.load_default(size=max(10, int(64 * u)))
    small = ImageFont.load_default(size=max(8, int(22 * u)))
    d.text((60 * u, 70 * u), 'OpenKatana', font=font, fill=(245, 245, 245))
    d.text((64 * u, 150 * u), 'effect preview  0123456789  ABCabc', font=small, fill=(200, 205, 215))
    a = np.asarray(im).astype(np.float32)
    cx, cy, rad = .74 * w, .26 * h, .09 * w   # a bright light spot (overexposed core, soft falloff) for glows and flares
    dist = np.hypot(x - cx, y - cy) / rad
    spot = np.exp(-dist * dist * 1.6)[..., None]
    a = a * (1 - spot) + np.array([255, 248, 225]) * spot
    a[dist < .35] = 255
    return Image.fromarray(a.clip(0, 255).astype(np.uint8))


def _still(path, folder, limit):
    with Image.open(path) as original:
        im = ImageOps.exif_transpose(original).convert('RGB')
    w, h = _fit(im.width, im.height, limit)
    folder.mkdir(parents=True)
    im.resize((w, h), Image.Resampling.LANCZOS).save(folder / '00000.png')
    return {'frames_dir': folder.name, 'n': 1, 'fps': 30, 'w': w, 'h': h, 'pattern': '%05d.png'}


def _video(path, out, at, seconds, fps, limit):
    from .editor_tools import metadata
    info = metadata(path)
    video = next((s for s in info['streams'] if s.get('codec_type') == 'video'), None)
    if not video:
        raise ContractError('source: the file has no video stream')
    rotations = [float(x.get('rotation', 0)) for x in video.get('side_data_list', [])] + [float(video.get('tags', {}).get('rotate', 0))]
    if video.get('color_transfer') in ('smpte2084', 'arib-std-b67') or any(abs(a) % 360 > .001 for a in rotations):
        raise ContractError('HDR/rotated video needs explicit conformance first (import_hdr_media / import_media)')
    total = float(info['format'].get('duration') or video.get('duration') or 0)
    if total and at >= total:
        raise ContractError(f'at: {at} s is past the end of the source ({total:.3f} s)')
    w, h = _fit(int(video['width']), int(video['height']), limit)
    excerpt = out / 'excerpt.mp4'
    run(['ffmpeg', '-v', 'error', '-nostdin', '-ss', str(at), '-i', path, '-t', str(seconds), '-map', '0:v:0', '-an',
         '-vf', f'fps={fps},scale={w}:{h}', '-c:v', 'libx264', '-crf', '12', '-preset', 'veryfast', '-pix_fmt', 'yuv420p', excerpt])
    clip = prepare(excerpt, out / 'source')
    if clip['n'] < 1:
        raise ContractError('source: no video frames at that time')
    return clip


def contact_sheet(frames_dir, picks, fps, path, label):
    tw, th, bar, cols = 320, 180, 22, 3
    rows = -(-len(picks) // cols)
    sheet = Image.new('RGB', (cols * tw, rows * (th + bar) + bar), '#141414')
    d = ImageDraw.Draw(sheet)
    d.text((8, 5), label, fill=(230, 230, 230))
    for i, f in enumerate(picks):
        with Image.open(frames_dir / f'{f:05d}.png') as im:
            tile = ImageOps.pad(im.convert('RGB'), (tw, th), color=(20, 20, 20))
        x, y = i % cols * tw, bar + i // cols * (th + bar)
        sheet.paste(tile, (x, y + bar))
        d.text((x + 8, y + 5), f'frame {f}  {f / fps:.3f} s', fill=(210, 210, 210))
    sheet.save(path)
    return path


def preview_effect(root, out, effect, params, source, seconds, fps, at, max_width):
    value = check_effect(effect, params)
    number(seconds, 'seconds', .01, 60)
    number(fps, 'fps', 1, 60, integer=True)
    number(at, 'at', 0)
    number(max_width, 'max_width', 64, 960, integer=True)
    count = int(round(seconds * fps))
    if not 1 <= count <= MAX_FRAMES:
        raise ContractError(f'seconds x fps gives {count} frames; a preview has 1..{MAX_FRAMES} frames')
    warnings = []
    src = None
    if source is not None:
        src = local_path(root, source)
        if not src.is_file():
            raise ContractError(f'source: no file at {source!r} in the project (give a project-relative image or video path)')
        if src.suffix.lower() not in STILLS + VIDEOS:
            raise ContractError(f'source: expected an image ({", ".join(STILLS)}) or a video ({", ".join(VIDEOS)})')
    if at and (src is None or src.suffix.lower() in STILLS):
        warnings.append({'code': 'at_ignored', 'message': 'at only moves the start of a video source; a still has no time'})
    out.mkdir(parents=True, exist_ok=False)
    try:
        if src is None:
            w, h = _even(max_width), _even(max_width * 9 / 16)
            (out / 'source').mkdir()
            test_card(w, h).save(out / 'source' / '00000.png')
            clip = {'frames_dir': 'source', 'n': 1, 'fps': fps, 'w': w, 'h': h, 'pattern': '%05d.png'}
        elif src.suffix.lower() in STILLS:
            clip = _still(src, out / 'source', max_width)
        else:
            clip = _video(src, out, at, seconds, fps, max_width)
            if clip['n'] < count:
                warnings.append({'code': 'source_short', 'message': f'the source has {clip["n"]} frames from {at} s; the preview is that long'})
                count = clip['n']
        still = clip['n'] == 1 and (src is None or src.suffix.lower() in STILLS)
        edit = {'canvas': {'w': clip['w'], 'h': clip['h'], 'fps': fps, 'frames': count},
                'clips': {'source': clip},
                'shots': [{'f0': 0, 'f1': count, 'clip': 'source', 'speed': 0 if still else 1, 'fx': {effect: value}}]}
        edit = validate(edit, out)
        write_json(out / 'timeline.json', edit)
        receipt = render(out / 'timeline.json', out / 'render')
        picks = sorted({round(i * (count - 1) / (SHEET_FRAMES - 1)) for i in range(SHEET_FRAMES)}) if count > 1 else [0]
        frames_dir = out / 'render' / 'frames'
        sheet = contact_sheet(frames_dir, picks, fps, out / 'contact-sheet.png',
                              f'{effect}  {clip["w"]}x{clip["h"]}  {count} frames at {fps} fps')
        from .preview import flat_frames
        for flat in flat_frames(edit, picks, [str(frames_dir / f'{f:05d}.png') for f in picks]):
            warnings.append({'code': 'flat_frame', 'frame': flat['frame'], 'message': f"frame {flat['frame']} rendered as one flat colour rgb{tuple(flat['rgb'])}; check the effect's values"})
        # A still under a static effect is meant to hold; only report frozen runs for a moving source.
        warnings += [w for w in receipt['warnings'] if not (still and w.get('code') == 'frozen_frames')]
    except BaseException:
        shutil.rmtree(out, ignore_errors=True)
        raise
    # The mp4 and the sheet are the preview; the PNG frames would only fill the disk.
    shutil.rmtree(frames_dir, ignore_errors=True)
    if src is not None and src.suffix.lower() in VIDEOS:
        for p in (out / 'source').glob('*.png'):
            p.unlink()
    return {'video': str((out / 'render' / 'video.mp4').resolve()), 'contact_sheet': str(sheet.resolve()),
            'preview_images': [str(sheet.resolve())], 'frames': count, 'fps': fps, 'width': clip['w'], 'height': clip['h'],
            'effect': effect, 'params': params or {}, 'source': str(src) if src else 'test card',
            'timeline': str((out / 'timeline.json').resolve()), 'warnings': warnings,
            'note': 'One shot with only this effect, rendered by the same engine as start_render. Watch the video for motion; the sheet shows 6 frames.'}
