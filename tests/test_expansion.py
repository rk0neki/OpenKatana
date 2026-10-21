import copy
import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from openkatana.contracts import validate,ContractError
from openkatana import projects
from openkatana.audio import mix
from openkatana.vision import masks,faces,interpolate
from openkatana.render import write_json
from openkatana.workflows import build
from openkatana.comfy import validate_workflow

class ExpansionTests(unittest.TestCase):
    def setUp(self):
        scratch=Path(__file__).resolve().parents[1]/'work';scratch.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=scratch);self.root=Path(self.temp.name);self.addCleanup(self.temp.cleanup)
        frames=self.root/'frames';frames.mkdir()
        for i in range(2):
            im=Image.new('RGB',(64,48),'#00ff00');ImageDraw.Draw(im).rectangle((20+i*4,12,39+i*4,35),fill='#ff0000');im.save(frames/f'{i:05d}.png')
        self.edit={'canvas':{'w':64,'h':48,'fps':24,'frames':24},'clips':{'A':{'frames_dir':'frames','n':2,'fps':2,'w':64,'h':48}},'shots':[{'clip':'A','f0':0,'f1':24}]}
        write_json(self.root/'timeline.json',self.edit)
    def test_new_effects_reject_malformed_inputs(self):
        for fx in [{'mosaic':{'from':0}}, {'wipe':{'kind':'unknown'}},{'particles':{'shape':'bogus'}},{'particles':{'colors':[]}},
                   {'polygon3d':{'points':[[1,2],[2,3]]}}, {'morph':{'from':[[0,0],[1,1]],'to':[[0,0]]}},
                   {'vignette':{'r0':1,'r1':.5}},{'big':{'text':'TEST'}}]:
            with self.subTest(fx=fx),self.assertRaises(ContractError):validate({**self.edit,'post':fx},self.root)
    def test_new_effects_accept_explicit_graphics(self):
        e=copy.deepcopy(self.edit);e['shots'][0]['layers']=[{'type':'particles','shape':'confetti','seed':2},
            {'type':'morph','from':[[0,0],[1,0],[1,1]],'to':[[0,.2],[.8,.2],[.9,.9]],'fill':'#ffffff'},
            {'type':'polygon3d','points':[[0,0,0],[10,0,0],[0,10,0]]}];validate(e,self.root)
    def test_matte_alpha_and_frame_alignment(self):
        out=self.root/'masks';masks(self.root/'timeline.json','A',out)
        for i in range(2):
            a=np.array(Image.open(out/f'{i:05d}.png'))[:,:,3]
            self.assertEqual(a[0,0],0);self.assertEqual(a[20,30+i*4],255)
        self.edit['clips']['A']['mask_dir']='masks';validate(self.edit,self.root)
    def test_optical_flow_preserves_endpoints_and_duration(self):
        out=self.root/'flow';clip=interpolate(self.root/'timeline.json','A',out,3)
        self.assertEqual(clip['n']/clip['fps'],1)
        self.assertTrue(np.array_equal(np.array(Image.open(out/'00000.png')),np.array(Image.open(self.root/'frames/00000.png'))))
        self.assertTrue(np.array_equal(np.array(Image.open(out/'00003.png')),np.array(Image.open(self.root/'frames/00001.png'))))
    def test_face_detection_does_not_invent_faces(self):
        result=faces(self.root/'timeline.json','A',self.root/'faces');self.assertEqual(result['detected'],0)
        self.assertEqual(json.loads((self.root/'faces/faces.json').read_text()),[None,None])
    def test_nested_analysis_outputs_return_usable_project_paths(self):
        matte=masks(self.root/'timeline.json','A',self.root/'analysis/matte')
        tracked=faces(self.root/'timeline.json','A',self.root/'analysis/faces')
        flow=interpolate(self.root/'timeline.json','A',self.root/'analysis/flow',2)
        self.assertEqual(matte['clip_update']['mask_dir'],'analysis/matte')
        self.assertEqual(tracked['clip_update']['faces'],'analysis/faces/faces.json')
        self.assertEqual(flow['frames_dir'],'analysis/flow')
        self.edit['clips']['A'].update(matte['clip_update']);validate(self.edit,self.root)
        for operation in (masks,faces,interpolate):
            outside=self.root.parent/(self.root.name+'-outside')
            with self.assertRaisesRegex(ContractError,'inside'):operation(self.root/'timeline.json','A',outside)
            self.assertFalse(outside.exists())
    def test_audio_placement_and_clipping(self):
        import wave
        # Diagnostic constant-valued recording permits an exact onset/level check.
        with wave.open(str(self.root/'recording.wav'),'wb') as f:
            f.setparams((1,2,48000,0,'NONE','not compressed'));f.writeframes(np.full(48000,8192,dtype='<i2').tobytes())
        a={'mode':'mix','tracks':[{'src':'recording.wav','at':.25,'start':.1,'duration':.5,'volume':.5}]}
        receipt=mix(a,self.root,self.root/'mixed.wav',1)
        self.assertEqual(receipt['sample_frames'],48000);self.assertLess(receipt['peak'],.13)
        import subprocess
        raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(self.root/'mixed.wav'),'-f','f32le','-'])
        values=np.frombuffer(raw,dtype='<f4').reshape(-1,2)
        self.assertLess(np.max(np.abs(values[:11999])),1e-6);self.assertGreater(np.mean(values[13000:20000]),.08)
        self.assertLess(np.max(np.abs(values[36001:])),1e-6)
        a['tracks'][0]['volume']=16
        with self.assertRaisesRegex(ContractError,'clips'):mix(a,self.root,self.root/'clipped.wav',1)
    def test_workflow_builders_use_local_nodes(self):
        for kind in ('matte','segmentation','interpolation','generation','qwen-generation'):
            from openkatana.workflows import build_from_form
            graph=build_from_form(kind,{'model':'user-supplied.safetensors','encoder':'encoder.safetensors','vae':'vae.safetensors'});p=self.root/(kind+'.json');write_json(p,graph);validate_workflow(p)
            self.assertFalse(any('AutoDownload' in v['class_type'] for v in graph.values()))
    def test_unknown_workflow_parameters_rejected(self):
        with self.assertRaisesRegex(ValueError,'definitely_not_a_param'):build('matte',definitely_not_a_param=123)
    def test_qwen_requires_all_components_and_valid_geometry(self):
        with self.assertRaisesRegex(ValueError,'encoder'):build('qwen-generation',model='model')
        with self.assertRaisesRegex(ValueError,'multiples'):build('qwen-generation',model='m',encoder='e',vae='v',width=513)
    def test_preflight_v3_optional_reference_ports_and_model_choices(self):
        from unittest.mock import patch
        from openkatana.workflows import preflight
        graph={'1':{'class_type':'TextEncodeQwenImage21','inputs':{'prompt':'test'}}}
        info={'TextEncodeQwenImage21':{'input':{'required':{'prompt':['STRING',{}],'images':['COMFY_AUTOGROW_V3',{'template':{'min':0}}]}}}}
        with patch('openkatana.workflows.capabilities',return_value=info):self.assertTrue(preflight(graph,'local')['ready'])
        graph['1']['inputs']['model']='absent';info['TextEncodeQwenImage21']['input']['required']['model']=['COMBO',{'options':['installed']}]
        with patch('openkatana.workflows.capabilities',return_value=info):self.assertFalse(preflight(graph,'local')['ready'])
    def test_project_saves_conflict_and_preserve_history(self):
        p=self.root/'project';projects.create(p);asset=projects.import_asset(p,self.root/'frames/00000.png','own')
        edit=projects.plan(p,[asset['id']],seconds=1,width=64,height=48)['timeline']
        saved=projects.save(p,edit,None)
        with self.assertRaisesRegex(ContractError,'changed'):projects.save(p,edit,None)
        edit['shots'][0]['cam']['z']=1.2;projects.save(p,edit,saved['revision'])
        self.assertTrue((p/'history'/(saved['revision']+'.json')).is_file())

if __name__=='__main__':unittest.main()
