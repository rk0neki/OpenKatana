"""Bounded motion revision loop (audit F-MOT-001). Renders the timeline, measures its per-second energy against a
reference video with the analyze_energy measures (cuts, flashes, shake frames, jitter, camera movement, motion energy),
and up to `max_revisions` times proposes camera-only edits on unlocked shots, re-renders and re-measures. The best
attempt (fewest failing measures, then the smallest log-ratio shortfall) is kept.

What a revision may change: shot `cam` entries only (shake bursts, pans and punch hits placed at the reference's event
times; later attempts scale amplitudes by the measured shortfall, bounded to 0.5-2x per step and absolute caps).
What it never changes: canvas, clips, shot spans and sources, transitions, specials/flashes, text, looks, post, audio
and the timeline-level camera. Cut and flash shortfalls are structural and are reported for the editor instead; since a
revision keeps the structure, attempts after the first score cuts/flashes from attempt 0 (detector drift caused by new
camera motion is not counted) while the re-measured values stay in the report."""
import copy
import json
import math
import shutil
import uuid
from pathlib import Path

from .contracts import ContractError
from .energy import chart, check, measure

LABEL = {'cuts_ps': 'cuts / s', 'flashes_ps': 'flashes / s', 'shake_ps': 'shake frames / s', 'jitter_px': 'jitter px',
         'move_px': 'camera movement px', 'motion': 'motion energy'}
KEY = {v: k for k, v in LABEL.items()}
MAX_HITS = 8          # punch hits per shot
STEP = (.5, 2.0)      # amplitude scale bounds per revision


def score(chk):
    dev = sum(abs(math.log(max(r['ratio'], .05))) for r in chk['rows'] if r['ratio'] is not None and r['verdict'].startswith('FAIL'))
    return [len(chk['fails']), round(dev, 3)]


def structure(edit):
    """Everything a revision must leave unchanged (all but shot cameras)."""
    return json.dumps({**{k: v for k, v in edit.items() if k != 'shots'}, 'shots': [{k: v for k, v in s.items() if k != 'cam'} for s in edit['shots']]},
                      sort_keys=True, default=str)


def _bound(x, lo, hi):
    return max(lo, min(hi, x))


def propose(edit, ref, chk, added, locked, ref_start, ceiling=None):
    """One bounded revision from the current best attempt. Returns (edit, changes, editor_items)."""
    e = copy.deepcopy(edit); c = e['canvas']; fps, W = c['fps'], c['w']; T = c['frames'] / fps
    amp_cap = .05 * W; add_cap = .02 * W   # new bursts start moderate: big jumps read as cuts and drop out of the measure
    fails = {KEY[r['measure']]: r for r in chk['rows'] if r['verdict'].startswith('FAIL')}
    editor = [f"{LABEL[k]} {r['verdict'].lower()} (ours {r['ours']} vs reference {r['reference']}): cut/flash structure is the editor's call"
              for k, r in fails.items() if k in ('cuts_ps', 'flashes_ps')]
    before = {i: copy.deepcopy(s.get('cam')) for i, s in enumerate(e['shots'])}

    def shot_at(t):
        f = math.ceil(t * fps - .5)
        for i, s in enumerate(e['shots']):
            if s['f0'] <= f < s['f1']:
                return None if (i in locked or 'special' in s) else i
        return None

    def events(kind):
        for ev in ref['events'][kind]:
            t = ev['t'] - ref_start
            if 0 <= t < T:
                i = shot_at(t)
                if i is not None:
                    yield i, round(t - e['shots'][i]['f0'] / fps, 3), ev

    def ratio(key):
        r = fails[key]['ratio']
        return r if r else .05

    def unlocked():
        return [i for i, s in enumerate(e['shots']) if i not in locked and 'special' not in s]

    low = {k for k, r in fails.items() if r['verdict'] == 'FAIL (too little)'}
    high = {k for k, r in fails.items() if r['verdict'] == 'FAIL (too much)'}
    if low & {'shake_ps', 'jitter_px'}:
        if 'shakes' not in added:
            added.add('shakes')
            for i, at, ev in events('shakes'):
                cam = e['shots'][i].setdefault('cam', {}); sh = cam.setdefault('shake', {})
                hits = sorted(set(sh.get('hits', [sh['at']] if 'at' in sh else []) + [at]))
                sh.pop('at', None); sh['hits'] = hits
                sh['d'] = round(_bound(max(sh.get('d', 0), ev['d'], 4 / fps), .05, 1.0), 3)
                a = min(add_cap, .6 * ev['amp_px']); old = sh.get('amp', [0, 0])
                sh['amp'] = [round(max(old[0], a), 1), round(max(old[1], .8 * a), 1)]; sh['every'] = 1
        else:
            k = _bound(1 / ratio('jitter_px'), 1, STEP[1]) if 'jitter_px' in low else 1
            dk = _bound(1 / ratio('shake_ps'), 1, STEP[1]) if 'shake_ps' in low else 1
            for i in unlocked():
                sh = (e['shots'][i].get('cam') or {}).get('shake')
                if sh:
                    if k > 1:
                        sh['amp'] = [round(min(amp_cap, v * k), 1) for v in sh.get('amp', [16, 12])]
                    if dk > 1:
                        sh['d'] = round(min(1.0, sh.get('d', .25) * dk), 3); sh['every'] = 1
    if high & {'shake_ps', 'jitter_px'}:
        k = _bound(min((fails[x]['reference'] / max(fails[x]['ours'], 1e-6)) for x in high & {'shake_ps', 'jitter_px'}), STEP[0], 1)
        for i in unlocked():
            cam = e['shots'][i].get('cam') or {}
            if 'shake' in cam:
                cam['shake']['amp'] = [round(v * k, 1) for v in cam['shake'].get('amp', [16, 12])]
            if isinstance(cam.get('handheld'), dict):
                cam['handheld']['amp'] = round(cam['handheld'].get('amp', cam['handheld'].get('v', 6)) * k, 2)
        if (e.get('cam') or {}).get('handheld') or any((e['shots'][i].get('cam') or {}).get('handheld') is True for i in unlocked()):
            editor.append('timeline-level / default handheld also adds jitter: lower it by hand if shake stays too high')
    if high & {'move_px', 'motion'}:
        # over-busy: scale camera movement and hits toward ceiling x reference (0.5x minimum per step)
        k = _bound(min(.9 * ceiling * fails[x]['reference'] / max(fails[x]['ours'], 1e-6) for x in high & {'move_px', 'motion'}), STEP[0], 1)
        for i in unlocked():
            cam = e['shots'][i].get('cam') or {}
            if 'pan' in cam:
                cam['pan'] = {a: round(v * k, 4) for a, v in cam['pan'].items() if a in ('dx', 'dy')}
            if 'push' in cam:
                cam['push'] = {a: round(v * k, 4) for a, v in cam['push'].items()}
            if 'zoom' in cam:
                z0 = cam['zoom'].get('z0', 1); cam['zoom']['z1'] = round(z0 + (cam['zoom'].get('z1', 1.08) - z0) * k, 4)
            for name in ('punch', 'crash', 'pulse'):
                if name in cam:
                    key = 'amt' if 'amt' in cam[name] else 'v'
                    default = {'punch': .07, 'crash': 4, 'pulse': .3}[name]
                    v = cam[name].get(key, default)
                    cam[name][key] = round(1 + (v - 1) * k, 4) if name == 'crash' else round(v * k, 4)
            if 'shake' in cam and 'motion' in high:
                cam['shake']['amp'] = [round(v * k, 1) for v in cam['shake'].get('amp', [16, 12])]
            if isinstance(cam.get('handheld'), dict):
                cam['handheld']['amp'] = round(cam['handheld'].get('amp', cam['handheld'].get('v', 6)) * k, 2)
        if (e.get('cam') or {}).keys() & {'handheld', 'zoom', 'push', 'pan', 'shake', 'punch'}:
            editor.append('the timeline-level camera also moves every shot: the loop leaves it to the editor')
    if 'move_px' in low:
        if 'pans' not in added:
            added.add('pans')
            for i, at, ev in events('pans'):
                cam = e['shots'][i].setdefault('cam', {})
                if 'pan' not in cam:
                    p = ev['edl']['cam']['pan']
                    cam['pan'] = {'dx': round(_bound(p['dx'], -.25, .25), 4), 'dy': round(_bound(p['dy'], -.25, .25), 4)}
        else:
            k = _bound(1 / ratio('move_px'), 1, STEP[1])
            for i in unlocked():
                cam = e['shots'][i].get('cam') or {}
                if 'pan' in cam:
                    cam['pan'] = {a: round(_bound(v * k, -.25, .25), 4) for a, v in cam['pan'].items() if a in ('dx', 'dy')}
                if 'push' in cam:
                    cam['push']['v'] = round(min(.3, cam['push'].get('v', .1) * k), 4)
    if low & {'move_px', 'motion'}:
        if 'hits' not in added:
            added.add('hits')
            for i, at, ev in events('hits'):
                cam = e['shots'][i].setdefault('cam', {}); pu = cam.setdefault('punch', {})
                hits = sorted(set(pu.get('hits', [pu['at']] if 'at' in pu else []) + [at]))[:MAX_HITS]
                pu.pop('at', None); pu['hits'] = hits; pu.setdefault('d', .2)
                if 'v' not in pu and 'amt' not in pu:
                    pu['v'] = .07
        elif 'motion' in low:
            k = _bound(1 / ratio('motion'), 1, 1.5)
            for i in unlocked():
                pu = (e['shots'][i].get('cam') or {}).get('punch')
                if pu:
                    key = 'amt' if 'amt' in pu else 'v'
                    pu[key] = round(min(.15, pu.get(key, .07) * k), 4)
    changes = [{'shot': i, 'before': before[i], 'after': s.get('cam')} for i, s in enumerate(e['shots']) if s.get('cam') != before[i]]
    return e, changes, editor


def not_responding(before_rows, now_rows, k):
    """Failing camera measures that got no closer to the reference after a revision (distance = |log(ours / reference)|,
    defined also for rows the check gives no ratio)."""
    dist = lambda r: abs(math.log(max(r['ours'], 1e-6) / max(r['reference'], 1e-6)))
    now = {r['measure']: r for r in now_rows}
    return [f"{r['measure']} did not respond to camera-only edits (attempt {k}: {r['ours']} -> {now[r['measure']]['ours']}, "
            f"reference {r['reference']}); it is likely footage motion or structure: an editorial change"
            for r in before_rows if r['verdict'].startswith('FAIL') and KEY[r['measure']] not in ('cuts_ps', 'flashes_ps')
            and dist(now[r['measure']]) >= dist(r) - 1e-9]


def run(root, edit, reference, out, max_revisions=2, locked=(), floor=.6, ref_start=0.0, ref_duration=None, render_fn=None, ceiling=None):
    from .render import render as default_render
    from .contracts import validate
    render_fn = render_fn or default_render
    root = Path(root); out = Path(out); out.mkdir(parents=True, exist_ok=False)
    c = edit['canvas']; W, T = c['w'], c['frames'] / c['fps']
    locked = set(locked)
    for i in locked:
        if not isinstance(i, int) or not 0 <= i < len(edit['shots']):
            raise ContractError(f'locked_shots: shot indices 0..{len(edit["shots"]) - 1}')
    ref = measure(reference, ref_start, ref_duration if ref_duration is not None else T, W)
    chart(ref, out / 'reference-energy.png')
    original = structure(edit); attempts, added, editor_items, unresponsive = [], set(), [], []
    best = None; cur = edit; changes = []; tried = {json.dumps(edit, sort_keys=True)}
    for k in range(max_revisions + 1):
        d = out / f'attempt-{k:02d}'; d.mkdir()
        validate(cur, root)
        tmp = root / f'.motion-{uuid.uuid4().hex[:8]}.json'   # the renderer resolves media against the timeline's folder
        tmp.write_text(json.dumps(cur), encoding='utf-8')
        try:
            render_fn(tmp, d / 'render')
        finally:
            tmp.unlink(missing_ok=True)
        video = d / 'draft.mp4'; shutil.move(str(d / 'render' / 'video.mp4'), video)
        shutil.rmtree(d / 'render' / 'frames', ignore_errors=True)
        m = measure(video, 0.0, None, W); chk = check(m, ref, floor, ceiling)
        measured_rows = chk['rows']
        if k and structure(cur) == original:
            # cuts and flashes cannot change (shot structure is identical); score them from attempt 0 so cut-detector
            # drift caused by new camera motion does not count against a camera revision (re-measured rows still reported)
            frozen = {r['measure']: r for r in attempts[0]['check_rows'] if KEY[r['measure']] in ('cuts_ps', 'flashes_ps')}
            rows = [frozen.get(r['measure'], r) for r in chk['rows']]
            chk = {**chk, 'rows': rows, 'fails': [r['measure'] for r in rows if r['verdict'].startswith('FAIL')]}
            chk['pass'] = not chk['fails']
        (d / 'timeline.json').write_text(json.dumps(cur, indent=1), encoding='utf-8')
        (d / 'assessment.json').write_text(json.dumps({'rates': m['rates'], 'check': chk, 'measured_rows': measured_rows}, indent=1), encoding='utf-8')
        sc = score(chk)
        attempts.append({'attempt': k, 'ok': chk['pass'], 'fails': [r for r in chk['rows'] if r['verdict'].startswith('FAIL')], 'score': sc,
                         'check_rows': chk['rows'], 'measured_rows': measured_rows,
                         'rates': m['rates'], 'changes': changes, 'video': str(video), 'chart': chart(m, d / 'energy.png'),
                         'structure_preserved': structure(cur) == original,
                         'locked_shots_unchanged': all(cur['shots'][i].get('cam') == edit['shots'][i].get('cam') for i in locked)})
        if best is not None:
            unresponsive += not_responding(best[3]['rows'], chk['rows'], k)
        if best is None or sc < best[1]:
            best = (k, sc, cur, chk)
        if chk['pass'] or k == max_revisions:
            break
        # continue from the last attempt (so a change that fell short can be escalated); the best attempt is what is kept
        cur, changes, editor_items = propose(cur, ref, chk, added, locked, ref_start, ceiling)
        if not changes:
            attempts[-1]['next'] = 'no adjustable camera measure left'
            break
        key = json.dumps(cur, sort_keys=True)
        if key in tried:
            attempts[-1]['next'] = 'the next bounded change repeats an earlier attempt: stopped'
            break
        tried.add(key)
    k, sc, best_edit, chk = best
    editor_items = [f"{r['measure']} {r['verdict'].lower()} (ours {r['ours']} vs reference {r['reference']}): cut/flash structure is the editor's call"
                    for r in chk['rows'] if r['verdict'].startswith('FAIL') and KEY[r['measure']] in ('cuts_ps', 'flashes_ps')] +                    [x for x in editor_items if 'handheld' in x or 'timeline-level' in x] + list(dict.fromkeys(unresponsive))
    return {'schema': 'openkatana.motion-loop/1', 'status': 'pass' if chk['pass'] else 'needs_editor', 'max_revisions': max_revisions, 'floor': floor, 'ceiling': ceiling,
            'reference': {'source': str(reference), 'start': ref_start, 'rates': ref['rates']}, 'attempts': attempts, 'best_attempt': k,
            'best_score': sc, 'timeline': best_edit, 'editor_items': editor_items, 'locked_shots': sorted(locked),
            'preserved': 'canvas, clips, shot spans/sources, transitions, specials, text, looks, post, audio, timeline camera'}
