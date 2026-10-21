import copy
import json
from pathlib import Path
import tempfile
import unittest
from openkatana import composition as c
from openkatana.contracts import ContractError
from openkatana.projects import fingerprint
from openkatana.render import digest


class CompositionContractTests(unittest.TestCase):
    def setUp(self):
        work=Path(__file__).resolve().parents[1]/'work';work.mkdir(exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=work);self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.doc=c.starter(640,360,12,6)

    def test_starter_single_frame_and_inputs(self):
        c.validate(c.starter(frames=1),self.root)
        hashes=c.inputs(self.doc,self.root)
        self.assertIn('@fonts/Inter[opsz,wght].ttf',hashes)
        self.assertTrue(any('licenses/' in k for k in hashes))

    def test_unknown_or_inapplicable_fields(self):
        edits=[lambda s:s.update(native_magic=True),lambda s:s['root'].update(text='ignored'),
               lambda s:s['root']['style'].update(animation='blink 1s'),lambda s:s['root'].update(dir='sideways')]
        for edit in edits:
            value=copy.deepcopy(self.doc);edit(value)
            with self.assertRaises(ContractError):c.validate(value,self.root)

    def test_dimensions_time_keys_and_duplicate_tracks(self):
        for bad in (True,float('nan'),0,8000):
            value=copy.deepcopy(self.doc);value['canvas']['w']=bad
            with self.assertRaises(ContractError):c.validate(value,self.root)
        self.doc['tracks'].append(copy.deepcopy(self.doc['tracks'][0]))
        with self.assertRaisesRegex(ContractError,'Duplicate'):c.validate(self.doc,self.root)

    def test_unknown_target_after_expansion(self):
        self.doc['root']['children']=[]
        with self.assertRaisesRegex(ContractError,'Unknown track'):c.validate(self.doc,self.root,expanded=True)

    def test_unsafe_styles_assets_and_invalid_node(self):
        for value in ('url(https://example.com/a)','red;opacity:0','red!important'):
            doc=copy.deepcopy(self.doc);doc['root']['style']['color']=value
            with self.assertRaises(ContractError):c.validate(doc,self.root)
        for path in ('../outside.png','https://example.com/a.png',str(self.root/'absolute.png')):
            with self.assertRaises(ContractError):c.asset(self.root,path,{'.png'})

    def test_responsive_rule_bounds_and_duplicate_ids(self):
        self.doc['root']['responsive']=[{'min_width':900,'max_width':300,'style':{}}]
        with self.assertRaises(ContractError):c.validate(self.doc,self.root)
        self.doc['root'].pop('responsive');self.doc['root']['children'][0]['id']='stage'
        with self.assertRaisesRegex(ContractError,'Duplicate node'):c.validate(self.doc,self.root)

    def test_bundled_complex_script_fonts_have_notices_and_coverage(self):
        from openkatana.fontcov import missing
        samples={'NotoSansArabic[wdth,wght].ttf':'مرحبا بالعالم','NotoSansDevanagari[wdth,wght].ttf':'नमस्ते दुनिया'}
        for name,text in samples.items():
            row=c.bundled_fonts.manifest()[name];p=c.bundled_fonts.FOLDER/name
            self.assertEqual(missing(p,text),[]);self.assertEqual(digest(p),row['sha256'])
            self.assertEqual(digest(c.bundled_fonts.FOLDER/row['license_file']),row['license_sha256'])
            self.assertIn('/47d54ca1ebb14fd864695f1d39dc734f39017c33/',row['source'])

    def test_save_conflicts_history_and_own_lock_cleanup(self):
        r=c.save_composition(self.root,'title.json',self.doc,None)
        self.assertFalse((self.root/'title.json.lock').exists())
        changed=copy.deepcopy(self.doc);changed['canvas']['frames']=10
        with self.assertRaisesRegex(ContractError,'changed'):c.save_composition(self.root,'title.json',changed,None)
        self.assertEqual(json.loads((self.root/'title.json').read_text()),self.doc)
        c.save_composition(self.root,'title.json',changed,r['revision'])
        self.assertEqual(json.loads((self.root/'.openkatana/composition-history'/(r['revision']+'.json')).read_text()),self.doc)
        lock=self.root/'title.json.lock';lock.write_text('another writer')
        with self.assertRaisesRegex(ContractError,'progress'):c.save_composition(self.root,'title.json',self.doc,fingerprint(changed))
        self.assertEqual(lock.read_text(),'another writer')

    def test_plugin_manifest_api_license_entry_and_traversal(self):
        (self.root/'p.js').write_text('// fixture');(self.root/'LICENSE.txt').write_text('MIT fixture')
        m={'api':1,'id':'demo','version':'1.0.0','entry':'p.js','files':['p.js','LICENSE.txt'],'license':'MIT'}
        path=self.root/'plugin.json';path.write_text(json.dumps(m));self.assertEqual(c.plugin_manifests(self.root,['plugin.json'])[0]['id'],'demo')
        for change in ({'api':99},{'id':'core'},{'files':['p.js']},{'entry':'missing.js'},{'files':['p.js','../LICENSE.txt']}):
            path.write_text(json.dumps({**m,**change}))
            with self.assertRaises(ContractError):c.plugin_manifests(self.root,['plugin.json'])

    def test_builtin_styles_inventory_matches_doc(self):
        guide=(Path(__file__).resolve().parents[1]/'docs/COMPOSITIONS.md').read_text(encoding='utf-8')
        self.assertTrue(all(k in guide for k in c.STYLES))


if __name__=='__main__':unittest.main()
