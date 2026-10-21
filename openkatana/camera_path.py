"""Reusable camera track: segment-based camera timing (pure Python, no bpy).

The layout lists contiguous segments. Each segment moves the camera position, its
look-at target and lens along a Catmull-Rom path through its poses, reparameterised by
arc length, with an explicit timing curve:

  * "whip"  - asymmetric cubic-Bezier timing (x1, 0)-(x2, 1): a short, quick acceleration,
              a nearly vertical middle (peak speed) and a long flat landing (slow-in).
  * "hold"  - gentle smoothstep drift between two close poses (readable holds).
  * "push"  - symmetric ease-in-out.
  * "accel" - ease-in only (speeding into a motivated cut).
A segment flagged "cut" starts on a new pose; Blender keys jump at f-0.5 so the shutter
never blends the two views. Values are sampled per integer frame and used by the
Blender build (keys every frame) and by QA plots, so both see the same motion.
"""
import math
from .contracts import ContractError, fields, number

EASES = {
    'whip': (0.30, 0.06),
    'snap': (0.40, 0.04),
    'push': (0.42, 0.58),
    'hold': None,
    'accel': (0.55, 1.0),
}


def cubic_bezier_timing(x1, x2, t, y1=0.0, y2=1.0):
    """CSS-style timing curve through (0,0),(x1,y1),(x2,y2),(1,1); returns y for x=t."""
    if t <= 0:
        return 0.0
    if t >= 1:
        return 1.0
    lo, hi = 0.0, 1.0
    for _ in range(60):
        s = (lo + hi) / 2
        x = 3 * (1 - s) ** 2 * s * x1 + 3 * (1 - s) * s ** 2 * x2 + s ** 3
        if x < t:
            lo = s
        else:
            hi = s
    s = (lo + hi) / 2
    return 3 * (1 - s) ** 2 * s * y1 + 3 * (1 - s) * s ** 2 * y2 + s ** 3


def ease(kind, t, params=None):
    if kind == 'hold':
        t = min(1.0, max(0.0, t))
        return t * t * (3 - 2 * t)
    x1, x2 = params or EASES[kind]
    if kind == 'accel':
        return cubic_bezier_timing(x1, x2, t, 0.0, 1.0)
    return cubic_bezier_timing(x1, x2, t)


def _catmull(p0, p1, p2, p3, t):
    t2, t3 = t * t, t * t * t
    return [0.5 * ((2 * p1[i]) + (-p0[i] + p2[i]) * t + (2 * p0[i] - 5 * p1[i] + 4 * p2[i] - p3[i]) * t2
                   + (-p0[i] + 3 * p1[i] - 3 * p2[i] + p3[i]) * t3) for i in range(len(p1))]


def _dedupe(points, tol=1e-6):
    """Merge consecutive near-identical waypoints (keeping both path ends exactly): a repeated
    point makes the Catmull-Rom curve loop past it and come back, i.e. the look-at target
    overshoots and reverses (a visible aim jolt)."""
    out = [list(points[0])]
    for p in points[1:]:
        if math.dist(p, out[-1]) < tol:
            if len(out) > 1:
                out[-1] = list(p)
            continue
        out.append(list(p))
    if math.dist(out[-1], points[-1]) > 1e-12:
        out.append(list(points[-1]))
    return out


def _path(points, n=240):
    """Dense samples along a Catmull-Rom path through points + cumulative arc length."""
    points = _dedupe(points)
    if len(points) == 1:
        return [points[0]], [0.0]
    ext = [points[0]] + list(points) + [points[-1]]
    out = []
    segs = len(points) - 1
    for k in range(segs):
        for j in range(max(2, n // segs) + 1):
            if k > 0 and j == 0:
                continue
            out.append(_catmull(ext[k], ext[k + 1], ext[k + 2], ext[k + 3], j / max(2, n // segs)))
    acc = [0.0]
    for a, b in zip(out, out[1:]):
        acc.append(acc[-1] + math.dist(a, b))
    return out, acc


def _at(samples, acc, u):
    if acc[-1] <= 1e-9:
        return list(samples[0])
    d = u * acc[-1]
    lo, hi = 0, len(acc) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if acc[mid] < d:
            lo = mid
        else:
            hi = mid
    span = acc[hi] - acc[lo]
    w = 0.0 if span <= 1e-12 else (d - acc[lo]) / span
    return [samples[lo][i] * (1 - w) + samples[hi][i] * w for i in range(len(samples[lo]))]


def _lens_at(lenses, u):
    if len(lenses) == 1:
        return lenses[0]
    x = u * (len(lenses) - 1)
    k = min(len(lenses) - 2, int(x))
    w = x - k
    w = w * w * (3 - 2 * w)
    return lenses[k] * (1 - w) + lenses[k + 1] * w


class CameraTrack:
    def __init__(self, segments, step=1.0):
        """step = master-frame spacing in schedule units (1.0 at 30 fps, 0.5 at 60 fps). A
        segment followed by a cut runs to the last displayed frame before that cut."""
        validate_segments(segments, step)
        self.step = step
        self.segs = []
        for s in segments:
            poses = s['poses']
            pos_s, pos_a = _path([p['pos'] for p in poses])
            tgt_s, tgt_a = _path([p['tgt'] for p in poses])
            self.segs.append(dict(s, _pos=(pos_s, pos_a), _tgt=(tgt_s, tgt_a), _lens=[p['lens'] for p in poses],
                                  _fstop=[p.get('fstop') for p in poses]))
        self.segs.sort(key=lambda s: s['f0'])
        for a, b in zip(self.segs, self.segs[1:]):
            a['_f1'] = (b['f0'] - step) if b.get('cut') else a['f1']
        self.segs[-1]['_f1'] = self.segs[-1]['f1']

    def segment(self, f):
        for s, nxt in zip(self.segs, self.segs[1:] + [None]):
            if nxt is None or f < nxt['f0']:
                return s
        return self.segs[-1]

    def sample(self, f):
        s = self.segment(f)
        t = max(0.0, min(1.0, (f - s['f0']) / max(1e-9, (s['_f1'] - s['f0']))))
        u = ease(s['type'], t, s.get('ease'))
        pos = _at(*s['_pos'], u)
        tgt = _at(*s['_tgt'], u)
        lens = _lens_at(s['_lens'], u)
        fs = [x for x in s['_fstop'] if x is not None]
        fstop = _lens_at(fs, u) if fs else None
        return {'pos': pos, 'tgt': tgt, 'lens': lens, 'fstop': fstop, 'u': u, 'segment': s.get('name', s['type'])}

    def cuts(self):
        return [s['f0'] for s in self.segs if s.get('cut')]


def validate_segments(segments, step=1.0):
    number(step, 'step', 1e-6, 1000)
    if not isinstance(segments, list) or not 1 <= len(segments) <= 1000:
        raise ContractError('Supply 1..1000 camera segments')
    previous = None
    for s in segments:
        fields(s, 'f0 f1 type poses ease name cut', 'camera segment')
        for k in ('f0', 'f1', 'type', 'poses'):
            if k not in s: raise ContractError('Camera segment missing ' + k)
        number(s['f0'], 'f0', 0, 100000); number(s['f1'], 'f1', s['f0'] + step, 100000)
        if s['type'] not in EASES: raise ContractError('Unknown camera timing curve')
        if type(s.get('cut', False)) is not bool: raise ContractError('cut must be boolean')
        if previous is not None and abs(previous['f1'] - s['f0']) > 1e-8:
            raise ContractError('Camera segments must be ordered and contiguous (shared boundary)')
        if 'ease' in s:
            if not isinstance(s['ease'], list) or len(s['ease']) != 2: raise ContractError('ease needs two x coordinates')
            for x in s['ease']: number(x, 'ease', 0, 1)
        poses = s['poses']
        if not isinstance(poses, list) or not 1 <= len(poses) <= 1000: raise ContractError('Supply camera poses')
        fs = []
        for p in poses:
            fields(p, 'pos tgt lens fstop', 'camera pose')
            for key in ('pos','tgt'):
                v = p.get(key)
                if not isinstance(v, list) or len(v) != 3: raise ContractError(key + ' needs three coordinates')
                for x in v: number(x, key, -1e6, 1e6)
            if math.dist(p['pos'], p['tgt']) < 1e-9: raise ContractError('Camera cannot look at itself')
            number(p.get('lens'), 'lens', 1, 2000)
            if p.get('fstop') is not None: number(p['fstop'], 'fstop', .1, 128)
            fs.append(p.get('fstop') is not None)
        if any(fs) and not all(fs): raise ContractError('Supply fstop on all poses or none')
        previous = s


def spring_follow(values, fps, hz=4.0, damping=.8, cuts=()):
    """Deterministic damped follower. Resets at cuts; supports scalar or vector samples.

    Returns cached samples for random access. Stable substeps depend on frequency/fps.
    Does not remove deliberate object snaps: use it for the camera's tracking proxy.
    """
    number(fps, 'fps', 1, 240); number(hz, 'hz', .01, 100); number(damping, 'damping', .05, 4)
    if not values: raise ContractError('Follower needs samples')
    vector = isinstance(values[0], (list, tuple))
    xs = [list(x) if vector else [x] for x in values]
    if not xs[0] or any(len(x) != len(xs[0]) for x in xs): raise ContractError('Inconsistent follower dimensions')
    for x in xs:
        for v in x: number(v, 'sample')
    for c in cuts: number(c, 'cut', 0, len(xs)-1, integer=True)
    w = 2 * math.pi * hz
    steps = max(8, math.ceil(w * max(1, damping) / fps * 8))
    dt = 1 / (fps * steps); y = xs[0][:]; vel = [0.] * len(y); out = []
    for i, x in enumerate(xs):
        if i == 0 or i in cuts:
            y = x[:]; vel = [0.] * len(y)
        else:
            prev = xs[i-1]
            for j in range(steps):
                for k in range(len(y)):
                    target = prev[k] + (x[k]-prev[k]) * (j+1)/steps
                    vel[k] += (w*w*(target-y[k])-2*damping*w*vel[k])*dt
                    y[k] += vel[k]*dt
        out.append(y[:] if vector else y[0])
    return out
