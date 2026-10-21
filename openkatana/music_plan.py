"""Music-driven cut planning (audit F-STU-004): a beat-aligned cut list and optional draft timeline from an audio
analysis. A planning aid — the editor still chooses shots, moments and treatments.

Pacing per level section ('auto', tempo-aware): the smallest of 1/2/4/8 beats lasting >= 0.5 s in loud sections,
>= 1 s in mid sections, >= 2 s in quiet ones; or a fixed pace (bar / two / beat / half). After a drop (a step of >= 4 dB into a loud section) the first bar is cut on
half-beats (burst). Cuts are snapped to the beat grid (or half-beats) and kept at least `min_shot` seconds apart.
Suggestions use valid OpenKatana syntax: a 2-frame white special at the drop, cam.punch on downbeats of loud
sections, cam.shake on the drop shot, and audio.cues (riser into the drop, impact on it, whoosh at section changes).
"""
import math

from .contracts import ContractError

PACE = {'bar': 4, 'two': 2, 'beat': 1, 'half': .5}
AUTO_MIN_S = {'quiet': 2.0, 'mid': 1.0, 'loud': .5}


def plan_cuts(analysis, fps, pace='auto', min_shot=.15, burst=True):
    if pace != 'auto' and pace not in PACE:
        raise ContractError(f'pace: use auto, {", ".join(PACE)}')
    dur, P = analysis['duration'], analysis['period']
    grid = [b for b in analysis['beats'] if b >= -1e-9] or [analysis['phase'] + P]
    half = sorted(grid + [b + P / 2 for b in grid if b + P / 2 < dur])
    downbeats = set(round(d, 4) for d in analysis['downbeats'])
    snap = lambda t, pts: min(pts, key=lambda b: abs(b - t))
    cuts, sections = [], analysis['sections']
    for si, sec in enumerate(sections):
        step = next((b for b in (1, 2, 4, 8) if b * P >= AUTO_MIN_S[sec['label']]), 8) if pace == 'auto' else PACE[pace]
        drop = si > 0 and sec['label'] == 'loud' and (sec.get('step_db') or 0) >= 4
        t0 = snap(sec['t0'], half if drop else grid) if si else 0.0   # a drop may land off the beat; other sections on it
        t1 = sec['t1']
        if si:
            cuts.append({'t': t0, 'kind': 'drop' if drop else 'section', 'section': si})
        t = t0
        burst_end = t0 + 4 * P if (drop and burst) else t0
        while True:
            inc = P / 2 if t < burst_end - 1e-6 else step * P
            t = t + inc
            if t >= t1 - 1e-6 or t >= dur - min_shot:
                break
            pts = half if (inc < P or step < 1) else grid
            ts = snap(t, pts)
            kind = 'burst' if inc < P and pace != 'half' else ('half' if step < 1 else 'beat')
            cuts.append({'t': ts, 'kind': kind, 'section': si})
            t = ts
    out, last = [], 0.0
    rank = {'drop': 0, 'section': 1}
    for c in sorted(cuts, key=lambda c: (round(c['t'], 3), rank.get(c['kind'], 2))):
        if c['t'] - last >= min_shot - 1e-9 and dur - c['t'] >= min_shot - 1e-9:
            frame = int(round(c['t'] * fps))
            if out and frame <= out[-1]['frame']:
                continue
            c = {**c, 't': round(c['t'], 4), 'frame': frame, 'downbeat': round(c['t'], 4) in downbeats}
            out.append(c); last = c['t']
    frames = int(round(dur * fps))
    bounds = [0] + [c['frame'] for c in out] + [frames]
    shots = [{'f0': a, 'f1': b} for a, b in zip(bounds, bounds[1:]) if b > a]
    suggestions = []
    for c in out:
        if c['kind'] == 'drop':
            suggestions.append({'at_frame': c['frame'], 'why': 'drop', 'specials': {'f0': c['frame'], 'n': 2, 'type': 'white'}})
            suggestions.append({'at_frame': c['frame'], 'why': 'drop shot', 'cam': {'shake': {'at': 0, 'd': .25, 'amp': [16, 12]}}})
            suggestions.append({'at_frame': c['frame'], 'why': 'drop', 'audio_cue': {'sfx': 'impact', 'at': round(c['t'], 4)}})
            if c['t'] >= 1.4:
                suggestions.append({'at_frame': c['frame'], 'why': 'into the drop', 'audio_cue': {'sfx': 'riser', 'at': round(c['t'] - 1.4, 4)}})
        elif c['kind'] == 'section':
            suggestions.append({'at_frame': c['frame'], 'why': 'section change', 'audio_cue': {'sfx': 'whoosh', 'at': round(max(0, c['t'] - .2), 4)}})
    for d in analysis['downbeats']:
        sec = next((s for s in sections if s['t0'] <= d < s['t1']), None)
        if sec and sec['label'] == 'loud':
            f = int(round(d * fps))
            shot = next((s for s in shots if s['f0'] <= f < s['f1']), None)
            if shot:
                suggestions.append({'at_frame': f, 'why': 'downbeat in a loud section', 'cam': {'punch': {'at': round((f - shot['f0']) / fps, 3)}}})
    return {'cuts': out, 'shots': shots, 'frames': frames, 'suggestions': suggestions}


def draft_timeline(plan, assets, fps, width, height, audio=None):
    """Assign supplied clips to the planned shots in order (videos advance their in-point so shots do not repeat)."""
    if not assets:
        return None
    clips, cursor, shots = {}, {}, []
    for k, s in enumerate(plan['shots']):
        key, a = assets[k % len(assets)]
        clips[key] = a['clip']
        n = s['f1'] - s['f0']
        shot = {'f0': s['f0'], 'f1': s['f1'], 'clip': key}
        if a['kind'] == 'image':
            shot['speed'] = 0
        else:
            src = cursor.get(key, 0)
            need = math.ceil(n * a['clip']['fps'] / fps)
            if src + need > a['clip']['n']:
                src = 0
            shot['srcf'] = src; cursor[key] = src + need
            shot['loop'] = 'loop' if need > a['clip']['n'] else 'clamp'
        shots.append(shot)
    edit = {'canvas': {'w': width, 'h': height, 'fps': fps, 'frames': plan['frames']}, 'clips': clips, 'shots': shots}
    if audio:
        edit['audio'] = audio
    return edit
