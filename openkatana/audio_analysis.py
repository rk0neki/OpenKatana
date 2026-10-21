"""Music analysis for cutting (audit F-AUD-003): tempo, a constant beat grid fitted to onsets, downbeats, onsets,
level-based sections, silence and EBU R128 loudness. numpy + FFmpeg only; no models or downloads.

Method (independent, textbook techniques): log-compressed spectral-flux onset envelope (full band and < 150 Hz);
tempo candidates from the envelope autocorrelation, scored by harmonic comb support and a log-tempo prior centred on
120 BPM (one-octave width); the beat grid is a weighted fit of period and phase to detected onsets, refined by least
squares; downbeats pick the bar phase (4 beats) with the most low-band and onset energy; sections split where the
beat-level loudness steps by >= 3 dB. Results are estimates for planning cuts, not a guarantee of musical structure.
"""
import json
import math
import re
import subprocess
from pathlib import Path

import numpy as np

from .contracts import ContractError

SR, N_FFT, HOP = 22050, 1024, 256   # a 1024-sample window keeps onset timing bias near 1 ms (2048: ~9 ms early)


def decode(path, start=0.0, duration=None, sr=SR):
    args = ['ffmpeg', '-nostdin', '-v', 'error', '-ss', f'{start:.6f}', '-i', str(path)]
    if duration is not None:
        args += ['-t', f'{duration:.6f}']
    args += ['-map', '0:a:0', '-ac', '1', '-ar', str(sr), '-f', 'f32le', '-']
    run = subprocess.run(args, capture_output=True, stdin=subprocess.DEVNULL)
    if run.returncode or not run.stdout:
        raise ContractError(f'No audio stream could be decoded from {Path(path).name}')
    return np.frombuffer(run.stdout, dtype=np.float32).astype(np.float64)


def spectrogram(x):
    pad = np.pad(x, (N_FFT // 2, N_FFT // 2))
    count = 1 + (len(pad) - N_FFT) // HOP
    idx = np.arange(N_FFT)[None, :] + HOP * np.arange(count)[:, None]
    return np.abs(np.fft.rfft(pad[idx] * np.hanning(N_FFT)[None, :], axis=1))


def envelopes(mag):
    """Full-band and low-band (< 150 Hz) onset strength per hop (frame i is centred at i*HOP/SR)."""
    logm = np.log1p(1000 * mag)
    flux = np.maximum(0, np.diff(logm, axis=0, prepend=logm[:1]))
    freqs = np.fft.rfftfreq(N_FFT, 1 / SR)
    full, low = flux.sum(axis=1), flux[:, freqs < 150].sum(axis=1)
    k = max(1, int(.4 * SR / HOP))   # remove the slow trend so the autocorrelation sees accents
    trend = np.convolve(full, np.ones(k) / k, mode='same')
    return full, low, np.maximum(0, full - trend)


def peaks(env, min_gap_s=.05, delta=None):
    """Onset times (s) and strengths: local maxima above a moving median + delta, parabolic sub-hop refinement."""
    k = max(3, int(.25 * SR / HOP)) | 1
    pad = np.pad(env, (k // 2, k // 2), mode='edge')
    med = np.median(np.lib.stride_tricks.sliding_window_view(pad, k), axis=1)
    delta = env.std() * .5 if delta is None else delta
    out, last = [], -1e9
    for i in range(1, len(env) - 1):
        if env[i] >= env[i - 1] and env[i] > env[i + 1] and env[i] > med[i] + delta:
            a, b, c = env[i - 1], env[i], env[i + 1]
            off = .5 * (a - c) / (a - 2 * b + c) if (a - 2 * b + c) != 0 else 0
            t = (i + off) * HOP / SR
            if t - last >= min_gap_s:
                out.append((t, float(b))); last = t
            elif b > out[-1][1]:
                out[-1] = (t, float(b)); last = t
    return out


def prior(bpm):
    return math.exp(-.5 * math.log2(bpm / 120) ** 2)


def tempo_candidates(onset_env, lo=55, hi=240):
    e = onset_env - onset_env.mean()
    n = len(e)
    acf = np.fft.irfft(np.abs(np.fft.rfft(e, 2 * n)) ** 2)[:n]
    acf /= acf[0] if acf[0] > 0 else 1
    fps = SR / HOP
    lags = np.arange(int(fps * 60 / hi), min(n - 1, int(fps * 60 / lo)) + 1)
    cands = []
    for L in lags[1:-1]:
        if acf[L] > acf[L - 1] and acf[L] >= acf[L + 1] and acf[L] > 0:
            a, b, c = acf[L - 1], acf[L], acf[L + 1]
            off = .5 * (a - c) / (a - 2 * b + c) if (a - 2 * b + c) != 0 else 0
            lag = L + off
            comb = sum(np.interp(lag * h, np.arange(n), acf) / h for h in (1, 2, 3, 4) if lag * h < n)
            bpm = 60 * fps / lag
            cands.append({'bpm': round(bpm, 2), 'support': round(float(comb), 4), 'prior': round(prior(bpm), 3),
                          'score': round(float(comb) * prior(bpm), 4)})
    return sorted(cands, key=lambda c: -c['score'])


def fit_grid(onsets, period0, duration, sigma=.02):
    """Weighted grid search of period (+-2 %) and phase, then least-squares refinement on matched onsets."""
    t = np.array([o[0] for o in onsets]); w = np.array([o[1] for o in onsets]); w = w / w.max()
    best = (-1, period0, 0.0)
    for P in np.linspace(period0 * .98, period0 * 1.02, 161):
        phases = np.arange(0, P, .001)
        d = (t[None, :] - phases[:, None]) % P
        d = np.minimum(d, P - d)
        score = (w[None, :] * np.exp(-d ** 2 / (2 * sigma ** 2))).sum(axis=1)
        i = int(score.argmax())
        if score[i] > best[0]:
            best = (float(score[i]), float(P), float(phases[i]))
    _, P, phi = best
    for _ in range(3):   # least squares on onsets within 40 ms of the grid
        k = np.round((t - phi) / P)
        r = t - (phi + k * P)
        m = np.abs(r) < .04
        if m.sum() < 4:
            break
        A = np.stack([np.ones(m.sum()), k[m]], 1)
        sol = np.linalg.lstsq(A * w[m, None], t[m] * w[m], rcond=None)[0]
        phi, P = float(sol[0]), float(sol[1])
    k = np.round((t - phi) / P); r = t - (phi + k * P); m = np.abs(r) < .04
    phi = phi - P * math.floor(phi / P + .5)   # first beat in [-P/2, P/2)
    drift = float(np.polyfit(t[m], r[m], 1)[0] * duration * 1000) if m.sum() > 3 else 0.0
    return P, phi, {'onsets_used': int(m.sum()), 'median_abs_err_ms': round(float(np.median(np.abs(r[m]))) * 1000, 3) if m.any() else None,
                    'drift_ms': round(drift, 3)}


def offbeat_support(onsets, P, phi, sigma=.02):
    """Onset strength on the half-period offbeats relative to the beats of a grid (high = the faster octave is the beat)."""
    t = np.array([o[0] for o in onsets]); w = np.array([o[1] for o in onsets])
    g = lambda shift: float((w * np.exp(-(np.minimum((t - phi - shift) % P, P - (t - phi - shift) % P)) ** 2 / (2 * sigma ** 2))).sum())
    on = g(0.0)
    return g(P / 2) / on if on > 0 else 0.0


def choose_octave(onsets, cands, duration, lo=55, hi=240):
    """Start from the best-scoring candidate; double while the offbeats carry at least half the on-beat strength,
    halve when every other beat is nearly empty."""
    bpm = cands[0]['bpm']; trail = []
    for _ in range(3):
        P, phi, _ = fit_grid(onsets, 60 / bpm, duration)
        support = offbeat_support(onsets, P, phi)
        trail.append({'bpm': round(60 / P, 2), 'offbeat_support': round(support, 3)})
        if support >= .5 and bpm * 2 <= hi:
            bpm *= 2; continue
        if bpm / 2 >= lo:
            Ps, phis, _ = fit_grid(onsets, 2 * P, duration)
            if offbeat_support(onsets, Ps, phis) < .25:
                trail.append({'bpm': round(60 / Ps, 2), 'offbeat_support': round(offbeat_support(onsets, Ps, phis), 3), 'halved': True})
                bpm = 60 / Ps; continue
        break
    return bpm, trail


def loudness(path, start, duration):
    args = ['ffmpeg', '-nostdin', '-hide_banner', '-nostats', '-ss', f'{start:.6f}', '-i', str(path)]
    if duration is not None:
        args += ['-t', f'{duration:.6f}']
    args += ['-map', '0:a:0', '-af', 'ebur128=peak=true', '-f', 'null', '-']
    text = subprocess.run(args, capture_output=True, stdin=subprocess.DEVNULL, text=True, errors='replace').stderr
    summary = text[text.rfind('Summary:'):]
    grab = lambda key: (lambda m: float(m.group(1)) if m else None)(re.search(key + r':\s+(-?[\d.]+)', summary))
    return {'I': grab('I'), 'LRA': grab('LRA'), 'TP': grab('Peak'), 'threshold': grab('Threshold'),
            'unit': {'I': 'LUFS', 'LRA': 'LU', 'TP': 'dBTP'}, 'tool': 'ffmpeg ebur128=peak=true'}


def analyze(path, start=0.0, duration=None, fps=None, beats_per_bar=4):
    x = decode(path, start, duration)
    if len(x) < SR:
        raise ContractError('Need at least one second of audio to analyse')
    dur = len(x) / SR
    mag = spectrogram(x)
    full, low, detrended = envelopes(mag)
    onset_list = peaks(full)
    low_list = peaks(low, min_gap_s=.1, delta=1.5 * low.std())
    if len(onset_list) < 8:
        raise ContractError('Too few onsets for a beat grid (fewer than 8); the recording may be silent or arrhythmic')
    cands = tempo_candidates(detrended)
    if not cands:
        raise ContractError('No tempo candidate between 55 and 240 BPM')
    chosen = cands[0]
    bpm0, octave_trail = choose_octave(onset_list, cands, dur)
    P, phi, grid = fit_grid(onset_list, 60 / bpm0, dur)
    # beats carry the low end (kick/bass); if the half-period-shifted grid has clearly more low-band energy, the fit
    # locked onto offbeats (e.g. hi-hats, which have more broadband flux than a kick)
    lowsum = lambda ph: sum(float(low[max(0, min(len(low) - 1, int(round((ph + k * P) * SR / HOP))))]) for k in range(int(dur / P) + 1))
    if lowsum(phi + P / 2) > 1.25 * lowsum(phi):
        phi = phi + P / 2 - P * math.floor((phi + P / 2) / P + .5)
        grid['phase_shifted_to_low_band'] = True
        res = [t - phi - P * round((t - phi) / P) for t, _ in low_list]
        res = [r for r in res if abs(r) < .04]
        if len(res) >= 4:   # re-centre on the low-band (kick) onsets
            phi += float(np.median(res))
    bpm = 60 / P
    beats = [round(phi + k * P, 4) for k in range(int((dur - phi) / P) + 1) if phi + k * P < dur]
    strengths = np.array([o[1] for o in onset_list])
    strong = [o for o in onset_list if o[1] >= strengths.mean() + .5 * strengths.std()]
    near = lambda t, grid_p: abs(((t - phi + grid_p / 2) % grid_p) - grid_p / 2) < .04
    grid['strong_on_beat_share'] = round(sum(near(o[0], P) for o in strong) / max(1, len(strong)), 3)
    grid['strong_on_8th_share'] = round(sum(near(o[0], P / 2) for o in strong) / max(1, len(strong)), 3)
    # downbeats: bar phase with the most low-band + full-band energy on its beats
    times = np.arange(len(full)) * HOP / SR
    at = lambda env, t: float(env[max(0, min(len(env) - 1, int(round(t * SR / HOP))))])
    lowv, fullv = low / (low.max() or 1), full / (full.max() or 1)
    scores = [sum(at(lowv, b) + .5 * at(fullv, b) for b in beats[o::beats_per_bar]) / max(1, len(beats[o::beats_per_bar])) for o in range(beats_per_bar)]
    # sections usually start on a downbeat: level steps of >= 3 dB at a beat vote for that bar phase
    for sec in level_sections(x, beats, beats, strong, dur)[1:]:
        k = next((i for i, b in enumerate(beats) if abs(b - sec['t0']) < .05), None)
        if k is not None and sec['step_db'] is not None:
            scores[k % beats_per_bar] += abs(sec['step_db']) / 12 * max(scores)
    order = np.argsort(scores)[::-1]
    bar0 = int(order[0])
    downbeats = beats[bar0::beats_per_bar]
    db_conf = round((scores[order[0]] - scores[order[1]]) / scores[order[0]], 3) if scores[order[0]] > 0 else 0.0
    # octave report
    half = next((c for c in cands if abs(c['bpm'] - bpm / 2) / (bpm / 2) < .04), None)
    double = next((c for c in cands if abs(c['bpm'] - bpm * 2) / (bpm * 2) < .04), None)
    octave = {'chosen': round(bpm, 2), 'half': round(bpm / 2, 2), 'double': round(bpm * 2, 2),
              'half_score': half['score'] if half else 0, 'double_score': double['score'] if double else 0,
              'margin': round(1 - (cands[1]['score'] / chosen['score']), 3) if len(cands) > 1 else 1.0,
              'ambiguous': bool(half and half['score'] > .85 * chosen['score']), 'decision': octave_trail}
    sections = level_sections(x, beats, downbeats, strong, dur)
    silence = silent_spans(x)
    result = {'duration': round(dur, 3), 'source_offset_s': start,
              'time_base': 'seconds from the analysed window start (source time = t + source_offset_s)',
              'bpm': round(bpm, 2), 'period': round(P, 5), 'phase': round(phi, 4), 'confidence': round(chosen['score'] / sum(c['score'] for c in cands[:5]), 3),
              'octave': octave, 'tempo_candidates': cands[:6], 'grid_fit': grid, 'beats': beats, 'downbeats': downbeats,
              'downbeat_confidence': db_conf, 'beats_per_bar': beats_per_bar,
              'onsets': [round(o[0], 4) for o in onset_list], 'strong_onsets': [round(o[0], 4) for o in strong],
              'low_onsets': [round(o[0], 4) for o in low_list], 'sections': sections, 'silence': silence,
              'loudness': loudness(path, start, duration)}
    if fps:
        fr = lambda ts: [max(0, int(round(t * fps))) for t in ts]
        result.update(fps=fps, beat_frames=fr(beats), downbeat_frames=fr(downbeats), strong_onset_frames=fr(result['strong_onsets']))
    return result, (times, full, low, x)


def level_sections(x, beats, downbeats, strong, dur, step_db=3.0):
    def db(t0, t1):
        seg = x[int(t0 * SR):max(int(t0 * SR) + 1, int(t1 * SR))]
        return 20 * math.log10(max(1e-9, float(np.sqrt(np.mean(seg ** 2)))))
    cuts = sorted(set([round(t, 3) for t in downbeats if 1.0 <= t <= dur - 1.0] + [round(o[0], 3) for o in strong if 1.0 <= o[0] <= dur - 1.0]))
    steps = {c: db(c, min(dur, c + 2.0)) - db(max(0.0, c - 2.0), c) for c in cuts}
    # keep the strongest level steps (>= step_db), at least 1 s apart, strongest first
    chosen = []
    for c in sorted(steps, key=lambda c: -abs(steps[c])):
        if abs(steps[c]) >= step_db and all(abs(c - k) >= 1.0 for k in chosen):
            chosen.append(c)
    bounds = [0.0] + sorted(chosen) + [dur]
    levels = [db(a, b) for a, b in zip(bounds, bounds[1:])]
    while len(bounds) > 2:   # merge neighbours whose levels differ by less than step_db
        diffs = [abs(levels[i + 1] - levels[i]) for i in range(len(levels) - 1)]
        i = int(np.argmin(diffs))
        if diffs[i] >= step_db:
            break
        del bounds[i + 1]
        levels = [db(a, b) for a, b in zip(bounds, bounds[1:])]
    top = max(levels)
    out = []
    for i, (a, b) in enumerate(zip(bounds, bounds[1:])):
        rel = levels[i] - top
        label = 'loud' if rel > -3 else 'mid' if rel > -12 else 'quiet'
        beat0 = next((k for k, t in enumerate(beats) if abs(t - a) < .04), None)
        out.append({'t0': round(a, 3), 't1': round(b, 3), 'label': label, 'db': round(levels[i], 3), 'rel_db': round(rel, 3),
                    'step_db': round(levels[i] - levels[i - 1], 3) if i else None, 'beat0': beat0})
    return out


def silent_spans(x, floor_db=-50, min_s=.5):
    win = int(.05 * SR)
    n = len(x) // win
    if not n:
        return []
    rms = np.sqrt(np.mean(x[:n * win].reshape(n, win) ** 2, axis=1))
    quiet = 20 * np.log10(np.maximum(rms, 1e-9)) < floor_db
    spans, s = [], None
    for i, q in enumerate(list(quiet) + [False]):
        if q and s is None:
            s = i
        if not q and s is not None:
            if (i - s) * .05 >= min_s:
                spans.append({'t0': round(s * .05, 3), 't1': round(i * .05, 3)})
            s = None
    return spans


def timeline_image(result, curves, path, width=1600):
    """Waveform, onset envelope, beat grid (downbeats bold), strong onsets and sections."""
    from PIL import Image, ImageDraw
    times, full, low, x = curves
    dur = result['duration']; H = 300
    im = Image.new('RGB', (width, H), (18, 18, 22)); d = ImageDraw.Draw(im)
    X = lambda t: int(t / dur * (width - 1))
    colours = {'quiet': (40, 50, 70), 'mid': (60, 70, 50), 'loud': (90, 50, 50)}
    for s in result['sections']:
        d.rectangle((X(s['t0']), 0, X(s['t1']), 18), fill=colours[s['label']]); d.text((X(s['t0']) + 3, 3), f"{s['label']} {s['db']:.1f} dB", fill=(230, 230, 230))
    step = max(1, len(x) // width)
    env = np.abs(x[:step * (len(x) // step)]).reshape(-1, step).max(axis=1)
    for i, v in enumerate(env[:width]):
        d.line((i, 110 - v * 85, i, 110 + v * 85), fill=(90, 120, 160))
    f = full / (full.max() or 1)
    pts = [(X(t), 290 - v * 150) for t, v in zip(times, f) if t <= dur]
    d.line(pts, fill=(220, 200, 90))
    for b in result['beats']:
        d.line((X(b), 20, X(b), 300), fill=(120, 120, 120))
    for b in result['downbeats']:
        d.line((X(b), 20, X(b), 300), fill=(240, 240, 240), width=2)
    for o in result['strong_onsets']:
        d.ellipse((X(o) - 3, 196, X(o) + 3, 202), fill=(255, 90, 90))
    d.text((6, H - 14), f"{result['bpm']} BPM  phase {result['phase']}s  {len(result['beats'])} beats  {result['loudness']['I']} LUFS", fill=(240, 240, 240))
    im.save(path)
    return str(path)
