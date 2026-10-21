import copy
import json
from pathlib import Path
import tempfile
import unittest

from openkatana.agent_api import AgentAPI
from openkatana.contracts import ContractError
from openkatana.scene3d import asset, inspect_model, import_model, starter, validate, WEB
from openkatana.render import digest


class SceneTests(unittest.TestCase):
    def setUp(self):
        parent=Path(__file__).resolve().parents[1]/'work';parent.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=parent);self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.scene=starter(frames=12,fps=12)

    def test_all_starters_validate_without_models_or_services(self):
        for kind in ('product','morph','physics'):validate(starter(kind),self.root)

    def test_unknown_and_inapplicable_fields_fail(self):
        for change in (lambda s:s.update(magic=True),lambda s:s['objects'][1]['geometry'].update(height=3),
                       lambda s:s['lights'][0].update(decay=3),lambda s:s['objects'][0].update(animation={'clip':0})):
            s=copy.deepcopy(self.scene);change(s)
            with self.assertRaises(ContractError):validate(s,self.root)

    def test_nonfinite_dimensions_and_time_are_rejected(self):
        for v in (float('nan'),float('inf'),True,-1):
            s=copy.deepcopy(self.scene);s['camera']['fov']=v
            with self.assertRaises(ContractError):validate(s,self.root)
        self.scene['tracks'][0]['keys'][1][0]=0
        with self.assertRaisesRegex(ContractError,'increase'):validate(self.scene,self.root)

    def test_parent_cycles_and_unknown_targets(self):
        self.scene['objects']=[{'id':'a','type':'group','parent':'b'},{'id':'b','type':'group','parent':'a'}]
        with self.assertRaisesRegex(ContractError,'acyclic'):validate(self.scene,self.root)
        s=starter();s['tracks'][0]['target']='missing'
        with self.assertRaises(ContractError):validate(s,self.root)

    def test_duplicate_tracks_and_wrong_property_types(self):
        s=starter();s['tracks'].append(copy.deepcopy(s['tracks'][0]))
        with self.assertRaises(ContractError):validate(s,self.root)
        s=starter();s['tracks'][0]['keys'][0][1]='wrong'
        with self.assertRaises(ContractError):validate(s,self.root)

    def test_physics_rejects_conflicting_transform_keys(self):
        s=starter('physics');s['tracks']=[{'target':'hero','property':'position','keys':[[0,[0,1,0]]]}]
        with self.assertRaisesRegex(ContractError,'Physics owns'):validate(s,self.root)

    def test_model_external_dependencies_are_checked_and_copied(self):
        (self.root/'mesh.bin').write_bytes(bytes(12))
        p=self.root/'model.gltf';p.write_text(json.dumps({'asset':{'version':'2.0'},'buffers':[{'uri':'mesh.bin','byteLength':12}]}))
        info=inspect_model(p);self.assertIn('mesh.bin',info['dependencies'])
        imported=import_model(p,self.root/'copied');self.assertEqual(digest(self.root/'copied/mesh.bin'),digest(self.root/'mesh.bin'))
        with self.assertRaises(FileExistsError):import_model(p,self.root/'copied')

    def test_model_remote_paths_and_unsupported_extensions_rejected(self):
        p=self.root/'model.gltf'
        for uri in ('https://example.com/a.bin','../escape.bin','%2e%2e/escape.bin','C:/a.bin','//example.com/a.bin'):
            p.write_text(json.dumps({'asset':{'version':'2.0'},'buffers':[{'uri':uri}]}))
            with self.assertRaises(ContractError):inspect_model(p)
        p.write_text(json.dumps({'asset':{'version':'2.0'},'extensionsUsed':['KHR_draco_mesh_compression']}))
        with self.assertRaisesRegex(ContractError,'extensions'):inspect_model(p)

    def test_missing_and_malformed_models_fail(self):
        p=self.root/'broken.glb';p.write_bytes(b'no')
        with self.assertRaises(ContractError):inspect_model(p)
        with self.assertRaises(ContractError):asset(self.root,'missing.glb')

    def test_vendor_files_match_pinned_license_manifests(self):
        manifest=json.loads((WEB/'vendor3d/manifest.json').read_text())
        self.assertEqual(manifest['three']['version'],'0.180.0')
        for name,record in manifest.items():
            self.assertEqual(record['license'],'MIT')
            self.assertIn('LICENSE',record['files'])
            for rel,sha in record['files'].items():self.assertEqual(digest(WEB/'vendor3d'/name/rel),sha)

    def test_agent_scene_creation_validation_and_boundaries(self):
        api=AgentAPI(self.root);api.create_project('3D','demo')
        result=api.create_scene3d('demo');self.assertTrue(api.check_scene3d('demo',result['scene'])['valid'])
        with self.assertRaises(FileExistsError):api.create_scene3d('demo')
        with self.assertRaises(ContractError):api.create_scene3d('demo','../escape')

    def test_blender_script_needs_explicit_trust_before_execution(self):
        from openkatana.blender_bridge import render_blender
        p=self.root/'author.py';p.write_text('raise RuntimeError("must not execute")')
        with self.assertRaisesRegex(ContractError,'trusted_script'):render_blender(p,self.root/'out')
        with self.assertRaisesRegex(ContractError,'boolean'):render_blender(p,self.root/'out',trusted_script='false')
        self.assertFalse((self.root/'out').exists())


if __name__=='__main__':unittest.main()
