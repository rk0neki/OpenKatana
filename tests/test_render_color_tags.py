"""Rendered video.mp4 is tagged BT.709 throughout: ffmpeg 7.1+ ignores the output -color_primaries/-color_trc options
and tags the stream from the filtered frames, so untagged PNGs left primaries and transfer "unknown"
(work/face-text-002/editor-tool-regression/receipt.json). The tags must come from the filter chain without moving a pixel."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image

HAVE_FFMPEG = bool(shutil.which('ffmpeg') and shutil.which('ffprobe'))
CANVAS = {'w': 64, 'h': 36, 'fps': 30, 'frames': 30}
BT709 = {'pix_fmt': 'yuv420p', 'color_range': 'tv', 'color_space': 'bt709', 'color_transfer': 'bt709', 'color_primaries': 'bt709'}


def _chrome():
    try:
        from openkatana.render import chrome_path
        return bool(chrome_path())
    except Exception:
        return False


def ffmpeg(*args):
    return subprocess.run(['ffmpeg', '-v', 'error', '-y', *map(str, args)], check=True, capture_output=True, text=True,
                          stdin=subprocess.DEVNULL).stdout.strip()


def tags(info):
    video = next(s for s in info['streams'] if s['codec_type'] == 'video')
    return {k: video.get(k) for k in BT709}


@unittest.skipUnless(HAVE_FFMPEG, 'needs ffmpeg')
class ColorTagTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.root = Path(self.tmp.name)
        self.frames = self.root / 'frames'; self.frames.mkdir()
        for i in range(CANVAS['frames']):
            Image.new('RGB', (CANVAS['w'], CANVAS['h']), (8 * i, 255 - 8 * i, 90)).save(self.frames / f'{i:05d}.png')

    def probe_tags(self, movie):
        from openkatana.render import probe
        return tags(probe(movie))

    def test_every_encode_mode_tags_all_four(self):
        from openkatana.render import encode, soundtrack_check
        track, wav = self.root / 'track.m4a', self.root / 'audio.wav'
        ffmpeg('-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000', '-t', '1.003', '-c:a', 'aac', '-b:a', '128k', track)
        ffmpeg('-f', 'lavfi', '-i', 'sine=frequency=330:sample_rate=48000', '-t', '1', wav)
        for mode, kw in (('silent', {}), ('copy', {'soundtrack': track}), ('mixed', {'mixed': wav})):
            with self.subTest(mode=mode):
                movie = self.root / f'{mode}.mp4'
                encode(self.frames, CANVAS, movie, **kw)
                self.assertEqual(self.probe_tags(movie), BT709)
        unchanged, _, problem = soundtrack_check(track, self.root / 'copy.mp4')
        self.assertTrue(unchanged, problem)

    def test_tagging_moves_no_pixels(self):
        from openkatana import render as module
        new = list(module.VIDEO_ENCODE)
        chain = new[new.index('-vf') + 1]
        self.assertIn(',setparams=', chain)
        old = [a.split(',setparams=')[0] if a == chain else a for a in new]   # the chain before this fix
        self.addCleanup(setattr, module, 'VIDEO_ENCODE', new)
        movies = {}
        for name, args in (('old', old), ('new', new)):
            module.VIDEO_ENCODE = args
            movies[name] = self.root / f'{name}.mp4'
            module.encode(self.frames, CANVAS, movies[name])
        module.VIDEO_ENCODE = new
        # Some FFmpeg builds infer BT.709 even without setparams. The contract
        # is explicit output tags with unchanged pixels, not missing old tags.
        self.assertEqual(self.probe_tags(movies['new']), BT709)
        decoded = {k: ffmpeg('-i', m, '-map', '0:v:0', '-f', 'framemd5', '-') for k, m in movies.items()}
        self.assertEqual(decoded['old'], decoded['new'])
        coded = {k: ffmpeg('-i', m, '-map', '0:v:0', '-c', 'copy', '-f', 'md5', '-') for k, m in movies.items()}
        self.assertEqual(coded['old'], coded['new'])   # only the SPS colour description differs

    def test_srgb_tagged_frames_are_still_tagged_bt709(self):
        from openkatana.render import encode
        for p in self.frames.glob('*.png'):
            ffmpeg('-i', p, '-vf', 'setparams=color_primaries=bt709:color_trc=iec61966-2-1', p.with_suffix('.srgb.png'))
            p.with_suffix('.srgb.png').replace(p)
        frame = subprocess.run(['ffprobe', '-v', 'error', '-show_frames', '-show_entries', 'frame=color_transfer', '-of', 'csv=p=0',
                                str(self.frames / '00000.png')], check=True, capture_output=True, text=True, stdin=subprocess.DEVNULL)
        self.assertEqual(frame.stdout.strip(), 'iec61966-2-1')   # the old flags would have tagged the movie sRGB
        movie = self.root / 'srgb.mp4'
        encode(self.frames, CANVAS, movie)
        self.assertEqual(self.probe_tags(movie), BT709)

    @unittest.skipUnless(_chrome(), 'needs Chrome')
    def test_render_receipt_probe_is_tagged(self):
        from openkatana.render import render
        (self.root / 'f').mkdir(); Image.new('RGB', (64, 36), (40, 40, 40)).save(self.root / 'f' / '00000.png')
        edit = {'canvas': dict(CANVAS), 'clips': {'A': {'frames_dir': 'f', 'n': 1, 'fps': 30, 'w': 64, 'h': 36}},
                'shots': [{'f0': 0, 'f1': 30, 'clip': 'A', 'speed': 0}]}
        (self.root / 't.json').write_text(json.dumps(edit))
        receipt = render(self.root / 't.json', self.root / 'out')
        self.assertTrue(receipt['ok'])
        self.assertEqual(tags(receipt['probe']), BT709)
        self.assertEqual(self.probe_tags(self.root / 'out' / 'video.mp4'), BT709)


if __name__ == '__main__':
    unittest.main()
