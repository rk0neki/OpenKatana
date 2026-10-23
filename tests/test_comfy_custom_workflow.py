"""Model-independent local extension stays explicit and keeps paid/download boundaries."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock,patch
from openkatana import comfy
from openkatana.workflows import preflight


class CustomWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.path=self.root/'workflow.json'
        self.graph={'1':{'class_type':'OtherLocalModel','inputs':{'model':'installed.safetensors'}}}
        self.path.write_text(json.dumps(self.graph),encoding='utf-8')

    def test_extension_is_local_explicit_and_not_global(self):
        with self.assertRaisesRegex(ValueError,'allowlist'):comfy.validate_workflow(self.path)
        self.assertEqual(comfy.validate_workflow(self.path,reviewed_local_nodes=['OtherLocalModel']),self.graph)
        with self.assertRaisesRegex(ValueError,'allowlist'):comfy.validate_workflow(self.path)
        with self.assertRaisesRegex(ValueError,'only to local'):
            comfy.validate_workflow(self.path,'cloud',['OtherLocalModel'])
        for bad in ('*',[''],['DownloadAnyModel'],[False]):
            with self.assertRaises(ValueError):comfy.validate_workflow(self.path,reviewed_local_nodes=bad)

    def test_preflight_rejects_paid_missing_and_optional_missing_models(self):
        with patch('openkatana.workflows.capabilities',return_value={}):
            self.assertFalse(preflight(self.graph,'local',['OtherLocalModel'])['ready'])
        spec={'OtherLocalModel':{'api_node':True,'input':{}}}
        with patch('openkatana.workflows.capabilities',return_value=spec):
            self.assertIn('hosted API',preflight(self.graph,'local',['OtherLocalModel'])['errors'][0])
        spec['OtherLocalModel']={'input':{'optional':{'model':[['other.safetensors']]}}}
        with patch('openkatana.workflows.capabilities',return_value=spec):
            self.assertIn('not installed',preflight(self.graph,'local',['OtherLocalModel'])['errors'][0])

    def test_receipt_carries_extension_through_sdk(self):
        client=MagicMock();client.submit.return_value=SimpleNamespace(id='local-job')
        with patch('openkatana.workflows.preflight',return_value={'ready':True}) as check, \
             patch('openkatana.comfy.require_reachable'),patch('openkatana.comfy.client_at') as ctx:
            ctx.return_value.__enter__.return_value=client
            result=comfy.submit(self.path,self.root/'job','http://127.0.0.1:8189',
                native_endpoint='http://127.0.0.1:8000',reviewed_local_nodes=['OtherLocalModel'])
            self.assertEqual(result['reviewed_local_nodes'],['OtherLocalModel'])
            self.assertEqual(result['execution'],'local');self.assertFalse(result['paid_authorized'])
            check.assert_called_once_with(self.graph,'http://127.0.0.1:8000',['OtherLocalModel'])
            client.submit.assert_called_once()

    def test_paid_node_never_reaches_sdk_even_with_review(self):
        info={'OtherLocalModel':{'api_node':True,'input':{}}}
        with patch('openkatana.workflows.capabilities',return_value=info), \
             patch('openkatana.comfy.require_reachable'),patch('openkatana.comfy.client_at') as ctx:
            with self.assertRaisesRegex(ValueError,'hosted API'):
                comfy.submit(self.path,self.root/'job','http://127.0.0.1:8189',
                    native_endpoint='http://127.0.0.1:8000',reviewed_local_nodes=['OtherLocalModel'])
            ctx.assert_not_called();self.assertFalse((self.root/'job').exists())

    def test_request_identity_includes_review(self):
        from openkatana.agent_api import AgentAPI
        from openkatana.contracts import ContractError
        from openkatana.render import write_json
        api=AgentAPI(self.root);api.create_project('Test','test')
        (self.root/'test/workflow.json').write_text(json.dumps(self.graph),encoding='utf-8')
        def submitted(workflow,directory,*args,**kwargs):
            directory.mkdir();receipt={'state':'submitted','job_id':'existing'}
            write_json(directory/'job.json',receipt);return receipt
        args=dict(project_id='test',workflow='workflow.json',request_id='stable',reviewed_local_nodes=['OtherLocalModel'])
        with patch('openkatana.comfy.submit',side_effect=submitted) as submit:
            api.submit_workflow(**args);api.submit_workflow(**args)
            with self.assertRaisesRegex(ContractError,'different workflow'):
                api.submit_workflow(**(args|{'reviewed_local_nodes':['OtherLocalModel','Another']}))
            submit.assert_called_once()


# Input contract served at /object_info by ComfyUI 0.42.0 for the core ReferenceMultiLatent node
# (comfy_extras/nodes_edit_model.py). Its autogrow template lists the image port as optional.
REFERENCE_MULTI_LATENT={'input':{
    'required':{'positive':['CONDITIONING',{}],'resolution':['COMFY_DYNAMICCOMBO_V3',{'options':[
        {'key':'keep resolution','inputs':{'required':{}}},
        {'key':'resize','inputs':{'required':{'megapixels':['FLOAT',{'default':1.0,'min':0.01,'max':16.0,'step':0.01}]}}}]}]},
    'optional':{'negative':['CONDITIONING',{}],'vae':['VAE',{}],
        'images':['COMFY_AUTOGROW_V3',{'template':{'input':{'required':{},'optional':{'image':['IMAGE',{}]}},
                                                   'prefix':'image','min':1,'max':100}}]}},
    'output':['CONDITIONING','CONDITIONING','LATENT']}


class OptionalTemplatePortTests(unittest.TestCase):
    """Multi-reference edits connect images.imageN ports whose template input is optional."""
    def setUp(self):
        self.info={'ReferenceMultiLatent':REFERENCE_MULTI_LATENT,'Conditioning':{'input':{},'output':['CONDITIONING']},
                   'VAELoader':{'input':{'required':{'vae_name':[['flux2-vae.safetensors']]}},'output':['VAE']},
                   'LoadImage':{'input':{'required':{'image':[['first.png','second.png'],{'image_upload':True}]}},'output':['IMAGE','MASK']}}
        self.node={'positive':['10',0],'vae':['12',0],'resolution':'keep resolution','images.image0':['20',0],'images.image1':['21',0]}
        self.graph={'10':{'class_type':'Conditioning','inputs':{}},
                    '12':{'class_type':'VAELoader','inputs':{'vae_name':'flux2-vae.safetensors'}},
                    '20':{'class_type':'LoadImage','inputs':{'image':'first.png'}},
                    '21':{'class_type':'LoadImage','inputs':{'image':'second.png'}},
                    '11':{'class_type':'ReferenceMultiLatent','inputs':self.node}}

    def errors(self):
        with patch('openkatana.workflows.capabilities',return_value=self.info):
            return preflight(self.graph,'local',['ReferenceMultiLatent'])['errors']

    def test_reference_ports_use_the_optional_template_input(self):
        self.assertEqual(self.errors(),[])
        self.node['images.image1']=['21',1]
        self.assertEqual(self.errors(),['11.images.image1: MASK output cannot feed IMAGE'])
        del self.node['images.image1'];self.node['images.image100']=['21',0]
        self.assertIn('11.images.image100: invalid reference port',self.errors())

    def test_optional_template_still_needs_one_reference(self):
        for port in ('images.image0','images.image1'):del self.node[port]
        self.assertEqual(self.errors(),['11.images: too few references'])


if __name__=='__main__':unittest.main()
