import copy
import json
from pathlib import Path
import tempfile
import unittest
from openkatana.json_ops import apply
from openkatana.contracts import ContractError
from openkatana import projects
from openkatana.agent_api import AgentAPI


class OpsTests(unittest.TestCase):
    def test_copy_move_escapes_and_test(self):
        doc={'a/b':{'~key':[1,2,3]},'x':[]}
        ops=[{'op':'test','path':'/a~1b/~0key/1','value':2.0},
             {'op':'copy','from':'/a~1b/~0key/0','path':'/x/-'},
             {'op':'move','from':'/a~1b/~0key/0','path':'/a~1b/~0key/2'},
             {'op':'replace','path':'/x/0','value':7}, {'op':'remove','path':'/a~1b/~0key/1'}]
        self.assertEqual(apply(doc,ops),{'a/b':{'~key':[2,1]},'x':[7]})
        self.assertEqual(doc['a/b']['~key'],[1,2,3])

    def test_atomic_failure_and_strict_pointers(self):
        for op in ({'op':'test','path':'/flag','value':1},{'op':'remove','path':'/absent'},
                   {'op':'add','path':'/a/01','value':2},{'op':'copy','from':'/a','path':'/bad~2'},
                   {'op':'move','from':'/a','path':'/a/0'},{'op':'add','path':'/a/-','value':float('nan')}):
            doc={'flag':True,'a':[3]};before=copy.deepcopy(doc)
            with self.assertRaises(ContractError):apply(doc,[{'op':'add','path':'/added','value':1},op])
            self.assertEqual(doc,before)

    def test_revision_conflicts_writer_lock_and_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);api=AgentAPI(root);api.create_project('Test','edit')
            timeline={'canvas':{'w':64,'h':64,'fps':12,'frames':12},'clips':{},
                      'shots':[{'f0':0,'f1':12,'special':{'type':'color','color':'#112233'}}]}
            rev=projects.save(root/'edit',timeline,None)['revision']
            ops=[{'op':'replace','path':'/shots/0/special/color','value':'#ff4400'}]
            proposed=api.edit_timeline('edit',ops,rev)
            self.assertFalse(proposed['saved']);self.assertEqual(projects.state(root/'edit')['revision'],rev)
            (root/'edit/timeline.json.lock').touch()
            with self.assertRaisesRegex(ContractError,'progress'):api.edit_timeline('edit',ops,rev,True)
            (root/'edit/timeline.json.lock').unlink()
            result=api.edit_timeline('edit',ops,rev,True);self.assertTrue(result['saved'])
            self.assertNotEqual(result['revision'],rev)
            with self.assertRaisesRegex(ContractError,'changed'):api.edit_timeline('edit',ops,rev,True)
            self.assertTrue((root/'edit/history'/f'{rev}.json').is_file())
            bad=[{'op':'add','path':'/shots/0/unsupported','value':1}]
            with self.assertRaises(ContractError):api.edit_timeline('edit',bad,result['revision'],True)
            self.assertEqual(projects.state(root/'edit')['revision'],result['revision'])
