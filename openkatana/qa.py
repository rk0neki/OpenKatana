"""Technical render QA (audit F-STU-005), written into every render receipt.

Checks (each reports measurements and, when violated, a warning; they never change the render):
  * loudness: integrated LUFS and true peak of the delivered audio (ffmpeg ebur128); warns when true peak > -1.0 dBTP
    or loudness is outside the target window (default -16..-9 LUFS, platform-dependent);
  * photosensitivity: general flashes per second from frame-average relative luminance (a flash = a pair of opposing
    changes of >= 10 % of maximum relative luminance where the darker state is below 0.8, the WCAG 2.x general-flash
    definition applied to the whole frame); warns above 3 flashes in any one-second window;
  * black frames (average luma < 0.03 for >= 0.5 s) and frozen runs (identical frames for >= 1 s) as information;
  * rhythm: share of shot cuts within 40 ms of a beat or half-beat of the delivered audio (needs audio);
  * face crop: frames whose tracked face (eye midpoint and eye distance from the frame trace) extends more than 25 %
    outside the canvas;
  * text safe area: global text anchors outside the central 90 % of the canvas.
Simplifications: the flash test uses the whole-frame average (not the 25 % area rule or the red-flash rule), so
localised flashes are not detected.
"""
import subprocess
from pathlib import Path

import numpy as np


def _gray_frames(movie, width=160):
    import json
    info = json.loads(subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height',
                                      '-of', 'json', str(movie)], capture_output=True, text=True, stdin=subprocess.DEVNULL).stdout)['streams'][0]
    H = max(2, int(round(info['height'] * width / info['width'] / 2)) * 2)
    raw = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(movie), '-vf', f'scale={width}:{H}:flags=area,format=gray', '-f', 'rawvideo', '-'],
                         capture_output=True, stdin=subprocess.DEVNULL).stdout
    n = len(raw) // (width * H)
    return np.frombuffer(raw[:n * width * H], dtype=np.uint8).reshape(n, H, width).astype(np.float32) / 255


def flash_rate(luma_linear, fps, threshold=.1, dark_limit=.8):
    """Max general flashes in any one-second window: hysteresis on frame-average relative luminance registers a
    transition each time the level moves >= threshold away from the last extreme in the opposite direction (the
    darker state below dark_limit); two transitions make one flash."""
    transitions, ref, state = [], float(luma_linear[0]), None
    for i, v in enumerate(map(float, luma_linear)):
        if state != 'up' and v - ref >= threshold and min(v, ref) < dark_limit:
            transitions.append(i); state, ref = 'up', v
        elif state != 'down' and ref - v >= threshold and min(v, ref) < dark_limit:
            transitions.append(i); state, ref = 'down', v
        elif (state == 'up' and v > ref) or (state == 'down' and v < ref):
            ref = v
    win = max(1, int(round(fps)))
    best, at = 0.0, None
    for i, t in enumerate(transitions):
        count = sum(1 for u in transitions[i:] if u < t + win)
        if count / 2 > best:
            best, at = count / 2, t
    return best, at, len(transitions)


def _runs(mask, min_len):
    out, s = [], None
    for i, v in enumerate(list(mask) + [False]):
        if v and s is None:
            s = i
        if not v and s is not None:
            if i - s >= min_len:
                out.append((s, i))
            s = None
    return out


def loudness(movie):
    import re
    text = subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-nostats', '-i', str(movie), '-map', '0:a:0', '-af', 'ebur128=peak=true', '-f', 'null', '-'],
                          capture_output=True, text=True, errors='replace', stdin=subprocess.DEVNULL).stderr
    summary = text[text.rfind('Summary:'):]
    grab = lambda key: (lambda m: float(m.group(1)) if m else None)(re.search(key + r':\s+(-?[\d.]+|-inf)', summary.replace('-inf', '-999')))
    return {'integrated_lufs': grab('I'), 'true_peak_dbtp': grab('Peak'), 'lra': grab('LRA')}


def render_qa(edit, movie, trace, has_audio, lufs_window=(-16.0, -9.0), true_peak_max=-1.0, flash_limit=3.0):
    c = edit['canvas']; fps, W, H = c['fps'], c['w'], c['h']
    g = _gray_frames(movie)
    lum = g.mean(axis=(1, 2)) ** 2.2          # frame-average relative luminance (approximate linearisation)
    warnings, report = [], {}
    rate, at, transitions = flash_rate(lum, fps)
    report['photosensitivity'] = {'max_flashes_per_second': rate, 'at_seconds': round(at / fps, 3) if at is not None else None,
                                  'limit': flash_limit, 'transitions': transitions, 'method': 'whole-frame average; general flash only'}
    if rate > flash_limit:
        warnings.append({'code': 'flash_rate', 'message': f'{rate:g} general flashes in one second at {at / fps:.2f} s exceeds {flash_limit:g}/s (photosensitivity risk)'})
    black = _runs(g.mean(axis=(1, 2)) < .03, int(round(.5 * fps)))
    diffs = np.r_[1.0, np.abs(np.diff(g, axis=0)).mean(axis=(1, 2))]
    frozen = _runs(diffs < 1e-4, int(round(fps)))
    report['black_runs_s'] = [[round(a / fps, 3), round(b / fps, 3)] for a, b in black]
    report['frozen_runs_s'] = [[round(a / fps, 3), round(b / fps, 3)] for a, b in frozen]
    if black:
        warnings.append({'code': 'black_frames', 'message': f'{len(black)} black run(s) of >= 0.5 s: {report["black_runs_s"][:3]}'})
    if frozen:
        warnings.append({'code': 'frozen_frames', 'message': f'{len(frozen)} identical-frame run(s) of >= 1 s (fine if authored freezes): {report["frozen_runs_s"][:3]}'})
    cuts = [s['f0'] / fps for s in edit['shots'][1:]]
    if has_audio:
        report['loudness'] = loudness(movie)
        tp, i = report['loudness']['true_peak_dbtp'], report['loudness']['integrated_lufs']
        if tp is not None and tp > true_peak_max:
            warnings.append({'code': 'true_peak', 'message': f'true peak {tp} dBTP exceeds {true_peak_max} dBTP'})
        if i is not None and not lufs_window[0] <= i <= lufs_window[1]:
            warnings.append({'code': 'loudness', 'message': f'integrated loudness {i} LUFS outside {lufs_window[0]}..{lufs_window[1]} LUFS'})
        report['loudness']['target_window_lufs'] = list(lufs_window); report['loudness']['true_peak_max_dbtp'] = true_peak_max
        if cuts:
            try:
                from .audio_analysis import analyze
                music, _ = analyze(movie)
                grid = np.array(music['beats']); half = np.r_[grid, grid + music['period'] / 2]
                on = [t for t in cuts if np.min(np.abs(half - t)) <= .04]
                report['rhythm'] = {'bpm': music['bpm'], 'cuts': len(cuts), 'cuts_on_beat_or_half': len(on), 'share': round(len(on) / len(cuts), 3)}
            except Exception as e:   # too short / arrhythmic audio: report, do not fail the render
                report['rhythm'] = {'unavailable': str(e)[:200]}
    else:
        report['loudness'] = None; report['rhythm'] = {'unavailable': 'no audio'}
    crops = []
    for row in trace:
        f = row.get('face')
        if not f:
            continue
        w, h = 2.4 * f['D'], 3.2 * f['D']; x0, y0 = f['x'] - w / 2, f['y'] - .9 * f['D']
        inside = max(0, min(W, x0 + w) - max(0, x0)) * max(0, min(H, y0 + h) - max(0, y0))
        if w * h > 0 and inside / (w * h) < .75:
            crops.append(row['frame'])
    report['face_crop_frames'] = len(crops)
    if crops:
        warnings.append({'code': 'face_cropped', 'message': f'face more than 25 % outside the frame on {len(crops)} frame(s), first at {crops[0] / fps:.2f} s'})
    outside = [i for i, t in enumerate(edit.get('text', [])) if not all(.05 <= v <= .95 for v in t.get('pos', [.5, .5]))]
    report['text_outside_safe_area'] = outside
    if outside:
        warnings.append({'code': 'text_safe_area', 'message': f'text item(s) {outside} anchored outside the central 90 % of the canvas'})
    report['warnings'] = warnings
    report['status'] = 'warn' if warnings else 'pass'
    return report
