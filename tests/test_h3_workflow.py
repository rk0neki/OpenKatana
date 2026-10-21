"""H3 adapter boundary tests; no downloads, paid jobs or GPU execution."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from openkatana.comfy import validate_workflow
from openkatana.workflows import build, preflight


COMPONENTS=dict(model='h3.safetensors',encoder='encoder.safetensors',vae='video.safetensors',
                audio_vae='audio.safetensors',lora='turbo.safetensors')


class H3WorkflowTests(unittest.TestCase):
    def test_modes_have_valid_links_and_explicit_asset_ports(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'workflow.json'
            for mode,ports in [('t2v',set()),('i2v',{'first_frame'}),('first-last',{'first_frame','last_frame'})]:
                for sage in (False,True):
                    graph=build('h3-generation',**COMPONENTS,input_mode=mode,sage_attention=sage)
                    path.write_text(json.dumps(graph),encoding='utf-8')
                    validate_workflow(path)
                    self.assertEqual(set(graph['7']['inputs']) & {'first_frame','last_frame'},ports)
                    self.assertEqual(graph['8']['inputs']['model'],graph['10']['inputs']['model'])
                    for port in ports:
                        loader=graph[graph['7']['inputs'][port][0]]
                        self.assertEqual(loader['class_type'],'LoadImage')
                    self.assertEqual(graph['15']['inputs']['fps'],24)
                    self.assertEqual(graph['15']['inputs']['audio'],['14',0])

    def test_invalid_geometry_components_and_controls_fail_before_submission(self):
        for override in ({'width':513},{'height':True},{'length':120},{'length':379},
                         {'steps':0},{'seed':-1},{'sage_attention':'true'},
                         {'input_mode':'reference'},{'audio_vae':''},{'lora':None}):
            with self.subTest(override=override),self.assertRaises(ValueError):
                build('h3-generation',**(COMPONENTS|override))

    def test_missing_weights_and_hosted_nodes_block_preflight(self):
        graph={'1':{'class_type':'LoraLoaderModelOnly','inputs':{
            'model':['2',0],'lora_name':'missing.safetensors','strength_model':1.}}}
        info={'LoraLoaderModelOnly':{'input':{'required':{'lora_name':[['installed.safetensors']]}}}}
        with patch('openkatana.workflows.capabilities',return_value=info):
            self.assertIn('not installed',preflight(graph,'local')['errors'][0])
        info['LoraLoaderModelOnly']['api_node']=True
        graph['1']['inputs']['lora_name']='installed.safetensors'
        with patch('openkatana.workflows.capabilities',return_value=info):
            self.assertIn('hosted API',preflight(graph,'local')['errors'][0])

    def test_paid_h3_node_remains_rejected_locally(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'workflow.json'
            path.write_text(json.dumps({'1':{'class_type':'ComfyCloudMiniMaxH3TextToVideoNode','inputs':{}}}))
            with self.assertRaisesRegex(ValueError,'allowlist'):validate_workflow(path)

    def test_mcp_exposes_h3_builder(self):
        from openkatana.agent_api import AgentAPI
        with tempfile.TemporaryDirectory() as tmp:
            api=AgentAPI(Path(tmp));api.create_project('H3 test','h3')
            result=api.call('build_workflow',{'project_id':'h3','kind':'h3-generation','parameters':COMPONENTS})
            self.assertTrue((Path(tmp)/'h3'/result['workflow']).exists())


if __name__=='__main__':unittest.main()
