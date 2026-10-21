"""Edit recipes (audit F-PRE-001): OpenKatana's own starting-point timelines for eight common short-form families.
Each recipe arranges supplied assets with documented timeline features. The result is returned for the editor to change (never saved automatically).

beat_cut_punch     cuts on the music's beat grid (plan_music_edit), punch-ins on loud downbeats, impact/riser cues
xerox_ink          photocopy look with accent key, hard cuts every bar, light grain
mono_noir          noir studio look, slow push-ins, letterbox, white dip at the end
cutout_collage     collage special with two panels, then the panels' clips full-frame
speed_ramp_freeze  real-time -> slow-motion ramp, then a freeze with a white flash
facelock_strobe    face-locked camera (needs a clip face track) with a strobe burst
timed_type         clean shots under typewriter text, one phrase per shot
glitch_hits        glitch transitions on every cut and RGB split on beats
"""
import math

from .contracts import ContractError

FAMILIES = ('beat_cut_punch', 'xerox_ink', 'mono_noir', 'cutout_collage', 'speed_ramp_freeze', 'facelock_strobe', 'timed_type', 'glitch_hits')


def _clipshots(clips, frames, step, fps):
    """Cut every `step` frames, cycling clips and advancing their in-points."""
    shots, f, k, cursor = [], 0, 0, {}
    while f < frames:
        key, clip = clips[k % len(clips)]
        n = min(step, frames - f)
        src = cursor.get(key, 0)
        need = math.ceil(n * clip['fps'] / fps)
        if src + need > clip['n']:
            src = 0
        shot = {'f0': f, 'f1': f + n, 'clip': key}
        if clip['n'] > 1:
            shot['srcf'] = src; cursor[key] = src + need
            if need > clip['n']:
                shot['loop'] = 'loop'
        else:
            shot['speed'] = 0
        shots.append(shot); f += n; k += 1
    return shots


def build(family, clips, fps=30, width=1080, height=1920, seconds=6.0, music=None, analysis=None, text=None, family_font=None):
    """clips: [(id, clip)] in order; music: project-relative audio path; analysis: analyze_audio result for that music."""
    if family not in FAMILIES:
        raise ContractError(f'recipe: one of {", ".join(FAMILIES)}')
    if not clips:
        raise ContractError('recipe: needs at least one imported video/image asset')
    frames = max(2, round(seconds * fps))
    edit = {'canvas': {'w': width, 'h': height, 'fps': fps, 'frames': frames, 'bg': '#000000'}, 'clips': dict(clips)}
    notes = []
    if family == 'beat_cut_punch':
        if not (music and analysis):
            raise ContractError('beat_cut_punch needs music (an imported audio asset) to find the beat grid')
        from .music_plan import draft_timeline, plan_cuts
        plan = plan_cuts({**analysis, 'duration': min(analysis['duration'], seconds)}, fps)
        assets = [(k, {'kind': 'image' if c['n'] == 1 else 'video', 'clip': c}) for k, c in clips]
        edit = draft_timeline(plan, assets, fps, width, height)
        for sug in plan['suggestions']:
            if 'cam' in sug and 'punch' in sug['cam']:
                shot = next(s for s in edit['shots'] if s['f0'] <= sug['at_frame'] < s['f1'])
                shot.setdefault('cam', {})['punch'] = {'hits': sorted(set(shot.get('cam', {}).get('punch', {}).get('hits', []) + [sug['cam']['punch']['at']])), 'v': .08, 'd': .2}
        edit['audio'] = {'mode': 'mix', 'tracks': [{'src': music, 'duration': round(plan['frames'] / fps, 4)}],
                         'cues': [s['audio_cue'] for s in plan['suggestions'] if 'audio_cue' in s]}
        notes.append(f'{len(plan["cuts"])} cuts on the {analysis["bpm"]} BPM grid')
        frames = edit['canvas']['frames']
    elif family == 'xerox_ink':
        step = round(4 * 60 / analysis['bpm'] * fps) if analysis else round(.8 * fps)
        edit['shots'] = _clipshots(clips, frames, step, fps)
        edit['look'] = {'type': 'xerox', 'key': True, 'grit': .35}
        edit['post'] = {'grain': {'v': .25}}
    elif family == 'mono_noir':
        edit['shots'] = _clipshots(clips, frames, round(1.5 * fps), fps)
        for s in edit['shots']:
            s['cam'] = {'zoom': {'z0': 1, 'z1': 1.08, 'ease': 'out3'}}
        edit['look'] = 'mono_noir'
        edit['post'] = {'letterbox': {'v': .1}}
        edit['shots'][-1]['out'] = {'type': 'dip', 'd': .4, 'color': '#ffffff'}
    elif family == 'cutout_collage':
        a = clips[0][0]; b = clips[1 % len(clips)][0]
        half = frames // 2
        panel = lambda k, rect: {'clip': k, 'rect': rect, **({'speed': 0} if dict(clips)[k]['n'] == 1 else {'srcf': 0, 'loop': 'loop'})}
        edit['shots'] = [{'f0': 0, 'f1': half, 'special': {'type': 'collage', 'bg': '#f2efe6', 'brackets': True,
                                                          'panels': [panel(a, [.04, .06, .44, .88]), panel(b, [.52, .06, .44, .88])]}}]
        edit['shots'] += [dict(s, f0=s['f0'] + half, f1=s['f1'] + half) for s in _clipshots(clips, frames - half, max(1, (frames - half) // 2), fps)]
        if any('mask_dir' in c for _k, c in clips):
            for s in edit['shots'][1:]:
                if 'mask_dir' in dict(clips)[s['clip']]:
                    s['fx'] = {'cutout': True, 'outline': True}
        else:
            notes.append('no clip has a matte: cut-out outlines skipped (analyze_clip masks adds one)')
    elif family == 'speed_ramp_freeze':
        key, clip = clips[0]
        a = round(frames * .55)
        # freeze on the frame the ramp ends on: speed falls linearly 1 -> .35, so it covers (a - 1) * 1.35 / 2 output frames
        held = min(clip['n'] - 1, round((a - 1) * (1 + .35) / 2 * clip['fps'] / fps))
        edit['shots'] = [{'f0': 0, 'f1': a, 'clip': key, 'srcf': 0, 'speed': 1, 'speed1': .35},
                         {'f0': a, 'f1': frames, 'clip': key, 'srcf': held, 'speed': 0,
                          'in': {'type': 'flash', 'd': .15}, 'cam': {'push': {'v': .06}}}]
    elif family == 'facelock_strobe':
        faced = [(k, c) for k, c in clips if c.get('faces')]
        if not faced:
            raise ContractError('facelock_strobe needs a clip with a face track (analyze_clip faces, apply: true)')
        key, clip = faced[0]
        edit['clips'] = {key: clip}
        edit['shots'] = [{'f0': 0, 'f1': frames, 'clip': key, 'srcf': 0, 'loop': 'pingpong', 'cam': {'type': 'facelock'},
                          'layers': [{'type': 'strobe', 'every': 2, 'at': seconds * .4, 'd': min(.5, seconds * .2), 'amt': .8}]}]
    elif family == 'timed_type':
        if not family_font:
            raise ContractError('timed_type needs a declared font family (fonts) for the text')
        words = (text or 'YOUR WORDS HERE').split()
        phrases = [' '.join(words[i:i + 3]) for i in range(0, len(words), 3)] or ['']
        step = max(1, frames // len(phrases))
        edit['shots'] = _clipshots(clips, frames, step, fps)
        edit['text'] = [{'type': 'font', 'family': family_font, 'text': p, 'f0': k * step, 'f1': min(frames, (k + 1) * step), 'pos': [.5, .78],
                         'size': round(height * .05), 'anim': 'type', 'dt': .04, 'fill': '#ffffff', 'stroke': '#000000', 'render_style': 'explicit', 'shadow': False}
                        for k, p in enumerate(phrases) if k * step < frames]
    elif family == 'glitch_hits':
        step = round(2 * 60 / analysis['bpm'] * fps) if analysis else round(.6 * fps)
        edit['shots'] = _clipshots(clips, frames, step, fps)
        for i, s in enumerate(edit['shots']):
            if i:
                s['in'] = {'type': 'glitch', 'd': .12}
            s.setdefault('layers', []).append({'type': 'rgbsplit', 'v': 8, 'at': 0, 'd': .15})
    if music and family != 'beat_cut_punch':
        edit['audio'] = {'mode': 'mix', 'tracks': [{'src': music, 'duration': round(frames / fps, 4)}]}
    edit['canvas']['frames'] = frames
    return edit, notes
