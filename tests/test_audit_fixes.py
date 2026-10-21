"""Regression tests for defects found by the whole-product audit."""
import json
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
HAVE_FFMPEG = bool(shutil.which('ffmpeg'))


def png_chunks(path):
    data = Path(path).read_bytes(); i = 8; chunks = []
    while i < len(data):
        length = struct.unpack('>I', data[i:i + 4])[0]; kind = data[i + 4:i + 8].decode('latin1'); chunks.append(kind); i += 12 + length
        if kind == 'IDAT':
            break
    return chunks


@unittest.skipUnless(HAVE_FFMPEG, 'needs ffmpeg')
class PlateColourTests(unittest.TestCase):
    """F-OK-008: BT.709-tagged footage must not produce colour-managed (gAMA/cHRM/cICP) plates."""

    def test_prepare_writes_untagged_plates_with_unchanged_pixels(self):
        from openkatana.render import prepare
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp); src = tmp / 'tagged.mp4'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=160x90:rate=30:duration=0.2', '-pix_fmt', 'yuv420p',
                            '-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709', '-c:v', 'libx264', '-crf', '12', str(src)], check=True)
            clip = prepare(src, tmp / 'plates')
            first = tmp / 'plates' / '00000.png'
            self.assertEqual(clip['n'], 6)
            self.assertFalse({'gAMA', 'cHRM', 'cICP', 'iCCP', 'sRGB'} & set(png_chunks(first)))
            raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(src), '-frames:v', '1', '-vf', 'format=rgb24', '-f', 'rawvideo', '-'], capture_output=True, check=True).stdout
            expected = np.frombuffer(raw, dtype=np.uint8).reshape(90, 160, 3)
            self.assertTrue((np.asarray(Image.open(first).convert('RGB')) == expected).all())

    def test_renderer_decodes_plates_without_colour_management(self):
        engine = (ROOT / 'openkatana' / 'web' / 'engine.js').read_text(encoding='utf-8')
        self.assertIn("colorSpaceConversion:'none'", engine)


def _have_cv2():
    try:
        import cv2  # noqa: F401
        return True
    except ImportError:
        return False


@unittest.skipUnless(_have_cv2(), 'needs the vision extra')
class InterpolationAnnotationTests(unittest.TestCase):
    """F-OK-009: interpolate keeps the matte and face track and apply rescales srcf, listing every change."""

    def setUp(self):
        from openkatana.agent_api import AgentAPI
        from openkatana.render import write_json
        parent = ROOT / 'work'; parent.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=parent); self.addCleanup(self.tmp.cleanup)
        self.ws = Path(self.tmp.name); self.api = AgentAPI(self.ws); self.api.create_project('p', 'p'); root = self.ws / 'p'
        (root / 'f').mkdir(); (root / 'm').mkdir(); rows = []
        for i in range(4):
            im = Image.new('RGB', (64, 48), (20, 20, 20)); x = 10 + 6 * i
            from PIL import ImageDraw
            ImageDraw.Draw(im).ellipse((x, 10, x + 20, 34), fill=(230, 180, 140)); im.save(root / 'f' / f'{i:05d}.png')
            m = Image.new('RGBA', (64, 48), (255, 255, 255, 0)); ImageDraw.Draw(m).ellipse((x, 10, x + 20, 34), fill=(255, 255, 255, 255)); m.save(root / 'm' / f'{i:05d}.png')
            rows.append({'f': i, 'box': [x, 10, 20, 24], 'eyes': [[x + 6, 18], [x + 14, 18]]})
        write_json(root / 'faces.json', rows)
        clip = {'frames_dir': 'f', 'n': 4, 'fps': 30, 'w': 64, 'h': 48, 'pattern': '%05d.png', 'mask_dir': 'm', 'faces': 'faces.json'}
        tl = {'canvas': {'w': 64, 'h': 48, 'fps': 30, 'frames': 4}, 'clips': {'A': clip}, 'shots': [{'f0': 0, 'f1': 4, 'clip': 'A', 'srcf': 1, 'speed': 0}]}
        self.api.save_timeline('p', tl, None); self.root = root

    def test_apply_keeps_annotations_and_rescales_srcf(self):
        result = self.api.analyze_clip('p', 'A', 'interpolate', {'multiplier': 2}, apply=True)
        clip = self.api.get_project('p')['timeline']['clips']['A']; shot = self.api.get_project('p')['timeline']['shots'][0]
        self.assertEqual((clip['n'], clip['fps'], shot['srcf']), (8, 60, 2))
        self.assertTrue(clip['mask_dir'].endswith('/mask') and clip['faces'].endswith('/faces.json'))
        self.assertEqual({c['path'] for c in result['changes']}, {'clips.A.frames_dir', 'clips.A.n', 'clips.A.fps', 'clips.A.mask_dir', 'clips.A.faces', 'shots[0].srcf'})
        track = json.loads((self.root / clip['faces']).read_text())
        self.assertEqual(len(track), 8); self.assertEqual(track[2]['box'], [16.0, 10.0, 20.0, 24.0]); self.assertEqual(track[3]['src'], 'interp')
        self.assertEqual(track[3]['box'], [19.0, 10.0, 20.0, 24.0])
        mask0 = np.asarray(Image.open(self.root / clip['mask_dir'] / '00002.png'))[:, :, 3]
        self.assertTrue((mask0 == np.asarray(Image.open(self.root / 'm' / '00001.png'))[:, :, 3]).all())
        from openkatana.contracts import validate
        validate(self.api.get_project('p')['timeline'], self.root)


@unittest.skipUnless(HAVE_FFMPEG, 'needs ffmpeg')
class AudioValidationTests(unittest.TestCase):
    """F-OK-012: problems the mixer would hit at render time are reported by validation."""

    def setUp(self):
        import wave
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.root = Path(self.tmp.name)
        with wave.open(str(self.root / 'tone.wav'), 'wb') as f:   # 2 s, constant 0.5 full scale
            f.setparams((1, 2, 48000, 0, 'NONE', 'not compressed')); f.writeframes(np.full(96000, 16384, dtype='<i2').tobytes())
        (self.root / 'f').mkdir(); Image.new('RGB', (32, 18)).save(self.root / 'f' / '00000.png')
        self.edit = {'canvas': {'w': 32, 'h': 18, 'fps': 30, 'frames': 30}, 'clips': {'A': {'frames_dir': 'f', 'n': 1, 'fps': 30, 'w': 32, 'h': 18}},
                     'shots': [{'f0': 0, 'f1': 30, 'clip': 'A', 'speed': 0}]}

    def check(self, audio, error=None):
        from openkatana.contracts import ContractError, validate
        edit = {**self.edit, 'audio': audio}
        if error:
            with self.assertRaisesRegex(ContractError, error):
                validate(json.loads(json.dumps(edit)), self.root)
        else:
            validate(json.loads(json.dumps(edit)), self.root)

    def test_render_time_audio_errors_are_validation_errors(self):
        t = lambda **k: {'mode': 'mix', 'tracks': [{'src': 'tone.wav', **k}]}
        self.check(t(at=1.5), 'after the end')
        self.check(t(start=1.5, duration=1), 'extends beyond')
        self.check(t(duration=.5, fade_in=.3, fade_out=.3), 'fades')
        self.check(t(start=3), 'beyond the')
        self.check({'mode': 'mix', 'tracks': [{'src': 'f/00000.png'}]}, 'No audio stream')
        self.check(t(volume=3), 'clips')
        self.check({**t(volume=3), 'limiter': True})
        self.check(t(volume=1.9))
        self.check({'mode': 'copy', 'src': 'tone.wav'}, 'audio copy')


class FontAndFieldTests(unittest.TestCase):
    """F-OK-013 corrupt fonts fail validation; F-OK-003 renderer-read fields are accepted."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.root = Path(self.tmp.name)
        (self.root / 'f').mkdir(); Image.new('RGB', (32, 18)).save(self.root / 'f' / '00000.png')
        self.edit = {'canvas': {'w': 32, 'h': 18, 'fps': 30, 'frames': 3}, 'clips': {'A': {'frames_dir': 'f', 'n': 1, 'fps': 30, 'w': 32, 'h': 18}},
                     'shots': [{'f0': 0, 'f1': 3, 'clip': 'A', 'speed': 0}]}

    def test_corrupt_and_truncated_fonts_rejected_with_names(self):
        from openkatana.contracts import ContractError, validate
        (self.root / 'bad.ttf').write_bytes(b'not a font' * 20)
        (self.root / 'cut.ttf').write_bytes(b'true' + b'0' * 40)
        for name in ('bad.ttf', 'cut.ttf'):
            with self.assertRaisesRegex(ContractError, f'"X" \\({name}\\)'):
                validate({**self.edit, 'fonts': [{'family': 'X', 'url': name}]}, self.root)

    def test_renderer_read_fields_accepted(self):
        from openkatana.contracts import ContractError, validate
        validate({**self.edit, 'shots': [{**self.edit['shots'][0], 'fx': {'blurOut': {'frame': False}, 'magenta': {'from': 20, 'to': 8}}}]})
        windows_arial = Path('C:/Windows/Fonts/arial.ttf')
        if windows_arial.is_file():
            shutil.copyfile(windows_arial, self.root / 'a.ttf')
            t = {'type': 'font', 'family': 'A', 'text': 'x', 'pos': [.5, .5], 'f0': 0, 'f1': 3}
            for w in ('bold', 'normal', '600', 700):
                validate({**self.edit, 'fonts': [{'family': 'A', 'url': 'a.ttf'}], 'text': [{**t, 'weight': w}]}, self.root)
            with self.assertRaisesRegex(ContractError, 'weight'):
                validate({**self.edit, 'fonts': [{'family': 'A', 'url': 'a.ttf'}], 'text': [{**t, 'weight': 'heavy'}]}, self.root)


class WarningsAndLimitsTests(unittest.TestCase):
    """F-OK-014 warnings, F-OK-015 limits, F-OK-010 layer text in the reference audit."""
    base = {'canvas': {'w': 320, 'h': 180, 'fps': 30, 'frames': 30},
            'clips': {'A': {'frames_dir': 'f', 'n': 10, 'fps': 30, 'w': 320, 'h': 180}, 'Q': {'frames_dir': 'q', 'n': 10, 'fps': 30, 'w': 100, 'h': 100}},
            'shots': [{'f0': 0, 'f1': 30, 'clip': 'A'}]}

    def codes(self, **shot):
        from openkatana.warnings import timeline_warnings
        edit = json.loads(json.dumps(self.base)); edit['shots'][0].update(shot)
        return sorted(w['code'] for w in timeline_warnings(edit))

    def test_warnings(self):
        self.assertEqual(self.codes(), ['clamp_past_end'])                 # 1 s from a 0.33 s clip, default clamp
        self.assertEqual(self.codes(loop='clamp'), [])                     # explicit hold: no warning
        self.assertEqual(self.codes(loop='loop'), [])
        self.assertEqual(self.codes(speed=0), [])
        self.assertEqual(self.codes(speed=0, clip='Q'), ['cover_crop'])
        self.assertEqual(self.codes(speed=0, clip='Q', cam={'crop': .3}), [])
        self.assertEqual(self.codes(speed=0, fx={'outline': True}), ['needs_matte'])
        self.assertEqual(self.codes(speed=0, out='magenta'), ['magenta_out'])
        self.assertEqual(self.codes(speed=0, layers=[{'type': 'polygon3d', 'points': [[0, 0, 0], [.2, 0, 0], [0, .2, 0]]}]), ['polygon3d_units'])

    def test_canvas_limit_and_clip_ids(self):
        from openkatana.contracts import ContractError, validate
        edit = json.loads(json.dumps(self.base)); edit['canvas'].update(w=4096, h=2160); validate(edit)
        edit = json.loads(json.dumps(self.base)); edit['clips']['A B'] = edit['clips'].pop('A'); edit['shots'][0]['clip'] = 'A B'
        with self.assertRaisesRegex(ContractError, 'Clip id'):
            validate(edit)

    def test_reference_audit_reads_layer_text(self):
        from openkatana.editor_tools import audit_plan
        from openkatana.render import digest, write_json
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); src = root / 'ref.bin'; src.write_bytes(b'reference')
            plan = {'source': str(src), 'fps': 30, 'frames': 30, 'cut_frames': [], 'texts': [{'text': 'HI', 'f0': 0, 'f1': 15}], 'allow_extra_text': False}
            write_json(root / 'reference-plan.json', {'plan': plan, 'source_sha256': digest(src)})
            edit = json.loads(json.dumps(self.base)); edit['shots'][0]['layers'] = [{'type': 'text', 'text': 'HI', 'at': 0, 'd': .5}]
            self.assertTrue(audit_plan(root, edit)['matches_plan'])
            edit['shots'][0]['layers'][0]['at'] = .1
            self.assertFalse(audit_plan(root, edit)['matches_plan'])


def _chrome():
    try:
        from openkatana.render import chrome_path
        return bool(chrome_path())
    except Exception:
        return False


class TransitionTests(unittest.TestCase):
    """F-STU-002: two-shot transitions (contract, shared frame-window rule, renderer composite)."""
    clips = {'A': {'frames_dir': 'a', 'n': 1, 'fps': 30, 'w': 64, 'h': 36}, 'B': {'frames_dir': 'b', 'n': 1, 'fps': 30, 'w': 64, 'h': 36}}

    def edit(self, spec, cut=30, frames=60):
        return {'canvas': {'w': 64, 'h': 36, 'fps': 30, 'frames': frames}, 'clips': self.clips,
                'shots': [{'f0': 0, 'f1': cut, 'clip': 'A', 'speed': 0}, {'f0': cut, 'f1': frames, 'clip': 'B', 'speed': 0, 'transition': spec}]}

    def test_renderer_defaults_match_contract(self):
        import re
        from openkatana.transitions import SPECS
        js = (ROOT / 'openkatana' / 'web' / 'transitions.js').read_text(encoding='utf-8')
        block = re.search(r'// DEFAULTS-BEGIN\s*const DEFAULTS = (\{.*?\});\s*// DEFAULTS-END', js, re.S).group(1)
        table = json.loads(block)
        self.assertEqual(set(table), set(SPECS))
        for kind, (d, params, _) in SPECS.items():
            self.assertEqual(table[kind], {'d': d, 'params': params}, kind)

    def test_frame_window(self):
        from openkatana.transitions import frame_window
        self.assertEqual(frame_window({'type': 'dissolve'}, 30, 30), (23, 38))
        self.assertEqual(frame_window({'type': 'dissolve', 'align': 'start'}, 30, 30), (30, 45))
        self.assertEqual(frame_window({'type': 'dissolve', 'align': 'end'}, 30, 30), (15, 30))
        self.assertEqual(frame_window({'type': 'push', 'd': .01}, 30, 30), (29, 31))      # at least two frames
        self.assertEqual(frame_window({'type': 'flash'}, 30, 30), (30, 37))               # 1 peak + ceil(.06*ln 20*30) tail
        self.assertEqual(frame_window({'type': 'flash', 'pre_frames': 3}, 30, 30), (27, 37))

    def test_validation(self):
        from openkatana.contracts import ContractError, validate
        validate(self.edit({'type': 'wipe', 'shape': 'star', 'mode': 'close', 'feather': .1}))
        validate(self.edit({'type': 'flash', 'mode': 'add', 'pre_frames': 2, 'pre': [.2, .9]}))
        cases = [({'type': 'iris'}, 'needs a type'), ({'type': 'push', 'dir': 'diagonal'}, 'use one of'), ({'type': 'push', 'speed': 2}, 'unsupported fields: speed'),
                 ({'type': 'flash', 'd': .3}, 'not d'), ({'type': 'dissolve', 'd': 3}, 'must lie inside'), ({'type': 'zoom', 'center': [.5]}, r'\[x, y\]'),
                 ({'type': 'luma', 'softness': 2}, 'softness'), ({'type': 'wipe', 'count': 2.5}, 'count'), ({'type': 'fade', 'color': 'blue!'}, 'color')]
        for spec, error in cases:
            with self.assertRaisesRegex(ContractError, error, msg=spec):
                validate(self.edit(spec))
        first = self.edit({'type': 'dissolve'}); first['shots'][0]['transition'] = {'type': 'dissolve'}
        with self.assertRaisesRegex(ContractError, 'first shot'):
            validate(first)
        three = self.edit({'type': 'dissolve', 'd': .9}, frames=90); three['shots'][1]['f1'] = 40
        three['shots'].append({'f0': 40, 'f1': 90, 'clip': 'A', 'speed': 0, 'transition': {'type': 'dissolve', 'd': .5}})
        with self.assertRaisesRegex(ContractError, 'must lie inside|before the previous'):
            validate(three)

    @unittest.skipUnless(HAVE_FFMPEG and _chrome(), 'needs ffmpeg and Chrome')
    def test_render_composites_both_shots(self):
        from openkatana.render import render
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, colour in (('a', (230, 30, 30)), ('b', (30, 30, 230))):
                (root / name).mkdir(); Image.new('RGB', (64, 36), colour).save(root / name / '00000.png')
            edit = self.edit({'type': 'dissolve', 'd': .5}, cut=10, frames=20)
            (root / 'timeline.json').write_text(json.dumps(edit)); render(root / 'timeline.json', root / 'out')
            frame = lambda i: np.asarray(Image.open(root / 'out' / 'frames' / f'{i:05d}.png').convert('RGB'), dtype=float)[18, 32]
            self.assertLess(np.abs(frame(0) - (230, 30, 30)).max(), 2)
            self.assertLess(np.abs(frame(19) - (30, 30, 230)).max(), 2)
            mid = frame(10)   # window 3..18, p = 7.5/15
            self.assertLess(np.abs(mid - (130, 30, 130)).max(), 4, mid)
            trace = json.loads((root / 'out' / 'frame-trace.json').read_text())
            self.assertEqual([t.get('transition', {}).get('type') for t in trace].count('dissolve'), 15)


if __name__ == '__main__':
    unittest.main()
