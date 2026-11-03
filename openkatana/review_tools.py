"""Review aids for matching a reference (docs/EDITOR_TOOLS.md): a side-by-side video and look statistics against the
reference (compare_reference), a numbered sheet with one picture per shot (shot_sheet) and eye crops across a clip
(eye_sheet). They show; they do not judge. Visual review stays with the editor."""
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps

from .contracts import ContractError, local_path, number
from .render import run, write_json


def side_by_side(reference, rendered, out, offset=0):
    """Reference (left) and render (right) at the same height, the render shifted so render time = reference time +
    offset, with the reference's audio."""
    number(offset, 'render_offset', -3600, 3600)
    path = out / 'side_by_side.mp4'
    ref_in = ['-ss', str(-offset)] if offset < 0 else []
    ren_in = ['-ss', str(offset)] if offset > 0 else []
    run(['ffmpeg', '-v', 'error', '-nostdin', *ref_in, '-i', str(reference), *ren_in, '-i', str(rendered),
         '-filter_complex', '[0:v]scale=-2:540,setsar=1[a];[1:v]scale=-2:540,setsar=1[b];[a][b]hstack=inputs=2,format=yuv420p[v]',
         '-map', '[v]', '-map', '0:a:0?', '-c:v', 'libx264', '-crf', '18', '-preset', 'fast', '-c:a', 'aac', '-shortest',
         '-movflags', '+faststart', str(path)])
    return str(path)


def look(source, every=3):
    """Median look statistics of a video (reference_measure.LOOK_KEYS), every `every` frames."""
    from .reference_measure import _frames, _frame_look, _look_dict, _probe
    fps, w, h = _probe(source)
    th = max(2, int(round(192 * h / w / 2)) * 2)
    rows = [_frame_look(rgb) for i, rgb in enumerate(_frames(source, 0, 86400, 192, th, 'rgb24')) if i % every == 0]
    if not rows:
        raise ContractError(f'No frames decoded from {source}')
    return _look_dict(rows)


def look_difference(reference, rendered):
    a, b = look(reference), look(rendered)
    return {'reference': a, 'render': b, 'render_minus_reference': {k: round(b[k] - a[k], 3) for k in a},
            'note': 'Medians over the whole of each file: luma percentiles (0-255), HSV-style saturation (0-1), and the '
                    'colour cast (channel minus the mean) of the darkest and brightest quarters.'}


def _font(size):
    from PIL import ImageFont
    try:
        return ImageFont.truetype(str(Path(__file__).parent / 'fonts' / 'Inter[opsz,wght].ttf'), size)
    except OSError:
        return ImageFont.load_default()


def _tile(im, label, w, h):
    tile = ImageOps.fit(im.convert('RGB'), (w, h), Image.Resampling.LANCZOS) if im is not None else Image.new('RGB', (w, h), '#222222')
    d = ImageDraw.Draw(tile); f = _font(max(12, h // 9)); box = d.textbbox((0, 0), label, font=f)
    d.rectangle((0, 0, box[2] + 12, box[3] + 10), fill='#000000'); d.text((6, 4), label, fill='#ffffff', font=f)
    return tile


def _sheets(tiles, out, stem, columns, per_sheet=40):
    paths = []
    for first in range(0, len(tiles), per_sheet):
        batch = tiles[first:first + per_sheet]; w, h = batch[0].size; rows = math.ceil(len(batch) / columns)
        sheet = Image.new('RGB', (columns * w, rows * h), '#111111')
        for i, t in enumerate(batch):
            sheet.paste(t, (i % columns * w, i // columns * h))
        p = out / f'{stem}-{first // per_sheet:02d}.jpg'; sheet.save(p, quality=90); paths.append(str(p))
    return paths


def frame_count(source, fps):
    import json
    info = json.loads(run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=nb_frames:format=duration',
                           '-of', 'json', str(source)]))
    n = (info.get('streams') or [{}])[0].get('nb_frames')
    return int(n) if n and str(n).isdigit() else int(round(float(info['format']['duration']) * fps))


def shot_sheet(source, out, cuts, fps, position=.75, columns=5):
    """One numbered picture per shot of a video: shot n spans cuts[n-1]..cuts[n] (cuts include the first start and the
    end). Frames past the end of the video show its last frame."""
    from .reference_measure import _frames, _probe
    number(position, 'position', 0, 1); number(columns, 'columns', 1, 8, integer=True)
    if len(cuts) - 1 > 200:
        raise ContractError('At most 200 shots per sheet set')
    vfps, w, h = _probe(source)
    if abs(vfps - fps) / fps > .01:
        raise ContractError(f'The video runs at {vfps:g} fps but the cuts count frames at {fps:g} fps')
    shots = [{'n': i + 1, 'f0': a, 'f1': b, 'frame': min(b - 1, a + int(round((b - a) * position))), 'time': round(a / fps, 3)}
             for i, (a, b) in enumerate(zip(cuts, cuts[1:]))]
    want = {s['frame']: s for s in shots}; th = max(2, int(round(480 * h / w / 2)) * 2); got = {}
    last = None
    for f, rgb in enumerate(_frames(source, 0, 86400, 480, th, 'rgb24')):
        last = rgb
        if f in want:
            got[f] = Image.fromarray(rgb)
        if f >= max(want):
            break
    for f in want:
        if f not in got and last is not None:
            got[f] = Image.fromarray(last)
    out.mkdir(parents=True, exist_ok=False)
    tiles = [_tile(got.get(s['frame']), f"{s['n']}  {s['time']:.1f}s", 384, int(384 * th / 480)) for s in shots]
    paths = _sheets(tiles, out, 'shot-sheet', columns)
    write_json(out / 'shots.json', shots)
    return {'preview_images': paths, 'shots': shots,
            'note': f'Each tile is the frame {round(position * 100)} % into its shot, labelled with the shot number and its start time.'}


def eye_sheet(root, clip, out, frames):
    """Crops around both eyes (YuNet landmarks) across frames of a clip, for judging gaze and face-replacement eye
    artefacts by eye."""
    import cv2
    from .vision import YUNET
    if not YUNET.is_file() or not hasattr(cv2, 'FaceDetectorYN'):
        raise ContractError('eye_sheet needs OpenCV >= 4.8 and the bundled YuNet model')
    if not 1 <= len(frames) <= 60:
        raise ContractError('frames: 1..60 clip frames')
    folder = local_path(root, clip['frames_dir']); det = None; rows, tiles = [], []
    for f in frames:
        number(f, 'frame', 0, clip['n'] - 1, integer=True)
        im = cv2.imread(str(folder / (clip.get('pattern', '%05d.png') % f)))
        if im is None:
            raise ContractError(f'Missing source frame {f}')
        h, w = im.shape[:2]; s = min(1., 960 / w); small = cv2.resize(im, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
        if det is None or det.getInputSize() != (small.shape[1], small.shape[0]):
            det = cv2.FaceDetectorYN.create(str(YUNET), '', (small.shape[1], small.shape[0]), .6, .3, 5000)
        _, faces = det.detect(small)
        if faces is None or not len(faces):
            rows.append({'frame': f, 'face': False}); tiles.append(_tile(Image.fromarray(im[:, :, ::-1]), f'{f}  no face', 360, 120)); continue
        x = [float(v) for v in max(faces, key=lambda r: r[2] * r[3])]; (rx, ry), (lx, ly) = (x[4] / s, x[5] / s), (x[6] / s, x[7] / s)
        d = math.hypot(lx - rx, ly - ry); cx, cy = (rx + lx) / 2, (ry + ly) / 2; bw, bh = 2.4 * d, .8 * d
        x0, y0 = int(max(0, cx - bw / 2)), int(max(0, cy - bh / 2)); x1, y1 = int(min(w, cx + bw / 2)), int(min(h, cy + bh / 2))
        crop = Image.fromarray(im[y0:y1, x0:x1, ::-1]) if x1 > x0 + 4 and y1 > y0 + 4 else None
        rows.append({'frame': f, 'face': True, 'eye_distance': round(d, 1), 'eyes': [[round(rx, 1), round(ry, 1)], [round(lx, 1), round(ly, 1)]]})
        tiles.append(_tile(crop, str(f), 360, 120))
    out.mkdir(parents=True, exist_ok=False)
    paths = _sheets(tiles, out, 'eye-sheet', 4, per_sheet=60)
    write_json(out / 'eyes.json', rows)
    return {'preview_images': paths, 'frames': rows,
            'note': 'Eye crops for judging gaze direction and eye artefacts (white or doubled eyes from face replacement) '
                    'by eye. No automatic gaze score is computed.'}
