"""Frame-level reference measurement (analyze_reference `measure`, docs/EDITOR_TOOLS.md): what a reference edit does at
every frame of a 60-fps clock. OpenKatana analyses every reference at 60 fps, never lower, so whips, flashes, one-frame
cuts, shakes and the shape of every ease are all seen; a slower source repeats frames on that clock (24p in a 2-3
pattern) and frame numbers and curves line up with a 60-fps timeline. Estimates for the editor to verify by eye, not a
reconstruction.

  cuts         cuts from the frame-to-frame change of brightness-normalised thumbnails. A change whose picture comes
               back within a few frames (only the exposure or focus moved) is reported as a `dip`, not a cut.
  cadence      repeated pictures (24p material on a 60p clock repeats in a 2-3 pattern) and the unique-picture rate.
  look         tone (luma percentiles), saturation and the shadow/highlight colour cast, overall and per shot.
  textures     how long small bright specks (dust, scratches, grain plates) persist: the overlay's own picture rate.
  transitions  the first frames after the real cuts, as the median across cuts (each shot's own camera move averages
               out): motion (scale, offset), defocus radius and brightening, returned as `local_curve` arrays.
"""
import json
import subprocess
from fractions import Fraction

import numpy as np

from .contracts import ContractError, number
from .render import write_json

MEASURES = ('cuts', 'cadence', 'look', 'textures', 'transitions')
LW = np.array([.2126, .7152, .0722], np.float32)
CLOCK = 60                                              # the analysis clock: every reference is measured at 60 fps


def _cv():
    try:
        import cv2
    except ImportError as e:
        raise ContractError('Install OpenKatana with the vision extra to measure a reference') from e
    return cv2


def _probe(source):
    info = json.loads(subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
                                      'stream=width,height,r_frame_rate', '-of', 'json', str(source)],
                                     capture_output=True, text=True, timeout=60).stdout or '{}')
    streams = info.get('streams') or []
    if not streams:
        raise ContractError('The reference has no video stream to measure')
    s = streams[0]
    return float(Fraction(s['r_frame_rate'])), s['width'], s['height']


def _frames(source, start, duration, w, h, fmt):
    """Decode the window on the 60-fps analysis clock as uint8 arrays: a 60-fps source passes through frame for frame,
    a slower one repeats its frames."""
    channels = {'gray': 1, 'rgb24': 3}[fmt]
    size = w * h * channels
    p = subprocess.Popen(['ffmpeg', '-v', 'error', '-nostdin', '-ss', str(start), '-t', str(duration), '-i', str(source),
                          '-an', '-fps_mode', 'passthrough', '-vf', f'scale={w}:{h}:flags=area,fps={CLOCK}', '-f', 'rawvideo', '-pix_fmt', fmt, '-'],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        while True:
            b = p.stdout.read(size)
            if len(b) < size:
                break
            yield np.frombuffer(b, np.uint8).reshape((h, w, channels) if channels > 1 else (h, w))
    finally:
        p.stdout.close(); err = p.stderr.read().decode('utf-8', 'replace'); p.stderr.close(); p.wait()
    if p.returncode:
        raise ContractError('Decoding the reference failed: ' + err[-1500:])


def _norm(x):
    x = x.astype(np.float32); x -= x.mean(); sd = x.std()
    return x / sd if sd > 1e-3 else x * 0


def _ncc(a, b):
    return float((a * b).mean())


def _frame_look(rgb):
    x = rgb.astype(np.float32) / 255; L = x @ LW; p = np.percentile(L, [2, 25, 50, 75, 98])
    mx, mn = x.max(-1), x.min(-1); sat = float(np.where(mx > 1e-4, (mx - mn) / np.maximum(mx, 1e-4), 0).mean())
    sh = x[L <= p[1]].mean(0); hi = x[L >= p[3]].mean(0)
    return np.r_[p * 255, sat, (sh - sh.mean()) * 255, (hi - hi.mean()) * 255]


LOOK_KEYS = ('p2', 'p25', 'p50', 'p75', 'p98', 'saturation', 'shadow_r', 'shadow_g', 'shadow_b', 'highlight_r', 'highlight_g', 'highlight_b')


def _look_dict(rows):
    m = np.median(np.asarray(rows), 0)
    return {k: round(float(v), 3 if k == 'saturation' else 1) for k, v in zip(LOOK_KEYS, m)}


def detect_cuts(thumbs, hists, lumas, fps, structure=.3, colour=.18, min_gap=None):
    """thumbs: brightness-normalised grey thumbnails; hists: normalised hue/saturation histograms; lumas: mean luma.
    A cut changes both the picture's structure and its colour distribution (flicker, whips, spins and blur bursts inside
    a shot change the structure only). A step in brightness with little change of structure, or a change whose picture
    comes back a few frames later, is a dip. Returns [{frame, kind, structure, colour, luma_ratio}]."""
    n = len(thumbs); min_gap = min_gap or max(3, int(round(fps * .1)))
    st, co = np.zeros(n), np.zeros(n)
    for i in range(1, n):
        st[i] = 1 - _ncc(thumbs[i - 1], thumbs[i]); co[i] = .5 * float(np.abs(hists[i] - hists[i - 1]).sum())
    ratio = np.ones(n); ratio[1:] = (np.asarray(lumas[1:]) + 1) / (np.asarray(lumas[:-1]) + 1)
    out, last = [], -10 ** 9
    for i in range(1, n):
        lo, hi = max(1, i - min_gap), min(n, i + min_gap + 1)
        cut = st[i] >= structure and co[i] >= colour and st[i] + co[i] >= (st[lo:hi] + co[lo:hi]).max()
        near = slice(max(1, i - 2), min(n, i + 3))      # brightness steps are sharp: the largest within 2 frames
        step = abs(np.log(ratio[i])) >= np.log(1.35) and st[i] < structure and abs(np.log(ratio[i])) >= np.abs(np.log(ratio[near])).max()
        if not (cut or step) or i - last < min_gap:
            continue
        kind = 'dip' if step else 'cut'
        if cut:   # the same picture on both sides, past any flash or blur: a dip after all
            pairs = [(i - k, j) for k in (1, 2, 3) if i - k >= 0 for j in range(i + 2, min(n, i + 2 + min_gap * 2))]
            if max((_ncc(thumbs[a], thumbs[b]) for a, b in pairs), default=-1.) > .8:
                kind = 'dip'
        out.append({'frame': i, 'kind': kind, 'structure': round(float(st[i]), 3), 'colour': round(float(co[i]), 3),
                    'luma_ratio': round(float(ratio[i]), 3)})
        last = i
    return out


def _cadence(diffs, fps):
    """How often the underlying picture steps: a frame changing clearly more than both neighbours is a step, and the
    rate is the frame rate over the mean gap between steps (gaps of 1-4 frames). 24p material on a 60p clock steps
    2, 3, 2, 3 frames apart even when effects move on every frame."""
    d = np.asarray(diffs, float); n = len(d)
    if n < 8:
        return None
    peak = np.zeros(n, bool)
    for i in range(1, n - 1):
        peak[i] = d[i] > 1 and d[i] > 1.5 * max(d[i - 1], d[i + 1])
    idx = np.flatnonzero(peak); gaps = np.diff(idx); regular = gaps[(gaps >= 1) & (gaps <= 4)]
    rate = float(fps / regular.mean()) if len(regular) >= 4 else None
    near = min((23.976, 24, 25, 29.97, 30, 50, 59.94, 60), key=lambda b: abs(rate - b) / b) if rate else None
    base = near if near and abs(rate - near) / near < .06 else None
    a = int(idx[0]) if len(idx) else 0
    return {'pictures_per_second': round(rate, 2) if rate else None, 'base_fps': base,
            'gap_counts': {str(k): int((regular == k).sum()) for k in (1, 2, 3, 4)},
            'regular_share': round(len(regular) / max(1, len(gaps)), 2),
            'pattern': ''.join('n' if q else '.' for q in peak[a:a + 40]), 'pattern_start_frame': a,
            'note': 'n = the picture steps on this frame. 24p material on a 60p clock steps 2 and 3 frames apart '
                    '(gap_counts 2 and 3 about equal); regular_share is low where frames move continuously (optical-flow slow motion).'}


def _specks(g, cv2):
    hp = g.astype(np.float32) - cv2.medianBlur(g, 5).astype(np.float32)
    m = (hp > 18).astype(np.uint8)
    k, lab, st, _ = cv2.connectedComponentsWithStats(m, 8)
    small = np.zeros(k, bool); small[1:] = (st[1:, 4] >= 2) & (st[1:, 4] <= 40) & (st[1:, 2] <= 9) & (st[1:, 3] <= 9)
    return cv2.dilate(small[lab].astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)


def _spectrum(cv2, y0, mask):
    v = []
    for s in (.7, 1.5, 3, 6, 10, 18):
        y = cv2.GaussianBlur(y0, (0, 0), s, borderType=cv2.BORDER_REFLECT)
        v.append(np.hypot(cv2.Sobel(y, cv2.CV_32F, 1, 0), cv2.Sobel(y, cv2.CV_32F, 0, 1))[mask].mean())
    v = np.maximum(np.array(v), 1e-6)
    return np.log(v[:-1] / v[-1])


def _transitions(cv2, windows, cuts_used, max_frames):
    """windows: {cut: [grey float32 frames from the cut on]}. Median motion, blur and brightening across cuts."""
    H, W = next(iter(windows.values()))[0].shape
    cen = np.array([W / 2, H / 2, 1.])
    mask = np.zeros((H, W), bool); m = max(2, H // 40); mask[m:-m, m:-m] = True
    radii = np.r_[0, np.geomspace(.25, 30, 48)]          # blur radii in analysis px
    motion, blur, lift = [], [], []
    for c in cuts_used:
        F = windows[c]; n = len(F)
        rows = []
        for i in range(1, n):
            x = _norm(cv2.GaussianBlur(F[i - 1], (0, 0), 2)); y = _norm(cv2.GaussianBlur(F[i], (0, 0), 2))
            try:
                cc, M = cv2.findTransformECC(x, y, np.eye(2, 3, dtype=np.float32), cv2.MOTION_AFFINE, (3, 80, 1e-5), None, 5)
                s = float(np.sqrt(abs(np.linalg.det(M[:, :2])))); d = (M @ cen - cen[:2]) / H
                rows.append([s, d[0], d[1]])
            except cv2.error:
                rows.append([np.nan] * 3)
        motion.append(rows + [[np.nan] * 3] * (max_frames - len(rows)))
        rest = F[-1]
        cal = np.array([_spectrum(cv2, cv2.GaussianBlur(rest, (0, 0), r, borderType=cv2.BORDER_REFLECT) if r > 0 else rest, mask) for r in radii])
        b = [float(radii[int(np.argmin(((cal - _spectrum(cv2, f, mask)) ** 2).sum(1)))]) / H for f in F]
        blur.append(b + [np.nan] * (max_frames + 1 - len(b)))
        base = max(float(rest.mean()), 1.)
        e = [float(f.mean()) / base for f in F]
        lift.append(e + [np.nan] * (max_frames + 1 - len(e)))
    A = np.array(motion, float)                         # cuts x steps x (s, dx, dy): the move from frame i to i + 1
    med = np.nanmedian(A, 0); count = np.sum(~np.isnan(A[:, :, 0]), 0)
    N = int(max([i + 1 for i in range(len(count)) if count[i] >= max(3, len(cuts_used) // 3)] or [0]))
    S, X, Y = [1.] * (N + 1), [0.] * (N + 1), [0.] * (N + 1)
    for i in range(N - 1, -1, -1):                      # frame i + 1 = s (frame i - centre) + centre + d, back from rest
        s, dx, dy = med[i]
        S[i] = S[i + 1] / s; X[i] = (X[i + 1] - dx) / s; Y[i] = (Y[i + 1] - dy) / s
    Bm = np.nanmedian(np.array(blur, float), 0)[:N + 1]; Em = np.nanmedian(np.array(lift, float), 0)[:N + 1]
    q = lambda a, lo, hi: [round(float(np.clip(v, lo, hi)), 4) for v in a]
    curve = {'scale': q(S, .05, 20), 'dx': q(X, -5, 5), 'dy': q(Y, -5, 5), 'blur': q(Bm, 0, .5), 'exposure': q(Em, 0, 8)}
    raw = {'motion_steps': np.round(A, 5).tolist(), 'blur': np.round(np.array(blur, float), 5).tolist(),
           'brightness_ratio': np.round(np.array(lift, float), 4).tolist()}
    return curve, N + 1, raw


def measure(source, out, start, duration, measures, max_transition_frames=36):
    """Measure a reference video window; writes measure.json in `out` and returns the summary."""
    cv2 = _cv()
    number(start, 'start', 0); number(duration, 'duration', .01, 120)
    number(max_transition_frames, 'max_transition_frames', 4, 120, integer=True)
    measures = list(dict.fromkeys(measures))
    bad = [m for m in measures if m not in MEASURES]
    if bad or not measures:
        raise ContractError(f'measure: one or more of {", ".join(MEASURES)}')
    source_fps, sw, sh = _probe(source); fps = CLOCK
    out.mkdir(parents=True, exist_ok=True)
    tw = 192; th = max(2, int(round(tw * sh / sw / 2)) * 2)
    thumbs, hists, lumas, diffs, looks, prev = [], [], [], [], [], None
    for rgb in _frames(source, start, duration, tw, th, 'rgb24'):
        g = (rgb.astype(np.float32) @ LW)
        thumbs.append(_norm(cv2.resize(g, (48, max(2, int(48 * th / tw))), interpolation=cv2.INTER_AREA)))
        h = cv2.calcHist([cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)], [0, 1], None, [16, 8], [0, 180, 0, 256]).ravel()
        hists.append(h / max(float(h.sum()), 1.)); lumas.append(float(g.mean()))
        diffs.append(float(np.abs(g - prev).mean()) if prev is not None else 0.); prev = g
        if 'look' in measures:
            looks.append(_frame_look(rgb))
    n = len(thumbs)
    if n < 2:
        raise ContractError('The window holds fewer than two frames')
    cuts = detect_cuts(thumbs, hists, lumas, fps)
    for c in cuts:
        c['time'] = round(start + c['frame'] / fps, 4)
    real = [c['frame'] for c in cuts if c['kind'] == 'cut']
    report = {'source': str(source), 'start': start, 'duration': round(n / fps, 4), 'fps': fps,
              'source_fps': round(source_fps, 4), 'frames': n,
              'note': 'Measured on a 60-fps clock (a slower source repeats frames). Frame numbers count from the first frame '
                      'of the window. Estimates: verify them on the frames.'}
    summary = {'fps': fps, 'source_fps': report['source_fps'], 'frames': n}
    if 'cuts' in measures or 'transitions' in measures or 'look' in measures:
        report['cuts'] = cuts
        summary['cuts'] = [{k: c[k] for k in ('frame', 'time', 'kind')} for c in cuts]
    if 'cadence' in measures:
        report['cadence'] = summary['cadence'] = _cadence(diffs, fps)
    if 'look' in measures:
        bounds = [0] + real + [n]
        report['look'] = summary['look'] = {
            'overall': _look_dict(looks),
            'shots': [{'f0': a, 'f1': b, **_look_dict(looks[a:b])} for a, b in zip(bounds, bounds[1:]) if b > a]}
    if 'textures' in measures or 'transitions' in measures:
        gw = 640; gh = max(2, int(round(gw * sh / sw / 2)) * 2)
        ww = 384; wh = max(2, int(round(ww * sh / sw / 2)) * 2)
        nxt = {c: (real + [n])[i + 1] for i, c in enumerate(real)}
        used = [c for c in real if nxt[c] - c >= 12]
        want = {c: min(max_transition_frames, nxt[c] - c - 2) for c in used}
        windows = {c: [] for c in used}
        recent, overlaps, counts = [], [[] for _ in range(6)], []
        for f, g in enumerate(_frames(source, start, duration, gw, gh, 'gray')):
            if 'textures' in measures:
                m = _specks(g, cv2); counts.append(int(m.sum()))
                if m.sum() >= 20:
                    for k, r in enumerate(reversed(recent[-6:])):
                        overlaps[k].append(float((m & r).sum() / m.sum()))
                recent = (recent + [m])[-6:]
            for c in used:
                if c <= f <= c + want[c]:
                    windows[c].append(cv2.resize(g, (ww, wh), interpolation=cv2.INTER_AREA).astype(np.float32))
        if 'textures' in measures:
            present = int(np.median(counts)) if counts else 0
            if present >= 20 and overlaps[0]:
                lag = [round(float(np.mean(o)), 3) if o else 0. for o in overlaps]
                rate = fps * (1 - lag[0])                 # the specks change wherever consecutive frames do not share them
                report['textures'] = summary['textures'] = {
                    'speck_pixels_per_frame': present, 'overlap_by_lag': lag, 'speck_pictures_per_second': round(rate, 2),
                    'speck_frames': round(fps / rate, 2) if rate > 0 else None,
                    'note': 'overlap_by_lag[k]: the mean share of a frame\'s specks still there k + 1 frames later. Specks of a '
                            '24p overlay on a 60p clock change on 2 frames in 5: overlap 0.6 at lag 1, 24 pictures a second. '
                            'Bright points in the footage itself persist too and read slower.'}
            else:
                report['textures'] = summary['textures'] = {'speck_pixels_per_frame': present, 'note': 'No persistent small bright specks found.'}
        if 'transitions' in measures:
            if len(used) < 3:
                report['transitions'] = summary['transitions'] = {'cuts_used': len(used), 'note': 'Fewer than three cuts with 12+ frames after them; nothing to average.'}
            else:
                curve, frames, raw = _transitions(cv2, {c: windows[c] for c in used}, used, max_transition_frames)
                report['transitions'] = {'cuts_used': used, 'frames': frames, 'local_curve': curve, 'per_cut': raw}
                summary['transitions'] = {'cuts_used': len(used), 'frames': frames, 'local_curve': curve,
                                          'note': 'Median across cuts, frame 0 = the cut. Use as a shot fx or timeline post '
                                                  '{"local_curve": ...}; exposure carries all the measured brightening: lower it '
                                                  'and raise glow to move part of it into a bloom.'}
    write_json(out / 'measure.json', report)
    summary['report'] = str(out / 'measure.json')
    return summary
