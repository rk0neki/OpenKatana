import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from openkatana.agent_api import AgentAPI,TOOLS
from openkatana.contracts import ContractError
from openkatana.render import write_json

class AgentTests(unittest.TestCase):
    def setUp(self):
        parent=Path(__file__).resolve().parents[1]/'work';parent.mkdir(exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=parent);self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.api=AgentAPI(self.root)
    def test_project_boundaries_and_existing_project(self):
        with self.assertRaises(ContractError):self.api.create_project('bad','../outside')
        self.api.create_project('one','one')
        with self.assertRaises(FileExistsError):self.api.create_project('duplicate','one')
        self.assertIsNone(self.api.get_project('one')['revision'])
    def test_dispatch_is_explicit(self):
        self.assertEqual({t['name'] for t in self.api.catalog()},set(TOOLS))
        with self.assertRaises(ContractError):self.api.call('_source',{'source':'secret'})
    def test_comfy_unknown_submission_is_not_retried(self):
        self.api.create_project('one','one');root=self.root/'one'
        write_json(root/'graph.json',{'1':{'class_type':'EmptyImage','inputs':{}}})
        calls=[]
        def unknown(workflow,directory,*args):
            calls.append(directory);directory.mkdir()
            write_json(directory/'job.json',{'state':'submission_unknown','job_id':None})
            raise TimeoutError('response lost')
        with patch('openkatana.comfy.submit',side_effect=unknown):
            with self.assertRaises(TimeoutError):self.api.submit_workflow('one','graph.json','once')
            result=self.api.submit_workflow('one','graph.json','once')
        self.assertEqual(result['receipt']['state'],'submission_unknown');self.assertEqual(len(calls),1)
        write_json(root/'graph.json',{'1':{'class_type':'EmptyImage','inputs':{'width':10}}})
        with self.assertRaisesRegex(ContractError,'different'):self.api.submit_workflow('one','graph.json','once')

if __name__=='__main__':unittest.main()
