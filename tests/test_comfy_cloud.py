"""Paid routing tests use fake SDK jobs: no network, credentials or spending."""
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, create_autospec, patch
from openkatana import comfy, projects
from openkatana.agent_api import AgentAPI
from openkatana.comfy_assets import import_outputs
from openkatana.render import digest, write_json


class CloudTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.workflow=self.root/'workflow.json'
        write_json(self.workflow,{'1':{'class_type':'ExamplePartnerNode','inputs':{'prompt':'test'}}})
        self.key=patch.dict(os.environ,{'COMFY_API_KEY':'test-only-not-a-real-key'})
        self.key.start();self.addCleanup(self.key.stop)

    def test_cloud_requires_explicit_mode_permission_endpoint_and_key(self):
        cases=[('https://cloud.comfy.org','local',True),
               ('https://cloud.comfy.org','cloud',False),
               ('https://cloud.comfy.org.evil.example','cloud',True),
               ('http://cloud.comfy.org','cloud',True),
               ('http://127.0.0.1:8189','cloud',True)]
        with patch('openkatana.comfy.client_at') as client:
            for endpoint,execution,allow in cases:
                with self.assertRaises(ValueError):
                    comfy.submit(self.workflow,self.root/'job',endpoint,execution=execution,allow_paid=allow)
            with patch.dict(os.environ,{'COMFY_API_KEY':''}):
                with self.assertRaisesRegex(ValueError,'COMFY_API_KEY'):
                    comfy.submit(self.workflow,self.root/'job','https://cloud.comfy.org',execution='cloud',allow_paid=True)
            client.assert_not_called()
        self.assertFalse((self.root/'job').exists())

    def test_guide_and_mcp_schema_expose_both_routes(self):
        import asyncio
        from openkatana.mcp_server import create_server
        api=AgentAPI(self.root)
        self.assertIn('Comfy Cloud',api.read_guide('comfy-models')['markdown'])
        catalog=asyncio.run(create_server(self.root).list_tools())
        tool=next(t for t in catalog if t.name=='submit_workflow')
        self.assertEqual(tool.inputSchema['properties']['execution']['enum'],['local','cloud'])
        self.assertFalse(tool.inputSchema['properties']['allow_paid']['default'])
        self.assertTrue(tool.annotations.openWorldHint)

    def test_local_allowlist_is_not_relaxed_by_paid_flag(self):
        with self.assertRaisesRegex(ValueError,'allowlist'):
            comfy.validate_workflow(self.workflow)
        self.assertEqual(comfy.validate_workflow(self.workflow,'cloud')['1']['class_type'],'ExamplePartnerNode')

    def test_credentials_in_workflow_rejected(self):
        write_json(self.workflow,{'1':{'class_type':'ExamplePartnerNode','inputs':{'api_key':'do-not-save'}}})
        with self.assertRaisesRegex(ValueError,'Credentials'):
            comfy.validate_workflow(self.workflow,'cloud')

    def test_sdk_receipt_collect_and_no_credential_persistence(self):
        output=MagicMock();output.name='result.png';output.type='image'
        output.to_file.side_effect=lambda path:Path(path).write_bytes(b'result')
        client=MagicMock();client.submit.return_value.id='paid-job-1'
        client.jobs.get.return_value=SimpleNamespace(status='succeeded',outputs=[output])
        with patch('openkatana.comfy.client_at') as context:
            context.return_value.__enter__.return_value=client
            out=self.root/'job'
            receipt=comfy.submit(self.workflow,out,'https://cloud.comfy.org',execution='cloud',allow_paid=True)
            self.assertEqual(receipt['execution'],'cloud')
            self.assertTrue(receipt['paid_authorized'])
            collected=comfy.collect(out)
            self.assertEqual(collected['state'],'collected')
            comfy.collect(out)
            client.submit.assert_called_once()
            client.jobs.get.assert_called_once_with('paid-job-1')
            self.assertNotIn('test-only-not-a-real-key',(out/'job.json').read_text())
            (out/collected['outputs'][0]['file']).write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'changed'):comfy.collect(out)

    def test_client_routes_explicitly_and_restores_environment(self):
        with patch.dict(os.environ,{'COMFY_BASE_URL':'https://previous.example'}):
            with patch('comfy_sdk.Comfy') as factory:
                with comfy.client_at('http://127.0.0.1:8189'):
                    self.assertEqual(os.environ['COMFY_BASE_URL'],'http://127.0.0.1:8189')
                self.assertNotIn('api_key',factory.call_args.kwargs)
                with self.assertRaises(RuntimeError):
                    with comfy.client_at('https://cloud.comfy.org','cloud'):
                        self.assertEqual(factory.call_args.kwargs['api_key'],'test-only-not-a-real-key')
                        raise RuntimeError('test')
                self.assertEqual(os.environ['COMFY_BASE_URL'],'https://previous.example')

    def test_unknown_cloud_submission_is_never_repeated(self):
        api=AgentAPI(self.root);api.create_project('Test','project')
        project=self.root/'project';write_json(project/'workflow.json',json.loads(self.workflow.read_text()))
        client=MagicMock();client.submit.side_effect=TimeoutError('unknown')
        args=dict(project_id='project',workflow='workflow.json',request_id='stable',
                  execution='cloud',allow_paid=True,endpoint='https://cloud.comfy.org')
        with patch('openkatana.comfy.client_at') as context:
            context.return_value.__enter__.return_value=client
            with self.assertRaises(TimeoutError):api.submit_workflow(**args)
            self.assertEqual(api.submit_workflow(**args)['receipt']['state'],'submission_unknown')
            client.submit.assert_called_once()
            with self.assertRaisesRegex(Exception,'different'):
                api.submit_workflow(**{**args,'execution':'local','endpoint':'http://127.0.0.1:8189'})

    def sdk_client(self):
        """Fake client whose calls must match the installed comfy_sdk.Comfy signatures."""
        from comfy_sdk import Comfy
        client=create_autospec(Comfy,instance=True)
        client.workflows=MagicMock();client.assets=MagicMock()
        client.submit.return_value.id='job-1'
        return client

    def assert_key_absent(self,folder):
        files=[p for p in folder.rglob('*') if p.is_file()]
        self.assertTrue(files)
        for path in files:
            self.assertNotIn(b'test-only-not-a-real-key',path.read_bytes(),path.relative_to(folder).as_posix())

    def test_cloud_submission_sends_key_for_partner_nodes(self):
        # Without the key, Cloud partner nodes fail "Unauthorized: Please login first to use this node".
        source=self.root/'source.png';source.write_bytes(b'source')
        client=self.sdk_client()
        # The SDK strips the key it sends as the bearer token; the partner copy must match it.
        with patch.dict(os.environ,{'COMFY_API_KEY':' test-only-not-a-real-key\n'}),patch('openkatana.comfy.client_at') as context:
            context.return_value.__enter__.return_value=client
            receipt=comfy.submit(self.workflow,self.root/'job','https://cloud.comfy.org',[f'1.image={source}'],
                                 execution='cloud',allow_paid=True)
        context.assert_called_once_with('https://cloud.comfy.org','cloud')
        client.submit.assert_called_once_with(client.workflows.from_file.return_value,
            idempotency_key=receipt['idempotency_key'],api_key='test-only-not-a-real-key')
        self.assertEqual((receipt['state'],receipt['job_id']),('submitted','job-1'))
        self.assert_key_absent(self.root/'job')

    def test_local_submission_never_sends_key(self):
        # The local proxy passes extra_data on to ComfyUI, where partner nodes could spend credits.
        write_json(self.workflow,{'1':{'class_type':'LoadImage','inputs':{'image':'source.png'}},
                                  '2':{'class_type':'SaveImage','inputs':{'images':['1',0],'filename_prefix':'out'}}})
        client=self.sdk_client()
        with patch('openkatana.comfy.require_reachable'),patch('openkatana.comfy.client_at') as context:
            context.return_value.__enter__.return_value=client
            receipt=comfy.submit(self.workflow,self.root/'job','http://127.0.0.1:8189')
        context.assert_called_once_with('http://127.0.0.1:8189','local')
        client.submit.assert_called_once_with(client.workflows.from_file.return_value,idempotency_key=receipt['idempotency_key'])
        self.assertNotIn('api_key',client.submit.call_args.kwargs)
        self.assert_key_absent(self.root/'job')

    def test_unknown_cloud_submission_keeps_key_out_of_receipt_and_error(self):
        client=self.sdk_client();client.submit.side_effect=TimeoutError('read timed out')
        with patch('openkatana.comfy.client_at') as context:
            context.return_value.__enter__.return_value=client
            with self.assertRaises(TimeoutError) as raised:
                comfy.submit(self.workflow,self.root/'job','https://cloud.comfy.org',execution='cloud',allow_paid=True)
        client.submit.assert_called_once()
        self.assertEqual(client.submit.call_args.kwargs['api_key'],'test-only-not-a-real-key')
        self.assertEqual(json.loads((self.root/'job/job.json').read_text())['state'],'submission_unknown')
        self.assertNotIn('test-only-not-a-real-key',str(raised.exception))
        self.assert_key_absent(self.root/'job')

    def test_agent_tool_cloud_submission_sends_key_without_saving_it(self):
        api=AgentAPI(self.root);api.create_project('Test','project')
        project=self.root/'project';write_json(project/'workflow.json',json.loads(self.workflow.read_text()))
        client=self.sdk_client()
        with patch('openkatana.comfy.client_at') as context:
            context.return_value.__enter__.return_value=client
            result=api.submit_workflow('project','workflow.json','partner-nodes',execution='cloud',
                                       allow_paid=True,endpoint='https://cloud.comfy.org')
        self.assertEqual(client.submit.call_args.kwargs['api_key'],'test-only-not-a-real-key')
        self.assertEqual(result['receipt']['job_id'],'job-1')
        self.assert_key_absent(project)

    def test_cli_cloud_submission_sends_key_without_printing_it(self):
        from openkatana.cli import main
        client=self.sdk_client();out=StringIO()
        argv=['openkatana','comfy-submit',str(self.workflow),'--out',str(self.root/'job'),
              '--execution','cloud','--endpoint','https://cloud.comfy.org','--allow-paid']
        with patch('sys.argv',argv),patch('openkatana.comfy.client_at') as context,redirect_stdout(out):
            context.return_value.__enter__.return_value=client
            main()
        self.assertEqual(client.submit.call_args.kwargs['api_key'],'test-only-not-a-real-key')
        self.assertEqual(json.loads(out.getvalue())['job_id'],'job-1')
        self.assertNotIn('test-only-not-a-real-key',out.getvalue())
        self.assert_key_absent(self.root/'job')

    def test_video_import_records_origin_and_requires_output_selection(self):
        project=self.root/'project';projects.create(project)
        job=self.root/'job';job.mkdir();(job/'result.mp4').write_bytes(b'fake media')
        (job/'preview.png').write_bytes(b'preview')
        outputs=[{'file':n,'sha256':digest(job/n),'type':'video' if n.endswith('mp4') else 'image'} for n in ('result.mp4','preview.png')]
        write_json(job/'job.json',{'state':'collected','job_id':'job-1','execution':'cloud',
            'workflow_sha256':'workflow-hash','assets':[],'outputs':outputs})
        with self.assertRaisesRegex(Exception,'output_file'):import_outputs(job,project)
        def prepare(source,folder):
            folder.mkdir(parents=True);(folder/'00000.png').write_bytes(b'frame')
            return {'frames_dir':str(folder),'n':1,'fps':30,'w':8,'h':8,'pattern':'%05d.png'}
        with patch('openkatana.projects.prepare',side_effect=prepare):
            asset=import_outputs(job,project,output_file='result.mp4')
        self.assertEqual(asset['kind'],'video')
        self.assertEqual(asset['provenance']['execution'],'cloud')
        self.assertEqual(asset['rights'],'review_pending')
        self.assertTrue((project/asset['clip']['frames_dir']/'comfy-origin.json').is_file())


if __name__=='__main__':unittest.main()
