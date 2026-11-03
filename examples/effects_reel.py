"""Reproduce the README reel of the After Effects packs (docs/assets/ae-packs.mp4 and .gif).

Each entry of the spec (effects_reel.json beside this script) is one labelled segment: an original test plate with that
entry's shot fx, rendered by OpenKatana and encoded as ae-packs.mp4 and ae-packs.gif. Frames are deleted segment by
segment, so the disk never holds more than one segment plus the labelled frames. No service, model or footage.

    python examples/effects_reel.py                      # writes work/effects-reel/ae-packs.mp4 and ae-packs.gif
    python examples/effects_reel.py --spec my.json --out reel --width 1280 --height 720

A spec is a JSON list of {"label": "Twirl", "fx": {"local_twirl": {...}}}: any shot fx of docs/TIMELINE.md.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

try:
    import openkatana
except ImportError:   # a source checkout without an installed package
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import openkatana
from PIL import Image, ImageDraw, ImageEnhance, ImageFont

from openkatana.contracts import validate
from openkatana.render import render

HERE = Path(__file__).resolve().parent
PACKAGE = Path(openkatana.__file__).resolve().parent


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    p.add_argument('--spec', type=Path, default=HERE / 'effects_reel.json', help='the effects to show (default: %(default)s)')
    p.add_argument('--out', type=Path, default=Path('work/effects-reel'), help='output folder (default: %(default)s)')
    p.add_argument('--width', type=int, default=640)
    p.add_argument('--height', type=int, default=360)
    p.add_argument('--fps', type=int, default=24)
    p.add_argument('--frames', type=int, default=24, help='frames per effect (default: %(default)s, 1 s)')
    p.add_argument('--gif-width', type=int, default=560)
    a = p.parse_args(argv)
    if a.width < 16 or a.height < 16 or a.width % 2 or a.height % 2:
        p.error('--width and --height: even numbers of at least 16')
    if not 1 <= a.fps <= 120 or not 1 <= a.frames <= 600:
        p.error('--fps 1..120 and --frames 1..600')
    return a


def load_spec(path):
    spec = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(spec, list) or not spec:
        raise ValueError(f'{path}: expected a nonempty list of {{"label": ..., "fx": {{...}}}}')
    for i, e in enumerate(spec):
        if not (isinstance(e, dict) and isinstance(e.get('label'), str) and isinstance(e.get('fx'), dict)):
            raise ValueError(f'{path}[{i}]: expected {{"label": text, "fx": {{effect: params}}}}')
    return spec


def draw_plate(w, h):
    """The original test plate (designed at 640x360): a dark gradient, a grid, the OpenKatana logo kept below the light
    thresholds, and one bright light spot for glows, rays and flares."""
    u = h / 360
    plate = Image.new('RGB', (w, h), (12, 14, 22))
    d = ImageDraw.Draw(plate)
    for y in range(h):
        c = int(12 + 16 * (1 - abs(y / h - .5) * 2))
        d.line([(0, y), (w, y)], fill=(c, c + 2, c + 10))
    step = max(4, round(32 * u))
    for x in range(0, w, step):
        d.line([(x, 0), (x, h)], fill=(44, 52, 80), width=1)
    for y in range(0, h, step):
        d.line([(0, y), (w, y)], fill=(44, 52, 80), width=1)
    with Image.open(PACKAGE / 'web' / 'openkatana-logo.jpg') as im:
        logo = im.convert('RGB')
    lh = max(2, round(200 * u))
    logo = logo.resize((max(1, round(logo.width * lh / logo.height)), lh), Image.Resampling.LANCZOS)
    logo = ImageEnhance.Brightness(logo).enhance(.82)
    plate.paste(logo, ((w - logo.width) // 2, (h - logo.height) // 2))
    r = 14 * u
    d.ellipse([w * .78 - r, h * .22 - r, w * .78 + r, h * .22 + r], fill=(255, 250, 235))
    return plate


def label_font(size):
    try:
        return ImageFont.truetype('arialbd.ttf', size)     # the README reel's labels
    except OSError:
        pass
    try:
        font = ImageFont.truetype(str(PACKAGE / 'fonts' / 'Inter[opsz,wght].ttf'), size)
        try:
            font.set_variation_by_name('Bold')
        except (OSError, ValueError):
            pass
        return font
    except OSError:
        return ImageFont.load_default(size=size)


def segment(plate_dir, w, h, fps, frames, fx):
    return {'canvas': {'w': w, 'h': h, 'fps': fps, 'frames': frames},
            'clips': {'P': {'frames_dir': plate_dir, 'n': 1, 'fps': fps, 'w': w, 'h': h}},
            'shots': [{'f0': 0, 'f1': frames, 'clip': 'P', 'speed': 0, 'fx': fx}]}


def label(im, text, font, u):
    d = ImageDraw.Draw(im)
    w, h = im.size
    d.rounded_rectangle([12 * u, h - 44 * u, 24 * u + d.textlength(text, font=font), h - 12 * u], 6 * u, fill=(0, 0, 0))
    d.text((18 * u, h - 41 * u), text, font=font, fill=(255, 255, 255))
    return im


def main(argv=None):
    a = parse_args(argv)
    spec = load_spec(a.spec)
    w, h, fps, seg = a.width, a.height, a.fps, a.frames
    out = a.out.resolve()
    work = out / 'reel-work'
    shutil.rmtree(work, ignore_errors=True)
    (work / 'plate').mkdir(parents=True)
    draw_plate(w, h).save(work / 'plate' / '00000.png')
    for e in spec:   # every entry is checked before the first render
        validate(segment('plate', w, h, fps, seg, e['fx']), work)
    u = h / 360
    font = label_font(max(8, round(22 * u)))
    n = 0
    for e in spec:
        (work / 't.json').write_text(json.dumps(segment('plate', w, h, fps, seg, e['fx'])), encoding='utf-8')
        shutil.rmtree(work / 'o', ignore_errors=True)
        render(work / 't.json', work / 'o')
        for f in range(seg):
            with Image.open(work / 'o' / 'frames' / f'{f:05d}.png') as im:
                label(im.convert('RGB'), e['label'], font, u).save(work / f'r{n:05d}.png')
            n += 1
        shutil.rmtree(work / 'o', ignore_errors=True)
        print(f'{e["label"]}: done', flush=True)
    mp4, gif = out / 'ae-packs.mp4', out / 'ae-packs.gif'
    subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-framerate', str(fps), '-i', str(work / 'r%05d.png'),
                    '-c:v', 'libx264', '-crf', '20', '-pix_fmt', 'yuv420p', str(mp4)], check=True)
    subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-i', str(mp4), '-vf',
                    f'fps=10,scale={min(a.gif_width, w)}:-1:flags=lanczos,split[a][b];'
                    '[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer:bayer_scale=4', str(gif)], check=True)
    shutil.rmtree(work, ignore_errors=True)
    print(json.dumps({'mp4': str(mp4), 'gif': str(gif), 'effects': len(spec), 'frames': n,
                      'credits_used': 0, 'assets': 'Original test plate and the OpenKatana logo; no footage or music.'}))
    return mp4, gif


if __name__ == '__main__':
    main()
