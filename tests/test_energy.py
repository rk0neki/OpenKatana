"""F-AUD-004: energy measurement on a synthetic video with a known pan, cut, white flash and shake burst."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import numpy as np

HAVE_FFMPEG = bool(shutil.which('ffmpeg'))


def _have_cv2():
    try:
        import cv2  # noqa: F401
        return True
    except ImportError:
        return False


def make_video(path, fps=30):
    rng = np.random.default_rng(5)
    big = lambda seed: np.kron(np.random.default_rng(seed).integers(30, 200, (60, 80)), np.ones((8, 8)))   # 480x640 blocks
    A, B = big(1), big(2)
    W, H = 320, 240; frames = []
    for i in range(120):
        if i < 30:                                   # pan: 2 px/frame to the right
            src, x, y = A, 100 - 2 * i, 100
        else:                                         # cut at 30 to B; shake burst 70-76
            jx, jy = ((rng.integers(-8, 9), rng.integers(-8, 9)) if 70 <= i <= 76 else (0, 0))
            src, x, y = B, 100 + jx, 100 + jy
        f = src[y:y + H, x:x + W].astype(np.uint8)
        if 50 <= i <= 52:                             # white flash, 3 frames
            f = np.full_like(f, 245)
        frames.append(f)
    raw = np.stack(frames).tobytes()
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'gray', '-s', f'{W}x{H}', '-r', str(fps), '-i', '-',
                    '-c:v', 'libx264', '-crf', '8', '-pix_fmt', 'yuv420p', str(path)], input=raw, check=True)


@unittest.skipUnless(HAVE_FFMPEG and _have_cv2(), 'needs ffmpeg and OpenCV')
class EnergyTests(unittest.TestCase):
    def test_events_and_check(self):
        from openkatana.energy import check, measure
        with tempfile.TemporaryDirectory() as tmp:
            v = Path(tmp) / 'v.mp4'; make_video(v)
            r = measure(v, canvas_w=320)
            ev = r['events']
            self.assertEqual([c['t'] for c in ev['cuts']], [1.0])
            self.assertEqual([(f['t'], f['n'], f['type']) for f in ev['flashes']], [(round(50 / 30, 3), 3, 'white')])
            self.assertTrue(any(70 / 30 - .1 <= s['t'] <= 77 / 30 for s in ev['shakes']), ev['shakes'])
            self.assertEqual(len(ev['pans']), 1)
            pan = ev['pans'][0]['edl']['cam']['pan']
            self.assertAlmostEqual(pan['dx'], 2 * 30 / 160 * 160 / 320, delta=.03)   # image moves right 60 px/s of 320
            self.assertGreater(pan['dx'], 0)
            same = check(r, r)
            self.assertTrue(same['pass'])
            calm = {'rates': {**r['rates'], 'cuts_ps': 0, 'shake_ps': 0}}
            self.assertIn('cuts / s', check(calm, r)['fails'])


if __name__ == '__main__':
    unittest.main()
