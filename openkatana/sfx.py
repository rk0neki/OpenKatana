"""Sound effects synthesised by OpenKatana (audit F-SFX-001). Every sound is generated deterministically by the code
below (numpy; no recordings, no downloads), so it carries no third-party licence. Timelines place them with
`audio.cues`: [{"sfx": "whoosh", "variant": 2, "at": 1.25, "level_db": -14}] — each cue becomes a mix track of the
generated file (written once under the project's .openkatana/sfx/), at its category's default level unless given.
"""
import hashlib
import wave
from pathlib import Path

import numpy as np

from .contracts import ContractError, fields, number

SR = 48000
VERSION = 1   # bump when synthesis changes (cached files are keyed by it)


def _noise(rng, n):
    return rng.standard_normal(n)


def _env(n, attack, release, sr=SR):
    t = np.arange(n) / sr
    a = np.clip(t / max(attack, 1e-4), 0, 1)
    return a * np.exp(-np.maximum(0, t - attack) / max(release, 1e-4))


def _onepole(x, cutoff_hz, high=False):
    """Time-varying one-pole low-pass (or high-pass) with a per-sample cutoff."""
    c = np.broadcast_to(np.asarray(cutoff_hz, dtype=float), x.shape)
    a = 1 - np.exp(-2 * np.pi * c / SR); y = np.empty_like(x); v = 0.0
    for i in range(len(x)):
        v += a[i] * (x[i] - v); y[i] = v
    return x - y if high else y


def _sweep(f0, f1, n, curve=1.0):
    k = np.linspace(0, 1, n) ** curve
    freq = f0 * (f1 / f0) ** k
    return np.sin(2 * np.pi * np.cumsum(freq) / SR)


def hit(rng, v):
    n = int(SR * (.28 + .05 * v)); body = _sweep(140 + 15 * v, 42, n, .5) * _env(n, .002, .09)
    click = _onepole(_noise(rng, n), 3000) * _env(n, .0005, .006) * 3
    return body + click


def impact(rng, v):
    n = int(SR * (.9 + .1 * v)); boom = _sweep(90, 30, n, .4) * _env(n, .003, .25)
    rumble = _onepole(_noise(rng, n), 400 + 80 * v) * _env(n, .01, .35) * 1.6
    crack = _onepole(_noise(rng, n), 5000, high=True) * _env(n, .0005, .02) * .8
    return boom + rumble + crack


def whoosh(rng, v):
    d = .45 + .08 * v; n = int(SR * d); t = np.linspace(0, 1, n)
    cutoff = 300 + 3200 * np.sin(np.pi * t) ** 2
    x = _onepole(_onepole(_noise(rng, n), cutoff), 150, high=True)
    return x * np.sin(np.pi * t) ** 1.5 * 3


def riser(rng, v):
    d = 1.4 + .3 * v; n = int(SR * d); t = np.linspace(0, 1, n)
    tone = _sweep(180, 1400 + 200 * v, n, 1.6) * .35
    air = _onepole(_noise(rng, n), 600 + 6000 * t ** 2) * 1.5
    return (tone + air) * t ** 2.2


def click(rng, v):
    n = int(SR * .02); return _onepole(_noise(rng, n), 6000) * _env(n, .0002, .002 + .0005 * v) * 4


def slap(rng, v):
    n = int(SR * .12); x = _onepole(_onepole(_noise(rng, n), 4500), 400, high=True)
    return x * _env(n, .0005, .018 + .004 * v) * 4


def pop(rng, v):
    n = int(SR * .09); return _sweep(900 + 80 * v, 300, n, .7) * _env(n, .001, .025)


def glitch(rng, v):
    n = int(SR * (.18 + .04 * v)); out = np.zeros(n); pos = 0
    while pos < n:
        seg = int(SR * rng.uniform(.006, .03)); f = rng.uniform(200, 3000)
        sq = np.sign(np.sin(2 * np.pi * f * np.arange(seg) / SR)) * rng.uniform(.3, .9)
        out[pos:pos + seg] = sq[:max(0, min(seg, n - pos))]; pos += seg + int(SR * rng.uniform(0, .01))
    return np.round(out * 6) / 6 * .7


def ding(rng, v):
    n = int(SR * 1.2); t = np.arange(n) / SR; f = 1320 * (1 + .06 * v)
    return (np.sin(2 * np.pi * f * t) + .45 * np.sin(2 * np.pi * 2.01 * f * t) + .2 * np.sin(2 * np.pi * 3.02 * f * t)) * _env(n, .002, .35) * .6


def shutter(rng, v):
    a = click(rng, v); gap = np.zeros(int(SR * (.055 + .01 * v))); return np.concatenate([a, gap, click(rng, v + 1) * .8])


LIBRARY = {   # name: (category, synth, default level dB under a full-scale mix, description)
    'hit': ('impact', hit, -10, 'short low thump with a click (beat hits, cuts)'),
    'impact': ('impact', impact, -9, 'boom + rumble + crack (drops, title hits)'),
    'whoosh': ('transition', whoosh, -14, 'swept noise pass (whips, pushes)'),
    'riser': ('transition', riser, -16, 'rising tone and air into a drop'),
    'click': ('ui', click, -18, 'tiny click (text, UI)'),
    'slap': ('ui', slap, -14, 'sticker/text slap'),
    'pop': ('ui', pop, -16, 'pitched pop (bubbles, appear)'),
    'glitch': ('digital', glitch, -18, 'bit-crushed squares (glitch transitions)'),
    'ding': ('ui', ding, -18, 'bell ding'),
    'shutter': ('foley', shutter, -16, 'camera shutter double click'),
}
VARIANTS = 4


def generate(name, variant=1):
    """Mono float signal normalised to peak 0.9."""
    if name not in LIBRARY:
        raise ContractError(f'sfx: unknown sound {name!r} (have: {", ".join(LIBRARY)})')
    seed = int(hashlib.sha256(f'{name}:{variant}:{VERSION}'.encode()).hexdigest()[:8], 16)
    x = LIBRARY[name][1](np.random.default_rng(seed), variant - 1)
    peak = np.abs(x).max() or 1
    return x / peak * .9


def path_for(root, name, variant):
    return Path(root) / '.openkatana' / 'sfx' / f'{name}-{variant}-v{VERSION}.wav'


def ensure(root, name, variant=1):
    p = path_for(root, name, variant)
    if not p.is_file():
        x = generate(name, variant); p.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(p), 'wb') as f:
            f.setparams((2, 2, SR, 0, 'NONE', 'not compressed'))
            f.writeframes((np.repeat(x[:, None], 2, axis=1) * 32767).astype('<i2').tobytes())
    return p


def catalog():
    return [{'sfx': n, 'category': c, 'default_level_db': lv, 'variants': VARIANTS, 'description': d,
             'duration_s': round(len(generate(n, 1)) / SR, 3)} for n, (c, _f, lv, d) in LIBRARY.items()]


def validate_cue(cue, where):
    fields(cue, 'sfx variant at level_db', where)
    if cue.get('sfx') not in LIBRARY:
        raise ContractError(f'{where}.sfx: one of {", ".join(LIBRARY)}')
    number(cue.get('variant', 1), where + '.variant', 1, VARIANTS, integer=True)
    number(cue.get('at'), where + '.at', 0)
    number(cue.get('level_db', LIBRARY[cue['sfx']][2]), where + '.level_db', -60, 6)


def cue_track(cue, root):
    """The mix track for a cue (relative path inside the project)."""
    p = ensure(root, cue['sfx'], cue.get('variant', 1))
    return {'src': p.relative_to(Path(root)).as_posix(), 'at': cue['at'], 'volume': round(10 ** (cue.get('level_db', LIBRARY[cue['sfx']][2]) / 20), 6)}
