"""Reference energy measurement (audit F-AUD-004): cuts, flashes, shake bursts, pans and hits with ready timeline
entries, per-second rates, a 0.5 s energy curve, and a check of a render against a reference.

Method: frames are decoded to
160 px wide greyscale and held (duplicate) frames are set aside, so 30 fps content in a 60 fps file measures the
same as at 30 fps. Between consecutive distinct frames: mean absolute difference, grey-histogram distance and the
whole-frame shift from phase correlation (OpenCV) with its peak response as reliability.
  * flash: a run of up to 4 frames (longer runs are split) whose luma stands >= 25 levels above both the level before
    it and the steady level after it (white), or below both (black);
  * cut: a distinct-frame step whose histogram distance and pixel difference both spike over their local level and
    whose phase-correlation peak is low (not the same content shifted), or a flash whose surrounding content differs;
  * shake: reliable shifts whose jitter (shift minus its 5-step moving average) exceeds 1.5 px at 160 px, skipping
    cuts and flashes; bursts are grouped, amplitudes reported in pixels of a `canvas_w`-wide canvas;
  * pan: sustained smoothed motion; hit: motion-energy peak.
"""
import json
import subprocess

import numpy as np

from .contracts import ContractError

W160 = 160


def frames_gray(path, start=0.0, duration=None):
    probe = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height,r_frame_rate',
                            '-of', 'json', str(path)], capture_output=True, stdin=subprocess.DEVNULL, text=True).stdout
    info = json.loads(probe or '{}').get('streams')
    if not info:
        raise ContractError(f'No video stream to measure in {path}')
    w, h = info[0]['width'], info[0]['height']; num, den = (int(v) for v in info[0]['r_frame_rate'].split('/'))
    fps = num / den if den else 30.0
    H = max(2, int(round(h * W160 / w / 2)) * 2)
    args = ['ffmpeg', '-nostdin', '-v', 'error', '-ss', f'{start:.6f}', '-i', str(path)]
    if duration is not None:
        args += ['-t', f'{duration:.6f}']
    args += ['-vf', f'scale={W160}:{H}:flags=area,format=gray', '-f', 'rawvideo', '-']
    raw = subprocess.run(args, capture_output=True, stdin=subprocess.DEVNULL).stdout
    n = len(raw) // (W160 * H)
    if n < 3:
        raise ContractError('Need at least three video frames to measure')
    return np.frombuffer(raw[:n * W160 * H], dtype=np.uint8).reshape(n, H, W160).astype(np.float32), fps


def _runs(mask):
    idx = np.flatnonzero(mask)
    return np.split(idx, np.flatnonzero(np.diff(idx) > 1) + 1) if len(idx) else []


def _flashes(luma):
    """(start, n, kind, frame before, frame after) for runs of up to 4 frames standing out from both the level before
    the rise and the steady level 4-8 frames after it (a flash over a cut settles at the new shot's level)."""
    n = len(luma); out = []
    for sign, kind in ((1, 'white'), (-1, 'black')):
        i = 1
        while i < n - 1:
            pre = luma[i - 1]
            if sign * (luma[i] - pre) < 25:
                i += 1; continue
            post = float(np.median(luma[i + 4:i + 9])) if i + 4 < n else float(pre)
            ref = max(pre, post) if sign > 0 else min(pre, post)
            peak = luma[i:i + 8].max() if sign > 0 else luma[i:i + 8].min()
            thr = ref + sign * max(12.0, .25 * abs(peak - ref))
            j = i
            while j < n and j - i < 8 and sign * (luma[j] - thr) >= 0:
                j += 1
            if j > i and sign * (peak - ref) >= 25 and j - i < 8:
                for c in range(i, j, 4):
                    out.append((c, min(4, j - c), kind, i - 1, min(n - 1, j)))
                i = j
            else:
                i += 1
    return sorted(out)


def measure(path, start=0.0, duration=None, canvas_w=1080):
    import cv2
    g, fps = frames_gray(path, start, duration)
    n = len(g)
    luma = g.mean(axis=(1, 2))
    diff = np.r_[0, np.abs(np.diff(g, axis=0)).mean(axis=(1, 2))]
    distinct = [0] + [i for i in range(1, n) if diff[i] > .35]
    hist = lambda im: np.histogram(im, bins=32, range=(0, 256))[0] / im.size
    win = cv2.createHanningWindow((g.shape[2], g.shape[1]), cv2.CV_32F)
    m = len(distinct)
    dpix, dhist, shift, resp = np.zeros(m), np.zeros(m), np.zeros((m, 2)), np.zeros(m)
    for k in range(1, m):
        a, b = g[distinct[k - 1]], g[distinct[k]]
        dpix[k] = float(np.abs(b - a).mean()); dhist[k] = .5 * float(np.abs(hist(b) - hist(a)).sum())
        (dx, dy), r = cv2.phaseCorrelate(a.copy(), b.copy(), win)   # phaseCorrelate writes into its inputs
        shift[k] = (dx, dy); resp[k] = r
    t = lambda i: round(start + i / fps, 3)
    pos = {f: k for k, f in enumerate(distinct)}
    flashes, flash_frames, cut_frames = [], set(), set()
    for s, count, kind, before, after in _flashes(luma):
        flashes.append({'t': t(s), 'n': int(count), 'type': kind, 'edl': {'specials': {'t0': t(s), 'n': int(count), 'type': kind}}})
        flash_frames.update(range(s, s + count))
        if after < n and .5 * float(np.abs(hist(g[after]) - hist(g[before])).sum()) > .25:
            cut_frames.add(min(f for f in range(before + 1, after + 1)))   # content changed across the flash
    starts = {f[0] for f in _flashes(luma)}
    ends = {f[0] + f[1] for f in _flashes(luma)}
    for k in range(1, m):
        f = distinct[k]
        if f in starts or f in ends:   # a flash's own rise and fall are not cuts (content change is checked above)
            continue
        lo, hi = max(1, k - 6), min(m, k + 7)
        near = [j for j in range(lo, hi) if j != k]
        # a low percentile keeps a dense run of cuts from raising its own reference level
        mp, mh = (float(np.percentile(dpix[near], 30)), float(np.percentile(dhist[near], 30))) if near else (0.0, 0.0)
        # a camera move keeps a high phase-correlation peak (same content shifted); a cut does not (all observed
        # cuts <= 0.15, motion false positives 0.47-0.97)
        tone_change = dhist[k] > .15 and dhist[k] > 2.5 * max(mh, .02)
        if dpix[k] > 12 and dpix[k] > 3 * max(mp, 1.0) and resp[k] < .2 and (tone_change or (dpix[k] > 25 and resp[k] < .1)):
            cut_frames.add(f)
    cuts = sorted(cut_frames)
    # motion on distinct frames, away from cuts and flashes
    bad = set()
    for f in set(cuts) | flash_frames:
        k = pos.get(f, None)
        if k is None:
            k = int(np.searchsorted(distinct, f))
        bad.update(range(max(0, k - 2), min(m, k + 3)))
    valid = (resp > .08) & np.array([k not in bad for k in range(m)]); valid[0] = False
    K = 5; pad = np.pad(shift, ((K // 2, K // 2), (0, 0)), mode='edge')
    smooth = np.stack([np.convolve(pad[:, c], np.ones(K) / K, mode='valid') for c in (0, 1)], 1)
    jitter = np.linalg.norm(shift - smooth, axis=1)
    span = np.r_[1, np.diff(distinct)]                       # output frames each distinct step covers
    shake = valid & (jitter > 1.5)
    scale = canvas_w / W160
    shakes = []
    for grp in np.split(np.flatnonzero(shake), np.flatnonzero(np.diff(np.flatnonzero(shake)) > 2) + 1) if shake.any() else []:
        f0 = distinct[grp[0] - 1] + 1 if grp[0] else distinct[grp[0]]
        frames = int(span[grp].sum()); d = round(frames / fps, 3); amp = float(np.percentile(jitter[grp], 90)) * scale
        if frames < 2:   # a single-frame blip is not a burst
            continue
        shakes.append({'t': t(f0), 'd': d, 'frames': frames, 'amp_px': round(amp, 1),
                       'edl': {'cam': {'shake': {'at': '<t - shot start>', 'd': d, 'amp': [round(amp, 1), round(amp * .8, 1)]}}}})
    per_frame = smooth / span[:, None]                       # px per output frame at 160 px
    speed = np.linalg.norm(per_frame, axis=1)
    moving = valid & (speed > .35)
    pans = []
    for grp in _runs(moving):
        frames = int(span[grp].sum())
        if frames / fps < .25:
            continue
        v = (per_frame[grp] * span[grp, None]).sum(axis=0) / frames
        dx, dy = v[0] * fps / W160, v[1] * fps / g.shape[1]   # image motion as a share of width/height per second = cam.pan dx/dy
        f0 = distinct[grp[0] - 1] + 1 if grp[0] else distinct[grp[0]]
        pans.append({'t': t(f0), 'd': round(frames / fps, 3), 'dir': '→' if dx > 0 else '←',
                     'edl': {'cam': {'pan': {'dx': round(float(dx), 3), 'dy': round(float(dy), 3)}}}})
    energy = np.zeros(n)
    for k in range(1, m):
        if k not in bad:
            energy[distinct[k]] = dpix[k] / span[k]
    thr = energy[energy > 0].mean() + energy[energy > 0].std() if (energy > 0).any() else 1e9
    hits, last = [], -1e9
    for i in range(1, n - 1):
        if energy[i] > thr and energy[i] >= energy[max(0, i - 2):i + 3].max() and i - last >= max(2, int(.066 * fps)):
            hits.append({'t': t(i), 'edl': {'cam': {'punch': {'at': '<t - shot start>'}}}}); last = i
    seconds = n / fps
    curve = [round(float(energy[int(h * fps / 2):int((h + 1) * fps / 2)].mean()), 2) for h in range(int(np.ceil(seconds * 2)))]
    rates = {'fps': round(fps, 3), 'seconds': round(seconds, 3), 'cuts_ps': round(len(cuts) / seconds, 2), 'flashes_ps': round(len(flashes) / seconds, 2),
             'shake_ps': round(int(span[shake].sum()) / seconds, 2), 'jitter_px': round(float(jitter[valid].mean()) if valid.any() else 0.0, 2),
             'move_px': round(float(speed[valid].mean()) if valid.any() else 0.0, 2), 'motion': round(float(energy.mean()), 2),
             'measured_share': round(float(span[valid].sum() / n), 2), 'distinct_frame_share': round(m / n, 2)}
    return {'source': str(path), 'start': start, 'canvas_w': canvas_w, 'rates': rates,
            'flash_mix': {'white': sum(f['type'] == 'white' for f in flashes), 'black': sum(f['type'] == 'black' for f in flashes)},
            'camera_moving_share': round(float(span[moving].sum() / n), 2),
            'events': {'cuts': [{'t': t(i)} for i in cuts], 'flashes': flashes, 'shakes': shakes, 'pans': pans, 'hits': hits},
            'energy_0_5s': curve}


def check(ours, reference, floor=.6, ceiling=None):
    """Per-second rates of a render against a reference: FAIL below floor x reference for measures the reference
    really uses; FAIL when shake frames or jitter exceed max(1.5 x reference, reference + 1 frame/s or 0.5 px); with
    `ceiling`, also FAIL when camera movement or motion energy exceed ceiling x reference (an over-busy edit)."""
    used = {'cuts_ps': .1, 'flashes_ps': .1, 'shake_ps': .5, 'jitter_px': .5, 'move_px': .5, 'motion': .3}
    labels = {'cuts_ps': 'cuts / s', 'flashes_ps': 'flashes / s', 'shake_ps': 'shake frames / s', 'jitter_px': 'jitter px',
              'move_px': 'camera movement px', 'motion': 'motion energy'}
    rows, fails = [], []
    for key, label in labels.items():
        r, o = reference['rates'][key], ours['rates'][key]
        if r < used[key]:
            verdict, ratio = 'n/a (reference barely uses it)', None
        else:
            ratio = round(o / r, 2)
            verdict = 'PASS' if o >= floor * r else 'FAIL (too little)'
        if key in ('shake_ps', 'jitter_px') and o > max(1.5 * r, r + (1 if key == 'shake_ps' else .5)):
            verdict = 'FAIL (too much)'
        if ceiling and key in ('move_px', 'motion') and r >= used[key] and o > ceiling * r:
            verdict = 'FAIL (too much)'
        if verdict.startswith('FAIL'):
            fails.append(label)
        rows.append({'measure': label, 'reference': r, 'ours': o, 'ratio': ratio, 'verdict': verdict})
    return {'floor': floor, 'ceiling': ceiling, 'rows': rows, 'fails': fails, 'pass': not fails}


def chart(result, path, width=1400):
    """Per-0.5 s motion energy with cuts (white), flashes (yellow), shakes (red) and pans (blue) marked."""
    from PIL import Image, ImageDraw
    secs = result['rates']['seconds']; H = 220
    im = Image.new('RGB', (width, H), (18, 18, 22)); d = ImageDraw.Draw(im)
    X = lambda t: int((t - result['start']) / secs * (width - 1))
    curve = result['energy_0_5s']; top = max(curve) or 1
    for i, v in enumerate(curve):
        d.rectangle((X(result['start'] + i / 2), H - 20 - v / top * 150, X(result['start'] + (i + 1) / 2) - 1, H - 20), fill=(70, 90, 120))
    ev = result['events']
    for p in ev['pans']:
        d.rectangle((X(p['t']), 22, X(p['t'] + p['d']), 30), fill=(80, 140, 255))
    for sh in ev['shakes']:
        d.rectangle((X(sh['t']), 32, max(X(sh['t']) + 2, X(sh['t'] + sh['d'])), 40), fill=(255, 80, 80))
    for c in ev['cuts']:
        d.line((X(c['t']), 44, X(c['t']), H - 20), fill=(235, 235, 235))
    for f in ev['flashes']:
        d.rectangle((X(f['t']) - 2, 44, X(f['t']) + 2, 60), fill=(255, 230, 80))
    for s in range(int(secs) + 1):
        d.text((X(result['start'] + s) + 2, H - 16), str(s), fill=(150, 150, 150))
    r = result['rates']
    d.text((6, 4), f"cuts/s {r['cuts_ps']}  flashes/s {r['flashes_ps']}  shake frames/s {r['shake_ps']}  jitter {r['jitter_px']}px  move {r['move_px']}px", fill=(240, 240, 240))
    im.save(path)
    return str(path)
