"""F-AUD-003: tempo / beat grid / downbeats / sections on synthetic music with known structure."""
import shutil
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

HAVE_FFMPEG = bool(shutil.which('ffmpeg'))
SR = 44100


def track(path, bpm, seconds, offbeat_hats=True, phase=.05, quiet_until=None):
    """Kick on every beat (accented on beat 1 of 4), optional hats on the offbeats, a level step at `quiet_until`."""
    rng = np.random.default_rng(3); n = int(seconds * SR); x = np.zeros(n); P = 60 / bpm
    kick = np.sin(2 * np.pi * 60 * np.arange(int(.12 * SR)) / SR) * np.exp(-np.arange(int(.12 * SR)) / (.03 * SR))
    hat = rng.normal(0, 1, int(.03 * SR)) * np.exp(-np.arange(int(.03 * SR)) / (.006 * SR)) * .25
    k = 0
    while phase + k * P < seconds - .2:
        i = int((phase + k * P) * SR); x[i:i + len(kick)] += kick * (1.0 if k % 4 == 0 else .6)
        if offbeat_hats:
            j = int((phase + (k + .5) * P) * SR); x[j:j + len(hat)] += hat
        k += 1
    if quiet_until:
        x[:int(quiet_until * SR)] *= .25
    x = (x / np.abs(x).max() * .8 * 32767).astype('<i2')
    with wave.open(str(path), 'wb') as f:
        f.setparams((1, 2, SR, 0, 'NONE', 'not compressed')); f.writeframes(x.tobytes())


@unittest.skipUnless(HAVE_FFMPEG, 'needs ffmpeg')
class AudioAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.dir = Path(self.tmp.name)

    def test_grid_downbeats_and_sections(self):
        from openkatana.audio_analysis import analyze
        track(self.dir / 't.wav', 128, 16, phase=.07, quiet_until=.07 + 12 * 60 / 128)   # level step on the downbeat of bar 4
        r, _ = analyze(self.dir / 't.wav', fps=30)
        self.assertAlmostEqual(r['bpm'], 128, delta=.3)
        truth = .07 + np.arange(len(r['beats'])) * 60 / 128
        self.assertLess(np.abs(np.array(r['beats']) - truth[:len(r['beats'])]).max(), .015)
        self.assertLess(abs(r['downbeats'][0] - .07), .015)                  # accented beat 1
        self.assertEqual(len(r['sections']), 2)
        self.assertLess(abs(r['sections'][1]['t0'] - (.07 + 12 * 60 / 128)), .05)
        self.assertEqual(r['sections'][1]['label'], 'loud')
        self.assertEqual(r['beat_frames'][:3], [2, 16, 30])

    def test_octave_follows_offbeats(self):
        from openkatana.audio_analysis import analyze
        track(self.dir / 'slow.wav', 70, 14, offbeat_hats=False)
        r, _ = analyze(self.dir / 'slow.wav')
        self.assertAlmostEqual(r['bpm'], 70, delta=.3)            # empty offbeats: not doubled
        track(self.dir / 'busy.wav', 85, 14, offbeat_hats=True)
        r, _ = analyze(self.dir / 'busy.wav')
        self.assertAlmostEqual(r['bpm'], 85, delta=.3)            # hats at half strength stay offbeats

    def test_silence_and_errors(self):
        from openkatana.audio_analysis import analyze
        from openkatana.contracts import ContractError
        with wave.open(str(self.dir / 's.wav'), 'wb') as f:
            f.setparams((1, 2, SR, 0, 'NONE', 'not compressed')); f.writeframes(np.zeros(SR * 3, dtype='<i2').tobytes())
        with self.assertRaisesRegex(ContractError, 'Too few onsets'):
            analyze(self.dir / 's.wav')


if __name__ == '__main__':
    unittest.main()
