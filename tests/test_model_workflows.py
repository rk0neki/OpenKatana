import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from openkatana.agent_api import AgentAPI
from openkatana.contracts import ContractError
from openkatana.workflows import build, preflight
from openkatana.model_workflows import asset_ports
from openkatana.comfy import validate_workflow
from openkatana.workflow_schema import check_graph

COMPONENTS=dict(model='model.safetensors',encoder='encoder.safetensors',vae='vae.safetensors')


class ModelWorkflowTests(unittest.TestCase):
    def test_reference_images_connect_to_both_conditioning_and_correct_latent(self):
        graph=build('qwen-edit',**COMPONENTS,references=3)
        self.assertEqual(graph['7']['inputs']['latent_image'],['4',2])
        self.assertEqual(graph['4']['inputs']['vae'],['3',0])
        self.assertEqual(set(asset_ports(graph)),{'21.image','22.image','23.image'})
        self.assertIn('images.image_3',graph['4']['inputs'])

    def test_h3_reference_has_video_image_audio_and_no_incompatible_default_lora(self):
        g=build('h3-reference',**COMPONENTS,audio_vae='av.safetensors',images=2,videos=1,audios=1)
        self.assertEqual(set(asset_ports(g)),{'20.image','21.image','40.video','60.audio'})
        self.assertNotIn('5',g)
        self.assertEqual(g['8']['inputs']['model'],['1',0])
        self.assertEqual(g['7']['class_type'],'MiniMaxH3ReferenceToVideo')
        self.assertEqual(g['40']['inputs']['force_rate'],24)

    def test_all_builders_are_local_and_well_linked(self):
        cases={'qwen-edit':COMPONENTS,'h3-reference':dict(COMPONENTS,audio_vae='audio.safetensors'),
               'seedvr2-restore':dict(model='model.safetensors',vae='vae.safetensors'),
               'model-interpolation':dict(model='rife.safetensors'),'image-upscale':dict(model='up.pth')}
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'graph.json'
            for kind,parameters in cases.items():
                graph=build(kind,**parameters);p.write_text(json.dumps(graph))
                self.assertEqual(validate_workflow(p),graph)
                self.assertNotIn('Download',str(graph))

    def test_restore_preserves_audio_and_fps_and_interpolation_sets_output_rate(self):
        g=build('seedvr2-restore',model='m',vae='v')
        self.assertEqual(g['14']['inputs']['audio'],['2',1])
        self.assertEqual(g['14']['inputs']['fps'],['2',2])
        g=build('model-interpolation',model='rife',fps=30,multiplier=2)
        self.assertEqual(g['4']['inputs']['fps'],60)

    def test_bad_parameters_rejected(self):
        for p in ({'references':0},{'resolution':257},{'steps':True},{'seed':-1},{'width':512}):
            with self.assertRaises(ValueError):build('qwen-edit',**COMPONENTS,**p)
        with self.assertRaises(ValueError):build('seedvr2-restore',model='m',vae='v',scale=float('nan'))

    def test_expanded_ports_types_and_cycles_checked(self):
        info={'Ref':{'input':{'required':{'images':['COMFY_AUTOGROW_V3',{'template':{'names':['image_1'],'min':1,'input':{'required':{'image':['IMAGE']}}}}]}},'output':['IMAGE']},
              'Text':{'input':{},'output':['STRING']}}
        g={'1':{'class_type':'Text','inputs':{}},'2':{'class_type':'Ref','inputs':{'images.image_1':['1',0]}}}
        self.assertIn('cannot feed',str(check_graph(g,info,set())))
        g['2']['inputs']={'images.missing':['1',0]}
        self.assertIn('invalid reference port',str(check_graph(g,info,set())))
        g['2']['inputs']={'images.image_1':['2',0]}
        self.assertIn('cycle',str(check_graph(g,info,set())))

    def test_resume_collects_original_and_rejects_changed_assets(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);api=AgentAPI(root);api.create_project('Workflow','p')
            (root/'p/ref.png').write_bytes(b'fixture')
            args=dict(project_id='p',kind='qwen-edit',parameters=COMPONENTS,assets={'21.image':'ref.png'},request_id='stable')
            with patch.object(api,'submit_workflow',return_value={'directory':'job','receipt':{'job_id':'original'}}) as submit, patch.object(api,'collect_workflow',return_value={'state':'collected','job_id':'original'}):
                self.assertEqual(api.run_model_workflow(**args)['receipt']['job_id'],'original')
                self.assertEqual(api.run_model_workflow(**args)['receipt']['job_id'],'original')
                self.assertEqual(submit.call_args.args[2],'stable')
                (root/'p/ref.png').write_bytes(b'changed')
                with self.assertRaises(ContractError):api.run_model_workflow(**args)
            with self.assertRaises(ContractError):api.run_model_workflow(**dict(args,assets={}))


if __name__=='__main__':unittest.main()
