"""Frame-level reference measurement (analyze_reference measure) and the review aids (compare_reference side_by_side /
look, shot_sheet, eye_sheet), on a synthetic reference whose cuts, dip, cadence, texture and transition are known."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

try:
    import cv2
except ImportError:   # the vision extra
    cv2 = None

FPS, N, W, H = 60, 180, 640, 360
CUTS = [36, 72, 108, 144]


def make_reference(path):
    """Five 36-frame shots (distinct blob patterns and tints). The picture steps at 24p in a 2-3 cadence; each shot opens
    at 0.9x scale and 1.8x exposure, easing to rest over 10 frames; frames 90-95 dip to half brightness; 2 px white specks
    change with every 24p picture."""
    rng = np.random.default_rng(7)
    tints = [(1, .7, .5), (.5, .8, 1), (.7, 1, .6), (1, .5, .9), (.9, .9, .5)]
    shots = []
    for t in tints:
        base = cv2.GaussianBlur(rng.random((H + 80, W + 80)).astype(np.float32), (0, 0), 9)
        base = (base - base.min()) / (base.max() - base.min())
        shots.append(np.dstack([base * c for c in t]) * 200 + 20)
    specks = [rng.integers(0, [W - 2, H - 2], (40, 2)) for _ in range(80)]
    p = subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS),
                          '-i', '-', '-c:v', 'libx264', '-crf', '12', '-pix_fmt', 'yuv420p', str(path)], stdin=subprocess.PIPE)
    for f in range(N):
        s = f // 36; k = f - s * 36; pic = (f * 24) // FPS            # the 24p picture this frame shows
        off = (pic * 3) % 60
        img = shots[s][40:40 + H, off:off + W].copy()
        u = min(1, k / 10); scale = .9 + .1 * u; expo = 1.8 - .8 * u
        M = np.array([[scale, 0, W / 2 * (1 - scale)], [0, scale, H / 2 * (1 - scale)]], np.float32)
        img = cv2.warpAffine(img, M, (W, H), borderMode=cv2.BORDER_REFLECT) * expo
        if 90 <= f < 96:
            img = img * .5
        for x, y in specks[pic % 80]:
            img[y:y + 2, x:x + 2] = 255
        p.stdin.write(np.clip(img, 0, 255).astype(np.uint8).tobytes())
    p.stdin.close(); p.wait()


@unittest.skipUnless(cv2 is not None and shutil.which('ffmpeg'), 'needs the vision extra and ffmpeg')
class ReferenceMeasureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(); cls.root = Path(cls.tmp.name)
        cls.video = cls.root / 'ref.mp4'; make_reference(cls.video)
        from openkatana.reference_measure import measure
        cls.m = measure(cls.video, cls.root / 'm', 0, 10, ['cuts', 'cadence', 'look', 'textures', 'transitions'])

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_cuts_and_dips(self):
        cuts = [c['frame'] for c in self.m['cuts'] if c['kind'] == 'cut']
        dips = [c['frame'] for c in self.m['cuts'] if c['kind'] == 'dip']
        self.assertEqual(cuts, CUTS)
        self.assertEqual(dips, [90, 96])
        report = json.loads(Path(self.m['report']).read_text())
        self.assertAlmostEqual(next(c for c in report['cuts'] if c['frame'] == 90)['luma_ratio'], .5, delta=.08)

    def test_cadence_reads_24p_on_a_60p_clock(self):
        self.assertEqual(self.m['cadence']['base_fps'], 23.976)
        g = self.m['cadence']['gap_counts']
        self.assertGreater(g['2'], 10); self.assertGreater(g['3'], 10)

    def test_texture_specks_refresh_with_each_picture(self):
        t = self.m['textures']
        self.assertAlmostEqual(t['speck_pictures_per_second'], 24, delta=4)
        self.assertGreater(t['overlap_by_lag'][0], t['overlap_by_lag'][2])

    def test_transition_curve(self):
        tr = self.m['transitions']; c = tr['local_curve']
        self.assertEqual(tr['cuts_used'], 4)
        self.assertAlmostEqual(c['scale'][0], .9, delta=.03)
        self.assertAlmostEqual(c['exposure'][0], 1.8, delta=.2)
        self.assertAlmostEqual(c['exposure'][-1], 1, delta=.05); self.assertAlmostEqual(c['scale'][-1], 1, delta=.01)
        from openkatana.contracts import validate      # the arrays are a valid local_curve as they stand
        (self.root / 'f').mkdir(exist_ok=True); cv2.imwrite(str(self.root / 'f' / '00000.png'), np.zeros((36, 64, 3), np.uint8))
        validate({'canvas': {'w': 64, 'h': 36, 'fps': 60, 'frames': 2}, 'clips': {'A': {'frames_dir': 'f', 'n': 1, 'fps': 60, 'w': 64, 'h': 36}},
                  'shots': [{'f0': 0, 'f1': 2, 'clip': 'A', 'fx': {'local_curve': c}}]}, self.root)

    def test_look(self):
        overall = self.m['look']['overall']
        self.assertLess(overall['p2'], overall['p50']); self.assertLess(overall['p50'], overall['p98'])
        self.assertEqual(len(self.m['look']['shots']), 5)

    def test_review_aids(self):
        from openkatana import review_tools
        out = self.root / 'cmp'; out.mkdir()
        diff = review_tools.look_difference(self.video, self.video)
        self.assertTrue(all(abs(v) < 1e-9 for v in diff['render_minus_reference'].values()))
        sbs = review_tools.side_by_side(self.video, self.video, out, 0)
        info = json.loads(subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height',
                                          '-of', 'json', sbs], capture_output=True, text=True).stdout)['streams'][0]
        self.assertEqual((info['width'], info['height']), (1920, 540))
        sheet = review_tools.shot_sheet(self.video, self.root / 'sheet', [0, *CUTS, N], FPS, .5, 5)
        self.assertEqual([s['frame'] for s in sheet['shots']], [18, 54, 90, 126, 162])
        self.assertTrue(Path(sheet['preview_images'][0]).is_file())

    def test_api(self):
        from openkatana.agent_api import AgentAPI
        from openkatana.contracts import ContractError
        api = AgentAPI(self.root / 'ws'); (self.root / 'ws').mkdir(exist_ok=True); api.create_project('p', 'p')
        r = api.analyze_reference('p', str(self.video), 0, 3, .25, ['cuts'])
        self.assertEqual([c['frame'] for c in r['measured']['cuts'] if c['kind'] == 'cut'], CUTS)
        s = api.shot_sheet('p', str(self.video), cuts=CUTS, fps=60, start_frame=72)
        self.assertEqual([x['n'] for x in s['shots']], [3, 4, 5])
        with self.assertRaisesRegex(ContractError, 'times, side_by_side or look'):
            api.compare_reference('p', str(self.video), str(self.video))
        self.assertIn('look', api.compare_reference('p', str(self.video), str(self.video), look=True))


@unittest.skipUnless(cv2 is not None, 'needs the vision extra')
class EyeSheetTests(unittest.TestCase):
    def test_crops_follow_the_eye_landmarks(self):
        from openkatana.review_tools import eye_sheet
        from openkatana.contracts import ContractError

        class Detector:
            def __init__(self, size): self.size = size
            def getInputSize(self): return self.size
            def detect(self, im):   # one face: box, right eye (300, 200), left eye (400, 200) in 960-wide pixels
                return 1, np.array([[250, 120, 220, 260, 300, 200, 400, 200, 350, 260, 310, 320, 390, 320, .99]], np.float32)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / 'f').mkdir()
            for i in range(3):
                im = np.full((540, 960, 3), 40, np.uint8); im[190:210, 290:410] = 250; cv2.imwrite(str(root / 'f' / f'{i:05d}.png'), im)
            clip = {'frames_dir': 'f', 'n': 3, 'fps': 30, 'w': 960, 'h': 540}
            with patch.object(cv2, 'FaceDetectorYN', create=True) as fake:
                fake.create.side_effect = lambda model, cfg, size, *a: Detector(size)
                r = eye_sheet(root, clip, root / 'out', [0, 2])
            self.assertEqual([x['eye_distance'] for x in r['frames']], [100.0, 100.0])
            self.assertTrue(Path(r['preview_images'][0]).is_file())
            with self.assertRaisesRegex(ContractError, 'out of range'):
                eye_sheet(root, clip, root / 'out2', [3])


if __name__ == '__main__':
    unittest.main()
