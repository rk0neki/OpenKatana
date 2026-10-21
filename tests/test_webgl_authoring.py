import copy
from contextlib import chdir
import json
from pathlib import Path
import tempfile
import unittest

from openkatana.agent_api import AgentAPI, TOOLS
from openkatana.contracts import ContractError
from openkatana.scene3d import validate, input_manifest, render_scene
from openkatana.webgl_authoring import create_kit, camera_schedule


class WebGLAuthoringTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        create_kit(self.root,'film',160,96,24,12)
        self.path = self.root/'film/scene.json'
        self.scene = json.loads(self.path.read_text())

    def test_kit_is_portable_valid_and_non_overwriting(self):
        self.assertEqual(validate(self.scene,self.path.parent),self.scene)
        inputs = input_manifest(self.scene,self.path.parent)
        self.assertEqual(set(inputs),{'scene.js','display/atlas.png','display/receipt.json'})
        with self.assertRaises(FileExistsError): create_kit(self.root,'film')
        with self.assertRaises(ContractError): create_kit(self.root,'../escape')

    def test_relative_workspace_returns_portable_paths_and_manifest(self):
        with chdir(self.root.parent):
            root = Path(self.root.name)
            result = create_kit(root, 'relative-film', 160, 96, 24, 12)
            self.assertEqual(result['scene'], 'relative-film/scene.json')
            self.assertEqual(result['module'], 'relative-film/scene.js')
            scene = json.loads((root/result['scene']).read_text())
            manifest = input_manifest(scene, root/'relative-film')
        self.assertEqual(set(manifest), {'scene.js','display/atlas.png','display/receipt.json'})

    def test_local_dependencies_and_modules_are_enforced(self):
        for module in ('../escape.js','https://example.com/s.js','missing.js','display/atlas.png'):
            s=copy.deepcopy(self.scene);s['authoring']['module']=module
            with self.assertRaises(ContractError):validate(s,self.path.parent)
        for files in ('scene.js',['missing.json'],['scene.js','scene.js'],[1]):
            s=copy.deepcopy(self.scene);s['authoring']['files']=files
            with self.assertRaises(ContractError):validate(s,self.path.parent)
        s=copy.deepcopy(self.scene);s['authoring']['unknown']=True
        with self.assertRaises(ContractError):validate(s,self.path.parent)

    def test_module_content_affects_input_hash(self):
        first=input_manifest(self.scene,self.path.parent)
        with (self.path.parent/'scene.js').open('a') as f:f.write('\n// revised scene\n')
        self.assertNotEqual(first,input_manifest(self.scene,self.path.parent))

    def test_script_requires_explicit_trust_before_browser_or_output(self):
        with self.assertRaisesRegex(ContractError,'trusted_script'):
            render_scene(self.path,self.root/'out')
        with self.assertRaisesRegex(ContractError,'boolean'):
            render_scene(self.path,self.root/'out',trusted_script='false')
        self.assertFalse((self.root/'out').exists())

    def test_chunk_ranges_and_preview_are_unambiguous(self):
        for kwargs in ({'start':-1},{'end':12},{'start':5,'end':4},{'start':1.0},{'samples':[0],'start':0}):
            with self.assertRaises(ContractError):render_scene(self.path,self.root/'out',trusted_script=True,**kwargs)
        self.assertFalse((self.root/'out').exists())

    def test_camera_path_native_frames_fov_and_cut(self):
        cache=camera_schedule(self.scene['camera_path'],self.scene['canvas'])
        self.assertEqual(cache['cuts'],[6]);self.assertEqual(len(cache['poses']),12)
        self.assertGreater(cache['poses'][5]['position'][0],0)
        self.assertLess(cache['poses'][6]['position'][0],0)
        # Horizontal sensor fitting: portrait scenes have larger vertical FOV.
        portrait=dict(self.scene['canvas'],width=96,height=160)
        self.assertGreater(camera_schedule(self.scene['camera_path'],portrait)['poses'][0]['fov'],cache['poses'][0]['fov'])

    def test_camera_schedule_can_resample_a_different_timebase(self):
        data=copy.deepcopy(self.scene['camera_path']);data['schedule_fps']=48
        for seg in data['segments']:seg['f0']*=2;seg['f1']*=2
        self.assertEqual(camera_schedule(data,self.scene['canvas'])['poses'],camera_schedule(self.scene['camera_path'],self.scene['canvas'])['poses'])

    def test_camera_conflicts_coverage_and_alignment_fail(self):
        for change in ('orthographic','track','coverage','fractional'):
            s=copy.deepcopy(self.scene)
            if change=='orthographic':s['camera']['type']='orthographic'
            if change=='track':s['tracks']=[{'target':'camera','property':'fov','keys':[[0,40]]}]
            if change=='coverage':s['camera_path']['segments'][-1]['f1']=10
            if change=='fractional':
                s['camera_path']['segments'][0]['f1']=5.5;s['camera_path']['segments'][1]['f0']=5.5
            with self.assertRaises(ContractError):validate(s,self.path.parent)

    def test_api_discovery_and_creation(self):
        api=AgentAPI(self.root);api.create_project('Film','film-project')
        result=api.call('create_webgl_kit',{'project_id':'film-project','frames':12,'width':160,'height':96})
        self.assertTrue(api.check_scene3d('film-project',result['scene'])['valid'])
        self.assertIn('assemble_render_clips',TOOLS)
        with self.assertRaises(ContractError):api.call('create_webgl_kit',{'project_id':'film-project','unexpected':True})


if __name__=='__main__':unittest.main()
