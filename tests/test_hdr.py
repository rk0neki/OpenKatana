"""Numeric HDR integration tests: real FFmpeg transforms, no model/service calls."""
import copy
from pathlib import Path
import shutil
import tempfile
import unittest

import numpy as np
from PIL import Image

from openkatana import hdr
from openkatana.contracts import ContractError
from openkatana.render import probe


@unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg required')
class HDRTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.c = dict(width=512, height=32, fps=4, frames=4)
        # Continuous 0..1000-nit ramp with more dark samples, exercising PQ code precision.
        # A uniform-nit ramp wastes samples where PQ code steps are coarse.
        cls.pixels = np.broadcast_to((np.linspace(0, 1, 512, dtype=np.float32)**3*10)[None, :, None], (32, 512, 3)).copy()
        raw = cls.root/'fixture.raw'
        raw.write_bytes(cls.pixels.transpose(2, 0, 1)[[1, 2, 0]].tobytes()*4)
        for transfer in ('pq', 'hlg'):
            hdr.encode_linear(raw, cls.c, cls.root/f'{transfer}.mkv', transfer, True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def doc(self, transfer='pq'):
        return dict(schema='openkatana.hdr/1', canvas=self.c, output=dict(transfer=transfer, peak_nits=1000),
                    clips=[dict(source=f'{transfer}.mkv', start=0, frames=4)])

    def test_pq_and_hlg_roundtrip_preserve_highlights_and_more_than_8bit(self):
        for transfer in ('pq', 'hlg'):
            with self.subTest(transfer=transfer):
                path = self.root/f'{transfer}.mkv'
                with hdr.Decoder(path, hdr.source_profile(path), self.c, frames=1) as d:
                    actual = d.read()
                self.assertLess(float(np.abs(actual-self.pixels).max()), .015)
                self.assertGreater(len(np.unique(actual[0, :, 0])), 500)
                self.assertGreater(float(actual.max()), 9.98)

    def test_render_blend_exposure_and_tags(self):
        doc = self.doc()
        doc['clips'][0]['exposure'] = -1
        doc['clips'].append(dict(source='pq.mkv', start=0, frames=4, opacity=.5))
        out = self.root/'blend'
        result = hdr.render(doc, self.root, out)
        video = next(v for v in probe(out/'video.mp4')['streams'] if v['codec_type']=='video')
        self.assertEqual(video['pix_fmt'], 'yuv420p10le')
        self.assertEqual(video['color_transfer'], 'smpte2084')
        self.assertEqual(video['color_primaries'], 'bt2020')
        self.assertEqual(int(video['nb_read_frames']), 4)
        with hdr.Decoder(out/'video.mp4', hdr.source_profile(out/'video.mp4'), self.c, frames=1) as d:
            self.assertGreater(len(np.unique(d.read()[16,:,0])), 256)
        with hdr.Decoder(out/'master.mkv', hdr.source_profile(out/'master.mkv'), self.c, frames=1) as d:
            self.assertLess(float(np.abs(d.read()-self.pixels*.75).max()), .02)
        self.assertLess(abs(result['max_rgb_nits']-750), 2)
        self.assertTrue(result['review_required'])

    def test_srgb_overlay_is_linear_and_declares_white_luminance(self):
        png = self.root/'overlay.png'
        Image.new('RGBA', (512, 32), (255, 255, 255, 128)).save(png)
        rgb, alpha = hdr.overlay_pixels(png, self.c, 203)
        self.assertTrue(np.allclose(rgb, 2.03, atol=1e-5))
        self.assertAlmostEqual(float(alpha[0,0,0]), 128/255, places=6)

    def test_agent_import_retains_hdr_and_export_muxes_audio(self):
        from openkatana.agent_api import AgentAPI
        import wave
        api=AgentAPI(self.root/'projects');api.create_project('HDR fixture','hdr')
        imported=api.import_hdr_media('hdr',str(self.root/'pq.mkv'),fps=4,duration=1)
        original=self.root/'projects/hdr'/imported['original']
        self.assertEqual(original.read_bytes(),(self.root/'pq.mkv').read_bytes())
        self.assertEqual(imported['asset']['clip']['n'],4)
        wav=self.root/'projects/hdr/tone.wav'
        with wave.open(str(wav),'wb') as f:
            f.setnchannels(1);f.setsampwidth(2);f.setframerate(8000);f.writeframes(b'\0\0'*8000)
        doc=imported['hdr_document'];doc['audio']='tone.wav'
        result=api.render_hdr('hdr',doc)
        streams=probe(Path(result['video']))['streams']
        self.assertEqual([s['codec_type'] for s in streams],['video','audio'])
        self.assertEqual(next(s for s in streams if s['codec_type']=='video')['color_transfer'],'smpte2084')

    def test_animated_overlay_sequence_and_hlg_export(self):
        folder=self.root/'animated';folder.mkdir()
        for i in range(4):Image.new('RGBA',(512,32),(255,255,255,255 if i%2 else 0)).save(folder/f'{i:05d}.png')
        doc=self.doc('hlg');doc['overlays']=[dict(source='animated',start=0,frames=4,white_nits=203)]
        result=hdr.render(doc,self.root,self.root/'overlay-result')
        master=Path(result['master'])
        with hdr.Decoder(master,hdr.source_profile(master),self.c,frames=4) as d:
            first=d.read();second=d.read()
        self.assertGreater(float(first.max()),9.98)
        self.assertTrue(np.allclose(second,2.03,atol=.01))
        self.assertEqual(probe(Path(result['video']))['streams'][0]['color_transfer'],'arib-std-b67')
        self.assertEqual(len(result['overlays'][0]['files']),4)

    def test_strict_contract(self):
        for change in ({'unknown': True}, {'output': {'transfer':'sdr','peak_nits':1000}}, {'canvas':dict(self.c,width=True)}):
            doc = copy.deepcopy(self.doc());doc.update(change)
            with self.assertRaises(ContractError):hdr.validate(doc, self.root)
        doc = self.doc();doc['clips'][0]['source']='../outside.mp4'
        with self.assertRaises(ContractError):hdr.validate(doc, self.root)

    def test_short_source_fails_instead_of_repeating_last_frame(self):
        doc = self.doc();doc['canvas']=dict(self.c,frames=8);doc['clips'][0]['frames']=8
        with self.assertRaisesRegex(ContractError,'ended'):
            hdr.render(doc,self.root,self.root/'short')
        self.assertFalse((self.root/'short/manifest.json').exists())


if __name__ == '__main__':unittest.main()
