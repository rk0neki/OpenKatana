import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from xml.etree import ElementTree

from openkatana.contracts import ContractError
from openkatana.text_shape import shape_text, export_text

FONTS = Path(__file__).resolve().parents[1]/'openkatana/fonts'


@unittest.skipUnless(importlib.util.find_spec('uharfbuzz'), 'optional text extra')
class TextShapeTests(unittest.TestCase):
    def test_arabic_forms_clusters_and_svg(self):
        font=FONTS/'NotoSansArabic[wdth,wght].ttf'
        word=shape_text(font,'سلام',language='ar')
        separate=[shape_text(font,c,language='ar')['glyphs'][0]['id'] for c in 'سلام']
        self.assertEqual(word['direction'],'rtl')
        self.assertNotEqual([g['id'] for g in word['glyphs']],separate)
        self.assertEqual(word['missing_clusters'],[])
        self.assertTrue(all(0 <= g['cluster'] < 4 for g in word['glyphs']))
        self.assertTrue(any(g['path'] for g in word['glyphs']))
        ElementTree.fromstring(word['svg'])
        self.assertEqual(word,shape_text(font,'سلام',language='ar'))

    def test_indic_combining_clusters_and_vertical_advances(self):
        font=FONTS/'NotoSansDevanagari[wdth,wght].ttf'
        r=shape_text(font,'क्षि',language='hi')
        self.assertEqual(r['missing_clusters'],[])
        self.assertLess(len({g['cluster'] for g in r['glyphs']}),len('क्षि'))
        v=shape_text(font,'कख',direction='ttb',language='hi')
        self.assertEqual(v['advance'][0],0)
        self.assertGreater(v['advance'][1],0)

    def test_variations_affect_outlines_and_advance(self):
        font=FONTS/'NotoSansArabic[wdth,wght].ttf'
        a=shape_text(font,'سلام',variations={'wdth':62.5,'wght':100})
        b=shape_text(font,'سلام',variations={'wdth':100,'wght':900})
        self.assertNotEqual(a['advance'],b['advance'])
        self.assertNotEqual(a['glyphs'][0]['path'],b['glyphs'][0]['path'])
        curved=shape_text(font,'سلام',radius=100)
        self.assertNotEqual(curved['glyphs'][0]['origin'],b['glyphs'][0]['origin'])
        self.assertNotEqual(curved['glyphs'][0]['angle'],0)

    def test_invalid_requests_fail_and_missing_glyphs_are_visible(self):
        font=FONTS/'anton_Anton-Regular.ttf'
        for kw in ({'size':True},{'size':float('nan')},{'radius':0},{'direction':'invalid'},
                   {'variations':{'wght':99}}, {'features':{'liga':'yes'}}, {'script':'wrong'}):
            with self.assertRaises(ContractError):shape_text(font,'test',**kw)
        for text in ('','a\nb','x'*4097):
            with self.assertRaises(ContractError):shape_text(font,text)
        self.assertTrue(shape_text(font,'سلام')['missing_clusters'])

    def test_export_and_agent_dont_replace_outputs(self):
        from openkatana.agent_api import AgentAPI
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);font=FONTS/'anton_Anton-Regular.ttf'
            r=export_text(font,'OPEN',root/'export')
            self.assertTrue(Path(r['svg_file']).is_file())
            self.assertEqual(json.loads((root/'export/glyphs.json').read_text())['text'],'OPEN')
            with self.assertRaises(FileExistsError):export_text(font,'OPEN',root/'export')
            api=AgentAPI(root);api.create_project('Glyphs','glyphs')
            r=api.shape_text('glyphs',str(font),'OPEN')
            self.assertTrue(Path(r['svg_file']).resolve().is_relative_to((root/'glyphs').resolve()))
            with self.assertRaises(ContractError):api.shape_text('missing',str(font),'OPEN')
