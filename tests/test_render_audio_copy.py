"""Copied soundtracks keep every AAC packet when they run a few ms past the last frame (AHe1 render r1: 1526 -> 1525)."""
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

HAVE_FFMPEG = bool(shutil.which('ffmpeg') and shutil.which('ffprobe'))
CANVAS = {'w': 64, 'h': 36, 'fps': 30, 'frames': 30}


def _chrome():
    try:
        from openkatana.render import chrome_path
        return bool(chrome_path())
    except Exception:
        return False


def ffmpeg(*args):
    subprocess.run(['ffmpeg', '-v', 'error', '-y', *map(str, args)], check=True, capture_output=True, stdin=subprocess.DEVNULL)


@unittest.skipUnless(HAVE_FFMPEG, 'needs ffmpeg')
class AudioCopyMuxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.root = Path(self.tmp.name)
        self.frames = self.root / 'frames'; self.frames.mkdir()
        for i in range(CANVAS['frames']):
            Image.new('RGB', (CANVAS['w'], CANVAS['h']), (8 * i, 255 - 8 * i, 90)).save(self.frames / f'{i:05d}.png')
        # 1.003 s of AAC beside 1.000 s of picture: the encoder's last packets end past the final frame, like AHe1.mp4
        self.track = self.root / 'track.m4a'
        ffmpeg('-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000', '-t', '1.003', '-c:a', 'aac', '-b:a', '128k', self.track)

    def video(self, movie):
        from openkatana.render import probe
        return next(s for s in probe(movie)['streams'] if s['codec_type'] == 'video')

    def video_md5(self, movie):
        return subprocess.run(['ffmpeg', '-v', 'error', '-i', str(movie), '-map', '0:v:0', '-c', 'copy', '-f', 'md5', '-'],
                              check=True, capture_output=True, text=True, stdin=subprocess.DEVNULL).stdout.strip()

    def test_copy_keeps_every_packet_and_the_exact_frame_count(self):
        from openkatana.render import audio_packets, encode, soundtrack_check
        source = audio_packets(self.track)
        self.assertGreater(source['seconds'], CANVAS['frames'] / CANVAS['fps'])   # the fixture really runs past the picture
        movie = self.root / 'video.mp4'
        encode(self.frames, CANVAS, movie, soundtrack=self.track)
        unchanged, details, problem = soundtrack_check(self.track, movie)
        self.assertTrue(unchanged, problem)
        self.assertIsNone(problem)
        self.assertEqual(details['output']['packets'], source['packets'])
        video = self.video(movie)
        self.assertEqual(int(video['nb_read_frames']), CANVAS['frames'])
        self.assertEqual((video['width'], video['height'], video['r_frame_rate']), (64, 36, '30/1'))
        self.assertEqual(sorted(p.name for p in self.root.glob('*.mp4')), ['video.mp4'])   # the picture-only pass is removed
        # the picture is bit-identical (and identically tagged) to the single-pass silent encode
        silent = self.root / 'silent.mp4'
        encode(self.frames, CANVAS, silent)
        self.assertEqual(self.video_md5(movie), self.video_md5(silent))
        keys = ('pix_fmt', 'color_range', 'color_space', 'color_transfer', 'color_primaries')
        self.assertEqual({k: video.get(k) for k in keys}, {k: self.video(silent).get(k) for k in keys})

    def test_lost_packets_are_named_in_plain_words(self):
        from openkatana.render import audio_packets, soundtrack_check
        n = audio_packets(self.track)['packets']
        short = self.root / 'short.m4a'
        ffmpeg('-i', self.track, '-map', '0:a:0', '-c', 'copy', '-frames:a', n - 2, short)
        unchanged, details, problem = soundtrack_check(self.track, short)
        self.assertFalse(unchanged)
        self.assertEqual(details['source']['packets'] - details['output']['packets'], 2)
        # AAC end padding varies slightly across FFmpeg versions. Require the
        # exact packet loss and a useful numeric duration, bounded by the fixture.
        match = re.fullmatch(rf'copied soundtrack lost 2 of {n} packets / (\d+\.\d) ms', problem)
        self.assertIsNotNone(match, problem)
        self.assertGreater(float(match[1]), 20)
        self.assertLess(float(match[1]), 24)

    def test_silent_and_mixed_encodes_are_unchanged(self):
        from openkatana.render import encode, probe
        silent = self.root / 'silent.mp4'
        encode(self.frames, CANVAS, silent)
        self.assertEqual([s['codec_type'] for s in probe(silent)['streams']], ['video'])
        self.assertEqual(int(self.video(silent)['nb_read_frames']), CANVAS['frames'])
        wav = self.root / 'audio.wav'
        ffmpeg('-f', 'lavfi', '-i', 'sine=frequency=330:sample_rate=48000', '-t', '1', wav)
        mixed = self.root / 'mixed.mp4'
        encode(self.frames, CANVAS, mixed, mixed=wav)
        streams = probe(mixed)['streams']
        self.assertEqual(sorted(s['codec_name'] for s in streams), ['aac', 'h264'])
        self.assertEqual(int(self.video(mixed)['nb_read_frames']), CANVAS['frames'])

    @unittest.skipUnless(_chrome(), 'needs Chrome')
    def test_render_copy_mode_receipt_and_failure_message(self):
        from openkatana import render as module
        (self.root / 'f').mkdir(); Image.new('RGB', (64, 36), (40, 40, 40)).save(self.root / 'f' / '00000.png')
        edit = {'canvas': dict(CANVAS), 'clips': {'A': {'frames_dir': 'f', 'n': 1, 'fps': 30, 'w': 64, 'h': 36}},
                'shots': [{'f0': 0, 'f1': 30, 'clip': 'A', 'speed': 0}], 'audio': {'src': 'track.m4a', 'mode': 'copy'}}
        (self.root / 't.json').write_text(json.dumps(edit))
        receipt = module.render(self.root / 't.json', self.root / 'ok')
        self.assertTrue(receipt['ok']); self.assertTrue(receipt['audio_stream_unchanged']); self.assertEqual(receipt['contract_failures'], [])
        self.assertEqual(receipt['audio_copy']['output']['packets'], receipt['audio_copy']['source']['packets'])
        self.assertEqual(receipt['frames'], CANVAS['frames'])
        # A mux that drops the last two packets (as -frames:v did) must fail and say so, not just "failed its contract"
        n = module.audio_packets(self.track)['packets']
        short = self.root / 'short.m4a'
        ffmpeg('-i', self.track, '-map', '0:a:0', '-c', 'copy', '-frames:a', n - 2, short)
        real = module.encode
        with mock.patch.object(module, 'encode', lambda frames, canvas, movie, soundtrack=None, mixed=None: real(frames, canvas, movie, short, mixed)), \
             self.assertRaisesRegex(RuntimeError, rf'failed its contract: copied soundtrack lost 2 of {n} packets / \d+\.\d ms'):
            module.render(self.root / 't.json', self.root / 'bad')
        bad = json.loads((self.root / 'bad' / 'receipt.json').read_text(encoding='utf-8'))
        self.assertFalse(bad['ok']); self.assertFalse(bad['audio_stream_unchanged'])


if __name__ == '__main__':
    unittest.main()
